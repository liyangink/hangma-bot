#!/usr/bin/env python3
"""影子路线覆盖率探针：定位多路线签名在各过滤条件的流失点。

用途：新一批影子运行的首要验收项是"审计快照版本 + 多路线事实覆盖率"。本探针
在单根牌山上逐窗口统计：摸牌窗口数、含弃牌候选数、事实完整数、七对向听非空数、
Pareto 前沿非空数，并给出前沿规模分布。不产生收益结论。
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

import asyncio
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / 'big-hand-paths-2026-09-09')))

from lab import ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits
from run_tables import RecordingEngine
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.config import TournamentConfig, TimingConfig
from hangma_bot.offline.evaluate import (MatchExperiment, PolicyDeclaration, MatchSeedSpec,
                                         run_match_experiment)
from hangma_bot.policy.balanced_shadow import V2BalancedShadowPolicy, _pareto, _route_signature
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice

BASE = 'v2_hu_upgrade_v1'
CAND = V2BalancedShadowPolicy.VERSION
stats = Counter()
calls = Counter()
errors = []
seat_seen = Counter()
frontier_sizes = Counter()
phase_seen = Counter()
notes = 0


class Probe:
    """统计影子层每个分支的流失位置；不改变任何动作。"""

    def __init__(self, policy, label):
        self.policy, self.label = policy, label

    async def choose(self, request, budget):
        try:
            plan = await self.policy.choose(request, budget)
        except Exception as error:
            errors.append(f'{self.label}:{type(error).__name__}:{error}')
            raise
        global notes
        obs = request.observation
        calls[self.label] += 1
        seat_seen[(self.label, obs.seat, request.window_key.phase if hasattr(request,'window_key') else '?')] += 1
        phase_seen[(self.label, obs.phase)] += 1
        if self.label != 'cand' or obs.phase != 'draw':
            return plan
        stats['draw_windows'] += 1
        cands = [c for c in request.rules.legal_candidates if isinstance(c.action, Discard)]
        stats['with_discards'] += 1 if cands else 0
        complete = [c for c in cands if c.facts is not None
                    and c.facts.fact_kind is CandidateFactKind.HAND_PROGRESS
                    and c.facts.completeness is RuleCompleteness.COMPLETE]
        stats['with_complete_facts'] += 1 if complete else 0
        pairs = [c for c in complete if c.facts.standard_shanten_after is not None
                 and c.facts.seven_pairs_shanten_after is not None]
        stats['with_seven_pairs_shanten'] += 1 if pairs else 0
        no_replacement = [c for c in pairs if not c.facts.replacement_draw_unknown]
        stats['with_replacement_known'] += 1 if no_replacement else 0
        frontier = _pareto(cands)
        stats['frontier_nonempty'] += 1 if frontier else 0
        if frontier:
            frontier_sizes[len(frontier)] += 1
        if plan.candidates and any('影子路线[' in r for r in plan.candidates[0].reasons):
            notes += 1
        return plan


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1190000
    raw = HangmaRules(RuleConfig(RULESET, 1, False))
    rules_hash = compute_rules_hash(ROOT)
    config = TournamentConfig(1, 8, raw.config, TimingConfig(1, 1, 3))
    ids = [BASE, CAND, 'opp-v2-1', 'opp-v2-2', 'opp-v2-3']
    policies = {
        BASE: Probe(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS, risk_version=RISK_VERSION,
                                      safety_margin=SAFETY_MARGIN), 'base'),
        CAND: Probe(V2BalancedShadowPolicy(monotonic=lambda: 0, baseline=V2HuUpgradePolicy(monotonic=lambda: 0,
            risk_cells=RISK_CELLS, risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)), 'cand'),
        **{pid: Probe(ComparableHeuristicPolicyV2(monotonic=lambda: 0), 'opp') for pid in ids[2:]},
    }
    experiment = MatchExperiment(
        'matches', 'logical', PolicyDeclaration(BASE, BASE), PolicyDeclaration(CAND, CAND),
        tuple(PolicyDeclaration(pid, 'weighted_heuristic_v2') for pid in ids[2:]), config,
        (MatchSeedSpec(seed, 'shadow-coverage-probe'),),
        ((0, 1, 2, 3),), 0, (0, 0, 0, 0),
        simulation_version='simulation-v1', match_id_prefix='route-preserve')
    engine = RecordingEngine(SimulationEngine(raw, rules_hash=rules_hash))
    out = asyncio.run(run_match_experiment(
        experiment, engine=engine, spec_factory=MatchSpec, choice_factory=SimulationChoice,
        policies_by_id=policies, rules=raw, rules_hash=rules_hash,
        now_monotonic=lambda: 0, wall_clock=None, budget_policy=BudgetPolicy()))
    print('calls per label:', dict(calls))
    print('errors:', errors[:3], 'count', len(errors))
    print('tables:', [(r.policy_ids_by_seat[0], list(r.scores_after)) for r in out.results])
    print('excluded:', list(out.excluded))
    print(json.dumps({
        'seed': seed,
        'phase_windows': {f'{label}:{phase}': n for (label, phase), n in sorted(phase_seen.items())},
        'funnel': dict(stats),
        'frontier_sizes': dict(sorted(frontier_sizes.items())),
        'shadow_notes': notes,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
