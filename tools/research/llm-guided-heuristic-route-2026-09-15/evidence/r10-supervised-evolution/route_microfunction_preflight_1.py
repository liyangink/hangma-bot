"""R10 条件路线价值微函数第一批：六配置装配与冻结真实观察行为预检。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

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


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE, _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run")):
    sys.path.insert(0, str(path))

import structural_behavior_preflight as preflight  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-01-20260921')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
SOURCES = {task: _project_file(_PROJECT_ROOT, BATCH / f"generations/{task}/candidate.py") for task in ("M1", "M2")}


def main() -> None:
    ingest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8"))
    if set(ingest.get("accepted") or []) != set(SOURCES):
        raise ValueError("微函数生成端准入集合漂移")
    preflight.BATCH = BATCH
    preflight.SOURCES = SOURCES
    preflight.BASES = {task: V2 for task in SOURCES}
    preflight.main()
    summary_path = _project_file(_PROJECT_ROOT, BATCH / "behavior-preflight-v2/summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["schema"] = "r10-route-microfunction-behavior-preflight/1"
    summary["scope_note"] = (
        "冻结真实观察只用于零效应、执行上界和行为差异存在性；它不含本批新效果标签，不能选优。"
    )
    preflight.write_json(summary_path, summary)
    print(json.dumps({
        "status": "COMPLETE_ROUTE_MICROFUNCTION_PREFLIGHT_1",
        "passed_tasks": summary["passed_tasks"],
        "failed_tasks": summary["failed_tasks"],
        "configurations": summary["configurations_materialized"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
