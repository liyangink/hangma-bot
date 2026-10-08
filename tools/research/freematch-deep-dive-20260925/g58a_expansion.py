#!/usr/bin/env python3
"""G58A：锁定派生源码，在 H/M 各 12 个未见根做四座完整桌扩样。"""

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

import concurrent.futures
from collections import Counter
import json
from pathlib import Path

import g58a_paired_pilot as pilot


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g58a-contextual-width-expansion-20260927')
SEED = 2026122802
ROOTS = tuple(range(1, 13))
ARMS = pilot.ARMS
panel = pilot.panel
FROZEN = {
    "g58a_author_program.py": "0b65f5edaffa75b3da05d454ebe9962e98118da6442c3d52b2f5b4b6a7770349",
    "g58a_contextual_width_policy.py": "5f8169c6ba8dc343e6b4e7d511e0f881e86c34cc1dfe14e77a1090c54d3aa553",
    "g58a_paired_pilot.py": "0499c8934f9fdb7fdf90b99502092cabf1272332bda43badc38f9f3abbe5390b",
    "evidence/g58a-contextual-width-pilot-20260927/result.json": "4e4acb1cd0c85afc3301310f029c51f09b261faa32ce8a70362b33a4ecbf6d56",
}


def manifest() -> dict:
    """先验证候选和小批摘要，再锁新牌山与评测核心。"""

    for name, expected in FROZEN.items():
        if pilot.sha(_project_file(_PROJECT_ROOT, HERE / name)) != expected:
            raise ValueError(f"G58A 预登记输入漂移：{name}")
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    return {
        "schema": "g58a-contextual-width-expansion/1",
        "panel_seed": SEED,
        "roots_per_mix": len(ROOTS),
        "root_start": ROOTS[0],
        "mixes": list(panel.MIXES),
        "seats": list(panel.SEATS),
        "arms": list(ARMS),
        "tables_per_stage": int(contract["group"]["tables_per_group"]),
        "planned_complete_tables": 384,
        "rules_source_hash": panel.natural.compute_rules_hash(pilot.ROOT),
        "inputs_sha256": {path.name: pilot.sha(path) for path in (
            _project_file(_PROJECT_ROOT, HERE / "G58A-CONTEXTUAL-WIDTH-EXPANSION-PREREG-2026-09-27.md"),
            _project_file(_PROJECT_ROOT, HERE / "g58a_author_program.py"),
            _project_file(_PROJECT_ROOT, HERE / "g58a_contextual_width_policy.py"),
            _project_file(_PROJECT_ROOT, HERE / "g58a_paired_pilot.py"),
            _project_file(_PROJECT_ROOT, HERE / "g58a_expansion.py"),
            _project_file(_PROJECT_ROOT, HERE / "evidence/g58a-contextual-width-pilot-20260927/result.json"),
            panel.paired.CONTRACT)},
        "statistical_unit": "对手池×牌山根；四座及每阶段两桌在根内平均",
        "boundary": "新根开发扩样；不得与 G58A 首批合并成独立确认。",
    }


def metrics(units: list[tuple[str, int, int, str, int]]) -> dict:
    """汇总实际改选和异常回退，不把动作数当统计样本量。"""

    counts = Counter()
    by_mix = {mix: Counter() for mix in panel.MIXES}
    elapsed = []
    for unit in units:
        if unit[3] != ARMS[1]:
            continue
        stage = json.loads(panel.paired.unit_path(OUT, unit).read_text(encoding="utf-8"))["stage"]
        for row in stage["g58a_metrics"]:
            counts[row["status"]] += 1
            by_mix[unit[0]][row["status"]] += 1
            if "elapsed_ms" in row:
                elapsed.append(row["elapsed_ms"])
    elapsed.sort()
    return {"counts": dict(sorted(counts.items())),
            "per_mix": {mix: dict(sorted(count.items())) for mix, count in by_mix.items()},
            "elapsed_ms": {} if not elapsed else {
                name: elapsed[int((len(elapsed) - 1) * fraction)]
                for name, fraction in (("p50", .5), ("p95", .95), ("max", 1.0))}}


def main() -> None:
    """逐阶段保存并复核，全部 384 桌结算后才读取根级分差。"""

    frozen = manifest()
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), frozen)
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
        completed = 0
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as workers:
            futures = {workers.submit(pilot.run_unit, unit): unit for unit in pending}
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
    args = type("PanelArgs", (), {"root_start": ROOTS[0],
                                   "roots_per_mix": len(ROOTS)})()
    result = panel._result(args=args, arms=ARMS, units=units,
                           out=OUT, tables_per_stage=frozen["tables_per_stage"])
    result["g58a_metrics"] = metrics(units)
    result["manifest_sha256"] = pilot.sha(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    result["script_sha256"] = pilot.sha(Path(__file__))
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    deltas = {mix: [row["delta_vs_baseline_per_table"][ARMS[1]]
                    for row in result["root_clusters"] if row["mix"] == mix]
              for mix in panel.MIXES}
    print(json.dumps({"complete_tables": result["complete_tables"],
                      "mean_delta_by_mix": {mix: sum(values) / len(values)
                                            for mix, values in deltas.items()},
                      "g58a_metrics": result["g58a_metrics"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
