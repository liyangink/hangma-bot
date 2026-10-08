#!/usr/bin/env python3
"""G93：同不可变世界的合法弃牌双分支单局结算恒等预检。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROOT / "review/llm-guided-heuristic-route-2026-09-15/tools"),
             _project_file(_PROJECT_ROOT, ROOT / "review/r18-four-arm-evaluation-2026-09-23"), HERE):
    sys.path.insert(0, str(path))

import sitin_natural_panel as natural  # noqa: E402
import paired_study as paired  # noqa: E402
from g13_hand_accounting import HandAccountingEngine  # noqa: E402
from hangma_bot import bootstrap  # noqa: E402
from hangma_bot.application.deadline import BudgetPolicy, ManualClock  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.actions import WindowPhase  # noqa: E402
from hangma_bot.kernel.serialization import window_key_to_json  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    MatchDriverConfig, drive_match, frame_observation_summary, resume_match,
)
from hangma_bot.simulation.interface import SimulationFrame  # noqa: E402


G89 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g89-g88-hm-development-20260928')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G93-SAME-HAND-BRANCH-PREFLIGHT-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g93-same-hand-branch-preflight-20260928/result.json')


def sha(path: Path) -> str:
    """绑定面板、规则和预检程序的内容身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CaptureEngine:
    """透明转发模拟器公开接口；仅暂存同一进程的不可变世界引用。"""

    def __init__(self, inner: HandAccountingEngine) -> None:
        self.inner = inner
        self.latest_world: Any = None

    def start(self, spec: Any) -> Any:
        return self.inner.start(spec)

    def frame(self, world: Any) -> SimulationFrame:
        self.latest_world = world
        return self.inner.frame(world)

    def advance(self, world: Any, revision: int, choices: Any) -> Any:
        return self.inner.advance(world, revision, choices)


class CapturePolicy:
    """只从合法可见请求选第一个同向听弃牌分歧，不改父代返回。"""

    def __init__(self, inner: Any, engine: CaptureEngine) -> None:
        self.inner = inner
        self.engine = engine
        self.policy_id = getattr(inner, "policy_id", None)
        self.world: Any = None
        self.request: Any = None
        self.parent_key: str | None = None
        self.alternate_key: str | None = None
        self.facts: dict[str, dict] = {}

    async def choose(self, request: Any, budget: Any) -> Any:
        plan = await self.inner.choose(request, budget)
        if self.world is not None or request.window_key.phase is not WindowPhase.DRAW:
            return plan
        observation = request.observation
        if not any(meld.kind in ("chi", "peng")
                   for meld in observation.melds[observation.seat]):
            return plan
        if not plan.candidates or not plan.candidates[0].action_key.startswith("discard:"):
            return plan
        entries = {candidate.action_key: candidate.facts
                   for candidate in request.rules.legal_candidates}
        parent = plan.candidates[0].action_key
        first = entries.get(parent)
        if first is None or type(first.standard_shanten_after) is not int:
            return plan

        def useful(key: str) -> tuple[int, int]:
            """公开未见有效牌的码数与容量，绝不读取真实牌墙。"""
            tiles = entries[key].standard_useful_tiles
            return len(tiles or ()), sum(tile.remaining_estimate for tile in (tiles or ()))

        alternates = [ranked.action_key for ranked in plan.candidates[1:]
                      if ranked.action_key.startswith("discard:")
                      and entries.get(ranked.action_key) is not None
                      and entries[ranked.action_key].standard_shanten_after ==
                      first.standard_shanten_after]
        if not alternates:
            return plan
        alternate = min(alternates, key=lambda key: (-useful(key)[0], -useful(key)[1], key))
        if self.engine.latest_world is None:
            raise ValueError("G93 目标窗口未取得同帧不可变世界")
        self.world = self.engine.latest_world
        self.request = request
        self.parent_key = parent
        self.alternate_key = alternate
        self.facts = {key: {"standard_shanten_after": entries[key].standard_shanten_after,
                            "ordinary_codes": useful(key)[0],
                            "public_unseen_capacity": useful(key)[1]}
                      for key in (parent, alternate)}
        return plan


class ForceOncePolicy:
    """仅在冻结 WindowKey 把既有合法候选移到首位，其他窗口保持父代。"""

    def __init__(self, inner: Any, target: Any, forced_key: str) -> None:
        self.inner = inner
        self.target = target
        self.forced_key = forced_key
        self.policy_id = getattr(inner, "policy_id", None)
        self.used = 0

    async def choose(self, request: Any, budget: Any) -> Any:
        plan = await self.inner.choose(request, budget)
        if request.window_key != self.target:
            return plan
        if self.used:
            raise ValueError("G93 目标窗口重复调用")
        chosen = next((item for item in plan.candidates
                       if item.action_key == self.forced_key), None)
        if chosen is None or self.forced_key not in {
                item.action_key for item in request.rules.legal_candidates}:
            raise ValueError("G93 强制动作不在本次合法表")
        reordered = (chosen,) + tuple(item for item in plan.candidates
                                        if item.action_key != self.forced_key)
        self.used += 1
        return replace(plan, candidates=tuple(replace(item, rank=index)
                                               for index, item in enumerate(reordered, 1)))


class SingleHandEngine:
    """从同一世界续打；完成目标单局时以公开结算构造研究终点。"""

    def __init__(self, inner: Any, target_round: int) -> None:
        self.inner = inner
        self.target_round = target_round
        self.exported_hand: dict | None = None

    def frame(self, world: Any) -> SimulationFrame:
        base = self.inner.frame(world)
        if base.completed_hands < self.target_round:
            return base
        if self.exported_hand is None:
            self.exported_hand = self.inner.export_hand(world, self.target_round)
        return SimulationFrame(
            revision=base.revision, decisions=(),
            completed_hands=base.completed_hands,
            final_scores=tuple(self.exported_hand["scores_after"]), blocked_reason=None)

    def advance(self, world: Any, revision: int, choices: Any) -> Any:
        return self.inner.advance(world, revision, choices)


def runtime_for(plan: Any, versions: dict) -> tuple[Any, Any, HangmaRules]:
    """逐项复用 G13/G89 的组合根装配，不另建规则或牌墙。"""
    rules_config = natural.RuleConfig(
        ruleset_version=str(versions["ruleset_version"]),
        base_score=int(versions["base_score"]),
        you_cai_bi_kao=bool(versions["you_cai_bi_kao"]))
    tournament_config = natural.TournamentConfig(
        max_games=1, rounds_per_game=int(versions["rounds_per_game"]),
        rules=rules_config,
        timing=natural.TimingConfig(**dict(natural.stage.DEFAULT_TIMING)))
    runtime = getattr(bootstrap, natural.BOOTSTRAP_RUNTIME_HOOK)(
        "matches", natural.MatchExperiment(
            kind="matches", clock_mode=str(versions["clock_mode"]),
            baseline=natural.PolicyDeclaration(policy_id="natural-slot-a", name="panel", weights=()),
            challenger=natural.PolicyDeclaration(policy_id="natural-slot-b", name="panel", weights=()),
            opponents=tuple(natural.PolicyDeclaration(
                policy_id=f"natural-slot-{index}", name="panel", weights=())
                for index in (3, 4, 5)),
            tournament_config=tournament_config,
            seeds=(natural.MatchSeedSpec(seed=plan.seed, scenario_id=plan.scenario_id),),
            seat_permutations=(natural.stage.IDENTITY_PERMUTATION,),
            initial_dealer=0, initial_scores=(0, 0, 0, 0)))
    spec = runtime["spec_factory"](
        match_id=plan.match_id, scenario_id=plan.scenario_id,
        config=tournament_config, seed=plan.seed,
        initial_dealer=plan.initial_dealer, initial_scores=[0, 0, 0, 0])
    return runtime, spec, HangmaRules(rules_config)


def policies_for(plan: Any, contract: dict, clock: ManualClock) -> tuple[Any, ...]:
    """按 G89 的物理座位装配冻结 R18 v2 和同池三家策略。"""
    logical = natural.arm_logical_policies(
        arm="candidate", candidate_scorer=None,
        logical_participants=plan.logical_participants,
        opponent_policies=contract["panel"]["opponent_scenarios"]["H"]["opponent_policies"],
        monotonic=clock.now,
        candidate_policy_factory=paired.policy_factory("r18_v2"))
    return natural.seat_policies_from(
        logical, plan.permutation, plan.logical_participants)


def run_full(plan: Any, contract: dict, versions: dict) -> tuple[dict, Any, Any, Any, Any]:
    """完整运行一个旧父代桌并捕获首个合格目标；仅用于量具恒等对照。"""
    runtime, spec, rules = runtime_for(plan, versions)
    inner = HandAccountingEngine(runtime["engine"])
    capture_engine = CaptureEngine(inner)
    clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
    policies = list(policies_for(plan, contract, clock))
    focal_seat = plan.seats().index(natural.FOCAL_PARTICIPANT)
    captured = CapturePolicy(policies[focal_seat], capture_engine)
    policies[focal_seat] = captured
    situation = natural.build_stage_situation(
        plan=plan, table_no=1, tables_completed=0, totals={}, place_totals={},
        rounds_per_game=int(versions["rounds_per_game"]))
    config = MatchDriverConfig(
        clock_mode=str(versions["clock_mode"]),
        step_limit=int(contract["stop"]["step_limit"]),
        budget_policy=BudgetPolicy(), competition_tournament_id=plan.scenario_id)
    outcome = asyncio.run(drive_match(
        engine=capture_engine, spec=spec, policies_by_seat=tuple(policies),
        rules=rules, choice_factory=runtime["choice_factory"],
        config=config, now_monotonic=clock.now, wall_clock=None,
        value_limits=paired.LIMITS, stage_situation=situation))
    if outcome.status != "complete" or len(inner.hands) != 8:
        raise ValueError("G93 原父代桌未完整完成")
    old_unit = ("H", 1, focal_seat, "r18_v2", 2026110801)
    archived = json.loads(paired.unit_path(G89, old_unit).read_text(encoding="utf-8"))
    expected = archived["stage"]["tables"][0]["scores_by_seat"]
    if list(outcome.final_scores or ()) != expected:
        raise ValueError("G93 未分叉桌与 G89 冻结终分不符")
    return {"final_scores": list(outcome.final_scores), "hands": inner.hands,
            "decisions": outcome.decisions}, captured, runtime, rules, situation


def run_branch(*, captured: CapturePolicy, plan: Any, contract: dict,
               versions: dict, runtime: dict, rules: HangmaRules,
               situation: Any, forced_key: str | None) -> dict:
    """从同一保存世界只续打目标单局；另一臂仅一次替换合法弃牌。"""
    if captured.world is None or captured.request is None:
        raise ValueError("G93 未捕获合法目标")
    target_round = captured.request.window_key.round_no
    single = SingleHandEngine(runtime["engine"], target_round)
    clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
    policies = list(policies_for(plan, contract, clock))
    focal = captured.request.window_key.seat
    force = None
    if forced_key is not None:
        force = ForceOncePolicy(policies[focal], captured.request.window_key, forced_key)
        policies[focal] = force
    snapshot = {"observation_summary": frame_observation_summary(
        runtime["engine"].frame(captured.world)),
        "match_spec": {"match_id": plan.match_id}}
    config = MatchDriverConfig(
        clock_mode=str(versions["clock_mode"]),
        step_limit=int(contract["stop"]["step_limit"]),
        budget_policy=BudgetPolicy(), competition_tournament_id=plan.scenario_id)
    outcome = asyncio.run(resume_match(
        engine=single, world=captured.world, policies_by_seat=tuple(policies),
        rules=rules, choice_factory=runtime["choice_factory"],
        config=config, now_monotonic=clock.now, wall_clock=None,
        stage_snapshot=snapshot,
        remaining_schedule={"declared_endpoint": "target_round_settlement"},
        value_limits=paired.LIMITS, stage_situation=situation))
    if outcome.status != "complete" or single.exported_hand is None:
        raise ValueError("G93 单局续打未完整结算")
    if force is not None and force.used != 1:
        raise ValueError("G93 备选弃牌未恰好强制一次")
    runtime_counts = asdict(outcome.runtime_counts)
    if any(runtime_counts.get(key, 0) for key in
           ("fallbacks", "illegal_choices", "timeouts")):
        raise ValueError("G93 单局续打发生降级、非法动作或超时")
    hand = single.exported_hand
    return {"hand": {name: hand[name] for name in
                     ("round_no", "hand_id", "scores_before", "scores_after",
                      "score_delta", "winner_seat", "is_draw", "fan", "details")},
            "decision_count": len(outcome.decisions),
            "first_decision_action": outcome.decisions[0].action_key,
            "runtime_counts": runtime_counts,
            "forced_once": force.used if force is not None else 0}


def main() -> None:
    """结果盲找窗、双分支恒等验证并只保存公开事实与单局结算。"""
    if OUT.exists():
        raise FileExistsError("G93 证据已存在，拒绝覆盖")
    contract = json.loads(paired.CONTRACT.read_text(encoding="utf-8"))
    versions = natural.stage.contract_versions_block(contract)
    found = None
    for seat in range(4):
        plan = natural.build_seat_stage_plans(
            contract=contract, opponent="H", root_index=1, focal_seat=seat,
            panel_seed=2026110801)[0]
        full, captured, runtime, rules, situation = run_full(plan, contract, versions)
        if captured.world is not None:
            found = (plan, full, captured, runtime, rules, situation)
            break
    if found is None:
        raise ValueError("G93 预定根四座均无同向听已吃碰弃牌分歧")
    plan, full, captured, runtime, rules, situation = found
    parent = run_branch(captured=captured, plan=plan, contract=contract,
                        versions=versions, runtime=runtime, rules=rules,
                        situation=situation, forced_key=None)
    alternate = run_branch(captured=captured, plan=plan, contract=contract,
                           versions=versions, runtime=runtime, rules=rules,
                           situation=situation, forced_key=captured.alternate_key)
    target_round = captured.request.window_key.round_no
    old_hand = full["hands"][target_round - 1]
    for key in ("round_no", "hand_id", "scores_before", "scores_after", "score_delta",
                "winner_seat", "is_draw", "fan", "details"):
        if parent["hand"][key] != old_hand[key]:
            raise ValueError("G93 父代同世界续打与完整原局不恒等：" + key)
    if parent["first_decision_action"] != captured.parent_key:
        raise ValueError("G93 父代续打首动作漂移")
    if alternate["first_decision_action"] != captured.alternate_key:
        raise ValueError("G93 备选续打首动作漂移")
    before = parent["hand"]["scores_before"]
    for row in (parent, alternate):
        hand = row["hand"]
        if hand["scores_before"] != before or sum(hand["score_delta"]) != 0:
            raise ValueError("G93 双分支起始积分或结算守恒失败")
    result = {"schema": "g93-same-hand-branch-preflight/1",
              "experiment": "smoke_only_not_candidate_value",
              "input_sha256": {"prereg": sha(PREREG), "script": sha(Path(__file__)),
                               "contract": sha(paired.CONTRACT),
                               "g89_manifest": sha(_project_file(_PROJECT_ROOT, G89 / "manifest.json"))},
              "table_id": plan.table_id, "seed": plan.seed,
              "target_window": window_key_to_json(captured.request.window_key),
              "parent_action": captured.parent_key,
              "alternate_action": captured.alternate_key,
              "visible_action_facts": captured.facts,
              "branch_observation_summary_sha256": hashlib.sha256(json.dumps(
                  frame_observation_summary(runtime["engine"].frame(captured.world)),
                  ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
              "full_table_scores_match_g89": True,
              "parent_hand_matches_full_run": True,
              "parent": parent, "alternate": alternate,
              "boundary": "同一个历史隐藏世界的单一窗口预检；实际策略不能读取世界，"
                          "单次结算不代表牌墙分布、整桌收益或独立确认。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"table_id": plan.table_id,
                      "target": result["target_window"],
                      "parent_action": captured.parent_key,
                      "alternate_action": captured.alternate_key,
                      "parent_score_delta": parent["hand"]["score_delta"],
                      "alternate_score_delta": alternate["hand"]["score_delta"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
