#!/usr/bin/env python3
"""F-1 侦察：单白局里，我们有多少次放弃了"爆头就绪"的弃牌？

背景：提案 F-1（单白局路线专项）的第一步是"重放单白局，比较实际弃牌与白单吊/嵌入
替代路线"。爆头（摸任意一张即胡）是该路线的终点状态，其判定由规则侧唯一来源
hand_analysis.any_tile_win 给出（摸前 13-3*副露数 张暗牌 + 任意一张种类都成胡）。

本工具不改任何策略行为，只在固定牌山上包一层探针：

- 取样窗口：摸牌相位、手牌恰好一张白、存在弃牌候选；
- 对每个弃牌候选，扣除该张后的暗牌喂给 any_tile_win，得到"弃这一张会不会进爆头"；
- 记录实际选择是否就绪、是否存在**就绪却没选**的窗口（机会缺口）。

只做测量，不下结论；也不声称"选了就绪路线一定更好"（放弃向听/安全另有代价）。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
import collections
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
sys.path.insert(0, str(WORK))

from gate_candidate import ValuesWhenNeeded, build_policy  # noqa: E402
from lab import ROOT, RULESET, HangmaRules, RuleConfig  # noqa: E402
from hangma_bot.application.deadline import BudgetPolicy  # noqa: E402
from hangma_bot.hangma.hand_analysis import any_tile_win  # noqa: E402
from hangma_bot.kernel.actions import Discard  # noqa: E402
from hangma_bot.kernel.config import TournamentConfig, TimingConfig  # noqa: E402
from hangma_bot.offline.evaluate import (MatchExperiment, PolicyDeclaration, MatchSeedSpec,  # noqa: E402
                                         run_match_experiment)
from hangma_bot.simulation.artifacts import compute_rules_hash  # noqa: E402
from hangma_bot.simulation.engine import SimulationEngine  # noqa: E402
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice  # noqa: E402

HANDS_PER_TABLE = 8
ROTATIONS = ((0, 1, 2, 3),)


class BaotouProbePolicy:
    """包一层：先问被测策略，再独立评估"每个弃牌候选是否进爆头"。"""

    def __init__(self, inner):
        self._inner = inner
        self.records = []

    async def choose(self, request, budget):
        plan = await self._inner.choose(request, budget)
        try:
            self._probe(request, plan)
        except Exception as error:  # 探针失败绝不影响决策
            self.records.append(dict(error=type(error).__name__ + ":" + str(error)[:120]))
        return plan

    def _probe(self, request, plan):
        obs = request.observation
        if obs.phase != "draw" or obs.drawn_tile is None:
            return
        hand = tuple(obs.my_hand)  # 字段名是 my_hand；曾误写 hand 导致每窗 AttributeError
        # 财神牌码固定为「白」；不用内部 is_wealth，避免依赖规则包的私有模块。
        if sum(1 for tile in hand if tile.code == "白") != 1:
            return
        meld_count = len(obs.melds[obs.seat])
        # 摸牌相位：my_hand 是不含当前摸牌的暗牌，摸到的那张要一起进池子，
        # 否则"弃掉刚摸的牌"会 remove 失败（曾整批报 ValueError）。
        base = list(hand) + [obs.drawn_tile]
        if len(base) != 14 - 3 * meld_count:
            return
        # 候选来自**计划**：RuleAnalysis 只给事实，合法候选经底座策略排成 DecisionPlan。
        candidates = [item for item in plan.candidates
                      if isinstance(item.action, Discard)]
        if not candidates:
            return
        ready_actions = []
        for item in candidates:
            after = list(base)
            after.remove(item.action.tile)
            if any_tile_win(tuple(sorted(after)), meld_count):
                ready_actions.append(item.action_key)
        chosen = plan.candidates[0].action_key if plan.candidates else None
        self.records.append(dict(
            ready=sorted(ready_actions),
            ready_count=len(ready_actions),
            candidate_count=len(candidates),
            chosen=chosen,
            chosen_ready=chosen in ready_actions))


def root_run(item):
    candidate_name, index, seed, prefix = item
    raw = HangmaRules(RuleConfig(RULESET, 1, False))
    rules_hash = compute_rules_hash(ROOT)
    config = TournamentConfig(1, HANDS_PER_TABLE, raw.config, TimingConfig(1, 1, 3))
    probe = BaotouProbePolicy(build_policy(candidate_name))
    # MatchExperiment 要求基线/候选的 policy_id 不同；这里两臂桌型相同（探针 1 席 + 3 名 V2），
    # 因此用两个标签指向**同一个探针实例**，记录合并到同一份里。
    policies = {"probe-a": probe, "probe-b": probe,
                "opp-1": build_policy("weighted_heuristic_v2"),
                "opp-2": build_policy("weighted_heuristic_v2"),
                "opp-3": build_policy("weighted_heuristic_v2")}
    experiment = MatchExperiment(
        "matches", "logical", PolicyDeclaration("probe-a", candidate_name),
        PolicyDeclaration("probe-b", candidate_name),
        tuple(PolicyDeclaration(pid, "weighted_heuristic_v2")
              for pid in ("opp-1", "opp-2", "opp-3")), config,
        (MatchSeedSpec(seed, "{0}-{1}".format(prefix, index)),), ROTATIONS, index % 4,
        (0, 0, 0, 0), simulation_version="simulation-v1", match_id_prefix=prefix)
    engine = SimulationEngine(raw, rules_hash=rules_hash)
    asyncio.run(run_match_experiment(
        experiment, engine=engine, spec_factory=MatchSpec, choice_factory=SimulationChoice,
        policies_by_id=policies, rules=ValuesWhenNeeded(raw), rules_hash=rules_hash,
        now_monotonic=lambda: 0, wall_clock=None, budget_policy=BudgetPolicy()))
    return probe.records, list()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default="v2_hu_upgrade_v1")
    parser.add_argument("--roots", type=int, default=64)
    parser.add_argument("--seed-start", type=int, default=1360000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--scenario-prefix", default="gate")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    directory = Path(args.out)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [(args.candidate, i, args.seed_start + i, args.scenario_prefix)
                for i in range(args.roots)]
        for index, (rows, _bad) in enumerate(pool.map(root_run, jobs)):
            records.extend(rows)
            if (index + 1) % 16 == 0:
                print("baotou-probe", index + 1, "/", args.roots, "windows", len(records), flush=True)
    windows = [r for r in records if "ready" in r]
    errors = [r for r in records if "error" in r]
    any_ready = [r for r in windows if r["ready_count"] > 0]
    chosen_ready = [r for r in windows if r["chosen_ready"]]
    missed = [r for r in any_ready if not r["chosen_ready"]]
    summary = dict(schema="baotou-probe/1", candidate=args.candidate, roots=args.roots,
                   single_white_windows=len(windows), probe_errors=len(errors),
                   windows_with_a_ready_discard=len(any_ready),
                   chosen_is_ready=len(chosen_ready),
                   missed_ready=len(missed),
                   missed_rate=(len(missed) / len(any_ready)) if any_ready else None,
                   ready_hit_rate=(len(chosen_ready) / len(any_ready)) if any_ready else None,
                   error_samples=dict(collections.Counter(
                       r["error"] for r in errors).most_common(5)),
                   ready_count_dist=dict(collections.Counter(
                       str(r["ready_count"]) for r in windows)))
    (directory / "baotou-probe.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
