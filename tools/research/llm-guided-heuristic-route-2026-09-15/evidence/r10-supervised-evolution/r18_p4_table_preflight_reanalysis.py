"""修正 R18 P4 桌赛预检对 ``degraded_reasons`` 的错误判读。

``ActionValuePolicy`` 在评分成功时也把 ``action_value: ... 评分完成`` 放入
``degraded_reasons``，所以“字段非空”不是降级。唯一失败口径是生产执行审计
识别的 ``action_value_failed:``、歧义或未分类评分窗口。本文件不重跑桌赛，
只按该既有正式口径复算已经冻结的 64 张桌。
"""

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


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p4_table_preflight as preflight  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402


OUT = preflight.OUT


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """用生产执行审计口径替换错误的“非空即降级”检查。"""

    target = OUT / "result-v2.json"
    if target.exists():
        raise SystemExit("result-v2.json 已存在；拒绝覆盖")
    manifest = preflight.verify_manifest()
    original = json.loads((OUT / "result.json").read_text(encoding="utf-8"))
    run_summary = json.loads((OUT / "run-summary.json").read_text(encoding="utf-8"))
    paired = json.loads((OUT / "paired-units.json").read_text(encoding="utf-8"))[
        "rows"
    ]
    all_tables = []
    request_counts = {
        "requests": 0,
        "policy_errors": 0,
        "changed_top_actions": 0,
        "opportunity_overlay_present": 0,
        "opportunity_triggered": 0,
    }
    for source in preflight.sources():
        for arm in preflight.ARMS:
            doc = json.loads(
                preflight.stage_path(arm, source).read_text(encoding="utf-8")
            )
            all_tables.extend(doc["stage"]["tables"])
            if arm == "candidate":
                counts = (doc.get("request_audit") or {}).get("counts") or {}
                for key in request_counts:
                    request_counts[key] += int(counts.get(key, 0))
    execution = natural.execution_audit.review_tables(all_tables)
    recorded = execution["recorded_counts"]
    action_value_failure_windows = sum(
        int(recorded[key])
        for key in (
            "action_value_failed",
            "ambiguous_diagnostics",
            "unclassified_action_value",
        )
    )
    deltas = [int(row["stage_score_delta"]) for row in paired]
    checks = {
        "all_tables_complete": run_summary["actual_tables"] == preflight.PLANNED_TABLES,
        "zero_runtime_failures": execution["zero_internal_failures_verified"] is True,
        "candidate_request_errors": request_counts["policy_errors"] == 0,
        "all_candidate_requests_action_value_scored": (
            recorded["action_value_scored"] == request_counts["requests"]
        ),
        "zero_action_value_failure_windows": action_value_failure_windows == 0,
        "paired_stage_score_delta_mean_nonnegative": (
            sum(deltas) / len(deltas) >= 0
        ),
        "negative_paired_stage_units_zero": sum(value < 0 for value in deltas) == 0,
    }
    passed = all(checks.values())
    result = {
        "schema": "r18-p4-table-preflight-result/2",
        "status": "PASS_R18_P4_TABLE_PREFLIGHT" if passed else "FAIL_R18_P4_TABLE_PREFLIGHT",
        "supersedes_result_sha256": digest(OUT / "result.json"),
        "supersession_reason": (
            "v1把所有非空degraded_reasons误判为降级；ActionValuePolicy成功路径按合同也写入"
            "action_value: <scorer> 评分完成。v2改用sitin_execution_audit对"
            "action_value_failed/ambiguous/unclassified的正式分类。"
        ),
        "tables_reexecuted": 0,
        "manifest_sha256": digest(OUT / "manifest.json"),
        "candidate_sha256": manifest["candidate_sha256"],
        "tables": preflight.PLANNED_TABLES,
        "source_units": preflight.SOURCE_UNITS,
        "overall": original["overall"],
        "by_mix": original["by_mix"],
        "request_counts": request_counts,
        "execution_review": execution,
        "action_value_failure_windows": action_value_failure_windows,
        "gate_checks": checks,
        "measurement_defect": {
            "affected_field": "v1.request_audit_counts.degraded_plans",
            "observed": original["request_audit_counts"]["degraded_plans"],
            "correct_interpretation": "评分成功诊断条目数，不是失败/保底数",
            "authoritative_scored": recorded["action_value_scored"],
            "authoritative_failed": recorded["action_value_failed"],
        },
        "natural_trigger_interpretation": original["natural_trigger_interpretation"],
        "strength_claim": False,
        "confirmation_eligible": passed,
        "release_eligible": False,
        "next": (
            "扩展多手牌P4开发/新隐藏题；P4作为Pareto机会精英进入下一代"
            if passed else
            "停止晋级并检查正式评分执行分类或候选运行失败"
        ),
    }
    preflight.write_json(target, result)
    preflight.verify_manifest()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
