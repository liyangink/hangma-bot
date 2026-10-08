#!/usr/bin/env python3
"""G216：同种子无观察包装父代复跑，排除记录器改变行为。"""

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
import json
from pathlib import Path

import g13_accounted_panel as accounted
import g14_accounted_paired_panel as panel
import g210_post_claim_guarded_familiar_policy as parent
import g216_visible_reach_calibration as reach


OUT = reach.OUT / "parity.json"


def verify(unit: tuple[str, int, int]) -> dict:
    """同一完整阶段由未包装父代复跑，与记录臂逐桌分与逐局账对拍。"""
    mix, root, seat = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=reach.SEED)
    plain = accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=parent.parent_factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    archive_path = reach.stage_path(*unit)
    archive = json.loads(archive_path.read_text(encoding="utf-8"))["stage"]
    if (plain["status"] != "complete" or archive["status"] != "complete"
            or plain["focal_stage_score"] != archive["focal_stage_score"]
            or len(plain["tables"]) != 2 or len(archive["tables"]) != 2):
        raise ValueError("未包装父代与记录臂阶段不一致")
    for raw, recorded in zip(plain["tables"], archive["tables"]):
        for key in ("table_id", "seed", "scores_by_seat", "policy_execution",
                    "hand_account", "hand_records"):
            if raw[key] != recorded[key]:
                raise ValueError(f"G216 观察包装改变 {unit} 的 {key}")
        if raw["result"]["runtime_counts"] != recorded["result"]["runtime_counts"]:
            raise ValueError("G216 观察包装改变运行计数")
    return {"mix": mix, "root_index": root, "start_seat": seat,
            "archived_stage_sha256": reach.digest(archive_path),
            "complete_tables_equal": 2}


def main() -> None:
    """只对已存 G216 64 桌对拍，输出一次性证明。"""
    if OUT.exists():
        raise FileExistsError(OUT)
    units = [(mix, root, seat) for mix in reach.MIXES
             for root in reach.ROOTS for seat in reach.SEATS]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as workers:
        futures = {workers.submit(verify, unit): unit for unit in units}
        rows = []
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            rows.append(future.result())
            if count % 8 == 0:
                print(json.dumps({"verified_stages": count}), flush=True)
    rows.sort(key=lambda row: (row["mix"], row["root_index"], row["start_seat"]))
    reach.write_new(OUT, {
        "schema": "g216-observer-parity/1",
        "manifest_sha256": reach.digest(reach.OUT / "manifest.json"),
        "complete_stages_equal": len(rows),
        "complete_tables_equal": sum(row["complete_tables_equal"] for row in rows),
        "rows": rows,
        "boundary": "记录器行为恒等性核验；不把重复同种子桌当候选增益样本。",
    })


if __name__ == "__main__":
    main()
