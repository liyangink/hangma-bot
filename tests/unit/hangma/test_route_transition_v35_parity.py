"""P2 v35 自然轨迹对拍：已见官方水位与本地给定条件路径分开。"""

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import observation, public_event
from hangma_bot.hangma.engine import HangmaRules, _build_context
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.observation_rules import enrich_observation, reconcile_observation
from hangma_bot.hangma.route_transition import (
    ConditionalIdentity, ConditionalPhase, _state,
    analyze_given_replacement_draw, apply_given_draw,
    apply_legal_draw_discard, apply_legal_draw_hu,
    advance_given_other_discard, advance_given_other_draw,
    advance_given_other_gang,
    advance_given_response, advance_response_state,
    finish_given_exhaustive_draw, project_legal_roots,
)
from hangma_bot.kernel.actions import Discard, Gang, GangKind, Hu, Pass, Tile
from hangma_bot.kernel.config import RuleConfig


FIXTURES = Path(__file__).parents[2] / "fixtures/official/v35/vip-p2-natural"


def _case(name):
    """从脱敏原始响应走官方 DTO 和投影；返回的后态只作验算标签。"""

    data = json.loads((FIXTURES / name).read_text())
    events = tuple(public_event(event) for event in parse_state_response(
        {"events": data["public_or_own_events"]}).events)
    views = []
    for item in data["state_responses"]:
        response = parse_state_response(item["response"])
        assert response.snapshot is not None and not response.gap
        view = observation(response.snapshot,
                           tuple(event for event in events if event.seq <= response.snapshot.seq),
                           data["game_id"])
        views.append(replace(view, consumed_seq=response.snapshot.seq))
    rule_config = data["provenance"]["rule_config"]
    assert data["provenance"]["guide_version"] == 35
    assert (rule_config["base_score"], rule_config["you_cai_bi_kao"]) == (1, False)
    config = RuleConfig(rule_config["ruleset_version"], 1, False)
    return data, tuple(views), events, HangmaRules(config)


def _root(rules, before, key, *, enrich=True):
    """用动作前观察建立同次候选；可显式复现裸投影的富集缺口。"""

    analysis = rules.analyze(before, value_limits=ValueAnalysisLimits())
    projected_input = enrich_observation(before) if enrich else before
    roots = project_legal_roots(projected_input, _build_context(projected_input),
                                analysis.legal_candidates, config=rules.config)
    assert tuple(root.action_key for root in roots) == tuple(
        candidate.action_key for candidate in analysis.legal_candidates)
    assert key in {candidate.action_key for candidate in analysis.legal_candidates}
    return next(root for root in roots if root.action_key == key)


def _same_observable_state(state, official):
    """对拍本人暗牌与四座公开事实；官方未提供的链内字段不补零。"""

    assert Counter(state.concealed) == Counter(official.my_hand)
    assert state.drawn_tile == official.drawn_tile
    assert state.public_view is not None
    public = state.public_view
    assert public.discards == official.discards
    # v35 snapshot 的 meld 对象不带供牌座位；只对拍它实际给出的牌形。
    # 条件明杠的供牌座位另与已见 tile_discarded 事件逐项核对。
    assert tuple(tuple((meld.kind, meld.tiles) for meld in seat_melds)
                 for seat_melds in public.melds) == tuple(
        tuple((meld.kind, meld.tiles) for meld in seat_melds)
        for seat_melds in official.melds)
    assert all(assumed.from_seat == observed.from_seat
               for assumed_seat, observed_seat in zip(public.melds, official.melds)
               for assumed, observed in zip(assumed_seat, observed_seat)
               if observed.from_seat is not None)
    assert public.hand_counts == official.hand_counts
    assert public.remaining_tile_count == official.remaining_tile_count
    assert state.wall_remaining == official.remaining_tile_count
    assert state.baotou == official.rule_state.baotou
    assert state.chain_count == official.rule_state.chain_count


def _watermark_is_official_root(state, before):
    """给定条件动作只添本地路径，不制造官方事件或序号。"""

    assert state.identity is not None and state.identity.path
    assert state.identity.game_id == before.game_id
    assert state.identity.round_no == before.round_no
    assert state.public_view.snapshot_seq == before.snapshot_seq
    assert state.public_view.consumed_seq == before.consumed_seq
    assert state.public_view.public_history == before.public_history


def _same_legal_keys(rules, state, confirmed):
    """条件杠补与已确认动作后的生产分析必须有相同合法动作全集。"""

    given = analyze_given_replacement_draw(
        state, seat=confirmed.seat, dealer_seat=confirmed.dealer_seat,
        config=rules.config)
    actual = rules.analyze(confirmed, value_limits=ValueAnalysisLimits())
    assert {candidate.action_key for candidate in given.legal_candidates} == {
        candidate.action_key for candidate in actual.legal_candidates}
    return given, actual


def test_v35_bugang_replacement_and_followup_discard_parity():
    """补杠只升级原碰；给定补牌及跟打逐字段对拍真实后态。"""

    data, (before, landed, discarded), events, rules = _case(
        "bugang-replenish-1510-1514.json")
    assert tuple(view.snapshot_seq for view in (before, landed, discarded)) == (1510, 1512, 1514)
    assert tuple(event.seq for event in events) == (1510, 1511, 1512, 1513)
    assert all(receipt["response"] == {"ok": True}
               for receipt in data["successful_action_receipts"])
    assert next(event for event in events if event.seq == 1511).detail_kind == "bu"
    replacement = next(event for event in events if event.seq == 1512)
    assert replacement.gang_replenish and replacement.tiles == (Tile("7t"),)

    action = Gang(Tile("2t"), GangKind.ADDED)
    root = _root(rules, before, "gang:added:2t")
    waiting = root.branches[0].state
    assert waiting.phase is ConditionalPhase.REPLACEMENT_DRAW
    assert waiting.public_view.melds[before.seat][0].kind == "gang_bu"
    assert waiting.public_view.melds[before.seat][0].from_seat == before.melds[before.seat][0].from_seat
    assert waiting.public_view.hand_counts[before.seat] == before.hand_counts[before.seat] - 1
    assert waiting.public_view.remaining_tile_count == before.remaining_tile_count
    assert Counter(waiting.concealed) == Counter(before.my_hand) - Counter((Tile("2t"),))
    _watermark_is_official_root(waiting, before)

    given = apply_given_draw(waiting, replacement.tiles[0], replacement=True)
    _same_observable_state(given, landed)
    _watermark_is_official_root(given, before)
    confirmed = reconcile_observation(before, landed, confirmed_action=action)
    assert confirmed.chain_piao == 0 and confirmed.gang_draw is True
    conditional, actual = _same_legal_keys(rules, given, confirmed)
    assert conditional.immediate_settlement is None
    with pytest.raises(ValueError, match="合法动作全集"):
        apply_legal_draw_hu(conditional)
    assert "discard:6t" in {candidate.action_key for candidate in actual.legal_candidates}
    with pytest.raises(ValueError, match="合法动作全集"):
        apply_legal_draw_discard(conditional, "discard:不存在")
    with pytest.raises(ValueError, match="合法动作全集"):
        apply_legal_draw_discard(conditional, "gang:added:2t")

    after_discard = apply_legal_draw_discard(conditional, "discard:6t")
    assert isinstance(next(candidate.action for candidate in actual.legal_candidates
                           if candidate.action_key == "discard:6t"), Discard)
    _same_observable_state(after_discard, discarded)
    _watermark_is_official_root(after_discard, before)
    assert after_discard.identity.path[-2:] == ("draw:7t", "discard:6t")
    assert after_discard.phase is ConditionalPhase.RESPONSE_RESOLUTION
    assert (waiting.chain_count, given.chain_count, after_discard.chain_count) == (1, 1, 0)


def test_v35_minggang_replacement_hu_and_four_seat_settlement_parity():
    """明杠获裁决后才移三张；补摸胡与官方番数、四座净分逐项相等。"""

    data, (before, landed, settled), events, rules = _case(
        "minggang-replenish-hu-1228-1231.json")
    assert tuple(view.snapshot_seq for view in (before, landed, settled)) == (1228, 1230, 1231)
    assert tuple(event.seq for event in events) == (1228, 1229, 1230, 1231)
    assert all(receipt["response"] == {"ok": True}
               for receipt in data["successful_action_receipts"])
    assert next(event for event in events if event.seq == 1229).detail_kind == "ming"
    replacement = next(event for event in events if event.seq == 1230)
    assert replacement.gang_replenish and replacement.tiles == (Tile("6b"),)

    action = Gang(Tile("4b"), GangKind.EXPOSED)
    assert before.chain_piao is None and before.gang_draw is None
    assert enrich_observation(before).chain_piao == 0
    root = _root(rules, before, "gang:exposed:4b")
    proposal = root.proposal_state
    assert proposal is not None and proposal.concealed == before.my_hand
    assert proposal.public_view.melds == before.melds
    assert root.branches[0].state.structural_only
    _watermark_is_official_root(proposal, before)
    choices = tuple((seat, action if seat == before.seat else Pass())
                    for seat in before.responding_seats)
    awarded = advance_given_response(
        root, window=before.phase, discard_seat=before.last_discard.seat,
        discarded_tile=before.last_discard.tile,
        responding=before.responding_seats, choices=choices,
        retained_in_river=False)
    assert awarded.resolution.status == "resolved"
    waiting = awarded.state
    assert waiting.phase is ConditionalPhase.REPLACEMENT_DRAW and waiting.claim_awarded
    assert Counter(waiting.concealed) == Counter(before.my_hand) - Counter((Tile("4b"),) * 3)
    assert waiting.public_view.melds[before.seat][-1].kind == "gang_ming"
    assert waiting.public_view.melds[before.seat][-1].from_seat == next(
        event.seat for event in events if event.seq == 1228)
    assert waiting.public_view.hand_counts[before.seat] == before.hand_counts[before.seat] - 3
    assert waiting.public_view.discards[before.last_discard.seat] == before.discards[before.last_discard.seat][:-1]
    _watermark_is_official_root(waiting, before)

    given = apply_given_draw(waiting, replacement.tiles[0], replacement=True)
    _same_observable_state(given, landed)
    _watermark_is_official_root(given, before)
    confirmed = reconcile_observation(before, landed, confirmed_action=action)
    assert confirmed.chain_piao == 0 and confirmed.gang_draw is True
    conditional, actual = _same_legal_keys(rules, given, confirmed)
    assert any(isinstance(candidate.action, Hu) for candidate in conditional.legal_candidates)
    terminal = next(event for event in events if event.seq == 1231)
    hu = next(candidate for candidate in actual.legal_candidates if candidate.action_key == "hu")
    assert hu.value_facts is not None
    authoritative_result = hu.value_facts.immediate_settlement
    assert authoritative_result is not None
    assert (authoritative_result.fan, authoritative_result.details,
            authoritative_result.score_delta) == (
        terminal.result_fan, terminal.result_details, terminal.result_scores)
    assert settled.scores == tuple(before.scores[seat] + authoritative_result.score_delta[seat]
                                   for seat in range(4))
    result = conditional.immediate_settlement
    assert result is not None
    assert result == authoritative_result
    with pytest.raises(ValueError, match="已证四座结算"):
        apply_legal_draw_hu(replace(conditional, immediate_settlement=None))
    ended = apply_legal_draw_hu(conditional)
    assert ended.phase is ConditionalPhase.TERMINAL
    assert ended.terminal_result is not None
    assert (ended.terminal_result.winner_seat, ended.terminal_result.is_draw,
            ended.terminal_result.fan, ended.terminal_result.details,
            ended.terminal_result.score_delta) == (
        before.seat, False, terminal.result_fan, terminal.result_details,
        terminal.result_scores)
    _watermark_is_official_root(ended, before)
    assert ended.identity.path[-1] == "hu"


def test_v35_raw_projection_uses_same_inferable_chain_fact():
    """裸观察入口也须和同次生产分析共享可推导的链证据。"""

    _, (before, _, _), _, rules = _case("minggang-replenish-hu-1228-1231.json")
    assert before.rule_state.chain_count == 0 and before.chain_piao is None
    assert enrich_observation(before).chain_piao == 0
    root = _root(rules, before, "gang:exposed:4b", enrich=False)
    action = Gang(Tile("4b"), GangKind.EXPOSED)
    awarded = advance_given_response(
        root, window=before.phase, discard_seat=before.last_discard.seat,
        discarded_tile=before.last_discard.tile,
        responding=before.responding_seats,
        choices=tuple((seat, action if seat == before.seat else Pass())
                      for seat in before.responding_seats),
        retained_in_river=False)
    assert awarded.resolution.status == "resolved"
    given = apply_given_draw(awarded.state, Tile("6b"), replacement=True)
    analysis = analyze_given_replacement_draw(
        given, seat=before.seat, dealer_seat=before.dealer_seat,
        config=rules.config)
    assert "hu" in {candidate.action_key for candidate in analysis.legal_candidates}
    assert not any(issue.area == "route_transition.input_evidence" for issue in analysis.issues)
    # 生产候选与条件根均在各自入口使用同一可见事实富集；原始快照仍保持
    # chain_piao=None，不能把条件结论写回官方观察或伪造事件序号。
    assert analysis.immediate_settlement is not None


def test_v35_other_minggang_replacement_and_discard_public_parity():
    """本座只见公开牌，给定他座明杠裁决后按原始 v35 轨迹续补摸和弃牌。"""

    data, (before, landed, discarded), events, rules = _case(
        "other-minggang-1201-1209.json")
    assert data["seat"] == before.seat == 2
    assert all(item["tile"] == "" for item in data["public_or_own_events"]
               if item["type"] == "tile_drawn" and item["seat"] != before.seat)
    assert tuple(view.snapshot_seq for view in (before, landed, discarded)) == (1201, 1207, 1209)
    assert next(item for item in events if item.seq == 1206).detail_kind == "ming"
    assert next(item for item in events if item.seq == 1207).gang_replenish
    assert before.phase == "response_chi" and before.last_discard is not None

    # 1201 本座不是吃窗响应人：从本座权威观察播种公开条件状态。
    # 1202 的他座过与 1205/1206 的明杠结果在测试中作为给定公开裁决；
    # 不把看不见的其余响应选择当成已证历史。
    seed = _state(before, _build_context(before), ConditionalPhase.RESPONSE_RESOLUTION)
    seed = replace(seed, identity=ConditionalIdentity(
        before.game_id, before.round_no, "public-prefix"))
    chi = advance_response_state(
        seed, window="response_chi", discard_seat=before.last_discard.seat,
        discarded_tile=before.last_discard.tile, responding=(0,),
        choices=((0, Pass()),))
    assert chi.resolution.status == "resolved"
    assert chi.state.expected_draw_seat == 0
    drawn = advance_given_other_draw(chi.state, seat=0)
    offered = advance_given_other_discard(drawn, seat=0, tile=Tile("1w"))
    gang = advance_response_state(
        offered, window="response_peng", discard_seat=0,
        discarded_tile=Tile("1w"), responding=(1, 2, 3),
        choices=((1, Gang(Tile("1w"), GangKind.EXPOSED)),
                 (2, Pass()), (3, Pass())), retained_in_river=False)
    assert gang.resolution.status == "resolved" and gang.gap_kinds == ()
    assert gang.state.expected_draw_seat == 1
    assert gang.state.expected_replacement_draw
    with pytest.raises(ValueError, match="摸牌来源"):
        advance_given_other_draw(gang.state, seat=1)
    replenished = advance_given_other_draw(gang.state, seat=1, replacement=True)
    _same_observable_state(replenished, landed)
    _watermark_is_official_root(replenished, before)
    after = advance_given_other_discard(replenished, seat=1, tile=Tile("1t"))
    _same_observable_state(after, discarded)
    _watermark_is_official_root(after, before)
    assert after.response_trigger == (1, Tile("1t"))
    assert after.identity.path[-2:] == ("other-replacement-draw:1", "other-discard:1:1t")


def test_v35_last_draw_then_full_responses_end_as_draw():
    """权威 21→20 末墙片段中，不能在碰吃响应完成前抢先流局。"""

    data, (before, offered, settled), events, rules = _case(
        "exhaustive-draw-1147-1159.json")
    assert data["seat"] == before.seat == 0
    assert tuple(view.snapshot_seq for view in (before, offered, settled)) == (
        1147, 1154, 1159)
    assert (before.remaining_tile_count, offered.remaining_tile_count,
            settled.remaining_tile_count) == (21, 20, 20)
    assert all(item["tile"] == "" for item in data["public_or_own_events"]
               if item["type"] == "tile_drawn" and item["seat"] != before.seat)
    ended_event = next(item for item in events if item.kind == "round_ended")
    assert ended_event.result_draw and ended_event.result_scores == (0, 0, 0, 0)

    root = _root(rules, before, "discard:南")
    after_own_discard = root.branches[0].state
    first_peng = advance_response_state(
        after_own_discard, window="response_peng", discard_seat=0,
        discarded_tile=Tile("南"), responding=(1, 2, 3),
        choices=((1, Pass()), (2, Pass()), (3, Pass())))
    first_chi = advance_response_state(
        first_peng.state, window="response_chi", discard_seat=0,
        discarded_tile=Tile("南"), responding=(1,), choices=((1, Pass()),))
    assert first_chi.state.expected_draw_seat == 1
    other_draw = advance_given_other_draw(first_chi.state, seat=1)
    assert other_draw.wall_remaining == 20
    after_other_discard = advance_given_other_discard(
        other_draw, seat=1, tile=Tile("9w"))
    _same_observable_state(after_other_discard, offered)
    with pytest.raises(ValueError, match="已裁决"):
        finish_given_exhaustive_draw(after_other_discard)
    second_peng = advance_response_state(
        after_other_discard, window="response_peng", discard_seat=1,
        discarded_tile=Tile("9w"), responding=(2, 3, 0),
        choices=((2, Pass()), (3, Pass()), (0, Pass())))
    second_chi = advance_response_state(
        second_peng.state, window="response_chi", discard_seat=1,
        discarded_tile=Tile("9w"), responding=(2,), choices=((2, Pass()),))
    assert second_chi.state.expected_draw_seat == 2
    terminal = finish_given_exhaustive_draw(second_chi.state)
    assert terminal.phase is ConditionalPhase.TERMINAL
    assert terminal.terminal_result is not None
    assert terminal.terminal_result.is_draw
    assert terminal.terminal_result.score_delta == ended_event.result_scores
    assert terminal.public_view.remaining_tile_count == settled.remaining_tile_count
    assert terminal.public_view.discards == settled.discards
    _watermark_is_official_root(terminal, before)


def test_v35_other_concealed_gang_replacement_public_state_parity():
    """他座暗杠及补摸只核本座可见公开后态，不用赛后暗摸牌计算其胡番。"""

    data, (before, settled), events, _ = _case("other-angang-1218-1222.json")
    assert data["seat"] == before.seat == 2
    assert (before.snapshot_seq, settled.snapshot_seq) == (1218, 1222)
    assert all(item["tile"] == "" for item in data["public_or_own_events"]
               if item["type"] == "tile_drawn" and item["seat"] != before.seat)
    assert before.phase == "response_chi" and before.last_discard is not None
    assert next(item for item in events if item.seq == 1220).detail_kind == "an"
    assert next(item for item in events if item.seq == 1221).gang_replenish
    terminal_event = next(item for item in events if item.kind == "round_ended")
    assert terminal_event.result_fan == 2

    seed = _state(before, _build_context(before), ConditionalPhase.RESPONSE_RESOLUTION)
    seed = replace(seed, identity=ConditionalIdentity(
        before.game_id, before.round_no, "public-prefix"))
    chi = advance_response_state(
        seed, window="response_chi", discard_seat=before.last_discard.seat,
        discarded_tile=before.last_discard.tile, responding=(3,),
        choices=((3, Pass()),))
    assert chi.state.expected_draw_seat == 3
    drawn = advance_given_other_draw(chi.state, seat=3)
    pending = advance_given_other_gang(
        drawn, seat=3, action=Gang(Tile("3b"), GangKind.CONCEALED))
    assert pending.expected_replacement_draw and pending.expected_draw_seat == 3
    replenished = advance_given_other_draw(pending, seat=3, replacement=True)
    _same_observable_state(replenished, settled)
    _watermark_is_official_root(replenished, before)
    assert replenished.wall_remaining == before.remaining_tile_count - 2 == 59
    assert replenished.public_view.melds[3][-1].kind == "gang_an"
    # 后继是他座胡；玩家观察无法读其暗牌，本条件前缀不伪称能复算该胡。
    assert replenished.phase is ConditionalPhase.PUBLIC_WAIT


def test_v35_other_added_gang_replacement_and_discard_public_parity():
    """原碰的公开供牌证据随他座补杠保留，补摸跟打与本座后态相等。"""

    data, (before, landed, discarded), events, _ = _case(
        "other-bugang-781-787.json")
    assert data["seat"] == before.seat == 2
    assert tuple(view.snapshot_seq for view in (before, landed, discarded)) == (
        781, 785, 787)
    assert all(item["tile"] == "" for item in data["public_or_own_events"]
               if item["type"] == "tile_drawn" and item["seat"] != before.seat)
    assert next(item for item in events if item.seq == 727).kind == "peng"
    assert next(item for item in events if item.seq == 784).detail_kind == "bu"
    assert next(item for item in events if item.seq == 785).gang_replenish

    seed = _state(before, _build_context(before), ConditionalPhase.RESPONSE_RESOLUTION)
    seed = replace(seed, identity=ConditionalIdentity(
        before.game_id, before.round_no, "public-prefix"))
    chi = advance_response_state(
        seed, window="response_chi", discard_seat=before.last_discard.seat,
        discarded_tile=before.last_discard.tile, responding=(1,),
        choices=((1, Pass()),))
    assert chi.state.expected_draw_seat == 1
    drawn = advance_given_other_draw(chi.state, seat=1)
    pending = advance_given_other_gang(
        drawn, seat=1, action=Gang(Tile("9b"), GangKind.ADDED))
    assert pending.expected_replacement_draw and pending.expected_draw_seat == 1
    assert pending.public_view.melds[1][0].kind == "gang_bu"
    replenished = advance_given_other_draw(pending, seat=1, replacement=True)
    _same_observable_state(replenished, landed)
    _watermark_is_official_root(replenished, before)
    after = advance_given_other_discard(replenished, seat=1, tile=Tile("北"))
    _same_observable_state(after, discarded)
    _watermark_is_official_root(after, before)
    assert after.wall_remaining == before.remaining_tile_count - 2 == 66
