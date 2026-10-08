#!/usr/bin/env python3
"""G221：新 H/M 牌山根的 R18 v2／结算路线候选成对完整桌开发。"""

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
import g210_post_claim_guarded_familiar_policy as parent
import g221_settlement_route_policy as candidate


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G221-SETTLEMENT-ROUTE-CANDIDATE-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g221-settlement-route-panel-20260929')
SEED = 20261229221
ROOTS = tuple(range(1, 5))
ARMS = ("r18_v2", "g221_settlement_route_v1")


def digest(path: Path) -> str:
    """绑定候选、规则、合同与预登记的原始字节。"""
    return sha256(path.read_bytes()).hexdigest()


def run_unit(unit: tuple[str, int, int, str, int]) -> dict:
    """一个 H/M×根×座位×策略臂运行两张完整八单局桌。"""
    mix, root, seat, arm, panel_seed = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=panel_seed)
    metrics: list[dict] = []
    factory = (parent.parent_factory if arm == ARMS[0]
               else candidate.policy_factory(metrics))
    stage = panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    stage["g221_metrics"] = metrics
    return {"mix": mix, "root_index": root, "focal_seat": seat,
            "arm": arm, "stage": stage}


def manifest() -> dict:
    """任何完整桌结果打开前冻结输入身份、根与发布基线。"""
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    return {
        "schema": "g221-settlement-route-panel-manifest/1",
        "panel_seed": SEED, "roots_per_mix": len(ROOTS), "root_start": ROOTS[0],
        "mixes": list(panel.MIXES), "seats": list(panel.SEATS),
        "arms": list(ARMS),
        "tables_per_stage": int(contract["group"]["tables_per_group"]),
        "planned_complete_tables": 128,
        "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in (
            PREREG, Path(__file__), _project_file(_PROJECT_ROOT, HERE / "g221_settlement_route_policy.py"),
            _project_file(_PROJECT_ROOT, HERE / "g219_two_draw_settlement_route.py"),
            _project_file(_PROJECT_ROOT, HERE / "g220_future_qualification_audit.py"),
            _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"),
            panel.paired.CONTRACT)},
        "statistical_unit": "对手池×独立牌山根；四座与两张桌先根内平均",
        "boundary": "新根开发，不替代独立确认、官方规则／时限／接线门。",
    }


def summarize_metrics(units: list[tuple[str, int, int, str, int]]) -> dict:
    """逐对手池计触达和安全性，决策不充当独立统计样本。"""
    counts = {mix: Counter() for mix in panel.MIXES}
    changed_roots = {mix: set() for mix in panel.MIXES}
    elapsed = []
    width = Counter()
    highfan = Counter()
    for unit in units:
        if unit[3] != ARMS[1]:
            continue
        path = panel.paired.unit_path(OUT, unit)
        stage = json.loads(path.read_text(encoding="utf-8"))["stage"]
        for row in stage["g221_metrics"]:
            counts[unit[0]][row["status"]] += 1
            if row["status"] == "adopted":
                changed_roots[unit[0]].add(unit[1])
                width["static_strict_wider" if row["type_gain"] > 0
                      and row["capacity_gain"] > 0 else "not_static_strict_wider"] += 1
                highfan["positive" if row["half_special_gain"] > 0 else
                        "negative" if row["half_special_gain"] < 0 else "equal"] += 1
            elapsed.append(row["elapsed_ms"])
    elapsed.sort()
    return {
        "per_mix": {mix: dict(sorted(value.items())) for mix, value in counts.items()},
        "changed_roots": {mix: len(values) for mix, values in changed_roots.items()},
        "width_of_changes": dict(sorted(width.items())),
        "special_gain_sign_of_changes": dict(sorted(highfan.items())),
        "selector_elapsed_ms": {} if not elapsed else {
            name: elapsed[int((len(elapsed) - 1) * fraction)]
            for name, fraction in (("p50", .5), ("p95", .95), ("max", 1.0))},
    }


def main() -> None:
    """阶段独立落盘且可恢复；全部完成后才计算根级配对分差。"""
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
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_unit, unit): unit for unit in pending}
            for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
                unit = futures[future]
                row = future.result()
                panel.verify_unit(row, unit=unit,
                                  tables_per_stage=frozen["tables_per_stage"])
                panel._write_new(panel.paired.unit_path(OUT, unit), row)
                if count % 8 == 0 or count == len(pending):
                    print(json.dumps({"new_units_completed": count,
                                      "new_units_planned": len(pending)}), flush=True)
    if any(not panel.paired.unit_path(OUT, unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress", "units_completed": sum(
            panel.paired.unit_path(OUT, unit).exists() for unit in units),
            "units_planned": len(units)}), flush=True)
        return
    panel_args = type("PanelArgs", (), {
        "root_start": ROOTS[0], "roots_per_mix": len(ROOTS)})()
    result = panel._result(args=panel_args, arms=ARMS, units=units,
                           out=OUT, tables_per_stage=frozen["tables_per_stage"])
    result["g221_metrics"] = summarize_metrics(units)
    result["manifest_sha256"] = digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    result["script_sha256"] = digest(Path(__file__))
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"complete_tables": result["complete_tables"],
                      "g221_metrics": result["g221_metrics"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
