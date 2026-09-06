"""官方指南 v18 §1.2/1.3 的定向动作转移回归（2026-09-06）。

通过公开 resolve/attach_draw 检查听牌态和动作链；不读取线上资料，不依赖
随机实战触发。规则来源：review/official-adapter/guide-v18-20260906/guide.json。
弃牌后 13−3m 张是完整听牌态，直接应用“摸任意一张即胡”的定义。
"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.progression import (
    DrawRequest, MeldRecord, attach_draw, deal_state, resolve,
)
from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Pass, Peng, Tile
from hangma_bot.kernel.observation import PublicDiscard


def _tiles(codes: str) -> tuple[Tile, ...]:
    return tuple(Tile(code) for code in codes.split())


def _state(hand: str, *, baotou=False, count=0, piao=0, melds=()):
    """构造本人可见的动作前态；其他座位不参与本组规则判断。"""
    other = _tiles("1b 2b 3b 4b 5b 6b 7b 8b 9b 南 南 西 西")
    state = deal_state(1, 0, (_tiles(hand), other, other, other), (0, 0, 0, 0), 0, 1, 60, 80)
    seat = replace(state.seats[0], baotou=baotou, chain_count=count, chain_piao=piao, melds=melds)
    return replace(state, seats=(seat,) + state.seats[1:])


def _next_own_draw(state, tile: str, *, replacement=False):
    """注入下一次本人摸牌；省略不会改变本人暗牌和链的他家动作。"""
    state = replace(
        state, window="pending_draw", turn_seat=None, responding=(),
        pending_draw=DrawRequest(0, replacement, state.seq + 1, True, True),
    )
    return attach_draw(state, Tile(tile)).state


def test_discard_can_enter_baotou_without_starting_an_action_chain():
    """普通弃牌清链，但弃后四面子加单白仍须进入爆头听牌态。"""
    hand = _tiles("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 白 北")
    other = _tiles("1b 2b 3b 4b 5b 6b 7b 8b 9b 南 南 西 西")
    state = deal_state(1, 0, (hand, other, other, other), (0, 0, 0, 0), 0, 1, 60, 80)
    state = attach_draw(state, Tile("东")).state
    assert state.seats[0].baotou is False

    state = resolve(state, ((0, Discard(Tile("北"))),)).state

    assert state.seats[0].baotou is True
    assert state.seats[0].chain_count == 0
    assert state.seats[0].chain_piao == 0


@pytest.mark.parametrize("discard,expected_baotou", [("9b", True), ("3w", False)])
def test_normal_discard_breaks_chain_independently_of_remaining_baotou(discard, expected_baotou):
    """同一旧爆头态，打回新摸牌保持听牌，拆顺子退出；两者都断链。"""
    state = _state("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 东 白", baotou=True, count=2, piao=1)
    state = _next_own_draw(state, "9b")
    state = resolve(state, ((0, Discard(Tile(discard))),)).state
    assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (0, 0)
    assert state.seats[0].baotou is expected_baotou


def test_non_baotou_white_discard_can_enter_baotou_but_is_not_piao():
    """手留四白不爆头；弃白后进入任意听不能倒算本次弃白为飘。"""
    state = _state("1w 2w 3w 4w 5w 6w 东 东 东 北 白 白 白", count=2, piao=0)
    state = _next_own_draw(state, "白")
    assert state.seats[0].baotou is False
    state = resolve(state, ((0, Discard(Tile("白"))),)).state
    assert state.seats[0].baotou is True
    assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (0, 0)


@pytest.mark.parametrize("claim", ["chi", "peng", "ming"])
def test_claims_preserve_existing_baotou_and_only_gang_increases_chain(claim):
    """已确认采用的持续状态语义：吃碰不清爆头，明杠只增加链动作。"""
    hand = "1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 东 白"
    state = _state(hand, baotou=True, count=2, piao=1)
    tile = Tile("1w") if claim == "chi" else Tile("东")
    state = replace(
        state, window="response_chi" if claim == "chi" else "response_peng",
        turn_seat=3, responding=(0,) if claim == "chi" else (0, 1, 2),
        last_discard=PublicDiscard(3, tile, 0), pending_draw=None,
    )
    if claim == "chi":
        choices = ((0, Chi(_tiles("1w 2w 3w"))),)
    else:
        action = Peng(tile) if claim == "peng" else Gang(tile, GangKind.EXPOSED)
        choices = ((0, action), (1, Pass()), (2, Pass()))
    state = resolve(state, choices).state
    assert state.seats[0].baotou is True
    assert state.seats[0].chain_count == (3 if claim == "ming" else 2)
    assert state.seats[0].chain_piao == 1
    assert state.seats[0].drawn is None


@pytest.mark.parametrize("kind", [GangKind.CONCEALED, GangKind.ADDED])
def test_self_gang_preserves_prior_baotou_and_increments_chain(kind):
    if kind is GangKind.CONCEALED:
        state = _state("1w 1w 1w 1w 2w 3w 4w 5w 6w 7w 东 东 白", baotou=True, count=2, piao=1)
        drawn = Tile("东")
    else:
        meld = MeldRecord("peng", None, _tiles("1w 1w 1w"), 3)
        state = _state("2w 3w 4w 5w 6w 7w 东 东 白 北", baotou=True, count=2, piao=1, melds=(meld,))
        drawn = Tile("1w")
    seat = replace(state.seats[0], drawn=drawn)
    state = replace(state, seats=(seat,) + state.seats[1:], window="draw", turn_seat=0, pending_draw=None)
    state = resolve(state, ((0, Gang(Tile("1w"), kind)),)).state
    assert state.seats[0].baotou is True
    assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (3, 1)
    assert state.pending_draw.replacement is True


def test_concealed_gang_can_form_new_baotou_before_replacement_draw():
    """原13张非任意听，移出暗杠后成为三面子加单白；补牌可新进入。"""
    state = _state("1w 1w 1w 1w 2w 3w 4w 5w 6w 7w 东 东 白")
    state = _next_own_draw(state, "东")
    assert state.seats[0].baotou is False
    state = resolve(state, ((0, Gang(Tile("1w"), GangKind.CONCEALED)),)).state
    state = attach_draw(state, Tile("北")).state
    assert state.seats[0].baotou is True
    assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (1, 0)


def test_replacement_draw_preserves_prior_baotou_when_static_shape_changes():
    """用户确认的持续语义；补牌不能抹掉动作前爆头，普通摸牌则重算。"""
    meld = MeldRecord("gang", "an", _tiles("1w 1w 1w 1w"), None)
    base = _state("2w 3w 4w 5w 6w 7w 东 东 白 北", baotou=True, count=1, melds=(meld,))
    replacement = _next_own_draw(base, "9b", replacement=True)
    ordinary = _next_own_draw(base, "9b")
    assert replacement.seats[0].baotou is True
    assert ordinary.seats[0].baotou is False


def test_four_held_whites_override_inherited_baotou_on_replacement_draw():
    meld = MeldRecord("gang", "an", _tiles("1w 1w 1w 1w"), None)
    state = _state("2w 3w 4w 东 东 东 北 白 白 白", baotou=True, count=1, melds=(meld,))
    state = _next_own_draw(state, "白", replacement=True)
    assert state.seats[0].baotou is False


def test_piao_gang_piao_chain_break_and_restart():
    """确定序列：飘→暗杠→飘累计；普通弃牌断链；新杠从1开始。"""
    state = _state("1w 1w 1w 2w 2w 2w 3w 3w 3w 东 白 白 白")
    state = _next_own_draw(state, "东")
    state = resolve(state, ((0, Discard(Tile("白"))),)).state
    assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (1, 1)
    state = _next_own_draw(state, "3w")
    state = resolve(state, ((0, Gang(Tile("3w"), GangKind.CONCEALED)),)).state
    state = attach_draw(state, Tile("白")).state
    assert state.seats[0].baotou is True  # 手留3白+已飘1白=4，不适用手留4白排除。
    assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (2, 1)
    state = resolve(state, ((0, Discard(Tile("白"))),)).state
    assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (3, 2)
    state = _next_own_draw(state, "北")
    state = resolve(state, ((0, Discard(Tile("北"))),)).state
    assert state.seats[0].baotou is True
    assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (0, 0)
    state = _next_own_draw(state, "1w")
    state = resolve(state, ((0, Gang(Tile("1w"), GangKind.CONCEALED)),)).state
    assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (1, 0)


def test_three_consecutive_piao_keep_baotou_and_reach_four_white_total():
    """四面子单白连续摸白弃白：三次飘后手留1白，链内3白。"""
    state = _state("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 东 白")
    for expected in (1, 2, 3):
        state = _next_own_draw(state, "白")
        assert state.seats[0].baotou is True
        state = resolve(state, ((0, Discard(Tile("白"))),)).state
        assert state.seats[0].baotou is True
        assert (state.seats[0].chain_count, state.seats[0].chain_piao) == (expected, expected)
    assert sum(tile.code == "白" for tile in state.seats[0].hand) == 1


def test_non_dealer_initial_baotou_survives_claim_before_first_own_draw():
    """闲家起手任意听，首次摸牌前吃→暗杠；补牌须继承起手爆头。

    本例四家起手与两次注入摸牌均不超过每种牌四张。吃后杠补前的暗牌
    已不是任意听，所以补牌处 True 必须来自起手生命周期，不能碰巧重算得到。
    """
    dealer = _tiles("1t 2t 3t 4t 5t 6t 7t 8t 9t 东 东 北 北")
    claimant = _tiles("1w 1w 1w 1w 白 白 2w 3w 4w 2w 3w 4w 6w")
    other = _tiles("1b 2b 3b 4b 5b 6b 7b 8b 9b 南 南 西 西")
    state = deal_state(1, 0, (dealer, claimant, other, other), (0, 0, 0, 0), 0, 1, 60, 80)
    state = attach_draw(state, Tile("2w")).state
    state = resolve(state, ((0, Discard(Tile("2w"))),)).state
    state = resolve(state, ((1, Pass()), (2, Pass()), (3, Pass()))).state
    state = resolve(state, ((1, Chi(_tiles("2w 3w 4w"))),)).state
    state = resolve(state, ((1, Gang(Tile("1w"), GangKind.CONCEALED)),)).state
    state = attach_draw(state, Tile("2w")).state
    assert state.seats[1].baotou is True
    assert (state.seats[1].chain_count, state.seats[1].chain_piao) == (1, 0)
