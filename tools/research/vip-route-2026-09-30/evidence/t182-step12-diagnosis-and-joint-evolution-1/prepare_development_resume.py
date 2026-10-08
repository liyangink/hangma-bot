"""T182 原512桌的资源调度准备；旧研究进程安全退出后才冻结剩余未开始任务。"""
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
import ast
import ctypes
import fcntl
import json
import os
import shlex
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import close_development as dev
import close_development_readout_repair as repair

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PLAN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/RESOURCE-SCHEDULING-PLAN.json')
ORIGINAL_PLAN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/DEVELOPMENT-PLAN.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/RESOURCE-SCHEDULING-CONTRACT.md')
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/resource-scheduling')
TABLE_FILES = ("START.json", "CLOSURE.json", "PAIRING-IDENTITY.json", "focal-decisions.jsonl.gz", "views.jsonl.gz")
CHECKPOINT_FILES = ("RESOURCE-OLD-RUNNER-HANDOFF.json", "RESOURCE-OLD-RUNNER-EXIT.json", "RESOURCE-OBSERVATION-001.json")
REPAIR_RESOURCE_FAILURE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/DEVELOPMENT-READOUT-REPAIR-PRECHECK-FAILED-001.json')


def background_priority():
    """仅降低本研究进程CPU/IO；导入不操作资源或进程。"""
    dev.require(sys.platform == "darwin", "本批资源切换须使用macOS后台IO")
    priority = os.getpriority(os.PRIO_PROCESS, 0)
    if priority < 15:
        os.nice(15 - priority)
    dev.require(os.getpriority(os.PRIO_PROCESS, 0) >= 15, "研究CPU优先级未降至nice15")
    io = ctypes.CDLL(None, use_errno=True).setiopolicy_np
    io.argtypes, io.restype = [ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int
    dev.require(io(0, 0, 3) == 0, "研究未获得macOS后台IO")


@contextmanager
def research_lock(name):
    """独占本批独立研究槽；重复进程立即失败，不使用共用赛后锁。"""
    path = _project_file(_PROJECT_ROOT, HERE / (".resource-scheduling-" + name + ".lock"))
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("研究槽已有进程持锁:" + name) from None
        try:
            yield
        finally:
            primary = sys.exc_info()[1]
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except BaseException as secondary:
                if primary is None:
                    raise
                primary.add_note("释放研究锁再次失败:" + type(secondary).__name__ + ": " + str(secondary))


def new_json(path, value):
    """排他新建新调度证据；不改原计划、原桌或旧结果。"""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def ordinal_tasks(original):
    """冻结原根→换座→臂的0起始序号；worker槽=ordinal%2，不看积分。"""
    tasks = []
    for index, root in enumerate(original["roots"], 1):
        for rotation in original["rotations"]:
            for arm_index in range(1 + len(original["candidates"])):
                ordinal = len(tasks)
                directory = _project_file(_PROJECT_ROOT, HERE / "natural-development" / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm_index}")
                tasks.append({"ordinal": ordinal, "worker": ordinal % 2, "index": index,
                              "root_id": root["root_id"], "rotation": rotation, "arm_index": arm_index,
                              "directory": str(directory)})
    dev.require(len(tasks) == 512, "本次必须保留原512桌分母")
    return tasks


def table_pins(task, *, require_all=True, pin_errors=None):
    """只核原字节；失败留档传pin_errors逐件收集，保留其他可读原件且不授成功。"""
    directory = Path(task["directory"])
    files = {}
    for name in TABLE_FILES:
        path = directory / name
        try:
            dev.require(path.is_file(), "原桌缺文件:" + str(path))
            files[str(path)] = dev.pin(path)
        except (OSError, ValueError) as error:
            if require_all or pin_errors is None:
                raise
            pin_errors.append({"path": str(path), "type": type(error).__name__, "message": str(error)})
    return files


def completed_metadata(task, original, original_pin):
    """核原完成包的身份/终态/输入证明；不提取原结算分数或候选评分。"""
    directory = Path(task["directory"])
    start, start_pin = dev.read(directory / "START.json")
    closure, closure_pin = dev.read(directory / "CLOSURE.json")
    pairing, pairing_pin = dev.read(directory / "PAIRING-IDENTITY.json")
    root = original["roots"][task["index"] - 1]
    arm = [original["parent"], *original["candidates"]][task["arm_index"]]
    rotation = task["rotation"]
    dev.require(start.get("plan_pin") == original_pin, "原START未绑定原DEV计划")
    for record in (start, closure, pairing):
        dev.require(record.get("root") == root and record.get("rotation") == rotation and record.get("arm") == arm,
                    "原完成桌来源/座位/公式身份不符")
    dev.require(start.get("table_starts_reserved") == 1 and start.get("logical_clock_not_official_deadline") is True and
                start.get("model_calls") == 0, "原START声明不符")
    dev.require(closure.get("complete") is True and closure.get("source_stable") is True and closure.get("failure") is None and
                closure.get("actual_table_starts") == 1 and closure.get("focal_seat") == rotation and closure.get("model_calls") == 0 and
                closure.get("normal_fallbacks_allowed") is False and closure.get("deadline_or_strength_admission") is False,
                "原桌未完整闭合、失败、漂移或回退")
    outcome = closure.get("outcome")
    dev.require(type(outcome) is dict and outcome.get("status") == "complete" and outcome.get("completed_hands") == 8 and
                outcome.get("error_reason") is None and outcome.get("blocked_reason") is None, "原桌不是完整八单局")
    counts = outcome.get("runtime_counts")
    dev.require(type(counts) is dict and set(counts) == dev.RUNTIME_KEYS and
                all(type(v) is int and v == 0 for v in counts.values()), "原桌运行计数未知或非零")
    dev.require(type(closure.get("settlements")) is list and len(closure["settlements"]) == 8, "原桌八结算不齐")
    decisions = dev.integer(closure.get("actual_focal_decisions"), "原焦点决策数", 1)
    dev.require(dev.integer(closure.get("actual_focal_score_calls"), "原评分数", 1) == decisions, "原评分次数不符")
    capture = closure.get("capture")
    dev.require(type(capture) is dict and type(capture.get("terminal")) is dict and
                all(capture["terminal"].get(k) is True for k in
                    ("terminal_valid", "closed", "verified", "store_calls_reconciled")) and
                capture["terminal"].get("errors") == [] and capture.get("failed_store_calls") == 0 and
                capture.get("store_calls") == decisions, "原输入捕获不完整")
    dev.require(closure.get("pairing_identity_pin") == pairing_pin and pairing.get("evidence") ==
                "本次运行实际从policies_by_id选取并传入drive_match的映射；焦点席位为None", "原实际装配映射未绑定")
    opponents = pairing.get("opponent_policy_ids_physical")
    dev.require(type(opponents) is list and len(opponents) == 4 and opponents[rotation] is None and
                all(type(opponents[s]) is str and opponents[s] for s in range(4) if s != rotation) and
                opponents == closure.get("opponent_policy_ids_physical"), "原三对手身份不完整")
    proofs = closure.get("pairing_proofs")
    dev.require(type(proofs) is list and len(proofs) == 8, "原八局配对证明不齐")
    for round_no, proof in enumerate(proofs, 1):
        dev.require(type(proof.get("round_no")) is int and proof["round_no"] == round_no and
                    proof.get("export_matches_frozen_sampler") is True and proof.get("teacher_only_not_policy_input") is True,
                    "原公开导出配对证明无效")
        dev.sha256(proof.get("physical_wall_sha256"), "原物理牌山")
        dev.sha256(proof.get("actual_initial_sha256"), "原实际起手")
    pins = table_pins(task)
    dev.require(pins[str(directory / "START.json")] == start_pin and pins[str(directory / "CLOSURE.json")] == closure_pin and
                pins[str(directory / "PAIRING-IDENTITY.json")] == pairing_pin, "原完成元数据读取期间漂移")
    actual_capture = pins[str(directory / "views.jsonl.gz")]
    dev.require(actual_capture["sha256"] == capture["terminal"].get("compressed_sha256") and
                actual_capture["bytes"] == capture["terminal"].get("observed_compressed_bytes"), "原捕获gzip与终态不符")
    return pins


def research_imports():
    """AST递归冻结本调度静态import的全部同目录研究实现，不执行入口。"""
    queue = [_project_file(_PROJECT_ROOT, HERE / n) for n in ("prepare_development_resume.py", "run_development_resume.py", "close_development_resume.py")]
    files, edges = {}, {}
    while queue:
        path = queue.pop().resolve()
        if str(path) in files:
            continue
        children = set()
        for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
            modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                       else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for module in modules:
                local = _project_file(_PROJECT_ROOT, HERE / (module.split(".")[0] + ".py"))
                if local.is_file():
                    children.add(local.resolve())
        files[str(path)] = dev.pin(path)
        edges[str(path)] = sorted(str(c) for c in children)
        queue.extend(children)
    return files, edges


def stable(plan, plan_pin=None):
    """每桌前后核原计划/生产/新包装器；旧大文件只在阶段边界统一验。"""
    dev.frozen(plan)
    if plan_pin is not None:
        dev.require(dev.pin(PLAN) == plan_pin, "调度计划漂移")


def old_evidence_stable(plan):
    """重核安全切换前旧完成原件，不读取中途积分。"""
    for path, expected in plan["old_completed_files"].items():
        dev.require(dev.pin(Path(path)) == expected, "旧完成原件漂移:" + path)


def checkpoint_records(tasks, original_pin, old_files):
    """绑定root实际14桌边界交接证据；只核元数据，不读积分或发送信号。"""
    records, pins = {}, {}
    for name in CHECKPOINT_FILES:
        records[name], pins[str(_project_file(_PROJECT_ROOT, HERE / name))] = dev.read(_project_file(_PROJECT_ROOT, HERE / name))
    handoff, exit_record, observation = (records[name] for name in CHECKPOINT_FILES)
    expected_dirs = [str(Path(t["directory"]).relative_to(HERE)) for t in tasks[:14]]
    dev.require(handoff.get("schema") == "t182-original-runner-handoff/1" and
                handoff.get("planned_total") == 512 and handoff.get("completed_tables") == expected_dirs and
                handoff.get("all_started_tables_completed") is True and handoff.get("open_tables") == 0 and
                handoff.get("scores_extracted") is False, "旧交接非事先完整14桌边界")
    old_pid = dev.integer(handoff.get("original_runner_pid"), "交接研究PID", 1)
    dev.require(exit_record.get("schema") == "t182-old-runner-exit/1" and
                exit_record.get("original_runner_pid") == old_pid and exit_record.get("completed_tables") == 14 and
                exit_record.get("actual_process_absent") is True and exit_record.get("actual_ps_exit_code") == 1 and
                exit_record.get("actual_ps_output") == "" and exit_record.get("open_tables") == 0 and
                exit_record.get("freematch_processes_signaled") is False, "缺旧研究实际退出证据")
    dev.require(observation.get("schema") == "t182-resource-observation/1" and
                observation.get("development_plan_pin") == original_pin and
                observation.get("outcome_points_extracted") is False, "资源观察不绑定原DEV或已提取积分")
    expected_meta = {str(Path(t["directory"]) / n) for t in tasks[:14] for n in ("START.json", "CLOSURE.json")}
    dev.require(type(handoff.get("files")) is dict and set(handoff["files"]) == expected_meta and
                all(old_files.get(p) == h for p, h in handoff["files"].items()), "14桌旧交接元数据漂移或不完整")
    before = handoff.get("actual_command_before")
    dev.require(type(before) is str, "旧研究命令未知")
    columns = before.strip().split(None, 3)
    dev.require(len(columns) == 4 and columns[0] == str(old_pid), "旧研究命令/PID不符")
    command = shlex.split(columns[3])
    dev.require(len(command) == 35 and (_project_file(_PROJECT_ROOT, ROOT / command[1])).resolve() == _project_file(_PROJECT_ROOT, HERE / "run_development.py") and
                command[2] == "--roots" and command[3:] == [str(i) for i in range(1, 33)], "旧原runner命令不符")
    return old_pid, command, pins


def old_command_absent(pid, expected_command):
    """只用ps读命令；PID重用为不同命令可记录，不向任何进程发信号。"""
    result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False)
    dev.require(result.returncode in (0, 1), "ps不能确认旧研究命令已退出")
    if result.returncode == 1:
        dev.require(result.stdout.strip() == "", "ps退出但仍返回未知命令")
        return {"actual_command_absent": True, "pid_reused_by_different_command": False,
                "actual_ps_exit_code": 1, "actual_ps_command": ""}
    actual = result.stdout.strip()
    dev.require(bool(actual) and shlex.split(actual) != expected_command, "原研究命令仍在旧PID运行，不得切换")
    return {"actual_command_absent": True, "pid_reused_by_different_command": True,
            "actual_ps_exit_code": 0, "actual_ps_command": actual}


def read_schedule(*, verify_old_evidence=False):
    """只接受固定两worker、512完整分母、事前奇偶分区及精确旧完成/未开始分割。"""
    dev.require(sys.flags.optimize == 0, "原run_table使用assert；禁止python -O关闭冻结审计")
    plan, plan_pin = dev.read(PLAN)
    dev.require(plan.get("schema") == "t182-development-resource-scheduling/1" and
                plan.get("workers") == [0, 1] and plan.get("max_cpu_workers") == 2 and
                plan.get("planned_table_instances") == 512 and plan.get("ordinal_base") == 0 and
                plan.get("partition") == "worker=ordinal%2" and plan.get("normal_fallbacks_allowed") is False,
                "调度版本/槽数/原分母/分区不符")
    stable(plan, plan_pin)
    original, original_pin = dev.read(ORIGINAL_PLAN)
    dev.validate_plan(original)
    dev.frozen(original)
    dev.require(original_pin == plan.get("original_plan_pin"), "调度未绑定原DEV计划")
    tasks = ordinal_tasks(original)
    dev.require(plan.get("tasks") == tasks, "调度改变原任务顺序或身份")
    old, todo = plan.get("old_completed_ordinals"), plan.get("not_started_ordinals")
    dev.require(type(old) is list and type(todo) is list and all(type(v) is int for v in old + todo) and
                old == sorted(set(old)) and todo == sorted(set(todo)) and
                not set(old) & set(todo) and sorted(old + todo) == list(range(512)), "调度分割遗漏/重复/新增任务")
    dev.require(old == list(range(14)) and todo == list(range(14, 512)), "本次交接须恰14旧完成/498未开始")
    expected_old_paths = {str(Path(tasks[o]["directory"]) / n) for o in old for n in TABLE_FILES}
    dev.require(type(plan.get("old_completed_files")) is dict and set(plan["old_completed_files"]) == expected_old_paths,
                "旧完成原件冻结分母不完整")
    checkpoint = plan.get("old_runner_checkpoint")
    dev.require(type(checkpoint) is dict and checkpoint.get("root_confirmed_safe_exit") is True and
                checkpoint.get("actual_command_absent") is True and
                checkpoint.get("all_started_have_complete_closure") is True, "缺root安全退出确认")
    old_pid, command, checkpoint_pins = checkpoint_records(tasks, original_pin, plan["old_completed_files"])
    dev.require(checkpoint.get("pid") == old_pid and checkpoint.get("original_command") == command and
                all(plan["files"].get(p) == h for p, h in checkpoint_pins.items()), "调度未冻结三份交接原件/原研究命令")
    imported, edges = research_imports()
    dev.require(plan.get("research_imports") == edges and all(plan["files"].get(p) == h for p, h in imported.items()) and
                str(CONTRACT) in plan["files"] and str(ORIGINAL_PLAN) in plan["files"], "调度import/合同/原计划未冻结")
    repair_files = repair.frozen_repair()
    dev.require(plan.get("readout_schema_repair") == "production_opponent_diagnostics_and_object_ids_only_v1" and
                all(plan["files"].get(p, plan["old_completed_files"].get(p)) == h for p, h in repair_files.items()),
                "调度未冻结成功修复验证及原失败/实际收据")
    dev.require(plan["files"].get(str(REPAIR_RESOURCE_FAILURE)) == dev.pin(REPAIR_RESOURCE_FAILURE), "未冻结修复首个sandbox资源失败")
    if verify_old_evidence:
        old_evidence_stable(plan)
    return plan, plan_pin, original


def main(old_runner_pid, old_runner_session, checkpoint_confirmed):
    """root确认旧研究进程已退出且全部START闭合后，只冻结未开始任务；不启桌。"""
    dev.require(checkpoint_confirmed is True, "须由root明确确认旧研究runner安全checkpoint退出")
    dev.require(sys.flags.optimize == 0, "禁止python -O关闭冻结原运行审计")
    dev.integer(old_runner_pid, "旧研究PID", 1)
    dev.require(type(old_runner_session) is str and old_runner_session, "缺旧执行session身份")
    background_priority()
    with research_lock("prepare"):
        dev.require(not PLAN.exists() and not EVIDENCE.exists() and not dev.OUTPUT.exists(), "新调度证据或原开发闭合已存在，拒绝覆盖")
        original, original_pin = dev.read(ORIGINAL_PLAN)
        dev.validate_plan(original)
        dev.frozen(original)
        tasks, old, todo, old_files = ordinal_tasks(original), [], [], {}
        for task in tasks:
            directory = Path(task["directory"])
            if directory.exists():
                dev.require(directory.is_dir(), "原桌路径不是目录")
                old_files.update(completed_metadata(task, original, original_pin))
                old.append(task["ordinal"])
            else:
                todo.append(task["ordinal"])
        dev.require(old == list(range(14)) and todo == list(range(14, 512)), "本次须恰14旧完成/498未开始，拒绝补根或改变分母")
        old_pid, command, checkpoint_pins = checkpoint_records(tasks, original_pin, old_files)
        dev.require(old_runner_pid == old_pid, "CLI不是实际交接研究PID")
        absent = old_command_absent(old_runner_pid, command)
        # 越计划原目录不允许悄悄遗失支出；只检查目录身份，不看成绩。
        parent = _project_file(_PROJECT_ROOT, HERE / "natural-development")
        expected_dirs = {Path(t["directory"]) for t in tasks}
        if parent.exists():
            actual_dirs = {p for p in parent.glob("root-*/seat-*-arm-*") if p.is_dir()}
            dev.require(actual_dirs == {expected_dirs_element for expected_dirs_element in expected_dirs if expected_dirs_element.exists()},
                        "自然开发存在越计划目录，不能切换")
        imported, edges = research_imports()
        repair_files = repair.frozen_repair()
        files = dict(original["files"])
        dev.require(all(p not in files or files[p] == h for p, h in imported.items()), "本地import与原冻结研究实现不同")
        files.update(imported)
        files.update(checkpoint_pins)
        files[str(REPAIR_RESOURCE_FAILURE)] = dev.pin(REPAIR_RESOURCE_FAILURE)
        for path, expected in repair_files.items():
            if path in old_files:
                dev.require(old_files[path] == expected, "修复验证与旧完成原件不同")
            else:
                dev.require(path not in files or files[path] == expected, "修复验证与原源码不同")
                files[path] = expected
        files[str(CONTRACT)] = dev.pin(CONTRACT)
        files[str(ORIGINAL_PLAN)] = original_pin
        plan = {"schema": "t182-development-resource-scheduling/1", "original_plan_pin": original_pin,
            "planned_table_instances": 512, "tasks": tasks, "old_completed_ordinals": old,
            "not_started_ordinals": todo, "old_completed_files": old_files,
            "workers": [0, 1], "max_cpu_workers": 2, "ordinal_base": 0, "partition": "worker=ordinal%2",
            "files": files, "source_manifest": original["source_manifest"], "research_imports": edges,
            "old_runner_checkpoint": {"pid": old_runner_pid, "exec_session": old_runner_session,
                "root_confirmed_safe_exit": True, "original_command": command, **absent,
                "all_started_have_complete_closure": True},
            "common_postprocess_lock_held_during_simulation": False, "nice_at_least": 15, "macos_background_io": True,
            "normal_fallbacks_allowed": False, "no_score_based_selection": True,
            "original_framework_rules_seed_and_score_unchanged": True,
            "readout_schema_repair": "production_opponent_diagnostics_and_object_ids_only_v1",
            "new_models_scores_worlds_tables_in_preparation": 0, "deadline_admission": False, "release_admission": False}
        stable(plan)
        dev.frozen(original)
        dev.require(dev.pin(ORIGINAL_PLAN) == original_pin, "准备期间原DEV计划漂移")
        old_evidence_stable(plan)
        dev.require(all(not Path(tasks[o]["directory"]).exists() for o in todo), "准备期间未开始目录出现，停止切换")
        new_json(PLAN, plan)
    print(json.dumps({"prepared": True, "original_tables": 512, "old_complete": len(old), "remaining_unstarted": len(todo),
                      "new_models_scores_worlds_tables": 0}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-runner-pid", type=int, required=True)
    parser.add_argument("--old-runner-session", required=True)
    parser.add_argument("--checkpoint-confirmed", action="store_true", help="root已核旧研究runner安全退出；程序仍核旧PID命令及原终态，PID重用不发信号")
    args = parser.parse_args()
    try:
        main(args.old_runner_pid, args.old_runner_session, args.checkpoint_confirmed)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        print(json.dumps({"prepared": False, "status": "unknown_or_invalid_no_schedule", "error_type": type(error).__name__,
                          "reason": str(error), "original_evidence_retained": True}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
