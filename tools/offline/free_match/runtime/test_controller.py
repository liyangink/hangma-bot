"""T199控制器人工会话验证：假launcher，真实可信终态验证与临时共享锁。"""
from __future__ import annotations

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

import fcntl
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as runtime
import release_gate as gate

ORIGIN = _PROJECT_ROOT
BASE_SPEC = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/runtime-workspace/BASELINE-RUNTIME-SPEC.json')


class FixtureController(runtime.Controller):
    """仅把离线发布资格换成人工夹具；真实watch从未执行此实现。"""

    def check_admission(self):
        return gate.preflight(self.spec)


class FakePlayer:
    """人工玩家wait时写假终态；没有terminate/kill接口，违规调用会立即失败。"""

    pid = 199001

    def __init__(self, callback):
        self.callback = callback

    def wait(self):
        self.callback()
        return 0


class RuntimeTests(unittest.TestCase):
    """验证单次派发、可信verify适配、停线及自然回退，不连接官方。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="t199-controller-")
        self.base = Path(self.temp.name).resolve()
        self.spec = gate.read_json(BASE_SPEC)
        self.spec["active_root"] = str(self.base)
        self.spec["shared"] = {"owner_lock": str(self.base / "owner.lock"),
            "postprocess_lock": str(self.base / "postprocess.lock"),
            "worker_lock": str(self.base / "worker.lock"), "state_dir": str(self.base / "state")}
        self.spec["credential_path"] = str(self.base / "never-read-credential")
        self.spec_path = self.base / "spec.json"
        self.spec_path.write_text(json.dumps(self.spec))
        self.calls = []
        self.pending_fault = False
        self.owner = (self.base / "owner.lock").open("a+")
        fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.value = FixtureController(self.spec_path, launcher=self.launch,
            process_observer=lambda *_: {"expected_command_live": True})
        self.value.STATE.mkdir()
        runtime.write_state(self.value.CONTROL, {"continue_after_cycle": True, "background_enabled": True})
        self.value.tools.h.other_players = lambda: []

    def tearDown(self):
        self.owner.close()
        self.temp.cleanup()

    def launch(self, command, **settings):
        self.calls.append((command, settings))
        if "run_auto_match.py" in command[2]:
            directory = Path(command[command.index("--config") + 1]).parent
            return FakePlayer(lambda: self.make_terminal(directory, settings["stdout"]))
        return FakePlayer(lambda: None)

    def make_terminal(self, directory, stdout):
        """记录结构与生产契约相同，但数据都是人工值，不能授官方通过。"""
        plan = gate.read_json(directory / "PLAN.json")
        session = Path(plan["free_session"])
        run = session / "audit/runs/fake-run"
        games = run / "participants/u_fixture/games"
        games.mkdir(parents=True)
        written = {}
        raw = run / "participants/u_fixture/raw"
        raw.mkdir()
        for i in range(10):
            gid = "a_fixture_r%02d" % i
            path = games / (gid + ".jsonl")
            record = {"kind": "game_finished", "context": {"game_id": gid},
                      "payload": {"final_scores": [-3, 1, 1, 1]}, "monotonic_ns": 2}
            path.write_text(json.dumps(record) + "\n")
            written[str(path.relative_to(run))] = 1
            raw_path = raw / (gid + ".jsonl")
            raw_record = {"kind": "raw_protocol_state", "context": {"game_id": gid}, "monotonic_ns": 1,
                "payload": {"source": "state_response", "http_status": 200, "seq_requested": 0,
                            "raw": json.dumps({"snapshot": {"seat": 0}, "events": []})}}
            raw_path.write_text(json.dumps(raw_record) + "\n")
            written[str(raw_path.relative_to(run))] = 1
        summary = {"run_id": "fake-run", "dropped_low_priority": 0, "missing_high_priority": 0,
            "serialization_failures": 0, "write_failures": 0, "audit_degraded": False,
            "raw_retention": {"emitted_attempts": 10, "dropped": 0}, "written_by_path": written}
        (run / "summary.json").write_text(json.dumps(summary))
        identity = self.spec["identity"]
        manifest = {"policy_version": identity["free_strategy"],
            "policy_release": {"release_package_id": identity["package_ids"]["free"], "hand_math": identity["hand_math"]},
            "hand_math": identity["hand_math"], "sse_effective": True, "discard_pacing_enabled": False,
            "max_games": 10, "rounds_per_game": 8, "base_score": 1, "you_cai_bi_kao": False}
        (run / "manifest.json").write_text(json.dumps({"payload": manifest}))
        compute = {"closed": True, **{k: 0 for k in gate.RESOURCE_COUNTS},
                   "faults": int(self.pending_fault), "policy_failures": 0, "restarts": 0, "discarded": 0}
        stdout.write("RESULT " + json.dumps({"run_id": "fake-run", "terminal_reason": "tournament_finished",
            "audit_degraded": False, "decision_compute": compute}) + "\n")
        stdout.flush()

    def test_new_entry_cwd_pythonpath_and_actual_fd_are_frozen(self):
        result = self.value.run_room(1, self.owner.fileno())
        command, settings = self.calls[0]
        self.assertEqual(Path(command[2]).parent.parent, self.value.ROOT)
        self.assertEqual(settings["cwd"], self.value.ROOT)
        self.assertEqual(settings["env"]["PYTHONPATH"], str(self.value.ROOT / "src") + ":" + str(self.value.ROOT))
        self.assertEqual(settings["pass_fds"], (self.owner.fileno(),))
        self.assertTrue(result["natural_boundary_verified"])
        self.assertTrue(result["gate"]["engineering_passed"])

    def test_room_does_not_wait_for_held_postprocess_lock(self):
        with (self.base / "postprocess.lock").open("a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.value.run_room(1, self.owner.fileno())
        self.assertTrue(result["natural_boundary_verified"])
        self.assertEqual(len(self.calls), 1)

    def test_fault_waits_natural_end_blocks_next_candidate(self):
        self.pending_fault = True
        result = self.value.run_room(1, self.owner.fileno())
        self.assertTrue((Path(result["directory"]) / "FREE-CHILD-TERMINAL.json").exists())
        self.assertTrue(result["gate"]["rollback_required"])
        self.assertFalse(gate.read_json(self.value.CONTROL)["continue_after_cycle"])
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(gate.GateError):
            self.value.run_room(2, self.owner.fileno())
        self.assertEqual(len(self.calls), 1)

    def test_unknown_launch_result_not_replayed_after_restart(self):
        def failed(*args, **kwargs):
            self.calls.append((args, kwargs))
            raise OSError("artificial Popen uncertainty")
        self.value.launcher = failed
        with self.assertRaises(OSError):
            self.value.run_room(1, self.owner.fileno())
        ledger = gate.ReleaseLedger(self.value.STATE / "batch-001/handoff")
        self.assertTrue(ledger.status()["dispatch_ambiguity"])
        with self.assertRaises(gate.GateError):
            self.value.recover_closed()
        self.assertEqual(len(self.calls), 1)

    def test_actual_player_still_live_does_not_launch(self):
        self.value.tools.h.other_players = lambda: [199099]
        with self.assertRaises(gate.GateError):
            self.value.run_room(1, self.owner.fileno())
        self.assertEqual(self.calls, [])

    def test_stale_config_package_refused_before_batch_or_dispatch(self):
        self.value.spec["identity"] = {**self.value.spec["identity"], "package_ids": {"free": "wrong-package"}}
        with self.assertRaises(gate.GateError):
            self.value.run_room(1, self.owner.fileno())
        self.assertFalse((self.value.STATE / "batch-001").exists())
        self.assertEqual(self.calls, [])

    def test_closed_terminal_recovers_without_new_launcher(self):
        result = self.value.run_room(1, self.owner.fileno())
        self.assertEqual(self.value.recover_closed(), [1])
        self.assertEqual(len(self.calls), 1)

    def test_postprocess_start_excluded_and_old_unstarted_adopted(self):
        self.value.run_room(1, self.owner.fileno())
        batch = self.value.STATE / "batch-001"
        old = self.base / "old-batch"
        old.mkdir()
        (old / "RUN-CLOSED.json").write_text("{}")
        self.value.spec["adopted_jobs"] = [{"directory": str(old)}]
        self.assertEqual(set(self.value.pending_jobs()), {batch, old})
        (old / "POSTPROCESS-START.json").write_text("{}")
        self.assertEqual(self.value.pending_jobs(), [batch])

    def test_natural_rollback_uses_parent_root_and_same_owner_fd(self):
        self.pending_fault = True
        closed = self.value.run_room(1, self.owner.fileno())
        parent = dict(self.spec)
        parent["shared"] = {**self.spec["shared"], "state_dir": str(self.base / "parent-state")}
        parent["qualification"] = {"corrected_fallback_passed": True}
        parent_path = self.base / "parent.json"
        parent_path.write_text(json.dumps(parent))
        self.value.spec["rollback_spec"] = str(parent_path)
        self.value.rollback(closed, self.owner.fileno())
        command, settings = self.calls[-1]
        self.assertIn("watch", command)
        self.assertEqual(settings["pass_fds"], (self.owner.fileno(),))
        self.assertEqual(settings["env"][runtime.OWNER_FD_ENV], str(self.owner.fileno()))
        self.assertEqual(settings["env"][runtime.ADOPT_STATE_ENV], str(self.value.STATE))
        self.assertFalse(gate.read_json(self.value.CONTROL)["background_enabled"])
        with self.assertRaises(gate.GateError):
            self.value.rollback(closed, self.owner.fileno())
        self.assertEqual(len(self.calls), 2)

    def test_rollback_wrong_core_or_open_room_rejected(self):
        self.value.rollback({"natural_boundary_verified": False}, self.owner.fileno())
        self.assertEqual(self.calls, [])

    def test_rollback_parent_known_fault_not_rearmed(self):
        self.pending_fault = True
        closed = self.value.run_room(1, self.owner.fileno())
        parent = dict(self.spec)
        parent_state = self.base / "parent-state"
        parent_state.mkdir()
        runtime.write_state(parent_state / "control.json", {"candidate_blocked": True})
        parent["shared"] = {**self.spec["shared"], "state_dir": str(parent_state)}
        parent["qualification"] = {"corrected_fallback_passed": True}
        parent_path = self.base / "parent.json"
        parent_path.write_text(json.dumps(parent))
        self.value.spec["rollback_spec"] = str(parent_path)
        with self.assertRaises(gate.GateError):
            self.value.rollback(closed, self.owner.fileno())
        self.assertEqual(len(self.calls), 1)

    def test_transfer_queue_only_adopts_unstarted(self):
        old_state = self.base / "old-state"
        first = old_state / "batch-001"
        second = old_state / "batch-002"
        first.mkdir(parents=True)
        second.mkdir()
        for path in (first, second):
            (path / "RUN-CLOSED.json").write_text("{}")
        (first / "POSTPROCESS-START.json").write_text("{}")
        runtime.write_state(self.value.STATE / "TRANSFER-QUEUE.json", {"predecessor_state": str(old_state)})
        self.assertEqual(self.value.pending_jobs(), [second])

    def test_light_scan_missing_data_and_budget_stay_unknown(self):
        empty = self.base / "empty"
        empty.mkdir()
        self.assertIsNone(runtime.scan_lightweight(empty, max_bytes=100, max_seconds=1)["real_new_missed_actions"])
        games = empty / "participants/u_x/games"
        games.mkdir(parents=True)
        (games / "g.jsonl").write_text(json.dumps({"kind": "game_finished", "payload": {}, "context": {}}) + "\n")
        self.assertIsNone(runtime.scan_lightweight(empty, max_bytes=1, max_seconds=1)["unrecovered_state"])

    def test_light_timeout_uses_own_seat_and_full_snapshot_clears_conflict(self):
        run = self.base / "scan"
        raw = run / "raw"
        raw.mkdir(parents=True)
        def row(stamp, body, requested=0):
            return {"kind": "raw_protocol_state", "context": {"game_id": "g"}, "monotonic_ns": stamp,
                "payload": {"source": "state_response", "http_status": 200, "seq_requested": requested, "raw": json.dumps(body)}}
        events = [{"type": "timeout", "seq": 9, "seat": 1, "data": {"kind": "discard"}},
                  {"type": "timeout", "seq": 10, "seat": 2, "data": {"kind": "discard"}}]
        rows = [row(1, {"gap": True}), row(2, {"snapshot": {"seat": 1}, "events": events}),
                row(3, {"snapshot": {"seat": 1}, "events": events})]
        (raw / "g.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
        result = runtime.scan_lightweight(run, max_bytes=10000, max_seconds=1)
        self.assertEqual(result["real_new_missed_actions"], 1)
        self.assertEqual(result["unrecovered_state"], 0)

    def test_protocol_events_null_missing_and_malformed(self):
        self.assertEqual(runtime.protocol_events({}), [])
        self.assertEqual(runtime.protocol_events({"events": None}), [])
        for value in (False, 0, "events", {}, [None], [{"seq": True, "type": "timeout"}]):
            with self.assertRaises(gate.GateError):
                runtime.protocol_events({"events": value})

    def test_sse_events_enter_timeout_parser_and_deduplicate_state(self):
        run = self.base / "sse-scan"
        raw = run / "participants/u_fixture/raw"
        raw.mkdir(parents=True)
        event = {"type": "timeout", "seq": 11, "seat": 2, "data": {"kind": "discard"}}
        rows = [{"kind": "raw_protocol_state", "context": {"game_id": "g"}, "monotonic_ns": 1,
            "payload": {"source": "state_response", "http_status": 200, "seq_requested": 0,
                        "raw": json.dumps({"snapshot": {"game_id": "g", "seat": 2}, "events": [event]})}},
            {"kind": "raw_protocol_state", "context": {"game_id": "g"}, "monotonic_ns": 2,
            "payload": {"source": "sse_frame", "raw": json.dumps({"seq": 11, "events": [event]})}}]
        (raw / "g.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
        result = runtime.scan_lightweight(run, max_bytes=10000, max_seconds=1)
        self.assertEqual(result["real_new_missed_actions"], 1)
        self.assertEqual(result["discard_timeout_events_deduplicated"], 1)
        self.assertEqual(result["state_events_loaded"], result["sse_events_loaded"])
        self.assertEqual(result["own_seats_by_game"], {"g": 2})

    def test_snapshot_gid_mismatch_rejected(self):
        run = self.base / "gid-scan"
        raw = run / "raw"
        raw.mkdir(parents=True)
        row = {"kind": "raw_protocol_state", "context": {"game_id": "g"}, "monotonic_ns": 1,
            "payload": {"source": "state_response", "http_status": 200, "seq_requested": 0,
                        "raw": json.dumps({"snapshot": {"game_id": "wrong", "seat": 0}, "events": None})}}
        (raw / "g.jsonl").write_text(json.dumps(row) + "\n")
        with self.assertRaises(gate.GateError):
            runtime.scan_lightweight(run, max_bytes=10000, max_seconds=1)


class ChiLightScanTests(unittest.TestCase):
    """真实吃窗片段走原轻扫接缝；临时文件不模拟HTTP或改变现场状态。"""
    def test_actual_chi_proof_reclassifies_only_illegal_counter(self):
        path = _project_file(_PROJECT_ROOT, ORIGIN / '.private/t200-eoh-fast-evolution/free-incident-batch011-chi/CHI-CASE.json')
        if not path.is_file():
            self.skipTest('真实Chi原件仅在本机私有证据中；可移植合成反控仍必跑')
        case = json.loads(path.read_text())
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); participant = run / 'participants/u_fixture'
            raw = participant / 'raw'; games = participant / 'games'
            raw.mkdir(parents=True); games.mkdir()
            records = []
            for record in case['records']:
                record = json.loads(json.dumps(record))
                if record['kind'] == 'decision_input':
                    item = record['payload']
                    record['payload'] = {'budget': item['budget'], 'request': {
                        'window_key': item['window'],
                        'observation': {'snapshot_seq': item['snapshot_seq'], 'consumed_seq': item['consumed_seq']},
                        'rules': {'completeness': item['rule_completeness'],
                                  'legal_candidates': [{'action_key': key} for key in item['legal_keys']]}}}
                records.append(record)
            (participant / 'decisions.jsonl').write_text('\n'.join(json.dumps(x) for x in records) + '\n')
            (raw / 'g.jsonl').write_text('\n'.join(json.dumps(x) for x in
                [*case['raw_pre_post_records'], case['rejection']]) + '\n')
            (games / 'g.jsonl').write_text('\n'.join(json.dumps(x) for x in case['applied_records']) + '\n')
            result = runtime.scan_lightweight(run, max_bytes=1048576, max_seconds=5,
                phase_index_max_bytes=1048576, phase_index_max_seconds=5)
        self.assertTrue(result['scan_complete'])
        self.assertEqual(result['illegal_submissions'], 0)
        self.assertEqual(result['unrecovered_state'], 0)
        self.assertEqual(result['warnings']['explicit_rejection'], 1)
        self.assertEqual(result['warnings']['recovered_expired_chi_window'], 1)
        self.assertEqual(result['warnings']['lost_response_opportunity'], 1)
        self.assertEqual(result['phase_reclassification_proofs'][0]['actual_outcome'], 'SubmitRejectedNoRefresh')


if __name__ == "__main__":
    unittest.main(verbosity=2)
