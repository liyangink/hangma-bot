#!/usr/bin/env python3
"""G74：新 H/M 根、四座换位完整桌小批，验收单张字牌帕累托候选。"""

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
import concurrent.futures
import hashlib
import json
from pathlib import Path

import g14_accounted_paired_panel as panel
import g74_single_honor_policy as candidate


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g74-single-honor-pilot-20260928')
SEED = 2026122803
ROOTS = (1, 2, 3, 4)
ARMS = ("r18_v2", "g74_single_honor_pareto_v1")


def sha(path: Path) -> str:
    """绑定候选、行为门和评测契约。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_unit(unit: tuple[str, int, int, str, int]) -> dict:
    """两臂从相同牌山根完整桌首独立运行，记录候选改选及回退。"""

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
    stage["g74_metrics"] = metrics
    return {"mix": mix, "root_index": root, "focal_seat": seat,
            "arm": arm, "stage": stage}


def manifest() -> dict:
    """在任何桌赛结算前冻结行为门、源码和新牌山根。"""

    behavior = json.loads((_project_file(_PROJECT_ROOT, HERE / "evidence/g74-single-honor-behavior-20260928/result.json")).read_text(encoding="utf-8"))
    if (behavior["schema"] != "g74-single-honor-behavior/1"
            or behavior["counts"]["changed"] < 100 or behavior["changed_tables"] < 50
            or behavior["source_sha256"]["candidate"] != sha(_project_file(_PROJECT_ROOT, HERE / "g74_single_honor_policy.py"))):
        raise ValueError("G74 结果盲行为门未通过或候选源码漂移")
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    return {"schema": "g74-single-honor-pilot/1", "panel_seed": SEED,
            "roots_per_mix": len(ROOTS), "root_start": ROOTS[0],
            "mixes": list(panel.MIXES), "seats": list(panel.SEATS),
            "arms": list(ARMS),
            "tables_per_stage": int(contract["group"]["tables_per_group"]),
            "planned_complete_tables": 128,
            "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
            "inputs_sha256": {path.name: sha(path) for path in (
                _project_file(_PROJECT_ROOT, HERE / "G74-SINGLE-HONOR-PARETO-PREREG-2026-09-28.md"),
                _project_file(_PROJECT_ROOT, HERE / "g74_single_honor_policy.py"),
                _project_file(_PROJECT_ROOT, HERE / "g74_behavior_screen.py"),
                _project_file(_PROJECT_ROOT, HERE / "g74_paired_pilot.py"),
                _project_file(_PROJECT_ROOT, HERE / "evidence/g74-single-honor-behavior-20260928/result.json"),
                panel.paired.CONTRACT)},
            "statistical_unit": "对手池×牌山根；四座及每阶段两桌在根内平均",
            "boundary": "新根开发小批；不构成独立发布确认或线上时限证明。"}


def metrics(units: list[tuple[str, int, int, str, int]]) -> dict:
    """汇总实际改选、异常回退和本机选择器耗时。"""

    counts = Counter()
    by_mix = {mix: Counter() for mix in panel.MIXES}
    elapsed = []
    for unit in units:
        if unit[3] != ARMS[1]:
            continue
        stage = json.loads(panel.paired.unit_path(OUT, unit).read_text(encoding="utf-8"))["stage"]
        for row in stage["g74_metrics"]:
            counts[row["status"]] += 1
            by_mix[unit[0]][row["status"]] += 1
            if "elapsed_ms" in row:
                elapsed.append(row["elapsed_ms"])
    elapsed.sort()
    return {"counts": dict(sorted(counts.items())),
            "per_mix": {mix: dict(sorted(value.items())) for mix, value in by_mix.items()},
            "elapsed_ms": {} if not elapsed else {
                name: elapsed[int((len(elapsed)-1)*fraction)]
                for name, fraction in (("p50", .5), ("p95", .95), ("max", 1.0))}}


def main() -> None:
    frozen = manifest()
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != frozen:
            raise ValueError("G74 已冻结清单与当前输入不符")
    else:
        panel._write_new(manifest_path, frozen)
    units = [(mix, root, seat, arm, SEED)
             for mix in panel.MIXES for root in ROOTS
             for seat in panel.SEATS for arm in ARMS]
    pending = []
    for unit in units:
        path = panel.paired.unit_path(OUT, unit)
        if path.exists():
            panel.verify_unit(json.loads(path.read_text(encoding="utf-8")), unit=unit,
                              tables_per_stage=frozen["tables_per_stage"])
        else:
            pending.append(unit)
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as workers:
            futures = {workers.submit(run_unit, unit): unit for unit in pending}
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                unit = futures[future]
                row = future.result()
                panel.verify_unit(row, unit=unit,
                                  tables_per_stage=frozen["tables_per_stage"])
                panel._write_new(panel.paired.unit_path(OUT, unit), row)
                completed += 1
                if completed % 16 == 0 or completed == len(pending):
                    print(json.dumps({"completed_units": completed,
                                      "total_units": len(pending)}), flush=True)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("G74 完整小批结果已存在，拒绝覆盖")
    args = type("PanelArgs", (), {"root_start": ROOTS[0],
                                   "roots_per_mix": len(ROOTS)})()
    result = panel._result(args=args, arms=ARMS, units=units,
                           out=OUT, tables_per_stage=frozen["tables_per_stage"])
    result["g74_metrics"] = metrics(units)
    result["manifest_sha256"] = sha(manifest_path)
    result["script_sha256"] = sha(Path(__file__))
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    deltas = {mix: [row["delta_vs_baseline_per_table"][ARMS[1]]
                    for row in result["root_clusters"] if row["mix"] == mix]
              for mix in panel.MIXES}
    print(json.dumps({"complete_tables": result["complete_tables"],
                      "mean_delta_by_mix": {mix: sum(values)/len(values)
                                            for mix, values in deltas.items()},
                      "g74_metrics": result["g74_metrics"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
