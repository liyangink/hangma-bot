#!/usr/bin/env python3
"""坐隐 1.2c：并发扩展的对照实验（把"机器曲面"与"本负载特性"分开）。

问题：1.2b 显示 15 并发效率 47%，且每桌 CPU 时间从 1.468 涨到 2.646 秒（1.80 倍）。
需要区分两种解释：
  A. 机器本身的并发曲面（P/E 核、频率墙）——与我们的代码无关；
  B. 我们负载特有的资源争用（分配/缓存/内核态）。

本机拓扑（sysctl）：hw.ncpu=15，hw.perflevel0.physicalcpu=5（性能核），
hw.perflevel1.physicalcpu=10（能效核），无 SMT。

两组对照：
  C1 = 纯 C 级 CPU（sha256 循环）——最小内存足迹、无分配；
  C2 = 纯 Python 分配/GC 负载（小对象与 dict）——高分配率、低算术。
解读：若 C1 在 15 并发也只有约 60%，则是机器曲面；若 C1 接近线性而 C2 掉，则是分配/GC。
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

ROOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools/bench')
PY = sys.executable
LEVELS = [1, 2, 4, 8, 15]
WORK = 3_000_000

C1 = """
import hashlib, time
h = b"x" * 64
t = time.monotonic()
for _ in range(%d):
    h = hashlib.sha256(h).digest()
print(time.monotonic() - t)
""" % WORK

C2 = """
import time
t = time.monotonic()
acc = 0
for i in range(%d):
    d = {"a": i, "b": str(i), "c": (i, i + 1)}
    acc += d["a"]
print(time.monotonic() - t)
""" % (WORK // 3)

def run(script, level):
    ps = [subprocess.Popen([PY, "-c", script], stdout=subprocess.PIPE, text=True) for _ in range(level)]
    t0 = time.monotonic()
    outs = [p.communicate()[0].strip() for p in ps]
    wall = time.monotonic() - t0
    return wall, sum(float(o) for o in outs if o)

rows = []
for name, script in (("C1_sha256_cpu", C1), ("C2_python_alloc", C2)):
    base = None
    for level in LEVELS:
        if level == 1:
            run(script, 1)          # 预热，消掉首进程冷启动
        wall, cpu = run(script, level)
        if base is None:
            base = level / wall
        eff = (level / wall) / base / level
        row = {"control": name, "concurrency": level, "wall": round(wall, 3),
               "cpu_per_unit": round(cpu / level, 4), "efficiency": round(eff, 4)}
        rows.append(row)
        print("%-18s %2d 并发 | 墙钟 %6.3fs | 单位CPU %7.4fs | 效率 %3.0f%%"
              % (name, level, wall, row["cpu_per_unit"], eff * 100), flush=True)

(_project_file(_PROJECT_ROOT, ROOT / "controls.json")).write_text(json.dumps(rows, indent=2) + "\n")
print()
for name in ("C1_sha256_cpu", "C2_python_alloc"):
    r1 = [r for r in rows if r["control"] == name and r["concurrency"] == 1][0]
    r15 = [r for r in rows if r["control"] == name and r["concurrency"] == 15][0]
    print("%-18s 15 并发效率 %3.0f%%，单位 CPU 膨胀 %.2f 倍"
          % (name, r15["efficiency"] * 100, r15["cpu_per_unit"] / r1["cpu_per_unit"]))
print("坐隐桌赛（1.2b）      15 并发效率  47%%，单位 CPU 膨胀 1.80 倍")

