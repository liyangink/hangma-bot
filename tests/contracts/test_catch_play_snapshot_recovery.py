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
