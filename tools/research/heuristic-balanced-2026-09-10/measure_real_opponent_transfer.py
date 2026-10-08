#!/usr/bin/env python3
"""真实对手迁移核查：把"局部决策已接近上限"的结论从模拟外推到真实牌局。

两个同口径数据源：

- `night`：夜间自由赛战役的**真实对手**审计（每座位决策记录含完整候选事实）；
- `simulation`：本地同牌山换座模拟（V2 系对手）。

口径（只用 (普通型向听, 未见有效牌估计)，不使用七对向听——真实审计批次早于该字段）：

1. **机会空间**：摸牌窗口中有多少个候选达到该窗口最小向听（同距离候选数 ≥2 的窗口占比）；
2. **支配违规**：策略实际选择是否被另一个合法候选支配（向听不更差、有效牌不更少，且至少一项严格更好）；
3. **被支配样本定位**：给出可复盘的窗口键。

用法：
  measure_real_opponent_transfer.py night --main-root <主仓根> --output <json>
  measure_real_opponent_transfer.py simulation --roots 32 --seed-start 1310000 --output <json>
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
import glob
import gzip
import json
import sys
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, WORK.parent / 'big-hand-paths-2026-09-09')))

from lab import HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits, ROOT as WORKTREE  # noqa: E402
from hangma_bot.kernel.actions import Discard  # noqa: E402
from hangma_bot.kernel.config import TournamentConfig, TimingConfig  # noqa: E402
from hangma_bot.policy.balanced_shadow import V2BalancedShadowPolicy  # noqa: E402
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN  # noqa: E402
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy  # noqa: E402
from hangma_bot.simulation.artifacts import compute_rules_hash  # noqa: E402
from hangma_bot.simulation.engine import SimulationEngine  # noqa: E402
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice  # noqa: E402
import counterfactual_windows as cf  # noqa: E402


def production_policy():
    return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                             risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)


def signature_of(facts):
    """(向听, 有效牌估计) 二元签名；事实不完整返回 None。"""
    if not isinstance(facts, dict):
        return None
    if facts.get('fact_kind') != 'hand_progress' or facts.get('completeness') != 'complete':
        return None
    shanten = facts.get('shanten_after')
    if not isinstance(shanten, int):
        return None
    outs = sum(tile.get('remaining_estimate', 0) for tile in (facts.get('useful_tiles') or []))
    return shanten, outs


def dominated(a, b):
    """b 是否支配 a（向听不更差、有效牌不更少，且至少一项严格更好）。"""
    if a == b:
        return False
    return b[0] <= a[0] and b[1] >= a[1] and (b[0] < a[0] or b[1] > a[1])


def analyse_window(candidates, chosen_key, bucket, samples):
    """candidates: [(action_key, (shanten, outs))]；返回是否支配违规。"""
    known = [(key, sig) for key, sig in candidates if sig is not None]
    if len(known) < 2:
        bucket['候选不足(单候选)'] += 1
        return
    bucket['窗口数'] += 1
    best_shanten = min(sig[0] for _, sig in known)
    tied = [key for key, sig in known if sig[0] == best_shanten]
    bucket['同距离候选≥2的窗口'] += 1 if len(tied) >= 2 else 0
    chosen = next((sig for key, sig in known if key == chosen_key), None)
    if chosen is None:
        bucket['所选不在候选集'] += 1
        return
    dominators = [key for key, sig in known if dominated(chosen, sig)]
    if dominators:
        bucket['所选被支配'] += 1
        if len(samples) < 20:
            samples.append(dict(chosen=chosen_key, chosen_sig=list(chosen),
                                dominator=dominators[0],
                                dominator_sig=list(next(sig for key, sig in known if key == dominators[0]))))


def night(main_root: Path, output: Path | None):
    pattern = str(main_root / 'artifacts/sessions/auto-match-a_*/audit/runs/*/participants/u_13495c3d79c8/decisions.jsonl')
    files = sorted(glob.glob(pattern))
    bucket = collections.Counter()
    samples = []
    for path in files:
        inputs = {}
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = record.get('kind')
                context = record.get('context') or {}
                decision_id = context.get('decision_id')
                if kind == 'decision_input':
                    window = (record['payload'].get('window') or {})
                    if window.get('phase') != 'draw':
                        continue
                    request = record['payload']['request']
                    rules = request.get('rules') or {}
                    candidates = []
                    for candidate in rules.get('legal_candidates') or []:
                        action = candidate.get('action') or {}
                        if action.get('kind') != 'discard':
                            continue
                        candidates.append((candidate.get('action_key'), signature_of(candidate.get('facts'))))
                    inputs[decision_id] = dict(window=window, candidates=candidates)
                elif kind == 'decision_planned' and decision_id in inputs:
                    plan = record['payload'].get('returned_plan') or {}
                    ranked = plan.get('candidates') or record['payload'].get('candidates') or []
                    if not ranked:
                        continue
                    analyse_window(inputs[decision_id]['candidates'], ranked[0].get('action_key'), bucket, samples)
                    inputs.pop(decision_id, None)
    report = dict(source='night(真实对手)', files=len(files), stats=dict(bucket), samples=samples[:10])
    return report


def simulation(roots: int, seed_start: int, output: Path | None):
    rules = HangmaRules(RuleConfig('hangma-mvp-v10-public-counts', 1, False))
    engine = SimulationEngine(rules, rules_hash=compute_rules_hash(WORKTREE))
    policy = production_policy()
    opponent = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    bucket = collections.Counter()
    samples = []
    for index in range(roots):
        spec = MatchSpec(match_id='transfer-{0}'.format(index), scenario_id='transfer-{0}'.format(index),
                         config=TournamentConfig(1, 8, rules.config, TimingConfig(1, 1, 3)),
                         seed=seed_start + index, initial_dealer=index % 4, initial_scores=(0, 0, 0, 0))
        world = engine.start(spec)
        for _ in range(20000):
            frame = engine.frame(world)
            if frame.final_scores is not None:
                break
            for decision in frame.decisions:
                obs = decision.observation
                if obs.seat != 0 or obs.phase != 'draw':
                    continue
                analysis = rules.analyze(obs, value_limits=ValueAnalysisLimits())
                candidates = [(c.action_key, signature_of({
                    'fact_kind': 'hand_progress' if c.facts is not None else None,
                    'completeness': str(getattr(c.facts, 'completeness', '')).split('.')[-1].lower(),
                    # 与夜间审计同口径：用综合向听（min(普通型, 七对)）。夜间批次
                    # 早于 standard_shanten_after 字段拆分，记录里的 shanten_after
                    # 就是综合值；混用两种语义会得出不可比的支配率。
                    'shanten_after': getattr(c.facts, 'shanten_after', None),
                    'useful_tiles': [{'remaining_estimate': t.remaining_estimate}
                                     for t in (getattr(c.facts, 'useful_tiles', ()) or ())]}))
                              for c in analysis.legal_candidates if isinstance(c.action, Discard)]
                plan = asyncio.run(policy.choose(cf.request_for(rules, decision, 'transfer'),
                                                 cf.DecisionBudget(10, 11, 12)))
                analyse_window(candidates, plan.candidates[0].action_key, bucket, samples)
            choices = []
            for decision in frame.decisions:
                obs = decision.observation
                active = policy if obs.seat == 0 else opponent
                plan = asyncio.run(active.choose(cf.request_for(rules, decision, 'transfer'),
                                                 cf.DecisionBudget(10, 11, 12)))
                choices.append(SimulationChoice(decision.window_key, plan.candidates[0].action))
            world = engine.advance(world, frame.revision, tuple(choices))
    return dict(source='simulation(V2 对手)', roots=roots, stats=dict(bucket), samples=samples[:10])


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    night_parser = sub.add_parser('night')
    night_parser.add_argument('--main-root', type=Path, required=True)
    night_parser.add_argument('--output', type=Path)
    simulation_parser = sub.add_parser('simulation')
    simulation_parser.add_argument('--roots', type=int, default=32)
    simulation_parser.add_argument('--seed-start', type=int, default=1310000)
    simulation_parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = night(args.main_root, args.output) if args.command == 'night' else simulation(args.roots, args.seed_start, args.output)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + chr(10)
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    main()
