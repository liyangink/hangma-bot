"""全512原桌及两个真实worker闭合后调用原DEV读回；不重写开发统计和准入规则。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import sys
from contextlib import ExitStack
from pathlib import Path

import close_development as dev
import close_development_readout_repair as repair
import prepare_development_resume as scheduling
import run_development_resume as worker_runtime

HERE = Path(__file__).resolve().parent
OUTPUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/RESOURCE-SCHEDULING-CLOSED.json')


def record_identity(record, plan, plan_pin, worker, task=None):
    """核新收据关联；原START仍只绑定原DEV计划。"""
    for key, expected in worker_runtime.identity(plan, plan_pin, worker, task).items():
        dev.require(record.get(key) == expected, "新调度收据身份不符:" + key)


def collect_worker(slot, plan, plan_pin, original):
    """无积分预检：核成功worker真实START/CLOSE及其每次原函数前后收据。"""
    directory = scheduling.EVIDENCE / f"worker-{slot}"
    start, start_pin = dev.read(directory / "START.json")
    close, close_pin = dev.read(directory / "CLOSE.json")
    assigned = [o for o in plan["not_started_ordinals"] if o % 2 == slot]
    record_identity(start, plan, plan_pin, slot)
    record_identity(close, plan, plan_pin, slot)
    dev.require(start.get("schema") == "t182-development-resource-worker-start/1" and
                close.get("schema") == "t182-development-resource-worker-close/1", "worker收据版本不符")
    pid = dev.integer(start.get("pid"), "worker PID", 1)
    dev.require(close.get("pid") == pid and close.get("worker_start_pin") == start_pin and
                start.get("assigned_ordinals") == assigned and
                all(close.get(k) == assigned for k in ("assigned_ordinals", "attempted_ordinals", "completed_ordinals")),
                "worker序号不齐/越区/重复或START未绑定")
    dev.require(start.get("max_cpu_workers") == 2 and dev.integer(start.get("nice"), "worker nice", 15) >= 15 and
                start.get("macos_background_io") is True and start.get("common_postprocess_lock_held") is False and
                start.get("original_function") == "run_development.run_table" and
                start.get("original_globals_modified") is False and start.get("score_based_selection") is False and
                start.get("normal_fallbacks_allowed") is False, "worker资源/原实现/分区声明不符")
    dev.require(close.get("complete") is True and close.get("source_stable") is True and close.get("failure") is None and
                close.get("actual_original_run_table_calls") == len(assigned) and close.get("unknown_call_ordinals") == [] and
                close.get("other_worker_interrupted") is False and close.get("models_added_by_scheduler") == 0 and
                all(close.get(k) is False for k in ("normal_fallbacks_allowed", "deadline_admission", "release_admission")),
                "worker未成功真实闭合或未知/失败")
    files = {str(directory / "START.json"): start_pin, str(directory / "CLOSE.json"): close_pin}
    receipts, tables = {}, {}
    for ordinal in assigned:
        task = plan["tasks"][ordinal]
        receipt_dir = worker_runtime.task_directory(task)
        before, before_pin = dev.read(receipt_dir / "BEFORE.json")
        after, after_pin = dev.read(receipt_dir / "AFTER.json")
        record_identity(before, plan, plan_pin, slot, task)
        record_identity(after, plan, plan_pin, slot, task)
        dev.require(before.get("schema") == "t182-development-resource-task-before/1" and
                    after.get("schema") == "t182-development-resource-task-after/1" and
                    before.get("pid") == pid and after.get("pid") == pid and after.get("before_pin") == before_pin,
                    "原函数前后收据版本/PID/绑定不符")
        dev.require(before.get("original_directory_absent") is True and before.get("original_run_table_called") is False and
                    before.get("score_based_selection") is False and after.get("original_run_table_called") is True and
                    after.get("complete") is True and after.get("failure") is None and after.get("source_stable") is True and
                    after.get("original_table_pin_errors") == [] and
                    after.get("other_worker_interrupted") is False and
                    all(after.get(k) is False for k in ("normal_fallbacks_allowed", "deadline_admission", "release_admission")),
                    "原桌未开始/原函数调用/闭合收据不完整")
        actual = scheduling.completed_metadata(task, original, plan["original_plan_pin"])
        dev.require(after.get("original_table_files") == actual, "新调度后的原桌原件漂移或缺失")
        tables.update(actual)
        receipts.update({str(receipt_dir / "BEFORE.json"): before_pin, str(receipt_dir / "AFTER.json"): after_pin})
    dev.require(close.get("task_receipt_files") == receipts, "worker新桌收据冻结集合遗漏/新增/漂移")
    files.update(receipts)
    files.update(tables)
    return files


def file_set_stable(files):
    """流式重核全pin，不解码原评分或生成统计。"""
    for path, expected in files.items():
        dev.require(dev.pin(Path(path)) == expected, "调度读回期间原件漂移:" + path)


def main():
    """只有两槽成功及全批原件稳定才调用dev.main；外层不持共用赛后锁，避免嵌套死锁。"""
    scheduling.background_priority()
    dev.require(not OUTPUT.exists(), "调度闭合已存在，拒绝覆盖")
    dev.require(not dev.OUTPUT.exists(), "原DEV已闭合，拒绝补写调度闭合或重算")
    # 两个研究槽都已释放才可闭合；本进程不操作其他进程，也不持postprocess.lock。
    with ExitStack() as locks:
        for slot in (0, 1):
            locks.enter_context(scheduling.research_lock(f"worker-{slot}"))
        plan, plan_pin, original = scheduling.read_schedule(verify_old_evidence=True)
        files = dict(plan["files"])
        files[str(scheduling.PLAN)] = plan_pin
        files.update(plan["old_completed_files"])
        for slot in (0, 1):
            files.update(collect_worker(slot, plan, plan_pin, original))
        expected_tables = {str(Path(t["directory"]) / n) for t in plan["tasks"] for n in scheduling.TABLE_FILES}
        dev.require(expected_tables <= set(files), "完整512原桌元数据/评分原文件分母不齐")
        task_dirs = {p.resolve() for p in (scheduling.EVIDENCE / "tasks").glob("task-*") if p.is_dir()}
        dev.require(task_dirs == {worker_runtime.task_directory(plan["tasks"][o]).resolve() for o in plan["not_started_ordinals"]},
                    "新桌收据目录越计划或遗漏")
        scheduling.stable(plan, plan_pin)
        file_set_stable(files)
        # 修复main自行nice15/后台IO并等待共用锁；此处没有持该锁。
        # 原预检/account/comparisons/bootstrap/选择不变，严格校正对手诊断和对象ID的记录格式。
        repair.main()
        readout, readout_pin = dev.read(dev.OUTPUT)
        dev.require(readout.get("schema") == "t182-natural-development-closed/1" and
                    readout.get("complete") is True and readout.get("source_stable") is True and
                    readout.get("planned_table_instances") == 512 and readout.get("actual_table_instances") == 512 and
                    readout.get("completed_hand_instances") == 4096 and readout.get("independent_mother_sources") == 32 and
                    readout.get("selection_is_development_screen_only") is True and
                    readout.get("readout_schema_repair") == "production_opponent_diagnostics_and_object_ids_only_v1" and
                    all(readout.get(k) is False for k in
                        ("deadline_admission", "confirmation_admission", "strength_admission", "release_admission")),
                    "原DEV读回没有按冻结完整分母闭合")
        dev.require(type(readout.get("files")) is dict and all(files.get(p) == h for p, h in readout["files"].items()),
                    "原开发闭合与调度冻结原件不同")
        files[str(dev.OUTPUT)] = readout_pin
        scheduling.stable(plan, plan_pin)
        file_set_stable(files)
        result = {"schema": "t182-development-resource-scheduling-closed/1", "complete": True,
                  "source_stable": True, "original_plan_pin": plan["original_plan_pin"], "schedule_plan_pin": plan_pin,
                  "original_development_closed_pin": readout_pin, "files": files,
                  "source_manifest": plan["source_manifest"], "original_table_instances": 512,
                  "old_complete_table_instances": 14, "new_complete_table_instances": 498,
                  "completed_hand_instances": 4096, "actual_successful_workers": [0, 1], "max_cpu_workers": 2,
                  "partition": "worker=ordinal%2", "normal_fallbacks_allowed": False,
                  "original_run_table_globals_rules_seeds_scoring_unchanged": True,
                  "resource_scheduling_only_not_new_statistical_method": True, "new_scores_computed_by_scheduler": 0,
                  "repaired_dev_readout_called_once_after_all_terminals": True,
                  "old_original_readout_failed_probe_preserved": True,
                  "readout_schema_repair": "production_opponent_diagnostics_and_object_ids_only_v1",
                  "common_postprocess_lock_held_by_wrapper": False,
                  "deadline_admission": False, "confirmation_admission": False,
                  "strength_admission": False, "release_admission": False}
        scheduling.new_json(OUTPUT, result)
    print(json.dumps({"complete": True, "output": str(OUTPUT), "original_complete_tables": 512,
                      "resource_scheduling_only": True, "release_admission": False}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, IndexError, AttributeError) as error:
        print(json.dumps({"complete": False, "status": "unknown_or_invalid_no_resource_admission",
                          "error_type": type(error).__name__, "reason": str(error),
                          "original_evidence_retained": True, "release_admission": False}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
