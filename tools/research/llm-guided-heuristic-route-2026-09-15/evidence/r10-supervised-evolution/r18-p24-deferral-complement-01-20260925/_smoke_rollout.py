"""单配对冒烟：核对双臂动作、分叉点与算术，不写入正式产物。"""

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
import r18_p24_deferral_complement_teacher as t

targets = t.targets()
target = targets[0]
started = time.time()
row = t.execute_rollout(target, 1, "r18-p24-deferral-complement-future-wall-01")
print("elapsed_s", round(time.time()-started, 1))
print(json.dumps({k: row[k] for k in ("target_id","actual_actions","force_count","divergence",
                  "focal_current_round_settlement_delta","focal_current_table_score",
                  "decisions_after_cut","mechanical_ok")}, ensure_ascii=False, indent=2))
print("ref", json.dumps(row["reference"], ensure_ascii=False))
print("int", json.dumps(row["intervention"], ensure_ascii=False))
print("widths", json.dumps(row["focal_widths"], ensure_ascii=False))
t.validate_rollout_row(row, target, 1, "r18-p24-deferral-complement-future-wall-01")
print("VALIDATE_OK")
