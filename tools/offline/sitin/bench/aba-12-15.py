#!/usr/bin/env python3
"""坐隐 1.2c：12 vs 15 并发的重复配对（A/B/A），确认并发上限。

单次扫描里 10→12 的吞吐跳变看起来像噪声，不能据此下结论。
按专项复核的建议：**交错、重复**测量同一批固定工作，报告分布而非只报最好一次。
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
import json, re, shutil, subprocess, sys, time
from pathlib import Path

REPO = Path("/Users/liyang/Projects/Opensource/hangma-bot")
ROOT = _project_file(_PROJECT_ROOT, REPO / "runs/bench-sitin-1.2b2")
PY = str(_project_file(_PROJECT_ROOT, REPO / ".venv/bin/python3"))
EVAL = str(_project_file(_PROJECT_ROOT, REPO / "scripts/evaluate.py"))
DESIGN = [(12, "A"), (15, "B"), (12, "A"), (15, "B")]
TABLES_PER_PROC = 16


def parse_time(path):
    text = path.read_text()
    def g(k):
        m = re.search(r"^%s\s+([\d.]+)" % k, text, re.M)
        return float(m.group(1)) if m else 0.0
    return g("user"), g("sys")


def run_once(level, tag, seq):
    dirs = []
    for i in range(level):
        d = _project_file(_PROJECT_ROOT, ROOT / ("R%d-%s-%d" % (seq, tag, i)))
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        exp = json.loads((_project_file(_PROJECT_ROOT, ROOT / "template.json")).read_text())
        exp["match_id_prefix"] = "rep%d" % seq
        (d / "experiment.json").write_text(json.dumps(exp, indent=2) + "\n")
        dirs.append(d)
    procs = []
    for d in dirs:
        log = open(d / "log.txt", "w")
        procs.append((subprocess.Popen(
            ["/usr/bin/time", "-p", PY, EVAL, "matches",
             "--experiment", str(d / "experiment.json"), "--out", str(d / "out")],
            stdout=log, stderr=subprocess.STDOUT, cwd=str(REPO)), log, d))
    time.sleep(3.0)
    t0 = time.monotonic()
    for p, log, _ in procs:
        p.wait(); log.close()
    wall = time.monotonic() - t0
    tables = level * TABLES_PER_PROC
    cpu = sum(sum(parse_time(d / "log.txt")) for d in dirs)
    return {"level": level, "tag": tag, "seq": seq, "wall": round(wall, 2),
            "tables": tables, "tables_per_second": round(tables / wall, 3),
            "cpu_per_table": round(cpu / tables, 4)}


# 固定模板：16 桌/进程
tmpl = {
    "experiment_schema_version": 1, "kind": "matches", "clock_mode": "logical",
    "baseline_policy": {"policy_id": "weighted_heuristic_v1", "name": "weighted_heuristic_v1", "weights": {}},
    "challenger_policy": {"policy_id": "weighted_heuristic_v2", "name": "weighted_heuristic_v2", "weights": {}},
    "opponent_pool": [{"policy_id": "opp-%d" % i, "name": "weighted_heuristic", "weights": {}} for i in range(3)],
    "tournament_config": {"schema_version": 1, "max_games": 1, "rounds_per_game": 8,
        "rules": {"ruleset_version": "hangma-mvp-v10-public-counts", "base_score": 1, "you_cai_bi_kao": False},
        "timing": {"peng_timeout_sec": 1.0, "chi_timeout_sec": 1.0, "discard_timeout_sec": 3.0}},
    "seeds": [{"seed": 2029000000 + k, "scenario_id": "fixed-%d" % k} for k in range(4)],
    "seat_permutations": [[0, 1, 2, 3], [1, 2, 3, 0]],
    "initial_dealer": 0, "initial_scores": [0, 0, 0, 0],
    "match_id_prefix": "rep", "primary_metric": "table_score_delta",
    "tie_method": "strict", "n_resamples": 200, "resample_seed": 2029,
}
ROOT.mkdir(parents=True, exist_ok=True)
(_project_file(_PROJECT_ROOT, ROOT / "template.json")).write_text(json.dumps(tmpl, indent=2) + "\n")

rows = []
for seq, (level, tag) in enumerate(DESIGN, 1):
    row = run_once(level, tag, seq)
    rows.append(row)
    print("%s(%2d 进程) | 墙钟 %6.2fs | %.3f 桌/s | CPU %.4f s/桌"
          % (tag, row["level"], row["wall"], row["tables_per_second"], row["cpu_per_table"]), flush=True)

(_project_file(_PROJECT_ROOT, ROOT / "aba.json")).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
print()
for level in (12, 15):
    vals = [r["tables_per_second"] for r in rows if r["level"] == level]
    print("%2d 进程：桌/秒 %s（均值 %.3f）" % (level, vals, sum(vals) / len(vals)))
a = [r["tables_per_second"] for r in rows if r["level"] == 12]
b = [r["tables_per_second"] for r in rows if r["level"] == 15]
print("15 相对 12：%.1f%%" % ((sum(b) / len(b)) / (sum(a) / len(a)) * 100 - 100))
