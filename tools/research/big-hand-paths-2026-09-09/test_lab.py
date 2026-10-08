"""案例评估的物理约束、同源规则、信息权限与全程续打验收。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/big-hand-paths-2026-09-09'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
from dataclasses import asdict
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab import generate, witness, observation, HangmaRules, RuleConfig, RULESET, CANONICAL_TILE_ORDER
from continuation import source_hand
from hangma_bot.simulation.engine import SimulationEngine

ROWS, CASES = generate()


@pytest.mark.parametrize('case', CASES, ids=lambda c:c.case_id)
def test_each_official_anchor_has_a_physical_prefix_and_exact_terminal_settlement(case):
    proof = witness(case, ROWS, False)
    assert proof['allowed']
    assert proof['fan'] == ROWS[case.anchor_line]['response']['fan']
    assert max(Counter(case.initial_hand + case.future_draws).values()) <= 4


@pytest.mark.parametrize('wall', [24,48,80])
def test_wall_variants_have_consistent_visible_inventory_and_reserve_future_copies(wall):
    for case in CASES:
        obs = observation(case.initial_hand,case_id=case.case_id,wall=wall,reserve=case.future_draws)
        public = [t.code for river in obs.discards for t in river]
        assert 14 + 39 + len(public) + wall == 136
        assert max(Counter(list(case.initial_hand) + public + list(case.future_draws)).values()) <= 4
        assert not obs.history_complete  # 合成库存不冒充完整公开事件历史。


def test_full_world_sampler_has_no_future_witness_leak_and_exact_conservation():
    case=asdict(CASES[-1])
    first=source_hand(case,1050000)
    changed=dict(case,future_draws=['东']*100,discards=['南']*100,anchor_line=-1)
    assert first == source_hand(changed,1050000)
    engine=SimulationEngine(HangmaRules(RuleConfig(RULESET,1,False)))
    first_obs=engine.frame(engine.from_replay(first)).decisions[0].observation
    for seed in range(1050001,1050010):
        other=source_hand(case,seed)
        payload=other['initial']['world_payload']
        assert Counter(sum(payload['hands'],[]) + [payload['dealer_drawn_tile']] + payload['wall']) == Counter({c:4 for c in CANONICAL_TILE_ORDER})
        obs=engine.frame(engine.from_replay(other)).decisions[0].observation
        # 场次 ID 携带重现种子，牌局可见事实不随其他三家暗牌与牌墙改变。
        from dataclasses import replace
        assert replace(obs,game_id=first_obs.game_id) == first_obs


def test_invalid_fifth_copy_is_rejected_before_a_counterfactual_can_be_claimed():
    case=asdict(CASES[0]);case['initial_hand']=['东']*14
    with pytest.raises(AssertionError):
        source_hand(case,1050000)


def test_seven_pairs_wait_with_exhausted_tiles_has_no_conditional_win_route():
    """关键牌耗尽是独立负例；牌型仍听牌，实际未见进张应为零而非虚构大牌机会。"""
    from dataclasses import replace
    from hangma_bot.kernel.actions import Tile
    from hangma_bot.hangma.interface import ValueAnalysisLimits, ValueCoverage
    hand='1w 1w 3w 3w 5w 5w 2b 2b 4b 4b 6b 6b 8t 9t'.split()
    obs=observation(hand,case_id='seven-exhausted-control',wall=83,dealer=0)
    # 两圈各家两张弃牌：第一圈逐家弃白，第二圈圈主最后弃东退出，当前无圈。
    rivers=tuple(tuple(Tile(c) for c in row.split()) for row in ['白 8t','白 8t','白 8t','白 东'])
    exhausted=replace(obs,discards=rivers,remaining_tile_count=75)
    rules=HangmaRules(RuleConfig(RULESET,1,False))
    live={c.action_key:c for c in rules.analyze(obs,value_limits=ValueAnalysisLimits()).legal_candidates}
    dead={c.action_key:c for c in rules.analyze(exhausted,value_limits=ValueAnalysisLimits()).legal_candidates}
    assert sum(t.remaining_estimate for t in live['discard:9t'].facts.useful_tiles)==7
    assert dead['discard:9t'].facts.seven_pairs_shanten_after==0
    assert sum(t.remaining_estimate for t in dead['discard:9t'].facts.useful_tiles)==0
    assert dead['discard:9t'].value_facts.coverage is ValueCoverage.COMPLETE
    assert not dead['discard:9t'].value_facts.routes
    assert sum(t.remaining_estimate for t in dead['discard:8t'].facts.useful_tiles)==3
