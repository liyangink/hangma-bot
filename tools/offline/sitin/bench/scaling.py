#!/usr/bin/env python3
"""坐隐 1.2b：受控并发扩展曲线。

修正 1.2 的测量缺陷：先前 8/15 路每次只有 16 桌、1/2 路有 32 桌，
每进程工作量不同，加速比不可比。本测试让**每个分片固定 16 桌**
（4 根 × 2 换座 × 2 臂），并令总桌数 = 并发数 × 16。
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
import json, os, re, subprocess, sys, time
from pathlib import Path

REPO = Path("/Users/liyang/Projects/Opensource/hangma-bot")
ROOT = _project_file(_PROJECT_ROOT, REPO / "runs/bench-sitin-1.2b")
PY = str(_project_file(_PROJECT_ROOT, REPO / ".venv/bin/python3"))
EVAL = str(_project_file(_PROJECT_ROOT, REPO / "scripts/evaluate.py"))
BASE = json.loads((_project_file(_PROJECT_ROOT, REPO / "runs/bench-sitin-1.2/single/experiment.json")).read_text())
LEVELS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15]
TABLES_PER_SHARD = 16

def exp_for(level, i):
    return {
        **BASE,
        "seeds": [{"seed": 2027000000 + level * 10000 + i * 100 + k, "scenario_id": f"L{level}-{i}-{k}"} for k in range(4)],
        "seat_permutations": [[0, 1, 2, 3], [1, 2, 3, 0]],
        "match_id_prefix": f"b2-L{level}-{i}",
        "n_resamples": 200,
    }

def parse_time(path):
    text = path.read_text()
    def g(k):
        m = re.search(r"^%s\s+([\d.]+)" % k, text, re.M)
        return float(m.group(1)) if m else None
    return g("real"), g("user"), g("sys")

results = []
for level in LEVELS:
    procs = []
    for i in range(level):
        d = _project_file(_PROJECT_ROOT, ROOT / f"L{level}-{i}")
        (d).mkdir(parents=True, exist_ok=True)
        (d / "experiment.json").write_text(json.dumps(exp_for(level, i), indent=2) + "\n")
        log = open(d / "log.txt", "w")
        procs.append((subprocess.Popen(
            ["/usr/bin/time", "-p", PY, EVAL, "matches", "--experiment", str(d / "experiment.json"), "--out", str(d / "out")],
            stdout=log, stderr=subprocess.STDOUT, cwd=str(REPO)), log, d))
    t0 = time.monotonic()
    for p, log, _ in procs:
        p.wait(); log.close()
    wall = time.monotonic() - t0
    tables = level * TABLES_PER_SHARD
    real = [parse_time(d / "log.txt")[0] for _, _, d in procs]
    user = [parse_time(d / "log.txt")[1] for _, _, d in procs]
    cpu = sum(u for u in user if u) 
    row = {"concurrency": level, "tables": tables, "wall_seconds": round(wall, 2),
           "tables_per_second": round(tables / wall, 3),
           "max_shard_real": max(r for r in real if r), "sum_user": round(cpu, 1),
           "cpu_seconds_per_table": round(cpu / tables, 3)}
    results.append(row)
    print("%2d 并发 | %3d 桌 | 墙钟 %7.2fs | %.3f 桌/s | 最慢分片 %6.2fs | CPU %.3f s/桌"
          % (level, tables, wall, row["tables_per_second"], row["max_shard_real"], row["cpu_seconds_per_table"]), flush=True)

base = results[0]["tables_per_second"]
for row in results:
    row["speedup_vs_1"] = round(row["tables_per_second"] / base, 3)
    row["efficiency"] = round(row["speedup_vs_1"] / row["concurrency"], 3)
(_project_file(_PROJECT_ROOT, ROOT / "scaling.json")).write_text(json.dumps({"tables_per_shard": TABLES_PER_SHARD, "rows": results}, indent=2) + "\n")
print()
print("%-4s %-6s %-9s %-8s %-9s" % ("并发", "加速比", "并行效率", "桌/秒", "CPU s/桌"))
for row in results:
    print("%-4d %-6.2f %-9.0f%% %-8.3f %-9.3f" % (row["concurrency"], row["speedup_vs_1"], row["efficiency"]*100, row["tables_per_second"], row["cpu_seconds_per_table"]))
