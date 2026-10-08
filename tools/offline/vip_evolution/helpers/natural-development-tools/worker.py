"""实际后台worker独占一个t182槽，按冻结清单各跑8桌；结束释放实际FD。"""

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
import argparse
import asyncio
import ctypes
import fcntl
import json
import os
import sys
import time
from common import HERE, ROOT, PLAN, pin, save, unchanged, execution_approved, stop_new_tables
from run_table import run


def background():
    before = os.getpriority(os.PRIO_PROCESS, 0)
    if before < 19:
        os.nice(19 - before)
    nice = os.getpriority(os.PRIO_PROCESS, 0)
    low_io = False
    observed = None
    if sys.platform == "darwin":
        lib = ctypes.CDLL(None, use_errno=True)
        result = lib.setiopolicy_np(0, 0, 3)
        if result == 0:
            observed = lib.getiopolicy_np(0, 0)
            low_io = observed == 3
    return {"nice_before": before, "nice_actual": nice, "low_IO_actual": low_io, "io_policy_actual": observed}


async def main(lane, fd, stage):
    plan = json.loads(PLAN.read_text())
    execution_approved(plan, stage)
    plan_pin = pin(PLAN)
    assert unchanged(plan)
    expected = os.stat(plan["slot_paths"][lane])
    actual = os.fstat(fd)
    assert (expected.st_dev, expected.st_ino) == (actual.st_dev, actual.st_ino)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    priorities = background()
    assert priorities["nice_actual"] == 19 and priorities["low_IO_actual"] is True
    ordinals = plan["pilot_ordinals"] if stage == "pilot" else [ordinal for ordinal in plan["lanes"][lane] if ordinal in plan["remaining_ordinals"]]
    if stage == "remaining":
        assert json.loads((_project_file(_PROJECT_ROOT, HERE / "PILOT-CLOSED.json")).read_text())["complete"] is True
    directory = _project_file(_PROJECT_ROOT, HERE / "workers" / f"{stage}-{lane}")
    directory.mkdir(parents=True, exist_ok=False)
    save(directory / "START.json", {"lane": lane, "pid": os.getpid(), "slot_fd": fd,
        "slot_path": plan["slot_paths"][lane], "plan_pin": plan_pin, "priorities": priorities,
        "ordinals": ordinals, "slot_actually_locked": True, "stage": stage})
    results = []
    failure = None
    started = time.monotonic()
    try:
        for ordinal in ordinals:
            if (_project_file(_PROJECT_ROOT, HERE / "STOP-NEW-TABLES.json")).exists():
                break
            assert unchanged(plan) and pin(PLAN) == plan_pin
            task = plan["tasks"][ordinal]
            print(json.dumps({"lane": lane, "table_start": task["table_no"], "pid": os.getpid()}), flush=True)
            result = await run(task, plan)
            results.append({"table_no": task["table_no"], "complete": result["complete"],
                "failure": result["failure"], "focal_score_calls": result["focal_score_calls"]})
            save(directory / "PROGRESS.json", {"completed_attempts": len(results), "results": results}, replace=True)
            print(json.dumps({"lane": lane, "table_terminal": task["table_no"], "complete": result["complete"]}), flush=True)
            if not result["complete"]:
                stop_new_tables({"failed_table": task["table_no"], "failure": result["failure"], "no_retry": True})
                break
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
        stop_new_tables({"failed_lane": lane, "failure": failure, "no_retry": True})
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        released = True
    stable = unchanged(plan) and pin(PLAN) == plan_pin
    complete = failure is None and stable and len(results) == len(ordinals) and all(result["complete"] for result in results)
    save(directory / "CLOSED.json", {"lane": lane, "pid": os.getpid(), "complete": complete,
        "failure": failure, "source_stable": stable, "results": results, "slot_released": released,
        "wall_seconds": time.monotonic() - started, "priorities": priorities})
    return 0 if complete else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", type=int, required=True)
    parser.add_argument("--slot-fd", type=int, required=True)
    parser.add_argument("--stage", choices=("pilot", "remaining"), required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.lane, args.slot_fd, args.stage)))
