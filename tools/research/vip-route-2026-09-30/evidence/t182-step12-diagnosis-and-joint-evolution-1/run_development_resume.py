"""仅用两个后台研究槽续跑原DEV未开始桌；原run_table、globals、规则和采样不改。"""
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

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import close_development as dev
import run_development as runtime
import prepare_development_resume as scheduling

HERE = Path(__file__).resolve().parent
RUNNER = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/run_development_resume.py')


def task_directory(task):
    """新收据独立于原桌目录；0起始序号只用于固定分区和关联。"""
    return scheduling.EVIDENCE / "tasks" / f"task-{task['ordinal']:04d}"


def identity(plan, plan_pin, worker, task=None):
    """记录调度/原计划/包装器原字节身份，不向原模拟器加入新输入。"""
    record = {"schedule_plan_pin": plan_pin, "original_plan_pin": plan["original_plan_pin"],
              "new_runner_pin": plan["files"][str(RUNNER)], "worker": worker}
    if task is not None:
        record["task"] = task
    return record


async def run_one(task, plan, plan_pin, original):
    """前后新收据夹住原函数一次调用；失败不重试，不触及另一worker。"""
    worker = task["worker"]
    scheduling.stable(plan, plan_pin)
    dev.require(not Path(task["directory"]).exists(), "原桌目录已存在，禁止重试或覆盖")
    receipts = task_directory(task)
    receipts.mkdir(parents=True, exist_ok=False)
    before = {"schema": "t182-development-resource-task-before/1", **identity(plan, plan_pin, worker, task),
              "pid": os.getpid(), "unix_seconds": time.time(), "original_directory_absent": True,
              "original_run_table_called": False, "score_based_selection": False}
    scheduling.new_json(receipts / "BEFORE.json", before)
    before_pin = dev.pin(receipts / "BEFORE.json")
    failure, files, called, complete, source_stable, pin_errors = None, {}, False, False, False, []
    started = time.monotonic()
    try:
        # 原函数有自己的START、费用、捕获和CLOSURE；不修改模块globals或传入计划。
        scheduling.stable(plan, plan_pin)
        dev.require(not Path(task["directory"]).exists(), "执行前原目录出现，停止而不重试")
        called = True
        await runtime.run_table(task["index"], task["rotation"], task["arm_index"], original)
        files = scheduling.completed_metadata(task, original, plan["original_plan_pin"])
        scheduling.stable(plan, plan_pin)
        dev.require(dev.pin(receipts / "BEFORE.json") == before_pin, "执行前收据漂移")
        source_stable = True
        complete = True
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        if not complete:
            try:
                files = scheduling.table_pins(task, require_all=False, pin_errors=pin_errors)
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
                pin_errors.append({"path": task["directory"], "type": type(error).__name__, "message": str(error)})
            try:
                scheduling.stable(plan, plan_pin)
                dev.require(dev.pin(receipts / "BEFORE.json") == before_pin, "执行前收据漂移")
                source_stable = True
            except BaseException as error:
                source_stable = False
                failure = failure or {"type": type(error).__name__, "message": str(error)}
        after = {"schema": "t182-development-resource-task-after/1", **identity(plan, plan_pin, worker, task),
                 "pid": os.getpid(), "unix_seconds": time.time(), "before_pin": before_pin,
                 "original_run_table_called": called, "complete": complete, "failure": failure,
                 "source_stable": source_stable, "original_table_files": files,
                 "original_table_pin_errors": pin_errors,
                 "elapsed_monotonic_seconds": time.monotonic() - started,
                 "other_worker_interrupted": False, "normal_fallbacks_allowed": False,
                 "deadline_admission": False, "release_admission": False}
        scheduling.new_json(receipts / "AFTER.json", after)
    print(json.dumps({"worker": worker, "ordinal": task["ordinal"], "complete": complete,
                      "failure": failure}, ensure_ascii=False), flush=True)
    if not complete:
        raise RuntimeError("该研究槽停止；原桌/费用/新收据保留，不重试:" + str(failure))
    return {str(receipts / name): dev.pin(receipts / name) for name in ("BEFORE.json", "AFTER.json")}


async def main(worker):
    """一个进程只推进固定奇偶槽；槽锁限制最多两个CPU worker，模拟不持共用赛后锁。"""
    dev.require(type(worker) is int and worker in (0, 1), "仅允许冻结worker0或1")
    scheduling.background_priority()
    with scheduling.research_lock(f"worker-{worker}"):
        plan, plan_pin, original = scheduling.read_schedule(verify_old_evidence=True)
        dev.require(runtime.HERE == HERE and runtime.ROOT == scheduling.ROOT and dev.HERE == HERE,
                    "原函数目录与冻结研究目录不符")
        assigned = [o for o in plan["not_started_ordinals"] if o % 2 == worker]
        directory = scheduling.EVIDENCE / f"worker-{worker}"
        directory.mkdir(parents=True, exist_ok=False)
        start = {"schema": "t182-development-resource-worker-start/1", **identity(plan, plan_pin, worker),
                 "pid": os.getpid(), "unix_seconds": time.time(), "assigned_ordinals": assigned,
                 "max_cpu_workers": 2, "nice": os.getpriority(os.PRIO_PROCESS, 0),
                 "macos_background_io": True, "common_postprocess_lock_held": False,
                 "original_function": "run_development.run_table", "original_globals_modified": False,
                 "normal_fallbacks_allowed": False, "score_based_selection": False}
        scheduling.new_json(directory / "START.json", start)
        start_pin = dev.pin(directory / "START.json")
        started = time.monotonic()
        attempted, completed, receipts, failure, source_stable = [], [], {}, None, False
        try:
            for ordinal in assigned:
                attempted.append(ordinal)
                receipts.update(await run_one(plan["tasks"][ordinal], plan, plan_pin, original))
                completed.append(ordinal)
            scheduling.stable(plan, plan_pin)
            scheduling.old_evidence_stable(plan)
            dev.require(dev.pin(directory / "START.json") == start_pin, "worker START漂移")
            for path, expected in receipts.items():
                dev.require(dev.pin(Path(path)) == expected, "新桌收据漂移:" + path)
            source_stable = True
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            # 失败桌的AFTER也被冻结；不能让失败的最后一次尝试从worker留档中消失。
            if attempted:
                failed_dir = task_directory(plan["tasks"][attempted[-1]])
                for name in ("BEFORE.json", "AFTER.json"):
                    path = failed_dir / name
                    if path.is_file():
                        try:
                            receipts[str(path)] = dev.pin(path)
                        except BaseException as secondary:
                            failure["receipt_pin_error"] = type(secondary).__name__ + ": " + str(secondary)
        finally:
            actual_calls, unknown_calls = 0, []
            for ordinal in attempted:
                path = task_directory(plan["tasks"][ordinal]) / "AFTER.json"
                try:
                    record, _ = dev.read(path)
                    called = record.get("original_run_table_called")
                    dev.require(type(called) is bool, "实际原函数调用状态未知")
                    actual_calls += int(called)
                except BaseException:
                    unknown_calls.append(ordinal)
            if unknown_calls:
                failure = failure or {"type": "UnknownCallReceipt", "message": "实际原函数调用数未知，禁止完成"}
            complete = failure is None and source_stable and completed == assigned
            close = {"schema": "t182-development-resource-worker-close/1", **identity(plan, plan_pin, worker),
                     "pid": os.getpid(), "unix_seconds": time.time(), "worker_start_pin": start_pin,
                     "assigned_ordinals": assigned, "attempted_ordinals": attempted, "completed_ordinals": completed,
                     "complete": complete, "failure": failure, "source_stable": source_stable,
                     "task_receipt_files": receipts, "actual_original_run_table_calls": actual_calls,
                     "unknown_call_ordinals": unknown_calls,
                     "elapsed_monotonic_seconds": time.monotonic() - started,
                     "other_worker_interrupted": False, "models_added_by_scheduler": 0,
                     "normal_fallbacks_allowed": False, "deadline_admission": False, "release_admission": False}
            scheduling.new_json(directory / "CLOSE.json", close)
        print(json.dumps({"worker": worker, "closed": complete, "assigned": len(assigned), "completed": len(completed),
                          "failure": failure, "other_worker_interrupted": False}, ensure_ascii=False), flush=True)
        if not complete:
            raise RuntimeError("worker未知/失败，保留原件；整批不得授完成:" + str(failure))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=int, choices=(0, 1), required=True)
    try:
        asyncio.run(main(parser.parse_args().worker))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, IndexError, AttributeError) as error:
        print(json.dumps({"status": "unknown_or_invalid_worker_stopped", "error_type": type(error).__name__,
                          "reason": str(error), "original_evidence_retained": True,
                          "other_worker_interrupted": False}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
