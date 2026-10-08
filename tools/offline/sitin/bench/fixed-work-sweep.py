#!/usr/bin/env python3
"""坐隐 1.2b：固定工作量的并发扫描（复核并发上限）。

方法学修正（吸取专项复核 1.2 REVIEW.md 的意见）：
  1. **每个并发级别跑完全相同的任务**——同一个 experiment 文件重复启动 N 次，
     种子/牌山/换座/两臂全部固定，因此"每桌实际工作量"在级别之间可比；
     （原 scaling.py 每个级别换种子，不同牌山工作量不同，是混淆因素。）
  2. 并发进程**准备后统一放行**，计时只覆盖桌赛执行；
  3. 同时记录 wall / user / sys，**CPU 秒 = user + sys**（原稿只累计 user）。

目的：回答"本机建议并发上限"与"每桌 CPU 成本随并发的变化"。
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
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path

REPO = Path("/Users/liyang/Projects/Opensource/hangma-bot")
ROOT = _project_file(_PROJECT_ROOT, REPO / "runs/bench-sitin-1.2b2")
PY = str(_project_file(_PROJECT_ROOT, REPO / ".venv/bin/python3"))
EVAL = str(_project_file(_PROJECT_ROOT, REPO / "scripts/evaluate.py"))
LEVELS = [1, 4, 6, 8, 10, 12, 15]

# 固定任务：4 根 × 2 换座 × 2 臂 = 16 桌/进程
TASK = {
    "experiment_schema_version": 1, "kind": "matches", "clock_mode": "logical",
    "baseline_policy": {"policy_id": "weighted_heuristic_v1", "name": "weighted_heuristic_v1", "weights": {}},
    "challenger_policy": {"policy_id": "weighted_heuristic_v2", "name": "weighted_heuristic_v2", "weights": {}},
    "opponent_pool": [
        {"policy_id": "opp-0", "name": "weighted_heuristic", "weights": {}},
        {"policy_id": "opp-1", "name": "weighted_heuristic", "weights": {}},
        {"policy_id": "opp-2", "name": "weighted_heuristic", "weights": {}},
    ],
    "tournament_config": {"schema_version": 1, "max_games": 1, "rounds_per_game": 8,
        "rules": {"ruleset_version": "hangma-mvp-v10-public-counts", "base_score": 1, "you_cai_bi_kao": False},
        "timing": {"peng_timeout_sec": 1.0, "chi_timeout_sec": 1.0, "discard_timeout_sec": 3.0}},
    "seeds": [{"seed": 2029000000 + k, "scenario_id": "fixed-%d" % k} for k in range(4)],
    "seat_permutations": [[0, 1, 2, 3], [1, 2, 3, 0]],
    "initial_dealer": 0, "initial_scores": [0, 0, 0, 0],
    "match_id_prefix": "fixedtask", "primary_metric": "table_score_delta",
    "tie_method": "strict", "n_resamples": 200, "resample_seed": 2029,
}
TABLES_PER_PROC = 16


def parse_time(path):
    text = path.read_text()
    def g(k):
        m = re.search(r"^%s\s+([\d.]+)" % k, text, re.M)
        return float(m.group(1)) if m else 0.0
    return g("real"), g("user"), g("sys")


results = []
for level in LEVELS:
    dirs = []
    for i in range(level):
        d = _project_file(_PROJECT_ROOT, ROOT / ("L%d-%d" % (level, i)))
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        exp = dict(TASK)
        exp["match_id_prefix"] = "fixedtask-L%d" % level
        (d / "experiment.json").write_text(json.dumps(exp, indent=2) + "\n")
        dirs.append(d)
    procs = []
    for d in dirs:
        log = open(d / "log.txt", "w")
        procs.append((subprocess.Popen(
            ["/usr/bin/time", "-p", PY, EVAL, "matches",
             "--experiment", str(d / "experiment.json"), "--out", str(d / "out")],
            stdout=log, stderr=subprocess.STDOUT, cwd=str(REPO)), log, d))
    # 统一放行：所有进程已启动（准备阶段：解释器与模块加载）
    time.sleep(3.0)
    t0 = time.monotonic()
    for p, log, _ in procs:
        p.wait(); log.close()
    wall = time.monotonic() - t0
    tables = level * TABLES_PER_PROC
    parsed = [parse_time(d / "log.txt") for d in dirs]
    cpu = sum(u + s for _, u, s in parsed)
    row = {
        "concurrency": level, "tables": tables,
        "wall_seconds_after_release": round(wall, 2),
        "tables_per_second": round(tables / wall, 3),
        "cpu_seconds_total": round(cpu, 1),
        "cpu_seconds_per_table": round(cpu / tables, 4),
        "max_process_wall": round(max(r for r, _, _ in parsed), 2),
        "cpu_per_wall": round(cpu / wall, 3),
    }
    results.append(row)
    print("%2d 进程 | %3d 桌 | 放行后 %7.2fs | %.3f 桌/s | CPU %.4f s/桌 | 平均占用 %.2f 核"
          % (level, tables, wall, row["tables_per_second"],
             row["cpu_seconds_per_table"], row["cpu_per_wall"]), flush=True)

base = results[0]
for row in results:
    row["throughput_vs_1"] = round(row["tables_per_second"] / base["tables_per_second"], 3)
    row["cpu_cost_vs_1"] = round(row["cpu_seconds_per_table"] / base["cpu_seconds_per_table"], 3)
(_project_file(_PROJECT_ROOT, ROOT / "fixed-work-sweep.json")).write_text(
    json.dumps({"tables_per_process": TABLES_PER_PROC, "rows": results}, indent=2) + "\n", encoding="utf-8")
print()
print("%-4s %-9s %-9s %-11s %-9s" % ("并发", "吞吐倍数", "单桌CPU倍", "桌/秒", "占用核数"))
for row in results:
    print("%-4d %-9.2f %-9.2f %-11.3f %-9.2f" % (
        row["concurrency"], row["throughput_vs_1"], row["cpu_cost_vs_1"],
        row["tables_per_second"], row["cpu_per_wall"]))
