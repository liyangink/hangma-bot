"""R10 第二结构批次：复用首批测量实现，在既有真实观察上做行为预检。"""
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


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921')
S3_PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/behavior-preflight-v2/configurations/s3-cfg-02/candidate.py')
V2_PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
TASK_MAP = {"S1": "T1", "S2": "T2", "S3": "T3", "S4": "T4"}


def main() -> None:
    """绑定第二批源码/父代，跳过首批专属的测量缺陷结案文件。"""
    preflight.BATCH = BATCH
    preflight.SOURCES = {
        old: _project_file(_PROJECT_ROOT, BATCH / f"generations/{new}/candidate.py")
        for old, new in TASK_MAP.items()
    }
    preflight.BASES = {
        "S1": S3_PARENT,
        "S2": S3_PARENT,
        "S3": V2_PARENT,
        "S4": S3_PARENT,
    }
    original_write = preflight.write_json

    def write_without_first_batch_closure(path: Path, value: object) -> None:
        if path == _project_file(_PROJECT_ROOT, BATCH / "behavior-preflight/closure-v1.json"):
            return
        original_write(path, value)

    preflight.write_json = write_without_first_batch_closure
    preflight.main()
    out = _project_file(_PROJECT_ROOT, BATCH / "behavior-preflight-v2")
    summary_path = out / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for row in summary["tasks"]:
        row["internal_family_id"] = row["task"]
        row["task"] = TASK_MAP[row["task"]]
    summary["passed_tasks"] = [TASK_MAP[item] for item in summary["passed_tasks"]]
    summary["failed_tasks"] = [TASK_MAP[item] for item in summary["failed_tasks"]]
    summary["schema"] = "r10-structural-behavior-preflight/2"
    summary["task_id_mapping"] = TASK_MAP
    original_write(summary_path, summary)
    manifest_path = out / "configuration-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["configurations"]:
        row["internal_family_id"] = row["task"]
        row["task"] = TASK_MAP[row["task"]]
    manifest["schema"] = "r10-structural-configuration-manifest/2"
    manifest["task_id_mapping"] = TASK_MAP
    original_write(manifest_path, manifest)
    print(json.dumps({
        "status": "COMPLETE_STRUCTURAL_BEHAVIOR_PREFLIGHT_2",
        "passed_tasks": summary["passed_tasks"],
        "failed_tasks": summary["failed_tasks"],
        "configurations": summary["configurations_materialized"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
