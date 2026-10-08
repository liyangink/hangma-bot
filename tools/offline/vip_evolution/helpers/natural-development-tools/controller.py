"""本次离线32桌实际派发及自然终态controller；不联网、不盯盘、不碰玩家。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = '.private/t199-four-step-execution/natural-development-tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import fcntl
import json
import os
import subprocess
import sys
import time
import argparse
from pathlib import Path
from common import HERE, ROOT, PLAN, pin, save, unchanged, execution_approved, stop_new_tables


def main(stage):
    plan = json.loads(PLAN.read_text())
    execution_approved(plan, stage)
    if (_project_file(_PROJECT_ROOT, HERE / "STOP-NEW-TABLES.json")).exists():
        raise ValueError("已有自然诊断失败；不继续/补桌")
    plan_pin = pin(PLAN)
    assert unchanged(plan) and len(plan["tasks"]) == 32
    if stage == "remaining":
        assert json.loads((_project_file(_PROJECT_ROOT, HERE / "PILOT-CLOSED.json")).read_text())["complete"] is True
    lanes = [0] if stage == "pilot" else list(range(4))
    logs = _project_file(_PROJECT_ROOT, HERE / (stage + "-worker-logs"))
    logs.mkdir(exist_ok=False)
    slots = []
    workers = []
    started = time.monotonic()
    prefix = "PILOT" if stage == "pilot" else "CONTROLLER"
    save(_project_file(_PROJECT_ROOT, HERE / (prefix + "-START.json")), {"pid": os.getpid(), "plan_pin": plan_pin,
        "source_stable": True, "planned_table_instances": len(plan["pilot_ordinals"]) if stage == "pilot" else len(plan["remaining_ordinals"]),
        "slot_paths": [plan["slot_paths"][lane] for lane in lanes], "stage": stage})
    try:
        for lane in lanes:
            path = plan["slot_paths"][lane]
            slot = open(path, "a+")
            slots.append(slot)
            fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
        environment = dict(os.environ, PYTHONPATH=str(_project_file(_PROJECT_ROOT, ROOT / "src")), PYTHONDONTWRITEBYTECODE="1")
        for lane, slot in zip(lanes, slots):
            log = (logs / f"worker-{lane}.log").open("xb")
            process = subprocess.Popen([sys.executable, "-B", str(_project_file(_PROJECT_ROOT, HERE / "worker.py")), "--lane", str(lane),
                "--slot-fd", str(slot.fileno()), "--stage", stage], cwd=ROOT, env=environment, pass_fds=(slot.fileno(),),
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            log.close()
            workers.append({"lane": lane, "pid": process.pid, "process": process})
        save(_project_file(_PROJECT_ROOT, HERE / (prefix + "-DISPATCHED.json")), {"controller_pid": os.getpid(), "plan_pin": plan_pin,
            "workers": [{"lane": row["lane"], "pid": row["pid"]} for row in workers],
            "actual_workers": len(lanes), "all_slots_inherited": True, "table_retries": 0, "stage": stage})
        # 子进程继承同一open-file-description；父关闭后各worker独持自己的槽。
        for slot in slots:
            slot.close()
        slots = []
        exits = []
        for row in workers:
            exits.append({"lane": row["lane"], "pid": row["pid"], "exit_code": row["process"].wait()})
        terminals = [json.loads((_project_file(_PROJECT_ROOT, HERE / "workers" / f"{stage}-{row['lane']}" / "CLOSED.json")).read_text()) for row in workers]
        stable = unchanged(plan) and pin(PLAN) == plan_pin
        complete = stable and all(row["exit_code"] == 0 for row in exits) and all(row["complete"] for row in terminals)
        save(_project_file(_PROJECT_ROOT, HERE / (prefix + "-CLOSED.json")), {"complete": complete, "controller_pid": os.getpid(),
            "plan_pin": plan_pin, "source_stable": stable, "workers": exits,
            "worker_terminals": terminals, "all_our_worker_slots_released": all(row["slot_released"] for row in terminals),
            "wall_seconds": time.monotonic() - started, "planned_table_instances": len(plan["pilot_ordinals"]) if stage == "pilot" else len(plan["remaining_ordinals"]),
            "table_retries": 0, "stage": stage,
            "HTTP_calls": 0, "LLM_calls": 0})
        return 0 if complete else 2
    except BaseException as error:
        stop_new_tables({"controller_failure": type(error).__name__, "no_retry": True})
        save(_project_file(_PROJECT_ROOT, HERE / (prefix + "-FAILED.json")), {"failure": {"type": type(error).__name__, "message": str(error)},
            "controller_pid": os.getpid(), "workers_started": [{"lane": row["lane"], "pid": row["pid"]} for row in workers],
            "plan_pin": plan_pin, "source_stable": unchanged(plan), "actual_tables_not_retried": True})
        raise
    finally:
        for slot in slots:
            slot.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("pilot", "remaining"), required=True)
    raise SystemExit(main(parser.parse_args().stage))
