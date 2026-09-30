"""当前胡的真实分数与两名续打者的继续价值须逐根对齐。"""

from copy import deepcopy

import pytest

from scripts.vip_p3_hu_wait_audit import audit


def _teacher(reference: str, wait_points: tuple[int, int]) -> dict:
    """同观察同世界的 Hu 与一条继续动作。"""

    def outcome(sample: int, value: int, *, hu: bool = False) -> dict:
        return {
            "sample": sample,
            "terminal": {
                "winner_seat": 0 if hu or value > 0 else 1,
                "is_draw": False, "fan": 1,
                "score_delta": [value, -value, 0, 0],
            },
        }

    return {
        "scope": "P3_offline_teacher_labels_only_not_candidate_policy_value",
        "reference": "shape", "continuation_reference": reference,
        "selection_tag": "first_low_fan_hu",
        "start_seed": 1, "requested_seeds": 1, "worlds_per_root": 2,
        "rows": [{
            "seed": 1, "root_id": "root", "observation": {"seat": 0},
            "sample_count": 2,
            "legal_action_keys": ["hu", "discard:1w"],
            "outcomes_by_action": {
                "hu": [outcome(0, 10, hu=True), outcome(1, 10, hu=True)],
                "discard:1w": [outcome(sample, value)
                                for sample, value in enumerate(wait_points)],
            },
        }],
    }


def _scan() -> dict:
    return {
        "scope": "result_blind_opportunity_root_selection_not_outcome_or_probability",
        "selection_method": "first_low_fan_hu_under_shape_per_seed",
        "start_seed": 1, "requested_seeds": 1,
        "counts": {"selected_first_low_fan_hu": 1},
        "selected_roots": [{
            "seed": 1, "observation_sha256": "root", "tags": ["first_low_fan_hu"],
            "current_hu_fan": 1, "current_hu_net": 10,
            "white_count": 2, "wall_remaining": 40,
        }],
    }


def test_continue_direction_can_reverse_under_same_hu_settlement():
    result = audit(_scan(), _teacher("shape", (20, -8)),
                   _teacher("r18_frozen", (20, 20)))
    assert result["root_count"] == 1
    assert result["all_continue_action_signs"]["opposite"] == 1
    assert result["roots_with_any_positive_continue"] == {
        "shape": 0, "r18_frozen": 1,
    }


def test_teacher_cannot_change_exact_current_hu_or_drop_world():
    first = _teacher("shape", (20, -8))
    alternate = _teacher("r18_frozen", (20, 20))
    broken = deepcopy(alternate)
    broken["rows"][0]["outcomes_by_action"]["hu"][0]["terminal"][
        "score_delta"] = [12, -12, 0, 0]
    with pytest.raises(ValueError, match="当前 Hu 教师结局"):
        audit(_scan(), first, broken)
    missing = deepcopy(alternate)
    missing["rows"][0]["outcomes_by_action"]["discard:1w"].pop()
    with pytest.raises(ValueError, match="隐藏世界编号"):
        audit(_scan(), first, missing)
