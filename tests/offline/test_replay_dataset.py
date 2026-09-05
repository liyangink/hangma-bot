"""统一牌谱数据集组装测试：官方分块转换、身份合并、legacy 不伪造。"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from hangma_bot.adapters.recording.bundle import create_bundle, pack_bundle
from hangma_bot.offline.replay import (
    REPLAY_SCHEMA_VERSION,
    build_dataset,
    hand_id,
    load_hand_rows,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hangma" / "archived-rooms"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_decision_record(root: Path, run_id: str, pid: str, *, with_input: bool):
    run_dir = root / "runs" / run_id / "participants" / pid
    run_dir.mkdir(parents=True)
    context = {
        "run_id": run_id,
        "tournament_id": "t_6c121bfda7e8",
        "participant_id": pid,
        "stage_attempt_id": "sa-" + run_id,
        "game_id": "t_6c121bfda7e8_r4_b0_t0",
        "round_no": 1,
        "trigger_seq": 10,
        "decision_id": "dec-" + run_id,
    }
    if with_input:
        request = {
            "codec_version": 1,
            "decision_id": "dec-" + run_id,
            "trigger_seq": 10,
            "window_key": {"schema_version": 1, "game_id": "t_6c121bfda7e8_r4_b0_t0", "round_no": 1, "trigger_seq": 10, "phase": "draw", "seat": 0},
            "observation": _observation_json(),
            "competition": {"schema_version": 1, "tournament_id": "t_6c121bfda7e8", "stage_no": None, "stage_role": None, "stage_total": None, "participant_rank": None, "ranking": [], "observed_at_unix_ms": 1},
            "rules": {"codec_version": 1, "legal_candidates": [], "emergency_candidate": None, "completeness": "complete", "ruleset_version": "v1", "issues": []},
            "rejected_attempts": [],
        }
        payload = {
            "plan_revision": 1,
            "budget_origin_monotonic": 100.0,
            "rule_elapsed_ms": 1.0,
            "request": request,
            "budget": {"codec_version": 1, "enhancement_deadline_monotonic": 100.5, "fallback_deadline_monotonic": 100.7, "latest_send_at_monotonic": 100.85},
            "window": {"game_id": "t_6c121bfda7e8_r4_b0_t0", "round_no": 1, "trigger_seq": 10, "phase": "draw", "seat": 0},
            "capture_profile": "audit-plus-v1",
            "audit_producer": "application",
        }
        (run_dir / "decisions.jsonl").write_text(
            json.dumps({"schema_version": 1, "kind": "decision_input", "context": context,
                        "wall_time_unix_ms": 1, "monotonic_ns": 1, "payload": payload}, ensure_ascii=False)
            + chr(10),
            encoding="utf-8",
        )
    ended_payload = {"plan_revision": 1, "end_reason": "exhausted", "attempt_count": 0, "sent_attempts": 0}
    with open(run_dir / "decisions.jsonl", "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"schema_version": 1, "kind": "decision_ended", "context": context,
                        "wall_time_unix_ms": 2, "monotonic_ns": 2, "payload": ended_payload}, ensure_ascii=False)
            + chr(10)
        )
    (root / "runs" / run_id / "summary.json").write_text("{}", encoding="utf-8")


def _observation_json():
    return {
        "schema_version": 1,
        "game_id": "t_6c121bfda7e8_r4_b0_t0",
        "seat": 0,
        "round_no": 1,
        "snapshot_seq": 10,
        "phase": "draw",
        "dealer_seat": 0,
        "turn_seat": 0,
        "responding_seats": [],
        "my_hand": ["1w", "2w", "3w"],
        "drawn_tile": None,
        "discards": [[], [], [], []],
        "melds": [[], [], [], []],
        "hand_counts": [13, 13, 13, 13],
        "last_discard": None,
        "remaining_tile_count": None,
        "scores": [0, 0, 0, 0],
        "rule_state": {"wealth_god": "白", "baotou": False, "chain_count": 0, "catch_play": False},
        "public_history": [],
    }


def _bundle_with_room(root: Path, run_ids) -> Path:
    manifest = create_bundle(root, run_ids=run_ids, out_dir=root / "bundles-root")
    bundle_dir = root / "bundles-root" / "bundles" / manifest.bundle_id
    off_dir = bundle_dir / "official" / "dl-1"
    off_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "t_6c121bfda7e8_b0.json", off_dir / "events.json")
    (off_dir / "source.json").write_text(
        json.dumps({
            "room_id": "t_6c121bfda7e8",
            "game_id": "t_6c121bfda7e8_r4_b0_t0",
            "batch": 0,
            "guide_version": 14,
            "captured_at_unix_ms": 1,
        }),
        encoding="utf-8",
    )
    pack_bundle(bundle_dir, root / "b.tar.gz")
    return bundle_dir


def test_full_dataset_build_with_identity_merge(tmp_path):
    """官方分块样本 + 两个运行视角：一个 hand_id、两条视角、决策行完整。"""

    root = tmp_path / "audit"
    root.mkdir()
    _write_decision_record(root, "run-0", "p-0", with_input=True)
    _write_decision_record(root, "run-1", "p-1", with_input=True)
    bundle_dir = _bundle_with_room(root, ["run-0", "run-1"])
    report = build_dataset(
        bundle_dir, tmp_path / "datasets", source_namespace="hangma-official",
        guide_version=14, guide_captured_at="2026-09-05",
    )
    assert report["hands_total"] == 1
    assert report["decisions_total"] == 2
    assert report["excluded_decisions"] == 0
    dataset_dir = Path(report["dataset_dir"])
    index = [
        json.loads(line)
        for line in (dataset_dir / "index.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(index) == 1
    assert index[0]["hand_id"] == hand_id(
        "hangma-official", "t_6c121bfda7e8", "t_6c121bfda7e8_r4_b0_t0", 1
    )
    assert len(index[0]["views"]) == 2
    assert index[0]["attempt_status"] == "valid"
    assert index[0]["official_refs"][0]["room_id"] == "t_6c121bfda7e8"
    hands = load_hand_rows(dataset_dir / "hands.jsonl")
    assert len(hands) == 1
    hand = hands[0]
    assert hand["replay_schema_version"] == REPLAY_SCHEMA_VERSION
    assert hand["origin"] == "official"
    assert hand["coverage"] == "full_history"
    assert hand["initial"]["wall"] is None
    assert hand["initial"]["draw_identity_known"] is False
    assert len(hand["events"]) == 448
    # 事件保留官方字段语义与来源引用（未知字段原样保留）。
    assert hand["events"][0]["seq"] == 1
    assert hand["events"][0]["source_refs"][0]["json_pointer"].startswith("/blocks/")
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contract_id"] == "parallel-v1"
    assert manifest["replay_schema_version"] == 1
    assert manifest["guide_version"] == 14
    assert manifest["bundle_id"] == Path(bundle_dir).name
    validation = report["validation"]
    assert validation["file_integrity"]["status"] == "passed"
    assert validation["decision_completeness"]["status"] == "passed"
    assert validation["history_coverage"]["status"] == "passed"
    assert validation["world_importability"]["status"] == "not_checked"
    assert validation["rule_consistency"]["status"] == "not_checked"
    decisions = [
        json.loads(line)
        for line in (dataset_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert all(row["decision_complete"] for row in decisions)
    assert all(row["hand_id"] == index[0]["hand_id"] for row in decisions)


def test_legacy_decisions_go_to_excluded_not_fabricated(tmp_path):
    """缺 DECISION_INPUT 的旧记录只进 excluded，不伪造可训练决策。"""

    root = tmp_path / "audit"
    root.mkdir()
    _write_decision_record(root, "run-0", "p-0", with_input=False)
    bundle_dir = _bundle_with_room(root, ["run-0"])
    report = build_dataset(
        bundle_dir, tmp_path / "datasets", source_namespace="hangma-official"
    )
    assert report["decisions_total"] == 0
    assert report["excluded_decisions"] == 1
    assert report["validation"]["decision_completeness"]["status"] == "failed"


def test_unknown_replay_major_rejected_on_hand_rows(tmp_path):
    path = tmp_path / "hands.jsonl"
    path.write_text(
        json.dumps({"replay_schema_version": 99, "hand_id": "hand-x"}) + chr(10),
        encoding="utf-8",
    )
    before = path.read_bytes()
    with pytest.raises(ValueError):
        load_hand_rows(path)
    assert path.read_bytes() == before


def test_bundle_with_tampered_file_rejected(tmp_path):
    root = tmp_path / "audit"
    root.mkdir()
    _write_decision_record(root, "run-0", "p-0", with_input=True)
    bundle_dir = _bundle_with_room(root, ["run-0"])
    target = bundle_dir / "runs" / "run-0" / "summary.json"
    target.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError):
        build_dataset(bundle_dir, tmp_path / "datasets", source_namespace="hangma-official")


def _two_round_events_doc():
    """两份局各两个块的多局文档；用于指针对齐与覆盖测试。"""

    def _block(round_no, seq_start, seq_end):
        events = [
            {"seq": seq, "type": "tile_discarded" if (seq - seq_start) % 2 == 0 else "timeout",
             "seat": 0, "tile": "1w" if (seq - seq_start) % 2 == 0 else "", "data": None, "ts": 1}
            for seq in range(seq_start, seq_end + 1)
        ]
        hands = [
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b", "5b"],
            ["2b", "3b", "4b", "5b", "6b", "7b", "8b", "9b", "1t", "2t", "3t", "4t", "5t"],
            ["6t", "7t", "8t", "9t", "东", "南", "西", "北", "中", "发", "白", "1w", "2w"],
            ["3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b", "5b", "6b"],
        ]
        return {
            "round_no": round_no, "seq_start": seq_start, "seq_end": seq_end,
            "truncated": False, "dealer": 0,
            "start_hands": hands if seq_start == 1 else [None, None, None, None],
            "events": events,
        }

    return {
        "room_id": "t_multi", "game_id": "t_multi_r2_b0_t0", "batch": 0,
        "status": "finished", "seats": [],
        "rounds": [
            {"round_no": 1, "dealer": 0, "is_draw": 0, "winner": 0, "scores": [1, 0, 0, 0]},
            {"round_no": 2, "dealer": 0, "is_draw": 0, "winner": 1, "scores": [1, 2, 0, 0]},
        ],
        "blocks": [
            _block(1, 1, 3), _block(1, 4, 5),
            _block(2, 1, 2), _block(2, 3, 5),
        ],
    }


def _bundle_with_official_file(root: Path, run_ids, dir_name: str, file_name: str, content: str) -> Path:
    manifest = create_bundle(root, run_ids=run_ids, out_dir=root / "bundles-root")
    bundle_dir = root / "bundles-root" / "bundles" / manifest.bundle_id
    off_dir = bundle_dir / "official" / dir_name
    off_dir.mkdir(parents=True)
    (off_dir / file_name).write_text(content, encoding="utf-8")
    pack_bundle(bundle_dir, root / "b.tar.gz")
    return bundle_dir


def test_corrupt_events_json_download_surfaced_not_silent(tmp_path):
    """审查返工回归：官方下载损坏绝不静默丢弃——历史覆盖判 failed，
    不伪造空牌谱；运行侧决策行不受影响。"""

    root = tmp_path / "audit"
    root.mkdir()
    _write_decision_record(root, "run-0", "p-0", with_input=True)
    bundle_dir = _bundle_with_official_file(
        root, ["run-0"], "dl-bad", "events.json", "{broken json",
    )
    (bundle_dir / "official" / "dl-bad" / "source.json").write_text(
        json.dumps({"room_id": "t_6c121bfda7e8", "game_id": "t_6c121bfda7e8_r4_b0_t0",
                    "batch": 0, "guide_version": 14, "captured_at_unix_ms": 1}),
        encoding="utf-8",
    )
    report = build_dataset(bundle_dir, tmp_path / "datasets", source_namespace="hangma-official")
    assert report["hands_total"] == 0
    assert report["decisions_total"] == 1  # 决策证据独立于下载证据
    history = report["validation"]["history_coverage"]
    assert history["status"] == "failed"
    issues = {item["issue"] for item in history["issues"]}
    assert "corrupt_events_json" in issues


def test_incomplete_download_surfaced(tmp_path):
    """只有 source.json 没有 events.json：incomplete_download 显式报告。"""

    root = tmp_path / "audit"
    root.mkdir()
    _write_decision_record(root, "run-0", "p-0", with_input=True)
    bundle_dir = _bundle_with_official_file(
        root, ["run-0"], "dl-half", "source.json",
        json.dumps({"room_id": "t_6c121bfda7e8", "game_id": "t_6c121bfda7e8_r4_b0_t0",
                    "batch": 0, "guide_version": 14, "captured_at_unix_ms": 1}),
    )
    report = build_dataset(bundle_dir, tmp_path / "datasets", source_namespace="hangma-official")
    history = report["validation"]["history_coverage"]
    assert history["status"] == "failed"
    assert any(item["issue"] == "incomplete_download" for item in history["issues"])


def test_multi_round_download_hands_keep_document_pointers(tmp_path):
    """多局文档端到端：每局各自成行，事件 source_refs 的 json_pointer
    指向原文档 blocks 数组下标（第二局从 /blocks/2/ 起）。"""

    root = tmp_path / "audit"
    root.mkdir()
    _write_decision_record(root, "run-0", "p-0", with_input=True)
    bundle_dir = _bundle_with_official_file(
        root, ["run-0"], "dl-multi", "events.json",
        json.dumps(_two_round_events_doc(), ensure_ascii=False),
    )
    (bundle_dir / "official" / "dl-multi" / "source.json").write_text(
        json.dumps({"room_id": "t_multi", "game_id": "t_multi_r2_b0_t0",
                    "batch": 0, "guide_version": 14, "captured_at_unix_ms": 1}),
        encoding="utf-8",
    )
    report = build_dataset(bundle_dir, tmp_path / "datasets", source_namespace="hangma-official")
    assert report["hands_total"] == 2
    dataset_dir = Path(report["dataset_dir"])
    hands = load_hand_rows(dataset_dir / "hands.jsonl")
    by_round = {hand["round_no"]: hand for hand in hands}
    assert by_round[1]["events"][0]["source_refs"][0]["json_pointer"].startswith("/blocks/0/")
    assert by_round[2]["events"][0]["source_refs"][0]["json_pointer"].startswith("/blocks/2/")
    assert by_round[2]["events"][-1]["source_refs"][0]["json_pointer"].startswith("/blocks/3/")
