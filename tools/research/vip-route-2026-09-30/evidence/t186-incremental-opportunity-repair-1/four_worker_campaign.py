"""T186分阶段完整桌执行器：四个共用研究槽、唯一分片与全收据验收。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

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
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, OLD, pin, save
from evaluation_sharding import partition_tasks, resource_slot_paths
from t185_prepare_confirmation import background_priority
import full_table_runtime


def require(condition, message):
    """计划或收据不一致就停止新任务，保留已启动任务及费用。"""
    if not condition:
        raise ValueError(message)


def validate(plan_path):
    """事前核全部四换座父子任务；未暴露确认池不能作为自动接续。"""
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text())
    require(plan_path.parent == HERE and plan["plan_path"] == str(plan_path) and
            plan["schema"] == "t186-staged-development/1" and plan["rounds"] == 8 and
            plan["cpu_worker_count"] == 4 and plan["rotations"] == [0, 1, 2, 3], "阶段或进程配置不对应")
    full_table_runtime.dev.frozen(plan)
    prior = _project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json")
    old = json.loads(prior.read_text())
    require(plan["prior_closed_pin"] == pin(prior) and old["complete"] and old["resources_released"],
            "前批资源未自然结束")
    require(plan["root_indices"] == sorted(set(plan["root_indices"])) and
            all(type(i) is int and 1 <= i <= 64 for i in plan["root_indices"]), "开发来源范围非法")
    expected = [{"ordinal": o, "root": i, "rotation": r, "arm": a}
        for o, (i, r, a) in enumerate((i, r, a) for i in plan["root_indices"] for r in range(4)
                                     for a in range(1 + len(plan["candidates"])))]
    require(expected == plan["tasks"] and len(expected) == plan["planned_table_instances"], "全任务有重漏")
    require(plan["independent_confirmation_auto_dispatch"] is False, "不得自动购买大确认")
    output_name = "runtime-preflight-tables" if plan.get("purpose") == "runtime_preflight" else "natural-development"
    require(plan.get("purpose") != "runtime_preflight" or len(plan["candidates"]) == 0,
            "执行器预检只能用已知S02，不承接未合格候选")
    require(Path(plan["dispatch_directory"]).parent == HERE and
            Path(plan["output_directory"]) == _project_file(_PROJECT_ROOT, HERE / output_name), "输出不在本批独立目录")
    return plan, pin(plan_path), partition_tasks(expected, 4)


async def worker(plan_path, slot):
    """四个后台槽各自持锁；每桌成功或失败都保存真实调用前后收据。"""
    background_priority()
    plan, plan_pin, lanes = validate(plan_path)
    path = resource_slot_paths(OLD, 4)[slot]
    out = Path(plan["dispatch_directory"]) / f"worker-{slot}"
    with path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out.mkdir(exist_ok=False)
        tasks = lanes[slot]
        save(out / "START.json", {"pid": os.getpid(), "slot": slot, "plan_pin": plan_pin,
            "tasks": tasks, "nice": os.getpriority(os.PRIO_PROCESS, 0), "background_io": True,
            "shared_cpu_slot_lock": str(path), "common_postprocess_lock_held": False})
        attempted, completed, failure = [], [], None
        try:
            for task in tasks:
                full_table_runtime.dev.frozen(plan)
                require(pin(Path(plan_path)) == plan_pin, "阶段计划漂移")
                destination = Path(plan["output_directory"]) / f"root-{task['root']:03d}" / \
                              f"seat-{task['rotation']}-arm-{task['arm']}"
                require(not destination.exists(), "原桌存在，不自动重复或覆盖")
                receipt = out / f"task-{task['ordinal']:04d}"
                receipt.mkdir()
                attempted.append(task["ordinal"])
                save(receipt / "BEFORE.json", {"pid": os.getpid(), "task": task, "plan_pin": plan_pin,
                    "run_table_called": False, "unix_seconds": time.time()})
                problem = None
                try:
                    await full_table_runtime.run_table(task["root"], task["rotation"], task["arm"], plan, plan_pin)
                    closed = json.loads((destination / "CLOSURE.json").read_text())
                    require(closed["complete"] and closed["source_stable"] and closed["failure"] is None,
                            "原桌未完整闭合")
                except BaseException as error:
                    problem = {"type": type(error).__name__, "message": str(error)}
                save(receipt / "AFTER.json", {"pid": os.getpid(), "task": task, "plan_pin": plan_pin,
                    "run_table_called": True, "before_pin": pin(receipt / "BEFORE.json"),
                    "complete": problem is None, "failure": problem,
                    "table_files": {str(p): pin(p) for p in destination.iterdir() if p.is_file()}
                                   if destination.exists() else {}})
                require(problem is None, "原桌失败，不重试")
                completed.append(task["ordinal"])
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        save(out / "CLOSE.json", {"pid": os.getpid(), "slot": slot, "plan_pin": plan_pin,
            "start_pin": pin(out / "START.json"), "attempted_ordinals": attempted,
            "completed_ordinals": completed, "actual_table_calls": len(attempted),
            "complete": failure is None and completed == [t["ordinal"] for t in tasks], "failure": failure})
        require(failure is None, "worker失败，保留费用与全部原件")


def free_slots():
    """试取四个共用研究槽并立即释放；不操作持有者进程。"""
    handles = []
    try:
        for path in resource_slot_paths(OLD, 4):
            handle = path.open("a+")
            handles.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        for handle in handles:
            handle.close()


async def dispatch(plan_path):
    """全阶段自然退出后核全部收据；分数读回另行执行，不启动下一阶段。"""
    background_priority()
    plan, plan_pin, lanes = validate(plan_path)
    directory = Path(plan["dispatch_directory"])
    with (_project_file(_PROJECT_ROOT, HERE / ".campaign-owner.lock")).open("a+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        free_slots()
        directory.mkdir(exist_ok=False)
        save(directory / "START.json", {"pid": os.getpid(), "plan_pin": plan_pin,
            "cpu_worker_count": 4, "actual_table_calls_at_start": 0,
            "common_postprocess_lock_held": False})
        children, streams, completed, failure = [], [], [], None
        try:
            environment = dict(os.environ, PYTHONPATH=str(_project_file(_PROJECT_ROOT, ROOT / "src")), OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
            for slot in range(4):
                command = [sys.executable, str(Path(__file__)), "--plan", str(plan_path), "--slot", str(slot)]
                stream = (directory / f"WORKER-{slot}.log").open("x")
                streams.append(stream)
                child = await asyncio.create_subprocess_exec(*command, cwd=ROOT, env=environment,
                    stdout=stream, stderr=asyncio.subprocess.STDOUT)
                children.append(child)
                save(directory / f"WORKER-{slot}-DISPATCH.json", {"pid": child.pid, "slot": slot, "command": command})
            codes = await asyncio.gather(*(child.wait() for child in children))
            require(codes == [0] * 4, "worker失败，不能读分或追加下一阶段")
            for slot, child in enumerate(children):
                d = directory / f"worker-{slot}"
                start, end = (json.loads((d / f"{n}.json").read_text()) for n in ("START", "CLOSE"))
                expected = [t["ordinal"] for t in lanes[slot]]
                require(start["pid"] == end["pid"] == child.pid and start["plan_pin"] == end["plan_pin"] == plan_pin and
                        start["tasks"] == lanes[slot] and start["nice"] >= 15 and start["background_io"] and
                        end["complete"] and end["failure"] is None and end["start_pin"] == pin(d / "START.json") and
                        end["attempted_ordinals"] == end["completed_ordinals"] == expected and
                        end["actual_table_calls"] == len(expected), "worker完整任务收据不对应")
                for task in lanes[slot]:
                    receipt = d / f"task-{task['ordinal']:04d}"
                    before, after = (json.loads((receipt / f"{n}.json").read_text()) for n in ("BEFORE", "AFTER"))
                    destination = Path(plan["output_directory"]) / f"root-{task['root']:03d}" / \
                                  f"seat-{task['rotation']}-arm-{task['arm']}"
                    mandatory = {str(destination / name) for name in
                        ("START.json", "CLOSURE.json", "PAIRING-IDENTITY.json", "views.jsonl.gz", "focal-decisions.jsonl.gz")}
                    require(mandatory <= set(after["table_files"]), "逐桌原件集合缺项")
                    require(before["task"] == after["task"] == task and before["pid"] == after["pid"] == child.pid and
                            before["plan_pin"] == after["plan_pin"] == plan_pin and not before["run_table_called"] and
                            after["run_table_called"] and after["complete"] and after["failure"] is None and
                            after["before_pin"] == pin(receipt / "BEFORE.json") and
                            all(pin(Path(p)) == h for p, h in after["table_files"].items()), "逐桌收据或原件不对应")
                    completed.append(task["ordinal"])
            require(sorted(completed) == list(range(plan["planned_table_instances"])), "四槽任务重漏")
            free_slots()
            full_table_runtime.dev.frozen(plan)
            require(pin(Path(plan_path)) == plan_pin, "阶段结束计划漂移")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            await asyncio.gather(*(child.wait() for child in children))
        finally:
            for stream in streams:
                stream.close()
            attempted = []
            for slot in range(len(children)):
                close_path = directory / f"worker-{slot}/CLOSE.json"
                attempted.append(json.loads(close_path.read_text())["actual_table_calls"] if close_path.exists() else None)
            save(directory / "CLOSED.json", {"complete": failure is None, "failure": failure,
                "plan_pin": plan_pin, "actual_table_calls": sum(attempted) if None not in attempted else None,
                "verified_complete_table_calls": len(completed), "completed_ordinals": sorted(completed),
                "worker_attempted_table_calls": attempted,
                "child_pids": [c.pid for c in children], "worker_returncodes": [c.returncode for c in children],
                "cpu_worker_count": 4, "resources_released": failure is None,
                "scores_read": False, "independent_strength_or_online_admission": False})
        require(failure is None, "阶段失败，原记录保留，不自动重跑")
        print(json.dumps({"complete": True, "cpu_workers": 4, "tables": len(completed)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--slot", type=int, choices=range(4))
    args = parser.parse_args()
    asyncio.run(dispatch(args.plan) if args.slot is None else worker(args.plan, args.slot))
