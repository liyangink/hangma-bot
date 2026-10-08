"""两个固定奇偶后台槽执行T185全批；每次原桌调用有真实前后收据。"""

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
import asyncio
import ctypes
import fcntl
import json
import os
import sys
import time
from pathlib import Path

from common import HERE, OLD, ROOT, pin, save
import t185_run_development as runtime
import t185_close_development as reader


async def main(slot):
    """研究槽冲突或原T182未闭合就拒绝；不重试原桌，不持赛后采集锁。"""
    assert slot in (0, 1) and sys.platform == "darwin"
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        os.nice(15 - os.getpriority(os.PRIO_PROCESS, 0))
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    old_terminal = OLD / "RESOURCE-SCHEDULING-CLOSED.json"
    old = json.loads(old_terminal.read_text())
    assert old["complete"] and old["source_stable"] and old["original_table_instances"] == 512
    assert old["max_cpu_workers"] == 2 and old["actual_successful_workers"] == [0, 1]
    lock_path = OLD / f".resource-scheduling-worker-{slot}.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan_path = _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json")
        plan = json.loads(plan_path.read_text())
        reader.validate_plan(plan)
        reader.frozen(plan)
        plan_pin = pin(plan_path)
        tasks = [{"ordinal": o, "root": i, "rotation": r, "arm": a}
                 for o, (i, r, a) in enumerate((i, r, a) for i in range(1, 33) for r in plan["rotations"]
                    for a in range(len(plan["candidates"]) + 1)) if o % 2 == slot]
        out = _project_file(_PROJECT_ROOT, HERE / "development-workers" / f"worker-{slot}")
        out.mkdir(parents=True, exist_ok=False)
        save(out / "START.json", {"pid": os.getpid(), "slot": slot, "plan_pin": plan_pin, "tasks": tasks,
            "old_resource_terminal_pin": pin(old_terminal), "nice": os.getpriority(os.PRIO_PROCESS, 0),
            "background_io": True, "shared_cpu_slot_lock": str(lock_path), "common_postprocess_lock_held": False,
            "unix_seconds": time.time(), "max_cpu_workers": 2, "strength_or_deadline_admission": False})
        attempted, completed, failure = [], [], None
        try:
            for task in tasks:
                reader.frozen(plan)
                assert pin(plan_path) == plan_pin
                destination = _project_file(_PROJECT_ROOT, HERE / "natural-development" / f"root-{task['root']:03d}" / f"seat-{task['rotation']}-arm-{task['arm']}")
                assert not destination.exists()
                attempted.append(task["ordinal"])
                receipt = out / f"task-{task['ordinal']:04d}"
                receipt.mkdir(exist_ok=False)
                save(receipt / "BEFORE.json", {"task": task, "pid": os.getpid(), "plan_pin": plan_pin,
                    "original_directory_absent": True, "run_table_called": False, "unix_seconds": time.time()})
                task_failure = None
                try:
                    await runtime.run_table(task["root"], task["rotation"], task["arm"], plan)
                    closure = json.loads((destination / "CLOSURE.json").read_text())
                    assert closure["complete"] and closure["source_stable"] and closure["failure"] is None
                except BaseException as error:
                    task_failure = {"type": type(error).__name__, "message": str(error)}
                save(receipt / "AFTER.json", {"task": task, "pid": os.getpid(), "plan_pin": plan_pin,
                    "before_pin": pin(receipt / "BEFORE.json"), "run_table_called": True,
                    "complete": task_failure is None, "failure": task_failure,
                    "table_files": {str(p): pin(p) for p in destination.iterdir() if p.is_file()} if destination.exists() else {},
                    "unix_seconds": time.time()})
                if task_failure:
                    raise RuntimeError(str(task_failure))
                completed.append(task["ordinal"])
                print(json.dumps({"slot": slot, "ordinal": task["ordinal"], "complete": True}), flush=True)
            reader.frozen(plan)
            assert pin(plan_path) == plan_pin
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        finally:
            save(out / "CLOSE.json", {"pid": os.getpid(), "slot": slot, "plan_pin": plan_pin,
                "start_pin": pin(out / "START.json"), "attempted_ordinals": attempted, "completed_ordinals": completed,
                "complete": failure is None and completed == [t["ordinal"] for t in tasks], "failure": failure,
                "actual_table_calls": len(attempted), "strength_or_deadline_admission": False,
                "unix_seconds": time.time()})
        if failure:
            raise RuntimeError("保留已执行原桌，不自动覆盖重试：" + str(failure))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, choices=(0, 1), required=True)
    asyncio.run(main(parser.parse_args().slot))
