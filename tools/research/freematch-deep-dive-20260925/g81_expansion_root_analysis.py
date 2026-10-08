#!/usr/bin/env python3
"""G81 第二批：按冻结池×根单位报告净分与收入分量，描述性重采样。"""

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


HERE = Path(__file__).resolve().parent
INPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g81-posterior-wall-expansion-20260928/result.json')
MANIFEST = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g81-posterior-wall-expansion-20260928/manifest.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g81-posterior-wall-expansion-20260928/root_analysis.json')
ARM = "g81_posterior_wall_v1"
COMPONENTS = ("plain_self_win_delta", "special_self_win_delta", "other_win_delta", "draw_delta")
SEED = 2026122805
REPLICATES = 20_000


def sha(path: Path) -> str:
    """完整输入及分析脚本 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """对 12 个根分别在 H/M 池内有放回重采样；不调整候选或分组。"""

    if OUT.exists():
        raise SystemExit("G81 根级分析已存在，拒绝覆盖")
    result = json.loads(INPUT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (result["manifest_sha256"] != sha(MANIFEST) or result["complete_tables"] != 384
            or manifest["arms"] != ["r18_v2", ARM]):
        raise ValueError("G81 第二批评测身份或完整桌数漂移")
    rng = np.random.default_rng(SEED)
    summaries = {}
    sampled = {}
    for mix in ("H", "M"):
        rows = sorted((row for row in result["root_clusters"] if row["mix"] == mix),
                      key=lambda row: row["root_index"])
        if len(rows) != 12 or [row["root_index"] for row in rows] != list(range(1, 13)):
            raise ValueError("G81 第二批池内根号或数量漂移")
        values = np.asarray([row["delta_vs_baseline_per_table"][ARM] for row in rows], dtype=float)
        picks = rng.integers(0, len(values), size=(REPLICATES, len(values)))
        sampled[mix] = values[picks].mean(axis=1)
        components = {name: float(np.mean([
            row["component_delta_vs_baseline_per_table"][ARM][name] for row in rows
        ])) for name in COMPONENTS}
        if abs(sum(components.values()) - float(values.mean())) > 1e-9:
            raise ValueError("G81 根级收入分量与净分不守恒")
        summaries[mix] = {"roots": len(rows), "root_deltas": values.tolist(),
                          "mean_delta_per_complete_table": float(values.mean()),
                          "root_bootstrap_95": [float(np.quantile(sampled[mix], .025)),
                                                float(np.quantile(sampled[mix], .975))],
                          "positive_roots": int(np.sum(values > 0)),
                          "zero_roots": int(np.sum(values == 0)),
                          "negative_roots": int(np.sum(values < 0)),
                          "component_mean": components}
    combined_samples = (sampled["H"] + sampled["M"]) / 2.0
    combined = (summaries["H"]["mean_delta_per_complete_table"] +
                summaries["M"]["mean_delta_per_complete_table"]) / 2.0
    result_out = {"schema": "g81-expansion-root-analysis/1", "bootstrap_seed": SEED,
                  "bootstrap_replicates": REPLICATES,
                  "source_sha256": {"manifest": sha(MANIFEST), "result": sha(INPUT),
                                    "script": sha(Path(__file__))},
                  "by_mix": summaries,
                  "combined_mean_delta_per_complete_table": combined,
                  "combined_root_bootstrap_95": [float(np.quantile(combined_samples, .025)),
                                                 float(np.quantile(combined_samples, .975))],
                  "expansion_gate_passed": (summaries["H"]["mean_delta_per_complete_table"] > 0
                                            and summaries["M"]["mean_delta_per_complete_table"] > 0
                                            and combined >= 2
                                            and result["g81_metrics"]["counts"].get("fallback", 0) == 0
                                            and result["g81_metrics"]["counts"].get("adopted", 0) > 0),
                  "boundary": "开发扩样根级描述区间；不能作为一次性独立发布确认。"}
    OUT.write_text(json.dumps(result_out, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result_out.items() if key != "source_sha256"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
