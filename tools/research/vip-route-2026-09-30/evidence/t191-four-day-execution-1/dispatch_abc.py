"""唯一派发固定四片，自然等待全部退出；不读分、不重跑预检。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1'

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
import fcntl
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE / "evaluation")))
from abc_support import OLD, ROOT, background_priority, pin, read, require, resource_slot_paths, save, unchanged


def released_slots():
    """试取并立即释放共享研究槽；不会操作已有持有者。"""
    handles = []
    try:
        for path in resource_slot_paths(OLD, 4):
            handle = path.open("a+")
            handles.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        for handle in handles:
            handle.close()


async def main(args):
    """保存实际子进程与自然终态；失败也等已有子进程，不启动下一批。"""
    background_priority()
    plan_path, output = Path(args.plan).resolve(), Path(args.output).resolve()
    plan, plan_pin = read(plan_path), pin(plan_path)
    require(unchanged(plan), "派发前冻结材料漂移")
    preflight = read(args.preflight)
    require(preflight["complete"] and preflight["resources_released"] and
        preflight["plan_pin"] == plan_pin, "首目标预检未通过")
    directory = output / "dispatch"
    with (output / ".dispatch-owner.lock").open("a+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        released_slots()
        directory.mkdir(exist_ok=False)
        save(directory / "START.json", {"pid": os.getpid(), "plan_pin": plan_pin,
            "dispatcher_pin": pin(Path(__file__)), "preflight_pin": pin(Path(args.preflight)),
            "approval_pin": pin(Path(args.approval)), "preflight_reused": True,
            "additional_worlds_allowed": False, "performance_scores_accessed": False})
        children, streams, codes, failure = [], [], [], None
        try:
            for slot in range(4):
                command = [sys.executable, str(_project_file(_PROJECT_ROOT, HERE / "evaluation/run_abc.py")),
                    "--plan", str(plan_path), "--output", str(output),
                    "--approval", str(Path(args.approval).resolve()), "--worker", str(slot),
                    "--reuse-preflight", str(Path(args.preflight).resolve()), "--execute"]
                stream = (directory / f"WORKER-{slot}.log").open("x")
                streams.append(stream)
                env = dict(os.environ, PYTHONPATH=str(_project_file(_PROJECT_ROOT, ROOT / "src")),
                    OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
                child = await asyncio.create_subprocess_exec(*command, cwd=ROOT,
                    env=env, stdout=stream, stderr=asyncio.subprocess.STDOUT)
                children.append(child)
                save(directory / f"WORKER-{slot}-DISPATCH.json", {"pid": child.pid,
                    "slot": slot, "command": command})
            codes = await asyncio.gather(*(child.wait() for child in children))
            require(codes == [0] * 4, "固定分片自然失败，保留原件与费用")
            for slot, child in enumerate(children):
                closed = read(output / f"worker-{slot}/CLOSE.json")
                require(closed["pid"] == child.pid and closed["complete"] and
                    closed["failure"] is None, "真实分片未全闭合")
            require(unchanged(plan) and pin(plan_path) == plan_pin, "派发结束来源漂移")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            codes = await asyncio.gather(*(child.wait() for child in children))
        finally:
            for stream in streams:
                stream.close()
            released = False
            try:
                released_slots()
                released = True
            except BlockingIOError:
                failure = failure or {"type": "ResourceStillOwned", "message": "共享研究槽未释放"}
            save(directory / "CLOSED.json", {"complete": failure is None,
                "failure": failure, "plan_pin": plan_pin,
                "worker_returncodes": codes, "children": [child.pid for child in children],
                "all_processes_naturally_waited": True, "resources_released": released,
                "performance_scores_accessed": False})
        require(failure is None, "派发未通过；不得自动追加费用")
    print(json.dumps({"complete": True, "resources_released": released,
        "worker_returncodes": codes, "performance_scores_accessed": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("plan", "output", "approval", "preflight"):
        parser.add_argument("--" + field, required=True)
    asyncio.run(main(parser.parse_args()))
