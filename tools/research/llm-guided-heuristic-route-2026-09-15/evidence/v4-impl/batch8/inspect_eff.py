"""检查 eff 候选档案条目的统计材料与 normal_evaluations。"""

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

a = json.load(open("review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch8/archive.json"))
e = a["entries"]["6d9c1d5914509a966bf79a349142d41b2625c05eac55c28fb4b57b2ba56674e"]
print("keys:", sorted(e.keys()))
ne = e.get("normal_evaluations") or {}
print("normal_evaluations:", len(ne), sorted(ne)[:6])
sm = e.get("stats_material")
if isinstance(sm, dict):
    panels = sm.get("panels") or {}
    print("panels:", {k: (v.get("n_roots"), v.get("status")) for k, v in panels.items()})
print("overall:", json.dumps(e.get("overall"), ensure_ascii=False)[:400])
