"""互斥终局与同根、同世界配对不能因缺行而看似改善。"""

from copy import deepcopy

import pytest

from scripts.vip_p3_competing_tail_audit import audit


def _report(name: str, points: list[list[int]]) -> dict:
    """一根、两动作、两相关世界；积分按座位 0—3。"""

    keys = ("discard:1w", "discard:2w")
    return {
        "scope": "P3_offline_teacher_labels_only_not_candidate_policy_value",
        "reference": "shape", "continuation_reference": name,
        "start_seed": 1, "requested_seeds": 1,
        "selection_tag": "first_two_white", "worlds_per_root": 2,
        "rows": [{
            "seed": 1, "root_id": "same-observation", "sample_count": 2,
            "observation": {"seat": 0}, "legal_action_keys": list(keys),
            "outcomes_by_action": {
                key: [{
                    "sample": sample, "first_event_key": "self_normal_draw:1w",
                    "terminal": {
                        "winner_seat": 0 if value > 0 else 1,
                        "is_draw": False, "fan": 4 if value >= 96 else 1,
                        "score_delta": [value, -value, 0, 0],
                    },
                } for sample, value in enumerate(values)]
                for key, values in zip(keys, points)
            },
        }],
    }


def test_identical_first_event_can_hide_opposite_terminal_action_value():
    first = _report("shape", [[24, 24], [0, 0]])
    second = _report("shape_white_hold", [[0, 0], [96, 96]])
    result = audit(first, second)
    assert result["first_event_key_changed_action_worlds"] == 0
    assert result["paired_action_directions_vs_first_legal"]["opposite"] == 1
    assert result["roots_with_opposite_action_pair"] == 1
    assert result["outcomes"]["shape_white_hold"] == {
        "self_low": 0, "self_high": 2, "other_win": 2, "draw": 0,
    }


def test_missing_world_or_nonconserving_settlement_is_rejected():
    first = _report("shape", [[24, 24], [0, 0]])
    second = _report("shape_white_hold", [[0, 0], [96, 96]])
    missing = deepcopy(second)
    missing["rows"][0]["outcomes_by_action"]["discard:2w"].pop()
    with pytest.raises(ValueError, match="隐藏世界编号"):
        audit(first, missing)
    broken = deepcopy(second)
    broken["rows"][0]["outcomes_by_action"]["discard:2w"][0]["terminal"][
        "score_delta"][1] = 0
    with pytest.raises(ValueError, match="四座整数积分"):
        audit(first, broken)


def test_changed_observation_cannot_be_paired():
    first = _report("shape", [[24, 24], [0, 0]])
    second = _report("shape_white_hold", [[0, 0], [96, 96]])
    second["rows"][0]["observation"]["seat"] = 1
    with pytest.raises(ValueError, match="同根玩家观察"):
        audit(first, second)
