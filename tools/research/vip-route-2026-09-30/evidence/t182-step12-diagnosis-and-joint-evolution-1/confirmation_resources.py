"""确认的资源证据与固定研究槽；不生成世界、评分或修改计分统计。"""
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

import fcntl
import sys
from contextlib import contextmanager
from pathlib import Path

import close_development as dev

HERE = Path(__file__).resolve().parent
RESOURCE_CLOSED = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/RESOURCE-SCHEDULING-CLOSED.json')
RESOURCE_PLAN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/RESOURCE-SCHEDULING-PLAN.json')
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/confirmation-resources')
TABLE_FILES = ("START.json", "CLOSURE.json", "PAIRING-IDENTITY.json", "focal-decisions.jsonl.gz", "views.jsonl.gz")


def verify_files(files):
    """只在准备／启动／最终统一IO阶段核大文件；逐桌不重复这些读取。"""
    dev.require(type(files) is dict, "缺资源原件冻结集合")
    for path, expected in files.items():
        dev.require(dev.pin(Path(path)) == expected, "资源原证据漂移:" + path)


def development_resource_evidence(development_pin, development_plan_pin, *, verify=False):
    """必须有完整资源闭合，且回指本次DEV字节；DEV先落盘而包装器半闭合不得准入。"""
    closure, closure_pin = dev.read(RESOURCE_CLOSED)
    schedule, schedule_pin = dev.read(RESOURCE_PLAN)
    original, original_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))
    dev.require(original_pin == development_plan_pin, "资源绑定的原DEV计划字节不符")
    dev.require(closure.get("schema") == "t182-development-resource-scheduling-closed/1" and
                closure.get("complete") is True and closure.get("source_stable") is True and
                closure.get("original_development_closed_pin") == development_pin and
                closure.get("original_plan_pin") == development_plan_pin and
                closure.get("schedule_plan_pin") == schedule_pin, "开发资源未完整闭合或未绑定本次DEV")
    dev.require(closure.get("original_table_instances") == 512 and closure.get("old_complete_table_instances") == 14 and
                closure.get("new_complete_table_instances") == 498 and closure.get("completed_hand_instances") == 4096 and
                closure.get("actual_successful_workers") == [0, 1] and closure.get("max_cpu_workers") == 2 and
                closure.get("partition") == "worker=ordinal%2" and closure.get("normal_fallbacks_allowed") is False and
                closure.get("original_run_table_globals_rules_seeds_scoring_unchanged") is True and
                closure.get("resource_scheduling_only_not_new_statistical_method") is True and
                closure.get("repaired_dev_readout_called_once_after_all_terminals") is True and
                closure.get("old_original_readout_failed_probe_preserved") is True and
                closure.get("common_postprocess_lock_held_by_wrapper") is False and
                closure.get("new_scores_computed_by_scheduler") == 0 and all(closure.get(k) is False for k in
                    ("deadline_admission", "confirmation_admission", "strength_admission", "release_admission")),
                "开发资源闭合的完整分母／原实现／准入边界不符")
    dev.require(schedule.get("schema") == "t182-development-resource-scheduling/1" and
                schedule.get("workers") == [0, 1] and schedule.get("max_cpu_workers") == 2 and
                schedule.get("original_plan_pin") == development_plan_pin and schedule.get("planned_table_instances") == 512 and
                schedule.get("old_completed_ordinals") == list(range(14)) and
                schedule.get("not_started_ordinals") == list(range(14, 512)) and
                schedule.get("partition") == "worker=ordinal%2", "资源计划不是原14+498分母")
    files = closure.get("files")
    dev.require(type(files) is dict and files.get(str(RESOURCE_PLAN)) == schedule_pin and
                files.get(str(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json"))) == development_pin and
                files.get(str(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))) == development_plan_pin and
                all(files.get(p) == h for p, h in schedule["files"].items()) and
                all(files.get(p) == h for p, h in schedule["old_completed_files"].items()),
                "资源闭合未冻结原计划／DEV／资源包装器／旧14桌")
    for name in ("prepare_development_resume.py", "run_development_resume.py", "close_development_resume.py",
                 "RESOURCE-SCHEDULING-CONTRACT.md", "RESOURCE-OLD-RUNNER-HANDOFF.json", "RESOURCE-OLD-RUNNER-EXIT.json",
                 "RESOURCE-OBSERVATION-001.json"):
        dev.require(str(_project_file(_PROJECT_ROOT, HERE / name)) in schedule["files"], "资源未冻结必要包装器／交接事实:" + name)
    checkpoint = schedule.get("old_runner_checkpoint")
    dev.require(type(checkpoint) is dict and checkpoint.get("root_confirmed_safe_exit") is True and
                checkpoint.get("actual_command_absent") is True and checkpoint.get("all_started_have_complete_closure") is True,
                "资源原研究进程安全交接未知")
    tasks = schedule.get("tasks")
    expected_tasks = []
    for index, root in enumerate(original["roots"], 1):
        for rotation in original["rotations"]:
            for arm in range(1 + len(original["candidates"])):
                ordinal = len(expected_tasks)
                expected_tasks.append({"ordinal": ordinal, "worker": ordinal % 2, "index": index,
                    "root_id": root["root_id"], "rotation": rotation, "arm_index": arm,
                    "directory": str(_project_file(_PROJECT_ROOT, HERE / "natural-development" / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm}"))})
    dev.require(type(tasks) is list and len(tasks) == 512 and
                tasks == expected_tasks and closure.get("source_manifest") == original["source_manifest"] and
                schedule.get("source_manifest") == original["source_manifest"], "资源改变原任务或生产实现")
    dev.require(set(schedule["old_completed_files"]) ==
                {str(Path(t["directory"]) / name) for t in tasks[:14] for name in TABLE_FILES},
                "资源旧14桌原件集合不完整")
    for slot in (0, 1):
        directory = _project_file(_PROJECT_ROOT, HERE / "resource-scheduling" / f"worker-{slot}")
        start, start_pin = dev.read(directory / "START.json")
        end, end_pin = dev.read(directory / "CLOSE.json")
        assigned = [o for o in range(14, 512) if o % 2 == slot]
        common = {"schedule_plan_pin": schedule_pin, "original_plan_pin": development_plan_pin,
                  "new_runner_pin": schedule["files"][str(_project_file(_PROJECT_ROOT, HERE / "run_development_resume.py"))], "worker": slot}
        dev.require(all(row.get(k) == v for row in (start, end) for k, v in common.items()) and
                    files.get(str(directory / "START.json")) == start_pin and
                    files.get(str(directory / "CLOSE.json")) == end_pin and end.get("worker_start_pin") == start_pin and
                    start.get("schema") == "t182-development-resource-worker-start/1" and
                    end.get("schema") == "t182-development-resource-worker-close/1", "资源worker真实收据未绑定")
        dev.require(start.get("assigned_ordinals") == assigned and start.get("max_cpu_workers") == 2 and
                    dev.integer(start.get("nice"), "开发worker nice", 15) >= 15 and
                    start.get("macos_background_io") is True and start.get("common_postprocess_lock_held") is False and
                    end.get("pid") == dev.integer(start.get("pid"), "开发worker PID", 1) and
                    end.get("complete") is True and end.get("failure") is None and end.get("source_stable") is True and
                    all(end.get(k) == assigned for k in ("assigned_ordinals", "attempted_ordinals", "completed_ordinals")) and
                    end.get("actual_original_run_table_calls") == len(assigned) and end.get("unknown_call_ordinals") == [] and
                    end.get("other_worker_interrupted") is False and end.get("models_added_by_scheduler") == 0 and
                    start.get("original_function") == "run_development.run_table" and
                    start.get("original_globals_modified") is False and start.get("score_based_selection") is False and
                    start.get("normal_fallbacks_allowed") is False and all(end.get(k) is False for k in
                        ("normal_fallbacks_allowed", "deadline_admission", "release_admission")),
                    "开发worker未成功闭合／资源未知")
        receipts = end.get("task_receipt_files")
        expected = {str(_project_file(_PROJECT_ROOT, HERE / "resource-scheduling/tasks" / f"task-{o:04d}" / name))
                    for o in assigned for name in ("BEFORE.json", "AFTER.json")}
        dev.require(type(receipts) is dict and set(receipts) == expected and
                    all(files.get(p) == h for p, h in receipts.items()), "资源原函数前后收据分母不齐")
        for ordinal in assigned:
            task = tasks[ordinal]
            directory = _project_file(_PROJECT_ROOT, HERE / "resource-scheduling/tasks" / f"task-{ordinal:04d}")
            before, before_pin = dev.read(directory / "BEFORE.json")
            after, after_pin = dev.read(directory / "AFTER.json")
            identity = {**common, "task": task}
            dev.require(all(row.get(k) == v for row in (before, after) for k, v in identity.items()) and
                        before.get("schema") == "t182-development-resource-task-before/1" and
                        after.get("schema") == "t182-development-resource-task-after/1" and
                        before.get("pid") == start["pid"] and after.get("pid") == start["pid"] and
                        receipts[str(directory / "BEFORE.json")] == before_pin and
                        receipts[str(directory / "AFTER.json")] == after_pin and after.get("before_pin") == before_pin,
                        "资源前后收据的实际身份／pin不符")
            dev.require(before.get("original_directory_absent") is True and before.get("original_run_table_called") is False and
                        before.get("score_based_selection") is False and after.get("original_run_table_called") is True and
                        after.get("complete") is True and after.get("failure") is None and after.get("source_stable") is True and
                        after.get("other_worker_interrupted") is False and all(after.get(k) is False for k in
                            ("normal_fallbacks_allowed", "deadline_admission", "release_admission")),
                        "资源原桌调用失败／未知／半闭合")
            table_files = after.get("original_table_files")
            dev.require(type(table_files) is dict and set(table_files) ==
                        {str(Path(task["directory"]) / name) for name in TABLE_FILES} and
                        all(files.get(p) == h for p, h in table_files.items()), "资源AFTER未绑定原五文件")
    dev.require(all(str(Path(t["directory"]) / name) in files for t in tasks for name in TABLE_FILES),
                "资源闭合缺原512桌原件")
    if verify:
        verify_files(files)
    return closure, closure_pin


def tasks(plan):
    """确认固定0起始根→换座→父子序号；奇偶槽划分只改变资源调度。"""
    result = []
    for index, root in enumerate(plan["roots"], 1):
        for rotation in plan["rotations"]:
            for arm in range(2):
                ordinal = len(result)
                result.append({"ordinal": ordinal, "worker": ordinal % 2, "index": index,
                               "root_id": root["root_id"], "rotation": rotation, "arm_index": arm})
    dev.require(len(result) == 1024, "确认资源任务须1024完整桌")
    return result


def table_directory(task):
    """原确认桌目录，禁止资源包装器改写原件路径。"""
    return _project_file(_PROJECT_ROOT, HERE / "natural-confirmation" / f"root-{task['index']:03d}" / f"seat-{task['rotation']}-arm-{task['arm_index']}")


def task_directory(task):
    """新资源收据与原桌分开，保留失败调用的费用关联。"""
    return _project_file(_PROJECT_ROOT, EVIDENCE / "tasks" / f"task-{task['ordinal']:04d}")


def identity(plan, plan_pin, worker, task=None):
    """资源身份仅用于关联，不作为策略／模拟世界输入。"""
    record = {"confirmation_plan_pin": plan_pin, "runner_pin": plan["files"][str(_project_file(_PROJECT_ROOT, HERE / "run_confirmation.py"))],
              "development_resource_closed_pin": plan["development_resource_closed_pin"], "worker": worker}
    if task is not None:
        record["task"] = task
    return record


def confirmation_worker_evidence(plan, plan_pin):
    """全两槽终态与1024原函数前后收据预检，无积分提取；返回待统一验字节的原件集合。"""
    files = {}
    for slot in (0, 1):
        directory = _project_file(_PROJECT_ROOT, EVIDENCE / f"worker-{slot}")
        start, start_pin = dev.read(directory / "START.json")
        end, end_pin = dev.read(directory / "CLOSE.json")
        assigned = [t["ordinal"] for t in plan["resource_tasks"] if t["worker"] == slot]
        expected_identity = identity(plan, plan_pin, slot)
        dev.require(all(row.get(k) == v for row in (start, end) for k, v in expected_identity.items()) and
                    start.get("schema") == "t182-confirmation-resource-worker-start/1" and
                    end.get("schema") == "t182-confirmation-resource-worker-close/1", "确认worker来源／版本不符")
        pid = dev.integer(start.get("pid"), "确认worker PID", 1)
        dev.require(end.get("pid") == pid and end.get("worker_start_pin") == start_pin and
                    start.get("assigned_ordinals") == assigned and start.get("max_cpu_workers") == 2 and
                    dev.integer(start.get("nice"), "确认worker nice", 15) >= 15 and
                    start.get("macos_background_io") is True and start.get("common_postprocess_lock_held") is False and
                    start.get("original_function") == "run_confirmation.run_table" and
                    start.get("score_based_selection") is False and start.get("normal_fallbacks_allowed") is False,
                    "确认worker原函数／固定分区／后台资源未知")
        dev.require(end.get("complete") is True and end.get("failure") is None and end.get("source_stable") is True and
                    all(end.get(k) == assigned for k in ("assigned_ordinals", "attempted_ordinals", "completed_ordinals")) and
                    end.get("actual_original_run_table_calls") == len(assigned) and end.get("unknown_call_ordinals") == [] and
                    end.get("other_worker_interrupted") is False and end.get("models_added_by_scheduler") == 0 and
                    all(end.get(k) is False for k in ("normal_fallbacks_allowed", "deadline_admission", "release_admission")),
                    "确认worker失败／未知／半闭合")
        files.update({str(directory / "START.json"): start_pin, str(directory / "CLOSE.json"): end_pin})
        receipts = {}
        for ordinal in assigned:
            task = plan["resource_tasks"][ordinal]
            receipt_dir = task_directory(task)
            before, before_pin = dev.read(receipt_dir / "BEFORE.json")
            after, after_pin = dev.read(receipt_dir / "AFTER.json")
            expected = identity(plan, plan_pin, slot, task)
            dev.require(all(row.get(k) == v for row in (before, after) for k, v in expected.items()) and
                        before.get("schema") == "t182-confirmation-resource-task-before/1" and
                        after.get("schema") == "t182-confirmation-resource-task-after/1" and
                        before.get("pid") == pid and after.get("pid") == pid and after.get("before_pin") == before_pin,
                        "确认任务前后收据身份／字节关联不符")
            dev.require(before.get("original_directory_absent") is True and before.get("original_run_table_called") is False and
                        before.get("score_based_selection") is False and after.get("original_run_table_called") is True and
                        after.get("complete") is True and after.get("failure") is None and after.get("source_stable") is True and
                        after.get("pin_errors") == {} and
                        after.get("other_worker_interrupted") is False and all(after.get(k) is False for k in
                            ("normal_fallbacks_allowed", "deadline_admission", "release_admission")),
                        "确认原函数未成功恰一次调用或资源收据半闭合")
            table_files = after.get("original_table_files")
            dev.require(type(table_files) is dict and
                        set(table_files) == {str(table_directory(task) / name) for name in TABLE_FILES},
                        "确认任务原桌五文件分母不齐")
            for expected_pin in table_files.values():
                dev.sha256(expected_pin.get("sha256"), "确认任务原件")
                dev.integer(expected_pin.get("bytes"), "确认任务原件字节", 1)
            files.update(table_files)
            receipts.update({str(receipt_dir / "BEFORE.json"): before_pin, str(receipt_dir / "AFTER.json"): after_pin})
        dev.require(end.get("task_receipt_files") == receipts, "确认worker未冻结全部任务前后收据")
        files.update(receipts)
    expected_tasks = {task_directory(t).resolve() for t in plan["resource_tasks"]}
    actual_tasks = {p.resolve() for p in (_project_file(_PROJECT_ROOT, EVIDENCE / "tasks")).glob("task-*") if p.is_dir()}
    expected_tables = {table_directory(t).resolve() for t in plan["resource_tasks"]}
    actual_tables = {p.resolve() for p in (_project_file(_PROJECT_ROOT, HERE / "natural-confirmation")).glob("root-*/seat-*-arm-*") if p.is_dir()}
    dev.require(actual_tasks == expected_tasks and actual_tables == expected_tables, "确认存在越计划／缺失桌或未知费用目录")
    return files


@contextmanager
def research_lock(worker):
    """每槽非阻塞独占；重复worker失败，模拟从不占共用赛后锁。"""
    dev.require(type(worker) is int and worker in (0, 1), "只有两个确认研究槽")
    with (_project_file(_PROJECT_ROOT, HERE / f".confirmation-worker-{worker}.lock")).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            primary = sys.exc_info()[1]
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except BaseException as secondary:
                if primary is None:
                    raise
                primary.add_note("确认研究槽释放再次失败:" + str(secondary))
