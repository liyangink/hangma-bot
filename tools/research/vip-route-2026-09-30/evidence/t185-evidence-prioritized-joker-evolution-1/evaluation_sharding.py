"""后续完整桌评测的四进程分片；不改变当前冻结批，不启动进程或桌赛。"""

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
from collections import Counter
from pathlib import Path

DEFAULT_CPU_WORKERS = 4


def partition_tasks(tasks, cpu_worker_count=DEFAULT_CPU_WORKERS):
    """将完整桌任务唯一分配到后台槽，返回槽顺序排列的任务列表。

    ordinal 为本批从零开始的连续序号；root 为母来源序号，rotation 为
    换座序号，arm 为父代/候选编号。相同来源、换座和算法只可出现一次。
    不计算积分、不修改输入；非法数量、漏项和重复任务直接拒绝。
    """
    if type(cpu_worker_count) is not int or cpu_worker_count < DEFAULT_CPU_WORKERS:
        raise ValueError("后续完整桌评测至少使用四个后台计算进程")
    if not isinstance(tasks, (list, tuple)) or len(tasks) < cpu_worker_count:
        raise ValueError("任务数量不足或任务不是固定列表")
    originals = []
    for ordinal, task in enumerate(tasks):
        if not isinstance(task, dict) or set(task) != {"ordinal", "root", "rotation", "arm"}:
            raise ValueError("完整桌任务字段不匹配")
        if any(type(task[k]) is not int for k in task):
            raise ValueError("完整桌任务编号必须为整数，布尔值不算整数")
        if task["ordinal"] != ordinal or task["root"] < 1 or not 0 <= task["rotation"] <= 3 or task["arm"] < 0:
            raise ValueError("任务序号不连续或来源/换座/算法编号非法")
        originals.append((task["root"], task["rotation"], task["arm"]))
    if len(set(originals)) != len(originals):
        raise ValueError("相同完整桌被重复派发")
    lanes = [[] for _ in range(cpu_worker_count)]
    for task in tasks:
        lanes[task["ordinal"] % cpu_worker_count].append(dict(task))
    flattened = [task for lane in lanes for task in lane]
    if Counter(t["ordinal"] for t in flattened) != Counter(range(len(tasks))):
        raise RuntimeError("分片遗漏或重复任务")
    if max(map(len, lanes)) - min(map(len, lanes)) > 1:
        raise RuntimeError("后台槽任务数量分配不均")
    return lanes


def resource_slot_paths(existing_slot_directory, cpu_worker_count=DEFAULT_CPU_WORKERS):
    """返回共用计算槽锁路径；沿用旧 0/1 槽，新增 2/3 槽，避免另起锁绕过旧占用。

    路径仅返回给下一批派发器；本函数不创建锁文件、不取锁或释放他人资源。
    实际调用方必须验证前批自然终态，派发前试取全部槽，worker 持锁到自然结束。
    """
    if type(cpu_worker_count) is not int or cpu_worker_count < DEFAULT_CPU_WORKERS:
        raise ValueError("后续完整桌评测至少使用四个后台计算进程")
    root = Path(existing_slot_directory)
    return tuple(root / f".resource-scheduling-worker-{slot}.lock" for slot in range(cpu_worker_count))
