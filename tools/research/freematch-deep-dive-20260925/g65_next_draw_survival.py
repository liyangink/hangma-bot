#!/usr/bin/env python3
"""G65：强手弃牌后能否再次本人摸牌，按房留出的公开信息预测。"""

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

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from extract_room_scores import load_rooms
import g61_strong_draw_batch as g61


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G60 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g65-next-draw-survival-20260928')
BASE = ("wall", "wall_sq", "round_no", "own_discards", "dealer", "own_melds", "whites")
EXTRA = ("opponent_meld_sum", "opponent_meld_max", "opponent_discard_sum",
         "opponent_discard_max", "opponent_hand_min", "catch_play", "score_gap_to_max")
LAMBDA = 0.01


def sha(path: Path) -> str:
    """冻结输入与程序摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def fold(room: str) -> int:
    """按整个官方房分折，同房两位强手不会泄漏到训练。"""

    return int(hashlib.sha256(room.encode("utf-8")).hexdigest()[:12], 16) % 5


def features(observation: dict) -> dict[str, float]:
    """只取本座依法可见的当前状态；不访问赛后事件。"""

    seat = observation["seat"]
    if type(seat) is not int or seat not in range(4):
        raise ValueError("G65 当前观察座位无效")
    discards, melds = observation["discards"], observation["melds"]
    hand_counts, scores = observation["hand_counts"], observation["scores"]
    if (any(len(value) != 4 for value in (discards, melds, hand_counts, scores)) or
            type(observation["remaining_tile_count"]) is not int):
        raise ValueError("G65 公开观察向量缺失")
    others = [index for index in range(4) if index != seat]
    wall = observation["remaining_tile_count"]
    if not 0 <= wall <= 136 or any(type(value) is not int for value in hand_counts + scores):
        raise ValueError("G65 墙余、手牌张数或桌内积分非法")
    opponent_melds = [len(melds[index]) for index in others]
    opponent_discards = [len(discards[index]) for index in others]
    return {"wall": float(wall), "wall_sq": float(wall * wall),
            "round_no": float(observation["round_no"]),
            "own_discards": float(len(discards[seat])),
            "dealer": float(seat == observation["dealer_seat"]),
            "own_melds": float(len(melds[seat])),
            "whites": float(observation["my_hand"].count("白")),
            "opponent_meld_sum": float(sum(opponent_melds)),
            "opponent_meld_max": float(max(opponent_melds)),
            "opponent_discard_sum": float(sum(opponent_discards)),
            "opponent_discard_max": float(max(opponent_discards)),
            "opponent_hand_min": float(min(hand_counts[index] for index in others)),
            "catch_play": float(bool(observation["rule_state"]["catch_play"])),
            "score_gap_to_max": float(scores[seat] - max(scores))}


def event_index(doc: dict) -> dict[int, list[dict]]:
    """按单局串联官方事件，要求 seq 严格递增且终局唯一。"""

    by_round = defaultdict(list)
    for block in doc.get("blocks") or []:
        by_round[block["round_no"]].extend(block.get("events") or [])
    if len(by_round) != 8:
        raise ValueError("G65 官方完整桌不是八个单局")
    for round_no, events in by_round.items():
        seqs = [item.get("seq") for item in events]
        if (any(type(item) is not int for item in seqs) or
                seqs != sorted(set(seqs)) or
                sum(item.get("type") == "round_ended" for item in events) != 1):
            raise ValueError(f"G65 官方单局事件 seq 或终局不完整：{round_no}")
    return by_round


def label(window: dict, events: list[dict], positions: dict[int, int]) -> dict:
    """当前弃牌后至终局前是否再次本人摸牌；未来仅用于标签。"""

    seq, seat, action = window["draw_seq"], window["seat"], window["actual_action"]
    position = positions.get(seq)
    if position is None or events[position].get("type") != "tile_drawn" or events[position].get("seat") != seat:
        raise ValueError("G65 当前本人摸牌事件未对齐")
    skip = {"pass", "timeout"}
    for index in range(position + 1, len(events)):
        event = events[index]
        if event.get("type") in skip:
            continue
        if (event.get("type") != "tile_discarded" or event.get("seat") != seat or
                action != "discard:" + str(event.get("tile"))):
            raise ValueError("G65 当前摸后首个实质事件不是 G61 已核弃牌")
        position = index
        break
    else:
        raise ValueError("G65 当前摸牌没有后继弃牌")
    for event in events[position + 1:]:
        if event.get("type") == "tile_drawn" and event.get("seat") == seat:
            return {"next_own_draw": 1, "terminal_kind": "next_own_draw",
                    "next_seq": event["seq"]}
        if event.get("type") == "round_ended":
            data = event.get("data") or {}
            if data.get("draw"):
                kind = "wall_draw"
            elif event.get("seat") == seat:
                kind = "own_win_without_draw"
            else:
                kind = "other_win"
            return {"next_own_draw": 0, "terminal_kind": kind,
                    "next_seq": event["seq"]}
    raise ValueError("G65 当前弃牌后未出现下一摸或单局终局")


def design(rows: list[dict], keys: tuple[str, ...]) -> np.ndarray:
    """固定列序构造数值输入，不把房号或 label 拼入矩阵。"""

    return np.asarray([[row["features"][key] for key in keys] for row in rows], dtype=float)


def fit_predict(train_x: np.ndarray, train_y: np.ndarray,
                test_x: np.ndarray) -> np.ndarray:
    """固定 λ 的岭逻辑回归牛顿迭代，标准化只用训练房。"""

    mu = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    x = np.column_stack((np.ones(len(train_x)), (train_x - mu) / scale))
    future = np.column_stack((np.ones(len(test_x)), (test_x - mu) / scale))
    weights = np.zeros(x.shape[1])
    penalty = np.eye(x.shape[1]) * LAMBDA
    penalty[0, 0] = 0.0
    for _ in range(30):
        prob = 1.0 / (1.0 + np.exp(-np.clip(x @ weights, -30, 30)))
        grad = x.T @ (prob - train_y) / len(train_y) + penalty @ weights
        variance = prob * (1.0 - prob)
        hessian = x.T @ (x * variance[:, None]) / len(train_y) + penalty
        step = np.linalg.solve(hessian, grad)
        weights -= step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    prediction = 1.0 / (1.0 + np.exp(-np.clip(future @ weights, -30, 30)))
    return np.clip(prediction, 1e-6, 1.0 - 1e-6)


def metrics(rows: list[dict], name: str) -> dict:
    """可重复计算的逐窗 Brier、对数损失与校准十分位。"""

    y = np.asarray([row["label"] for row in rows], dtype=float)
    p = np.asarray([row["prediction"][name] for row in rows], dtype=float)
    loss = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    order = np.argsort(p, kind="stable")
    bins = []
    for indices in np.array_split(order, 10):
        bins.append({"n": len(indices), "predicted": float(p[indices].mean()),
                     "observed": float(y[indices].mean())})
    return {"n": len(rows), "event_rate": float(y.mean()),
            "brier": float(np.mean((p - y) ** 2)),
            "logloss": float(loss.mean()), "calibration_deciles": bins}


def main() -> None:
    """从 G61 当前观察建特征，从官方后续事件打标签并房级交叉留出。"""

    if OUT.exists():
        raise SystemExit("G65 结果目录已存在，拒绝覆盖")
    g61_result_path, g60_manifest_path = _project_file(_PROJECT_ROOT, SOURCE / "result.json"), _project_file(_PROJECT_ROOT, G60 / "manifest.json")
    g61_result = json.loads(g61_result_path.read_text(encoding="utf-8"))
    g60_manifest = json.loads(g60_manifest_path.read_text(encoding="utf-8"))
    if (g61_result["outcome_labels_opened"] is not False or
            g61_result["totals"]["legal_verified_windows"] != 17_938 or
            g60_manifest["release_package_id"] != "e82f904c2c1fb70beea3f195110c8b2db0648971ed3eaa9bfcbed1b6543de486"):
        raise ValueError("G65 来源图谱或发布包漂移")
    rooms = {unit.split("/", 1)[1] for unit in g61_result["units"]}
    if len(rooms) != 31:
        raise ValueError("G65 唯一房数量漂移")
    docs = {room: {} for room in rooms}
    for _mtime, room, _tag, gid, doc in load_rooms():
        if room in docs and gid in g60_manifest["included"][room]:
            if gid in docs[room]:
                raise ValueError("G65 官方完整桌重复")
            docs[room][gid] = doc
    if any(set(by_gid) != set(g60_manifest["included"][room]) for room, by_gid in docs.items()):
        raise ValueError("G65 官方完整房牌谱缺失")
    indexed = {(room, gid): event_index(doc) for room, by_gid in docs.items()
               for gid, doc in by_gid.items()}
    positions = {(room, gid, round_no): {event["seq"]: index for index, event in enumerate(events)}
                 for (room, gid), rounds in indexed.items()
                 for round_no, events in rounds.items()}
    manifest = {"schema": "g65-next-draw-survival-manifest/1",
                "source_sha256": {"g61_result": sha(g61_result_path),
                                  "g60_manifest": sha(g60_manifest_path),
                                  "g65_prereg": sha(_project_file(_PROJECT_ROOT, HERE / "G65-NEXT-DRAW-SURVIVAL-PREREG-2026-09-28.md")),
                                  "g65_script": sha(Path(__file__))},
                "units": sorted(g61_result["units"]),
                "unique_rooms": sorted(rooms), "folds": {room: fold(room) for room in sorted(rooms)},
                "base_features": BASE, "extra_features": EXTRA,
                "ridge_lambda": LAMBDA, "outcome_label": "next_own_tile_drawn_before_round_ended"}
    rows = []
    counts = Counter()
    for unit, record in sorted(g61_result["units"].items()):
        peer, room = unit.split("/", 1)
        path = _project_file(_PROJECT_ROOT, SOURCE / "rooms" / (peer + "--" + room) / "windows.json")
        if sha(path) != record["windows_sha256"]:
            raise ValueError("G65 G61 逐窗证据漂移")
        windows = json.loads(path.read_text(encoding="utf-8"))["windows"]
        for window in windows:
            gid, round_no = window["game_id"], window["round_no"]
            events = indexed[(room, gid)][round_no]
            observed = label(window, events, positions[(room, gid, round_no)])
            if observed["terminal_kind"] == "own_win_without_draw":
                raise ValueError("G65 本人未再次摸牌却自摸胡，需单独审查")
            row = {"peer": peer, "room": room, "game_id": gid,
                   "round_no": round_no, "draw_seq": window["draw_seq"],
                   "seat": window["seat"], "features": features(window["observation"]),
                   "label": observed["next_own_draw"],
                   "terminal_kind": observed["terminal_kind"],
                   "next_seq": observed["next_seq"], "fold": fold(room)}
            rows.append(row)
            counts[observed["terminal_kind"]] += 1
    if len(rows) != 17_938 or counts.total() != len(rows):
        raise ValueError("G65 合法窗口未全部贴标签")
    labels = np.asarray([row["label"] for row in rows], dtype=float)
    folds = np.asarray([row["fold"] for row in rows], dtype=int)
    predictions = {name: np.full(len(rows), np.nan)
                   for name in ("base", "enhanced")}
    fold_counts = Counter(int(value) for value in folds)
    if len(fold_counts) != 5 or min(fold_counts.values()) < 100:
        raise ValueError("G65 房级五折覆盖不足")
    for name, keys in (("base", BASE), ("enhanced", BASE + EXTRA)):
        matrix = design(rows, keys)
        for heldout in range(5):
            train, test = folds != heldout, folds == heldout
            predictions[name][test] = fit_predict(matrix[train], labels[train], matrix[test])
        if not np.all(np.isfinite(predictions[name])):
            raise ValueError("G65 留出预测缺失")
    for index, row in enumerate(rows):
        row["prediction"] = {name: float(values[index]) for name, values in predictions.items()}
    subsets = {"all": rows}
    subsets.update({peer: [row for row in rows if row["peer"] == peer]
                    for peer in g61.PEERS})
    scores = {group: {name: metrics(sample, name) for name in predictions}
              for group, sample in subsets.items()}
    room_delta = {}
    for peer in g61.PEERS:
        room_delta[peer] = {}
        for room in sorted({row["room"] for row in subsets[peer]}):
            sample = [row for row in subsets[peer] if row["room"] == room]
            old, new = metrics(sample, "base"), metrics(sample, "enhanced")
            room_delta[peer][room] = {"n": len(sample),
                                       "brier_gain": old["brier"] - new["brier"],
                                       "logloss_gain": old["logloss"] - new["logloss"]}
    review = {peer: {"rooms": len(values),
                     "brier_positive_rooms": sum(item["brier_gain"] > 0 for item in values.values()),
                     "logloss_positive_rooms": sum(item["logloss_gain"] > 0 for item in values.values()),
                     "brier_gain": scores[peer]["base"]["brier"] - scores[peer]["enhanced"]["brier"],
                     "logloss_gain": scores[peer]["base"]["logloss"] - scores[peer]["enhanced"]["logloss"]}
              for peer, values in room_delta.items()}
    manifest_body = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    OUT.mkdir(parents=True)
    with (_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")).open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    result = {"schema": "g65-next-draw-survival-result/1",
              "manifest_sha256": hashlib.sha256(manifest_body.encode("utf-8")).hexdigest(),
              "rows_sha256": sha(_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")),
              "counts": dict(sorted(counts.items())), "fold_counts": dict(sorted(fold_counts.items())),
              "scores": scores, "room_delta": room_delta, "review": review,
              "boundary": "强手本人真实弃牌轨迹的下一摸标签，非动作反事实；公开事实房级留出，未验证我方迁移或整桌收益。"}
    (_project_file(_PROJECT_ROOT, OUT / "manifest.json")).write_text(manifest_body, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"rows": len(rows), "counts": result["counts"],
                      "fold_counts": result["fold_counts"], "review": review},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
