#!/usr/bin/env python3
"""G239：冻结数牌路线候选与 R18 v2 的全新 H/M 同墙换座完整桌开发。"""

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
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path

import g14_accounted_paired_panel as panel
import g239_numeric_route_policy as candidate


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G239-NUMERIC-ROUTE-FULL-TABLE-PREREG-2026-09-29.md')
EXPOSURE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g238-all-window-numeric-exposure-20260929/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g239-numeric-route-development-20260929')
SEED = 20261229337
ROOTS = tuple(range(1, 33))
ARMS = ("r18_v2", "g239_numeric_route")


def digest(path: Path) -> str:
    """把事前判据、父代与候选源码绑定到同一清单。"""
    return sha256(path.read_bytes()).hexdigest()


def run_unit(unit: tuple[str, int, int, str, int]) -> dict:
    """每臂独立实例；同种子、同座位、同对手池完成八局阶段。"""
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
    stage["g239_metrics"] = records
    return {"mix": mix, "root_index": root, "focal_seat": seat,
            "arm": arm, "stage": stage}


def manifest() -> dict:
    """核独立行为材料，固定未见牌山与两臂源码身份。"""
    exposure = json.loads(EXPOSURE.read_text(encoding="utf-8"))
    if (exposure.get("schema") != "g238-all-window-numeric-exposure-result/1"
            or exposure.get("material_gate_pass") is not True
            or exposure.get("complete_tables_verified") != 128):
        raise ValueError("G239 新根行为材料门未通过")
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    return {
        "schema": "g239-numeric-route-development-manifest/1",
        "panel_seed": SEED, "mixes": list(panel.MIXES),
        "roots": list(ROOTS), "seats": list(panel.SEATS),
        "arms": list(ARMS),
        "tables_per_stage": int(contract["group"]["tables_per_group"]),
        "planned_complete_tables": 1024,
        "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in (
            PLAN, EXPOSURE,
            _project_file(_PROJECT_ROOT, HERE / "g237_numeric_inversion_policy.py"),
            _project_file(_PROJECT_ROOT, HERE / "g239_numeric_route_policy.py"), Path(__file__),
            panel.paired.CONTRACT,
            _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"))},
        "statistical_unit": "H/M×独立牌山根；四座两桌先根内平均",
        "boundary": "全新根完整桌开发，仍需独立确认和官方规则／时限／接线门。",
    }


def summarize_metrics(units: list[tuple[str, int, int, str, int]]) -> dict:
    """真实改选窗口、桌和根，以及选择器实际耗时。"""
    counts = Counter()
    per_mix = {mix: Counter() for mix in panel.MIXES}
    roots = {mix: set() for mix in panel.MIXES}
    tables = {mix: set() for mix in panel.MIXES}
    elapsed = []
    for unit in units:
        if unit[3] != ARMS[1]:
            continue
        stage = json.loads(panel.paired.unit_path(OUT, unit).read_text(encoding="utf-8"))[
            "stage"]
        for row in stage["g239_metrics"]:
            counts[row["status"]] += 1
            per_mix[unit[0]][row["status"]] += 1
            if row["status"] == "adopted":
                roots[unit[0]].add(unit[1])
                tables[unit[0]].add(":".join(row["decision_id"].split(":")[:2]))
            if "elapsed_ms" in row:
                elapsed.append(row["elapsed_ms"])
    elapsed.sort()
    return {
        "counts": dict(sorted(counts.items())),
        "per_mix": {mix: dict(sorted(value.items())) for mix, value in per_mix.items()},
        "changed_roots": {mix: len(values) for mix, values in roots.items()},
        "changed_tables": {mix: len(values) for mix, values in tables.items()},
        "selector_elapsed_ms": {} if not elapsed else {
            name: elapsed[int((len(elapsed) - 1) * fraction)]
            for name, fraction in (("p50", 0.5), ("p95", 0.95), ("max", 1.0))},
    }


def main() -> None:
    """可断点续跑；只在 1,024 张臂别桌齐备后聚合收益。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-units", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
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
        with ProcessPoolExecutor(max_workers=args.workers) as workers:
            futures = {workers.submit(run_unit, unit): unit for unit in pending}
            for count, future in enumerate(as_completed(futures), 1):
                unit = futures[future]
                value = future.result()
                panel.verify_unit(value, unit=unit,
                                  tables_per_stage=frozen["tables_per_stage"])
                panel._write_new(panel.paired.unit_path(OUT, unit), value)
                if count % 16 == 0 or count == len(pending):
                    print(json.dumps({"new_units": count,
                                      "planned_new_units": len(pending)}), flush=True)
    if any(not panel.paired.unit_path(OUT, unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress", "units_complete": sum(
            panel.paired.unit_path(OUT, unit).exists() for unit in units)}), flush=True)
        return
    panel_args = type("PanelArgs", (), {
        "root_start": ROOTS[0], "roots_per_mix": len(ROOTS)})()
    result = panel._result(args=panel_args, arms=ARMS, units=units,
                           out=OUT, tables_per_stage=frozen["tables_per_stage"])
    result["g239_metrics"] = summarize_metrics(units)
    result["manifest_sha256"] = digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    result["script_sha256"] = digest(Path(__file__))
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"complete_tables": result["complete_tables"],
                      "mean_delta": result["descriptive_mean_delta_vs_baseline_per_table"],
                      "metrics": result["g239_metrics"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
