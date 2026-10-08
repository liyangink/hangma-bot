"""T199门工具负例：只用临时文件／本地子进程，无官方连接和玩家。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_gate as gate


def room():
    """人工终态输入不是官方验收收据；分数按座位0—3，资源计数为当前值。"""
    return {"identity": {"package": "fixture"},
            **{key: 0 for key in gate.HARD_COUNTS},
            "serialization_failures": 0, "write_failures": 0,
            "terminal": {"actual_exit_code": 0, "terminal_reason": "tournament_finished",
                         "termination_signal_sent": False},
            "raw_audit_present": True, "owner_released_by_player": True,
            "compute": {"closed": True, **{key: 0 for key in gate.RESOURCE_COUNTS}},
            "tables": [{"game_id": "table_%02d" % i, "source": "fixture/audit.jsonl",
                        "final_scores_seat_order_0_3": [-3, 1, 1, 1]} for i in range(10)],
            "warnings": {"recovered_429": 1, "active_pass": 7, "missing_score_diagnosed": 2}}


class GateTests(unittest.TestCase):
    """验证边界拒绝、根隔离和持久启动意图；不镜像评分实现。"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="t199-release-gate-")
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "release"
        self.root.mkdir()
        modes = {}
        files = {}
        for mode in gate.MODES:
            relative = "packages/" + mode + ".json"
            path = self.root / relative
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps({"allowed_modes": [mode]}))
            files[relative] = gate.pin(path)
            modes[mode] = relative
        self.spec = {"release_root": str(self.root), "active_root": str(self.base / "active"),
                     "files": files, "mode_manifests": modes,
                     "shared": {key: str(self.base / "shared" / key) for key in
                                ("owner_lock", "postprocess_lock", "worker_lock", "state_dir")}}

    def tearDown(self):
        self.temporary.cleanup()

    def test_byte_drift_rejected(self):
        self.assertTrue(gate.preflight(self.spec)["complete"])
        (self.root / self.spec["mode_manifests"]["auto_match"]).write_text("{}")
        with self.assertRaises(gate.GateError):
            gate.preflight(self.spec)

    def test_duplicate_scope_rejected(self):
        path = self.root / self.spec["mode_manifests"]["test_room"]
        path.write_text(json.dumps({"allowed_modes": ["auto_match"]}))
        self.spec["files"][self.spec["mode_manifests"]["test_room"]] = gate.pin(path)
        with self.assertRaises(gate.GateError):
            gate.preflight(self.spec)

    def test_root_local_locks_rejected(self):
        self.spec["shared"]["owner_lock"] = str(self.root / "owner.lock")
        with self.assertRaises(gate.GateError):
            gate.preflight(self.spec)

    def test_escape_symlink_rejected(self):
        outside = self.base / "outside.py"
        outside.write_text("pass\n")
        (self.root / "source.py").symlink_to(outside)
        with self.assertRaises(gate.GateError):
            gate.relative_file(self.root, "source.py")

    def test_active_root_rejected(self):
        self.spec["release_root"] = self.spec["active_root"]
        with self.assertRaises(gate.GateError):
            gate.inspect_layout(self.spec)

    def test_recovered_warning_and_negative_score_do_not_trigger_rollback(self):
        result = gate.room_gate(room(), {"package": "fixture"})
        self.assertTrue(result["engineering_passed"])
        self.assertFalse(result["rollback_required"])
        self.assertTrue(result["does_not_wait_for_postprocess"])

    def test_real_missed_action_blocks_candidate(self):
        evidence = room()
        evidence["real_new_missed_actions"] = 1
        result = gate.room_gate(evidence, evidence["identity"])
        self.assertTrue(result["block_next_candidate_room"])
        self.assertTrue(result["rollback_required"])

    def test_unknown_not_false_or_zero(self):
        evidence = room()
        del evidence["illegal_submissions"]
        result = gate.room_gate(evidence, evidence["identity"])
        self.assertFalse(result["engineering_passed"])
        self.assertIn("illegal_submissions", result["unknown"])

    def test_false_exit_and_nonfinished_terminal_rejected(self):
        for code, reason in ((False, "tournament_finished"), (0, "tournament_void")):
            evidence = room()
            evidence["terminal"]["actual_exit_code"] = code
            evidence["terminal"]["terminal_reason"] = reason
            self.assertFalse(gate.room_gate(evidence, evidence["identity"])["engineering_passed"])

    def test_resource_and_identity_drift_rejected(self):
        evidence = room()
        evidence["compute"]["owned"] = 1
        self.assertFalse(gate.room_gate(evidence, evidence["identity"])["continuation_allowed"])
        evidence = room()
        self.assertTrue(gate.room_gate(evidence, {"package": "wrong"})["rollback_required"])

    def _boundary_ledger(self):
        ledger = gate.ReleaseLedger(self.base / "ledger")
        receipt = gate.preflight(self.spec)
        ledger.append("prechecked", receipt)
        ledger.append("pause_requested", {"new_runtime_receipt_only": True})
        ledger.append("boundary_verified", {"engineering_passed": True,
            "other_players_live": False, "owner_lock_acquired": True})
        return ledger, receipt

    def test_boundary_requires_real_lock_and_no_players(self):
        ledger = gate.ReleaseLedger(self.base / "ledger")
        ledger.append("prechecked", gate.preflight(self.spec))
        ledger.append("pause_requested", {})
        with self.assertRaises(gate.GateError):
            ledger.append("boundary_verified", {"engineering_passed": True,
                "other_players_live": True, "owner_lock_acquired": True})

    def test_activation_failure_does_not_write_dispatch_intent(self):
        ledger, receipt = self._boundary_ledger()
        with self.assertRaises(gate.GateError):
            ledger.append("dispatch_intent", {"activation_prechecked": False,
                                               "spec_sha256": receipt["spec_sha256"]})
        self.assertEqual(ledger.status()["phase"], "boundary_verified")

    def test_activation_identity_must_equal_prechecked_identity(self):
        ledger, _ = self._boundary_ledger()
        with self.assertRaises(gate.GateError):
            ledger.append("dispatch_intent", {"activation_prechecked": True, "spec_sha256": "changed"})

    def test_crash_after_intent_refuses_duplicate_launch(self):
        ledger, receipt = self._boundary_ledger()
        self.assertTrue(ledger.status()["new_dispatch_intent_allowed"])
        payload = {"activation_prechecked": True, "spec_sha256": receipt["spec_sha256"]}
        ledger.append("dispatch_intent", payload)
        restored = gate.ReleaseLedger(ledger.directory)
        self.assertTrue(restored.status()["dispatch_ambiguity"])
        self.assertFalse(restored.status()["automatic_rematch_allowed"])
        self.assertFalse(restored.status()["new_dispatch_intent_allowed"])
        with self.assertRaises(gate.GateError):
            restored.append("dispatch_intent", payload)

    def test_failed_new_owner_not_claimed_started(self):
        ledger, receipt = self._boundary_ledger()
        ledger.append("dispatch_intent", {"activation_prechecked": True,
            "spec_sha256": receipt["spec_sha256"]})
        with self.assertRaises(gate.GateError):
            ledger.append("started", {"controller_pid": 100, "expected_command_live": False,
                                      "owner_fd_inherited": True})
        self.assertEqual(ledger.status()["phase"], "dispatch_intent")

    def test_wrong_rule_parent_cannot_be_rollback(self):
        ledger, _ = self._boundary_ledger()
        ledger.append("fault", {"block_next_candidate_room": True})
        with self.assertRaises(gate.GateError):
            ledger.append("rollback_requested", {"corrected_rules_parent_verified": False})
        self.assertTrue(ledger.append("rollback_requested", {
            "corrected_rules_parent_verified": True})["block_next_candidate_room"])

    def test_warning_does_not_turn_into_fault(self):
        ledger, _ = self._boundary_ledger()
        with self.assertRaises(gate.GateError):
            ledger.append("fault", {"block_next_candidate_room": False, "recovered_429": 1})

    def test_fd_inode_mismatch_rejected_and_local_spawn_inherits_correct_fd(self):
        lock = self.base / "owner.lock"
        other = self.base / "other.lock"
        with lock.open("a+") as stream, other.open("a+") as different:
            gate.verify_owner_fd(stream.fileno(), lock)
            with self.assertRaises(gate.GateError):
                gate.verify_owner_fd(different.fileno(), lock)
            script = "import os,sys; f=os.fstat(int(sys.argv[1])); p=os.stat(sys.argv[2]); assert (f.st_dev,f.st_ino)==(p.st_dev,p.st_ino)"
            child = subprocess.run([sys.executable, "-I", "-B", "-c", script,
                str(stream.fileno()), str(lock)], pass_fds=(stream.fileno(),), capture_output=True)
            self.assertEqual(child.returncode, 0, child.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
