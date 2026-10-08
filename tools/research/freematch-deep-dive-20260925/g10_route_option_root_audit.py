#!/usr/bin/env python3
"""G10 双臂完成后按独立牌山根重核均值与描述性区间。"""

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

import json
from pathlib import Path
import statistics

import numpy as np


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-paired-teacher-20260927')
BOOTSTRAP_SEED = 2026092701
BOOTSTRAP_DRAWS = 20_000


def _load(name: str):
    return json.loads((_project_file(_PROJECT_ROOT, OUT / name)).read_text(encoding="utf-8"))


def _interval(values: np.ndarray, samples: np.ndarray) -> dict:
    means = values[samples].mean(axis=1)
    return {"roots": int(len(values)), "mean": float(values.mean()),
            "root_bootstrap_95": [float(np.quantile(means, 0.025)),
                                  float(np.quantile(means, 0.975))]}


def main() -> None:
    """拒绝部分批次；八份未来墙先在每根内平均，不作独立样本。"""

    path = _project_file(_PROJECT_ROOT, OUT / "root-audit.json")
    if path.exists():
        raise SystemExit("G10 根级审计已存在，拒绝覆盖")
    manifest = _load("manifest.json")
    summary = _load("run-summary.json")
    result = _load("result.json")
    if (summary["completed_tables"] != manifest["planned_tables"]
            or manifest["planned_tables"] != 1520
            or result["completed_tables"] != 1520):
        raise ValueError("G10 双臂批次未完整跑满")
    roots = result["roots"]
    if len(roots) != manifest["target_count"] or len(roots) != 95:
        raise ValueError("G10 根级目标数量漂移")
    seen = set()
    for row in roots:
        key = (row["route_kind"], row["source_root_id"])
        if key in seen or len(row["table_deltas"]) != 8:
            raise ValueError("G10 独立根重复或未来墙不足八份")
        seen.add(key)
        if statistics.mean(row["table_deltas"]) != row["table_delta_mean"]:
            raise ValueError("G10 根内均值不一致")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    routes = {}
    for kind in ("standard", "seven_pairs"):
        subsets = {mix: np.asarray([row["table_delta_mean"] for row in roots
                                    if row["route_kind"] == kind and row["mix"] == mix],
                                   dtype=np.float64)
                   for mix in ("H", "M")}
        if any(len(values) < 12 for values in subsets.values()):
            raise ValueError("G10 路线独立根暴露门漂移")
        indices = {mix: rng.integers(0, len(values), size=(BOOTSTRAP_DRAWS, len(values)))
                   for mix, values in subsets.items()}
        pooled = np.concatenate([subsets[mix][indices[mix]] for mix in ("H", "M")], axis=1)
        pool_equal = (subsets["H"][indices["H"]].mean(axis=1)
                      + subsets["M"][indices["M"]].mean(axis=1)) / 2
        routes[kind] = {
            "by_mix": {mix: _interval(subsets[mix], indices[mix]) for mix in ("H", "M")},
            "pooled_target_mean": float(np.concatenate(list(subsets.values())).mean()),
            "pooled_target_root_bootstrap_95": [float(np.quantile(pooled.mean(axis=1), 0.025)),
                                                 float(np.quantile(pooled.mean(axis=1), 0.975))],
            "equal_pool_mean": float((subsets["H"].mean() + subsets["M"].mean()) / 2),
            "equal_pool_root_bootstrap_95": [float(np.quantile(pool_equal, 0.025)),
                                             float(np.quantile(pool_equal, 0.975))],
        }
        if abs(routes[kind]["pooled_target_mean"] - result["by_route"][kind]["overall_mean_delta"]) > 1e-12:
            raise ValueError("G10 教师汇总与独立重算不一致")
    output = {
        "schema": "g10-route-option-root-audit/1", "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_draws": BOOTSTRAP_DRAWS, "independence_unit": "route_kind × source_root_id",
        "routes": routes,
        "boundary": "仅开发根描述性区间；两类路线并行检验且未校正多重比较，不能替代全程候选独立确认",
    }
    path.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    print(json.dumps(routes, ensure_ascii=False))


if __name__ == "__main__":
    main()
