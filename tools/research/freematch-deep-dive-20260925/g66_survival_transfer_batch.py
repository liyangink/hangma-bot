#!/usr/bin/env python3
"""G66：40 间未用于强手训练的 R18 v2 官方房，重建本人正常摸打。"""

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
G65 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g65-next-draw-survival-20260928')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g66-survival-transfer-20260928')


def sha(path: Path) -> str:
    """读取本地冻结输入及输出摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def choose_rooms(g60: dict, g61_manifest: dict) -> list[str]:
    """排除强手训练房后按房号摘要固定前 40 间。"""

    trained = {unit["room"] for unit in g61_manifest["units"]}
    candidates = set(g60["included"]) - trained
    if len(trained) != 31 or len(candidates) != 157:
        raise ValueError("G66 完整房或训练房集合漂移")
    return sorted(candidates, key=lambda room: (hashlib.sha256(room.encode("utf-8")).hexdigest(), room))[:40]


def directory(room: str) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rooms" / room)


def run_room(room: str) -> str:
    """每房十桌；重建器本身逐窗核对规则、暗手负控和后继事件。"""

    with contextlib.redirect_stdout(io.StringIO()):
        replay.run(room, 10, g59.US, directory(room))
    return room


def verify(room: str, expected_games: list[str]) -> dict:
    """只接受原 G05 冻结源码及同一房十桌的合法窗口。"""

    path = directory(room) / "result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    expected = sorted(expected_games)
    if (result["script_sha256"] != g61.REPLAYER_SHA or
            result["room_id"] != room or result["target_user_id"] != g59.US or
            result["selected_games"] != expected or
            result["outcome_labels_opened"] is not False or
            result["other_hidden_hand_perturbation_passed"] is not True):
        raise ValueError("G66 R18 房、源码或信息权限漂移")
    windows_path = directory(room) / "windows.json"
    windows = json.loads(windows_path.read_text(encoding="utf-8"))["windows"]
    if len(windows) != result["counts"].get("legal_verified_windows"):
        raise ValueError("G66 逐窗数量与房级结果不符")
    return {"result_sha256": sha(path), "windows_sha256": sha(windows_path),
            "counts": result["counts"], "failures": result["failures"]}


def main() -> None:
    """保存先验房清单、全量错误账和可断点复用的逐房结果。"""

    if sha(_project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py")) != g61.REPLAYER_SHA:
        raise ValueError("G66 G05 冻结重建器源码改变")
    g60_path, g61_path = _project_file(_PROJECT_ROOT, G60 / "manifest.json"), _project_file(_PROJECT_ROOT, G61 / "manifest.json")
    g60 = json.loads(g60_path.read_text(encoding="utf-8"))
    g61_manifest = json.loads(g61_path.read_text(encoding="utf-8"))
    g65_result = json.loads((_project_file(_PROJECT_ROOT, G65 / "result.json")).read_text(encoding="utf-8"))
    if (g65_result["schema"] != "g65-next-draw-survival-result/1" or
            g60["complete_rooms"] != 188):
        raise ValueError("G66 G65 训练或 G60 房基线漂移")
    rooms = choose_rooms(g60, g61_manifest)
    manifest = {"schema": "g66-survival-transfer-manifest/1",
                "policy_version": g60["policy_version"],
                "release_package_id": g60["release_package_id"],
                "selected_rooms": rooms,
                "selected_games": {room: g60["included"][room] for room in rooms},
                "source_sha256": {"g60_manifest": sha(g60_path),
                                  "g61_manifest": sha(g61_path),
                                  "g65_result": sha(_project_file(_PROJECT_ROOT, G65 / "result.json")),
                                  "g05_replayer": sha(_project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py")),
                                  "g66_prereg": sha(_project_file(_PROJECT_ROOT, HERE / "G66-SURVIVAL-TRANSFER-PREREG-2026-09-28.md")),
                                  "g66_script": sha(Path(__file__))}}
    g61.write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    pending = [room for room in rooms if not (directory(room) / "result.json").exists()]
    errors = {}
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as workers:
            futures = {workers.submit(run_room, room): room for room in pending}
            for future in concurrent.futures.as_completed(futures):
                room = futures[future]
                try:
                    future.result()
                    checked = verify(room, g60["included"][room])
                    print(json.dumps({"room": room,
                                      "legal_windows": checked["counts"]["legal_verified_windows"],
                                      "analysis_failures": checked["counts"].get("analysis_failures", 0)},
                                     ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    errors[room] = type(exc).__name__ + ": " + str(exc)[:300]
                    print(json.dumps({"room": room, "error": errors[room]},
                                     ensure_ascii=False), flush=True)
    records = {}
    for room in rooms:
        if room in errors:
            continue
        try:
            records[room] = verify(room, g60["included"][room])
        except Exception as exc:  # noqa: BLE001
            errors[room] = type(exc).__name__ + ": " + str(exc)[:300]
    totals = Counter()
    for record in records.values():
        totals.update(record["counts"])
    result = {"schema": "g66-survival-transfer-batch/1",
              "manifest_sha256": sha(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
              "selected_rooms": len(rooms), "completed_rooms": len(records),
              "rooms": records, "errors": dict(sorted(errors.items())),
              "totals": dict(sorted(totals.items())),
              "boundary": "固定 40 房，不按成绩或重建成败替换；G05 正常摸打限定子集，未来事件尚未用作标签。"}
    g61.write_new(_project_file(_PROJECT_ROOT, OUT / "batch_result.json"), result)
    print(json.dumps({"completed_rooms": len(records), "errors": errors,
                      "totals": result["totals"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
