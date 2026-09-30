"""两名续打者的动作差方向按根而非动作世界计数。"""

from copy import deepcopy

import pytest

from scripts.vip_p3_reference_sensitivity import compare


def _teacher(reference: str, scores: dict[str, list[int]]) -> dict:
    """一个根、两个共享编号的隐藏世界，填入本座最终净积分。"""

    return {
        "scope": "P3_offline_teacher_labels_only_not_candidate_policy_value",
        "reference": "shape", "continuation_reference": reference,
        "selection_tag": "first_two_white", "worlds_per_root": 2,
        "rows": [{
            "seed": 1, "root_id": "frozen-root", "observation": {"seat": 0},
            "legal_action_keys": list(scores), "sample_count": 2,
            "outcomes_by_action": {
                action: [
                    {"sample": sample,
                     "terminal": {"score_delta": [value, -value, 0, 0],
                                  "winner_seat": 0 if value > 0 else 1,
                                  "fan": 4 if value >= 96 else 1}}
                    for sample, value in enumerate(values)]
                for action, values in scores.items()
            },
        }],
    }


def test_opposite_action_direction_is_counted_once_under_one_root():
    """相同两世界下续打者会翻转动作顺序，根分母始终是一。"""

    shape = _teacher("shape", {"discard:1w": [24, 24], "discard:2w": [0, 0]})
    alternate = _teacher("r18_frozen", {
        "discard:1w": [0, 0], "discard:2w": [96, 96]})
    result = compare(shape, alternate)
    assert result["root_count"] == 1
    assert result["roots_with_opposite_pair"] == 1
    assert result["rows"][0]["pair_counts"] == {
        "both_zero": 0, "both_nonzero_same_sign": 0,
        "both_nonzero_opposite_sign": 1, "one_zero": 0,
    }
    assert result["rows"][0]["self_four_fan_action_worlds"] == {
        "shape": 0, "r18_frozen": 2,
    }


def test_changed_root_identity_is_rejected():
    """不同观察的动作结果不得拿来比较续打敏感性。"""

    shape = _teacher("shape", {"discard:1w": [24, 24]})
    alternate = _teacher("r18_frozen", {"discard:1w": [24, 24]})
    alternate = deepcopy(alternate)
    alternate["rows"][0]["root_id"] = "different-root"
    with pytest.raises(ValueError, match="同根玩家观察"):
        compare(shape, alternate)
