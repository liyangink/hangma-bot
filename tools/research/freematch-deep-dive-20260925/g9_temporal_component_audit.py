#!/usr/bin/env python3
"""事后解释性消融：拆分前态标志、墙余、他家动作和事件序号增量。"""

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

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

import g8_direct_race_train_model as direct
import g8_public_response_train_model as fit
import g9_temporal_delta_train as temporal


HERE = Path(__file__).resolve().parent
LABELS = direct.OUT / "race-labels.jsonl.gz"
FEATURES = temporal.OUT / "temporal-features.jsonl.gz"
FROZEN = temporal.OUT / "frozen-model.json"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-component-audit-20260927/result.json')
COMPONENTS = {
    "state": (),
    "availability": (0,),
    "availability_wall": (0, 2),
    "availability_opponent": (0, 3, 4, 5, 6, 7, 8),
    "availability_wall_opponent": (0, 2, 3, 4, 5, 6, 7, 8),
    "all_including_seq": tuple(range(9)),
}
CONTRASTS = (
    ("availability", "state"),
    ("availability_wall", "availability"),
    ("availability_opponent", "availability"),
    ("availability_wall_opponent", "availability_wall"),
    ("all_including_seq", "availability_wall_opponent"),
    ("all_including_seq", "state"),
)


def _key(row: dict) -> tuple:
    return row["game_id"], row["round_no"], row["discard_seq"]


def main() -> None:
    """只拆已发现的训练房预测增量；不重选 G9 冻结模型或验证门。"""

    if OUT.exists():
        raise SystemExit("G9 分量审计结果已存在，拒绝覆盖")
    original_rows, metadata = fit._load()
    labels = {}
    with gzip.open(LABELS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = _key(row)
            if key in labels:
                raise ValueError("直接先胡标签动作键重复")
            labels[key] = row["next_self_draw_or_terminal"]["kind"]
    features = {}
    with gzip.open(FEATURES, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = _key(row)
            if key in features:
                raise ValueError("时序差分动作键重复")
            features[key] = row["temporal"]
    rows, keys = [], []
    for row in original_rows:
        key = _key(row)
        kind = labels.get(key)
        if kind not in ("self_draw_reached", "other_hu_before_self_draw"):
            continue
        rows.append({**row, "label_claim": int(kind == "other_hu_before_self_draw")})
        keys.append(key)
    if len(rows) != 62910 or set(keys) != set(features):
        raise ValueError("G9 分量审计主二元标签与时序行不守恒")
    direct_model = json.loads((direct.OUT / "frozen-model.json").read_text(encoding="utf-8"))
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    if frozen["source_rows_gzip_sha256"] != metadata["rows_gzip_sha256"] or \
            frozen["temporal_features_gzip_sha256"] != hashlib.sha256(FEATURES.read_bytes()).hexdigest():
        raise ValueError("训练输入摘要漂移")
    full_x, y, _risk, names = fit._matrix(rows, direct_model["tiles"])
    if names != direct_model["all_feature_names"]:
        raise ValueError("静态特征次序漂移")
    state_x = full_x[:, direct_model["state_indices"]]
    delta_x = np.asarray([features[key] for key in keys])
    matrices = {name: np.column_stack([state_x, delta_x[:, list(index)]]) if index else state_x
                for name, index in COMPONENTS.items()}
    rooms = sorted(metadata["source_rooms"])
    row_rooms = np.array([row["room_id"] for row in rows])
    predictions = {name: np.empty(len(rows)) for name in matrices}
    for room in rooms:
        train = np.flatnonzero(row_rooms != room)
        check = np.flatnonzero(row_rooms == room)
        for name, x in matrices.items():
            beta = fit._fit_logistic(x[train], y[train], 100.0)
            predictions[name][check] = fit._predict(x[check], beta)
    by_room = {}
    for room in rooms:
        mask = row_rooms == room
        by_room[room] = {"rows": int(mask.sum()),
                         "models": {name: fit._metrics(y[mask], p[mask])
                                    for name, p in predictions.items()}}
    means = {name: {metric: float(np.mean([by_room[room]["models"][name][metric]
                                          for room in rooms]))
                    for metric in ("brier", "log_loss")}
             for name in matrices}
    rng = np.random.default_rng(20260927)
    samples = rng.integers(0, len(rooms), size=(20000, len(rooms)))
    contrasts = {}
    for newer, older in CONTRASTS:
        key = f"{newer}_minus_{older}"
        contrasts[key] = {}
        for metric in ("brier", "log_loss"):
            diff = np.array([by_room[room]["models"][newer][metric] -
                             by_room[room]["models"][older][metric] for room in rooms])
            boot = diff[samples].mean(axis=1)
            contrasts[key][metric] = {
                "mean": float(diff.mean()),
                "room_bootstrap_95": [float(np.quantile(boot, 0.025)),
                                      float(np.quantile(boot, 0.975))],
                "improved_rooms": int(np.sum(diff < 0))}
    result = {"schema": "g9-temporal-component-audit/1",
              "scope": "已打开的91间训练房；事后解释性消融，不做新候选选择或独立确认",
              "rooms": len(rooms), "rows": len(rows),
              "source_label_sha256": hashlib.sha256(LABELS.read_bytes()).hexdigest(),
              "source_feature_sha256": hashlib.sha256(FEATURES.read_bytes()).hexdigest(),
              "source_model_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "component_indices": {name: list(index) for name, index in COMPONENTS.items()},
              "room_equal_metrics": means, "contrasts": contrasts, "by_room": by_room,
              "boundary": "事后诊断；与预登记的完整模型独立验证门不可互换"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
