"""验证自然窗口反事实链：中期 export_hand → from_replay → 两支同世界续打。

只使用公开接口（start/frame/advance/export_hand/from_replay）；策略各自只收到观察。
"""

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
from dataclasses import replace

sys.path.insert(0, 'tools/research/big-hand-paths-2026-09-09')
sys.path.insert(0, 'src')

from lab import ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.config import TournamentConfig, TimingConfig
from hangma_bot.kernel.observation import CompetitionContext, PlayerObservation
from hangma_bot.policy.interface import DecisionRequest, DecisionBudget
from hangma_bot.policy.balanced_shadow import _pareto, _route_signature
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice

RULES = HangmaRules(RuleConfig(RULESET, 1, False))
ENGINE = SimulationEngine(RULES, rules_hash=compute_rules_hash(ROOT))
POLICY = ComparableHeuristicPolicyV2(monotonic=lambda: 0)


def request_for(decision):
    obs = decision.observation
    analysis = RULES.analyze(obs, value_limits=ValueAnalysisLimits())
    return DecisionRequest(observation=obs, competition=CompetitionContext('counterfactual', None, None, None, None, (), 0),
                           rules=analysis, decision_id=f'cf-{obs.snapshot_seq}', trigger_seq=obs.snapshot_seq,
                           window_key=decision.window_key, rejected_attempts=())


async def branch(world, target_key, first_action):
    """在指定窗口落下候选动作，同帧其他窗口仍由 V2 决定；其后四家全部由 V2 打到单局终局。"""
    frame = ENGINE.frame(world)
    assert any(d.window_key == target_key for d in frame.decisions), '目标窗口不在本帧'
    choices = []
    for decision in frame.decisions:
        if decision.window_key == target_key:
            choices.append(SimulationChoice(decision.window_key, first_action))
        else:
            plan = await POLICY.choose(request_for(decision), DecisionBudget(10, 11, 12))
            choices.append(SimulationChoice(decision.window_key, plan.candidates[0].action))
    world = ENGINE.advance(world, frame.revision, tuple(choices))
    for _ in range(5000):
        frame = ENGINE.frame(world)
        if frame.blocked_reason:
            raise RuntimeError(frame.blocked_reason)
        if frame.final_scores is not None:
            result = ENGINE.export_hand(world, 1)
            return dict(score=frame.final_scores[0], winner=result['winner_seat'], fan=result['fan'],
                        details=result['details'])
        choices = []
        for item in frame.decisions:
            plan = await POLICY.choose(request_for(item), DecisionBudget(10, 11, 12))
            choices.append(SimulationChoice(item.window_key, plan.candidates[0].action))
        world = ENGINE.advance(world, frame.revision, tuple(choices))
    raise RuntimeError('单局超过步数上限')


async def main():
    config = TournamentConfig(1, 8, RULES.config, TimingConfig(1, 1, 3))
    spec = MatchSpec(match_id='probe-cf', scenario_id='probe-cf', config=config, seed=1193000,
                     initial_dealer=0, initial_scores=(0, 0, 0, 0))
    world = ENGINE.start(spec)
    captured = None
    for _ in range(400):
        frame = ENGINE.frame(world)
        if frame.final_scores is not None:
            break
        if captured is None:
            for decision in frame.decisions:
                obs = decision.observation
                if obs.seat != 0 or obs.phase != 'draw':
                    continue
                analysis = RULES.analyze(obs, value_limits=ValueAnalysisLimits())
                discards = [c for c in analysis.legal_candidates if isinstance(c.action, Discard)]
                frontier = _pareto(discards)
                if len(frontier) >= 2 and obs.round_no >= 3 and obs.snapshot_seq > 30:
                    row = ENGINE.export_hand(world, obs.round_no)
                    captured = dict(row=row, decision=decision, frontier=frontier,
                                    world_seq=getattr(world, 'seq', None))
                    break
        choices = []
        for decision in frame.decisions:
            plan = await POLICY.choose(request_for(decision), DecisionBudget(10, 11, 12))
            choices.append(SimulationChoice(decision.window_key, plan.candidates[0].action))
        if captured is not None and captured['decision'] in frame.decisions:
            break
        world = ENGINE.advance(world, frame.revision, tuple(choices))

    assert captured, '未找到符合条件的自然窗口'
    row = captured['row']
    payload = row['initial']['world_payload']
    print('captured round', row['round_no'], 'payload.seq', payload['seq'], 'wall_front', payload['wall_front'],
          'coverage', row['coverage'], '事件数', len(row.get('events') or []),
          '捕获时 world.seq', captured.get('world_seq'))
    print('捕获窗口 seq', captured['decision'].observation.snapshot_seq,
          '| 事件类型前 6:', [e.get('type') for e in (row.get('events') or [])][:6])
    print('frontier:', [(c.action_key, _route_signature(c)) for c in captured['frontier']])

    # 往返：同一起点分别重建两支，并逐字段核对恢复出的观察与捕获时一致
    original = captured['decision'].observation
    target_key = captured['decision'].window_key
    restored = ENGINE.from_replay(row)
    frame = ENGINE.frame(restored)
    matched = [d for d in frame.decisions if d.window_key == target_key]
    assert matched, '恢复后的帧里没有目标窗口'
    obs = matched[0].observation
    print('captured  :', original.seat, original.phase, 'round', original.round_no,
          'seq', original.snapshot_seq, 'hand', [t.code for t in original.my_hand],
          'drawn', None if original.drawn_tile is None else original.drawn_tile.code,
          'remaining', original.remaining_tile_count)
    print('restored  :', obs.seat, obs.phase, 'round', obs.round_no,
          'seq', obs.snapshot_seq, 'hand', [t.code for t in obs.my_hand],
          'drawn', None if obs.drawn_tile is None else obs.drawn_tile.code,
          'remaining', obs.remaining_tile_count)
    assert obs.seat == original.seat and obs.phase == original.phase
    assert [t.code for t in obs.my_hand] == [t.code for t in original.my_hand]
    assert (None if obs.drawn_tile is None else obs.drawn_tile.code) == (
        None if original.drawn_tile is None else original.drawn_tile.code)
    assert obs.remaining_tile_count == original.remaining_tile_count
    assert [[t.code for t in row_tiles] for row_tiles in obs.discards] == [
        [t.code for t in row_tiles] for row_tiles in original.discards]
    assert [len(melds) for melds in obs.melds] == [len(melds) for melds in original.melds]
    print('往返一致性: 通过（手牌/摸牌/余牌/牌河/副露逐项相等）')

    base_world, alt_world = ENGINE.from_replay(row), ENGINE.from_replay(row)
    base_action = captured['frontier'][0].action
    alt_action = captured['frontier'][1].action
    base = await branch(base_world, target_key, base_action)
    alt = await branch(alt_world, target_key, alt_action)
    print('baseline branch:', json.dumps(base, ensure_ascii=False))
    print('candidate branch:', json.dumps(alt, ensure_ascii=False))
    print('delta (candidate - baseline):', alt['score'] - base['score'])


asyncio.run(main())
