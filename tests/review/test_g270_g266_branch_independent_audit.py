"""G270 只读审计的故障注入测试：只使用已冻结的 r2 冒烟分支。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/review'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (_project_file(_PROJECT_ROOT, ROOT / "review/freematch-deep-dive-20260925/"
          "g270_g266_branch_independent_audit.py"))
SMOKE = (_project_file(_PROJECT_ROOT, ROOT / "review/freematch-deep-dive-20260925/evidence/"
         "g266-plain-baotou-entry-smoke-r2-20260929"))
SPEC = importlib.util.spec_from_file_location("g270_g266_branch_independent_audit", SCRIPT)
assert SPEC and SPEC.loader
g270 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g270)


def smoke():
    """构造只引用 r2 冒烟证据的单根入选清单视图。"""
    branch = json.loads((_project_file(_PROJECT_ROOT, SMOKE / "branch-smoke.json")).read_text())
    identity = branch["identity"]
    stage = json.loads((_project_file(_PROJECT_ROOT, SMOKE / "stages/p2026122966-H-r0001-s3.json")).read_text())
    selected = {"panel_seed": identity["panel_seed"], "mix": identity["mix"],
                "root_index": identity["root_index"],
                "root_identity": identity["root_identity"], "half": identity["half"],
                "priority_layer": identity["layer"], "priority_hit": identity["hit"]}
    samples = json.loads((_project_file(_PROJECT_ROOT, SMOKE / "manifest.json")).read_text())["samples"]
    return branch, stage, selected, samples


def verify(branch, stage, selected, samples):
    """单根验证不读取正在运行的开发分支。"""
    return g270.verify_branch_payload(
        branch, stage, selected, samples, branch["manifest_sha256"],
        branch["selection_sha256"])


def test_r2_smoke_nine_worlds_and_six_class_accounting():
    branch, stage, selected, samples = smoke()
    row = verify(branch, stage, selected, samples)
    assert row["identity"]["root_identity"] == "2026122966|H|1"
    assert row["mean_table_delta"] == pytest.approx(20 / 9)
    assert row["first_enter_unknown_arm_worlds"] == 0
    assert sum(row["focal_income_delta"].values()) == pytest.approx(row["mean_table_delta"])


def test_reject_missing_or_duplicate_paired_world():
    branch, stage, selected, samples = smoke()
    branch["paired_worlds"][1]["sample_key"] = "historical"
    with pytest.raises(ValueError, match="九世界"):
        verify(branch, stage, selected, samples)


def test_reject_forced_action_not_exactly_once():
    branch, stage, selected, samples = smoke()
    branch["paired_worlds"][0]["alternate"]["forced_once"] = 0
    with pytest.raises(ValueError, match="强制动作"):
        verify(branch, stage, selected, samples)


def test_reject_historical_parent_settlement_drift():
    branch, stage, selected, samples = smoke()
    stage["table"]["hands"][0]["details"] = ["七对"]
    with pytest.raises(ValueError, match="历史前缀|原历史世界父代"):
        verify(branch, stage, selected, samples)


def test_reject_six_class_misaccounting():
    branch, stage, selected, samples = smoke()
    branch["paired_worlds"][0]["alternate"]["income"]["by_class"][
        "plain_baotou"]["focal_net_score"] += 1
    with pytest.raises(ValueError, match="分账不符"):
        verify(branch, stage, selected, samples)


def test_unknown_is_missing_not_zero_opportunity():
    branch, stage, selected, samples = smoke()
    pair = branch["paired_worlds"][1]
    arm = pair["parent"]
    assert arm["timeline"]["events"][1]["status"] == "no"
    arm["timeline"]["events"][1]["status"] = "unknown"
    with pytest.raises(ValueError, match="unknown 被计作无机会"):
        verify(branch, stage, selected, samples)
    arm["timeline"]["unknown_after_root"] = True
    row = verify(branch, stage, selected, samples)
    assert row["first_enter_unknown_arm_worlds"] == 1
    assert row["first_enter_delta"] is None


def test_incomplete_batch_refuses_before_opening_branch_json(tmp_path):
    """即使已有分支文件损坏，也先按文件名拒绝，绝不看中途收益。"""
    _branch, _stage, selected, _samples = smoke()
    selected["root_index"] = 3
    other = deepcopy(selected)
    other["root_index"] = 4
    (tmp_path / "branches").mkdir()
    g270.branch_file(tmp_path, selected).write_text("{ this is not JSON")
    with pytest.raises(ValueError, match="未完整收齐"):
        g270.require_complete_before_outcomes(tmp_path, [selected, other])
