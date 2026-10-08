"""等待窄候选的完整独立确认门；不沿用T185胜者、开发分数或中途结果。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import math
from pathlib import Path

from prepare_runtime_inputs import HERE, PLAN, ROOT, STAGE, pin, require


def strength_gate(summary, plan, dispatch, terminal):
    """核完整128来源、四换座配对和事前净分判据；输入缺失或未知均拒绝。"""
    require(plan["schema"] == "t191-single-confirmation/1" and len(plan["candidates"]) == 1 and
        plan["root_indices"] == list(range(1, 129)) and all(type(v) is int for v in plan["root_indices"]) and
        plan["planned_table_instances"] == 1024 and
        plan["minimum_mean_points_per_complete_table"] == 0.5 and
        plan["strictly_positive_lower95_required"] is True, "不是事前唯一确认范围")
    require(summary["schema"] == "t191-independent-confirmation-readout/1" and
        summary["complete"] is True and summary["source_stable"] is True and
        type(summary["actual_complete_tables"]) is int and summary["actual_complete_tables"] == 1024 and
        type(summary["actual_single_hands"]) is int and summary["actual_single_hands"] == 8192 and
        summary["all_resources_naturally_released"] is True and len(summary["comparisons"]) == 1 and
        type(summary["actual_focal_scores"]) is int and summary["actual_focal_scores"] > 0,
        "独立确认分母、完整性或自然资源未知")
    require(dispatch["complete"] is True and dispatch["failure"] is None and
        dispatch["resources_released"] is True and dispatch["worker_returncodes"] == [0, 0, 0, 0] and
        all(type(v) is int for v in dispatch["worker_returncodes"]) and
        type(dispatch["actual_table_calls"]) is int and dispatch["actual_table_calls"] == 1024 and
        type(dispatch["verified_complete_table_calls"]) is int and dispatch["verified_complete_table_calls"] == 1024 and
        terminal["complete"] is True and
        terminal["failure"] is None and terminal["observation_timed_out"] is False and
        terminal["observed_job_terminal_claimed"] is True and
        type(terminal["actual_reader_exit_code"]) is int and terminal["actual_reader_exit_code"] == 0,
        "真实执行和读回终态未闭合")
    row = summary["comparisons"][0]
    require(row["identity"] == plan["candidates"][0]["identity"] and len(row["sources"]) == 128,
        "确认候选或来源身份不同")
    mean, interval = row["mean_delta_per_complete_table"]["net"], row["independent_net_bootstrap95"]
    require(type(mean) in (int, float) and math.isfinite(mean) and mean >= 0.5 and
        type(interval) is list and len(interval) == 2 and
        all(type(v) in (int, float) and math.isfinite(v) for v in interval) and
        0 < interval[0] <= interval[1] and row["independent_strength_admission"] is True and
        summary["independent_strength_admission"] is True, "事前独立净分门未通过")
    total = 0
    for index, source in enumerate(row["sources"], 1):
        require(type(source["root"]) is int and source["root"] == index and
            source["root_id"] == plan["roots"][index - 1]["root_id"] and
            len(source["paired_tables"]) == 4 and
            [p["rotation"] for p in source["paired_tables"]] == [0, 1, 2, 3] and
            all(type(p["rotation"]) is int for p in source["paired_tables"]), "独立母来源/换座配对缺漏")
        values = [p["delta"]["net"] for p in source["paired_tables"]]
        source_total = source["four_seat_delta_sums"]["net"]
        require(all(type(v) is int for v in values) and type(source_total) is int and
            sum(values) == source_total, "四座来源净分未对账")
        total += source_total
    require(mean == total / 512, "独立均值与512配对桌不对账")
    return row


def read_accepted_confirmation(verify_raw_files=False):
    """只接受真实整批读回及原件绑定；确认未结束时在任何编译/评分之前拒绝。"""
    plan = json.loads(PLAN.read_text())
    directory = Path(plan["dispatch_directory"])
    terminal_path = PLAN.with_name("wait-confirmation-001-READBACK-TERMINAL.json")
    summary_path, dispatch_path = directory / "SUMMARY.json", directory / "CLOSED.json"
    terminal = json.loads(terminal_path.read_text())
    summary = json.loads(summary_path.read_text())
    dispatch = json.loads(dispatch_path.read_text())
    plan_pin = pin(PLAN)
    require(summary["plan_pin"] == dispatch["plan_pin"] == terminal["plan_pin"] == plan_pin and
        terminal["summary_pin"] == pin(summary_path) and
        summary["files"].get(str(dispatch_path)) == pin(dispatch_path), "读回与执行原件未互相绑定")
    row = strength_gate(summary, plan, dispatch, terminal)
    from hangma_bot import bootstrap
    actual_sources = bootstrap._vip_runtime_sources()
    require(set(actual_sources) == set(plan["source_manifest"]) and
        all(actual_sources[name] == expected["sha256"] and pin(_project_file(_PROJECT_ROOT, ROOT / name)) == expected
            for name, expected in plan["source_manifest"].items()) and
        all(pin(Path(p)) == expected for p, expected in plan["files"].items()), "确认后源码或输入漂移")
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / "CLOSED.json")).read_text())
    require(preparation["complete"] is True and preparation["source_stable"] is True and
        preparation["candidate"] == plan["candidates"][0], "编译输入未绑定确认胜者")
    if verify_raw_files:
        require(all(pin(Path(p)) == expected for p, expected in summary["files"].items()), "完整确认原件漂移")
    return plan, row, {str(p): pin(p) for p in (PLAN, terminal_path, summary_path, dispatch_path, _project_file(_PROJECT_ROOT, HERE / "CLOSED.json"))}


if __name__ == "__main__":
    read_accepted_confirmation()
    print("complete independent confirmation accepted; no compilation/scoring/HTTP")
