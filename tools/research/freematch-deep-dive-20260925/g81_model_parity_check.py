#!/usr/bin/env python3
"""G81：生产观察上的纯 Python 墙容量预测与 G79B NumPy 参照逐码对拍。"""

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

import g8_public_response_training_rows as source
import g80_action_relevance_screen as reference
import g81_posterior_wall_policy as candidate
from hangma_bot.application.audit_codec import decision_request_from_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g81-posterior-wall-behavior-20260928/parity.json')


def sha(path: Path) -> str:
    """输入/源码 SHA-256，用于复算同一观察的数值一致性。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """只取冻结清单首房最先 20 个可计算中后巡摸打观察。"""

    if OUT.exists():
        raise SystemExit("G81 数值对拍已存在，拒绝覆盖")
    frozen = json.loads(source.FROZEN.read_text(encoding="utf-8"))
    audit = source.ROOT / frozen["rooms"][0]["audit_dir"]
    decisions = audit / "participants" / source.ACTOR / "decisions.jsonl"
    fit = json.loads(reference.G79B.read_text(encoding="utf-8"))["model"]["coefficients"]
    beta = np.asarray([fit[name] for name in reference.occupancy.FEATURES])
    checked, max_error = 0, 0.0
    for _, raw, _ in source.screen._iter_decisions(audit):
        obs = raw.get("observation") or {}
        seat = obs.get("seat")
        if (obs.get("phase") != "draw" or type(seat) is not int
                or len(obs.get("discards") or []) != 4
                or len(obs["discards"][seat]) < 3):
            continue
        request = decision_request_from_json(raw)
        predicted = candidate.predict_wall_counts(request.observation)
        if predicted is None:
            continue
        X, n, H, wall = reference._observation_features(obs)
        _, model_hidden = reference.occupancy._predict(reference.occupancy.Window(
            "parity", 0, X, n, np.zeros(34, dtype=np.int16), H, wall
        ), beta)
        if tuple(n) != predicted[0] or (H, wall) != predicted[2:]:
            raise ValueError("G81 公开未知池与 G80 生产观察不同")
        error = float(np.max(np.abs((n - model_hidden) - predicted[1])))
        if error > 1e-9:
            raise ValueError("G81 预计逐码墙余与 G79B 参照不一致")
        max_error = max(max_error, error)
        checked += 1
        if checked == 20:
            break
    if checked != 20:
        raise ValueError("冻结首房没有二十个可比中后巡观察")
    result = {"schema": "g81-posterior-wall-parity/1", "windows": checked,
              "max_absolute_tile_error": max_error,
              "source_sha256": {"frozen_rooms": sha(source.FROZEN), "audit": sha(decisions),
                                "g79b_model": sha(reference.G79B),
                                "candidate": sha(_project_file(_PROJECT_ROOT, HERE / "g81_posterior_wall_policy.py")),
                                "g80_reference": sha(_project_file(_PROJECT_ROOT, HERE / "g80_action_relevance_screen.py")),
                                "script": sha(Path(__file__))},
              "boundary": "仅数值对拍，不读取赛后暗手，不证明候选桌赛收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
