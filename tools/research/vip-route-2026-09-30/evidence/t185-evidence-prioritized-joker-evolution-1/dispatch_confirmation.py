"""T185确认全批控制器：开发已全批闭合，两个固定后台槽自然结束后统一读回。"""

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
import asyncio
import ctypes
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from common import HERE, OLD, ROOT, pin, save
import t185_prepare_confirmation as reader


def prior_processes():
    """只返回旧研究程序的进程号；不打印任何比赛认证参数或全系统命令。"""
    rows = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True).splitlines()
    names = ("run_development_resume.py", "close_development_resume.py", "close_development_readout_repair.py")
    result = []
    for row in rows:
        pieces = row.strip().split(maxsplit=1)
        if len(pieces) == 2 and any(path in pieces[1] for path in (str(OLD), str(OLD.relative_to(ROOT)))) and any(n in pieces[1] for n in names):
            result.append(int(pieces[0]))
    return sorted(result)


def free_research_slots():
    """实际试取两个既有CPU槽；持有或未知时拒绝，不中断持有者。"""
    handles = []
    try:
        for slot in (0, 1):
            handle = (OLD / f".resource-scheduling-worker-{slot}.lock").open("a+")
            handles.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    finally:
        for handle in handles:
            handle.close()


async def main():
    """排他运行；不读取中途分、不重复原桌、不重启失败批，不操作官方玩家。"""
    assert sys.platform == "darwin"
    priority = os.getpriority(os.PRIO_PROCESS, 0)
    if priority < 15:
        os.nice(15 - priority)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    plan_path = _project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-PLAN.json")
    plan = json.loads(plan_path.read_text())
    reader.validate_plan(plan)
    reader.frozen(plan)
    plan_pin = pin(plan_path)
    assert plan["planned_table_instances"] == 1024
    directory = _project_file(_PROJECT_ROOT, HERE / "confirmation-dispatch")
    with (_project_file(_PROJECT_ROOT, HERE / ".confirmation-dispatch-owner.lock")).open("a+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory.mkdir(exist_ok=False)
        save(directory / "START.json", {"pid": os.getpid(), "plan_pin": plan_pin,
            "dispatcher_pin": pin(Path(__file__)), "unix_seconds": time.time(),
            "nice": os.getpriority(os.PRIO_PROCESS, 0), "background_io": True,
            "common_postprocess_lock_held": False, "waits_for_old_resource_close": False,
            "new_table_calls_at_start": 0, "strength_or_deadline_admission": False})
        failure = None
        children, streams, returncodes = [], [], []
        try:
            dispatch_pin, evidence = reader.require_development_dispatch()
            assert free_research_slots()
            assert shutil.disk_usage(HERE).free >= plan["minimum_free_bytes"]
            assert not (_project_file(_PROJECT_ROOT, HERE / "natural-confirmation")).exists() and not (_project_file(_PROJECT_ROOT, HERE / "confirmation-workers")).exists()
            reader.frozen(plan)
            save(directory / "RESOURCE-READY.json", {"development_dispatch_pin": dispatch_pin,
                "plan_pin": plan_pin, "actual_cpu_slots_released": [0, 1], "unix_seconds": time.time()})
            env = dict(os.environ)
            env.update(PYTHONPATH=str(_project_file(_PROJECT_ROOT, ROOT / "src")), OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
            for slot in (0, 1):
                stream = (directory / f"WORKER-{slot}.log").open("x")
                streams.append(stream)
                command = [sys.executable, str(_project_file(_PROJECT_ROOT, HERE / "run_confirmation_workers.py")), "--slot", str(slot)]
                child = await asyncio.create_subprocess_exec(*command, cwd=ROOT, env=env,
                    stdout=stream, stderr=asyncio.subprocess.STDOUT)
                children.append(child)
                save(directory / f"WORKER-{slot}-DISPATCH.json", {"pid": child.pid, "slot": slot,
                    "command": command, "plan_pin": plan_pin, "unix_seconds": time.time(),
                    "no_common_postprocess_lock": True})
            # 一个槽失败也等待另一个自然结束；不杀进程，不提前提取成绩。
            returncodes = await asyncio.gather(*(child.wait() for child in children))
            assert returncodes == [0, 0], "worker失败：保留原START及失败，不自动重跑"
            files, completed = {}, []
            for slot in (0, 1):
                out = _project_file(_PROJECT_ROOT, HERE / "confirmation-workers" / f"worker-{slot}")
                start = json.loads((out / "START.json").read_text())
                end = json.loads((out / "CLOSE.json").read_text())
                expected = list(range(slot, 1024, 2))
                assert start["pid"] == end["pid"] == children[slot].pid and start["plan_pin"] == end["plan_pin"] == plan_pin
                assert end["complete"] and end["failure"] is None
                assert end["attempted_ordinals"] == end["completed_ordinals"] == expected
                assert end["actual_table_calls"] == len(expected) and end["start_pin"] == pin(out / "START.json")
                assert start["nice"] >= 15 and start["background_io"] and not start["common_postprocess_lock_held"]
                for ordinal in expected:
                    before_file = out / f"task-{ordinal:04d}" / "BEFORE.json"
                    after_file = before_file.with_name("AFTER.json")
                    before, after = (json.loads(p.read_text()) for p in (before_file, after_file))
                    assert before["task"] == after["task"] == start["tasks"][ordinal // 2]
                    assert before["pid"] == after["pid"] == children[slot].pid
                    assert after["before_pin"] == pin(before_file) and after["complete"] and after["failure"] is None
                    assert after["run_table_called"] and not before["run_table_called"]
                    files.update({str(before_file): pin(before_file), str(after_file): pin(after_file)})
                completed.extend(expected)
                files.update({str(out / n): pin(out / n) for n in ("START.json", "CLOSE.json")})
            assert sorted(completed) == list(range(1024)) and free_research_slots()
            reader.frozen(plan)
            save(directory / "WORKERS-CLOSED.json", {"complete": True, "plan_pin": plan_pin,
                "actual_table_calls": 1024, "returncodes": returncodes, "completed_ordinals": sorted(completed),
                "files": files, "slots_released": [0, 1], "scores_read": False, "unix_seconds": time.time()})
            readout_command = [sys.executable, str(_project_file(_PROJECT_ROOT, HERE / "t185_close_confirmation.py"))]
            with (directory / "READOUT.log").open("x") as stream:
                process = await asyncio.create_subprocess_exec(*readout_command, cwd=ROOT, env=env,
                    stdout=stream, stderr=asyncio.subprocess.STDOUT)
                save(directory / "READOUT-START.json", {"pid": process.pid, "command": readout_command,
                    "all_workers_naturally_closed": True, "unix_seconds": time.time()})
                code = await process.wait()
            assert code == 0
            terminal = json.loads((_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json")).read_text())
            assert terminal["complete"] and terminal["actual_table_instances"] == 1024 and terminal["source_stable"]
            save(directory / "CLOSED.json", {"complete": True, "pid": os.getpid(), "plan_pin": plan_pin,
                "worker_returncodes": returncodes, "workers_closed_pin": pin(directory / "WORKERS-CLOSED.json"),
                "confirmation_closed_pin": pin(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json")), "readout_exit_code": code,
                "resources_released": True, "strength_or_deadline_admission": False, "unix_seconds": time.time()})
            print(json.dumps({"complete": True, "table_instances": 1024, "confirmation_evidence_only": True}), flush=True)
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            save(directory / "FAILED.json", {"failure": failure, "pid": os.getpid(), "plan_pin": plan_pin,
                "child_pids": [child.pid for child in children], "returncodes_observed": returncodes,
                "children_signalled": False, "no_automatic_retry": True, "unix_seconds": time.time()})
            raise
        finally:
            for stream in streams:
                stream.close()


if __name__ == "__main__":
    asyncio.run(main())
