"""留出账只能结算事前锁定动作，且按观察根而非动作世界计数。"""

import copy
from pathlib import Path

import pytest

from scripts.vip_p3_hu_wait_audit import _load
from scripts.vip_p3_hu_wait_holdout_eval import evaluate


_ROOT = (Path(__file__).resolve().parents[2] /
         "review/vip-route-2026-09-30/evidence/"
         "p3-hu-wait-teacher-20260930")


@pytest.fixture(scope="module")
def _evidence():
    return (
        _load(_ROOT / "holdout-scan.json"),
        _load(_ROOT / "holdout-predictions-before-labels.json"),
        _load(_ROOT / "holdout-shape-teacher.json.gz"),
        _load(_ROOT / "holdout-r18_frozen-teacher.json.gz"),
    )


def test_prelocked_holdout_gain_reproduces_at_root_unit(_evidence):
    report = evaluate(*_evidence)
    assert report["all_selected_roots"]["root_count"] == 24
    assert report["prelocked_wait_roots"]["root_count"] == 8
    assert report["all_selected_roots"]["shape"]["mean_paired_net_minus_immediate_hu_per_root"] == 4.0
    assert report["all_selected_roots"]["r18_frozen"]["mean_paired_net_minus_immediate_hu_per_root"] == 8.25
    assert report["wait_cross_reference_signs"] == {
        "negative/negative": 1,
        "negative/zero": 1,
        "positive/positive": 6,
    }


def test_post_label_action_substitution_is_rejected(_evidence):
    scan, frozen, shape, r18 = _evidence
    changed = copy.deepcopy(frozen)
    selected = next(row for row in changed["rows"]
                    if row["chosen_action_key"] != "hu")
    selected["chosen_action_key"] = "hu"
    with pytest.raises(ValueError, match="锁定预测与冻结同分排序规则不一致"):
        evaluate(scan, changed, shape, r18)
