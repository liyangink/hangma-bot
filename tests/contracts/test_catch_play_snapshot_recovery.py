"""缺史时恢复圈主的充分条件：当前牌河全部弃白都能逐座位对账。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.catch_play import analyze_catch_play
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicEvent, RulePublicState
from tests.unit.policy.support import make_observation


def sparse_observation():
    """圈主由座0转座1，中间缺非白动作；全部白板仍能被当前快照核对。"""
    history = (
        PublicEvent(1, "tile_discarded", 0, (Tile("白"),), catch_play=True),
        PublicEvent(3, "tile_discarded", 1, (Tile("白"),), catch_play=True),
        PublicEvent(6, "tile_discarded", 0, (Tile("5w"),), catch_play=True),
        PublicEvent(8, "timeout", 1, detail_kind="discard"),
    )
    return make_observation(
        snapshot_seq=8, consumed_seq=8, public_history=history,
        discards=((Tile("白"), Tile("5w")), (Tile("白"),), (), ()),
        rule_state=RulePublicState(Tile("白"), False, 0, True),
    )


def test_current_snapshot_accounts_for_every_white_despite_missing_nonwhite_events():
    context = analyze_catch_play(sparse_observation())

    assert (context.owner_seat, context.started_seq, context.issue) == (1, 3, None)
    assert context.source == "snapshot-white-accounting"
    assert context.restricts(0) and not context.restricts(1)


@pytest.mark.parametrize("problem", [
    "missing_white", "duplicate_white", "future_event", "stale_snapshot",
    "owner_already_discarded", "incompatible_river", "unknown_transition", "closed_flag",
])
def test_incomplete_or_conflicting_white_accounting_cannot_grant_owner_privilege(problem):
    observation = sparse_observation()
    if problem == "missing_white":
        observation = replace(observation, discards=(observation.discards[0], observation.discards[1], (Tile("白"),), ()))
    elif problem == "duplicate_white":
        observation = replace(observation, public_history=(observation.public_history[0],) + observation.public_history)
    elif problem == "future_event":
        observation = replace(observation, public_history=observation.public_history + (PublicEvent(9, "tile_drawn", 1),))
    elif problem == "stale_snapshot":
        observation = replace(observation, consumed_seq=9)
    elif problem == "owner_already_discarded":
        observation = replace(observation, discards=(observation.discards[0], (Tile("白"), Tile("6w")), (), ()))
    elif problem == "incompatible_river":
        observation = replace(observation, discards=((Tile("白"), Tile("6w")), observation.discards[1], (), ()))
    elif problem == "unknown_transition":
        observation = replace(observation, public_history=observation.public_history[:-1] + (PublicEvent(8, "unknown_rule_action", 1),))
    else:
        observation = replace(observation, public_history=observation.public_history[:2] + (
            replace(observation.public_history[2], catch_play=False), observation.public_history[3],
        ))

    context = analyze_catch_play(observation)

    assert context.active and context.owner_seat is None
    assert context.issue and all(context.restricts(seat) for seat in range(4))


def _official_owner_observation_with_discard_timeout():
    """复现 2026-09-23 自动房 a_e2b2d94b31c1_r1_b3_t0 的降级场景。

    快照（seq=201）时圈活跃、圈主为座 2；随后座 2 弃非白关圈，紧随
    timeout(kind=discard) 窗口记账与响应窗口走满，到当前水位本人摸牌。
    timeout(discard) 与同座位紧邻弃牌成对（官方代打动作已在弃牌事件中），
    不应阻断圈主推导。
    """
    history = (
        PublicEvent(202, "tile_discarded", 2, (Tile("5w"),), catch_play=False),
        PublicEvent(203, "timeout", 2, detail_kind="discard"),
        PublicEvent(204, "timeout", 1, detail_kind="response"),
        PublicEvent(205, "timeout", 3, detail_kind="response"),
        PublicEvent(206, "timeout", 1, detail_kind="response"),
        PublicEvent(207, "tile_drawn", 3),
        PublicEvent(208, "tile_discarded", 3, (Tile("北"),), catch_play=False),
        PublicEvent(209, "timeout", 0, detail_kind="response"),
        PublicEvent(210, "tile_drawn", 0),
    )
    return make_observation(
        snapshot_seq=201, consumed_seq=210, public_history=history,
        rule_state=RulePublicState(Tile("白"), False, 0, True, catch_play_owner_seat=2),
    )


def test_discard_timeout_bookkeeping_does_not_block_owner_derivation():
    """打牌窗口记账夹在快照与水位之间时，官方圈主路径必须完成推导。"""

    context = analyze_catch_play(_official_owner_observation_with_discard_timeout())

    assert context.issue is None
    assert context.active is False and context.owner_seat is None
    assert context.source == "official-snapshot+continuous-events"
    assert not any(context.restricts(seat) for seat in range(4))


def test_timeout_without_detail_kind_still_degrades_owner_derivation():
    """缺 detail_kind 的 timeout 无法排除自动动作，保持保守未知（回归保护）。"""

    observation = replace(
        _official_owner_observation_with_discard_timeout(),
        public_history=(
            PublicEvent(202, "tile_discarded", 2, (Tile("5w"),), catch_play=False),
            PublicEvent(203, "timeout", 2),
            PublicEvent(204, "timeout", 1, detail_kind="response"),
            PublicEvent(205, "timeout", 3, detail_kind="response"),
            PublicEvent(206, "timeout", 1, detail_kind="response"),
            PublicEvent(207, "tile_drawn", 3),
            PublicEvent(208, "tile_discarded", 3, (Tile("北"),), catch_play=False),
            PublicEvent(209, "timeout", 0, detail_kind="response"),
            PublicEvent(210, "tile_drawn", 0),
        ),
    )

    context = analyze_catch_play(observation)

    assert context.issue is not None
    assert context.owner_seat is None
