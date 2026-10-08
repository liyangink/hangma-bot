#!/usr/bin/env python3
"""仅用已开放训练房检查 G9 独立验证的行、特征与冻结系数接缝。"""

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

import hashlib
import json
from pathlib import Path

import numpy as np

import g9_temporal_delta_validate as validation


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-validation-preflight-20260927/result.json')


def main() -> None:
    """固定训练清单前三房；不扫描第 95 房以后目标行。"""
    if OUT.exists():
        raise SystemExit("G9 验证预检结果已存在，拒绝覆盖")
    frozen = json.loads(validation.source.FROZEN.read_text(encoding="utf-8"))
    selected = []
    for room in frozen["rooms"][:3]:
        audit = validation.source.ROOT / room["audit_dir"]
        manifest = audit / "manifest.json"
        selected.append({"room_id": room["room_id"], "audit_dir": room["audit_dir"],
                         "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                         "decision_bytes": room["decision_bytes"]})
    if len(selected) != 3 or len({row["room_id"] for row in selected}) != 3:
        raise ValueError("训练房预检来源不唯一")
    rows, counts = validation.validation_rows(selected)
    keys = [(row["game_id"], row["round_no"], row["discard_seq"]) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("已接受弃牌事件身份重复")
    temporal, temporal_counts = validation.temporal.temporal_rows(set(keys), selected)
    if len(temporal) != len(keys):
        raise ValueError("时序投影未覆盖全部动作行")
    base_model = json.loads((validation.direct.OUT / "frozen-model.json").read_text(encoding="utf-8"))
    frozen_model = json.loads(validation.MODEL.read_text(encoding="utf-8"))
    if hashlib.sha256(validation.MODEL.read_bytes()).hexdigest() != validation.EXPECTED_MODEL_SHA256:
        raise ValueError("冻结 G9 模型摘要漂移")
    full_x, y, _risk, names = validation.fit._matrix(rows, base_model["tiles"])
    if names != base_model["all_feature_names"]:
        raise ValueError("静态特征次序漂移")
    state_x = full_x[:, base_model["state_indices"]]
    temporal_x = np.asarray([temporal[key] for key in keys], dtype=np.float64)
    if temporal_x.shape != (len(rows), len(validation.temporal.NAMES)):
        raise ValueError("时序特征维度漂移")
    matrices = {"state": state_x,
                "state_plus_temporal": np.column_stack([state_x, temporal_x])}
    predictions = {}
    for name, matrix in matrices.items():
        spec = frozen_model["models"][name]
        expected = [names[index] for index in base_model["state_indices"]]
        if name == "state_plus_temporal":
            expected += list(validation.temporal.NAMES)
        if spec["feature_names"] != expected or len(spec["coefficients"]) != matrix.shape[1]:
            raise ValueError("冻结系数与预检特征不匹配")
        prediction = validation.fit._predict(matrix, np.asarray(spec["coefficients"]))
        if not np.all(np.isfinite(prediction)) or not np.all((0 < prediction) & (prediction < 1)):
            raise ValueError("冻结模型概率非有限或越界")
        predictions[name] = {"mean": float(np.mean(prediction)),
                             "brier": validation.fit._metrics(y, prediction)["brier"]}
    result = {"schema": "g9-temporal-validation-training-preflight/1",
              "source_rooms": [row["room_id"] for row in selected],
              "source_frozen_rooms_sha256": hashlib.sha256(validation.source.FROZEN.read_bytes()).hexdigest(),
              "model_sha256": validation.EXPECTED_MODEL_SHA256,
              "validator_script_sha256": hashlib.sha256(Path(validation.__file__).read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "rows": len(rows), "unique_keys": len(keys),
              "static_features": full_x.shape[1], "state_features": state_x.shape[1],
              "temporal_features": temporal_x.shape[1],
              "label_rate": float(np.mean(y)), "label_counts": dict(sorted(counts.items())),
              "coverage": dict(sorted(temporal_counts.items())),
              "predictions": predictions,
              "boundary": "仅用已开放的训练房核工程接缝；不构成独立预测或动作收益验证"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("label_counts", "coverage")},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
