"""R10 对比路线微函数：六配置装配、冻结真实观察与路线变形验收。"""
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

import route_microfunction_checks_1 as checks  # noqa: E402
import structural_behavior_preflight as preflight  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
SOURCES = {task: _project_file(_PROJECT_ROOT, BATCH / f"generations/{task}/candidate.py") for task in ("R1", "R2")}


def main() -> None:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    if {row["task"] for row in manifest["parents"]} != set(SOURCES):
        raise ValueError("对比微函数清单漂移")
    preflight.BATCH = BATCH
    preflight.SOURCES = SOURCES
    preflight.BASES = {task: V2 for task in SOURCES}
    preflight.main()
    summary_path = _project_file(_PROJECT_ROOT, BATCH / "behavior-preflight-v2/summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["schema"] = "r10-route-microfunction-contrastive-preflight/1"
    views, corpus = preflight.load_real_views()
    invariance = []
    for task in summary["tasks"]:
        for row in task["configurations"]:
            path = _project_file(_PROJECT_ROOT, BATCH / "behavior-preflight-v2/configurations" / row["config_id"] / "candidate.py")
            result = checks.partition_check(path, views)
            invariance.append({
                "task": task["task"], "config_id": row["config_id"],
                "cases": result["cases"], "passed": result["invariant"],
            })
    if any(row["cases"] != 12 or row["passed"] != 12 for row in invariance):
        raise ValueError("对比微函数路线拆分/重排变形检查失败")
    summary["route_partition_and_order"] = {
        "current_core_real_views": corpus["unique_real_views"],
        "configurations": invariance,
        "cases": sum(row["cases"] for row in invariance),
        "passed": sum(row["passed"] for row in invariance),
    }
    summary["scope_note"] = (
        "冻结真实观察和变形输入只检验接线、退化、行为差异及等价拆分；不提供动作标签或效果。"
    )
    preflight.write_json(summary_path, summary)
    print(json.dumps({
        "status": "COMPLETE_ROUTE_MICROFUNCTION_CONTRASTIVE_PREFLIGHT_1",
        "passed_tasks": summary["passed_tasks"],
        "failed_tasks": summary["failed_tasks"],
        "configurations": summary["configurations_materialized"],
        "partition_cases": summary["route_partition_and_order"]["cases"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
