"""R10 第二结构批次：对归一化后的唯一修复候选重跑真实观察行为预检。"""
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


SOURCE_BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921')
RUN_ROOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/repair-preflight')
S3_PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/behavior-preflight-v2/configurations/s3-cfg-02/candidate.py')
TASK_MAP = {"S2": "T2", "S4": "T4"}


def main() -> None:
    """仅测已通过机械归一化的T2/T4；T1/T3维持关闭。"""
    normalization = json.loads(
        (_project_file(_PROJECT_ROOT, SOURCE_BATCH / "repair-normalization-summary.json")).read_text(encoding="utf-8")
    )
    accepted = set(normalization["accepted"])
    if accepted != {"T2", "T4"}:
        raise ValueError(f"归一化准入集合漂移：{sorted(accepted)}")
    preflight.BATCH = RUN_ROOT
    preflight.SOURCES = {
        old: _project_file(_PROJECT_ROOT, SOURCE_BATCH / f"generations/{new}/repair/normalized/candidate.py")
        for old, new in TASK_MAP.items()
    }
    preflight.BASES = {old: S3_PARENT for old in TASK_MAP}

    original_write = preflight.write_json

    def write_without_first_batch_closure(path: Path, value: object) -> None:
        if path == _project_file(_PROJECT_ROOT, RUN_ROOT / "behavior-preflight/closure-v1.json"):
            return
        original_write(path, value)

    preflight.write_json = write_without_first_batch_closure
    preflight.main()
    out = _project_file(_PROJECT_ROOT, RUN_ROOT / "behavior-preflight-v2")
    summary_path = out / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for row in summary["tasks"]:
        row["internal_family_id"] = row["task"]
        row["task"] = TASK_MAP[row["task"]]
    summary["passed_tasks"] = [TASK_MAP[item] for item in summary["passed_tasks"]]
    summary["failed_tasks"] = [TASK_MAP[item] for item in summary["failed_tasks"]]
    summary["schema"] = "r10-structural-repair-behavior-preflight/2"
    summary["task_id_mapping"] = TASK_MAP
    summary["closed_before_preflight"] = ["T1", "T3"]
    original_write(summary_path, summary)

    manifest_path = out / "configuration-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["configurations"]:
        row["internal_family_id"] = row["task"]
        row["task"] = TASK_MAP[row["task"]]
    manifest["schema"] = "r10-structural-repair-configuration-manifest/2"
    manifest["task_id_mapping"] = TASK_MAP
    original_write(manifest_path, manifest)

    original_write(_project_file(_PROJECT_ROOT, SOURCE_BATCH / "repair-behavior-preflight-summary.json"), {
        "schema": "r10-structural-repair-behavior-preflight-summary/1",
        "source": str(summary_path.relative_to(SOURCE_BATCH)),
        "passed_tasks": summary["passed_tasks"],
        "failed_tasks": summary["failed_tasks"],
        "closed_before_preflight": ["T1", "T3"],
        "configurations_materialized": summary["configurations_materialized"],
        "effect_tables": 0,
    })
    print(json.dumps({
        "status": "COMPLETE_STRUCTURAL_REPAIR_BEHAVIOR_PREFLIGHT_2",
        "passed_tasks": summary["passed_tasks"],
        "failed_tasks": summary["failed_tasks"],
        "closed_before_preflight": ["T1", "T3"],
        "configurations": summary["configurations_materialized"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
