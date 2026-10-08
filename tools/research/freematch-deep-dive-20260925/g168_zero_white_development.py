#!/usr/bin/env python3
"""G168：冻结候选在全新 H/M 同牌山四座完整桌的可恢复开发面板。"""

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
import hashlib
import json
from pathlib import Path

import g14_accounted_paired_panel as panel
import g168_zero_white_first_width_policy as candidate


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G168-ZEROWHITE-FIRST-WIDTH-DEVELOPMENT-PREREG-2026-09-28.md')
BEHAVIOR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g168-zero-white-behavior-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g168-zero-white-development-20260928')
SEED = 20261228168
ROOTS = tuple(range(1, 17))
ARMS = ("r18_v2", "g168_zero_white_first_width_v1")


def sha(path: Path) -> str:
    """将面板预登记、候选及合同绑定到运行清单。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_unit(unit: tuple[str, int, int, str, int]) -> dict:
    """同一牌山的父代与研究候选各运行一个完整阶段，不共享状态。"""
    mix, root, seat, arm, panel_seed = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=panel_seed)
    metrics: list[dict] = []
    factory = (panel.paired.policy_factory("r18_v2") if arm == ARMS[0]
               else candidate.policy_factory(metrics))
    stage = panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    stage["g168_metrics"] = metrics
    return {"mix": mix, "root_index": root, "focal_seat": seat,
            "arm": arm, "stage": stage}


def manifest() -> dict:
    """在新牌山运行前固定评测边界和所有源码摘要。"""
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    behavior = json.loads(BEHAVIOR.read_text(encoding="utf-8"))
    if not behavior["behavior_gate_pass"]:
        raise ValueError("G168 行为门未通过")
    return {
        "schema": "g168-zero-white-development-manifest/1",
        "panel_seed": SEED,
        "roots_per_mix": len(ROOTS),
        "root_start": ROOTS[0],
        "mixes": list(panel.MIXES),
        "seats": list(panel.SEATS),
        "arms": list(ARMS),
        "tables_per_stage": int(contract["group"]["tables_per_group"]),
        "planned_complete_tables": 512,
        "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "input_sha256": {path.name: sha(path) for path in (
            PREREG, _project_file(_PROJECT_ROOT, HERE / "g168_zero_white_first_width_policy.py"),
            Path(__file__), BEHAVIOR, panel.paired.CONTRACT)},
        "statistical_unit": "对手池×牌山根；四座与每阶段两桌先根内平均",
        "boundary": "全新根开发桌赛，非独立发布确认或官方线上时限验收。",
    }


def metrics(units: list[tuple[str, int, int, str, int]]) -> dict:
    """只对候选臂计实际改选、保护、异常及局部选择器耗时。"""
    counts = Counter()
    per_mix = {mix: Counter() for mix in panel.MIXES}
    changed_roots = {mix: set() for mix in panel.MIXES}
    elapsed = []
    for unit in units:
        if unit[3] != ARMS[1]:
            continue
        stage = json.loads(panel.paired.unit_path(OUT, unit).read_text(
            encoding="utf-8"))["stage"]
        for row in stage["g168_metrics"]:
            counts[row["status"]] += 1
            per_mix[unit[0]][row["status"]] += 1
            if row["status"] == "adopted":
                changed_roots[unit[0]].add(unit[1])
            if "elapsed_ms" in row:
                elapsed.append(row["elapsed_ms"])
    elapsed.sort()
    return {"counts": dict(sorted(counts.items())),
            "per_mix": {mix: dict(sorted(value.items()))
                        for mix, value in per_mix.items()},
            "changed_roots": {mix: len(roots) for mix, roots in changed_roots.items()},
            "selector_elapsed_ms": {} if not elapsed else {
                name: elapsed[int((len(elapsed) - 1) * fraction)]
                for name, fraction in (("p50", 0.5), ("p95", 0.95), ("max", 1.0))}}


def main() -> None:
    """逐阶段断点恢复；父代与候选阶段全部合法完成后才汇总收益。"""
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
                if completed % 8 == 0 or completed == len(pending):
                    print(json.dumps({"new_units_completed": completed,
                                      "new_units_planned": len(pending)}), flush=True)
    if any(not panel.paired.unit_path(OUT, unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress", "units_completed":
                          sum(panel.paired.unit_path(OUT, unit).exists() for unit in units),
                          "units_planned": len(units)}), flush=True)
        return
    panel_args = type("PanelArgs", (), {
        "root_start": ROOTS[0], "roots_per_mix": len(ROOTS)})()
    result = panel._result(args=panel_args, arms=ARMS, units=units,
                           out=OUT, tables_per_stage=frozen["tables_per_stage"])
    result["g168_metrics"] = metrics(units)
    result["manifest_sha256"] = sha(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    result["script_sha256"] = sha(Path(__file__))
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    delta = {mix: [row["delta_vs_baseline_per_table"][ARMS[1]]
                   for row in result["root_clusters"] if row["mix"] == mix]
             for mix in panel.MIXES}
    print(json.dumps({"complete_tables": result["complete_tables"],
                      "root_mean_delta_by_pool": {
                          mix: sum(values) / len(values) for mix, values in delta.items()},
                      "g168_metrics": result["g168_metrics"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
