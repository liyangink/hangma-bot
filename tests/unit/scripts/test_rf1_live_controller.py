"""修复自由赛准入的真实包绑定负控；不读凭据、不启动HTTP或玩家。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/unit/scripts'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hangma_bot import bootstrap
from hangma_bot.policy import vip_g37_rf1_release as release

ROOT = Path(__file__).resolve().parents[3]
ENTRY = 'tools/offline/free_match/rf1_controller.py'
loader = importlib.util.spec_from_file_location("rf1_live_controller_test", _project_file(_PROJECT_ROOT, ROOT / ENTRY))
runtime = importlib.util.module_from_spec(loader)
loader.loader.exec_module(runtime)


def pin(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.fixture
def controller(tmp_path):
    """核主线真实批准原件，只有控制状态/假凭据位置在临时目录。"""
    modes = {mode: relative for _, (mode, _, relative) in release.PACKAGE_SCOPES.items()}
    package = bootstrap._load_vip_manifest("vip_g37_rf1_free_v1")
    qualification = {"release_kind": "scoring_defect_repair", "receipts": {}}
    for key, name in {**release.REQUIRED_RECEIPTS, "corrected_fallback_passed": "ENGINEERING-CLOSED.json"}.items():
        path = _project_file(_PROJECT_ROOT, ROOT / release.EVIDENCE_DIRECTORY / name)
        qualification[key] = True
        qualification["receipts"][key] = {"path": str(path), "pin": pin(path)}
    spec = {"release_root": str(ROOT), "active_root": str(tmp_path), "preparation_only": False,
            "files": {p: pin(_project_file(_PROJECT_ROOT, ROOT / p)) for p in [ENTRY, *modes.values()]}, "mode_manifests": modes,
            "qualification": qualification, "credential_path": str(tmp_path / "never-read.token"),
            "identity": {"free_strategy": package["strategy"], "package_ids": {"free": package["release_package_id"]},
                         "rules_source_hash": bootstrap.compute_rules_hash(ROOT),
                         "hand_math": bootstrap.hand_math_runtime_metadata()},
            "shared": {key: str(tmp_path / key) for key in ["owner_lock", "postprocess_lock", "worker_lock", "state_dir"]}}
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return runtime.Controller(path, tools=SimpleNamespace(),
                              process_observer=lambda *_: {"expected_command_live": False})


def test_real_repair_receipts_admit_without_strength_or_P0_impersonation(controller):
    result = controller.check_admission()
    assert result["repair_publication_verified"] is True
    assert result["strength_admission"] is False


def test_distinct_testroom_tokens_do_not_block_same_global_free_owner_check():
    processes = """101 /usr/bin/python3 /root/scripts/run_auto_match.py --config free.json
102 /usr/bin/python3 /root/scripts/run_test_room.py --config test.json
103 /usr/bin/python3 /root/scripts/run_participant.py --config seat.json
104 /bin/bash -c cat scripts/run_auto_match.py
105 /usr/bin/python3 scripts/run_auto_match.py --config duplicate.json
"""
    assert runtime.free_players_from_ps(processes) == [101, 105]


def test_unknown_process_inventory_refuses_match(monkeypatch):
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=""))
    with pytest.raises(runtime.gate.GateError, match="禁止重复匹配"):
        runtime.other_free_players()


@pytest.mark.parametrize("key", [*release.REQUIRED_RECEIPTS, "corrected_fallback_passed"])
def test_missing_one_repair_gate_refuses_before_matching(controller, key):
    controller.spec["qualification"][key] = False
    with pytest.raises(runtime.gate.GateError, match="未闭"):
        controller.check_admission()


@pytest.mark.parametrize("fault", ["P0_kind", "draft", "old_package", "receipt_drift"])
def test_wrong_scope_or_original_receipt_cannot_start(controller, fault):
    if fault == "P0_kind":
        controller.spec["qualification"]["release_kind"] = "P0"
    elif fault == "draft":
        controller.spec["preparation_only"] = True
    elif fault == "old_package":
        controller.spec["identity"]["package_ids"]["free"] = "0" * 64
    else:
        controller.spec["qualification"]["receipts"]["repair_passed"]["pin"] = {"bytes": 1, "sha256": "0" * 64}
    with pytest.raises((runtime.gate.GateError, RuntimeError, ValueError)):
        controller.check_admission()
