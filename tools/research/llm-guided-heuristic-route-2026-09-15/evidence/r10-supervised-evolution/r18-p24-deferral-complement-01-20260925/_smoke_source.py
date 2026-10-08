"""单来源冒烟：核对 P24 暴露谓词在一条真实 R18 v2 自然轨迹上的漏斗。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p24_exposure as p24

source = p24.sources()[0]
started = time.time()
result = p24.execute_source(source)
print(json.dumps({"elapsed_s": round(time.time()-started,1), "status": result["status"],
                  "tables": result["tables"], "counts": result["audit"]["counts"],
                  "eligible": result["audit"]["eligible_rows_before_source_dedup"],
                  "problems": result["audit"]["problems"][:3]}, ensure_ascii=False, indent=2))
rows = result["audit"]["eligible_rows"]
if rows:
    print(json.dumps(rows[0]["features"], ensure_ascii=False)[:1500])
