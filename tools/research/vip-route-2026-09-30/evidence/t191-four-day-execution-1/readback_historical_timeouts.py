"""确认旧第40房官方超时原件及可用证据边界，不推测缺失的客户端时序。

该脚本不是动态故障重现：原运行审计缺失，无法重放实际请求/动作路径。
只核已封存官方原件、旧摘要及两次超时；不修改线上或重新评分/触网。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t179-production-wiring-1/batch-040')
ARCHIVE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t190-four-day-targeted-review-1/SOURCE-INPUTS.jsonl.gz')


def pin(path):
    """原字节摘要和相对路径，用于后续恢复核对。"""
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def load(path):
    """仅读取指定原件，历史值不由本次诊断修正。"""
    return json.loads(path.read_text())


def main():
    """复核两桌原件和症状；客户端因果归因仍然未知。"""
    out = _project_file(_PROJECT_ROOT, HERE / "historical-timeouts-readback")
    out.mkdir(exist_ok=False)
    archive_meta = load(ARCHIVE.with_name("SOURCE-ARCHIVE-VERIFIED.json"))
    assert pin(ARCHIVE)["sha256"] == archive_meta["sha256"]
    summary = load(_project_file(_PROJECT_ROOT, OLD / "SUMMARY.json"))
    capture = load(_project_file(_PROJECT_ROOT, OLD / "free-capture/CAPTURE.json"))
    archived = {}
    archive_kind_counts = Counter()
    with gzip.open(ARCHIVE, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            name = row["reference"]["path"]
            archive_kind_counts[Path(name).name] += 1
            if "t179-production-wiring-1/batch-040/" not in name:
                continue
            raw = row["raw_utf8"].encode()
            assert hashlib.sha256(raw).hexdigest() == row["reference"]["sha256"]
            assert (_project_file(_PROJECT_ROOT, ROOT / name)).read_bytes() == raw
            archived[name] = row["reference"]
    assert len(archived) == 15
    actual = []
    for batch, seat, timeout_seq in ((5, 1, 739), (6, 0, 737)):
        gid = "a_ec73ebaae5ed_r1_b{}_t0".format(batch)
        ref = next(r for r in capture["ten_tables"] if r["game_id"] == gid)
        matches = [f for f in (_project_file(_PROJECT_ROOT, OLD / "free-capture")).glob("capture-*.bin")
                   if pin(f)["sha256"] == ref["original_sha256"]]
        assert len(matches) == 1
        source = matches[0]
        assert str(source.relative_to(ROOT)) in archived
        doc = load(source)
        events = [e for block in doc["blocks"] for e in block["events"]]
        i = next(i for i, e in enumerate(events) if e["seq"] == timeout_seq)
        timeout = events[i]
        discard, drawn = events[i - 1], events[i - 2]
        assert timeout["type"] == "timeout" and timeout["seat"] == seat
        assert timeout["data"]["kind"] == "discard"
        assert discard["type"] == "tile_discarded" and discard["seat"] == seat
        assert drawn["type"] == "tile_drawn" and drawn["seat"] == seat
        assert drawn["tile"] == discard["tile"]
        assert timeout["ts"] - drawn["ts"] == 3
        own = next(h for h in summary["hands"] if h["game_id"] == gid and h["round_no"] == 4)
        assert own["seat"] == seat
        destination = out / (gid + ".events.json")
        destination.write_bytes(source.read_bytes())
        actual.append({"game_id": gid, "round_no": 4, "our_seat": seat,
            "official_source": pin(source), "copied_original": pin(destination),
            "official_seq_clip": events[i - 4:i + 4],
            "draw_seq": drawn["seq"], "discard_seq": discard["seq"],
            "timeout_seq": timeout_seq, "official_ts_unit": "Unix秒，整数精度",
            "coarse_draw_to_timeout_seconds": 3,
            "local_receive_rule_compute_submit_response_timing": None,
            "local_exact_symptom_replay_available": False,
            "first_step_cause_verified": False})
    plan = load(_project_file(_PROJECT_ROOT, OLD / "PLAN.json"))
    session = _project_file(_PROJECT_ROOT, ROOT / plan["free_session"])
    audit = summary["audit"][0]
    assert not session.exists()
    assert not any(f["context"]["game_id"] in {r["game_id"] for r in actual}
        and f["context"]["round_no"] == 4 for f in audit["failed_plans"])
    value = {"schema": "t191-historical-timeouts-evidence-boundary/1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "official_discard_timeouts_confirmed": 2, "rows": actual,
        "original_session_path": str(session.relative_to(ROOT)), "session_exists": False,
        "original_run_id": "run-50a830aa0b9c4f5bb1d8cd500200ae18",
        "postgame_archive_original_path": plan["free_session"] +
            "/postgame/20261004T200857Z-531589bc/archives/20261004T200857Z-531589bc.tar.gz",
        "known_archive_contains_raw_run_timeline": False,
        "known_archive_source_types": dict(archive_kind_counts),
        "batch40_archived_members_exact": len(archived),
        "same_room_aggregate_not_causal": {
            "plans": audit["plans"], "complete_plans": audit["complete_plans"],
            "http_categories": audit["http_categories"], "state_queue_wait": audit["state_queue_wait"],
            "failed_plans_in_two_timeout_rounds": 0},
        "causal_attribution": "unknown",
        "not_proven": ["两次409对应这两个超时动作", "该房state429造成两次超时",
            "CPU或规则计算造成两次超时", "新free_v7已修复这两个历史时序"],
        "minimum_missing_evidence": ["原decisions.jsonl和两桌game审计",
            "原raw协议请求/响应（含SSE与请求时序）", "原run manifest用于复核运行版本与配置"],
        "diagnosis_skill_boundary": "静态症状读回非实际故障路径重现；因缺原时序，Phase1红能力动态复现未建立，未进入猜因或生产修复。",
        "online_or_policy_change": False, "new_HTTP_scores_worlds_models_tables": 0,
        "pins": [pin(ARCHIVE), pin(_project_file(_PROJECT_ROOT, OLD / "SUMMARY.json")), pin(_project_file(_PROJECT_ROOT, OLD / "PLAN.json")),
            pin(_project_file(_PROJECT_ROOT, OLD / "FREE-POSTGAME.log")), pin(_project_file(_PROJECT_ROOT, OLD / "free-capture/CAPTURE.json")), pin(Path(__file__))]}
    with (out / "CLOSED.json").open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"official_timeouts_confirmed": 2, "exact_archive_members": 15,
        "local_original_session_exists": False, "client_cause": "unknown", "new_HTTP_or_scores": 0}))


if __name__ == "__main__":
    main()
