#!/usr/bin/env python3
"""直接先胡竞速目标：训练房逐房留一比较局面与行动相关公开特征。"""

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

import g8_public_response_train_model as math
import g8_public_response_validate as official


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-direct-race-training-20260927')
STATE_PREFIXES = ("dealer_relative:", "river_length_rel", "meld_length_rel")
STATE_NAMES = {"intercept", "wall_100", "shanten_5", "white_4", "catch_play"}
PENALTIES = (1.0, 20.0, 100.0)


def training_rows() -> tuple[list[dict], dict, Counter, list[dict]]:
    """把官方下一次本人摸牌/终局诊断接到已有动作前行；流局不填作负例。"""

    rows, metadata = math._load()
    outcomes = official.next_self_draw_outcomes(set(metadata["source_rooms"]))
    counts = Counter()
    seen = set()
    races = []
    labels = []
    for row in rows:
        key = (row["game_id"], row["round_no"], row["discard_seq"])
        if key in seen:
            raise ValueError("同一真实弃牌重复")
        seen.add(key)
        outcome = outcomes.get(key)
        if outcome is None:
            raise ValueError("训练真实弃牌缺下一摸/终局")
        kind = outcome["kind"]
        counts[kind] += 1
        labels.append({"room_id": row["room_id"], "game_id": key[0],
                       "round_no": key[1], "discard_seq": key[2],
                       "next_self_draw_or_terminal": outcome})
        if kind not in ("other_hu_before_self_draw", "self_draw_reached"):
            continue
        # 只为沿用已有公开特征编码器替换临时标签，不改冻结的被鸣训练行。
        clone = dict(row)
        clone["label_claim"] = int(kind == "other_hu_before_self_draw")
        races.append(clone)
    if len(seen) != 62975 or len(labels) != 62975:
        raise ValueError("官方时序标签覆盖不全")
    if {row["room_id"] for row in races} != set(metadata["source_rooms"]):
        raise ValueError("训练房主要两类标签覆盖不全")
    return races, metadata, counts, labels


def state_columns(names: list[str]) -> list[int]:
    """状态负控删掉牌码、同牌外露与候选风险等行动相关字段。"""

    indices = [index for index, name in enumerate(names)
               if name in STATE_NAMES or name.startswith(STATE_PREFIXES)]
    selected = [names[index] for index in indices]
    expected = 1 + 4 + 4 + 3 + 3
    if len(selected) != expected:
        raise ValueError(f"状态负控维度 {len(selected)}，应为 {expected}")
    return indices


def main() -> None:
    """逐房留一选各自 L2，并按独立房比较完整/状态模型。"""

    if OUT.exists():
        raise SystemExit("直接时序训练目录已存在，拒绝覆盖冻结模型")
    rows, metadata, label_counts, labels = training_rows()
    tiles = sorted({row["features"]["tile"] for row in rows})
    full_x, y, _risk, names = math._matrix(rows, tiles)
    state_index = state_columns(names)
    state_x = full_x[:, state_index]
    state_names = [names[index] for index in state_index]
    rooms = sorted(metadata["source_rooms"])
    row_rooms = np.array([row["room_id"] for row in rows])
    predictions = {family: {penalty: np.empty(len(rows), dtype=np.float64)
                            for penalty in PENALTIES}
                   for family in ("state", "full")}
    matrices = {"state": state_x, "full": full_x}
    for room in rooms:
        train = np.flatnonzero(row_rooms != room)
        check = np.flatnonzero(row_rooms == room)
        if not len(train) or not len(check):
            raise ValueError("逐房留一缺训练/验收行")
        for family, matrix in matrices.items():
            for penalty in PENALTIES:
                beta = math._fit_logistic(matrix[train], y[train], penalty)
                predictions[family][penalty][check] = math._predict(matrix[check], beta)
    by_room = {}
    for room in rooms:
        mask = row_rooms == room
        by_room[room] = {
            "rows": int(mask.sum()),
            "observed_other_hu_rate": float(y[mask].mean()),
            "models": {family: {str(int(penalty)): math._metrics(y[mask], p[mask])
                                for penalty, p in curves.items()}
                       for family, curves in predictions.items()}}
    mean = {family: {
        str(int(penalty)): {
            metric: float(np.mean([by_room[room]["models"][family][str(int(penalty))][metric]
                                   for room in rooms]))
            for metric in ("brier", "log_loss")}
        for penalty in PENALTIES} for family in predictions}
    chosen = {family: min(PENALTIES,
                          key=lambda penalty: (mean[family][str(int(penalty))]["brier"],
                                               mean[family][str(int(penalty))]["log_loss"],
                                               penalty))
              for family in predictions}
    rng = np.random.default_rng(20260927)
    samples = rng.integers(0, len(rooms), size=(20000, len(rooms)))
    comparisons = {}
    for metric in ("brier", "log_loss"):
        differences = np.array([
            by_room[room]["models"]["full"][str(int(chosen["full"]))][metric] -
            by_room[room]["models"]["state"][str(int(chosen["state"]))][metric]
            for room in rooms])
        sampled = differences[samples].mean(axis=1)
        comparisons[metric] = {
            "mean_full_minus_state": float(differences.mean()),
            "room_bootstrap_95": [float(np.quantile(sampled, 0.025)),
                                  float(np.quantile(sampled, 0.975))],
            "improved_rooms": int(np.sum(differences < 0)),
            "worse_rooms": int(np.sum(differences > 0))}
    OUT.mkdir(parents=True)
    label_file = _project_file(_PROJECT_ROOT, OUT / "race-labels.jsonl.gz")
    with label_file.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressed:
            for row in labels:
                compressed.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    models = {}
    for family, matrix in matrices.items():
        beta = math._fit_logistic(matrix, y, chosen[family])
        models[family] = {"feature_names": state_names if family == "state" else names,
                          "penalty": chosen[family],
                          "coefficients": [float(value) for value in beta]}
    frozen = {
        "schema": "g8-direct-race-frozen-model/1",
        "source_claim_rows_gzip_sha256": metadata["rows_gzip_sha256"],
        "race_labels_gzip_sha256": hashlib.sha256(label_file.read_bytes()).hexdigest(),
        "trainer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "feature_extractor_source_sha256": hashlib.sha256(
            (_project_file(_PROJECT_ROOT, HERE / "g8_public_response_training_rows.py")).read_bytes()).hexdigest(),
        "feature_encoder_source_sha256": hashlib.sha256(
            (_project_file(_PROJECT_ROOT, HERE / "g8_public_response_train_model.py")).read_bytes()).hexdigest(),
        "next_draw_label_source_sha256": hashlib.sha256(
            (_project_file(_PROJECT_ROOT, HERE / "g8_public_response_validate.py")).read_bytes()).hexdigest(),
        "tiles": tiles, "all_feature_names": names, "state_indices": state_index,
        "models": models, "validation_labels_opened": False,
        "target": "other_hu_before_next_own_draw_vs_next_own_draw_reached"}
    model_path = _project_file(_PROJECT_ROOT, OUT / "frozen-model.json")
    model_path.write_text(json.dumps(frozen, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                          encoding="utf-8")
    result = {
        "schema": "g8-direct-race-training/1",
        "training_rooms": len(rooms), "source_executed_discards": len(labels),
        "labeled_competition_windows": len(rows),
        "outcome_counts": dict(sorted(label_counts.items())),
        "room_equal_cv_metrics": mean, "chosen_penalty": chosen,
        "full_minus_state": comparisons, "by_room": by_room,
        "frozen_model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "boundary": "只比较现行策略真实弃牌的观察预测；未执行备选牌和完整桌收益仍需因果验证"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                      encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
