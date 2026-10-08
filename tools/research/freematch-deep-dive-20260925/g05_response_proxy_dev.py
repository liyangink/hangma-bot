#!/usr/bin/env python3
"""房级留一评估两种有限鸣/过代理；只评行为吻合，不评赛事收益。"""

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
from fractions import Fraction
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-response-dev-behavior-01/windows.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-response-proxy-dev-01')
ROOMS = (
    "a_f8ddc4c3bd9b", "a_d773a8e428a0",
    "a_852fb97c102e", "a_2a8aa14dc8a1",
)
A_THRESHOLDS = (-12, -9, -6, -3, 0, 3, 6, 9, 12)
B_THRESHOLDS = (-9, -6, -3, 0, 3, 6, 9)
CONDITIONS = ("dealer", "white", "meld", "late", "baotou")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def condition(row: dict, name: str) -> bool:
    """仅从当时玩家可见的公开/自身字段计算单个布尔条件。"""
    return {
        "dealer": bool(row["dealer"]),
        "white": row["white_count"] >= 1,
        "meld": row["own_meld_count"] >= 1,
        "late": row["wall_remaining"] < 40,
        "baotou": bool(row["baotou"]),
    }[name]


def predict(row: dict, arm: str, params: tuple) -> bool:
    """A 为单阈值，B 为一个条件切分的双阈值。"""
    if arm == "A":
        threshold = params[0]
    else:
        name, t0, t1 = params
        threshold = t1 if condition(row, name) else t0
    return row["parent_margin"] > threshold


def candidates(arm: str) -> list[tuple]:
    if arm == "A":
        return [(t,) for t in A_THRESHOLDS]
    return [(name, t0, t1) for name in CONDITIONS
            for t0 in B_THRESHOLDS for t1 in B_THRESHOLDS]


def room_accuracy(rows: list[dict], arm: str, params: tuple) -> Fraction:
    """房内准确率；比较参数时每房等权，避免较长桌赛主导。"""
    return Fraction(sum(predict(row, arm, params) == row["actual_claim"]
                        for row in rows), len(rows))


def preference(arm: str, params: tuple, index: int) -> tuple:
    """同分优先无额外条件、距父代零阈值近、冻结候选序在前。"""
    if arm == "A":
        return (-abs(params[0]), -index)
    _, t0, t1 = params
    return (-int(t0 != t1), -(abs(t0) + abs(t1)), -index)


def select(rows_by_room: dict[str, list[dict]], arm: str) -> tuple:
    """仅用传入训练房挑参；不读取该折测试房。"""
    choices = candidates(arm)
    return max(enumerate(choices), key=lambda pair: (
        sum((room_accuracy(rows, arm, pair[1]) for rows in rows_by_room.values()),
            Fraction()),
        preference(arm, pair[1], pair[0]),
    ))[1]


def main() -> None:
    if OUT.exists():
        raise FileExistsError("开发代理结果目录已有文件，拒绝覆盖")
    rows = json.loads(SOURCE.read_text(encoding="utf-8"))["windows"]
    by_room = {room: [row for row in rows if row["room_id"] == room] for room in ROOMS}
    if sum(map(len, by_room.values())) != len(rows) or any(not value for value in by_room.values()):
        raise ValueError("房级分割与来源不一致")
    folds = {}
    predictions = []
    for room in ROOMS:
        train = {name: value for name, value in by_room.items() if name != room}
        params_a = select(train, "A")
        params_b = select(train, "B")
        count = Counter()
        for row in by_room[room]:
            actual = row["actual_claim"]
            parent = row["parent_claim"]
            if parent != (row["parent_margin"] > 0):
                raise ValueError("冻结父代预测与 margin 不一致")
            a = predict(row, "A", params_a)
            b = predict(row, "B", params_b)
            count["windows"] += 1
            count["parent_correct"] += parent == actual
            count["A_correct"] += a == actual
            count["B_correct"] += b == actual
            for arm, choice in (("A", a), ("B", b)):
                count[arm + "_corrected"] += parent != actual and choice == actual
                count[arm + "_new_errors"] += parent == actual and choice != actual
            predictions.append({
                "room_id": room, "game_id": row["game_id"],
                "round_no": row["round_no"], "discard_seq": row["discard_seq"],
                "actual_claim": actual, "parent_claim": parent,
                "A_claim": a, "B_claim": b,
            })
        folds[room] = {"A_params": list(params_a), "B_params": list(params_b),
                       "counts": dict(sorted(count.items()))}
    total = Counter()
    for fold in folds.values():
        total.update(fold["counts"])
    gates = {}
    for arm in ("A", "B"):
        gains = [fold["counts"][arm + "_correct"] - fold["counts"]["parent_correct"]
                 for fold in folds.values()]
        gates[arm] = {"total_gain_windows": sum(gains),
                      "rooms_nonnegative": sum(value >= 0 for value in gains),
                      "development_gate_passed": sum(gains) > 0
                      and sum(value >= 0 for value in gains) >= 3}
    result = {
        "schema": "g05-response-proxy-dev/1",
        "source_sha256": digest(SOURCE), "script_sha256": digest(Path(__file__)),
        "folds": folds, "total_counts": dict(sorted(total.items())),
        "development_gates": gates,
        "full_dev_fit": {arm: list(select(by_room, arm)) for arm in ("A", "B")},
        "no_outcome_value_used_as_action_quality_label": True,
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (_project_file(_PROJECT_ROOT, OUT / "predictions.json")).write_text(
        json.dumps({"schema": "g05-response-proxy-dev-predictions/1",
                    "predictions": predictions}, ensure_ascii=False,
                   sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total_counts": result["total_counts"],
                      "development_gates": gates}, ensure_ascii=False))


if __name__ == "__main__":
    main()
