"""有界定位三处实际决策原件，不全扫大审计，不把定位失败当作记录缺失。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import ctypes
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
TARGETS = (
    ("t179-batch-001-free", "run-4107962142a04b55aeef919f9384a8c5",
     "a_a8c4f4e461ce_r1_b7_t0", ((2, 242), (5, 982))),
    ("t179-batch-004-free", "run-27a24743b8cd43b6b3cc9715dace89fd",
     "a_94793050830e_r1_b0_t0", ((7, 1177),)),
)
MAX_READ = 64 * 1024 * 1024
MAX_LINE = 2 * 1024 * 1024


def canonical(value):
    """有限JSON用于字节摘要；不省略实际输入中的未知字段。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


class BoundedReader:
    """累计实际read字节；seek不伪称读过其跳过的记录。"""

    def __init__(self):
        self.bytes = 0

    def line(self, stream):
        limit = min(MAX_LINE, MAX_READ - self.bytes)
        if limit <= 0:
            raise RuntimeError("读取预算耗尽")
        raw = stream.readline(limit)
        self.bytes += len(raw)
        if raw and not raw.endswith(b"\n"):
            raise RuntimeError("记录超过有界读取长度；本次不宣称记录缺失")
        return raw

    def file(self, path):
        if path.stat().st_size > MAX_READ - self.bytes:
            raise RuntimeError("小文件读取预算耗尽")
        raw = path.read_bytes()
        self.bytes += len(raw)
        return raw

    def at(self, stream, offset):
        """从任意偏移跳过残行，再读取一条完整记录并保留其真实字节范围。"""
        stream.seek(max(0, offset))
        if offset:
            self.line(stream)
        start = stream.tell()
        raw = self.line(stream)
        return start, raw


def stamp_locator(stream, size, stamp, reader):
    """时间近似二分只用于找到邻域；结果必须再按完整窗口键正向核验。

    审计队列可能改变时间顺序，不假定文件严格排序。二分未找到原件时
    保留未知，不由空命中推导原记录不存在。
    """
    lo, hi = 0, size
    for _ in range(20):
        if hi - lo <= 64 * 1024:
            break
        at, raw = reader.at(stream, (lo + hi) // 2)
        if not raw:
            hi = (lo + hi) // 2
            continue
        record = json.loads(raw)
        if record["monotonic_ns"] < stamp:
            lo = min(at + len(raw), hi)
        else:
            hi = at
    return max(0, lo - 256 * 1024)


def main():
    """占共用赛后锁、降低CPU/IO优先级；仅写本批新的原件摘录及费用收据。"""
    target = _project_file(_PROJECT_ROOT, HERE / "EXACT-INPUTS.json")
    if target.exists():
        raise FileExistsError(target)
    os.nice(15)
    libc = ctypes.CDLL(None, use_errno=True)
    io_status = libc.setiopolicy_np(0, 0, 3)  # macOS进程后台磁盘IO；与CPU nice分开。
    if io_status != 0:
        raise OSError(ctypes.get_errno(), "后台IO设置失败")
    reader = BoundedReader()
    result = {"schema": "t182-exact-original-inputs/1", "windows": [],
              "read_limit_bytes": MAX_READ, "io_status": io_status,
              "locator_is_not_proof_of_absence": True, "new_rules_scores_worlds_calls": 0}
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for session, run_id, game_id, windows in TARGETS:
            audit = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions" / session / "audit/runs" / run_id)
            manifest_file = audit / "manifest.json"
            manifest_raw = reader.file(manifest_file)
            manifest = json.loads(manifest_raw)["payload"]
            participant = audit / "participants/u_13495c3d79c8"
            paths = sorted((participant / "raw").glob(game_id + ".*.jsonl.gz"))
            snapshots = {}
            raw_pins = []
            for path in paths:
                raw_pins.append({"path": str(path.relative_to(ROOT)),
                                 "sha256": hashlib.sha256(reader.file(path)).hexdigest()})
                with gzip.open(path, "rb") as stream:
                    while raw := reader.line(stream):
                        row = json.loads(raw)
                        context = row.get("context") or {}
                        key = context.get("round_no"), context.get("trigger_seq")
                        if key not in windows or row["payload"].get("source") != "state_response":
                            continue
                        doc = json.loads(row["payload"]["raw"])
                        snapshot = doc.get("snapshot")
                        if snapshot is None:
                            continue
                        assert doc["seq"] == key[1] and snapshot["game_id"] == game_id
                        assert snapshot["round_no"] == key[0]
                        assert key not in snapshots, "同窗多次快照须先明确选取规则"
                        snapshots[key] = row
            assert set(snapshots) == set(windows), "未定位完整快照，不能继续推断"
            decision_file = participant / "decisions.jsonl"
            before = decision_file.stat()
            with decision_file.open("rb") as stream:
                for key in windows:
                    snapshot = snapshots[key]
                    stamp = snapshot["monotonic_ns"]
                    begin = stamp_locator(stream, before.st_size,
                                          stamp - 3_000_000_000, reader)
                    stream.seek(begin)
                    if begin:
                        reader.line(stream)
                    records = []
                    neighborhood_bytes = 0
                    # 邻域上限8MiB；越界保持失败原件，不静默改成全文件扫描。
                    while neighborhood_bytes < 8 * 1024 * 1024:
                        offset = stream.tell()
                        raw = reader.line(stream)
                        if not raw:
                            break
                        neighborhood_bytes += len(raw)
                        row = json.loads(raw)
                        context = row.get("context") or {}
                        if (context.get("game_id") == game_id and
                                (context.get("round_no"), context.get("trigger_seq")) == key):
                            records.append({"offset": offset, "bytes": len(raw),
                                            "sha256": hashlib.sha256(raw).hexdigest(),
                                            "record": row})
                        if row["monotonic_ns"] > stamp + 5_000_000_000:
                            break
                    inputs = [r for r in records if r["record"]["kind"] == "decision_input"]
                    plans = [r for r in records if r["record"]["kind"] == "decision_planned"]
                    assert len(inputs) == 1 and len(plans) == 1, "有界邻域未核齐单一输入/计划"
                    decision_id = inputs[0]["record"]["context"]["decision_id"]
                    assert plans[0]["record"]["context"]["decision_id"] == decision_id
                    result["windows"].append({"game_id": game_id, "round_no": key[0],
                        "trigger_seq": key[1], "decision_id": decision_id,
                        "rule_config": {k: manifest[k] for k in (
                            "ruleset_version", "base_score", "you_cai_bi_kao")},
                        "policy_version": manifest["policy_version"],
                        "policy_release": manifest["policy_release"],
                        "manifest_source": str(manifest_file.relative_to(ROOT)),
                        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                        "raw_source_pins": raw_pins,
                        "snapshot_record": snapshot,
                        "decision_source": str(decision_file.relative_to(ROOT)),
                        "decision_file_size": before.st_size,
                        "locator_start_offset": begin, "records": records})
            after = decision_file.stat()
            assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        result["read_bytes"] = reader.bytes
        result["complete"] = len(result["windows"]) == 3
        with target.open("xb") as stream:
            stream.write(canonical(result) + b"\n")
    print(json.dumps({"complete": result["complete"], "windows": len(result["windows"]),
                      "read_bytes": reader.bytes, "new_rules_scores_worlds_calls": 0}))


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        failure = _project_file(_PROJECT_ROOT, HERE / "EXACT-INPUTS-FAILURE.json")
        if not failure.exists():
            with failure.open("xb") as stream:
                stream.write(canonical({"status": "failed", "type": type(error).__name__,
                                        "message": str(error)}) + b"\n")
        raise
