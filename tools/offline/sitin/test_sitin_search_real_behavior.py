"""真实面板接线回归：授权到冻结身份、完整计划去重、漂移拒绝和旧面板兼容。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sitin_search as search
import sitin_real_behavior as real

ROOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
PANEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/real-behavior-panel-v1/panel.json')
PILOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19/pilot/run/iterations')


def declaration(path=PANEL):
    return {"path": str(path.resolve()), "panel_digest": real.load_panel(path)[0]}


def authorization(panel):
    return {"schema": "sitin-authorization/1", "authorization_id": "test-real-panel",
            "batch_label": "test-real-panel", "issued_by": "lead", "trusted": True,
            "issued_at_utc": "2026-09-19T00:00:00Z", "allowed_operations": [],
            "allowed_accounts": {"tokens_input": 2048, "tokens_output": 8192},
            "development_behavior_panel": declaration(panel)}


def test_real_panel_distinguishes_historical_collision_and_legacy_stays_scoped():
    sources = [(_project_file(_PROJECT_ROOT, PILOT / name / "generation/candidate.py")).read_text() for name in ("iter-02", "iter-03")]
    legacy = [search._av_behavior_signature(s) for s in sources]
    assert legacy[0]["digest"] == legacy[1]["digest"]
    enhanced = [search._av_behavior_signature(s, real_panel=declaration()) for s in sources]
    assert enhanced[0]["digest"] != enhanced[1]["digest"]
    assert enhanced[0]["digest"] != legacy[0]["digest"]
    assert len(enhanced[0]["windows"]) == len(legacy[0]["windows"]) + 19
    assert search._av_behavior_duplicates({"parent": {"behavior_signature": enhanced[0]}},
                                         digest=enhanced[1]["digest"], candidate_id="child") == []


def test_same_first_different_plan_and_incomparable_never_collapse():
    archive = search.av_archive()
    left = {"windows": [{"window_id": "same", "action_key": "pass", "missing": False,
                         "plan_signature": {"ordered_actions": ["pass", "peng:1w"]}}]}
    right = json.loads(json.dumps(left))
    right["windows"][0]["plan_signature"]["ordered_actions"].append("gang:1w")
    assert archive.behavior_signature_digest(left) != archive.behavior_signature_digest(right)
    left["comparable"] = False
    assert archive.behavior_signature_digest(left) is None


def test_start_freezes_panel_and_resume_rejects_tampering(tmp_path):
    shutil.copytree(PANEL.parent, tmp_path / "panel")
    panel = tmp_path / "panel/panel.json"
    auth = authorization(panel)
    run_root = tmp_path / "run"
    state = search.av_start_iteration(run_root, authorization=auth, generation_mode="mock")
    assert state["plan"]["development_behavior_panel"] == declaration(panel)
    assert state["identity"]["frozen_manifest"]["surfaces"]["development_behavior_panel"] == declaration(panel)
    assert search.av_verify_run_identity(state)[0]
    ledger_before = (run_root / "av-ledger.json").read_bytes()
    manifest = json.loads(panel.read_text())
    target = panel.parent / manifest["windows"][0]["file"]
    data = json.loads(target.read_text())
    data["request"]["decision_id"] = "tampered"
    target.write_text(json.dumps(data))
    ok, reason, _ = search.av_verify_run_identity(state)
    assert not ok and "摘要不符" in reason
    assert (run_root / "av-ledger.json").read_bytes() == ledger_before


def test_missing_or_changed_manifest_rejected_before_generation_reservation(tmp_path):
    auth = authorization(PANEL)
    auth["development_behavior_panel"]["panel_digest"] = "wrong"
    with pytest.raises(ValueError, match="漂移"):
        search.av_start_iteration(tmp_path / "run", authorization=auth)
    assert not (tmp_path / "run").exists()


def test_disabled_panel_remains_explicitly_absent_in_manifest():
    assert search.av_frozen_manifest(plan={})["surfaces"]["development_behavior_panel"] is None


def test_indeterminate_behavior_cannot_replace_existing_archive_entry():
    previous = {"candidate_id": "same", "behavior_signature": {"windows": [{"action_key": "pass"}]}}
    before = json.loads(json.dumps(previous))
    with pytest.raises(ValueError, match="不可判定"):
        search.av_archive().merge_archive_entry(previous, "same", [],
                                                behavior_signature={"comparable": False})
    assert previous == before


def test_indeterminate_behavior_step_stops_before_evaluation(tmp_path, monkeypatch):
    state = {"plan": {"development_behavior_panel": declaration()}, "candidate_source": "test",
             "identity": {"candidate_id": "c"}, "admission": {"coverage": "PASS"},
             "status": "ADMITTED", "step_history": []}
    monkeypatch.setattr(search, "_av_previous_archive", lambda *_: {})
    monkeypatch.setattr(search, "_av_behavior_signature", lambda *_, **__: {"comparable": False, "digest": None})
    result = search._step_behavior(state, tmp_path)
    assert result["terminal"] == "INPUT_GAP"
    assert state["stop_reason"] == "development_behavior_indeterminate"
    assert not (tmp_path / "archive").exists()


def test_supervisor_feedback_bound_to_identity_and_rendered(tmp_path):
    plan = {"operator": "i1", "predicate": "branch_open", "opponent": "H", "supervisor_feedback": "本批先检验同类牌效刻度"}
    packet = search._av_generation_packet({"plan": plan}, search.av_generate(), tmp_path)
    assert plan["supervisor_feedback"] in packet.text
    first = search.av_frozen_manifest(plan=plan)
    second = search.av_frozen_manifest(plan=dict(plan, supervisor_feedback="不同假设"))
    assert search.av_frozen_manifest_digest(first) != search.av_frozen_manifest_digest(second)
