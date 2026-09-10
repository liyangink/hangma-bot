"""hangma.progression 规则推进单元测试（本线新增文件，不改既有测试）。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from hangma_bot.hangma.progression import (
    SeatProgression,
    ProgressionState,
    attach_draw,
    chain_after_discard,
    chain_after_gang,
    deal_state,
    next_dealer,
    recompute_baotou,
    resolve,
)
from hangma_bot.kernel.actions import Discard, Gang, GangKind, Hu, Pass, Peng, Tile
from hangma_bot.kernel.observation import PublicDiscard


def _state():
    """构造一个三座位响应窗口的最小推进状态（碰窗口，弃牌 5w）。"""
    seats = tuple(
        SeatProgression(
            hand=tuple(Tile(c) for c in (["5w", "5w"] if i == 1 else ["1b", "2b", "3b"])),
            melds=(), discards=(), drawn=None,
            catch_play=False, chain_count=0, chain_piao=0, baotou=False,
        )
        for i in range(4)
    )
    return ProgressionState(
        round_no=1, dealer_seat=0, base_score=1, seats=seats,
        scores=(0, 0, 0, 0), wall_drawable=63, wall_total=83, seq=1,
        window="response_peng", turn_seat=0, responding=(1, 2, 3),
        trigger_seq=1, last_discard=PublicDiscard(seat=0, tile=Tile("5w"), seq=1),
        pending_draw=None, hand_result=None,
    )


def _junk():
    return tuple(Tile(c) for c in ["1b", "4b", "7b", "2t", "5t", "8t", "3w", "6w", "9w", "东", "南", "西", "北"])


def test_discard_then_peng_window():
    state = deal_state(1, 0, (_junk(), _junk(), _junk(), _junk()), (0, 0, 0, 0), 0, 1, 63, 83)
    state = attach_draw(state, Tile("5w")).state
    transition = resolve(state, ((0, Discard(Tile("5w"))),))
    assert transition.blocked is None
    assert transition.state.window == "response_peng"
    assert transition.state.responding == (1, 2, 3)
    assert transition.state.turn_seat == 0  # 弃牌后行动权停留在弃牌者
    assert transition.state.last_discard.tile.code == "5w"
    assert transition.state.trigger_seq == transition.events[0].seq
    assert transition.events[0].kind == "tile_discarded"
    assert dict(transition.events[0].data)["catch_play"] is False


def test_all_pass_opens_chi_window_then_draw():
    state = _state()
    transition = resolve(state, ((1, Pass()), (2, Pass()), (3, Pass())))
    assert transition.state.window == "response_chi"
    assert transition.state.responding == (1,)
    assert [e.kind for e in transition.events] == ["pass", "pass", "pass"]
    transition2 = resolve(transition.state, ((1, Pass()),))
    assert transition2.state.window == "pending_draw"
    assert transition2.state.pending_draw.seat == 1


def test_single_claim_peng_resolves():
    state = _state()
    transition = resolve(state, ((1, Peng(Tile("5w"))), (2, Pass()), (3, Pass())))
    assert transition.state.window == "draw"
    assert transition.state.turn_seat == 1
    seat = transition.state.seats[1]
    assert seat.melds[0].kind == "peng"
    assert seat.drawn is None  # 碰后出牌窗口：无摸牌
    assert seat.baotou is False  # 副露后爆头保守重置（待确认口径）
    assert [e.kind for e in transition.events] == ["pass", "pass", "peng"]


def test_multi_claim_blocked_no_priority():
    """两家同时碰 → blocked：官方无优先级证据，禁止先到先得（契约 §6）。"""
    state = _state()
    seats = list(state.seats)
    seats[3] = replace(seats[3], hand=(Tile("5w"), Tile("5w"), Tile("1b")))
    state = replace(state, seats=tuple(seats))
    transition = resolve(state, ((1, Peng(Tile("5w"))), (2, Pass()), (3, Peng(Tile("5w")))))
    assert transition.blocked is not None
    assert "先到先得" in transition.blocked
    assert transition.events == ()


def test_chain_transitions():
    wealth = Tile("白")
    normal = Tile("1w")
    assert chain_after_discard(0, 0, False, wealth) == (0, 0)  # 非爆头打白=普通弃牌断链
    assert chain_after_discard(2, 1, True, wealth) == (3, 2)  # 爆头打白=飘
    assert chain_after_discard(2, 1, False, normal) == (0, 0)
    assert chain_after_gang(2, 1) == (3, 1)


def test_next_dealer_rotation():
    # v15 明文确认流局连庄；官方牌谱金例另外确认闲家胡后由赢家坐庄。
    assert next_dealer(0, None, True) == 0
    assert next_dealer(2, 2, False) == 2
    assert next_dealer(2, 0, False) == 0
    assert next_dealer(3, 1, False) == 1
    assert next_dealer(1, None, False) == 1  # 赢家未知时沿用既有保守行为。


def test_recompute_baotou():
    any_tile = tuple(Tile(c) for c in ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "白"])
    specific = tuple(Tile(c) for c in ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "东", "东", "东", "白", "北"])
    assert recompute_baotou(any_tile, 0, 2) is True
    assert recompute_baotou(specific, 0, 2) is False
    four_white = tuple(Tile(c) for c in "1w 2w 3w 4w 5w 6w 7b 8b 9b 白 白 白 白".split())
    assert recompute_baotou(four_white, 0, 4) is True  # v23：四白也按任意听判定。


def test_wealth_discard_skips_windows_and_circle_flag():
    """弃白不开响应窗口（v14 夹具 4/4）；圈主旗标持续到其下次弃牌。"""
    state = deal_state(1, 0, (_junk(), _junk(), _junk(), _junk()), (0, 0, 0, 0), 0, 1, 5, 25)
    t1 = attach_draw(state, Tile("白"))
    assert t1.events == ()  # 庄家直抽无事件（官方 v10）
    assert t1.state.window == "draw"
    assert t1.state.trigger_seq == 0
    t2 = resolve(t1.state, ((0, Discard(Tile("白"))),))
    assert t2.state.window == "pending_draw"  # 弃白无响应窗口，直接下家摸牌
    assert t2.state.seats[0].catch_play is True
    assert dict(t2.events[0].data)["catch_play"] is True
    # v26：三家依次摸切；每次只给圈主碰窗，供牌者为上家时才有吃窗。
    state = t2.state
    for seat, code in ((1, "1w"), (2, "4w"), (3, "5w")):
        drawn = attach_draw(state, Tile(code))
        discarded = resolve(drawn.state, ((seat, Discard(Tile(code))),))
        assert discarded.state.window == "response_peng"
        assert discarded.state.responding == (0,)
        assert discarded.state.seats[0].catch_play is True
        passed = resolve(discarded.state, ((0, Pass()),))
        if seat == 3:
            assert passed.state.window == "response_chi" and passed.state.responding == (0,)
            passed = resolve(passed.state, ((0, Pass()),))
        assert passed.state.window == "pending_draw"
        assert passed.state.pending_draw.seat == (seat + 1) % 4
        state = passed.state
    owner_draw = attach_draw(state, Tile("6w"))
    assert owner_draw.state.turn_seat == 0 and owner_draw.state.seats[0].catch_play
    closed = resolve(owner_draw.state, ((0, Discard(Tile("6w"))),))
    assert closed.state.seats[0].catch_play is False
    assert closed.state.responding == (1, 2, 3)


def test_win_settlement_exact_chain():
    """胡牌结算取推进状态精确链/piao/爆头（杠开 fan=2）。"""
    hand13 = tuple(Tile(c) for c in ["1w", "1w", "1w", "2w", "3w", "4w", "7w", "8w", "9w", "5w", "6w", "东", "东"])
    state = deal_state(1, 0, (hand13, _junk(), _junk(), _junk()), (0, 0, 0, 0), 0, 1, 63, 83)
    state = attach_draw(state, Tile("1w")).state
    t1 = resolve(state, ((0, Gang(Tile("1w"), GangKind.CONCEALED)),))
    assert t1.state.window == "pending_draw"
    assert t1.state.pending_draw.replacement is True
    assert t1.state.seats[0].chain_count == 1
    t2 = attach_draw(t1.state, Tile("7w"))
    assert t2.state.seats[0].chain_count == 1
    t3 = resolve(t2.state, ((0, Hu()),))
    result = t3.state.hand_result
    assert result.winner_seat == 0
    assert result.fan == 2
    assert result.details == ("平胡", "杠开")
    assert result.score_delta == (48, -16, -16, -16)


def test_choice_order_does_not_change_resolution():
    state = _state()
    seats = list(state.seats)
    seats[1] = replace(seats[1], hand=(Tile("5w"), Tile("5w"), Tile("1b")))
    state = replace(state, seats=tuple(seats))
    a = resolve(state, ((1, Peng(Tile("5w"))), (2, Pass()), (3, Pass())))
    b = resolve(state, ((3, Pass()), (2, Pass()), (1, Peng(Tile("5w")))))
    assert a.state == b.state
    assert a.events == b.events


def test_peng_window_missing_or_wrong_choices():
    state = _state()
    with pytest.raises(ValueError):
        resolve(state, ())
    with pytest.raises(ValueError):
        resolve(state, ((0, Pass()),))  # 非响应者座位
