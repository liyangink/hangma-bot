"""R18 P55：修复白板一摸即胡的 ValueRoute 漏检并重放失败源臂。"""

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

import argparse
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p47_integrated_parent_registration as p47  # noqa: E402
import r18_p53_guarded_successor_confirmation as p53  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.public_successor_leaf_executor import LeafProgramExecutor  # noqa: E402
from hangma_bot.policy.public_successor_search import reduce_public_successors  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v1 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V1_NAME,
    R18_INTEGRATED_POSITIVE_V1_SOURCE,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p55-white-value-route-repair-01-20260923')
P53_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p53-guarded-successor-confirmation-01-20260923')
FAILING_REQUEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p53-guarded-successor-confirmation-01-20260923/failing-request-white-capacity.json')
P53_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p53-guarded-successor-confirmation-01-20260923/result.json')
VALUE_ANALYSIS = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/hangma/value_analysis.py")
REGRESSION_TESTS = (
    _project_file(_PROJECT_ROOT, ROOT / "tests/unit/hangma/test_value_analysis.py"),
    _project_file(_PROJECT_ROOT, ROOT / "tests/unit/policy/test_public_successor_search.py"),
)
FAILED_SOURCES = (
    {"mix": "H", "root_index": 2, "focal_seat": 3, "source_id": "H:p53:r02:s3"},
    {"mix": "M", "root_index": 2, "focal_seat": 3, "source_id": "M:p53:r02:s3"},
    {"mix": "M", "root_index": 12, "focal_seat": 3, "source_id": "M:p53:r12:s3"},
)
LIMITS = ValueAnalysisLimits()


def digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def repair_identity() -> str:
    """绑定失败证据、规则修复及交叉回归测试。"""

    payload = {
        "schema": "r18-p55-white-value-route-repair/1",
        "p53_result_sha256": digest(P53_RESULT),
        "failing_request_sha256": digest(FAILING_REQUEST),
        "value_analysis_sha256": digest(VALUE_ANALYSIS),
        "regression_test_sha256": {path.name: digest(path) for path in REGRESSION_TESTS},
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def current_request(request: Any) -> Any:
    """用同一依法可见观察重新生成当前规则事实。"""

    rules = HangmaRules(
        RuleConfig(
            ruleset_version=request.rules.ruleset_version,
            base_score=1,
            you_cai_bi_kao=False,
        )
    )
    return replace(request, rules=rules.analyze(request.observation, value_limits=LIMITS))


async def replay_parent_requests() -> dict[str, Any]:
    """检查规则事实修复是否改变 R18 的 377 个冻结请求计划。"""

    policy = ActionValuePolicy(
        ActionValueScorer(R18_INTEGRATED_POSITIVE_V1_NAME, R18_INTEGRATED_POSITIVE_V1_SOURCE),
        value_limits=LIMITS,
    )
    budget = DecisionBudget(1_000_000_000.0, 1_000_000_000.0, 1_000_000_000.0)
    payload_changes = 0
    plan_changes: list[dict[str, Any]] = []
    for label, frozen in p47.current_requests():
        current = current_request(frozen)
        if current.rules != frozen.rules:
            payload_changes += 1
        old_plan = await policy.choose(frozen, budget)
        new_plan = await policy.choose(current, budget)
        if old_plan != new_plan:
            plan_changes.append(
                {
                    "label": label,
                    "old_top": old_plan.candidates[0].action_key,
                    "new_top": new_plan.candidates[0].action_key,
                }
            )
    return {
        "requests": 377,
        "rule_payload_changes": payload_changes,
        "plan_change_count": len(plan_changes),
        "plan_changes": plan_changes,
        "pass": not plan_changes,
    }


async def verify_counterexample() -> dict[str, Any]:
    """在 P53 首个冻结反例上核对胡边与 ValueRoute 容量。"""

    frozen = decision_request_from_json(json.loads(FAILING_REQUEST.read_text(encoding="utf-8")))
    current = current_request(frozen)
    rules = HangmaRules(RuleConfig(current.rules.ruleset_version, 1, False))
    successors = rules.analyze_public_self_draw_successors(current.observation)
    leaf = LeafProgramExecutor(
        p53.R17_SOURCE.read_text(encoding="utf-8"), name="r18-p55-r17-b"
    )
    reduced = reduce_public_successors(current, successors, leaf.window_scorer())
    roots = {}
    for key in ("discard:6w", "discard:9w"):
        candidate = next(item for item in current.rules.legal_candidates if item.action_key == key)
        white_routes = [
            tile.remaining_estimate
            for route in candidate.value_facts.routes
            if route.conditions.draw_kind == "normal" and route.followup_discard is None
            for tile in route.useful_tiles
            if tile.code == "白"
        ]
        root = next(item for item in reduced.roots if item.action_key == key)
        roots[key] = {
            "shanten_after": candidate.facts.shanten_after,
            "white_value_route_capacity": white_routes,
            "white_successor_hu_capacity": root.conditional_hu_capacity,
        }
    baseline = ActionValuePolicy(
        ActionValueScorer(R18_INTEGRATED_POSITIVE_V1_NAME, R18_INTEGRATED_POSITIVE_V1_SOURCE),
        value_limits=LIMITS,
    )
    budget = DecisionBudget(1_000_000_000.0, 1_000_000_000.0, 1_000_000_000.0)
    old_plan = await baseline.choose(frozen, budget)
    new_plan = await baseline.choose(current, budget)
    passed = (
        reduced.complete
        and all(row["shanten_after"] == 1 for row in roots.values())
        and all(row["white_value_route_capacity"] == [4] for row in roots.values())
        and all(row["white_successor_hu_capacity"] == 4 for row in roots.values())
        and old_plan == new_plan
    )
    return {
        "decision_id": current.decision_id,
        "reduction_complete": reduced.complete,
        "reduction_reason": reduced.reason,
        "roots": roots,
        "r18_old_top": old_plan.candidates[0].action_key,
        "r18_current_top": new_plan.candidates[0].action_key,
        "r18_full_plan_equal": old_plan == new_plan,
        "pass": passed,
    }


def run() -> None:
    """生成不可覆盖的规则修复验证包。"""

    if OUT.exists():
        raise SystemExit("P55 目录已存在；拒绝覆盖")
    p53_result = json.loads(P53_RESULT.read_text(encoding="utf-8"))
    if p53_result.get("status") != "FAIL_P53_EXECUTION_INCOMPLETE":
        raise ValueError("P53 失败前置证据漂移")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "stages")).mkdir()
    counterexample = asyncio.run(verify_counterexample())
    parent_replay = asyncio.run(replay_parent_requests())
    stage_rows = []
    for source in FAILED_SOURCES:
        row = p53.execute_stage("candidate", source)
        write_json(
            _project_file(_PROJECT_ROOT, OUT / "stages" / (str(source["source_id"]).replace(":", "-") + ".json")),
            row,
        )
        audit = row.get("request_audit") or {}
        stage_rows.append(
            {
                "source_id": source["source_id"],
                "status": row.get("stage", {}).get("status"),
                "tables": len(row.get("stage", {}).get("tables") or []),
                "request_audit_pass": audit.get("pass") is True,
                "request_failures": audit.get("failures") or [],
            }
        )
    checks = {
        "counterexample_closed": counterexample["pass"],
        "all_failed_sources_replayed": len(stage_rows) == len(FAILED_SOURCES),
        "all_stages_complete": all(row["status"] == "complete" for row in stage_rows),
        "all_six_tables_complete": sum(row["tables"] for row in stage_rows) == 6,
        "all_request_audits_pass": all(row["request_audit_pass"] for row in stage_rows),
        "p47_current_rule_plan_drift_zero": parent_replay["pass"],
    }
    passed = all(checks.values())
    result = {
        "schema": "r18-p55-white-value-route-repair-result/1",
        "status": "PASS_P55_WHITE_VALUE_ROUTE_REPAIR" if passed else "FAIL_P55_WHITE_VALUE_ROUTE_REPAIR",
        "repair_identity": repair_identity(),
        "root_cause": (
            "shanten_after==1 在四张自然牌已耗尽时仍可能由万能白板一摸成胡；"
            "旧快速路径把它错误证明为不听。"
        ),
        "fix": "仅 shanten_after>1 时跳过一次摸牌枚举；等于1时枚举白板路线。",
        "checks": checks,
        "counterexample": counterexample,
        "parent_replay": parent_replay,
        "targeted_stage_replay": stage_rows,
        "tables": 6,
        "strength_analyzed": False,
        "strength_claim": False,
        "selection_eligible": False,
        "next": "以新生产依赖身份预注册并重跑完整1024桌独立确认；P53保持失败封存。",
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    tracked = [
        Path(__file__), VALUE_ANALYSIS, *REGRESSION_TESTS, FAILING_REQUEST, P53_RESULT,
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_search.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/protected_public_successor_policy.py"),
    ]
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest.json"),
        {
            "schema": "r18-p55-white-value-route-repair-manifest/1",
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "repair_identity": repair_identity(),
            "runtime": guard.capture(source_paths=tracked),
            "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
            "platform": {
                "python": platform.python_version(),
                "implementation": platform.python_implementation(),
                "machine": platform.machine(),
                "system": platform.system(),
            },
            "model_calls": 0,
            "network_calls": 0,
            "official_platform_calls": 0,
        },
    )
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "README.json"),
        {
            "conclusion": result["status"],
            "interpretation": "该批次只验收数学修复与原失败源臂，不产生强度结论。",
            "immutable_predecessor": "P53仍为FAIL_P53_EXECUTION_INCOMPLETE。",
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
