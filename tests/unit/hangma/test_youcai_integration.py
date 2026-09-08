"""有财必拷响通过规则公开入口验收：真实拒胡、配置对照与正常排除。

依据：2026-09-07 用户确认有财必须爆头；t_64201ecc3ab3 两次官方拒胡。
完整暗牌与副露保留原场景，不将展开副露当成原场景接口对拍。
"""
from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.actions import Hu, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicMeld, RulePublicState


def make_observation(hand, draw, *, melds=(), baotou=False, chain=0, piao=0, gang=False):
    """摸前暗牌和摸牌分开；座位0为本人，明确链事实以隔离历史缺失。"""
    return PlayerObservation(
        game_id='youcai-case', seat=0, round_no=1, snapshot_seq=10,
        phase='draw', dealer_seat=0, turn_seat=0, responding_seats=(),
        my_hand=tuple(Tile(t) for t in hand), drawn_tile=Tile(draw),
        discards=((), (), (), ()), melds=(tuple(melds), (), (), ()),
        hand_counts=(len(hand)+1,13,13,13), last_discard=None,
        remaining_tile_count=60, scores=(0,0,0,0),
        rule_state=RulePublicState(Tile('白'),baotou,chain,False),
        public_history=(), chain_piao=piao, gang_draw=gang,
    )


def meld(kind, codes):
    return PublicMeld(seat=0, kind=kind, tiles=tuple(Tile(t) for t in codes), from_seat=None)


CASES = [
    ('xuanwu-b2-r5-seq1083', ['白','1w','7w','6w'], '5w',
     (meld('chi',['4t','5t','6t']),meld('chi',['4w','5w','6w']),meld('gang_ming',['1b']*4))),
    ('baihu-b0-r8-seq1950', ['4t','6w','6w','6w','7w','2t','白','6b','白','5w'], '6w',
     (meld('gang_ming',['4w']*4),)),
]


@pytest.mark.parametrize('tag,hand,draw,melds', CASES, ids=[c[0] for c in CASES])
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('hand_includes_draw', [False, True])
def test_official_rejected_hu_respects_room_config(tag, hand, draw, melds, enabled, hand_includes_draw):
    obs=make_observation(hand,draw,melds=melds,chain=1,gang=True)
    if hand_includes_draw:
        obs=replace(obs,my_hand=obs.my_hand+(obs.drawn_tile,))
    rules=HangmaRules(RuleConfig('youcai-test',1,enabled))
    analysis=rules.analyze(obs)
    assert ('hu' in {c.action_key for c in analysis.legal_candidates}) is (not enabled)
    assert rules.validate(obs,Hu()).legal is (not enabled)
    assert analysis.emergency_candidate is not None
    assert rules.validate(obs,analysis.emergency_candidate.action).legal
    assert analysis.completeness is RuleCompleteness.COMPLETE


@pytest.mark.parametrize('gang', [False, True, None])
def test_known_rule_exclusion_is_complete_not_analysis_failure(gang):
    obs=make_observation(['1w','2w','3w','4w','5w','6w','7b','8b','9b','白','1b','6t','7t'],
                         '5t',gang=gang)
    rules=HangmaRules(RuleConfig('youcai-test',1,True))
    analysis=rules.analyze(obs)
    assert not rules.validate(obs,Hu()).legal
    assert analysis.completeness is RuleCompleteness.COMPLETE
    assert analysis.issues == ()


@pytest.mark.parametrize('enabled', [False, True])
def test_four_white_baotou_passes_public_gate_under_both_configs(enabled):
    """v23 官方任意听四白牌例：成立的爆头在两种配置下均可胡。"""
    obs=make_observation(['1w','2w','3w','4w','5w','6w','7b','8b','9b']+['白']*4,
                         '东',baotou=True)
    rules=HangmaRules(RuleConfig('four-white-gate',1,enabled))
    assert rules.validate(obs,Hu()).legal
    assert rules.analyze(obs).completeness is RuleCompleteness.COMPLETE


def test_authoritative_inherited_baotou_is_not_replaced_by_static_analysis():
    """合成控制：将成牌的权威持续爆头置真；不冒充原拒胡窗口或官方胡牌轨迹。

    真实v18吃杠补继承过程由test_official_action_chain_trace单独验证。
    """
    from hangma_bot.hangma.hand_analysis import any_tile_win
    _,hand,draw,melds=CASES[0]
    assert not any_tile_win(tuple(Tile(t) for t in hand),len(melds))
    obs=make_observation(hand,draw,melds=melds,baotou=True,chain=1,gang=True)
    rules=HangmaRules(RuleConfig('inherited-baotou',1,True))
    assert rules.validate(obs,Hu()).legal
    assert rules.analyze(obs).completeness is RuleCompleteness.COMPLETE
