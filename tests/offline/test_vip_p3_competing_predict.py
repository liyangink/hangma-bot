"""竞争终局探针须在新根结局打开前独立复现合法动作和概率质量。"""

import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts.vip_p3_competing_predict import predict


_ROOT = (Path(__file__).resolve().parents[2] /
         "review/vip-route-2026-09-30/evidence/"
         "p3-competing-terminal-20260930")


def _inputs():
    with gzip.open(_ROOT / "new-root-scan.json.gz", "rt", encoding="utf-8") as stream:
        scan = json.load(stream)
    return scan, json.loads((_ROOT / "train-model.json").read_text(encoding="utf-8"))


def test_pre_outcome_competing_predictions_reproduce_and_conserve_probability():
    scan, model = _inputs()
    frozen = json.loads((_ROOT / "predictions-before-labels.json").read_text(
        encoding="utf-8"))
    assert predict(scan, model) == frozen
    assert frozen["root_count"] == 128
    assert frozen["changed_vs_shape_roots"] == 99
    for row in frozen["rows"]:
        assert {item["action_key"] for item in row["scores"]}
        for item in row["scores"]:
            mass = item["terminal_category_probability"]
            if item["action_key"] == "hu":
                assert mass is None
                assert item["exact_current_hu_net"] is not None
            else:
                assert len(mass) == 4
                assert all(0 <= value <= 1 for value in mass)
                assert sum(mass) == pytest.approx(1.0, abs=1e-12)


def test_training_source_drift_is_rejected():
    scan, model = _inputs()
    broken = copy.deepcopy(model)
    broken["training_sources"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="训练教师来源摘要漂移"):
        predict(scan, broken)
