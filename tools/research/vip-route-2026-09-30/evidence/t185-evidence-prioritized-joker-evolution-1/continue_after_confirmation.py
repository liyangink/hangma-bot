"""本批唯一候选的单次后台验收接续；等待原确认，不重复世界或自动换版。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from common import HERE, OLD, ROOT, pin, save
import t185_close_development as dev
from candidate_verification_common import check_files, require_strength, require_tools, resource_zero
from t185_prepare_confirmation import postprocess_lock, read_confirmation_plan

OUT = _project_file(_PROJECT_ROOT, HERE / "post-confirmation")
PLAN = OUT / "PLAN.json"
PRIVATE = _project_file(_PROJECT_ROOT, ROOT / ".private/t185-post-confirmation")
DEPENDENCIES = ((25513, "dispatch_with_readout_compat.py --phase confirmation"),
    (25518, "run_confirmation_workers.py --slot 0"), (25519, "run_confirmation_workers.py --slot 1"))
STEPS = (
    {"name": "native", "script": "prepare_candidate_native.py", "args": [], "result": "native-candidate/BUILD-CLOSED.json", "outer_lock": False},
    {"name": "equivalent-542", "script": "verify_candidate_native.py", "args": [], "result": "native-verification/CLOSED.json", "outer_lock": True},
    {"name": "heavy-equivalent-80", "script": "verify_heavy_candidate_native.py", "args": [], "result": "heavy-native-verification/CLOSED.json", "outer_lock": True},
    {"name": "heavy-reference-38", "script": "probe_heavy_complete_choices.py", "args": ["--phase", "reference"], "result": "heavy-complete-reference/CLOSED.json", "outer_lock": False},
    {"name": "original-deadline-59", "script": "probe_candidate_deadlines.py", "args": [], "result": "original-deadline-probe/CLOSED.json", "outer_lock": True},
    {"name": "heavy-nominal-19", "script": "probe_heavy_complete_choices.py", "args": ["--phase", "probe"], "result": "heavy-nominal-deadline-probe/CLOSED.json", "outer_lock": True},
)


def process(pid, expected=None):
    """仅查指定PID；ps观察失败保留UNKNOWN，不视为退出、不发任何信号。"""
    result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
    command = result.stdout.strip()
    if result.returncode == 1 and not command and not result.stderr.strip():
        return {"pid": pid, "state": "ABSENT"}
    if result.returncode != 0 or not command:
        return {"pid": pid, "state": "UNKNOWN", "ps_returncode": result.returncode}
    if expected is not None and command != expected:
        return {"pid": pid, "state": "DIFFERENT_PROCESS"}
    return {"pid": pid, "state": "LIVE", "command": command}


def publish(state, **details):
    """原子更新本离线控制器状态；UTC关联用Unix墙钟秒，不含凭证。"""
    target = OUT / "STATUS.json"
    temporary = OUT / ("status-" + str(os.getpid()) + ".tmp")
    temporary.write_text(json.dumps({"state": state, "pid": os.getpid(), "at_unix_seconds": time.time(),
        **details}, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, target)


def enabled():
    """控制开关只影响尚未开始的阶段；已经开始的子工具仍自然执行，不终止。"""
    value = dev.read(PRIVATE / "control.json")[0]["validation_enabled"]
    dev.require(type(value) is bool, "验收开关类型未知")
    return value


def prepare():
    """零评分预检后冻结唯一次序和三个原进程；只能在原确认真实存活时建立。"""
    dev.require(os.nice(0) == 0, "接续控制器需保持正常CPU优先级，子工具自行设置后台档")
    check_path = _project_file(_PROJECT_ROOT, HERE / "POST-CONFIRMATION-TOOLS-CHECKED.json")
    tool_check, tool_check_pin = dev.read(check_path)
    dev.require(tool_check["complete"] is True and tool_check["source_pin"] == pin(Path(__file__)) and
        tool_check["new_scores_compile_worlds_tables_HTTP_workers"] == 0, "本接续工具的零评分检查未通过")
    plan, plan_pin = read_confirmation_plan()
    files = require_tools()
    files[str(check_path)] = tool_check_pin
    heavy = _project_file(_PROJECT_ROOT, HERE / "HEAVY-COMPLETE-TOOLS-CHECKED-013.json")
    checked, checked_pin = dev.read(heavy)
    dev.require(checked["complete"] is True and checked["new_rule_analyses_scores_worlds_tables_HTTP_model_calls"] == 0,
        "重型完整工具零评分检查未通过")
    check_files(checked["files"])
    files.update(checked["files"])
    files.update({str(heavy): checked_pin, str(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-PLAN.json")): plan_pin})
    paths = {Path(__file__), *(_project_file(_PROJECT_ROOT, HERE / s["script"]) for s in STEPS)}
    files.update({str(p): pin(p) for p in paths})
    observations = []
    for pid, needle in DEPENDENCIES:
        actual = process(pid)
        dev.require(actual["state"] == "LIVE" and needle in actual["command"], "原确认进程未真实核实:" + str(pid))
        observations.append(actual)
    dev.require(not (_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json")).exists() and
        not (_project_file(_PROJECT_ROOT, HERE / "confirmation-dispatch/FAILED.json")).exists(), "此等待入口只为当前原活确认建立")
    dev.require(all(not (_project_file(_PROJECT_ROOT, HERE / s["result"])).parent.exists() for s in STEPS),
        "已有验收尝试目录，保留原结果，不接管或覆盖")
    OUT.mkdir(exist_ok=False)
    PRIVATE.mkdir(mode=0o700, exist_ok=False)
    save(PRIVATE / "control.json", {"validation_enabled": True})
    value = {"schema": "t185-one-shot-post-confirmation/1", "files": files,
        "confirmation_plan_pin": plan_pin, "selected_identity": plan["candidates"][0]["identity"],
        "original_dependencies": observations, "steps": list(STEPS), "planned_explicit_scores": 660,
        "planned_service_choose": 78, "new_authors_worlds_tables_HTTP": 0,
        "original_formulas_sources_seeds_thresholds_changed": False, "online_cutover_included": False}
    save(PLAN, value)
    save(OUT / "PREFLIGHT.json", {"complete": True, "plan_pin": pin(PLAN),
        "original_dependencies_live": True, "new_scores_compile_worlds_tables_HTTP_workers": 0})
    print({"prepared": True, "future_explicit_scores": 660, "future_service_choose": 78}, flush=True)


def validate_step(name, value, identity, execution_id):
    """实际子工具终态也必须符合原数量和全通过标记；退出0本身不足以继续。"""
    dev.require(value.get("complete") is True, name + "未全通过")
    if name == "native":
        dev.require(value.get("candidate_identity") == identity, "编译终态不是确认候选")
        return
    dev.require(value.get("source_stable") is True and value.get("identity") == identity and
        value.get("execution_id") == execution_id, name + "源码或执行身份不符")
    if name in ("equivalent-542", "heavy-equivalent-80", "heavy-reference-38"):
        count = {"equivalent-542": 542, "heavy-equivalent-80": 80, "heavy-reference-38": 38}[name]
        dev.require(type(value.get("actual_score_attempts")) is int and value["actual_score_attempts"] == count and
            value.get("capture", {}).get("terminal", {}).get("terminal_valid") is True, name + "评分或捕获未核齐")
        if name == "equivalent-542":
            dev.require(value.get("compiled_formula_equivalence_admitted") is True and
                value.get("completed_rows") == 156 and len(value.get("references", [])) == 39, "542完整参考未通过")
        if name == "heavy-reference-38":
            dev.require(len(value.get("references", [])) == 19, "19重型完整参考缺失")
    elif name == "original-deadline-59":
        waves = value.get("waves", [])
        dev.require(type(value.get("actual_service_choose")) is int and value["actual_service_choose"] == 59 and
            value.get("original_deadline_admitted_for_covered_inputs") is True and len(waves) == 5 and
            all(w.get("complete") is True and w.get("resources_released") is True and
                resource_zero(w.get("resource_terminal", {})) for w in waves), "59原预算或资源未通过")
    elif name == "heavy-nominal-19":
        dev.require(type(value.get("actual_service_choose")) is int and value["actual_service_choose"] == 19 and
            type(value.get("actual_rule_analyses")) is int and value["actual_rule_analyses"] == 19 and
            len(value.get("rows", [])) == 19 and all(r.get("complete") is True for r in value["rows"]) and
            value.get("resources_released") is True and resource_zero(value.get("resource_terminal", {})),
            "19名义窗口或资源未通过")
    else:
        raise ValueError("未声明的验收阶段")


def watch():
    """只接一次既有原确认；全六门通过后停在接线准备前，不运行官方比赛。"""
    dev.require(os.nice(0) == 0, "正常计时不可从后台nice15控制器继承")
    plan, plan_pin = dev.read(PLAN)
    preflight, _ = dev.read(OUT / "PREFLIGHT.json")
    dev.require(preflight["complete"] is True and preflight["plan_pin"] == plan_pin and
        preflight["new_scores_compile_worlds_tables_HTTP_workers"] == 0, "接续事前预检或计划摘要漂移")
    check_files(plan["files"])
    dev.require(plan["steps"] == list(STEPS), "接续次序漂移")
    with (PRIVATE / "owner.lock").open("a+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        own = process(os.getpid())
        dev.require(own["state"] == "LIVE", "控制器自身进程身份未核实")
        save(OUT / "START.json", {"pid": os.getpid(), "plan_pin": plan_pin,
            "expected_command": own["command"],
            "at_unix_seconds": time.time(), "scores_worlds_tables_HTTP_at_start": 0})
        phases, failure, strength_files, execution_id = [], None, {}, None
        stopped = False
        try:
            while True:
                if not enabled():
                    stopped = True
                    break
                observed = [process(x["pid"], x["command"]) for x in plan["original_dependencies"]]
                publish("waiting_confirmation_natural_exit", dependencies=observed)
                # UNKNOWN继续等待同一PID；不把观察失败、文件计数或CLOSED出现当退出。
                if all(x["state"] in ("ABSENT", "DIFFERENT_PROCESS") for x in observed):
                    break
                time.sleep(15)
            if stopped:
                return
            check_files(plan["files"])
            dev.require(not (_project_file(_PROJECT_ROOT, HERE / "confirmation-dispatch/FAILED.json")).exists(), "原确认派发失败，不自动重做")
            confirmation, confirmation_pin = read_confirmation_plan(verify_development_evidence=True)
            closed, closed_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json"))
            dispatch, dispatch_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "confirmation-dispatch/CLOSED.json"))
            require_strength(closed, confirmation, dispatch)
            dev.require(confirmation_pin == plan["confirmation_plan_pin"] and
                confirmation["candidates"][0]["identity"] == plan["selected_identity"] and
                dispatch["worker_returncodes"] == [0, 0] and dispatch["readout_exit_code"] == 0 and
                dispatch["confirmation_closed_pin"] == closed_pin and
                closed["files"][str(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-PLAN.json"))] == confirmation_pin,
                "确认实际终态、资源或绑定不足，禁止后续验收")
            strength_files = {str(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json")): closed_pin,
                str(_project_file(_PROJECT_ROOT, HERE / "confirmation-dispatch/CLOSED.json")): dispatch_pin}
            save(OUT / "STRENGTH-READY.json", {"complete": True, "files": strength_files,
                "candidate_identity": plan["selected_identity"], "original_dependencies_natural_exit": True})
            with ExitStack() as slots:
                for slot in (0, 1):
                    lock = slots.enter_context((OLD / f".resource-scheduling-worker-{slot}.lock").open("a+"))
                    while True:
                        try:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if not enabled():
                                stopped = True
                                return
                            publish("waiting_validation_resource_slot", slot=slot)
                            time.sleep(15)
                for step in STEPS:
                    if not enabled():
                        stopped = True
                        break
                    check_files(plan["files"])
                    check_files(strength_files)
                    dev.require(pin(PLAN) == plan_pin and not (_project_file(_PROJECT_ROOT, HERE / step["result"])).parent.exists(),
                        "阶段已尝试或计划漂移；不重复、接管或覆盖")
                    phase = OUT / step["name"]
                    phase.mkdir(exist_ok=False)
                    command = [sys.executable, str(_project_file(_PROJECT_ROOT, HERE / step["script"])), *step["args"]]
                    save(phase / "START.json", {"command": command, "plan_pin": plan_pin,
                        "at_unix_seconds": time.time(), "cpu_nice_parent": os.nice(0)})
                    with ExitStack() as stage_context, (phase / "OUTPUT.log").open("x") as output:
                        if step["outer_lock"]:
                            stage_context.enter_context(postprocess_lock("t185-post-confirmation-" + step["name"]))
                        child = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
                        save(phase / "CHILD.json", {"pid": child.pid, "at_unix_seconds": time.time()})
                        publish("running_validation", phase=step["name"], child_pid=child.pid)
                        code = child.wait()  # 不给子工具发终止信号，失败不自动重试
                    save(phase / "CHILD-TERMINAL.json", {"actual_exit_code": code,
                        "at_unix_seconds": time.time(), "termination_signal_sent": False})
                    dev.require(type(code) is int and code == 0, "原子工具失败，停止后续阶段:" + step["name"])
                    value, result_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / step["result"]))
                    validate_step(step["name"], value, plan["selected_identity"], execution_id)
                    if step["name"] == "native":
                        execution_id = hashlib.sha256(json.dumps({"build_plan_pin": value["build_plan_pin"],
                            "binary_pin": value["binary_pin"]}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                    result = {"phase": step["name"], "complete": True, "actual_exit_code": code,
                        "result_file": str(_project_file(_PROJECT_ROOT, HERE / step["result"])), "result_pin": result_pin, "execution_id": execution_id}
                    save(phase / "CLOSED.json", result)
                    phases.append(result)
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        finally:
            stable = False
            try:
                check_files(plan["files"])
                check_files(strength_files)
                dev.require(pin(PLAN) == plan_pin and all(pin(Path(r["result_file"])) == r["result_pin"] for r in phases),
                    "接续最终计划或阶段终态漂移")
                stable = True
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
            complete = failure is None and stable and not stopped and len(phases) == 6
            terminal = {"complete": complete, "failure": failure, "stopped_by_control": stopped,
                "source_stable": stable, "plan_pin": plan_pin, "strength_files": strength_files, "phases": phases,
                "validation_ready_for_isolated_wiring": complete, "online_or_formal_admission": False,
                "new_authors_worlds_tables_HTTP": 0, "original_processes_or_players_terminated": False}
            save(OUT / "CLOSED.json", terminal)
            publish("validation_complete" if complete else "validation_stopped", failure=failure, stopped_by_control=stopped)
        dev.require(complete, "一次性验收未通过，原尝试保留，不自动恢复")
        print({"validation_complete": True, "online_admission": False}, flush=True)


def status():
    """只读实际控制器与当前子工具；状态文件不代替进程核验。"""
    current = dev.read(OUT / "STATUS.json")[0]
    start = dev.read(OUT / "START.json")[0]
    value = {"state": current["state"], "controller": process(current["pid"], start["expected_command"]),
        "closed_exists": (OUT / "CLOSED.json").exists()}
    if current.get("child_pid"):
        phase = dev.read(OUT / current["phase"] / "START.json")[0]
        value["child"] = process(current["child_pid"], " ".join(phase["command"]))
    print(json.dumps(value, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "watch", "status"))
    {"prepare": prepare, "watch": watch, "status": status}[parser.parse_args().mode]()
