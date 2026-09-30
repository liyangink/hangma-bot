"""动作后态终局模型的训练与已开结果诊断可复算。"""

import json
import hashlib
from pathlib import Path

import pytest

from scripts.vip_p3_competing_value_probe import _load
from scripts.vip_p3_poststate_development_eval import evaluate
from scripts.vip_p3_poststate_value_probe import fit, probabilities


_BASE = Path("review/vip-route-2026-09-30/evidence")
_OUT = _BASE / "p3-poststate-value-20260930"
_OLD = _BASE / "p3-competing-terminal-20260930"
_TRAIN = (
    _BASE / "p3-all-action-teacher-20260930/report.json.gz",
    _BASE / "p3-hu-wait-teacher-20260930/dev-shape-teacher.json.gz",
)


def test_model_recomputes_without_teacher_future_in_features():
    """相同冻结训练账得到同系数、类别净分和公开后态特征合同。"""

    model = fit(_TRAIN)
    saved = json.loads((_OUT / "train-model.json").read_text(encoding="utf-8"))
    assert model == saved
    assert model["root_count"] == 104
    assert model["non_hu_action_count"] == 910
    assert model["immediate_hu_exact"] is True
    x = (1.0,) + (0.0,) * (len(model["feature_names"]) - 1)
    p = probabilities(x, tuple(tuple(row) for row in model["coefficients"]))
    assert all(value >= 0 for value in p)
    assert sum(p) == pytest.approx(1.0)


def test_opened_result_diagnostic_recomputes_and_rejects_source_drift():
    """已开批次仅检开发差；教师或特征摘要漂移必须拒绝。"""

    scan = _load(_OLD / "new-root-scan.json.gz")
    model = _load(_OUT / "train-model.json")
    old = _load(_OLD / "predictions-before-labels.json")
    shape = _load(_OLD / "new-shape-teacher.json.gz")
    r18 = _load(_OLD / "new-r18_frozen-teacher.json.gz")
    report = evaluate(scan, model, old, shape, r18)
    saved = _load(_OUT / "development-evaluation.json")
    assert report == saved
    assert report["root_count"] == 128
    assert report["deferred_current_hu"] == 0
    assert report["draw"]["shape"]["poststate_mean_net"] < 0
    assert report["draw"]["r18_frozen"]["poststate_mean_net"] < 0
    broken = {**model, "feature_sources": [{**model["feature_sources"][0],
                                             "sha256": "0" * 64},
                                            model["feature_sources"][1]]}
    with pytest.raises(ValueError, match="特征来源摘要漂移"):
        evaluate(scan, broken, old, shape, r18)


def test_development_manifest_binds_sources_and_outputs():
    """已开结果的训练来源、对照教师、脚本和结果文件都有稳定摘要。"""

    manifest = json.loads((_OUT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["scope"] == "opened_outcome_development_failure_not_independent_confirmation"
    assert len(manifest["files"]) == 12
    for item in manifest["files"]:
        assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
