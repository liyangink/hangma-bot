#!/usr/bin/env python3
"""G242：在根等权训练/诊断中核弃后牌形的竞争终点预测增量。"""

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
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

import g241_multi_action_competing_reach as source


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G242-COMPETING-RISK-CALIBRATION-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g242-competing-risk-calibration-20260929/result.json')
CLASSES = ("third_own_draw", "own_win_before_third", "other_win_or_draw_before_third")
WALL_FEATURES = ("intercept", "wall_centered", "wall_centered_squared")
EXTRA_FEATURES = (
    "standard_shanten_clipped", "standard_useful_type_count",
    "standard_useful_public_capacity", "seven_pairs_not_applicable",
    "seven_pairs_shanten_clipped", "one_white", "two_or_more_whites",
    "one_meld", "two_or_more_melds", "discard_honor",
    "discard_terminal_numeric", "discard_white",
)
FULL_FEATURES = WALL_FEATURES + EXTRA_FEATURES
L2 = 0.02
STEPS = 1000
LEARNING_RATE = 0.03


def digest(path: Path) -> str:
    """对输入和分析器使用原文字节摘要。"""
    return sha256(path.read_bytes()).hexdigest()


def load_rows() -> tuple[list[dict], dict]:
    """验证每个 G241 阶段摘要后才读取父代实际路径标签。"""
    result_path = source.OUT / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if len(result["stage_sha256"]) != 128:
        raise ValueError("G242 来源阶段数不符")
    rows = []
    for name, expected in sorted(result["stage_sha256"].items()):
        path = source.OUT / "stages" / name
        if digest(path) != expected:
            raise ValueError("G242 来源阶段摘要不符：" + name)
        stage = json.loads(path.read_text(encoding="utf-8"))
        rows.extend({"mix": stage["mix"], "root_index": stage["root_index"],
                     "start_seat": stage["start_seat"], **row}
                    for row in stage["normal_discard_labels"])
    if len(rows) != result["normal_discard_windows"]:
        raise ValueError("G242 来源窗口数不符")
    return rows, result


def target(row: dict) -> int:
    """第三摸／本人先胡／他胡或流局只能属于一类。"""
    if row["third_own_draw_reached"]:
        return 0
    if row["hand_terminal"] == "own_win":
        return 1
    if row["hand_terminal"] in ("other_win", "draw"):
        return 2
    raise ValueError("G242 未知竞争终点")


def features(row: dict, *, full: bool) -> list[float]:
    """所有输入均可从弃前可见状态和该合法弃牌生产事实得到。"""
    wall = row["remaining_tile_count"]
    standard = row["standard_shanten_after"]
    seven = row["seven_pairs_shanten_after"]
    whites = row["white_before"]
    melds = row["meld_count"]
    types = row["standard_useful_type_count"]
    capacity = row["standard_useful_public_capacity"]
    key = row["chosen_action"]
    if (type(wall) is not int or wall < 0 or type(standard) is not int
            or standard < 0 or (seven is not None and
                                  (type(seven) is not int or seven < 0))
            or type(whites) is not int or whites not in range(5)
            or type(melds) is not int or melds not in range(5)
            or type(types) is not int or types < 0
            or type(capacity) is not int or capacity < 0
            or not key.startswith("discard:")):
        raise ValueError("G242 行动前特征缺失或越界")
    centered = (wall - 64) / 32.0
    base = [1.0, centered, centered * centered]
    if not full:
        return base
    code = key.split(":", 1)[1]
    numeric = len(code) == 2 and code[0] in "123456789" and code[1] in "wbt"
    return base + [
        min(standard, 6) / 4.0, types / 12.0, capacity / 48.0,
        float(seven is None), 0.0 if seven is None else min(seven, 6) / 6.0,
        float(whites == 1), float(whites >= 2),
        float(melds == 1), float(melds >= 2),
        float(not numeric), float(numeric and code[0] in "19"),
        float(code == "白"),
    ]


def probabilities(matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """稳定 softmax；三个结局的概率按固定类别顺序归一。"""
    logits = matrix @ weights
    logits -= np.max(logits, axis=1, keepdims=True)
    exp = np.exp(logits)
    return exp / exp.sum(axis=1, keepdims=True)


def fit(matrix: np.ndarray, labels: np.ndarray,
        sample_weight: np.ndarray) -> tuple[np.ndarray, dict]:
    """确定性全批 Adam；根等权并对非截距参数作 L2 收缩。"""
    weights = np.zeros((matrix.shape[1], len(CLASSES)), dtype=np.float64)
    first_moment = np.zeros_like(weights)
    second_moment = np.zeros_like(weights)
    onehot = np.eye(len(CLASSES), dtype=np.float64)[labels]
    initial = loss(matrix, labels, sample_weight, weights)
    for step in range(1, STEPS + 1):
        predicted = probabilities(matrix, weights)
        gradient = matrix.T @ ((predicted - onehot) * sample_weight[:, None])
        gradient[1:] += L2 * weights[1:]
        first_moment = 0.9 * first_moment + 0.1 * gradient
        second_moment = 0.999 * second_moment + 0.001 * gradient * gradient
        corrected_first = first_moment / (1.0 - 0.9 ** step)
        corrected_second = second_moment / (1.0 - 0.999 ** step)
        weights -= LEARNING_RATE * corrected_first / (
            np.sqrt(corrected_second) + 1e-8)
    final = loss(matrix, labels, sample_weight, weights)
    if not np.isfinite(weights).all() or final >= initial:
        raise ValueError("G242 优化未收敛到比零参数更好")
    return weights, {"initial_objective": initial, "final_objective": final}


def loss(matrix: np.ndarray, labels: np.ndarray,
         sample_weight: np.ndarray, weights: np.ndarray) -> float:
    """根等权多项对数损失加固定 L2 正则。"""
    predicted = probabilities(matrix, weights)
    cross_entropy = -np.log(np.maximum(predicted[np.arange(len(labels)), labels], 1e-15))
    return float(np.sum(cross_entropy * sample_weight)
                 + 0.5 * L2 * np.sum(weights[1:] ** 2))


def prepare(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """依固定特征合同构建墙基线、扩展牌形与互斥结局矩阵。"""
    wall = np.asarray([features(row, full=False) for row in rows], dtype=np.float64)
    full = np.asarray([features(row, full=True) for row in rows], dtype=np.float64)
    labels = np.asarray([target(row) for row in rows], dtype=np.int64)
    roots = np.asarray([(row["mix"], row["root_index"]) for row in rows], dtype=object)
    if wall.shape != (len(rows), len(WALL_FEATURES)) or full.shape != (
            len(rows), len(FULL_FEATURES)):
        raise ValueError("G242 特征维度不符")
    return wall, full, labels, roots


def root_weights(rows: list[dict]) -> np.ndarray:
    """每个 H/M×独立牌山根总权相同，座位和窗口留在根内。"""
    counts = Counter((row["mix"], row["root_index"]) for row in rows)
    if len(counts) != 24:
        raise ValueError("G242 训练根数不符")
    result = np.asarray([1.0 / (len(counts) * counts[(row["mix"], row["root_index"])])
                         for row in rows], dtype=np.float64)
    if abs(float(result.sum()) - 1.0) > 1e-10:
        raise ValueError("G242 根权未归一")
    return result


def score(rows: list[dict], labels: np.ndarray,
          forecasts: dict[str, np.ndarray]) -> dict:
    """先按每根聚合损失，再按 H/M 分别报告。"""
    partitions = defaultdict(list)
    for index, row in enumerate(rows):
        partitions[(row["mix"], row["root_index"])].append(index)
    if set(partitions) != {(mix, root) for mix in source.MIXES
                          for root in range(13, 17)}:
        raise ValueError("G242 诊断留根身份缺失")
    root_rows = []
    for (mix, root), indices in sorted(partitions.items()):
        observed = np.bincount(labels[indices], minlength=len(CLASSES))
        metrics = {}
        for name, forecast in forecasts.items():
            selected = forecast[indices]
            truth = np.eye(len(CLASSES))[labels[indices]]
            log_losses = -np.log(np.maximum(
                selected[np.arange(len(indices)), labels[indices]], 1e-15))
            brier = np.sum((selected - truth) ** 2, axis=1)
            metrics[name] = {
                "log_loss": float(np.mean(log_losses)),
                "brier": float(np.mean(brier)),
                "predicted_counts": [float(v) for v in selected.sum(axis=0)],
            }
        root_rows.append({"mix": mix, "root_index": root,
                          "windows": len(indices), "observed_counts": observed.tolist(),
                          "models": metrics,
                          "full_minus_wall_log_loss": (metrics["full"]["log_loss"]
                                                       - metrics["wall"]["log_loss"]),
                          "full_minus_wall_brier": (metrics["full"]["brier"]
                                                    - metrics["wall"]["brier"])})
    by_mix = {}
    for mix in source.MIXES:
        group = [row for row in root_rows if row["mix"] == mix]
        by_mix[mix] = {
            "independent_roots": len(group),
            "windows": sum(row["windows"] for row in group),
            "mean_log_loss": {name: float(np.mean([
                row["models"][name]["log_loss"] for row in group]))
                for name in forecasts},
            "mean_brier": {name: float(np.mean([
                row["models"][name]["brier"] for row in group]))
                for name in forecasts},
            "root_brier_improvements_full_vs_wall": sum(
                row["full_minus_wall_brier"] < 0 for row in group),
        }
    gate = (all(by_mix[mix]["mean_log_loss"]["full"]
                < by_mix[mix]["mean_log_loss"]["wall"]
                and by_mix[mix]["mean_brier"]["full"]
                < by_mix[mix]["mean_brier"]["wall"] for mix in source.MIXES)
            and sum(row["full_minus_wall_brier"] < 0 for row in root_rows) >= 6)
    return {"roots": root_rows, "by_mix": by_mix,
            "predeclared_incremental_signal_gate_pass": gate}


def main() -> None:
    """只在保存来源摘要和完整预设权重后生成一次结果。"""
    if OUT.exists():
        raise FileExistsError(OUT)
    rows, source_result = load_rows()
    train = [row for row in rows if row["root_index"] <= 12]
    holdout = [row for row in rows if row["root_index"] >= 13]
    wall_train, full_train, train_y, _ = prepare(train)
    wall_holdout, full_holdout, holdout_y, _ = prepare(holdout)
    weights = root_weights(train)
    wall_model, wall_fit = fit(wall_train, train_y, weights)
    full_model, full_fit = fit(full_train, train_y, weights)
    constant = np.bincount(train_y, weights=weights,
                           minlength=len(CLASSES)).astype(np.float64)
    if np.any(constant <= 0):
        raise ValueError("G242 训练结局类缺失")
    forecasts = {
        "constant": np.tile(constant, (len(holdout), 1)),
        "wall": probabilities(wall_holdout, wall_model),
        "full": probabilities(full_holdout, full_model),
    }
    evaluation = score(holdout, holdout_y, forecasts)
    result = {
        "schema": "g242-competing-risk-calibration/1",
        "source_result_sha256": digest(source.OUT / "result.json"),
        "source_manifest_sha256": digest(source.OUT / "manifest.json"),
        "source_stage_count": len(source_result["stage_sha256"]),
        "input_sha256": {"prereg": digest(PREREG), "script": digest(Path(__file__))},
        "class_order": list(CLASSES), "wall_feature_order": list(WALL_FEATURES),
        "full_feature_order": list(FULL_FEATURES),
        "training_roots_per_pool": list(range(1, 13)),
        "diagnostic_roots_per_pool": list(range(13, 17)),
        "train_windows": len(train), "diagnostic_windows": len(holdout),
        "l2": L2, "steps": STEPS, "learning_rate": LEARNING_RATE,
        "constant_probability": constant.tolist(),
        "wall_coefficients": wall_model.tolist(),
        "full_coefficients": full_model.tolist(),
        "fit_objective": {"wall": wall_fit, "full": full_fit},
        "evaluation": evaluation,
        "boundary": "父代已选动作的观察性竞争结局预测；非备选弃牌因果收益或上线资格。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
                   + "\n", encoding="utf-8")
    print(json.dumps({"train_windows": len(train), "diagnostic_windows": len(holdout),
                      "by_mix": evaluation["by_mix"],
                      "gate_pass": evaluation["predeclared_incremental_signal_gate_pass"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
