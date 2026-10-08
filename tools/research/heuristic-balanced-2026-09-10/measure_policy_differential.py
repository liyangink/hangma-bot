#!/usr/bin/env python3
"""策略差分：同一批同牌山窗口上比较两个策略的实际选择，量化行为差异。

用途：在花门禁成本之前先回答"候选到底改了多少动作"。逐窗口记录两档选择、
差异计数与差异样例（含策略给出的理由），并给出差异窗口的自然频率。
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
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, WORK.parent / 'big-hand-paths-2026-09-09')))

from lab import ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import TournamentConfig, TimingConfig  # noqa: E402
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN  # noqa: E402
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy  # noqa: E402
from hangma_bot.simulation.artifacts import compute_rules_hash  # noqa: E402
from hangma_bot.simulation.engine import SimulationEngine  # noqa: E402
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice  # noqa: E402
import counterfactual_windows as cf  # noqa: E402


def build(name):
    if name == 'v2_hu_upgrade_v1':
        return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                 risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
    if name == 'v2_hu_upgrade_tierb_v1':
        from hangma_bot.policy.hu_upgrade_tierb import HuUpgradeTierBPolicy
        return HuUpgradeTierBPolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                    risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
    if name == 'v2_value_upgrade_v1':
        from hangma_bot.policy.v2_value_upgrade import V2ValueUpgradePolicy
        return V2ValueUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                    risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
    if name == 'v2_hu_upgrade_dealer_v1':
        from hangma_bot.policy.v2_hu_upgrade_dealer import V2HuUpgradeDealerPolicy
        return V2HuUpgradeDealerPolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                       risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
    if name == 'v2_hu_upgrade_risk_v3':
        from hangma_bot.policy.hu_upgrade_calibration import (
            RISK_CELLS_V3, RISK_VERSION_V3, SAFETY_MARGIN_V3)
        return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS_V3,
                                 risk_version=RISK_VERSION_V3, safety_margin=SAFETY_MARGIN_V3)
    if name == 'v2_hu_upgrade_dealer_v2':
        from hangma_bot.policy.v2_hu_upgrade_dealer import (
            DEALER_WEIGHTS_V2, V2HuUpgradeDealerPolicy)
        return V2HuUpgradeDealerPolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                       risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN,
                                       dealer_weights=DEALER_WEIGHTS_V2)
    if name == 'v2_hu_upgrade_tierb_v3':
        from hangma_bot.policy.hu_upgrade_calibration import (
            RISK_CELLS_V3, RISK_VERSION_V3, SAFETY_MARGIN_V3)
        from hangma_bot.policy.hu_upgrade_tierb import HuUpgradeTierBPolicy
        return HuUpgradeTierBPolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS_V3,
                                    risk_version=RISK_VERSION_V3, safety_margin=SAFETY_MARGIN_V3)
    if name == 'risk_v3_lossfree':
        # 诊断用：保留 v3 的庄闲分离与 band2 floor 调整，但把绝对支付归零，
        # 用来分离"支付项改错"与"其余改动本来也无效"两种解释。
        from dataclasses import replace as _replace
        from hangma_bot.policy.hu_upgrade_calibration import (
            RISK_CELLS_V3, RISK_VERSION_V3, SAFETY_MARGIN_V3)
        cells = tuple(_replace(c, loss_absolute=0.0) for c in RISK_CELLS_V3)
        return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=cells,
                                 risk_version=RISK_VERSION_V3 + "-lossfree",
                                 safety_margin=SAFETY_MARGIN_V3)
    if name == 'weighted_heuristic_v2':
        return ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    raise ValueError('未登记策略 ' + name)


def main(baseline_name, candidate_name, roots, seed_start, output):
    rules = HangmaRules(RuleConfig(RULESET, 1, False))
    engine = SimulationEngine(rules, rules_hash=compute_rules_hash(ROOT))
    baseline = build(baseline_name)
    candidate = build(candidate_name)
    opponent = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    stats = collections.Counter()
    actions = collections.defaultdict(collections.Counter)
    samples = []
    for index in range(roots):
        spec = MatchSpec(match_id='diff-{0}'.format(index), scenario_id='diff-{0}'.format(index),
                         config=TournamentConfig(1, 8, rules.config, TimingConfig(1, 1, 3)),
                         seed=seed_start + index, initial_dealer=index % 4, initial_scores=(0, 0, 0, 0))
        world = engine.start(spec)
        for _ in range(20000):
            frame = engine.frame(world)
            if frame.final_scores is not None:
                break
            choices = []
            for decision in frame.decisions:
                obs = decision.observation
                if obs.seat == 0:
                    request = cf.request_for(rules, decision, 'diff')
                    stats['窗口数'] += 1
                    plan_a = asyncio.run(baseline.choose(request, cf.DecisionBudget(10, 11, 12)))
                    plan_b = asyncio.run(candidate.choose(request, cf.DecisionBudget(10, 11, 12)))
                    key_a = plan_a.candidates[0].action_key
                    key_b = plan_b.candidates[0].action_key
                    actions[baseline_name][key_a.split(':')[0]] += 1
                    actions[candidate_name][key_b.split(':')[0]] += 1
                    if obs.dealer_seat == obs.seat:
                        actions[baseline_name + '·庄'][key_a.split(':')[0]] += 1
                        actions[candidate_name + '·庄'][key_b.split(':')[0]] += 1
                    if key_a != key_b:
                        stats['差异窗口'] += 1
                        stats['差异-{0}'.format(str(obs.phase))] += 1
                        if len(samples) < 12:
                            samples.append(dict(round_no=obs.round_no, phase=str(obs.phase),
                                                remaining=obs.remaining_tile_count,
                                                baseline=key_a, candidate=key_b,
                                                candidate_reason=plan_b.candidates[0].reasons[-1][:200]))
                    choices.append(SimulationChoice(decision.window_key, plan_b.candidates[0].action))
                else:
                    plan = asyncio.run(opponent.choose(cf.request_for(rules, decision, 'diff'),
                                                       cf.DecisionBudget(10, 11, 12)))
                    choices.append(SimulationChoice(decision.window_key, plan.candidates[0].action))
            world = engine.advance(world, frame.revision, tuple(choices))
    windows = stats['窗口数']
    report = dict(baseline=baseline_name, candidate=candidate_name, roots=roots,
                  seed_range=[seed_start, seed_start + roots - 1],
                  windows=windows, differences=stats['差异窗口'],
                  difference_rate=(stats['差异窗口'] / windows) if windows else None,
                  by_phase={k: v for k, v in stats.items() if k.startswith('差异-')},
                  action_distribution={name: dict(counts) for name, counts in actions.items()},
                  samples=samples)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + chr(10)
    if output:
        Path(output).write_text(rendered, encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--roots', type=int, default=32)
    parser.add_argument('--seed-start', type=int, default=1320000)
    parser.add_argument('--output')
    args = parser.parse_args()
    main(args.baseline, args.candidate, args.roots, args.seed_start, args.output)
