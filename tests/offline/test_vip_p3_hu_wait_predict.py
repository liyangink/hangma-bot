"""留出动作必须在读取教师结局前由冻结观察与系数复现。"""

import json
from pathlib import Path

import pytest

from scripts.vip_p3_hu_wait_predict import predict


_ROOT = (Path(__file__).resolve().parents[2] /
         "review/vip-route-2026-09-30/evidence/"
         "p3-hu-wait-teacher-20260930")


def test_frozen_holdout_predictions_reproduce_without_teacher_results():
    scan = json.loads((_ROOT / "holdout-scan.json").read_text(encoding="utf-8"))
    model = json.loads((_ROOT / "dev-route-model-freeze.json").read_text(
        encoding="utf-8"))
    frozen = json.loads((_ROOT / "holdout-predictions-before-labels.json").read_text(
        encoding="utf-8"))
    assert predict(scan, model) == frozen
    assert frozen["root_count"] == 24
    assert frozen["wait_chosen_roots"] == 8
    assert all("terminal" not in row and "future_wall" not in row
               for row in frozen["rows"])


def test_feature_source_drift_is_rejected():
    scan = json.loads((_ROOT / "holdout-scan.json").read_text(encoding="utf-8"))
    model = json.loads((_ROOT / "dev-route-model-freeze.json").read_text(
        encoding="utf-8"))
    model["feature_source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="特征源码摘要漂移"):
        predict(scan, model)
