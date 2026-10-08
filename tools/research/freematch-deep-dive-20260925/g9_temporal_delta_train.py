#!/usr/bin/env python3
"""逐房留一比较静态局面与最小公开前态差分对先胡竞速的预测。"""

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

import g8_direct_race_train_model as direct
import g8_public_response_train_model as fit
import g8_public_response_training_rows as source
import g9_temporal_delta_preflight as preflight


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-delta-training-20260927')
NAMES = ("prior_available", "seq_gap_50", "wall_delta_10",
         "river_rel1_delta_3", "river_rel2_delta_3", "river_rel3_delta_3",
         "meld_rel1_delta_2", "meld_rel2_delta_2", "meld_rel3_delta_2")
PENALTY = 100.0


def temporal_rows(source_keys: set[tuple], room_rows: list[dict] | None = None) -> tuple[dict[tuple, tuple[float, ...]], Counter]:
    """仅用本人与公开观察两次快照生成可复算差分，缺前态明示为零填充。"""

    frozen = json.loads(preflight.FROZEN.read_text(encoding="utf-8"))
    selected = frozen["rooms"] if room_rows is None else room_rows
    rows = {}
    counts = Counter()
    for room in selected:
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if "decision_bytes" in room and decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策记录字节数漂移")
        accepted = source._accepted(decision_file)
        previous = {}
        for context, request, _plan in source.screen._iter_decisions(audit):
            if (request.get("window_key") or {}).get("phase") != "draw":
                continue
            action = accepted.get(context.get("decision_id"))
            if not action or not action.startswith("discard:"):
                continue
            key = (context["game_id"], context["round_no"], context["trigger_seq"] + 1)
            round_key = key[:2]
            current = preflight._summary(request["observation"])
            prior = previous.get(round_key)
            values = (0.0,) * len(NAMES)
            if current is not None and prior is not None:
                old, old_seat = prior
                wall_delta = old[0] - current[0]
                river = tuple(now - before for now, before in zip(current[1], old[1]))
                meld = tuple(now - before for now, before in zip(current[2], old[2]))
                seq_gap = current[3] - old[3]
                if old_seat == request["observation"]["seat"] and wall_delta >= 0 and seq_gap > 0 \
                        and all(delta >= 0 for delta in river + meld):
                    values = (1.0, seq_gap / 50, wall_delta / 10,
                              river[1] / 3, river[2] / 3, river[3] / 3,
                              meld[1] / 2, meld[2] / 2, meld[3] / 2)
            if key in source_keys:
                if key in rows:
                    raise ValueError("源训练弃牌窗口被提取多次")
                rows[key] = values
                counts["source_rows"] += 1
                counts["prior_available"] += values[0] == 1.0
            if current is None:
                previous.pop(round_key, None)
            else:
                previous[round_key] = (current, request["observation"]["seat"])
    if set(rows) != source_keys:
        raise ValueError(f"时序差分与训练目标键不一致：缺 {len(source_keys - set(rows))}，多 {len(set(rows) - source_keys)}")
    return rows, counts


def main() -> None:
    """预登记固定 L2=100，同房 LOO、房等权指标与房级自助区间。"""

    if OUT.exists():
        raise SystemExit("G9 时序差分训练证据已存在，拒绝覆盖")
    pre = json.loads(preflight.OUT.read_text(encoding="utf-8"))
    if pre["outcome_blind"] is not True or pre["totals"]["prior_usable"] < 10000:
        raise ValueError("结果盲差分入口未过覆盖门")
    base_model = json.loads((direct.OUT / "frozen-model.json").read_text(encoding="utf-8"))
    if base_model["validation_labels_opened"] is not False:
        raise ValueError("来源训练/验证边界漂移")
    train_rows, metadata, _outcomes, _labels = direct.training_rows()
    keys = [(row["game_id"], row["round_no"], row["discard_seq"]) for row in train_rows]
    if len(keys) != len(set(keys)):
        raise ValueError("源训练动作键重复")
    temporal, counts = temporal_rows(set(keys))
    tiles = base_model["tiles"]
    full_x, y, _risk, full_names = fit._matrix(train_rows, tiles)
    if full_names != base_model["all_feature_names"]:
        raise ValueError("冻结静态特征次序漂移")
    state_index = base_model["state_indices"]
    state_x = full_x[:, state_index]
    delta_x = np.asarray([temporal[key] for key in keys], dtype=np.float64)
    extended_x = np.column_stack([state_x, delta_x])
    rooms = sorted(metadata["source_rooms"])
    row_rooms = np.array([row["room_id"] for row in train_rows])
    predictions = {"state": np.empty(len(y)), "state_plus_temporal": np.empty(len(y))}
    for room in rooms:
        train = np.flatnonzero(row_rooms != room)
        check = np.flatnonzero(row_rooms == room)
        for name, matrix in (("state", state_x), ("state_plus_temporal", extended_x)):
            beta = fit._fit_logistic(matrix[train], y[train], PENALTY)
            predictions[name][check] = fit._predict(matrix[check], beta)
    by_room = {}
    for room in rooms:
        mask = row_rooms == room
        by_room[room] = {"rows": int(mask.sum()),
                         "prior_available": int(np.sum(delta_x[mask, 0] == 1)),
                         "observed_other_hu_rate": float(y[mask].mean()),
                         "metrics": {name: fit._metrics(y[mask], values[mask])
                                     for name, values in predictions.items()}}
    mean = {name: {metric: float(np.mean([by_room[room]["metrics"][name][metric]
                                           for room in rooms]))
                   for metric in ("brier", "log_loss")}
            for name in predictions}
    rng = np.random.default_rng(20260927)
    samples = rng.integers(0, len(rooms), size=(20000, len(rooms)))
    comparison = {}
    for metric in ("brier", "log_loss"):
        differences = np.array([
            by_room[room]["metrics"]["state_plus_temporal"][metric] -
            by_room[room]["metrics"]["state"][metric] for room in rooms])
        boot = differences[samples].mean(axis=1)
        comparison[metric] = {"mean_extended_minus_state": float(differences.mean()),
                              "room_bootstrap_95": [float(np.quantile(boot, 0.025)),
                                                    float(np.quantile(boot, 0.975))],
                              "improved_rooms": int(np.sum(differences < 0))}
    OUT.mkdir(parents=True)
    feature_path = _project_file(_PROJECT_ROOT, OUT / "temporal-features.jsonl.gz")
    with feature_path.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressed:
            for row, key in zip(train_rows, keys):
                payload = {"room_id": row["room_id"], "game_id": key[0],
                           "round_no": key[1], "discard_seq": key[2],
                           "temporal": temporal[key]}
                compressed.write((json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    models = {}
    for name, matrix in (("state", state_x), ("state_plus_temporal", extended_x)):
        beta = fit._fit_logistic(matrix, y, PENALTY)
        models[name] = {"penalty": PENALTY,
                        "feature_names": [full_names[index] for index in state_index] +
                        (list(NAMES) if name == "state_plus_temporal" else []),
                        "coefficients": [float(value) for value in beta]}
    model_path = _project_file(_PROJECT_ROOT, OUT / "frozen-model.json")
    model_path.write_text(json.dumps({
        "schema": "g9-temporal-delta-frozen-model/1",
        "source_rooms": len(rooms), "source_rows_gzip_sha256": metadata["rows_gzip_sha256"],
        "temporal_features_gzip_sha256": hashlib.sha256(feature_path.read_bytes()).hexdigest(),
        "training_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "temporal_extract_source_sha256": hashlib.sha256(Path(preflight.__file__).read_bytes()).hexdigest(),
        "labels_source_sha256": base_model["next_draw_label_source_sha256"],
        "validation_labels_opened": False, "models": models},
        ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    result = {
        "schema": "g9-temporal-delta-training/1",
        "source_rooms": len(rooms), "source_rows": len(train_rows),
        "temporal_coverage": dict(counts), "penalty": PENALTY,
        "room_equal_cv_metrics": mean,
        "extended_minus_state": comparison,
        "by_room": by_room,
        "frozen_model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "boundary": "训练房预测信息试验；即使成功也不构成候选动作价值或上线资格"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                      encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
