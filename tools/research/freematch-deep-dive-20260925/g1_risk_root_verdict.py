#!/usr/bin/env python3
"""按对手池×牌山根归约 RISK0 完整桌配对与运行故障。"""

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

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import statistics


ARM = "candidate@review/freematch-deep-dive-20260925/candidates/OPTY-R18-G1-RISK0.py"
SOURCE_SHA256 = "a293d5094fce71adaa1dfb7ca9d268100e33996c1e4908caf0ae9b0a5a3794a8"
RUNTIME_FAILURE_FIELDS = (
    "audit_missing", "auto_actions", "fallbacks", "illegal_choices", "timeouts",
)
EXECUTION_FAILURE_FIELDS = ("action_value_failed", "ambiguous_diagnostics")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile_interval(values: list[float], draws: int, seed: int) -> list[float]:
    """只把一整个根当一次抽样，区间为固定种子的经验分位。"""
    rng = random.Random(seed)
    n = len(values)
    estimates = sorted(statistics.fmean(values[rng.randrange(n)] for _ in range(n))
                       for _ in range(draws))
    return [estimates[int(0.025 * (draws - 1))],
            estimates[int(0.975 * (draws - 1))]]


def stratified_interval(h: list[float], m: list[float], draws: int, seed: int) -> list[float]:
    """H/M 每次分别按根重抽，保留两池等权，不混抽桌或座位。"""
    rng = random.Random(seed)
    nh, nm = len(h), len(m)
    estimates = sorted((
        statistics.fmean(h[rng.randrange(nh)] for _ in range(nh))
        + statistics.fmean(m[rng.randrange(nm)] for _ in range(nm))
    ) / 2 for _ in range(draws))
    return [estimates[int(0.025 * (draws - 1))],
            estimates[int(0.975 * (draws - 1))]]


def summarize(values: list[float], draws: int, seed: int) -> dict:
    return {
        "roots": len(values), "mean_per_table": statistics.fmean(values),
        "bootstrap_95": percentile_interval(values, draws, seed),
        "positive_roots": sum(value > 0 for value in values),
        "negative_roots": sum(value < 0 for value in values),
        "zero_roots": sum(value == 0 for value in values),
    }


def main() -> None:
    """一次性核对身份、根与阶段完整性；结果写到证据目录 analysis.json。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--panel-seed", type=int, required=True)
    parser.add_argument("--roots-per-mix", type=int, required=True)
    parser.add_argument("--bootstrap-seed", type=int, required=True)
    parser.add_argument("--draws", type=int, default=20_000)
    args = parser.parse_args()
    target = args.directory / "analysis.json"
    if target.exists():
        raise FileExistsError("分析文件已存在，拒绝覆盖")
    manifest_path, result_path = args.directory / "manifest.json", args.directory / "result.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if (manifest["panel_seed"] != args.panel_seed
            or manifest["roots_per_mix"] != args.roots_per_mix
            or manifest["arms"] != ["r18_v2", ARM]
            or manifest.get("candidate_sources", {}).get(ARM) != SOURCE_SHA256):
        raise ValueError("冻结面板/候选身份不符")
    if result["complete_tables"] != manifest["planned_complete_tables"]:
        raise ValueError("结果桌数与清单不符")
    roots = result["root_clusters"]
    expected = {(mix, i) for mix in ("H", "M")
                for i in range(1, args.roots_per_mix + 1)}
    if {(row["mix"], row["root_index"]) for row in roots} != expected:
        raise ValueError("根集合不完整或重复")
    stage_paths = list((args.directory / "stages").glob("*.json"))
    if len(stage_paths) != len(expected) * 4 * 2:
        raise ValueError("阶段文件数不完整")
    runtime = Counter()
    identities = Counter()
    for path in stage_paths:
        stage = json.loads(path.read_text(encoding="utf-8"))["stage"]
        if stage["status"] != "complete" or len(stage["tables"]) != 2:
            raise ValueError("存在非完整阶段：" + str(path))
        for table in stage["tables"]:
            if table["result"]["status"] != "complete":
                raise ValueError("存在非完整桌：" + str(path))
            for field in RUNTIME_FAILURE_FIELDS:
                runtime[field] += (table["result"].get("runtime_counts") or {}).get(field, 0)
            execution = table.get("policy_execution") or {}
            for field in EXECUTION_FAILURE_FIELDS:
                runtime[field] += execution.get(field, 0)
            identities.update(execution.get("policy_ids_by_seat") or [])
    h = [row["delta_vs_baseline_per_table"][ARM] for row in roots if row["mix"] == "H"]
    m = [row["delta_vs_baseline_per_table"][ARM] for row in roots if row["mix"] == "M"]
    h_result = summarize(h, args.draws, args.bootstrap_seed + 1)
    m_result = summarize(m, args.draws, args.bootstrap_seed + 2)
    overall_mean = (h_result["mean_per_table"] + m_result["mean_per_table"]) / 2
    overall_ci = stratified_interval(h, m, args.draws, args.bootstrap_seed)
    complete_and_reliable = (len(stage_paths) == len(expected) * 8
                             and result["complete_tables"] == len(stage_paths) * 2
                             and all(runtime[field] == 0 for field in
                                     RUNTIME_FAILURE_FIELDS + EXECUTION_FAILURE_FIELDS))
    pass_confirmation = (complete_and_reliable and overall_mean >= 2.0
                         and overall_ci[0] > 0
                         and h_result["mean_per_table"] > 0
                         and m_result["mean_per_table"] > 0)
    analysis = {
        "schema": "g1-risk-root-verdict/1",
        "manifest_sha256": sha(manifest_path),
        "paired_result_sha256": sha(result_path),
        "script_sha256": sha(Path(__file__)),
        "bootstrap": {"draws": args.draws, "seed": args.bootstrap_seed,
                      "unit": "opponent_mix×root_index", "stratified_equal_mix": True},
        "pools": {"H": h_result, "M": m_result},
        "overall": {"roots": len(roots), "mean_per_table": overall_mean,
                    "bootstrap_95": overall_ci,
                    "positive_roots": h_result["positive_roots"] + m_result["positive_roots"],
                    "negative_roots": h_result["negative_roots"] + m_result["negative_roots"]},
        "completed_stages": len(stage_paths),
        "complete_tables": result["complete_tables"],
        "runtime_failure_counts": dict(sorted(runtime.items())),
        "focal_policy_id_counts": {key: value for key, value in sorted(identities.items())
                                   if "RISK0" in key or "r18-integrated-positive-v2" in key},
        "complete_and_reliable": complete_and_reliable,
        "passes_independent_confirmation_gate": pass_confirmation,
        "note": "开发批次仅检验方向；布尔确认门只对事先冻结的独立确认批次适用。",
    }
    target.write_text(json.dumps(analysis, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"overall": analysis["overall"], "pools": analysis["pools"],
                      "runtime_failure_counts": analysis["runtime_failure_counts"],
                      "passes_independent_confirmation_gate": pass_confirmation},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
