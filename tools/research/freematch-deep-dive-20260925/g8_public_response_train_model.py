#!/usr/bin/env python3
"""只在冻结训练房交叉验证公开被鸣概率；未来十房标签保持封存。"""

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

from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927/training-cv.json')
MODEL = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927/frozen-model.json')


def _load() -> tuple[list[dict], dict]:
    """校验训练行摘要与来源房；房号只用于分组，不进入预测特征。"""

    metadata = json.loads(RESULT.read_text(encoding="utf-8"))
    if hashlib.sha256(ROWS.read_bytes()).hexdigest() != metadata["rows_gzip_sha256"]:
        raise ValueError("训练压缩行摘要漂移")
    with gzip.open(ROWS, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    if len(rows) != metadata["counts"]["train_claim"] + metadata["counts"]["train_none"]:
        raise ValueError("训练行数与账本不符")
    if {row["room_id"] for row in rows} != set(metadata["source_rooms"]):
        raise ValueError("房级覆盖不符")
    return rows, metadata


def _feature_names(tiles: list[str]) -> list[str]:
    """显式公开特征顺序；不含游戏/房标识或赛后目标。"""

    return (["intercept"] + [f"tile:{tile}" for tile in tiles] +
            [f"dealer_relative:{value}" for value in range(4)] +
            ["wall_100", "shanten_5", "risk_1p5", "white_4", "own_tile_4",
             "public_tile_4", "catch_play"] +
            [f"river_length_rel{delta}_20" for delta in (1, 2, 3)] +
            [f"meld_length_rel{delta}_4" for delta in (1, 2, 3)] +
            [f"same_tile_river_rel{delta}_4" for delta in (1, 2, 3)])


def _matrix(rows: list[dict], tiles: list[str]) -> tuple[np.ndarray, np.ndarray,
                                                         np.ndarray, list[str]]:
    """动作前可见白名单编码，固定常量缩放，不从验证标签拟合标准化。"""

    names = _feature_names(tiles)
    x = np.zeros((len(rows), len(names)), dtype=np.float64)
    y = np.empty(len(rows), dtype=np.float64)
    risk = np.empty((len(rows), 2), dtype=np.float64)
    tile_index = {tile: index for index, tile in enumerate(tiles)}
    fixed_start = 1 + len(tiles) + 4
    for i, row in enumerate(rows):
        f = row["features"]
        x[i, 0] = 1.0
        if f["tile"] in tile_index:
            x[i, 1 + tile_index[f["tile"]]] = 1.0
        x[i, 1 + len(tiles) + f["dealer_relative"]] = 1.0
        wall = f["wall_remaining"]
        if type(wall) is not int:
            raise ValueError("训练房墙余公开事实缺失")
        values = ([wall / 100, f["shanten_after"] / 5, f["risk_units"] / 1.5,
                   f["white_count"] / 4, f["own_tile_count"] / 4,
                   f["public_tile_count"] / 4, float(f["catch_play"])] +
                  [value / 20 for value in f["river_lengths_relative"]] +
                  [value / 4 for value in f["meld_lengths_relative"]] +
                  [value / 4 for value in f["same_tile_river_relative"]])
        if len(values) != len(names) - fixed_start:
            raise ValueError("公开特征维度不守恒")
        x[i, fixed_start:] = values
        y[i] = row["label_claim"]
        risk[i] = [1.0, f["risk_units"] / 1.5]
    return x, y, risk, names


def _fit_logistic(x: np.ndarray, y: np.ndarray, penalty: float) -> np.ndarray:
    """二元逻辑回归 Newton 求解；只惩罚非截距，数值结果可复算。"""

    beta = np.zeros(x.shape[1], dtype=np.float64)
    rate = float(y.mean())
    beta[0] = math.log(rate / (1 - rate))
    ridge = np.eye(x.shape[1]) * penalty
    ridge[0, 0] = 0.0
    converged = False
    for _ in range(35):
        logits = np.clip(x @ beta, -30, 30)
        prob = 1 / (1 + np.exp(-logits))
        w = np.maximum(prob * (1 - prob), 1e-8)
        gradient = x.T @ (prob - y) + ridge @ beta
        hessian = x.T @ (w[:, None] * x) + ridge
        delta = np.linalg.solve(hessian, gradient)
        beta -= delta
        if np.max(np.abs(delta)) < 1e-7:
            converged = True
            break
    if not converged:
        raise ValueError("逻辑回归在 35 次 Newton 步内未收敛")
    return beta


def _predict(x: np.ndarray, beta: np.ndarray) -> np.ndarray:
    """将分数变成数值安全的概率。"""

    return 1 / (1 + np.exp(-np.clip(x @ beta, -30, 30)))


def _tile_dealer_prior(rows: list[dict], train: np.ndarray,
                       eval_indices: np.ndarray) -> np.ndarray:
    """牌码×相对庄位经验基率，按 20 个训练样本强度向全局率收缩。"""

    all_rate = float(np.mean([rows[int(i)]["label_claim"] for i in train]))
    cells = defaultdict(lambda: [0, 0])
    for index in train:
        row = rows[int(index)]
        key = (row["features"]["tile"], row["features"]["dealer_relative"])
        cells[key][0] += row["label_claim"]
        cells[key][1] += 1
    values = []
    for index in eval_indices:
        f = rows[int(index)]["features"]
        yes, total = cells[(f["tile"], f["dealer_relative"])]
        values.append((yes + 20 * all_rate) / (total + 20))
    return np.array(values, dtype=np.float64)


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    """每房平均 Brier 与 log-loss，避免大房把小房吞没。"""

    safe = np.clip(p, 1e-9, 1 - 1e-9)
    return {"brier": float(np.mean((p - y) ** 2)),
            "log_loss": float(np.mean(-y * np.log(safe) - (1 - y) * np.log(1 - safe)))}


def main() -> None:
    """逐房留一只用训练房，选择固定模型后保存源摘要与系数。"""

    rows, metadata = _load()
    tiles = sorted({row["features"]["tile"] for row in rows})
    x, y, risk, names = _matrix(rows, tiles)
    rooms = sorted(metadata["source_rooms"])
    pred = {name: np.empty(len(rows), dtype=np.float64)
            for name in ("tile_dealer_prior", "risk_units", "public_full_l2_1",
                         "public_full_l2_20", "public_full_l2_100")}
    row_rooms = np.array([row["room_id"] for row in rows])
    for room in rooms:
        train = np.flatnonzero(row_rooms != room)
        check = np.flatnonzero(row_rooms == room)
        if not len(train) or not len(check):
            raise ValueError("训练房逐房留一缺失")
        pred["tile_dealer_prior"][check] = _tile_dealer_prior(rows, train, check)
        beta_risk = _fit_logistic(risk[train], y[train], penalty=20.0)
        pred["risk_units"][check] = _predict(risk[check], beta_risk)
        for lam in (1.0, 20.0, 100.0):
            name = f"public_full_l2_{int(lam)}"
            beta = _fit_logistic(x[train], y[train], penalty=lam)
            pred[name][check] = _predict(x[check], beta)
    room_metrics = {}
    for room in rooms:
        mask = np.array([row["room_id"] == room for row in rows], dtype=bool)
        room_metrics[room] = {name: _metrics(y[mask], p[mask]) for name, p in pred.items()}
    mean = {name: {metric: float(np.mean([room_metrics[room][name][metric]
                                         for room in rooms])) for metric in ("brier", "log_loss")}
            for name in pred}
    public_names = [name for name in pred if name.startswith("public_full_l2_")]
    chosen = min(public_names, key=lambda name: (mean[name]["brier"], mean[name]["log_loss"], name))
    chosen_penalty = float(chosen.rsplit("_", 1)[1])
    rng = np.random.default_rng(20260927)
    samples = rng.integers(0, len(rooms), size=(20000, len(rooms)))
    comparisons = {}
    for baseline in ("tile_dealer_prior", "risk_units"):
        comparisons[baseline] = {}
        for metric in ("brier", "log_loss"):
            per_room = np.array([room_metrics[room][chosen][metric] -
                                 room_metrics[room][baseline][metric] for room in rooms])
            draws = per_room[samples].mean(axis=1)
            comparisons[baseline][metric] = {
                "mean_candidate_minus_baseline": float(per_room.mean()),
                "room_bootstrap_95": [float(np.quantile(draws, 0.025)),
                                      float(np.quantile(draws, 0.975))],
                "improved_rooms": int(np.sum(per_room < 0)),
                "worse_rooms": int(np.sum(per_room > 0))}
    chosen_beta = _fit_logistic(x, y, penalty=chosen_penalty)
    risk_beta = _fit_logistic(risk, y, penalty=20.0)
    tile_dealer_counts = defaultdict(lambda: [0, 0])
    for row in rows:
        f = row["features"]
        cell = tile_dealer_counts[(f["tile"], f["dealer_relative"])]
        cell[0] += row["label_claim"]
        cell[1] += 1
    model = {"schema": "g8-public-response-frozen-model/1",
             "train_rows_gzip_sha256": metadata["rows_gzip_sha256"],
             "trainer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "extractor_source_sha256": hashlib.sha256(
                 (_project_file(_PROJECT_ROOT, HERE / "g8_public_response_training_rows.py")).read_bytes()).hexdigest(),
             "numpy_version": np.__version__,
             "validation_labels_opened": False,
             "features": names, "tiles": tiles, "penalty": chosen_penalty,
             "coefficients": [float(value) for value in chosen_beta],
             "risk_baseline_coefficients": [float(value) for value in risk_beta],
             "tile_dealer_baseline_strength": 20,
             "tile_dealer_baseline_global_rate": float(y.mean()),
             "tile_dealer_baseline_counts": {
                 f"{tile}|{relative}": {"claimed": yes, "total": total}
                 for (tile, relative), (yes, total) in sorted(tile_dealer_counts.items())},
             "numeric_scales": "固定 100/5/1.5/4/20；见编码脚本",
             "fit": "L2 Newton logistic; 训练房逐房留一选 Brier 最小；候选分母=已接受实际弃牌"}
    MODEL.write_text(json.dumps(model, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                     encoding="utf-8")
    result = {"schema": "g8-public-response-training-cv/1",
              "train_rows_gzip_sha256": metadata["rows_gzip_sha256"],
              "training_rooms": len(rooms), "training_rows": len(rows),
              "training_claim_rate": float(y.mean()), "cross_validation": "leave-one-room-out",
              "mean_equal_room": mean, "by_room": room_metrics,
              "chosen_vs_baselines_room_bootstrap": comparisons,
              "chosen_public_model": chosen,
              "frozen_model_sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
              "boundary": "只用 91 间冻结训练房逐房留一；第 95 房起的验证标签尚未读取；预测不能代替桌分因果评估"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"training_rows": len(rows), "training_claim_rate": result["training_claim_rate"],
                      "mean_equal_room": mean, "chosen_public_model": chosen,
                      "chosen_vs_baselines_room_bootstrap": comparisons},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
