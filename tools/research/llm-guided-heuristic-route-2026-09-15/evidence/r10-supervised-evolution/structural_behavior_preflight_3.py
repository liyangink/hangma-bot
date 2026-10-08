"""R10 第三结构批次：装配十二配置并在冻结真实观察上做行为预检。"""
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


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-03-20260921')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
SOURCES = {
    task: _project_file(_PROJECT_ROOT, BATCH / f"generations/{task}/repair/normalized-v2/candidate.py")
    for task in ("C1", "C2")
}


def main() -> None:
    normalization = json.loads(
        (_project_file(_PROJECT_ROOT, BATCH / "normalization-v2-summary.json")).read_text(encoding="utf-8")
    )
    if set(normalization.get("accepted") or []) != set(SOURCES):
        raise ValueError("归一化准入集合漂移")
    preflight.BATCH = BATCH
    preflight.SOURCES = SOURCES
    preflight.BASES = {task: V2 for task in SOURCES}
    preflight.main()
    summary_path = _project_file(_PROJECT_ROOT, BATCH / "behavior-preflight-v2/summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["schema"] = "r10-structural-behavior-preflight/3"
    summary["normalization"] = "normalization-v2-summary.json"
    summary["scope_note"] = (
        "真实观察只用于零效应、运行上界和新行为存在性检查，不含第三批效果标签，不能选优。"
    )
    preflight.write_json(summary_path, summary)
    print(json.dumps({
        "status": "COMPLETE_STRUCTURAL_BEHAVIOR_PREFLIGHT_3",
        "passed_tasks": summary["passed_tasks"],
        "failed_tasks": summary["failed_tasks"],
        "configurations": summary["configurations_materialized"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
