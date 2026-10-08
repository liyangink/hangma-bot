#!/usr/bin/env python3
"""G32：逐根验算扩批分数、收益分量和保守赛事效用边界。"""

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
import hashlib
import json
from pathlib import Path
import statistics

import g14_accounted_paired_panel as panel


HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g32-edge-paired-expansion-20260927')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g32-edge-paired-expansion-20260927/result.json')
MANIFEST = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g32-edge-paired-expansion-20260927/manifest.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g32-edge-paired-expansion-20260927/analysis.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G30-EDGE-TIE-ONEWHITE-V1.py')
EXPECTED_SOURCE_SHA = "bdfaf823e5b52718f3eefef5ac9972ee455dc9742dfda560c1b53f4e238ae7b2"
T95 = {12: 2.200985, 24: 2.068658}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interval(values: list[float]) -> dict:
    """根级 t 区间；池间同号才有推进意义，不把桌当独立单位。"""

    n = len(values)
    if n not in T95:
        raise ValueError("本分析仅支持预登记的 12/24 根规模")
    mean = statistics.mean(values)
    radius = T95[n] * statistics.stdev(values) / (n ** 0.5)
    return {"n": n, "mean": mean, "lower_95": mean - radius,
            "upper_95": mean + radius, "positive": sum(value > 0 for value in values),
            "negative": sum(value < 0 for value in values),
            "zero": sum(value == 0 for value in values), "values": values}


def main() -> None:
    """所有 192 阶段、384 桌、3,072 单局机械核验后才算效果。"""

    if OUT.exists():
        raise SystemExit("G32 分析已存在，拒绝覆盖")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    arms = manifest["arms"]
    if (sha(CANDIDATE) != EXPECTED_SOURCE_SHA or manifest["panel_seed"] != 2026122703 or
            manifest["roots_per_mix"] != 12 or manifest["planned_complete_tables"] != 384 or
            arms[0] != "r18_v2" or manifest["candidate_sources"][arms[1]] != EXPECTED_SOURCE_SHA or
            result["baseline_arm"] != arms[0] or result["complete_tables"] != 384 or
            result["independent_root_clusters"] != 24):
        raise ValueError("G32 面板或候选身份漂移")
    audits = Counter()
    u_bounds = {}
    for mix in manifest["mixes"]:
        for root in range(manifest["root_start"], manifest["root_start"] + 12):
            lower = []
            upper = []
            for seat in manifest["seats"]:
                stages = {}
                for arm in arms:
                    unit = (mix, root, seat, arm, manifest["panel_seed"])
                    path = panel.paired.unit_path(EVIDENCE, unit)
                    stage_row = json.loads(path.read_text(encoding="utf-8"))
                    panel.verify_unit(stage_row, unit=unit,
                                      tables_per_stage=manifest["tables_per_stage"])
                    stage = stage_row["stage"]
                    execution = stage["execution_review"]
                    if execution["status"] != "complete" or execution["zero_internal_failures_verified"] is not True:
                        raise ValueError("G32 执行审查不完整或内部失败未证零")
                    if any(execution["recorded_failure_kinds"].values()) or execution["recorded_counts"]["action_value_failed"]:
                        raise ValueError("G32 存在动作价值评分失败")
                    audits["complete_stages"] += 1
                    audits["complete_tables"] += len(stage["tables"])
                    audits["complete_hands"] += sum(table["hand_account"]["complete_hands"] for table in stage["tables"])
                    audits["action_value_scored"] += execution["recorded_counts"]["action_value_scored"]
                    stages[arm] = stage
                candidate = stages[arms[1]]
                baseline = stages[arms[0]]
                lower.append(candidate["u_low"] - baseline["u_high"])
                upper.append(candidate["u_high"] - baseline["u_low"])
            u_bounds[(mix, root)] = {"conservative_low": statistics.mean(lower),
                                     "conservative_high": statistics.mean(upper)}
    if audits["complete_stages"] != 192 or audits["complete_tables"] != 384 or audits["complete_hands"] != 3072:
        raise ValueError("G32 阶段/桌/单局数量不符")
    roots = {(row["mix"], row["root_index"]): row for row in result["root_clusters"]}
    if len(roots) != 24 or set(roots) != set(u_bounds):
        raise ValueError("G32 根级结果身份不符")
    score_by_mix = {}
    component_by_mix = {}
    u_by_mix = {}
    for mix in manifest["mixes"]:
        group = [roots[(mix, root)] for root in range(1, 13)]
        score_by_mix[mix] = interval([row["delta_vs_baseline_per_table"][arms[1]] for row in group])
        component_by_mix[mix] = {name: statistics.mean(
            row["component_delta_vs_baseline_per_table"][arms[1]][name] for row in group)
            for name in panel.COMPONENTS}
        u_by_mix[mix] = {name: statistics.mean(u_bounds[(mix, root)][name] for root in range(1, 13))
                         for name in ("conservative_low", "conservative_high")}
    all_values = [roots[(mix, root)]["delta_vs_baseline_per_table"][arms[1]]
                  for mix in manifest["mixes"] for root in range(1, 13)]
    paired_values = [statistics.mean(roots[(mix, root)]["delta_vs_baseline_per_table"][arms[1]]
                                     for mix in manifest["mixes"]) for root in range(1, 13)]
    if abs(statistics.mean(all_values) - result["descriptive_mean_delta_vs_baseline_per_table"][arms[1]]) > 1e-9:
        raise ValueError("G32 逐根均值与面板结果不符")
    analysis = {"schema": "g32-edge-expansion-analysis/1",
                "manifest_sha256": sha(MANIFEST), "result_sha256": sha(RESULT),
                "candidate_source_sha256": sha(CANDIDATE), "script_sha256": sha(Path(__file__)),
                "audits": dict(sorted(audits.items())),
                "score_by_mix": score_by_mix,
                "score_combined_24_mix_root_clusters": interval(all_values),
                "score_combined_12_paired_roots": interval(paired_values),
                "component_delta_by_mix": component_by_mix,
                "u_conservative_delta_by_mix": u_by_mix,
                "u_conservative_delta_combined": {
                    name: statistics.mean(value[name] for value in u_bounds.values())
                    for name in ("conservative_low", "conservative_high")},
                "root_u_bounds": {f"{mix}-r{root:02d}": values for (mix, root), values in sorted(u_bounds.items())},
                "boundary": "开发根配对 t 区间；H/M 若共用根索引可能相关，故另报 12 个配对根区间；无独立确认或官方接线证据。"}
    OUT.write_text(json.dumps(analysis, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"score_by_mix": score_by_mix,
                      "combined_12": analysis["score_combined_12_paired_roots"],
                      "u": analysis["u_conservative_delta_by_mix"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
