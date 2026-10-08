"""R18 P38：包内活动研究父代的一致性、离线隔离与决策时延预检。"""

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

import r18_p32_two_wealth_baotou_rare_teacher as p32  # noqa: E402
import r18_p34_two_wealth_candidate_preflight as p34  # noqa: E402
import r18_p35_two_wealth_hidden_admission as p35  # noqa: E402
import r18_p37_two_wealth_active_parent as p37  # noqa: E402
import r18_p5_development_preflight as p5  # noqa: E402
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
    R18_TWO_WEALTH_BAOTOU_V1_NAME,
    R18_TWO_WEALTH_BAOTOU_V1_SHA256,
    R18_TWO_WEALTH_BAOTOU_V1_SOURCE,
    build_research_candidate_scorer,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p38-integrated-parent-preflight-01-20260922')
STRATEGY = "action_value:r18_two_wealth_baotou_v1"
REPEATS = 3
OPERATION_LIMIT = 100_000


def digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_digest(value: str) -> str:
    """返回 UTF-8 文本 SHA-256。"""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 JSON；只在离线证据目录产生副作用。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def percentile(values: Iterable[float], q: float) -> float:
    """用最近秩计算诊断分位数；输入单位由调用方固定为毫秒。"""

    ordered = sorted(values)
    if not ordered:
        raise ValueError("分位数输入不能为空")
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def current_requests() -> list[tuple[str, Any]]:
    """汇集 P37 当前真实请求；退化变体只参与评分器回放，不伪造 RuleAnalysis。"""

    result: list[tuple[str, Any]] = []
    document = json.loads(p32.OUT.joinpath("targets.json").read_text(encoding="utf-8"))
    for target in document["targets"]:
        if target["split"] != "development":
            continue
        snapshot = json.loads(p32.snapshot_path(target).read_text(encoding="utf-8"))
        result.append((
            "development:" + target["target_id"],
            p34.request_from_snapshot(target, snapshot),
        ))
    hidden_document = json.loads(
        p35.OUT.joinpath("targets.json").read_text(encoding="utf-8")
    )
    for target in hidden_document["targets"]:
        snapshot = json.loads(p35.snapshot_path(target).read_text(encoding="utf-8"))
        result.append((
            "hidden:" + target["target_id"],
            p34.request_from_snapshot(target, snapshot),
        ))
    for target in p5.prior.targets():
        result.append(("p5:" + target["target_id"], p5.exact_request(target)))
    real_windows, _ = p34.load_legacy_real_windows()
    for name, request, _origins in real_windows:
        result.append(("real:" + name, request))
    return result


async def choose_replay(
    packaged: ActionValuePolicy,
    reference: ActionValuePolicy,
    requests: list[tuple[str, Any]],
) -> tuple[list[dict[str, Any]], list[float]]:
    """逐请求核对完整决策计划并记录包内策略 choose 时延。"""

    budget = DecisionBudget(
        enhancement_deadline_monotonic=1_000_000_000.0,
        fallback_deadline_monotonic=1_000_000_000.0,
        latest_send_at_monotonic=1_000_000_000.0,
    )
    rows: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    for label, request in requests:
        expected = await reference.choose(request, budget)
        started = time.perf_counter_ns()
        actual = await packaged.choose(request, budget)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        if actual != expected:
            raise ValueError("包内策略完整计划与 P37 源码不相等：" + label)
        if any("action_value_failed" in reason for reason in actual.degraded_reasons):
            raise ValueError("包内策略发生 action_value 降级：" + label)
        rows.append({
            "label": label,
            "elapsed_ms": elapsed_ms,
            "candidate_count": len(actual.candidates),
            "top_action": None if not actual.candidates else actual.candidates[0].action_key,
            "exact_plan_equal": True,
        })
        latencies_ms.append(elapsed_ms)
    return rows, latencies_ms


def run() -> None:
    """执行包内身份、255 视图评分回放、252 请求计划回放与诊断计时。"""

    if OUT.exists():
        raise SystemExit("P38 证据目录已存在；拒绝覆盖")
    source_path = p37.OUT / "candidate.py"
    source = source_path.read_text(encoding="utf-8")
    checks = {
        "packaged_digest_matches_constant": (
            text_digest(R18_TWO_WEALTH_BAOTOU_V1_SOURCE)
            == R18_TWO_WEALTH_BAOTOU_V1_SHA256
        ),
        "packaged_source_exactly_matches_p37": R18_TWO_WEALTH_BAOTOU_V1_SOURCE == source,
        "strategy_in_research_registry": STRATEGY in RESEARCH_STRATEGY_NAMES,
        "strategy_absent_from_network_registry": STRATEGY not in AVAILABLE_STRATEGIES,
    }
    if not all(checks.values()):
        raise ValueError("P38 包内身份或隔离检查失败：" + repr(checks))

    package_scorer = build_research_candidate_scorer(R18_TWO_WEALTH_BAOTOU_V1_NAME)
    reference_scorer = ActionValueScorer(R18_TWO_WEALTH_BAOTOU_V1_NAME, source)
    score_rows: list[dict[str, Any]] = []
    score_latencies_ms: list[float] = []
    maximum_operations = 0
    for label, view in p37.views():
        expected = reference_scorer.score(view)
        timings = []
        actual = None
        operations = None
        for _ in range(REPEATS):
            started = time.perf_counter_ns()
            actual = package_scorer.score(view)
            timings.append((time.perf_counter_ns() - started) / 1_000_000.0)
            operations = package_scorer.last_operation_count
        if actual != expected:
            raise ValueError("包内评分与 P37 源码不相等：" + label)
        if operations is None or operations > OPERATION_LIMIT:
            raise ValueError("包内评分超出默认工作量：" + label)
        maximum_operations = max(maximum_operations, operations)
        score_latencies_ms.extend(timings)
        score_rows.append({
            "label": label,
            "exact_batch_equal": True,
            "operations": operations,
            "elapsed_ms": timings,
        })

    packaged_policy = build_research_policy(STRATEGY)
    if not isinstance(packaged_policy, ActionValuePolicy):
        raise TypeError("build_research_policy 未返回 ActionValuePolicy")
    reference_policy = ActionValuePolicy(
        ActionValueScorer(R18_TWO_WEALTH_BAOTOU_V1_NAME, source),
        value_limits=ValueAnalysisLimits(),
    )
    requests = current_requests()
    choose_rows, choose_latencies_ms = asyncio.run(
        choose_replay(packaged_policy, reference_policy, requests)
    )

    result = {
        "schema": "r18-p38-integrated-parent-preflight-result/1",
        "status": "PASS_P38_PACKAGE_INTEGRATION",
        "strategy": STRATEGY,
        "candidate_sha256": R18_TWO_WEALTH_BAOTOU_V1_SHA256,
        "checks": checks,
        "scoring_replay": {
            "views": len(score_rows),
            "repeats": REPEATS,
            "calls": len(score_latencies_ms),
            "all_exact_batch_equal": True,
            "maximum_operations": maximum_operations,
            "operation_limit": OPERATION_LIMIT,
            "latency_ms": {
                "p50": percentile(score_latencies_ms, 0.50),
                "p95": percentile(score_latencies_ms, 0.95),
                "p99": percentile(score_latencies_ms, 0.99),
                "max": max(score_latencies_ms),
            },
        },
        "choose_replay": {
            "requests": len(choose_rows),
            "all_exact_plan_equal": True,
            "action_value_failures": 0,
            "latency_ms": {
                "p50": percentile(choose_latencies_ms, 0.50),
                "p95": percentile(choose_latencies_ms, 0.95),
                "p99": percentile(choose_latencies_ms, 0.99),
                "max": max(choose_latencies_ms),
            },
        },
        "timing_scope": (
            "单进程离线诊断；scoring 仅含受限候选评分，choose 含 ScoringView 投影、"
            "评分和计划组装，不含规则分析、应用调度、并发和网络预留"
        ),
        "platform": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "system": platform.system(),
        },
        "selection_eligible": True,
        "confirmation_eligible": True,
        "release_eligible": False,
        "next": "冻结发布候选身份并执行全链并发时限、独立确认和人工发布审核",
    }
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "score-replay.json"), score_rows)
    write_json(_project_file(_PROJECT_ROOT, OUT / "choose-replay.json"), choose_rows)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p38-integrated-parent-preflight-manifest/1",
        "script_sha256": digest(Path(__file__)),
        "p37_candidate_sha256": digest(source_path),
        "p37_equivalence_sha256": digest(p37.OUT / "equivalence.json"),
        "package_module_sha256": digest(
            _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/research_candidates.py")
        ),
        "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
        "score_replay_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "score-replay.json")),
        "choose_replay_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "choose-replay.json")),
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    globals()[parser.parse_args().operation]()
