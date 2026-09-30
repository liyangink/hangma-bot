"""新根结果只能评价事前首选，不能用标签重选动作。"""

import copy
import json
from pathlib import Path

import pytest

from scripts.vip_p3_competing_holdout_eval import _load, evaluate
from scripts.vip_p3_competing_seed_interval import summarize


_ROOT = (Path(__file__).resolve().parents[2] /
         "review/vip-route-2026-09-30/evidence/"
         "p3-competing-terminal-20260930")


@pytest.fixture(scope="module")
def evidence():
    return (
        _load(_ROOT / "new-root-scan.json.gz"),
        _load(_ROOT / "predictions-before-labels.json"),
        _load(_ROOT / "new-shape-teacher.json.gz"),
        _load(_ROOT / "new-r18_frozen-teacher.json.gz"),
    )


def test_prelocked_action_once_evaluation_reproduces_at_root_unit(evidence):
    result = evaluate(*evidence)
    assert result["all_roots"]["root_count"] == 128
    assert result["changed_roots"]["root_count"] == 99
    assert result["all_roots"]["shape"]["mean_paired_net_delta_per_root"] == 1.21875
    assert result["all_roots"]["r18_frozen"]["mean_paired_net_delta_per_root"] == 0.75
    assert result["shape_terminal_category_calibration_all_non_hu_arms"]["root_count"] == 128
    assert result["teacher_sensitivity"]["action_worlds_per_reference"] == 4320


def test_post_label_chosen_action_substitution_is_rejected(evidence):
    scan, frozen, shape, r18 = evidence
    altered = copy.deepcopy(frozen)
    row = next(item for item in altered["rows"]
               if item["chosen_action_key"] != item["shape_first_action_key"])
    row["chosen_action_key"] = row["shape_first_action_key"]
    with pytest.raises(ValueError, match="事前首选不符合冻结评分排序"):
        evaluate(scan, altered, shape, r18)


def test_seed_cluster_interval_reproduces_without_treating_roots_as_independent():
    evaluation = _load(_ROOT / "prelocked-evaluation.json")
    frozen = json.loads((_ROOT / "seed-cluster-interval.json").read_text(
        encoding="utf-8"))
    assert summarize(evaluation) == frozen
    assert frozen["seed_count"] == 30
