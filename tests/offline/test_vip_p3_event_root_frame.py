"""结果盲事件抽样框只可含参考路径行动前事实。"""

import hashlib

import pytest

from hangma_bot.kernel.serialization import observation_from_json
from scripts.vip_p3_event_root_frame import scan


def test_event_frame_is_deterministic_and_preserves_action_time_identity():
    """已命中根的观察、窗口身份和标签可重算且不含教师结果。"""

    first = scan(start_seed=5001, seeds=3)
    assert first == scan(start_seed=5001, seeds=3)
    assert first["root_count"] == 12
    assert first["reached_counts"]["normal_draw_10"] == 1
    assert first["reached_counts"]["normal_draw_12"] == 0
    assert first["reached_counts"]["first_wall_le_40"] == 0
    identities = set()
    opponent_meld_roots = 0
    for root in first["selected_roots"]:
        observation = observation_from_json(root["observation"])
        assert hashlib.sha256(repr(observation).encode()).hexdigest() == root["root_id"]
        assert root["phase"] == observation.phase
        assert root["remaining_tile_count"] == observation.remaining_tile_count
        assert root["initial_dealer"] == observation.dealer_seat == root["seed"] % 4
        opponent_meld_roots += bool(sum(
            len(observation.melds[seat]) for seat in range(4)
            if seat != observation.seat
        ))
        assert not ({"outcomes_by_action", "terminal", "first_event"} & root.keys())
        assert (root["seed"], root["frame_revision"], root["root_id"]) not in identities
        identities.add((root["seed"], root["frame_revision"], root["root_id"]))
    assert opponent_meld_roots > 0


@pytest.mark.parametrize("start_seed,seeds", [(-1, 1), (0, 0), (True, 1), (0, True)])
def test_invalid_event_frame_ranges_are_rejected(start_seed, seeds):
    with pytest.raises(ValueError, match="范围无效"):
        scan(start_seed=start_seed, seeds=seeds)
