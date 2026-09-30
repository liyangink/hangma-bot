"""行动前分支摘要只能用于区分同事件后态，不能读取未来当特征。"""

import copy
import json
from pathlib import Path

import pytest

from scripts.vip_p3_conditional_branch_audit import audit
from scripts.vip_p3_multi_opportunity_analysis import _load


_ROOT = Path("review/vip-route-2026-09-30/evidence/p3-multi-opportunity-20260930")
_SELECTION = _ROOT / "selection-4101-4400.json.gz"
_FREEZE = _ROOT / "pre-outcome-freeze.json"
_TEACHER = _ROOT / "paired-outcomes.json.gz"


def test_same_first_event_differences_are_distinguished_by_pre_action_branches():
    """13 个改选根按相关世界计，不能把条件分支差冒充收益预测。"""

    result = audit(_load(_SELECTION), _load(_FREEZE), _load(_TEACHER), _FREEZE)
    assert result == json.loads((_ROOT / "conditional-branch-audit.json").read_text())
    assert result["changed_root_count"] == 13
    assert result["totals"]["shape"]["same_normal_draw_different_terminal_net"] == 35
    assert result["totals"]["shape"]["different_projected_branch_signature"] == 35
    assert result["totals"]["r18_frozen"]["same_normal_draw_different_terminal_net"] == 61
    assert result["totals"]["r18_frozen"]["different_projected_branch_signature"] == 61


def test_actual_next_draw_without_pre_action_rule_edge_is_rejected():
    """未来教师牌码若超出规则前沿，不能静默当成零价值。"""

    frozen = _load(_FREEZE)
    report = copy.deepcopy(_load(_TEACHER))
    by_key = {(item["root_id"], item["sample"], item["first_action_key"],
               item["continuation_reference"]): item for item in report["rows"]}
    pair = None
    for root in frozen["roots"]:
        model, baseline = root["roles"]["anchored"], root["roles"]["r18"]
        if model is None or model == baseline:
            continue
        for sample in range(root["worlds_per_root"]):
            left = by_key[(root["root_id"], sample, model, "shape")]
            right = by_key[(root["root_id"], sample, baseline, "shape")]
            if (left["first_event_key"] == right["first_event_key"]
                    and left["first_event_kind"] == "self_normal_draw"
                    and left["terminal"]["score_delta"][0] !=
                    right["terminal"]["score_delta"][0]):
                pair = left, right
                break
        if pair:
            break
    assert pair is not None
    for row in pair:
        row["first_event_key"] = "self_normal_draw:not-a-tile"
    with pytest.raises(ValueError, match="缺行动前条件边"):
        audit(_load(_SELECTION), frozen, report, _FREEZE)
