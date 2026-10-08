#!/usr/bin/env python3
"""G66：只用 G65 强手房训练截尾模型，外部评估 R18 v2 官方房。"""

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
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from extract_room_scores import load_rooms
import g61_strong_draw_batch as g61
import g65_next_draw_survival as g65


HERE = Path(__file__).resolve().parent
G65 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g65-next-draw-survival-20260928')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g66-survival-transfer-20260928')


def sha(path: Path) -> str:
    """绑定训练、固定房和本轮逐窗结果。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_training() -> list[dict]:
    """训练行仅来自 G65 的强手房，绝不包括 G66 留出房。"""

    result = json.loads((_project_file(_PROJECT_ROOT, G65 / "result.json")).read_text(encoding="utf-8"))
    path = _project_file(_PROJECT_ROOT, G65 / "rows.jsonl.gz")
    if result["rows_sha256"] != sha(path):
        raise ValueError("G66 G65 训练行摘要漂移")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    if len(rows) != 17_938 or len({row["room"] for row in rows}) != 31:
        raise ValueError("G66 强手训练房不完整")
    return rows


def main() -> None:
    """训练/外部房完全隔离，同列序、同 λ，不调任何模型参数。"""

    batch_path, manifest_path = _project_file(_PROJECT_ROOT, OUT / "batch_result.json"), _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    result_path, rows_path = _project_file(_PROJECT_ROOT, OUT / "transfer_result.json"), _project_file(_PROJECT_ROOT, OUT / "transfer_rows.jsonl.gz")
    if result_path.exists() or rows_path.exists():
        raise SystemExit("G66 外部评分已存在，拒绝覆盖")
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (batch["manifest_sha256"] != sha(manifest_path) or
            len(manifest["selected_rooms"]) != 40 or
            batch["selected_rooms"] != 40):
        raise ValueError("G66 固定 40 房清单漂移")
    train_rows = load_training()
    trained_rooms = {row["room"] for row in train_rows}
    if trained_rooms & set(manifest["selected_rooms"]):
        raise ValueError("G66 强手训练房泄漏至 R18 外部房")
    required = set(batch["rooms"])
    docs = {room: {} for room in required}
    for _mtime, room, _tag, gid, doc in load_rooms():
        if room in docs and gid in manifest["selected_games"][room]:
            if gid in docs[room]:
                raise ValueError("G66 官方桌重复")
            docs[room][gid] = doc
    if any(set(by_gid) != set(manifest["selected_games"][room])
           for room, by_gid in docs.items()):
        raise ValueError("G66 已重建房的牌谱缺失")
    indexed = {(room, gid): g65.event_index(doc) for room, by_gid in docs.items()
               for gid, doc in by_gid.items()}
    positions = {(room, gid, round_no): {event["seq"]: index for index, event in enumerate(events)}
                 for (room, gid), rounds in indexed.items()
                 for round_no, events in rounds.items()}
    rows = []
    counts = Counter()
    by_room = Counter()
    for room, record in sorted(batch["rooms"].items()):
        path = _project_file(_PROJECT_ROOT, OUT / "rooms" / room / "windows.json")
        if sha(path) != record["windows_sha256"]:
            raise ValueError("G66 R18 逐窗证据摘要漂移")
        windows = json.loads(path.read_text(encoding="utf-8"))["windows"]
        for window in windows:
            gid, round_no = window["game_id"], window["round_no"]
            observed = g65.label(window, indexed[(room, gid)][round_no],
                                  positions[(room, gid, round_no)])
            if observed["terminal_kind"] == "own_win_without_draw":
                raise ValueError("G66 本人未摸牌却自摸胡，需审查官方时序")
            rows.append({"room": room, "game_id": gid, "round_no": round_no,
                         "draw_seq": window["draw_seq"], "seat": window["seat"],
                         "features": g65.features(window["observation"]),
                         "label": observed["next_own_draw"],
                         "terminal_kind": observed["terminal_kind"],
                         "next_seq": observed["next_seq"]})
            by_room[room] += 1
            counts[observed["terminal_kind"]] += 1
        if by_room[room] != record["counts"]["legal_verified_windows"]:
            raise ValueError("G66 R18 合法窗口与外部标签数量不等")
    if len(rows) != batch["totals"]["legal_verified_windows"]:
        raise ValueError("G66 外部标签窗口漏行")
    labels = np.asarray([row["label"] for row in train_rows], dtype=float)
    predictions = {}
    for name, keys in (("base", g65.BASE), ("enhanced", g65.BASE + g65.EXTRA)):
        predictions[name] = g65.fit_predict(g65.design(train_rows, keys), labels,
                                             g65.design(rows, keys))
    for index, row in enumerate(rows):
        row["prediction"] = {name: float(values[index]) for name, values in predictions.items()}
    scores = {name: g65.metrics(rows, name) for name in predictions}
    room_delta = {}
    for room in manifest["selected_rooms"]:
        if room not in required:
            room_delta[room] = {"error": batch["errors"].get(room, "unknown reconstruction error")}
            continue
        sample = [row for row in rows if row["room"] == room]
        old, new = g65.metrics(sample, "base"), g65.metrics(sample, "enhanced")
        room_delta[room] = {"n": len(sample),
                            "brier_gain": old["brier"] - new["brier"],
                            "logloss_gain": old["logloss"] - new["logloss"]}
    evaluated = [value for value in room_delta.values() if "error" not in value]
    brier_gain = scores["base"]["brier"] - scores["enhanced"]["brier"]
    logloss_gain = scores["base"]["logloss"] - scores["enhanced"]["logloss"]
    positive_rooms = sum(value["brier_gain"] >= 0 for value in evaluated)
    gate = (not batch["errors"] and len(evaluated) == 40 and
            brier_gain > 0 and logloss_gain > 0 and positive_rooms >= 24)
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    result = {"schema": "g66-survival-transfer-result/1",
              "manifest_sha256": sha(manifest_path),
              "batch_sha256": sha(batch_path),
              "g65_training_sha256": sha(_project_file(_PROJECT_ROOT, G65 / "rows.jsonl.gz")),
              "script_sha256": sha(Path(__file__)),
              "rows_sha256": sha(rows_path),
              "selected_rooms": 40, "evaluated_rooms": len(evaluated),
              "window_counts": dict(sorted(counts.items())),
              "scores": scores, "room_delta": room_delta,
              "review": {"brier_gain": brier_gain, "logloss_gain": logloss_gain,
                         "brier_nondecrease_rooms": positive_rooms,
                         "fixed_transfer_gate_passed": gate},
              "boundary": "仅预测 R18 已发生弃牌后的下一本人摸牌；预测改善不是动作特异因果价值或整桌收益。"}
    result_path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"evaluated_rooms": len(evaluated), "windows": len(rows),
                      "counts": result["window_counts"], "review": result["review"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
