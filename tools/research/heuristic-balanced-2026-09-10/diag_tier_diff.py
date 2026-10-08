"""差分窗口诊断：打印两档计划、降级原因与相关候选的路线数值。"""

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

sys.path.insert(0, 'tools/research/big-hand-paths-2026-09-09')
sys.path.insert(0, 'src')

from lab import ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits
from hangma_bot.kernel.config import TournamentConfig, TimingConfig
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN
from hangma_bot.policy.hu_upgrade_tierb import HuUpgradeTierBPolicy
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice
import counterfactual_windows as cf

rules = HangmaRules(RuleConfig(RULESET, 1, False))
engine = SimulationEngine(rules, rules_hash=compute_rules_hash(ROOT))
a = V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS, risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
b = HuUpgradeTierBPolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS, risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
opp = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
found = 0
for index in range(4):
    spec = MatchSpec(match_id='diag-{}'.format(index), scenario_id='diag-{}'.format(index),
                     config=TournamentConfig(1, 8, rules.config, TimingConfig(1, 1, 3)),
                     seed=1320000 + index, initial_dealer=0, initial_scores=(0, 0, 0, 0))
    world = engine.start(spec)
    for _ in range(20000):
        frame = engine.frame(world)
        if frame.final_scores is not None:
            break
        choices = []
        for decision in frame.decisions:
            obs = decision.observation
            if obs.seat == 0:
                req = cf.request_for(rules, decision, 'diag')
                pa = asyncio.run(a.choose(req, cf.DecisionBudget(10, 11, 12)))
                pb = asyncio.run(b.choose(req, cf.DecisionBudget(10, 11, 12)))
                if pa.candidates[0].action_key != pb.candidates[0].action_key:
                    print('=== 差异窗口 round', obs.round_no, 'phase', obs.phase,
                          'remaining', obs.remaining_tile_count, 'baotou', obs.rule_state.baotou)
                    print('  A ->', pa.candidates[0].action_key, '|', json.dumps(pa.candidates[0].reasons[-1:], ensure_ascii=False)[:260])
                    print('  B ->', pb.candidates[0].action_key, '|', json.dumps(pb.candidates[0].reasons[-1:], ensure_ascii=False)[:260])
                    for cand in req.rules.legal_candidates:
                        facts = getattr(cand, 'value_facts', None)
                        if facts is None:
                            continue
                        imm = None if facts.immediate_settlement is None else facts.immediate_settlement.score_delta
                        routes = [(r.conditions.baotou, r.conditional_settlement.score_delta[obs.seat],
                                   sum(t.remaining_estimate for t in r.useful_tiles), len(r.useful_tiles))
                                  for r in facts.routes]
                        print('   候选', cand.action_key, 'immediate', imm, 'routes(baotou,score,unseen,kinds)',
                              routes[:2], '共', len(routes))
                    found += 1
                    if found >= 2:
                        raise SystemExit
                choices.append(SimulationChoice(decision.window_key, pa.candidates[0].action))
            else:
                plan = asyncio.run(opp.choose(cf.request_for(rules, decision, 'diag'), cf.DecisionBudget(10, 11, 12)))
                choices.append(SimulationChoice(decision.window_key, plan.candidates[0].action))
        world = engine.advance(world, frame.revision, tuple(choices))
