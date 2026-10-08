"""最短自然补牌组合的精确剪枝枚举；只用于离线结果盲筛查。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter

from hangma_bot.hangma._standard import need as standard_need
from hangma_bot.hangma.internal_types import TILE_ORDER


NATURAL = tuple(TILE_ORDER[:33])


def route_support_fast(after: Counter, melds: int,
                       capacity: dict[str, int]) -> dict:
    """枚举两或三张最短自然补牌组合，逐步向听未降的枝直接剪掉。

    最短缺口 L 是生产求解器的最少未来自然张数。增加一张自然牌最多
    使缺口下降 1；任何长为 L 且最终缺口 0 的组合，任意排列中的每
    一步都必须恰好下降 1。故固定牌序的深度优先剪枝不丢完整组合。
    """
    counts = tuple(after[code] for code in NATURAL)
    left = 4 - melds
    if not 1 <= left <= 4:
        raise ValueError("剩余面子数越界")
    gap = standard_need(counts, 0, left, True)
    result = {"natural_need": gap, "routes": 0, "q1": 0,
              "tested_states": 0}
    if gap not in (2, 3):
        return result
    cap = tuple(capacity[code] for code in NATURAL)
    if any(type(value) is not int or not 0 <= value <= 4 for value in cap):
        raise ValueError("公开容量上界越界")
    support = tuple(i for i, amount in enumerate(cap) if amount > 0)
    used = [0] * 33
    saturated = [0] * 33
    examples = []
    routes = 0
    tested = 0

    def walk(start: int, depth: int, state: tuple[int, ...],
             selected: tuple[int, ...]) -> None:
        nonlocal routes, tested
        for position in range(start, len(support)):
            i = support[position]
            if used[i] >= cap[i]:
                continue
            grown = state[:i] + (state[i] + 1,) + state[i + 1:]
            tested += 1
            if standard_need(grown, 0, left, True) != gap - depth - 1:
                continue
            used[i] += 1
            new_selected = selected + (i,)
            if depth + 1 == gap:
                routes += 1
                if len(examples) < 5:
                    examples.append([NATURAL[j] for j in new_selected])
                for j in set(new_selected):
                    if used[j] == cap[j]:
                        saturated[j] += 1
            else:
                walk(position, depth + 1, grown, new_selected)
            used[i] -= 1

    walk(0, 0, counts, ())
    result.update({"routes": routes, "q1": routes - max(saturated),
                   "tested_states": tested, "route_examples": examples})
    return result
