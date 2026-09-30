"""机会层的行动前选根、冻结身份与同世界 R18 对照。"""

from copy import deepcopy

import pytest

from scripts.vip_p3_all_action_teacher import audit
from scripts.vip_p3_opportunity_compare import compare
from scripts.vip_p3_opportunity_root_scan import scan


def test_result_blind_high_fan_root_replays_and_compares_with_r18():
    """宽四番根确实存在，但该正例中 R18 已选同一弃牌。"""

    selection = scan(start_seed=1310, seeds=1)
    assert selection["counts"]["selected_high_fan_witness"] == 1
    root = selection["selected_roots"][0]
    assert root["tags"] == ["high_fan_witness"]
    assert root["own_draw_index"] == 6
    assert root["high_fan_capacity"] == 102
    teacher = audit(start_seed=1310, seeds=1, worlds_per_root=2,
                    selection_report=selection, selection_tag="high_fan_witness")
    assert teacher["root_count"] == 1
    assert teacher["selection_root_count"] == 1
    assert teacher["rows"][0]["root_id"] == root["observation_sha256"]
    compared = compare(selection, teacher)
    assert compared["same_action_roots"] == 1
    assert compared["rows"][0]["selected_action"] == "discard:7t"
    assert compared["rows"][0]["r18_top_action"] == "discard:7t"
    assert compared["rows"][0]["paired_delta"] == [0, 0]


def test_frozen_opportunity_root_identity_rejects_changed_observation():
    """身份摘要错位时不准把另一牌况的结果算到已冻结机会根。"""

    selection = scan(start_seed=1310, seeds=1)
    corrupt = deepcopy(selection)
    corrupt["selected_roots"][0]["observation_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="玩家观察与冻结扫描身份不一致"):
        audit(start_seed=1310, seeds=1, worlds_per_root=1,
              selection_report=corrupt, selection_tag="high_fan_witness")
