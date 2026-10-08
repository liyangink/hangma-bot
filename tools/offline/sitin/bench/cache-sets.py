#!/usr/bin/env python3
"""坐隐 1.2d：区分"缓存/带宽争用"与"调度/拓扑损耗"。

假设：桌赛负载每进程有较大热点工作集（hand_analysis 的 65536 条记忆化缓存 +
每桌百万级标准型递归状态），并发时在共享缓存/内存带宽上互相挤出，
导致**每桌 CPU 时间上升**（1.2b 实测 1.468 -> 2.646 秒/桌，1.80 倍）。

对照设计（同一 P/E 拓扑，只改工作集大小，指令数相同）：
  S_small = 数组 4 KB（L1 内）—— 纯 CPU/拓扑
  S_large = 数组 4 MB（L2/L3 级）—— 相同循环，但访问共享缓存/带宽
若 S_large 在 15 并发下的效率明显低于 S_small，则**缓存/带宽争用**成立。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools/bench'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json, subprocess, sys, time
from pathlib import Path

ROOT = Path("/Users/liyang/Projects/Opensource/hangma-bot/runs/bench-sitin-1.2d")
ROOT.mkdir(parents=True, exist_ok=True)
PY = sys.executable
LEVELS = [1, 4, 8, 15]
ITERS = 400_000

TEMPLATE = """
import time
buf = [i * 7919 % 104729 for i in range(NELEM)]
acc = 0
t = time.monotonic()
for step in range(ITERS):
    acc += buf[(step * 31) % NELEM]
print(time.monotonic() - t)
"""

def script(nbytes):
    return TEMPLATE.replace("NELEM", str(nbytes // 8)).replace("ITERS", str(ITERS))

def run(s, level):
    ps = [subprocess.Popen([PY, "-c", s], stdout=subprocess.PIPE, text=True) for _ in range(level)]
    t0 = time.monotonic()
    outs = [p.communicate()[0].strip() for p in ps]
    wall = time.monotonic() - t0
    return wall, sum(float(o) for o in outs if o)

rows = []
for label, nb in (("S_small_4KB", 4096), ("S_large_4MB", 4_194_304)):
    s = script(nb)
    base = None
    for level in LEVELS:
        if level == 1:
            run(s, 1)
        wall, cpu = run(s, level)
        if base is None:
            base = level / wall
        eff = (level / wall) / base / level
        row = {"set": label, "concurrency": level, "wall": round(wall, 3),
               "cpu_per_unit": round(cpu / level, 3), "efficiency": round(eff, 3)}
        rows.append(row)
        print("%-14s %2d 并发 | 墙钟 %6.3fs | 单位CPU %7.3fs | 效率 %3.0f%%"
              % (label, level, wall, row["cpu_per_unit"], eff * 100), flush=True)
(_project_file(_PROJECT_ROOT, ROOT / "cache-sets.json")).write_text(json.dumps(rows, indent=2) + "\n")

print()
for label in ("S_small_4KB", "S_large_4MB"):
    r1 = [x for x in rows if x["set"] == label and x["concurrency"] == 1][0]
    r15 = [x for x in rows if x["set"] == label and x["concurrency"] == 15][0]
    print("%-14s 15 并发效率 %3.0f%%，单位CPU 膨胀 %.2f 倍"
          % (label, r15["efficiency"] * 100, r15["cpu_per_unit"] / r1["cpu_per_unit"]))
print("对照坐隐桌赛      15 并发效率  47%%，单位CPU 膨胀 1.80 倍")
