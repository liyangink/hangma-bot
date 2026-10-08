#!/usr/bin/env python3
"""G101：冻结 G85 新增的十六间同包自由赛房，并只重建公开正常摸打窗。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path
import tempfile

import g05_strong_draw_reconstruction as replay
import g59_freematch_white_value_audit as g59


HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927/manifest.json')
NEW = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g85-immediate-post-claim-discard-20260928/free_census.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G101-NEW-FREE-WIDER-ROUTE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g101-new-free-wider-route-20260928')
REPLAYER_SHA = "dd25efa11f95a53f81e195c7811db54f5c24595f7ca823180e6bc75f3ed6f78e"
G60_SHA = "b4559dff1333a8423d5ede0dce1cc05ca21077ed939be767fcaa4a7f942f4be1"
G85_SHA = "b9ad2d2bb401f2d446eb56f9d64df3822624e5ba68ffdd61cc8e30f437080029"


def sha_bytes(data: bytes) -> str:
    """输入文件与输出窗口使用相同字节摘要。"""
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    """返回文件的 SHA-256。"""
    return sha_bytes(path.read_bytes())


def write_new(path: Path, body: bytes) -> None:
    """结果已有时逐字核对，拒绝用新运行覆盖冻结证据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f"G101 冻结证据漂移：{path}")
        return
    path.write_bytes(body)


def json_bytes(payload: object) -> bytes:
    """机器证据保留中文，键排序使摘要可重复。"""
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def room_dir(room: str) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rooms" / room)


def run_room(room: str) -> str:
    """每房在临时目录运行已核重建器，再压缩逐窗公开证据。"""
    with tempfile.TemporaryDirectory(prefix="g101-replay-") as scratch:
        temporary = Path(scratch) / "replay"
        replay.run(room, 10, g59.US, temporary)
        windows = (temporary / "windows.json").read_bytes()
        result = (temporary / "result.json").read_bytes()
        write_new(room_dir(room) / "windows.json.gz", gzip.compress(windows, compresslevel=9, mtime=0))
        write_new(room_dir(room) / "result.json", result)
    return room


def verify(room: str, expected_games: list[str]) -> dict:
    """检查公开事实、十桌身份、未开结果标签和压缩证据一致。"""
    folder = room_dir(room)
    result_path = folder / "result.json"
    packed = (folder / "windows.json.gz").read_bytes()
    raw = gzip.decompress(packed)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    windows = json.loads(raw)["windows"]
    if (result["room_id"] != room or result["target_user_id"] != g59.US
            or result["script_sha256"] != REPLAYER_SHA
            or result["selected_games"] != expected_games
            or result["outcome_labels_opened"] is not False
            or not result["other_hidden_hand_perturbation_passed"]
            or len(windows) != result["counts"]["legal_verified_windows"]
            or any(window["room_id"] != room for window in windows)):
        raise ValueError(f"G101 房间复算或信息权限核验失败：{room}")
    return {
        "result_sha256": sha(result_path),
        "windows_uncompressed_sha256": sha_bytes(raw),
        "windows_gzip_sha256": sha_bytes(packed),
        "selected_games": expected_games,
        "counts": result["counts"],
        "parent_agreement": result["parent_agreement"],
        "parent_disagreement": result["parent_disagreement"],
    }


def main() -> None:
    """先冻结来源与房号，再并行只读重建并汇总覆盖账。"""
    for path, expected in ((OLD, G60_SHA), (NEW, G85_SHA),
                           (_project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py"), REPLAYER_SHA)):
        if sha(path) != expected:
            raise ValueError(f"G101 来源发生漂移：{path}")
    old = json.loads(OLD.read_text(encoding="utf-8"))["included"]
    new = json.loads(NEW.read_text(encoding="utf-8"))["included"]
    rooms = sorted(set(new) - set(old))
    if (len(rooms) != 16 or len(old) != 188 or len(new) != 204 or
            any(len(new[room]["game_ids"]) != 10 for room in rooms)):
        raise ValueError("G101 新旧完整房差集并非冻结的十六房")
    manifest = {
        "schema": "g101-new-free-wider-route-manifest/1",
        "outcome_labels_opened": False,
        "room_ids": rooms,
        "target_user_id": g59.US,
        "source_sha256": {
            "g60_manifest": sha(OLD), "g85_census": sha(NEW),
            "g05_replayer": sha(_project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py")),
            "g101_prereg": sha(PREREG), "g101_script": sha(Path(__file__)),
        },
        "boundary": "G85 已公开聚合房分；这里只分析官方当时可见动作，不能确认收益。",
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), json_bytes(manifest))
    pending = [room for room in rooms if not (room_dir(room) / "result.json").exists()]
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as workers:
            futures = {workers.submit(run_room, room): room for room in pending}
            for future in concurrent.futures.as_completed(futures):
                room = future.result()
                record = verify(room, new[room]["game_ids"])
                print(json.dumps({"room": room, "verified": record["counts"].get("legal_verified_windows"),
                                  "failures": record["counts"].get("analysis_failures", 0)},
                                 ensure_ascii=False), flush=True)
    records = {room: verify(room, new[room]["game_ids"]) for room in rooms}
    totals = Counter()
    for record in records.values():
        totals.update(record["counts"])
        totals["parent_agreement"] += record["parent_agreement"]
        totals["parent_disagreement"] += record["parent_disagreement"]
    result = {
        "schema": "g101-new-free-wider-route-batch/1", "outcome_labels_opened": False,
        "manifest_sha256": sha(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "rooms": records, "totals": dict(sorted(totals.items())),
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), json_bytes(result))
    print(json.dumps({"rooms": len(rooms), "totals": result["totals"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
