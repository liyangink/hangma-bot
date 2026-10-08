#!/usr/bin/env python3
"""G61：在已冻结同桌房批量运行 G05 公开摸打重建器，先不读结算标签。"""

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
import hashlib
import json
from pathlib import Path

import g05_strong_draw_reconstruction as replay


HERE = Path(__file__).resolve().parent
G60 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
PEERS = {"xuanwu_2346": "u_380da525337c", "tengshe_0638": "u_b2aa6abe7811"}
REPLAYER_SHA = "dd25efa11f95a53f81e195c7811db54f5c24595f7ca823180e6bc75f3ed6f78e"


def sha(path: Path) -> str:
    """本地输入摘要，用于防止规则重放和房间选择静默漂移。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, payload: dict) -> None:
    """已有批次清单必须逐字一致，不覆盖他人或先前实验。"""

    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != body:
            raise ValueError(f"G61 冻结内容漂移：{path}")
        return
    path.write_text(body, encoding="utf-8")


def room_dir(unit: tuple[str, str]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rooms" / (unit[0] + "--" + unit[1]))


def run_unit(unit: tuple[str, str]) -> tuple[str, str, dict]:
    """每个强手本人座位在隔离结果目录重放完整十张官方桌。"""

    peer, room = unit
    replay.run(room, 10, PEERS[peer], room_dir(unit))
    doc = json.loads((room_dir(unit) / "result.json").read_text(encoding="utf-8"))
    return peer, room, doc


def verify(unit: tuple[str, str]) -> dict:
    """断点恢复前核对来源、强手身份、十张桌及结果盲边界。"""

    peer, room = unit
    path = room_dir(unit) / "result.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    if (doc.get("room_id") != room or doc.get("target_user_id") != PEERS[peer] or
            doc.get("script_sha256") != REPLAYER_SHA or
            len(doc.get("selected_games") or []) != 10 or
            doc.get("outcome_labels_opened") is not False):
        raise ValueError(f"G61 房间结果身份或结果盲边界不符：{unit}")
    windows_path = room_dir(unit) / "windows.json"
    windows = json.loads(windows_path.read_text(encoding="utf-8"))["windows"]
    counts = doc.get("counts") or {}
    if len(windows) != counts.get("legal_verified_windows"):
        raise ValueError(f"G61 逐窗与汇总数量不符：{unit}")
    if any(row.get("room_id") != room for row in windows):
        raise ValueError(f"G61 混入其他房的动作窗：{unit}")
    return {"result_sha256": sha(path), "windows_sha256": sha(windows_path),
            "counts": counts,
            "parent_agreement": doc.get("parent_agreement"),
            "parent_disagreement": doc.get("parent_disagreement")}


def main() -> None:
    """先冻结全量房间，再以至多两个进程并行重建，保留每房失败。"""

    if sha(_project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py")) != REPLAYER_SHA:
        raise ValueError("G61 冻结 G05 重建器源码变化")
    g60 = json.loads((_project_file(_PROJECT_ROOT, G60 / "result.json")).read_text(encoding="utf-8"))
    base_manifest = json.loads((_project_file(_PROJECT_ROOT, G60 / "manifest.json")).read_text(encoding="utf-8"))
    units = sorted((peer, key.removesuffix("/" + peer))
                   for peer in PEERS
                   for key in g60["room_rows"] if key.endswith("/" + peer))
    if len(units) != 32 or Counter(peer for peer, _ in units) != {
            "xuanwu_2346": 15, "tengshe_0638": 17}:
        raise ValueError("G61 强手房数与预登记不符")
    if any(room not in base_manifest["included"] for _, room in units):
        raise ValueError("G61 混入 G60 未完整归档房")
    frozen = {
        "schema": "g61-strong-draw-action-atlas-manifest/1",
        "boundary": "只重建强手本人动作前可见事实，不打开动作后分数；已看 G05 两房单列。",
        "units": [{"peer": peer, "room": room, "target_user_id": PEERS[peer]}
                  for peer, room in units],
        "g60_manifest_sha256": sha(_project_file(_PROJECT_ROOT, G60 / "manifest.json")),
        "g60_result_sha256": sha(_project_file(_PROJECT_ROOT, G60 / "result.json")),
        "inputs_sha256": {path.name: sha(path) for path in (
            _project_file(_PROJECT_ROOT, HERE / "G61-STRONG-DRAW-ACTION-ATLAS-PREREG-2026-09-27.md"),
            _project_file(_PROJECT_ROOT, HERE / "g61_strong_draw_batch.py"),
            _project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py"))},
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), frozen)
    pending = []
    for unit in units:
        if (room_dir(unit) / "result.json").exists():
            verify(unit)
        else:
            pending.append(unit)
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=2) as workers:
            futures = {workers.submit(run_unit, unit): unit for unit in pending}
            for future in concurrent.futures.as_completed(futures):
                unit = futures[future]
                _peer, _room, doc = future.result()
                check = verify(unit)
                print(json.dumps({"completed": list(unit),
                                  "clean_windows": check["counts"].get("clean_windows"),
                                  "analysis_failures": check["counts"].get("analysis_failures", 0),
                                  "parent_disagreement": doc["parent_disagreement"]},
                                 ensure_ascii=False), flush=True)
    records = {peer + "/" + room: verify((peer, room)) for peer, room in units}
    totals = Counter()
    for record in records.values():
        totals.update(record["counts"])
        totals["parent_agreement"] += record["parent_agreement"]
        totals["parent_disagreement"] += record["parent_disagreement"]
    result = {"schema": "g61-strong-draw-action-atlas-batch/1",
              "manifest_sha256": sha(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
              "script_sha256": sha(Path(__file__)),
              "units": records, "totals": dict(sorted(totals.items())),
              "outcome_labels_opened": False,
              "boundary": "正常摸打限定子集；强手行为差异不等于净收益或可上线候选。"}
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"units": len(records), "totals": result["totals"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
