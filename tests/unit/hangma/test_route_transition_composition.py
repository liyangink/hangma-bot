"""T1 定向组合与算子不变量；给定公开条件不包含他家暗牌或未来墙。"""

from collections import Counter
from dataclasses import replace

import pytest

from hangma_bot.hangma import progression
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles_from_view
from hangma_bot.hangma.route_transition import (
    ConditionalPhase, advance_given_other_discard, advance_given_other_draw,
    advance_given_other_gang, advance_given_response, advance_response_state,
    analyze_given_claim_action, analyze_given_self_draw, analyze_waiting_draw_witness,
    apply_given_draw,
    apply_legal_claim_discard, apply_legal_draw_discard, apply_legal_draw_hu,
    apply_legal_followup_gang, finish_given_exhaustive_draw,
    finish_given_official_other_win,
)
from hangma_bot.kernel.actions import (
    CANONICAL_TILE_ORDER, Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile,
)
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation, PublicDiscard, PublicEvent, PublicMeld, RulePublicState,
)


_CONFIG = RuleConfig("t1-composition", 1, False)


def _observation(hand, *, drawn=None, phase="draw", trigger=None, melds=(),
                 wall=60, owner=None):
    """构造本座已知牌与公开快照；owner 空表示无抓打圈。"""

    return PlayerObservation(
        game_id="t1-composition", seat=0, round_no=1, snapshot_seq=10,
        phase=phase, dealer_seat=0, turn_seat=0 if phase == "draw" else trigger.seat,
        responding_seats=() if phase == "draw" else (0,),
        my_hand=tuple(Tile(code) for code in hand), drawn_tile=drawn,
        discards=tuple((trigger.tile,) if trigger and trigger.seat == seat else ()
                       for seat in range(4)),
        melds=(melds, (), (), ()),
        hand_counts=(len(hand) + int(drawn is not None), 13, 13, 13),
        last_discard=trigger, remaining_tile_count=wall, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, owner is not None,
                                   catch_play_owner_seat=owner),
        public_history=(), chain_piao=0, gang_draw=False,
    )


def _roots(observation):
    """同次生产合法全集原样投影；目标配置完整输入不得出现机械缺口。"""

    analysis = HangmaRules(_CONFIG).analyze(observation, route_limits=ValueAnalysisLimits())
    roots = analysis.conditional_roots
    assert roots is not None
    assert tuple(root.action_key for root in roots) == tuple(
        item.action_key for item in analysis.legal_candidates)
    assert all(root.gap_kind is None and root.gap_kinds == () for root in roots)
    return {root.action_key: root for root in roots}


def _assert_conserved(state, before):
    """独立计数核实体张数守恒、本人折算手牌、逐码上限和官方水位。"""

    view = state.public_view
    assert view is not None and state.wall_remaining == view.remaining_tile_count
    retained = sum(claim.retained_in_river is True for claim in view.claim_evidence)
    total = sum(view.hand_counts) + sum(len(row) for row in view.discards) + sum(
        len(meld.tiles) for row in view.melds for meld in row
    ) - retained + state.wall_remaining
    initial_total = sum(before.hand_counts) + sum(len(row) for row in before.discards) + sum(
        len(meld.tiles) for row in before.melds for meld in row
    ) - sum(claim.retained_in_river is True for claim in before.claim_evidence) + before.remaining_tile_count
    assert total == initial_total
    assert view.hand_counts[state.seat] == len(state.concealed)
    assert state.meld_count == len(view.melds[state.seat])
    waiting_size = 13 - 3 * state.meld_count
    assert len(state.concealed) == waiting_size + int(
        state.phase is ConditionalPhase.CLAIM_DISCARD or state.drawn_tile is not None)
    visible = Counter(tile.code for tile in state.concealed)
    visible.update(tile.code for row in view.discards for tile in row)
    visible.update(tile.code for row in view.melds for meld in row for tile in meld.tiles)
    for claim in view.claim_evidence:
        if claim.retained_in_river:
            visible[claim.claimed_tile.code] -= 1
    for code, capacity, evidence in zip(
            CANONICAL_TILE_ORDER, state.unseen_capacities, state.unseen_evidence):
        assert visible[code] <= 4
        assert evidence == "exact"
        assert capacity == 4 - visible[code]
    # 同时核算公开计数接口的重算结果；独立 Counter 断言避免仅自对拍。
    recalculated = count_unseen_tiles_from_view(
        view, seat=state.seat, concealed=state.concealed, drawn_tile=None,
        chain_piao=state.chain_piao)
    assert recalculated.unseen == state.unseen_capacities
    assert (view.snapshot_seq, view.consumed_seq, view.public_history) == (
        before.snapshot_seq, before.consumed_seq, before.public_history)


def test_other_claim_without_draw_cannot_accept_self_draw_terminal():
    """碰后未摸不是自摸行动点，完整公开结算也不能跳过摸牌来源。"""

    before = _observation(("1w", "2w", "3w", "4w", "5w", "6w", "7w",
                           "8w", "9w", "1t", "2t", "东", "南"), drawn=Tile("5b"))
    awarded = advance_given_response(
        _roots(before)["discard:5b"], window="response_peng", discard_seat=0,
        discarded_tile=Tile("5b"), responding=(1, 2, 3),
        choices=((1, Peng(Tile("5b"))), (2, Pass()), (3, Pass())),
        retained_in_river=True).state
    event = PublicEvent(11, "round_ended", 1, result_draw=False, result_fan=1,
                        result_details=("普通胡",), result_scores=(-2, 4, -1, -1))
    with pytest.raises(ValueError, match="已摸牌"):
        finish_given_official_other_win(
            awarded, event, game_id=before.game_id, round_no=before.round_no)


def test_three_concealed_gangs_keep_every_compatible_final_replacement_and_action():
    """三杠链逐步守恒，第三杠后逐码补牌与全部合法弃牌都能继续。"""

    before = _observation(("1w",) * 4 + ("2w",) * 4 + ("3w",) * 3 + ("东",) * 2,
                          drawn=Tile("3w"), wall=83)
    state = _roots(before)["gang:concealed:1w"].branches[0].state
    baseline = state.root_public_view
    for index, (draw, next_gang) in enumerate((("4w", "2w"), ("5w", "3w")), 1):
        _assert_conserved(state, baseline)
        assert state.chain_count == index and state.chain_piao == 0
        state = apply_given_draw(state, Tile(draw), replacement=True)
        _assert_conserved(state, baseline)
        given = analyze_given_self_draw(state, seat=0, dealer_seat=0, config=_CONFIG)
        state = apply_legal_followup_gang(given, "gang:concealed:" + next_gang)
    _assert_conserved(state, baseline)
    assert state.chain_count == 3 and state.meld_count == 3
    assert state.wall_remaining == 81
    assert state.public_view.hand_counts == (4, 13, 13, 13)
    compatible = tuple(code for code, capacity in zip(
        CANONICAL_TILE_ORDER, state.unseen_capacities) if capacity > 0)
    assert len(compatible) == 31
    followed = 0
    for code in compatible:
        landed = apply_given_draw(state, Tile(code), replacement=True)
        _assert_conserved(landed, baseline)
        given = analyze_given_self_draw(landed, seat=0, dealer_seat=0, config=_CONFIG)
        assert given.issues == () and given.legal_candidates
        discards = tuple(item for item in given.legal_candidates
                         if isinstance(item.action, Discard))
        assert {item.action.tile.code for item in discards} == {
            tile.code for tile in landed.concealed}
        for candidate in discards:
            continued = apply_legal_draw_discard(given, candidate.action_key)
            _assert_conserved(continued, baseline)
            followed += 1
        if any(isinstance(item.action, Hu) for item in given.legal_candidates):
            ended = apply_legal_draw_hu(given)
            _assert_conserved(ended, baseline)
            assert ended.terminal_result.fan >= 8
    assert followed == 121
    for code in ("1w", "2w", "3w"):
        with pytest.raises(ValueError, match="容量为零"):
            apply_given_draw(state, Tile(code), replacement=True)


def test_four_gang_chain_is_bounded_by_real_hand_and_meld_counts():
    """连续补东凑成第四杠，最后补牌只留下合法将牌窗口。"""

    before = _observation(("1w",) * 4 + ("2w",) * 4 + ("3w",) * 4 + ("东",),
                          drawn=Tile("白"), wall=83)
    state = _roots(before)["gang:concealed:1w"].branches[0].state
    for next_gang in ("2w", "3w", "东"):
        state = apply_given_draw(state, Tile("东"), replacement=True)
        given = analyze_given_self_draw(state, seat=0, dealer_seat=0, config=_CONFIG)
        state = apply_legal_followup_gang(given, "gang:concealed:" + next_gang)
        _assert_conserved(state, state.root_public_view)
    assert state.meld_count == state.chain_count == 4
    assert state.concealed == (Tile("白"),)
    landed = apply_given_draw(state, Tile("南"), replacement=True)
    given = analyze_given_self_draw(landed, seat=0, dealer_seat=0, config=_CONFIG)
    assert all(not isinstance(item.action, Gang) for item in given.legal_candidates)
    assert any(isinstance(item.action, Hu) for item in given.legal_candidates)
    _assert_conserved(apply_legal_draw_hu(given), state.root_public_view)


@pytest.mark.parametrize("retained", (False, True))
@pytest.mark.parametrize("gang_code,gang_kind", (
    ("5w", GangKind.ADDED), ("1w", GangKind.CONCEALED), ("2w", GangKind.CONCEALED)))
def test_awarded_peng_preserves_all_direct_discards_and_both_gang_continuations(
        retained, gang_code, gang_kind):
    """碰获裁决后，直接跟打与原碰补杠/其他暗杠同时完整保留。"""

    before = _observation(
        ("5w",) * 3 + ("1w",) * 4 + ("2w",) * 4 + ("东", "南"),
        phase="response_peng", trigger=PublicDiscard(1, Tile("5w"), 10), wall=83)
    root = _roots(before)["peng:5w"]
    awarded = advance_given_response(
        root, window="response_peng", discard_seat=1, discarded_tile=Tile("5w"),
        responding=(2, 3, 0),
        choices=((2, Pass()), (3, Pass()), (0, Peng(Tile("5w")))),
        retained_in_river=retained).state
    _assert_conserved(awarded, awarded.root_public_view)
    given = analyze_given_claim_action(awarded, seat=0, config=_CONFIG)
    discards = [item for item in given.legal_candidates if isinstance(item.action, Discard)]
    assert {item.action.tile.code for item in discards} == {
        branch.followup_discard for branch in root.branches}
    assert {item.action_key for item in given.legal_candidates if isinstance(item.action, Gang)} == {
        "gang:added:5w", "gang:concealed:1w", "gang:concealed:2w"}
    assert not any(isinstance(item.action, Hu) for item in given.legal_candidates)
    for candidate in discards:
        _assert_conserved(apply_legal_claim_discard(given, candidate.action_key),
                          awarded.root_public_view)
    pending = apply_legal_followup_gang(given, f"gang:{gang_kind.value}:{gang_code}")
    _assert_conserved(pending, awarded.root_public_view)
    for code, capacity in zip(CANONICAL_TILE_ORDER, pending.unseen_capacities):
        if capacity == 0:
            continue
        landed = apply_given_draw(pending, Tile(code), replacement=True)
        _assert_conserved(landed, awarded.root_public_view)
        analysis = analyze_given_self_draw(landed, seat=0, dealer_seat=0, config=_CONFIG)
        assert analysis.issues == () and analysis.legal_candidates


@pytest.mark.parametrize("retained", (False, True))
def test_other_added_then_two_concealed_gangs_preserve_public_counts(retained):
    """他座先碰即补杠，再两次暗杠；只有公开动作码进入条件量具。"""

    before = _observation(("1w", "2w", "3w", "4w", "5w", "6w", "7w",
                           "8w", "9w", "1t", "2t", "东", "南"), drawn=Tile("5b"), wall=83)
    state = advance_given_response(
        _roots(before)["discard:5b"], window="response_peng", discard_seat=0,
        discarded_tile=Tile("5b"), responding=(1, 2, 3),
        choices=((1, Peng(Tile("5b"))), (2, Pass()), (3, Pass())),
        retained_in_river=retained).state
    own_hand = state.concealed
    for code, kind in (("5b", GangKind.ADDED), ("9b", GangKind.CONCEALED),
                       ("8b", GangKind.CONCEALED)):
        state = advance_given_other_gang(state, seat=1, action=Gang(Tile(code), kind))
        _assert_conserved(state, state.root_public_view)
        assert state.concealed == own_hand and state.drawn_tile is None
        with pytest.raises(ValueError, match="摸牌来源"):
            advance_given_other_draw(state, seat=1, replacement=False)
        state = advance_given_other_draw(state, seat=1, replacement=True)
        _assert_conserved(state, state.root_public_view)
    assert state.public_view.hand_counts == (13, 5, 13, 13)
    assert tuple(meld.kind for meld in state.public_view.melds[1]) == (
        "gang_bu", "gang_an", "gang_an")
    assert state.wall_remaining == 80
    discarded = advance_given_other_discard(state, seat=1, tile=Tile("7b"))
    _assert_conserved(discarded, state.root_public_view)
    assert discarded.response_trigger == (1, Tile("7b"))


@pytest.mark.parametrize("start_wall", (21, 22, 23))
def test_last_compatible_gang_draw_closes_further_gangs_but_finishes_responses(start_wall):
    """墙余21/22/23只容许1/2/3次给定杠补，20张后仍完成跟打响应。"""

    before = _observation(("1w",) * 4 + ("2w",) * 4 + ("3w",) * 3 + ("东",) * 2,
                          drawn=Tile("3w"), wall=start_wall)
    state = _roots(before)["gang:concealed:1w"].branches[0].state
    for index in range(start_wall - 20):
        state = apply_given_draw(state, Tile(("4w", "5w", "6w")[index]), replacement=True)
        _assert_conserved(state, state.root_public_view)
        given = analyze_given_self_draw(state, seat=0, dealer_seat=0, config=_CONFIG)
        if state.wall_remaining > 20:
            state = apply_legal_followup_gang(given, "gang:concealed:" + ("2w", "3w")[index])
    assert state.wall_remaining == 20
    assert not any(isinstance(item.action, Gang) for item in given.legal_candidates)
    discard = next(item for item in given.legal_candidates
                   if isinstance(item.action, Discard) and item.action.tile.code != "白")
    state = apply_legal_draw_discard(given, discard.action_key)
    for window, responding in (("response_peng", (1, 2, 3)), ("response_chi", (1,))):
        with pytest.raises(ValueError, match="已裁决"):
            finish_given_exhaustive_draw(state)
        state = advance_response_state(
            state, window=window, discard_seat=0, discarded_tile=discard.action.tile,
            responding=responding, choices=tuple((seat, Pass()) for seat in responding)).state
    ended = finish_given_exhaustive_draw(state)
    assert ended.terminal_result == progression.exhaustive_draw_result()
    _assert_conserved(ended, ended.root_public_view)


@pytest.mark.parametrize("wall", (19, 20))
def test_gang_candidates_and_other_public_gang_reject_reserve_or_below(wall):
    """三类本人杠和他座公开杠都守住<=20边界，未知墙余也不假定可杠。"""

    before = _observation(("1w",) * 4 + ("2w",) * 4 + ("3w",) * 3 + ("东",) * 2,
                          drawn=Tile("3w"), wall=wall)
    roots = _roots(before)
    assert all(not key.startswith("gang:") for key in roots)
    waiting = roots["discard:东"].branches[0].state
    with pytest.raises(ValueError, match="保留区"):
        apply_given_draw(replace(waiting, phase=ConditionalPhase.NORMAL_DRAW),
                         Tile("南"), replacement=False)
    other_action = replace(
        waiting, phase=ConditionalPhase.PUBLIC_WAIT, response_window=None,
        response_trigger=None, expected_discard_seat=1)
    with pytest.raises(ValueError, match="保留区"):
        advance_given_other_gang(other_action, seat=1,
                                 action=Gang(Tile("9b"), GangKind.CONCEALED))


@pytest.mark.parametrize("owner", (None, 0, 1))
@pytest.mark.parametrize("wall", (20, 21))
def test_owner_and_restricted_self_added_or_concealed_gang_matrix(owner, wall):
    """圈主/非圈主×临界墙余：补杠受圈约束，暗杠仍由同源规则保留。"""

    meld = PublicMeld(0, "peng", (Tile("5b"),) * 3, 2)
    before = _observation(("5b",) + ("9b",) * 4 + ("1w", "2w", "3w", "东", "南"),
                          drawn=Tile("1t"), melds=(meld,), wall=wall, owner=owner)
    # 原碰领取是否留河已有公开缺口，与正常杠转移前置分别审计。
    analysis = HangmaRules(_CONFIG).analyze(before)
    keys = {item.action_key for item in analysis.legal_candidates}
    assert ("gang:added:5b" in keys) is (wall > 20 and owner != 1)
    assert ("gang:concealed:9b" in keys) is (wall > 20)
    discards = {item.action.tile.code for item in analysis.legal_candidates
                if isinstance(item.action, Discard)}
    assert discards == ({"1t"} if owner == 1 else {tile.code for tile in before.my_hand} | {"1t"})


@pytest.mark.parametrize("replacement", (False, True))
def test_other_public_terminal_consumes_only_confirmed_draw_source(replacement):
    """普通摸/杠补两种终局正例，以及错座位、待摸、重复终局负例。"""

    before = _observation(("1w", "2w", "3w", "4w", "5w", "6w", "7w",
                           "8w", "9w", "1t", "2t", "东", "南"), drawn=Tile("白"))
    waiting = _roots(before)["discard:白"].branches[0].state
    drawn = advance_given_other_draw(waiting, seat=1)
    if replacement:
        waiting = advance_given_other_gang(
            drawn, seat=1, action=Gang(Tile("9b"), GangKind.CONCEALED))
        drawn = advance_given_other_draw(waiting, seat=1, replacement=True)
    assert waiting.other_draw_replacement is None
    assert drawn.other_draw_replacement is replacement
    event = PublicEvent(11, "round_ended", 1, result_draw=False, result_fan=2,
                        result_details=("杠开" if replacement else "普通胡",),
                        result_scores=(-4, 8, -2, -2))
    with pytest.raises(ValueError, match="已摸牌"):
        finish_given_official_other_win(waiting, event,
                                        game_id=before.game_id, round_no=before.round_no)
    with pytest.raises(ValueError, match="当前行动他座"):
        finish_given_official_other_win(drawn, replace(event, seat=2),
                                        game_id=before.game_id, round_no=before.round_no)
    ended = finish_given_official_other_win(
        drawn, event, game_id=before.game_id, round_no=before.round_no)
    assert ended.other_draw_replacement is None
    assert ended.terminal_result.score_delta == event.result_scores
    _assert_conserved(ended, ended.root_public_view)
    with pytest.raises(ValueError, match="公开行动状态"):
        finish_given_official_other_win(ended, event,
                                        game_id=before.game_id, round_no=before.round_no)


@pytest.mark.parametrize("discard_code", ("白", "1t"))
def test_waiting_draw_witness_declares_scope_without_changing_source(discard_code):
    """非白待响应和弃白等待都可作局部胡宽度见证，原根不被提升。"""

    hand = ("1w", "2w", "3w", "1b", "2b", "3b", "1t", "2t", "3t",
            "7w", "8w", "东", "东")
    before = _observation(hand, drawn=Tile(discard_code), wall=83)
    state = _roots(before)["discard:" + discard_code].branches[0].state
    for restricted in (False, True):
        witness = analyze_waiting_draw_witness(
            state, Tile("9w"), wall_remaining_before_draw=80,
            catch_restricted=restricted, config=_CONFIG)
        assert witness.local_witness_only and witness.source_state.local_witness_only
        assert witness.source_state.catch_circle is None
        assert witness.source_state.wall_remaining == 79
        assert witness.source_state.public_view.remaining_tile_count == 79
        assert witness.immediate_settlement is not None
        assert any(isinstance(item.action, Hu) for item in witness.legal_candidates)
        _assert_conserved(witness.source_state, replace(state.root_public_view,
                                                       remaining_tile_count=80))
    assert state.wall_remaining == 83 and not state.local_witness_only
    assert state.phase in (ConditionalPhase.RESPONSE_RESOLUTION, ConditionalPhase.PUBLIC_WAIT)
    assert state.drawn_tile is None
    index = CANONICAL_TILE_ORDER.index("9w")
    evidence = list(state.unseen_evidence)
    evidence[index] = "conservative"
    with pytest.raises(ValueError, match="不精确"):
        analyze_waiting_draw_witness(
            replace(state, unseen_evidence=tuple(evidence)), Tile("9w"),
            wall_remaining_before_draw=80, catch_restricted=False, config=_CONFIG)


def test_waiting_draw_witness_rejects_unawarded_claim_branches():
    """预列跟打不可变真实等待；先获裁决再跟打才可作局部见证。"""

    before = _observation(("5w",) * 3 + ("1w",) * 4 + ("2w",) * 4 + ("东", "南"),
                          phase="response_peng", trigger=PublicDiscard(1, Tile("5w"), 10))
    root = _roots(before)["peng:5w"]
    with pytest.raises(ValueError, match="未裁决"):
        analyze_waiting_draw_witness(root.branches[0].state, Tile("3b"),
                                    wall_remaining_before_draw=60,
                                    catch_restricted=False, config=_CONFIG)
    with pytest.raises(ValueError, match="合法弃后等待"):
        analyze_waiting_draw_witness(root.claim_state, Tile("3b"),
                                    wall_remaining_before_draw=60,
                                    catch_restricted=False, config=_CONFIG)


def _resolve_all_pass(state):
    """完整给定碰窗和吃窗全过；不跳过未裁决窗口。"""

    feeder, tile = state.response_trigger
    for window, responding in (
            ("response_peng", tuple((feeder + offset) % 4 for offset in (1, 2, 3))),
            ("response_chi", ((feeder + 1) % 4,))):
        state = advance_response_state(
            state, window=window, discard_seat=feeder, discarded_tile=tile,
            responding=responding, choices=tuple((seat, Pass()) for seat in responding)).state
    return state


@pytest.mark.parametrize("retained", (False, True))
def test_peng_then_whole_public_circle_then_chi_keeps_added_and_concealed_gangs(retained):
    """先碰再跟打，三家公开摸弃后再吃，仍同时保留暗杠和旧碰补杠。"""

    before = _observation(
        ("9b",) * 3 + ("1w",) * 4 + ("1t", "2t", "7w", "8w", "9w", "东"),
        phase="response_peng", trigger=PublicDiscard(1, Tile("9b"), 10), wall=83)
    state = advance_given_response(
        _roots(before)["peng:9b"], window="response_peng", discard_seat=1,
        discarded_tile=Tile("9b"), responding=(2, 3, 0),
        choices=((2, Pass()), (3, Pass()), (0, Peng(Tile("9b")))),
        retained_in_river=retained).state
    state = apply_legal_claim_discard(
        analyze_given_claim_action(state, seat=0, config=_CONFIG), "discard:东")
    for seat, code in ((1, "4b"), (2, "5b"), (3, "3t")):
        state = _resolve_all_pass(state)
        state = advance_given_other_draw(state, seat=seat)
        assert state.other_draw_replacement is False
        state = advance_given_other_discard(state, seat=seat, tile=Tile(code))
        assert state.other_draw_replacement is None
        _assert_conserved(state, state.root_public_view)
    state = advance_response_state(
        state, window="response_peng", discard_seat=3, discarded_tile=Tile("3t"),
        responding=(0, 1, 2), choices=((0, Pass()), (1, Pass()), (2, Pass()))).state
    chi = Chi((Tile("1t"), Tile("2t"), Tile("3t")))
    state = advance_response_state(
        state, window="response_chi", discard_seat=3, discarded_tile=Tile("3t"),
        responding=(0,), choices=((0, chi),), retained_in_river=retained).state
    _assert_conserved(state, state.root_public_view)
    given = analyze_given_claim_action(state, seat=0, config=_CONFIG)
    assert {item.action_key for item in given.legal_candidates if isinstance(item.action, Gang)} == {
        "gang:added:9b", "gang:concealed:1w"}
    assert {item.action.tile.code for item in given.legal_candidates if isinstance(item.action, Discard)} == {
        tile.code for tile in state.concealed}
    assert not any(isinstance(item.action, Hu) for item in given.legal_candidates)
    for key in ("gang:added:9b", "gang:concealed:1w"):
        pending = apply_legal_followup_gang(given, key)
        _assert_conserved(pending, state.root_public_view)
        for code, capacity in zip(CANONICAL_TILE_ORDER, pending.unseen_capacities):
            if capacity:
                landed = apply_given_draw(pending, Tile(code), replacement=True)
                analysis = analyze_given_self_draw(landed, seat=0, dealer_seat=0, config=_CONFIG)
                assert analysis.issues == () and analysis.legal_candidates
                _assert_conserved(landed, state.root_public_view)


def test_public_white_relay_owner_claim_and_next_owner_nonwhite_close_circle():
    """连续公开换主后圈主可碰，非白跟打关圈且下一响应恢复三座。"""

    before = _observation(("1w", "2w", "3w", "4w", "5w", "6w", "7w",
                           "8w", "9w", "1t", "2t", "东", "南"), drawn=Tile("白"), wall=83)
    state = _roots(before)["discard:白"].branches[0].state
    for seat in (1, 2):
        state = advance_given_other_draw(state, seat=seat)
        state = advance_given_other_discard(state, seat=seat, tile=Tile("白"))
        assert state.catch_circle == progression.CatchPlayState(True, seat)
        _assert_conserved(state, state.root_public_view)
    state = advance_given_other_draw(state, seat=3)
    state = advance_given_other_discard(state, seat=3, tile=Tile("9b"))
    state = advance_response_state(
        state, window="response_peng", discard_seat=3, discarded_tile=Tile("9b"),
        responding=(2,), choices=((2, Peng(Tile("9b"))),), retained_in_river=False).state
    assert state.expected_discard_seat == 2 and state.other_draw_replacement is None
    assert state.catch_circle == progression.CatchPlayState(True, 2)
    state = advance_given_other_discard(state, seat=2, tile=Tile("8b"))
    assert state.catch_circle == progression.CatchPlayState(False, None)
    assert not state.catch_restricted
    _assert_conserved(state, state.root_public_view)
    state = _resolve_all_pass(state)
    assert state.expected_draw_seat == 3
    assert state.phase is ConditionalPhase.PUBLIC_WAIT


@pytest.mark.parametrize("event_seq", (11, 20))
def test_other_terminal_must_be_later_than_consumed_official_watermark(event_seq):
    """根已消费到20时，seq11的旧终局不能因晚于snapshot10而再次生效。"""

    before = replace(_observation(
        ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
         "1t", "2t", "东", "南"), drawn=Tile("白")), consumed_seq=20,
        public_history=tuple(PublicEvent(seq, "pass", 1) for seq in range(11, 20)) + (
            PublicEvent(20, "tile_drawn", 0, (Tile("白"),)),))
    state = advance_given_other_draw(
        _roots(before)["discard:白"].branches[0].state, seat=1)
    event = PublicEvent(event_seq, "round_ended", 1, result_draw=False, result_fan=1,
                        result_details=("普通胡",), result_scores=(-2, 4, -1, -1))
    with pytest.raises(ValueError, match="官方.*水位"):
        finish_given_official_other_win(
            state, event, game_id=before.game_id, round_no=before.round_no)
    ended = finish_given_official_other_win(
        state, replace(event, seq=21), game_id=before.game_id, round_no=before.round_no)
    assert ended.terminal_result.score_delta == event.result_scores
    assert ended.public_view.consumed_seq == 20


@pytest.mark.parametrize("evidence", ("conservative", "unknown"))
def test_waiting_draw_witness_preserves_unknown_capacity_as_input_gap(evidence):
    """不确定容量不能被局部见证提升为精确，原码及其证据仍保留。"""

    before = _observation(("1w", "2w", "3w", "4w", "5w", "6w", "7w",
                           "8w", "9w", "1t", "2t", "东", "南"), drawn=Tile("白"))
    state = _roots(before)["discard:白"].branches[0].state
    index = CANONICAL_TILE_ORDER.index("5b")
    marks, capacities = list(state.unseen_evidence), list(state.unseen_capacities)
    marks[index], capacities[index] = evidence, None if evidence == "unknown" else 3
    state = replace(state, unseen_evidence=tuple(marks), unseen_capacities=tuple(capacities))
    with pytest.raises(ValueError, match="不精确"):
        analyze_waiting_draw_witness(state, Tile("5b"), wall_remaining_before_draw=60,
                                    catch_restricted=False, config=_CONFIG)
    assert state.unseen_evidence[index] == evidence
    assert state.unseen_capacities[index] == capacities[index]
    assert not state.local_witness_only
