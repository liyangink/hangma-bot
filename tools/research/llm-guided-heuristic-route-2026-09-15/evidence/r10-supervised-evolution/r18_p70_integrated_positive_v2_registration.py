"""R18 P70：登记第二版累计正向能力父代，并验证包内离线装配。"""

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
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p47_integrated_parent_registration as p47  # noqa: E402
import r18_p66b_nonwhite_baotou_candidate_preflight as p66b  # noqa: E402
import r18_p67_nonwhite_baotou_blind_replication as p67  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.bootstrap import (  # noqa: E402
    AVAILABLE_STRATEGIES,
    RESEARCH_STRATEGY_NAMES,
    build_research_policy,
)
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.research_candidates import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_NAME,
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
    build_research_candidate_scorer,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p70-integrated-positive-v2-registration-01-20260923')
P69 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p69-nonwhite-baotou-table-confirmation-01-20260923/result.json')
CANDIDATE = p66b.CANDIDATE
STRATEGY = "action_value:r18_integrated_positive_v2"
REPEATS = 3
OPERATION_LIMIT = 100_000


def digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_digest(value: str) -> str:
    """返回 UTF-8 文本 SHA-256。"""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def percentile(values: Iterable[float], q: float) -> float:
    """用最近秩计算诊断分位数。"""

    ordered = sorted(values)
    if not ordered:
        raise ValueError("分位数输入不能为空")
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def current_views(
    requests: list[tuple[str, Any]] | None = None,
) -> list[tuple[str, Any]]:
    """把全部累计请求转为正式评分视图。"""

    limits = ValueAnalysisLimits()
    return [
        (label, build_scoring_view(request, value_limits=limits))
        for label, request in (current_requests() if requests is None else requests)
    ]


def current_requests() -> list[tuple[str, Any]]:
    """汇集 P47 全量请求与 P63 开发/复验 32 个精确自然窗口。"""

    result = list(p47.current_requests())
    for target in p66b.p64.targets():
        if target["split"] == "development":
            result.append(("p63:development:" + target["target_id"], p66b.exact_request(target)))
    for target in p67.targets():
        if target["split"] == "replication":
            result.append(("p63:replication:" + target["target_id"], p67.exact_request(target)))
    if len(result) != 409:
        raise ValueError("P70 累计请求数应为409，实际 " + str(len(result)))
    return result


async def replay_requests(
    packaged: ActionValuePolicy,
    reference: ActionValuePolicy,
    requests: list[tuple[str, Any]],
) -> tuple[list[dict[str, Any]], list[float]]:
    """经正式策略接缝逐请求核对完整计划与候选源码一致。"""

    budget = DecisionBudget(1_000_000_000.0, 1_000_000_000.0, 1_000_000_000.0)
    rows = []
    latencies = []
    for label, request in requests:
        expected = await reference.choose(request, budget)
        started = time.perf_counter_ns()
        actual = await packaged.choose(request, budget)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        if actual != expected:
            raise ValueError("包内完整计划与 P65 源码不等价：" + label)
        if any("action_value_failed" in reason for reason in actual.degraded_reasons):
            raise ValueError("包内策略发生 action_value 降级：" + label)
        rows.append({
            "label": label,
            "elapsed_ms": elapsed_ms,
            "candidate_count": len(actual.candidates),
            "top_action": None if not actual.candidates else actual.candidates[0].action_key,
            "exact_plan_equal": True,
        })
        latencies.append(elapsed_ms)
    return rows, latencies


def run() -> None:
    """验证包内身份与全部能力视图后，登记新的活动研究父代。"""

    if OUT.exists():
        raise SystemExit("P70 目录已存在；拒绝覆盖")
    p69 = json.loads(P69.read_text(encoding="utf-8"))
    source = CANDIDATE.read_text(encoding="utf-8")
    checks = {
        "p69_passed": p69.get("status") == "PASS_P69_NONWEALTH_BAOTOU_TABLE_CONFIRMATION",
        "p69_candidate_identity": p69.get("candidate_sha256") == text_digest(source),
        "p69_opened_registration": p69.get("decision") == "OPEN_P70_INTEGRATED_PARENT_PREFLIGHT",
        "packaged_digest_matches_constant": (
            text_digest(R18_INTEGRATED_POSITIVE_V2_SOURCE)
            == R18_INTEGRATED_POSITIVE_V2_SHA256
        ),
        "packaged_source_exactly_matches_p65": R18_INTEGRATED_POSITIVE_V2_SOURCE == source,
        "strategy_in_research_registry": STRATEGY in RESEARCH_STRATEGY_NAMES,
        "strategy_absent_from_network_registry": STRATEGY not in AVAILABLE_STRATEGIES,
    }
    if not all(checks.values()):
        raise ValueError("P70 身份或离线隔离检查失败：" + repr(checks))

    packaged_scorer = build_research_candidate_scorer(R18_INTEGRATED_POSITIVE_V2_NAME)
    reference_scorer = ActionValueScorer(R18_INTEGRATED_POSITIVE_V2_NAME, source)
    requests = current_requests()
    score_rows = []
    score_latencies = []
    maximum_operations = 0
    for label, view in current_views(requests):
        expected = reference_scorer.score(view)
        actual = None
        operations = 0
        timings = []
        for _ in range(REPEATS):
            started = time.perf_counter_ns()
            actual = packaged_scorer.score(view)
            timings.append((time.perf_counter_ns() - started) / 1_000_000.0)
            operations = packaged_scorer.last_operation_count
        if actual != expected:
            raise ValueError("包内评分与 P65 源码不等价：" + label)
        if operations > OPERATION_LIMIT:
            raise ValueError("包内评分超出默认工作量：" + label)
        maximum_operations = max(maximum_operations, operations)
        score_latencies.extend(timings)
        score_rows.append({
            "label": label,
            "exact_batch_equal": True,
            "operations": operations,
            "elapsed_ms": timings,
        })

    packaged_policy = build_research_policy(STRATEGY)
    reference_policy = ActionValuePolicy(
        ActionValueScorer(R18_INTEGRATED_POSITIVE_V2_NAME, source),
        value_limits=ValueAnalysisLimits(),
    )
    request_rows, request_latencies = asyncio.run(
        replay_requests(packaged_policy, reference_policy, requests)
    )

    result = {
        "schema": "r18-p70-integrated-positive-v2-registration-result/1",
        "status": "PASS_P70_INTEGRATED_POSITIVE_V2_REGISTRATION",
        "strategy": STRATEGY,
        "candidate_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "checks": checks,
        "scoring_replay": {
            "views": len(score_rows),
            "repeats": REPEATS,
            "calls": len(score_latencies),
            "all_exact_batch_equal": True,
            "maximum_operations": maximum_operations,
            "operation_limit": OPERATION_LIMIT,
            "latency_ms": {
                "p50": percentile(score_latencies, 0.50),
                "p95": percentile(score_latencies, 0.95),
                "p99": percentile(score_latencies, 0.99),
                "max": max(score_latencies),
            },
        },
        "choose_replay": {
            "requests": len(request_rows),
            "all_exact_plan_equal": True,
            "action_value_failures": 0,
            "latency_ms": {
                "p50": percentile(request_latencies, 0.50),
                "p95": percentile(request_latencies, 0.95),
                "p99": percentile(request_latencies, 0.99),
                "max": max(request_latencies),
            },
        },
        "selection_eligible": True,
        "active_research_parent": True,
        "release_eligible": False,
        "next": "执行P71累计候选全链并发、截止、409重规划与紧急降级预检",
    }
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "score-replay.json"), score_rows)
    write_json(_project_file(_PROJECT_ROOT, OUT / "choose-replay.json"), request_rows)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(_project_file(_PROJECT_ROOT, OUT / "active-parent.json"), {
        "schema": "r18-active-research-parent/3",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parent_id": "r18-p70-integrated-positive-v2-active-parent/v1",
        "role": "cumulative_hangma_opportunity_research_leader",
        "candidate_path": str(CANDIDATE),
        "candidate_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "inherited_capabilities": [
            "two_wealth.piao_keeps_baotou",
            "dealer_initial.seven_pairs_one_self_draw_value",
            "three_or_four_wealth.piao_proxy",
            "added_gang.strict_dominance",
            "hu_vs_nonwealth_baotou.complete_higher_fan_routes",
        ],
        "evidence": {
            "p47_parent_registration_sha256": digest(p47.OUT / "result.json"),
            "p66b_preflight_sha256": digest(p66b.OUT / "result.json"),
            "p67_blind_replication_sha256": digest(p67.OUT / "result.json"),
            "p69_table_confirmation_sha256": digest(P69),
        },
        "table_safety": {
            "tables": p69["tables"],
            "source_units": p69["source_units"],
            "independent_root_clusters": p69["independent_root_clusters"],
            "stage_score_delta_mean_vs_p47": p69["overall"]["stage_score_delta_mean"],
            "root_cluster_bootstrap_mean_95_interval": p69["overall"]["root_cluster_bootstrap_mean_95_interval"],
            "candidate_requests": p69["request_audit_counts"]["requests"],
            "new_overlay_triggered_requests": p69["natural_exposure"]["new_overlay_triggered_requests"],
            "request_failures": 0,
        },
        "stable_control": {
            "name": "P47",
            "candidate_path": str(p66b.PARENT),
            "candidate_sha256": digest(p66b.PARENT),
        },
        "selection_eligible": True,
        "active_research_parent": True,
        "release_eligible": False,
        "next_required": "完成P71全链预检；在另行冻结发布包前保持真实网络关闭",
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p70-integrated-positive-v2-registration-manifest/1",
        "script_sha256": digest(Path(__file__)),
        "candidate_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "p69_sha256": digest(P69),
        "package_module_sha256": digest(_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/research_candidates.py")),
        "package_source_module_sha256": digest(
            _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py")
        ),
        "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
        "active_parent_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "active-parent.json")),
        "platform": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "system": platform.system(),
        },
        "network_calls": 0,
        "model_calls": 0,
        "release_eligible": False,
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    globals()[parser.parse_args().operation]()
