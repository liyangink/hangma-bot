"""事件抽样必须先按牌山种子分池，并拒绝夹带未来结局。"""

import copy
import hashlib

import pytest

from scripts.vip_p3_event_root_frame import scan
from scripts.vip_p3_event_root_select import select


def test_result_blind_selection_preserves_seed_split_and_probability():
    """同一种子窗口不得跨拟合／确认池；入框概率处于有效范围。"""

    frame = scan(start_seed=5001, seeds=3)
    source = hashlib.sha256(repr(frame).encode()).hexdigest()
    result = select(frame, source)
    assert result == select(frame, source)
    assert result["population_root_count"] == 12
    assert result["selected_root_count"] == 3
    assert {row["seed"] for row in result["selected_roots"]} == {5002, 5003}
    by_seed = {}
    for row in result["selected_roots"]:
        by_seed.setdefault(row["seed"], set()).add(row["split"])
        assert 0 < row["inclusion_probability"] <= 1
        assert row["matched_selection_tags"]
    assert all(len(splits) == 1 for splits in by_seed.values())


def test_future_result_field_in_root_is_rejected():
    """即使上游抽样框被误写入教师字段，也不能继续挑根。"""

    frame = copy.deepcopy(scan(start_seed=5001, seeds=1))
    frame["selected_roots"][0]["terminal"] = {"score_delta": [0, 0, 0, 0]}
    with pytest.raises(ValueError, match="非行动前字段"):
        select(frame, "0" * 64)
