"""R18 P52：审计 P47 专项父代与 R17-B 普通弃牌搜索的受保护组合。"""

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
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p47_integrated_parent_registration as p47  # noqa: E402
from hangma_bot.bootstrap import build_research_policy  # noqa: E402
from hangma_bot.hangma import HangmaRules  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget, DecisionPlan  # noqa: E402
from hangma_bot.policy.public_successor_leaf_executor import (  # noqa: E402
    LeafProgramExecutor,
)
from hangma_bot.policy.public_successor_policy import (  # noqa: E402
    PublicSuccessorSearchPolicy,
)
from hangma_bot.policy.r18_integrated_positive_v1 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V1_SHA256,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p52-guarded-successor-composition-01-20260923')
R17_SOURCE = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-seed-author-b-sol-repair-01-20260921/candidate.py')
)
R17_AUTHOR = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-seed-author-b-sol-repair-01-20260921/author-record.json')
)
R17_REPRODUCTION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-generation1-reproduction-01-20260922/result.json')
P47_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p47-integrated-parent-registration-01-20260922/result.json')
P47_PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p47-integrated-parent-registration-01-20260922/active-parent.json')
P51_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p51-capability-inheritance-gate-01-20260922/result.json')
R17_SOURCE_SHA256 = "fb9764faa2a01ded3f8cea94eeee27d59929f014f1dcc0ffbd56380e5b1384a2"
R17_CANDIDATE_IDENTITY = (
    "73c2833da12f2844f69559d4ad6202c44fc4a1adc1b60e0b8b140c82590b4c37"
)
EXPECTED_REQUESTS = 377
EXPECTED_SPECIAL_PLANS = 87
SPECIAL_TRACE_KEYS = (
    "r18_opportunity_overlay",
    "r18_gang_dominance_overlay",
    "r18_seven_pairs_value_overlay",
    "two_wealth_piao_keeps_baotou_cf",
)


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


def triggered_specials(plan: DecisionPlan) -> tuple[str, ...]:
    """读取 P47 有界评分解释，返回本窗口实际触发的累计专项覆盖。"""

    found: set[str] = set()
    for candidate in plan.candidates:
        outer = candidate.score_trace
        if not isinstance(outer, Mapping):
            continue
        detail = outer.get("detail")
        if not isinstance(detail, Mapping):
            continue
        for key in SPECIAL_TRACE_KEYS:
            value = detail.get(key)
            if isinstance(value, Mapping) and value.get("triggered") is True:
                found.add(key)
    return tuple(key for key in SPECIAL_TRACE_KEYS if key in found)


class _FixedPlanPolicy:
    """把已完成的 P47 计划交给既有 R17 包装器，避免重复评分。"""

    def __init__(self, plan: DecisionPlan) -> None:
        self._plan = plan

    async def choose(self, request, budget) -> DecisionPlan:
        return self._plan


class _GuardedComposition:
    """专项窗口保持 P47；仅普通自摸弃牌窗口运行冻结 R17-B 归约。"""

    def __init__(self, baseline, provider, executor: LeafProgramExecutor) -> None:
        self._baseline = baseline
        self._provider = provider
        self._executor = executor

    async def choose(self, request, budget) -> tuple[DecisionPlan, tuple[str, ...]]:
        baseline = await self._baseline.choose(request, budget)
        specials = triggered_specials(baseline)
        if specials:
            return baseline, specials
        delegate = PublicSuccessorSearchPolicy(
            self._provider,
            self._executor,
            candidate_identity=R17_CANDIDATE_IDENTITY,
            baseline=_FixedPlanPolicy(baseline),
            monotonic=time.monotonic,
        )
        return await delegate.choose(request, budget), specials


def frozen_inputs() -> dict[str, str]:
    """返回会影响本审计结论的冻结输入。"""

    paths = {
        "script": Path(__file__),
        "r17_source": R17_SOURCE,
        "r17_author": R17_AUTHOR,
        "r17_reproduction": R17_REPRODUCTION,
        "p47_result": P47_RESULT,
        "p47_parent": P47_PARENT,
        "p51_result": P51_RESULT,
        "public_successor_policy": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_policy.py"),
        "public_successor_search": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_search.py"),
        "leaf_executor": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_leaf_executor.py"),
        "r18_candidate": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v1.py"),
    }
    return {name: digest(path) for name, path in paths.items()}


def freeze() -> None:
    """先冻结零桌组合审计的输入、边界与停止条件。"""

    if OUT.exists():
        raise SystemExit("P52 目录已存在；拒绝覆盖")
    if digest(R17_SOURCE) != R17_SOURCE_SHA256:
        raise ValueError("R17-B 源码摘要漂移")
    p47_result = json.loads(P47_RESULT.read_text(encoding="utf-8"))
    p51_result = json.loads(P51_RESULT.read_text(encoding="utf-8"))
    reproduction = json.loads(R17_REPRODUCTION.read_text(encoding="utf-8"))
    checks = {
        "p47_passed": p47_result.get("status")
        == "PASS_P47_INTEGRATED_PARENT_REGISTRATION",
        "p47_identity_exact": p47_result.get("candidate_sha256")
        == R18_INTEGRATED_POSITIVE_V1_SHA256,
        "p51_passed": p51_result.get("status") == "PASS_P51_INHERITANCE_GATE",
        "r17_b_selected": reproduction.get("selected_candidate", {}).get(
            "candidate_identity"
        )
        == R17_CANDIDATE_IDENTITY,
        "r17_b_confirmation_eligible": reproduction.get("confirmation_eligible") is True,
    }
    if not all(checks.values()):
        raise ValueError("P52 前置证据不成立：" + repr(checks))
    OUT.mkdir(parents=True)
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
        {
            "schema": "r18-p52-guarded-successor-composition-authorization/1",
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "purpose": "只验证组合可行性；不运行完整桌、不调用模型、不取得发布资格",
            "p47_candidate_sha256": R18_INTEGRATED_POSITIVE_V1_SHA256,
            "r17_candidate_identity": R17_CANDIDATE_IDENTITY,
            "r17_source_sha256": R17_SOURCE_SHA256,
            "expected_requests": EXPECTED_REQUESTS,
            "expected_special_plans": EXPECTED_SPECIAL_PLANS,
            "guard": {
                "rule": "任一候选评分解释触发冻结专项覆盖时，完整返回P47计划",
                "special_trace_keys": SPECIAL_TRACE_KEYS,
                "ordinary_scope": "仅无专项触发的draw弃牌窗口进入既有R17包装器",
            },
            "pass_conditions": {
                "all_special_plans_exact": True,
                "all_response_plans_exact": True,
                "candidate_key_sets_preserved": True,
                "action_value_failures": 0,
                "ordinary_changed_plans_min": 1,
            },
            "budgets": {"tables_full": 0, "model_calls": 0},
            "release_eligible": False,
            "frozen_inputs": frozen_inputs(),
        },
    )
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest-pre.json"),
        {
            "schema": "r18-p52-guarded-successor-composition-manifest-pre/1",
            "authorization_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "authorization.json")),
            "frozen_inputs": frozen_inputs(),
            "platform": {
                "python": platform.python_version(),
                "implementation": platform.python_implementation(),
                "machine": platform.machine(),
                "system": platform.system(),
            },
            "network_calls": 0,
            "model_calls": 0,
        },
    )
    print(json.dumps(checks, ensure_ascii=False, indent=2))


async def _run_requests() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requests = p47.current_requests()
    if len(requests) != EXPECTED_REQUESTS:
        raise ValueError("冻结请求数漂移")
    baseline = build_research_policy(p47.STRATEGY)
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    composition = _GuardedComposition(
        baseline,
        rules.analyze_public_self_draw_successors,
        LeafProgramExecutor(R17_SOURCE.read_text(encoding="utf-8"), name="r18-p52-r17-b"),
    )
    budget = DecisionBudget(
        enhancement_deadline_monotonic=time.monotonic() + 86_400.0,
        fallback_deadline_monotonic=time.monotonic() + 86_400.0,
        latest_send_at_monotonic=time.monotonic() + 86_400.0,
    )
    rows: list[dict[str, Any]] = []
    special_plans = 0
    special_exact = 0
    response_plans = 0
    response_exact = 0
    ordinary_draw_plans = 0
    ordinary_changed = 0
    key_set_failures = 0
    action_value_failures = 0
    special_counts = {key: 0 for key in SPECIAL_TRACE_KEYS}
    latencies: list[float] = []
    for index, (label, request) in enumerate(requests, 1):
        expected = await baseline.choose(request, budget)
        started = time.perf_counter_ns()
        actual, specials = await composition.choose(request, budget)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        latencies.append(elapsed_ms)
        expected_keys = tuple(item.action_key for item in expected.candidates)
        actual_keys = tuple(item.action_key for item in actual.candidates)
        same_plan = actual == expected
        same_key_set = set(actual_keys) == set(expected_keys)
        if not same_key_set:
            key_set_failures += 1
        if any("action_value_failed" in reason for reason in expected.degraded_reasons):
            action_value_failures += 1
        if specials:
            special_plans += 1
            special_exact += int(same_plan)
            for key in specials:
                special_counts[key] += 1
        elif request.observation.phase != "draw":
            response_plans += 1
            response_exact += int(same_plan)
        else:
            ordinary_draw_plans += 1
            ordinary_changed += int(not same_plan)
        rows.append(
            {
                "index": index,
                "label": label,
                "phase": request.observation.phase,
                "specials": specials,
                "same_plan": same_plan,
                "same_key_set": same_key_set,
                "top_before": expected_keys[0] if expected_keys else None,
                "top_after": actual_keys[0] if actual_keys else None,
                "elapsed_ms": elapsed_ms,
            }
        )
        if index % 50 == 0:
            print("P52 progress {0}/{1}".format(index, len(requests)), flush=True)
    summary = {
        "requests": len(requests),
        "special_plans": special_plans,
        "special_exact_plans": special_exact,
        "special_counts": special_counts,
        "response_plans": response_plans,
        "response_exact_plans": response_exact,
        "ordinary_draw_plans": ordinary_draw_plans,
        "ordinary_changed_plans": ordinary_changed,
        "candidate_key_set_failures": key_set_failures,
        "action_value_failures": action_value_failures,
        "latency_ms": {
            "mean": sum(latencies) / len(latencies),
            "max": max(latencies),
        },
    }
    return rows, summary


def run() -> None:
    """执行冻结请求的能力保护与普通弃牌非空组合审计。"""

    authorization_path = _project_file(_PROJECT_ROOT, OUT / "authorization.json")
    pre_path = _project_file(_PROJECT_ROOT, OUT / "manifest-pre.json")
    if not authorization_path.exists() or not pre_path.exists():
        raise SystemExit("必须先执行 freeze 并提交冻结记录")
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("P52 结果已存在；拒绝覆盖")
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    if authorization.get("frozen_inputs") != frozen_inputs():
        raise ValueError("P52 冻结输入漂移")
    rows, summary = asyncio.run(_run_requests())
    checks = {
        "request_count_exact": summary["requests"] == EXPECTED_REQUESTS,
        "special_plan_count_exact": summary["special_plans"]
        == EXPECTED_SPECIAL_PLANS,
        "all_special_plans_exact": summary["special_exact_plans"]
        == summary["special_plans"],
        "all_response_plans_exact": summary["response_exact_plans"]
        == summary["response_plans"],
        "candidate_key_sets_preserved": summary["candidate_key_set_failures"] == 0,
        "action_value_failures_zero": summary["action_value_failures"] == 0,
        "ordinary_path_nonempty": summary["ordinary_changed_plans"] >= 1,
    }
    passed = all(checks.values())
    result = {
        "schema": "r18-p52-guarded-successor-composition-result/1",
        "status": (
            "PASS_P52_GUARDED_COMPOSITION_FEASIBILITY"
            if passed
            else "FAIL_P52_GUARDED_COMPOSITION_FEASIBILITY"
        ),
        "p47_candidate_sha256": R18_INTEGRATED_POSITIVE_V1_SHA256,
        "r17_candidate_identity": R17_CANDIDATE_IDENTITY,
        "r17_source_sha256": R17_SOURCE_SHA256,
        "summary": summary,
        "checks": checks,
        "tables_run": 0,
        "model_calls": 0,
        "strength_claim": False,
        "release_eligible": False,
        "next": (
            "冻结组合身份，并在全新来源运行1024桌独立确认"
            if passed
            else "关闭或修正组合，不进入完整桌确认"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "request-audit.json"), rows)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest.json"),
        {
            "schema": "r18-p52-guarded-successor-composition-manifest/1",
            "authorization_sha256": digest(authorization_path),
            "manifest_pre_sha256": digest(pre_path),
            "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
            "request_audit_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "request-audit.json")),
            "frozen_inputs": frozen_inputs(),
            "network_calls": 0,
            "model_calls": 0,
            "release_eligible": False,
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "run"))
    globals()[parser.parse_args().operation]()
