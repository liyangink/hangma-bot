"""R18 P60：严格胡牌机会接管算子的零桌静态预检。"""

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
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p47_integrated_parent_registration as p47  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.protected_public_successor_policy import (  # noqa: E402
    ProtectedPublicSuccessorSearchPolicy,
    protected_trace_state,
)
from hangma_bot.policy.public_successor_leaf_executor import (  # noqa: E402
    LeafProgramExecutor,
)
from hangma_bot.policy.public_successor_search import (  # noqa: E402
    order_discard_keys_by_confirmed_hu_takeover,
    reduce_public_successors,
)
from hangma_bot.policy.r18_integrated_positive_v1 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V1_SHA256,
    R18_INTEGRATED_POSITIVE_V1_SOURCE,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p60-confirmed-hu-takeover-preflight-01-20260923')
P47_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p47-integrated-parent-registration-01-20260922/result.json')
P58_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p58-guarded-successor-confirmation-01-20260923/result.json')
R17_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-seed-author-b-sol-repair-01-20260921/candidate.py')
R17_SOURCE_SHA256 = "fb9764faa2a01ded3f8cea94eeee27d59929f014f1dcc0ffbd56380e5b1384a2"
R17_CANDIDATE_IDENTITY = (
    "73c2833da12f2844f69559d4ad6202c44fc4a1adc1b60e0b8b140c82590b4c37"
)
SPECIAL_TRACE_KEYS = (
    "r18_opportunity_overlay",
    "r18_gang_dominance_overlay",
    "r18_seven_pairs_value_overlay",
    "two_wealth_piao_keeps_baotou_cf",
)
EXPECTED_REQUESTS = 377
MAX_CHANGED_ORDINARY_RATE = 0.20
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


def frozen_inputs() -> dict[str, str]:
    """返回足以复算本预检的输入摘要。"""

    paths = {
        "script": Path(__file__),
        "p47_result": P47_RESULT,
        "p58_result": P58_RESULT,
        "r17_source": R17_SOURCE,
        "integrated_parent": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v1.py"),
        "protected_policy": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/protected_public_successor_policy.py"),
        "successor_policy": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_policy.py"),
        "successor_search": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_search.py"),
        "leaf_executor": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_leaf_executor.py"),
        "value_analysis": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/hangma/value_analysis.py"),
    }
    return {name: digest(path) for name, path in paths.items()}


async def evaluate() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """经正式策略接缝复算冻结请求，并独立核对接管数学。"""

    requests = p47.current_requests()
    if len(requests) != EXPECTED_REQUESTS:
        raise ValueError("冻结请求数漂移")
    baseline = ActionValuePolicy(
        ActionValueScorer("r18-p60-parent", R18_INTEGRATED_POSITIVE_V1_SOURCE),
        value_limits=LIMITS,
    )
    leaf_source = R17_SOURCE.read_text(encoding="utf-8")
    leaf = LeafProgramExecutor(leaf_source, name="r18-p60-r17-b-audit")
    rules_cache: dict[str, HangmaRules] = {}
    candidate_cache: dict[str, ProtectedPublicSuccessorSearchPolicy] = {}
    budget = DecisionBudget(10.0, 20.0, 30.0)
    counts: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    latencies: list[float] = []
    max_leaf_evaluations = 0
    max_candidate_operations = 0
    for index, (label, request) in enumerate(requests, 1):
        counts["requests"] += 1
        base_plan = await baseline.choose(request, budget)
        if any("action_value_failed" in reason for reason in base_plan.degraded_reasons):
            counts["action_value_failures"] += 1
            failures.append({"label": label, "reason": "parent_action_value_failed"})
            continue
        version = request.rules.ruleset_version
        rules = rules_cache.setdefault(version, HangmaRules(RuleConfig(version, 1, False)))
        candidate = candidate_cache.get(version)
        if candidate is None:
            candidate = ProtectedPublicSuccessorSearchPolicy(
                rules.analyze_public_self_draw_successors,
                LeafProgramExecutor(leaf_source, name="r18-p60-r17-b-policy"),
                candidate_identity=R17_CANDIDATE_IDENTITY,
                baseline=baseline,
                protected_trace_keys=SPECIAL_TRACE_KEYS,
                monotonic=lambda: 0.0,
                orderer=order_discard_keys_by_confirmed_hu_takeover,
            )
            candidate_cache[version] = candidate
        started = time.perf_counter_ns()
        actual_plan = await candidate.choose(request, budget)
        latencies.append((time.perf_counter_ns() - started) / 1_000_000.0)
        base_all = tuple(item.action_key for item in base_plan.candidates)
        actual_all = tuple(item.action_key for item in actual_plan.candidates)
        if set(base_all) != set(actual_all):
            counts["candidate_key_set_failures"] += 1
            failures.append({"label": label, "reason": "candidate_key_set_mismatch"})
        protected, protected_keys = protected_trace_state(base_plan, SPECIAL_TRACE_KEYS)
        if protected:
            counts["protected_plans"] += 1
            for key in protected_keys:
                counts["protected:" + key] += 1
            if actual_plan == base_plan:
                counts["protected_exact_plans"] += 1
            else:
                failures.append({"label": label, "reason": "protected_plan_changed"})
            continue
        if request.observation.phase != "draw":
            counts["response_plans"] += 1
            if actual_plan == base_plan:
                counts["response_exact_plans"] += 1
            else:
                failures.append({"label": label, "reason": "response_plan_changed"})
            continue
        baseline_keys = tuple(
            item.action_key
            for item in base_plan.candidates
            if item.action_key.startswith("discard:")
        )
        if len(baseline_keys) < 2:
            counts["draw_not_applicable"] += 1
            if actual_plan != base_plan:
                failures.append({"label": label, "reason": "inapplicable_draw_changed"})
            continue
        counts["eligible_ordinary_draws"] += 1
        scorer = leaf.window_scorer()
        reduction = reduce_public_successors(
            request,
            rules.analyze_public_self_draw_successors(request.observation),
            scorer,
        )
        max_leaf_evaluations = max(
            max_leaf_evaluations,
            sum(item.leaf_evaluations for item in reduction.roots),
        )
        max_candidate_operations = max(max_candidate_operations, scorer.operation_count)
        if not reduction.complete:
            failures.append({"label": label, "reason": reduction.reason})
            continue
        counts["complete_ordinary_draws"] += 1
        ordered = order_discard_keys_by_confirmed_hu_takeover(reduction, baseline_keys)
        actual_discards = tuple(
            item.action_key
            for item in actual_plan.candidates
            if item.action_key.startswith("discard:")
        )
        if actual_discards != ordered:
            counts["ordinary_order_mismatches"] += 1
            failures.append({"label": label, "reason": "policy_order_mismatch"})
            continue
        if ordered == baseline_keys:
            if actual_plan != base_plan:
                failures.append({"label": label, "reason": "no_trigger_plan_changed"})
            continue
        counts["changed_ordinary_draws"] += 1
        selected = next(item for item in reduction.roots if item.action_key == ordered[0])
        old_top = next(item for item in reduction.roots if item.action_key == baseline_keys[0])
        remaining_expected = tuple(key for key in baseline_keys if key != ordered[0])
        conditions = {
            "hu_capacity_strict": selected.conditional_hu_capacity
            > old_top.conditional_hu_capacity,
            "hu_net_support_strict": selected.conditional_hu_net_support
            > old_top.conditional_hu_net_support,
            "lower_nondecreasing": selected.lower_support_score
            >= old_top.lower_support_score,
            "upper_nondecreasing": selected.upper_support_score
            >= old_top.upper_support_score,
            "remaining_order_exact": ordered[1:] == remaining_expected,
        }
        if not all(conditions.values()):
            failures.append({"label": label, "reason": "takeover_invariant_failed"})
        changes.append(
            {
                "label": label,
                "top_before": baseline_keys[0],
                "top_after": ordered[0],
                "hu_capacity_before": old_top.conditional_hu_capacity,
                "hu_capacity_after": selected.conditional_hu_capacity,
                "hu_net_support_before": old_top.conditional_hu_net_support,
                "hu_net_support_after": selected.conditional_hu_net_support,
                "lower_before": old_top.lower_support_score,
                "lower_after": selected.lower_support_score,
                "upper_before": old_top.upper_support_score,
                "upper_after": selected.upper_support_score,
                "conditions": conditions,
            }
        )
        if index % 50 == 0:
            print("P60 progress {0}/{1}".format(index, len(requests)), flush=True)
    eligible = counts["eligible_ordinary_draws"]
    changed_rate = counts["changed_ordinary_draws"] / eligible if eligible else 0.0
    summary = {
        "counts": dict(counts),
        "changed_ordinary_rate": changed_rate,
        "latency_ms": {
            "mean": sum(latencies) / len(latencies),
            "max": max(latencies),
        },
        "workload": {
            "max_leaf_evaluations": max_leaf_evaluations,
            "max_candidate_operations": max_candidate_operations,
        },
        "failures": failures,
    }
    return changes, summary


def run() -> None:
    """冻结输入、执行预检并给出是否可进入开发桌赛的裁定。"""

    if OUT.exists():
        raise SystemExit("P60 目录已存在；拒绝覆盖")
    p47_result = json.loads(P47_RESULT.read_text(encoding="utf-8"))
    p58_result = json.loads(P58_RESULT.read_text(encoding="utf-8"))
    prerequisite_checks = {
        "p47_is_active_parent": (
            p47_result.get("status") == "PASS_P47_INTEGRATED_PARENT_REGISTRATION"
            and p47_result.get("active_research_parent") is True
            and p47_result.get("candidate_sha256") == R18_INTEGRATED_POSITIVE_V1_SHA256
        ),
        "p58_broad_reorder_rejected": (
            p58_result.get("status") == "FAIL_P58_GUARDED_SUCCESSOR_CONFIRMATION"
            and p58_result.get("selection_eligible") is False
        ),
        "r17_source_exact": digest(R17_SOURCE) == R17_SOURCE_SHA256,
    }
    if not all(prerequisite_checks.values()):
        raise ValueError("P60 前置证据不成立：" + repr(prerequisite_checks))
    OUT.mkdir(parents=True)
    inputs = frozen_inputs()
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
        {
            "schema": "r18-p60-confirmed-hu-takeover-authorization/1",
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "purpose": "只验证严格胡牌机会接管范围、数学不变量和接缝；不主张强度",
            "parent_sha256": R18_INTEGRATED_POSITIVE_V1_SHA256,
            "leaf_candidate_identity": R17_CANDIDATE_IDENTITY,
            "expected_requests": EXPECTED_REQUESTS,
            "maximum_changed_ordinary_rate": MAX_CHANGED_ORDINARY_RATE,
            "budgets": {"tables_full": 0, "model_calls": 0, "network_calls": 0},
            "frozen_inputs": inputs,
        },
    )
    changes, summary = asyncio.run(evaluate())
    counts = Counter(summary["counts"])
    checks = {
        "prerequisites_pass": all(prerequisite_checks.values()),
        "request_count_exact": counts["requests"] == EXPECTED_REQUESTS,
        "action_value_failures_zero": counts["action_value_failures"] == 0,
        "candidate_key_set_failures_zero": counts["candidate_key_set_failures"] == 0,
        "all_protected_plans_exact": counts["protected_plans"]
        == counts["protected_exact_plans"],
        "all_response_plans_exact": counts["response_plans"]
        == counts["response_exact_plans"],
        "all_ordinary_reductions_complete": counts["eligible_ordinary_draws"]
        == counts["complete_ordinary_draws"],
        "ordinary_order_mismatches_zero": counts["ordinary_order_mismatches"] == 0,
        "strict_takeover_nonempty": counts["changed_ordinary_draws"] > 0,
        "strict_takeover_rate_bounded": 0.0
        < summary["changed_ordinary_rate"]
        <= MAX_CHANGED_ORDINARY_RATE,
        "all_takeover_invariants_hold": all(
            all(row["conditions"].values()) for row in changes
        ),
        "failures_empty": not summary["failures"],
    }
    passed = all(checks.values())
    result = {
        "schema": "r18-p60-confirmed-hu-takeover-preflight-result/1",
        "status": (
            "PASS_P60_CONFIRMED_HU_TAKEOVER_PREFLIGHT"
            if passed
            else "FAIL_P60_CONFIRMED_HU_TAKEOVER_PREFLIGHT"
        ),
        "prerequisite_checks": prerequisite_checks,
        "checks": checks,
        "summary": summary,
        "tables_run": 0,
        "model_calls": 0,
        "network_calls": 0,
        "strength_claim": False,
        "selection_eligible": False,
        "release_eligible": False,
        "next": (
            "冻结组合并在与P58隔离的新来源运行256桌开发筛选"
            if passed
            else "停止桌赛；按触发密度或不变量失败修正接管定义"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "changes.json"), {"schema": "r18-p60-takeover-changes/1", "rows": changes})
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest.json"),
        {
            "schema": "r18-p60-confirmed-hu-takeover-manifest/1",
            "authorization_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "authorization.json")),
            "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
            "changes_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "changes.json")),
            "frozen_inputs": inputs,
            "tables_run": 0,
            "model_calls": 0,
            "network_calls": 0,
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    globals()[parser.parse_args().operation]()
