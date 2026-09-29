"""公开响应裁决和圈主规则：条件输入不需要他家暗牌或伪造官方序号。"""

import pytest

from hangma_bot.hangma.progression import (
    CatchPlayState,
    ProgressionState,
    SeatProgression,
    catch_play_after_discard,
    resolve,
    resolve_public_response,
)
from hangma_bot.kernel.actions import Chi, Gang, GangKind, Pass, Peng, Tile
from hangma_bot.kernel.observation import PublicDiscard


FIVE = Tile("5w")
NO_CIRCLE = CatchPlayState(False, None)


def _peng(choices, circle=NO_CIRCLE, responders=(1, 2, 3)):
    return resolve_public_response(
        "response_peng", 0, FIVE, responders, choices, circle,
    )


def test_missing_choice_is_unready_and_cannot_be_treated_as_all_pass():
    result = _peng(((1, Pass()), (3, Pass())))
    assert result.status == "unready"
    assert result.missing_seats == (2,)
    assert result.next_window is None and result.pass_seats == ()


def test_partial_choices_still_reject_a_claim_for_the_wrong_discard():
    with pytest.raises(ValueError, match="碰牌与触发弃牌不一致"):
        _peng(((1, Peng(Tile("6w"))), (3, Pass())))


def test_all_pass_peng_opens_chi_then_pass_requests_next_draw():
    peng = _peng(((3, Pass()), (1, Pass()), (2, Pass())))
    assert (peng.status, peng.pass_seats, peng.next_window, peng.next_responding) == (
        "resolved", (1, 2, 3), "response_chi", (1,),
    )
    chi = resolve_public_response(
        "response_chi", 0, FIVE, (1,), ((1, Pass()),), NO_CIRCLE,
    )
    assert (chi.status, chi.pass_seats, chi.next_window, chi.next_draw_seat) == (
        "resolved", (1,), "pending_draw", 1,
    )


def test_single_peng_or_exposed_gang_and_multi_claim_block():
    peng = _peng(((3, Pass()), (1, Peng(FIVE)), (2, Pass())))
    assert (peng.status, peng.pass_seats, peng.claim_seat, peng.next_window) == (
        "resolved", (2, 3), 1, "draw",
    )
    gang = _peng(((1, Gang(FIVE, GangKind.EXPOSED)), (2, Pass()), (3, Pass())))
    assert (gang.status, gang.claim_seat, gang.next_window) == (
        "resolved", 1, "pending_draw",
    )
    blocked = _peng(((1, Peng(FIVE)), (2, Pass()), (3, Gang(FIVE, GangKind.EXPOSED))))
    assert blocked.status == "blocked" and "先到先得" in blocked.reason
    assert blocked.pass_seats == () and blocked.claim_seat is None


def test_catch_owner_transfer_close_and_response_identity():
    circle = catch_play_after_discard(NO_CIRCLE, 0, Tile("白"))
    assert circle == CatchPlayState(True, 0)
    assert catch_play_after_discard(circle, 1, Tile("2w")) == circle
    circle = catch_play_after_discard(circle, 2, Tile("白"))
    assert circle == CatchPlayState(True, 2)
    owner_pass = _peng(((2, Pass()),), circle, (2,))
    assert owner_pass.next_window == "pending_draw" and owner_pass.next_draw_seat == 1
    with pytest.raises(ValueError, match="响应身份"):
        _peng(((1, Pass()),), circle, (1,))
    assert catch_play_after_discard(circle, 2, Tile("3w")) == NO_CIRCLE
    assert catch_play_after_discard(CatchPlayState(True, None), 1, FIVE) == CatchPlayState(True, None)
    unknown = resolve_public_response(
        "response_peng", 0, FIVE, (1,), ((1, Pass()),), CatchPlayState(True, None),
    )
    assert unknown.status == "unready" and unknown.next_window is None


def test_owner_as_next_seat_may_reach_chi_window():
    circle = CatchPlayState(True, 1)
    peng = _peng(((1, Pass()),), circle, (1,))
    assert peng.next_window == "response_chi" and peng.next_responding == (1,)
    chi = resolve_public_response(
        "response_chi", 0, FIVE, (1,),
        ((1, Chi((Tile("3w"), Tile("4w"), FIVE))),), circle,
    )
    assert chi.status == "resolved" and chi.claim_seat == 1 and chi.next_window == "draw"


def test_chi_claim_keeps_undrawn_action_window_for_immediate_gang():
    """官方 v18 本人可见 seq2267 吃→2268 暗杠，不能把吃后限定为弃牌。"""
    hand = (Tile("3w"), Tile("4w")) + (Tile("1b"),) * 4 + tuple(
        Tile(code) for code in ("2t", "3t", "4t", "5t", "6t", "7t", "8t")
    )
    seats = tuple(
        SeatProgression(
            hand=hand if i == 1 else (), melds=(), discards=(), drawn=None,
            catch_play=False, chain_count=0, chain_piao=0, baotou=False,
        )
        for i in range(4)
    )
    state = ProgressionState(
        round_no=1, dealer_seat=0, base_score=1, seats=seats,
        scores=(0, 0, 0, 0), wall_drawable=50, wall_total=70, seq=10,
        window="response_chi", turn_seat=0, responding=(1,), trigger_seq=10,
        last_discard=PublicDiscard(0, FIVE, 10), pending_draw=None, hand_result=None,
    )
    chi = resolve(state, ((1, Chi((Tile("3w"), Tile("4w"), FIVE))),))
    assert chi.state.window == "draw" and chi.state.turn_seat == 1
    assert chi.state.seats[1].drawn is None
    gang = resolve(chi.state, ((1, Gang(Tile("1b"), GangKind.CONCEALED)),))
    assert gang.state.window == "pending_draw"
    assert gang.state.pending_draw.replacement is True


def test_invalid_response_choices_do_not_create_a_resolution():
    with pytest.raises(ValueError, match="重复"):
        _peng(((1, Pass()), (1, Pass()), (2, Pass()), (3, Pass())))
    with pytest.raises(ValueError, match="触发弃牌"):
        _peng(((1, Peng(Tile("6w"))), (2, Pass()), (3, Pass())))
    with pytest.raises(ValueError, match="明杠"):
        _peng(((1, Gang(FIVE, GangKind.CONCEALED)), (2, Pass()), (3, Pass())))
    with pytest.raises(ValueError, match="非白"):
        resolve_public_response("response_peng", 0, Tile("白"), (1, 2, 3), (), NO_CIRCLE)
