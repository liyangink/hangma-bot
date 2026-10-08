#!/usr/bin/env python3
"""G69：在 G61 的相同强手房，以原 G05 严格口径重建我方正常摸打。"""

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
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path

import g05_strong_draw_reconstruction as replay
import g59_freematch_white_value_audit as g59
import g61_strong_draw_batch as g61


HERE = Path(__file__).resolve().parent
G60 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927')
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928')


def directory(room: str) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rooms" / room)


def seal_room(room: str) -> None:
    """完整 JSON 无损封存为确定性 gzip，避免把数百万行原文放进 Git。"""

    raw = directory(room) / "windows.json"
    sealed = directory(room) / "windows.json.gz"
    if not raw.exists():
        if not sealed.exists():
            raise ValueError("G69 房间缺逐窗证据")
        return
    if sealed.exists():
        raise ValueError("G69 同时存在未封存与已封存逐窗文件")
    raw_bytes = raw.read_bytes()
    with sealed.open("wb") as target:
        with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as stream:
            stream.write(raw_bytes)
    with gzip.open(sealed, "rb") as stream:
        if stream.read() != raw_bytes:
            raise ValueError("G69 无损封存后逐窗内容不一致")
    raw.unlink()


def run_room(room: str) -> str:
    """以隔离房目录保存逐窗证据；已存在目录由重建器拒绝覆盖。"""

    with contextlib.redirect_stdout(io.StringIO()):
        replay.run(room, 10, g59.US, directory(room))
    seal_room(room)
    return room


def verify(room: str, games: list[str]) -> dict:
    """核对十桌、原版 G05 源码、信息权限负控与逐窗合法性。"""

    result_path = directory(room) / "result.json"
    windows_path = directory(room) / "windows.json.gz"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    with gzip.open(windows_path, "rb") as stream:
        raw = stream.read()
    windows = json.loads(raw)["windows"]
    if (result["script_sha256"] != g61.REPLAYER_SHA or result["room_id"] != room or
            result["target_user_id"] != g59.US or result["selected_games"] != sorted(games) or
            result["outcome_labels_opened"] is not False or
            result["other_hidden_hand_perturbation_passed"] is not True or
            result["counts"].get("analysis_failures", 0) != 0 or
            len(windows) != result["counts"]["legal_verified_windows"]):
        raise ValueError("G69 我方同房十桌身份、合法性或信息权限不一致")
    return {"result_sha256": g61.sha(result_path),
            "windows_sha256": hashlib.sha256(raw).hexdigest(),
            "windows_gzip_sha256": g61.sha(windows_path),
            "counts": result["counts"]}


def main() -> None:
    if g61.sha(_project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py")) != g61.REPLAYER_SHA:
        raise ValueError("G69 冻结重建器源码变化")
    g60_path, g61_path = _project_file(_PROJECT_ROOT, G60 / "manifest.json"), _project_file(_PROJECT_ROOT, G61 / "manifest.json")
    g60 = json.loads(g60_path.read_text(encoding="utf-8"))
    g61_manifest = json.loads(g61_path.read_text(encoding="utf-8"))
    rooms = sorted({unit["room"] for unit in g61_manifest["units"]})
    if len(rooms) != 31 or g60["complete_rooms"] != 188 or any(room not in g60["included"] for room in rooms):
        raise ValueError("G69 强手同房母体漂移")
    manifest = {"schema": "g69-same-room-us-replay-manifest/1",
                "release_package_id": g60["release_package_id"],
                "rooms": rooms, "games": {room: g60["included"][room] for room in rooms},
                "source_sha256": {
                    "g60_manifest": g61.sha(g60_path),
                    "g61_manifest": g61.sha(g61_path),
                    "g05_replayer": g61.sha(_project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py")),
                    "g69_prereg": g61.sha(_project_file(_PROJECT_ROOT, HERE / "G69-SAME-ROOM-ROUTE-CHAIN-PREREG-2026-09-28.md")),
                    "g69_batch": g61.sha(Path(__file__)),
                }}
    g61.write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    for room in rooms:
        if (directory(room) / "result.json").exists():
            seal_room(room)
    pending = [room for room in rooms if not (directory(room) / "result.json").exists()]
    errors = {}
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as workers:
            futures = {workers.submit(run_room, room): room for room in pending}
            for future in concurrent.futures.as_completed(futures):
                room = futures[future]
                try:
                    future.result()
                    record = verify(room, g60["included"][room])
                    print(json.dumps({"room": room,
                                      "legal_windows": record["counts"]["legal_verified_windows"]},
                                     ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    errors[room] = type(exc).__name__ + ": " + str(exc)[:300]
                    print(json.dumps({"room": room, "error": errors[room]}, ensure_ascii=False), flush=True)
    records = {}
    for room in rooms:
        if room not in errors:
            try:
                records[room] = verify(room, g60["included"][room])
            except Exception as exc:  # noqa: BLE001
                errors[room] = type(exc).__name__ + ": " + str(exc)[:300]
    totals = Counter()
    for record in records.values():
        totals.update(record["counts"])
    result = {"schema": "g69-same-room-us-replay-batch/1",
              "manifest_sha256": g61.sha(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
              "selected_rooms": len(rooms), "completed_rooms": len(records),
              "rooms": records, "errors": dict(sorted(errors.items())),
              "totals": dict(sorted(totals.items())),
              "boundary": "同强手房、同 G05 正常摸打子集；不以别人的实际手牌作同墙反事实。"}
    g61.write_new(_project_file(_PROJECT_ROOT, OUT / "batch_result.json"), result)
    print(json.dumps({"completed_rooms": len(records), "errors": errors,
                      "totals": result["totals"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
