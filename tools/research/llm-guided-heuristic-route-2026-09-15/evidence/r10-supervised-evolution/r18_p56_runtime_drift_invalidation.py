"""封存 P56 在执行期间发生生产依赖漂移的事实，禁止强度分析。"""

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

import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p56-guarded-successor-confirmation-01-20260923')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("P56 已有结果；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    frozen = manifest["runtime"]
    current = guard.capture(source_paths=frozen["explicit_sources"])
    changed: dict[str, dict[str, str | None]] = {}
    old_modules = frozen["production_manifest"].get("module_closure", {})
    new_modules = current["production_manifest"].get("module_closure", {})
    for name in sorted(set(old_modules) | set(new_modules)):
        if old_modules.get(name) != new_modules.get(name):
            changed[name] = {
                "frozen_sha256": old_modules.get(name),
                "current_sha256": new_modules.get(name),
            }
    checks = {
        "run_completed_1024_tables": run_summary.get("actual_tables") == 1024,
        "run_failures_empty": not run_summary.get("failures"),
        "runtime_identity_changed": current != frozen,
        "special_rules_changed": "hangma_bot.hangma.special_rules" in changed,
    }
    if not all(checks.values()):
        raise ValueError("P56 漂移封存前提不成立：" + repr(checks))
    invalidation = {
        "schema": "r18-p56-runtime-drift-invalidation/1",
        "status": "INVALID_P56_DEPENDENCY_DRIFT",
        "reason": (
            "P56 预注册后、1024桌执行结束前，官方自由赛复盘修改了"
            "special_rules 与其记录派生调用方；分析前冻结身份校验正确拒绝继续。"
        ),
        "frozen_production_digest": frozen["production_digest"],
        "current_production_digest": current["production_digest"],
        "changed_production_modules": changed,
        "checks": checks,
        "tables_executed": 1024,
        "strength_analyzed": False,
        "strength_claim": False,
        "selection_eligible": False,
        "data_policy": "保留全部阶段作执行审计；不得计算或引用强度统计，不得补签旧身份。",
        "next": "冻结自由赛规则修复后的新生产身份，使用新panel_seed重跑独立确认。",
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "invalidation.json"), invalidation)
    write_json(result_path, invalidation)
    (_project_file(_PROJECT_ROOT, OUT / "README.md")).write_text(
        "# P56 运行时依赖漂移封存\n\n"
        "结论：1024/1024 桌执行完整，但执行期间生产规则依赖发生变化。"
        "分析前身份门已拒绝继续，因此本批不产生强度、选择或发布结论。\n\n"
        "阶段文件保留用于执行审计；禁止在新源码下补签或分析。"
        "后续必须以稳定的新身份和新 `panel_seed` 重跑。\n",
        encoding="utf-8",
    )
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "invalidation-manifest.json"),
        {
            "schema": "r18-p56-runtime-drift-invalidation-manifest/1",
            "script_sha256": digest(Path(__file__)),
            "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
            "run_summary_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "run-summary.json")),
            "invalidation_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "invalidation.json")),
            "model_calls": 0,
            "network_calls": 0,
            "official_platform_calls": 0,
        },
    )
    print(json.dumps(invalidation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
