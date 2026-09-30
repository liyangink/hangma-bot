"""事件教师必须复现结果盲根与守恒的首次互斥事件。"""

import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts.vip_p3_event_teacher import teach


_SELECTION = Path(
    "review/vip-route-2026-09-30/evidence/p3-event-mass-20260930/"
    "pre-outcome-selection.json.gz"
)


def _one_root(split: str, *, phase: str | None = None) -> dict:
    result = copy.deepcopy(json.loads(gzip.decompress(_SELECTION.read_bytes())))
    root = next(row for row in result["selected_roots"] if row["split"] == split
                and (phase is None or row["phase"].startswith(phase)))
    result["selected_roots"] = [root]
    result["selected_root_count"] = 1
    result["selected_split_counts"] = {split: 1}
    return result


def test_one_actionable_response_root_preserves_event_mass():
    """吃与过都与同一观察、同一隐藏世界配对；每参考者各一事件。"""

    report = teach(_one_root("fit", phase="response_"),
                   selection_sha256="0" * 64, split="fit")
    assert report["root_count"] == 1
    assert report["worlds_per_root"] == 4
    assert report["action_worlds_per_reference"] == 8
    assert sum(report["event_counts_by_reference"]["shape"].values()) == 8
    assert report["event_counts_by_reference"]["shape"]["self_claim_followup"] == 4
    row = report["rows"][0]
    assert len(row["legal_action_keys"]) == 2
    assert row["legal_action_keys"][1] == "pass"
    for action in row["legal_action_keys"]:
        for reference in report["continuation_references"]:
            samples = row["outcomes_by_action_and_reference"][action][reference]
            assert [item["sample"] for item in samples] == list(range(4))
            assert all(sum(item["terminal"]["score_delta"]) == 0 for item in samples)


def test_confirmation_outcome_cannot_open_without_frozen_all_action_predictions():
    """确认池在模型与全部合法动作分数冻结前拒绝生成教师结局。"""

    selection = _one_root("confirmation")
    with pytest.raises(ValueError, match="缺事前冻结"):
        teach(selection, selection_sha256="0" * 64, split="confirmation")
    root = selection["selected_roots"][0]
    prediction = {"scope": "vip_p3_event_confirmation_predictions_locked",
                  "selection_sha256": "0" * 64,
                  "roots": [{"root_id": root["root_id"],
                             "chosen_action_key": root["legal_action_keys"][0],
                             "scores_by_action": {root["legal_action_keys"][0]: 1.0}}]}
    with pytest.raises(ValueError, match="全部合法动作分数"):
        teach(selection, selection_sha256="0" * 64, split="confirmation",
              predictions=prediction)
