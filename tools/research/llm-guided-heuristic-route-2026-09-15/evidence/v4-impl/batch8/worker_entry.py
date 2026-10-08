"""子进程 worker：单候选统计与条目材料提取（隔离任何函数级状态污染）。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch8'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import sys
from pathlib import Path

BASE = Path("review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl")
sys.path.insert(0, 'tools/offline/sitin')
import sitin_archive as arch

name, cid = sys.argv[1], sys.argv[2]
samples = []
for mix in ("H", "M"):
    for sub in ("natural-" + mix, "natural-" + mix + "-r2"):
        d = BASE / "batch7" / "eval" / name / sub
        if not d.is_dir():
            continue
        sfx = "-r2" if sub.endswith("-r2") else ""
        for line in (d / "samples.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row["scenario"] = "normal"
            row["opponent_mix"] = mix
            if sfx:
                for key in ("root_id", "source_root_id"):
                    if row.get(key):
                        row[key] = row[key] + sfx
            samples.append(row)

stats = arch.paired_stage_statistics(samples, min_roots=1)
bck = stats["by_candidate"]
# 按行内实际 candidate_id 取（不信任外部字符串）
actual_cid = samples[0]["candidate_id"]
cstats = bck.get(actual_cid)
if cstats is None:
    print(json.dumps({"ok": False, "reason": "by_candidate missing actual cid",
                      "keys": sorted(bck)}))
    sys.exit(1)
normal = cstats.get("panels", {}).get("normal")
if normal is None:
    print(json.dumps({"ok": False, "reason": "normal block missing",
                      "panels": sorted(cstats.get("panels", {}))}))
    sys.exit(1)
nevals = {}
for mix, panel in sorted(normal["panels"].items()):
    for row in panel["root_rows"]:
        nevals[row["root_id"]] = {
            "d_point": row["d_point"], "d_low": row["d_low"], "d_high": row["d_high"],
            "unknown": row["unresolved"], "opponent_mix": mix,
            "cost": row["cost"], "role": row["role"],
        }
print(json.dumps({
    "ok": True,
    "actual_cid": actual_cid,
    "normal_evaluations": nevals,
    "overall": arch._overall_summary(cstats),
}, ensure_ascii=False))
