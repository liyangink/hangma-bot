"""探查吃碰响应窗口的候选事实：能否用同一套一摸价值口径比较"吃碰 vs 过"。"""

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
import sys
sys.path.insert(0, 'tools/research/big-hand-paths-2026-09-09')
sys.path.insert(0, 'src')
from lab import ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits
from hangma_bot.kernel.config import TournamentConfig, TimingConfig
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice

rules = HangmaRules(RuleConfig(RULESET, 1, False))
engine = SimulationEngine(rules, rules_hash=compute_rules_hash(ROOT))
policy = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
spec = MatchSpec(match_id='probe-claim', scenario_id='probe-claim',
                 config=TournamentConfig(1, 8, rules.config, TimingConfig(1, 1, 3)),
                 seed=1220000, initial_dealer=0, initial_scores=(0, 0, 0, 0))
world = engine.start(spec)
seen = 0
for _ in range(1200):
    frame = engine.frame(world)
    if frame.final_scores is not None:
        break
    for decision in frame.decisions:
        obs = decision.observation
        if obs.seat == 0 and obs.phase in ('response_peng', 'response_chi'):
            allc = rules.analyze(obs).legal_candidates
            claims = [c for c in allc if c.action_key.split(':')[0] in ('chi', 'peng', 'gang')]
            if not claims:
                continue
            withfacts = rules.analyze(obs, value_limits=ValueAnalysisLimits())
            analysis = withfacts
            kinds = [(c.action_key, c.facts is not None and c.facts.fact_kind.name,
                      None if c.facts is None else c.facts.standard_shanten_after,
                      None if c.facts is None else c.facts.seven_pairs_shanten_after)
                     for c in analysis.legal_candidates]
            print(obs.phase, '有鸣牌候选的窗口:', kinds)
            seen += 1
            if seen >= 3:
                break
    if seen >= 3:
        break
    import asyncio
    from dataclasses import replace
    choices = []
    for decision in frame.decisions:
        from hangma_bot.policy.interface import DecisionRequest, DecisionBudget
        from hangma_bot.kernel.observation import CompetitionContext
        obs = decision.observation
        req = DecisionRequest(observation=obs, competition=CompetitionContext('probe', None, None, None, None, (), 0),
                              rules=rules.analyze(obs), decision_id='p', trigger_seq=obs.snapshot_seq,
                              window_key=decision.window_key, rejected_attempts=())
        plan = asyncio.run(policy.choose(req, DecisionBudget(10, 11, 12)))
        choices.append(SimulationChoice(decision.window_key, plan.candidates[0].action))
    world = engine.advance(world, frame.revision, tuple(choices))
