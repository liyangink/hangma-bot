#!/usr/bin/env python3
"""训练房探索：冻结 G9 风险模型在已执行爆头弃胡窗口是否有区分力。"""

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
import g9_temporal_delta_train as temporal


HERE = Path(__file__).resolve().parent
SCOPE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-hu-deferral-scope-20260927/result.json')
MODEL = temporal.OUT / "frozen-model.json"
TEMPORAL = temporal.OUT / "temporal-features.jsonl.gz"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-hu-deferral-risk-training-20260927/result.json')


def main() -> None:
    """只用旧训练房标签做探索；不得将此结果当独立验证或阈值训练。"""
    if OUT.exists():
        raise SystemExit("G9 弃胡风险训练探针已存在，拒绝覆盖")
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    if scope["outcome_blind"] is not True or scope["totals"]["deferral_accepted_as_planned"] != 326:
        raise ValueError("结果盲弃胡入口与预期不符")
    keys = {(row["game_id"], row["round_no"], row["discard_seq"])
            for row in scope["deferral_windows"] if row["accepted_as_planned"]}
    if len(keys) != 326:
        raise ValueError("弃胡入口键不唯一")
    all_rows, metadata, label_counts, _labels = direct.training_rows()
    rows = [row for row in all_rows
            if (row["game_id"], row["round_no"], row["discard_seq"]) in keys]
    selected_keys = {(row["game_id"], row["round_no"], row["discard_seq"]) for row in rows}
    if not rows or len(selected_keys) != len(rows):
        raise ValueError("训练弃胡行缺失或重复")
    temporal_features = {}
    with gzip.open(TEMPORAL, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["game_id"], row["round_no"], row["discard_seq"])
            if key in selected_keys:
                temporal_features[key] = row["temporal"]
    if set(temporal_features) != selected_keys:
        raise ValueError("冻结时序字段未覆盖全部弃胡训练行")
    base = json.loads((direct.OUT / "frozen-model.json").read_text(encoding="utf-8"))
    frozen = json.loads(MODEL.read_text(encoding="utf-8"))
    full_x, y, _risk, names = fit._matrix(rows, base["tiles"])
    if names != base["all_feature_names"]:
        raise ValueError("静态特征合同漂移")
    state_x = full_x[:, base["state_indices"]]
    delta_x = np.asarray([temporal_features[(row["game_id"], row["round_no"], row["discard_seq"])]
                          for row in rows], dtype=np.float64)
    predictions = {}
    for name, x in (("state", state_x),
                    ("state_plus_temporal", np.column_stack([state_x, delta_x]))):
        spec = frozen["models"][name]
        expected = [names[index] for index in base["state_indices"]] + \
            (list(temporal.NAMES) if name == "state_plus_temporal" else [])
        if spec["feature_names"] != expected:
            raise ValueError("冻结 G9 特征次序漂移")
        predictions[name] = fit._predict(x, np.asarray(spec["coefficients"]))
    tertiles = {}
    groups_by_model = {}
    for name, p in predictions.items():
        cutoffs = np.quantile(p, [1 / 3, 2 / 3])
        groups = np.where(p <= cutoffs[0], "low",
                          np.where(p <= cutoffs[1], "middle", "high"))
        groups_by_model[name] = groups
        by_group = {}
        for group in ("low", "middle", "high"):
            mask = groups == group
            by_group[group] = {"rows": int(mask.sum()), "other_hu_events": int(y[mask].sum()),
                               "observed_rate": float(y[mask].mean()),
                               "predicted_mean": float(p[mask].mean()),
                               "rooms": len({row["room_id"] for row, include in zip(rows, mask) if include})}
        tertiles[name] = {"cutoffs": [float(value) for value in cutoffs],
                          "by_group": by_group}
    result = {
        "schema": "g9-hu-deferral-risk-training-probe/1",
        "source_scope_sha256": hashlib.sha256(SCOPE.read_bytes()).hexdigest(),
        "source_model_sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        "source_temporal_features_sha256": hashlib.sha256(TEMPORAL.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "training_rooms": len(metadata["source_rooms"]),
        "accepted_deferral_windows": len(keys),
        "binary_label_rows": len(rows),
        "excluded_nonbinary_labels": len(keys - selected_keys),
        "prior_available": int(np.sum(delta_x[:, 0] == 1)),
        "other_hu_events": int(y.sum()),
        "overall": {name: fit._metrics(y, p) for name, p in predictions.items()},
        "training_tertiles": tertiles,
        "changed_tertile_with_temporal": int(np.sum(
            groups_by_model["state"] != groups_by_model["state_plus_temporal"])),
        "source_label_counts": dict(label_counts),
        "boundary": "冻结模型在其自身训练房上的描述性检查；不能证明独立预测、动作价值或净积分",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "source_label_counts"},
                     ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
