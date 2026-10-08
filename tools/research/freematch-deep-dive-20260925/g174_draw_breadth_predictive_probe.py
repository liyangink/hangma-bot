#!/usr/bin/env python3
"""G174：冻结官方已接受摸打的连续下一摸，检验码数的额外预测值。"""

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
import hashlib
import json
from pathlib import Path

import numpy as np

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G174-DRAW-BREADTH-PREDICTIVE-PROBE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g174-draw-breadth-predictive-probe-20260928/result.json')
BOOTSTRAP_SEED = 20261228174
L2 = 1.0


def sha(path: Path) -> str:
    """冻结文件原始字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bucket(value: int) -> int:
    """白板数 0/1/2+；向听单独按 0/1/2/3+。"""
    return min(value, 2)


def _features(row: dict, capacity: int, types: int) -> tuple[float, ...]:
    """首窗全部是行动前可见事实；固定缩放不依赖留出房。"""
    c = capacity / 40.0
    wall = row["wall_remaining"] / 80.0
    shanten = min(row["standard"], 3)
    whites = _bucket(row["white_count"])
    return (1.0, c, c*c, wall, wall*wall,
            *(float(shanten == index) for index in (0, 1, 2)),
            *(float(whites == index) for index in (0, 1)),
            row["own_melds"] / 4.0, types / 10.0)


def _pairs(rows: list[dict]) -> tuple[list[dict], dict]:
    """与 G11 相同的机械连续条件，不将他家截尾当零命中。"""
    by_hand = defaultdict(list)
    counts = Counter()
    for row in rows:
        by_hand[(row["game_id"], row["round_no"], row["seat"])].append(row)
    samples = []
    for sequence in by_hand.values():
        sequence.sort(key=lambda row: row["trigger_seq"])
        for prior, next_row in zip(sequence, sequence[1:]):
            counts["consecutive_normal_draw_pairs"] += 1
            if prior["own_melds"] != next_row["own_melds"]:
                counts["meld_changed"] += 1
                continue
            if prior["after"] != next_row["before"]:
                counts["hand_not_continuous"] += 1
                continue
            counts["mechanically_continuous"] += 1
            facts = prior["legal"][prior["parent_action"]]
            entries = facts.get("standard_useful_tiles")
            if entries is None or not isinstance(entries, list):
                counts["standard_vector_unknown"] += 1
                continue
            if (type(prior["standard"]) is not int or prior["standard"] < 0
                    or type(prior["wall_remaining"]) is not int
                    or prior["wall_remaining"] < 0):
                counts["context_unknown"] += 1
                continue
            vector = {}
            for item in entries:
                code, amount = item.get("code"), item.get("remaining_estimate")
                if (not isinstance(code, str) or code in vector
                        or type(amount) is not int or not 0 <= amount <= 4):
                    raise ValueError("G174 生产普通进张向量非法或重复")
                vector[code] = amount
            capacity = sum(vector.values())
            types = sum(value > 0 for value in vector.values())
            if capacity == 0:
                counts["zero_capacity"] += 1
                continue
            hit = int(vector.get(next_row["drawn_tile"], 0) > 0)
            holdout = (int.from_bytes(hashlib.sha256(
                ("g174-holdout|" + prior["room_id"]).encode("utf-8")
            ).digest(), "big") % 5 == 0)
            samples.append({"room_id": prior["room_id"], "game_id": prior["game_id"],
                            "round_no": prior["round_no"], "seat": prior["seat"],
                            "trigger_seq": prior["trigger_seq"],
                            "white_bucket": _bucket(prior["white_count"]),
                            "standard_shanten": prior["standard"],
                            "capacity": capacity, "types": types,
                            "hit": hit, "holdout": holdout,
                            "features": _features(prior, capacity, types)})
    counts["samples"] = len(samples)
    return samples, dict(sorted(counts.items()))


def _fit(matrix: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """确定性 Newton 法；固定 L2，不用留出结果选择模型。"""
    beta = np.zeros(matrix.shape[1])
    ridge = np.eye(matrix.shape[1]) * L2
    ridge[0, 0] = 0.0
    for _ in range(50):
        linear = np.clip(matrix @ beta, -35, 35)
        probability = 1 / (1 + np.exp(-linear))
        gradient = matrix.T @ (probability - targets) + ridge @ beta
        weight = probability * (1 - probability)
        hessian = matrix.T @ (matrix * weight[:, None]) + ridge
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    if not np.isfinite(beta).all():
        raise ValueError("G174 逻辑回归未产生有限系数")
    return beta


def _prediction(matrix: np.ndarray, beta: np.ndarray) -> np.ndarray:
    """限制在开区间，确保对数损失有限。"""
    linear = np.clip(matrix @ beta, -35, 35)
    return np.clip(1 / (1 + np.exp(-linear)), 1e-12, 1 - 1e-12)


def _metrics(samples: list[dict]) -> dict:
    """完全留出房报告基础式与码数扩展式的逐窗预测。"""
    train = [item for item in samples if not item["holdout"]]
    test = [item for item in samples if item["holdout"]]
    if not train or not test:
        raise ValueError("G174 房间拆分后训练或留出为空")
    x_train = np.asarray([item["features"] for item in train], dtype=float)
    x_test = np.asarray([item["features"] for item in test], dtype=float)
    y_train = np.asarray([item["hit"] for item in train], dtype=float)
    y_test = np.asarray([item["hit"] for item in test], dtype=float)
    base = _fit(x_train[:, :-1], y_train)
    extended = _fit(x_train, y_train)
    p_base = _prediction(x_test[:, :-1], base)
    p_extended = _prediction(x_test, extended)
    base_loss = -(y_test*np.log(p_base) + (1-y_test)*np.log(1-p_base))
    extended_loss = -(y_test*np.log(p_extended) + (1-y_test)*np.log(1-p_extended))
    base_brier = (p_base-y_test)**2
    extended_brier = (p_extended-y_test)**2
    rooms = sorted({item["room_id"] for item in test})
    by_room = {room: np.asarray([i for i, item in enumerate(test)
                                 if item["room_id"] == room], dtype=int)
               for room in rooms}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    gains = []
    difference = base_loss - extended_loss
    for _ in range(2000):
        sampled = rng.choice(rooms, size=len(rooms), replace=True)
        indices = np.concatenate([by_room[room] for room in sampled])
        gains.append(float(np.mean(difference[indices])))
    by_white = {}
    for bucket in (0, 1, 2):
        indices = np.asarray([i for i, item in enumerate(test)
                              if item["white_bucket"] == bucket], dtype=int)
        by_white[str(bucket)] = {
            "windows": len(indices),
            "hit_rate": None if not len(indices) else float(np.mean(y_test[indices])),
            "mean_logloss_gain_base_minus_extended": None if not len(indices)
            else float(np.mean(difference[indices])),
        }
    gain = float(np.mean(difference))
    low, high = np.quantile(gains, [0.025, 0.975])
    return {
        "train_windows": len(train), "holdout_windows": len(test),
        "train_rooms": len({item["room_id"] for item in train}),
        "holdout_rooms": len(rooms),
        "train_hit_rate": float(np.mean(y_train)),
        "holdout_hit_rate": float(np.mean(y_test)),
        "base_coefficients": base.tolist(),
        "extended_coefficients": extended.tolist(),
        "types_coefficient": float(extended[-1]),
        "base_holdout_logloss": float(np.mean(base_loss)),
        "extended_holdout_logloss": float(np.mean(extended_loss)),
        "mean_logloss_gain_base_minus_extended": gain,
        "holdout_room_bootstrap_95": [float(low), float(high)],
        "base_holdout_brier": float(np.mean(base_brier)),
        "extended_holdout_brier": float(np.mean(extended_brier)),
        "by_white": by_white,
        "predictive_gate_pass": bool(extended[-1] > 0 and gain >= 0.001 and low > 0),
    }


def main() -> None:
    """冻结公开父代轨迹、机械连续抽样及房间留出后一次写结果。"""
    if OUT.exists():
        raise FileExistsError("G174 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("G174 冻结完整桌母体漂移")
    rows, coverage = g11._draw_rows(complete, frozen)
    samples, pair_counts = _pairs(rows)
    if pair_counts["mechanically_continuous"] != 41980:
        raise ValueError("G174 与 G11 机械连续窗口母体漂移")
    payload = {
        "schema": "g174-draw-breadth-predictive-probe/1",
        "input_sha256": {name: sha(path) for name, path in {
            "prereg": PREREG, "script": Path(__file__),
            "frozen_rooms": atlas.FROZEN,
            "g11_result": g11.OUT,
        }.items()},
        "complete_official_tables": len(complete),
        "source_accepted_draw_discards": coverage["accepted_normal_draw_discards"],
        "pair_counts": pair_counts,
        "model": _metrics(samples),
        "boundary": "仅实际到达下一本人正常摸牌后的条件命中预测；不可外推合法备选的赛事收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pair_counts": pair_counts, "model": payload["model"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
