"""观察派生按官方 v15（2026-09-05）的链规则与信息权限核验。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, WinDescription
from hangma_bot.hangma.observation_rules import enrich_observation, recompute_draw_rule_state
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicEvent, RulePublicState


def event(seq, kind, seat=0, tile=None):
    return PublicEvent(seq, kind, seat, (Tile(tile),) if tile else ())


def observation(**changes):
    values = dict(
        game_id="observation-rules", seat=0, round_no=1, snapshot_seq=10,
        phase="draw", dealer_seat=0, turn_seat=0, responding_seats=(),
        my_hand=tuple(Tile(x) for x in ("1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东")),
        drawn_tile=Tile("东"), discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(14, 13, 13, 13), last_discard=None, remaining_tile_count=60,
        scores=(0, 0, 0, 0), rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(), consumed_seq=10,
    )
    values.update(changes)
    return PlayerObservation(**values)


def with_chain(count, history, **changes):
    return observation(rule_state=RulePublicState(Tile("白"), False, count, False), public_history=history, **changes)


def test_old_white_discard_does_not_pollute_new_gang_chain():
    obs = with_chain(1, (event(6, "tile_discarded", tile="白"), event(7, "tile_discarded", tile="5w"), event(8, "gang", tile="9b"), event(9, "tile_drawn", tile="东"), event(10, "pass", seat=1)))
    result = enrich_observation(obs)
    assert result.chain_piao == 0
    assert result.gang_draw is True


def test_complete_chain_suffix_does_not_require_complete_hand_history():
    obs = with_chain(3, (event(1, "tile_discarded", tile="5w"), event(6, "gang", tile="9b"), event(7, "tile_drawn", tile="白"), event(8, "tile_discarded", tile="白"), event(9, "gang", tile="1b"), event(10, "tile_drawn", tile="东")))
    assert obs.history_complete is False
    assert enrich_observation(obs).chain_piao == 1


@pytest.mark.parametrize("history,watermark", [
    ((event(8, "gang"), event(10, "tile_drawn", tile="东")), 10),
    ((event(8, "gang"), event(9, "tile_drawn", tile="东")), 10),
    ((event(9, "tile_discarded", tile="5w"), event(10, "tile_drawn", tile="东")), 10),
    ((event(9, "gang"), event(10, "unknown")), 10),
    ((), 10),
])
def test_incomplete_chain_is_unknown(history, watermark):
    assert enrich_observation(with_chain(2, history, consumed_seq=watermark)).chain_piao is None


def test_zero_chain_is_known_without_history():
    assert enrich_observation(observation()).chain_piao == 0


def test_gang_draw_gap_is_unknown_and_old_draw_is_not_reused():
    gap = with_chain(2, (event(8, "gang"), event(10, "tile_drawn", tile="东")))
    assert enrich_observation(gap).gang_draw is None
    later = with_chain(2, (event(7, "gang"), event(8, "tile_drawn", tile="东"), event(9, "tile_discarded", tile="东"), event(10, "chi", tile="1b")))
    assert enrich_observation(later).gang_draw is None
    assert enrich_observation(replace(later, phase="response_peng")).gang_draw is False


def test_explicit_facts_survive_incomplete_history():
    result = enrich_observation(with_chain(2, (), chain_piao=1, gang_draw=True))
    assert (result.chain_piao, result.gang_draw) == (1, True)


def test_fourth_white_keeps_baotou_when_pre_draw_hand_is_any_tile_tenpai():
    hand = tuple(Tile(x) for x in ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "白", "白", "白"))
    obs = observation(my_hand=hand, drawn_tile=None, rule_state=RulePublicState(Tile("白"), True, 0, False))
    assert recompute_draw_rule_state(obs, Tile("白")).baotou is True
    assert recompute_draw_rule_state(obs, Tile("东")).baotou is True
    with pytest.raises(ValueError, match="摸牌前"):
        recompute_draw_rule_state(replace(obs, my_hand=hand + (Tile("白"),)), Tile("东"))


def rules():
    return HangmaRules(RuleConfig(ruleset_version="v15", you_cai_bi_kao=True, base_score=1))


def test_unknown_piao_rejects_deterministic_settlement():
    with pytest.raises(ValueError, match="链内飘次数未知"):
        rules().score(WinDescription(with_chain(1, ()), 0))
    assert rules().score(WinDescription(with_chain(1, (), chain_piao=0), 0)).fan == 2


def test_observation_issues_reach_rule_analysis():
    result = rules().analyze(observation(observation_issues=("官方 god 与推导不一致",)))
    assert result.completeness == RuleCompleteness.DEGRADED
    assert any(issue.area == "observation" for issue in result.issues)


@pytest.mark.parametrize('gang_draw', [True, False, None])
def test_gang_draw_does_not_exempt_youcai_or_degrade(gang_draw):
    hand = tuple(Tile(x) for x in ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "1b", "东", "白"))
    obs = observation(my_hand=hand, gang_draw=gang_draw)
    result = rules().analyze(obs)
    assert "hu" not in {c.action_key for c in result.legal_candidates}
    assert result.completeness is RuleCompleteness.COMPLETE
    assert result.issues == ()


def test_compare_detects_chain_reset_and_preserves_official_observation():
    from hangma_bot.hangma.observation_rules import compare_observation_transition
    before = with_chain(2, ())
    after = replace(before, consumed_seq=11, phase="response_peng")
    events = (event(11, "tile_discarded", tile="5w"),)
    result = compare_observation_transition(before, events, after)
    assert any(x.startswith("god_mismatch:chain_count:") for x in result)
    assert after.rule_state.chain_count == 2
    correct = replace(after, rule_state=replace(after.rule_state, chain_count=0))
    assert not any(x.startswith("god_mismatch:") for x in compare_observation_transition(before, events, correct))


def test_compare_white_piao_increments_only_when_before_baotou():
    from hangma_bot.hangma.observation_rules import compare_observation_transition
    before = observation(
        my_hand=tuple(Tile(t) for t in ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "白")),
        drawn_tile=Tile("南"), rule_state=RulePublicState(Tile("白"), True, 2, False))
    # 弃白按动作前爆头计飘；弃后剩单南，当前听牌态不再是任意听。
    after = replace(before, consumed_seq=11, phase="response_peng", drawn_tile=None,
                    my_hand=before.my_hand[:-1] + (Tile("南"),),
                    rule_state=replace(before.rule_state, chain_count=3, baotou=False))
    events = (event(11, "tile_discarded", tile="白"),)
    assert not any(x.startswith("god_mismatch:") for x in compare_observation_transition(before, events, after))
    normal_white = replace(before, rule_state=replace(before.rule_state, baotou=False))
    assert any(x.startswith("god_mismatch:chain_count:") for x in compare_observation_transition(normal_white, events, after))


def test_compare_fourth_white_accepts_baotou_and_detects_incorrect_clear():
    from hangma_bot.hangma.observation_rules import compare_observation_transition
    hand = tuple(Tile(x) for x in ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "白", "白", "白"))
    before = observation(my_hand=hand, drawn_tile=None, rule_state=RulePublicState(Tile("白"), True, 0, False))
    after = replace(before, consumed_seq=11, my_hand=hand + (Tile("白"),), drawn_tile=Tile("白"))
    result = compare_observation_transition(before, (event(11, "tile_drawn", tile="白"),), after)
    assert not any(x.startswith("god_mismatch:") for x in result)
    incorrect = replace(after, rule_state=replace(after.rule_state, baotou=False))
    assert any(x.startswith("god_mismatch:baotou:") for x in compare_observation_transition(before, (event(11, "tile_drawn", tile="白"),), incorrect))


def test_compare_gang_draw_checks_chain_and_unknown_coverage_is_skipped():
    from hangma_bot.hangma.observation_rules import compare_observation_transition
    before = observation()
    after = replace(before, consumed_seq=12, rule_state=replace(before.rule_state, chain_count=1))
    events = (event(11, "gang", tile="9b"), event(12, "tile_drawn", tile="东"))
    assert not any(x.startswith("god_mismatch:chain_count:") for x in compare_observation_transition(before, events, after))
    wrong = replace(after, rule_state=replace(after.rule_state, chain_count=0))
    assert any(x.startswith("god_mismatch:chain_count:") for x in compare_observation_transition(before, events, wrong))
    for unaligned in (replace(after, consumed_seq=13), replace(after, round_no=2)):
        result = compare_observation_transition(before, events, unaligned)
        assert result and all(x.startswith("not_checked:") for x in result)


@pytest.mark.parametrize("detail", [None, "new_kind"])
def test_nonresponse_timeout_invalidates_inference_and_transition_check(detail):
    """缺 detail_kind 或未来新增 kind 的 timeout 仍不能排除自动动作，保持未知。"""
    from hangma_bot.hangma.observation_rules import compare_observation_transition
    timeout = PublicEvent(13, "timeout", 0, detail_kind=detail)
    history = (event(11, "gang", tile="9b"), event(12, "tile_drawn", tile="东"), timeout)
    after = with_chain(1, history, consumed_seq=13)
    enriched = enrich_observation(after)
    assert enriched.gang_draw is None
    assert enriched.chain_piao is None
    result = compare_observation_transition(observation(), history, after)
    assert result and all(x.startswith("not_checked:") for x in result)


def test_discard_timeout_keeps_inference_and_transition_check():
    """timeout(kind=discard) 是打牌窗口记账，与 response 同为被动事件。

    2026-09-23 实测（两房 24/24 成对）：服务端代打动作以紧邻 tile_discarded
    进入公开流，本事件不携带独立规则信息；杠后摸牌证据与链核对不受影响。
    """
    from hangma_bot.hangma.observation_rules import compare_observation_transition
    timeout = PublicEvent(13, "timeout", 0, detail_kind="discard")
    history = (event(11, "gang", tile="9b"), event(12, "tile_drawn", tile="东"), timeout)
    after = with_chain(1, history, consumed_seq=13)
    enriched = enrich_observation(after)
    assert enriched.gang_draw is True
    assert enriched.chain_piao == 0
    assert not any(x.startswith("not_checked:chain_count:") for x in compare_observation_transition(observation(), history, after))



def test_confirmed_response_timeout_keeps_current_chain_and_draw_evidence():
    from hangma_bot.hangma.observation_rules import compare_observation_transition
    history = (event(11, "gang", tile="9b"), event(12, "tile_drawn", tile="东"), PublicEvent(13, "timeout", 1, detail_kind="response"))
    after = with_chain(1, history, consumed_seq=13)
    enriched = enrich_observation(after)
    assert enriched.gang_draw is True
    assert enriched.chain_piao == 0
    assert not any(x.startswith("not_checked:chain_count:") for x in compare_observation_transition(observation(), history, after))


def test_unknown_timeout_immediately_before_draw_is_not_normal_draw_evidence():
    after = with_chain(2, (PublicEvent(9, "timeout", 0), event(10, "tile_drawn", tile="东")))
    assert enrich_observation(after).gang_draw is None


def test_catch_play_without_drawn_has_no_fabricated_emergency_discard():
    obs = observation(drawn_tile=None, rule_state=RulePublicState(Tile("白"), False, 0, True))
    assert rules().emergency_action(obs) is None
    result = rules().analyze(obs)
    assert result.emergency_candidate is None
    assert not any(c.action_key.startswith("discard:") for c in result.legal_candidates)
