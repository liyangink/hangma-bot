#!/usr/bin/env python3
"""G193：早期三向听候选的可恢复、同牌山四座完整桌开发面板。"""

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
import concurrent.futures
from hashlib import sha256
import json
from pathlib import Path

import g14_accounted_paired_panel as panel
import g193_early_shape_policy as candidate


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G193-EARLY-THREE-SHANTEN-CANDIDATE-PREREG-2026-09-29.md')
EXPOSURE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g192-three-shanten-exposure-20260929/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g193-early-shape-development-20260929')
SEED = 20261229193
ROOTS = tuple(range(1, 33))
ARMS = ("r18_v2", "g193_early_three_shanten_v1")


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def run_unit(unit: tuple[str, int, int, str, int]) -> dict:
    """每臂独立实例与指标，父代和候选共用固定牌山身份。"""
    mix, root, seat, arm, panel_seed = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=panel_seed)
    records: list[dict] = []
    factory = (candidate.research_parent_factory if arm == ARMS[0]
               else candidate.policy_factory(records))
    stage = panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    stage["g193_metrics"] = records
    return {"mix": mix, "root_index": root, "focal_seat": seat,
            "arm": arm, "stage": stage}


def manifest() -> dict:
    """绑定源码、面板、规则和覆盖证据；运行后不得重算覆盖阈值。"""
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    exposure = json.loads(EXPOSURE.read_text(encoding="utf-8"))
    if (exposure.get("schema") != "g192-three-shanten-exposure/1"
            or exposure.get("source_tables") != 256
            or exposure.get("three_shanten_windows") != 169):
        raise ValueError("G193 结果盲覆盖证据不符")
    return {
        "schema": "g193-early-shape-development-manifest/1",
        "panel_seed": SEED, "roots_per_mix": len(ROOTS),
        "root_start": ROOTS[0], "mixes": list(panel.MIXES),
        "seats": list(panel.SEATS), "arms": list(ARMS),
        "tables_per_stage": int(contract["group"]["tables_per_group"]),
        "planned_complete_tables": 1024,
        "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "input_sha256": {path.name: digest(path) for path in (
            PREREG, EXPOSURE, _project_file(_PROJECT_ROOT, HERE / "g193_early_shape_policy.py"),
            Path(__file__), panel.paired.CONTRACT)},
        "statistical_unit": "对手池×牌山根；四座与每阶段两桌先根内平均",
        "boundary": "全新根完整桌开发；不替代独立确认和官方时限/接线。",
    }


def summarize_metrics(units: list[tuple[str, int, int, str, int]]) -> dict:
    """候选改选覆盖与选择器耗时，同根多动作不冒充独立样本。"""
    counts = Counter()
    by_mix = {mix: Counter() for mix in panel.MIXES}
    roots = {mix: set() for mix in panel.MIXES}
    elapsed = []
    for unit in units:
        if unit[3] != ARMS[1]:
            continue
        path = panel.paired.unit_path(OUT, unit)
        stage = json.loads(path.read_text(encoding="utf-8"))["stage"]
        for row in stage["g193_metrics"]:
            counts[row["status"]] += 1
            by_mix[unit[0]][row["status"]] += 1
            if row["status"] == "adopted":
                roots[unit[0]].add(unit[1])
            if "elapsed_ms" in row:
                elapsed.append(row["elapsed_ms"])
    elapsed.sort()
    return {
        "counts": dict(sorted(counts.items())),
        "per_mix": {mix: dict(sorted(value.items())) for mix, value in by_mix.items()},
        "changed_roots": {mix: len(values) for mix, values in roots.items()},
        "selector_elapsed_ms": {} if not elapsed else {
            name: elapsed[int((len(elapsed) - 1) * fraction)]
            for name, fraction in (("p50", 0.5), ("p95", 0.95), ("max", 1.0))},
    }


def main() -> None:
    """阶段断点恢复；仅全量双臂核验后聚合收益。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new-units", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("工作进程必须在 1..4")
    frozen = manifest()
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), frozen)
    units = [(mix, root, seat, arm, SEED)
             for mix in panel.MIXES for root in ROOTS
             for seat in panel.SEATS for arm in ARMS]
    pending = []
    for unit in units:
        path = panel.paired.unit_path(OUT, unit)
        if path.exists():
            panel.verify_unit(json.loads(path.read_text(encoding="utf-8")),
                              unit=unit, tables_per_stage=frozen["tables_per_stage"])
        else:
            pending.append(unit)
    if args.max_new_units > 0:
        pending = pending[:args.max_new_units]
    if pending:
        completed = 0
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as workers:
            futures = {workers.submit(run_unit, unit): unit for unit in pending}
            for future in concurrent.futures.as_completed(futures):
                unit = futures[future]
                row = future.result()
                panel.verify_unit(row, unit=unit,
                                  tables_per_stage=frozen["tables_per_stage"])
                panel._write_new(panel.paired.unit_path(OUT, unit), row)
                completed += 1
                if completed % 16 == 0 or completed == len(pending):
                    print(json.dumps({"new_units_completed": completed,
                                      "new_units_planned": len(pending)}), flush=True)
    if any(not panel.paired.unit_path(OUT, unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress", "units_completed":
                          sum(panel.paired.unit_path(OUT, unit).exists()
                              for unit in units), "units_planned": len(units)}),
              flush=True)
        return
    panel_args = type("PanelArgs", (), {
        "root_start": ROOTS[0], "roots_per_mix": len(ROOTS)})()
    result = panel._result(args=panel_args, arms=ARMS, units=units,
                           out=OUT, tables_per_stage=frozen["tables_per_stage"])
    result["g193_metrics"] = summarize_metrics(units)
    result["manifest_sha256"] = digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    result["script_sha256"] = digest(Path(__file__))
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"complete_tables": result["complete_tables"],
                      "g193_metrics": result["g193_metrics"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
