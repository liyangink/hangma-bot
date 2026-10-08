"""R18 P41：双财神候选的离线全链并发、截止、重规划与重装配预检。"""

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

import confirmation_execution_identity as guard  # noqa: E402
import r18_p38_integrated_parent_preflight as p38  # noqa: E402
from hangma_bot.application.audit import AuditTrail  # noqa: E402
from hangma_bot.application.contracts import (  # noqa: E402
    AuditReceipt,
    AuditSummary,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitRejectedRetryable,
)
from hangma_bot.application.deadline import BudgetPolicy, SystemClock  # noqa: E402
from hangma_bot.application.decision_loop import (  # noqa: E402
    RuntimeServices,
    run_action_window,
)
from hangma_bot.bootstrap import (  # noqa: E402
    AVAILABLE_STRATEGIES,
    build_research_policy,
)
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.actions import WindowKey  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.research_candidates import (  # noqa: E402
    R18_TWO_WEALTH_BAOTOU_V1_SHA256,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p41-full-chain-release-preflight-01-20260922')
P40A = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p40a-two-wealth-directed-confirmation-01-20260922/result.json')
P40B = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p40b-two-wealth-table-confirmation-01-20260922/result.json')
STRATEGY = "action_value:r18_two_wealth_baotou_v1"
RULE_CONFIG = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
LIMITS = ValueAnalysisLimits()
CONCURRENCY = 10
WINDOW_SECONDS = 1.0
MAX_END_TO_END_MS = 900.0
RESTART_REPLAYS = 32


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


def percentile(values: Iterable[float], q: float) -> float:
    """用最近秩返回毫秒分位数。"""

    ordered = sorted(values)
    if not ordered:
        raise ValueError("分位数输入不能为空")
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


class MemoryAuditSink:
    """P41 内存审计接缝；保留全部记录且不执行文件或网络副作用。"""

    def __init__(self) -> None:
        self.records: list[Any] = []

    def emit(self, record: Any) -> AuditReceipt:
        self.records.append(record)
        return AuditReceipt(queued=True, audit_degraded=False)

    async def aclose(self, timeout_seconds: float) -> AuditSummary:
        del timeout_seconds
        return AuditSummary(
            written=len(self.records),
            dropped_low_priority=0,
            missing_high_priority=0,
            serialization_failures=0,
            audit_degraded=False,
        )


class SequentialIds:
    """单进程并发预检使用的确定性审计标识生成器。"""

    def __init__(self) -> None:
        self._decision = 0

    def new_run_id(self) -> str:
        return "run-r18-p41"

    def new_decision_id(self, window_key: WindowKey) -> str:
        self._decision += 1
        return "dec-r18-p41-{0:04d}".format(self._decision)

    def new_stage_attempt_id(self, stage_no: int | None) -> str:
        return "sa-r18-p41-{0}".format("x" if stage_no is None else stage_no)


class AcceptingSession:
    """只记录动作并立即明确接收；不访问官方网络。"""

    def __init__(self) -> None:
        self.submitted: list[Any] = []

    async def submit(self, attempt: Any) -> SubmitAccepted:
        self.submitted.append(attempt)
        return SubmitAccepted(
            official_code="P41-OFFLINE-ACCEPT",
            authoritative_seq=attempt.based_on_authoritative_seq + 1,
        )


class RetryOnceSession(AcceptingSession):
    """第一次明确拒绝并返回同一窗口权威刷新，第二次接收。"""

    def __init__(self, window: ObservedActionWindow) -> None:
        super().__init__()
        self._window = window

    async def submit(self, attempt: Any) -> Any:
        self.submitted.append(attempt)
        if len(self.submitted) == 1:
            refreshed_seq = self._window.authoritative_seq + 1
            refreshed_observation = replace(
                self._window.observation,
                snapshot_seq=refreshed_seq,
                # 权威刷新已经消费到同一新水位；只改 snapshot_seq 会违反
                # PlayerObservation 的 consumed_seq >= snapshot_seq 不变量。
                consumed_seq=(
                    None
                    if self._window.observation.consumed_seq is None
                    else refreshed_seq
                ),
            )
            refreshed = ObservedActionWindow(
                observation=refreshed_observation,
                window_key=self._window.window_key,
                authoritative_seq=refreshed_observation.snapshot_seq,
                received_at_monotonic=time.monotonic(),
                timeout_seconds=self._window.timeout_seconds,
            )
            return SubmitRejectedRetryable(
                official_code="P41-OFFLINE-409",
                rejected_action_key=attempt.action_key,
                refreshed_window=refreshed,
            )
        return SubmitAccepted(
            official_code="P41-OFFLINE-ACCEPT",
            authoritative_seq=attempt.based_on_authoritative_seq + 1,
        )


class DelayedPolicy:
    """包裹冻结候选并故意越过保底截止，用于验证应用层紧急降级。"""

    def __init__(self, inner: Any, delay_seconds: float) -> None:
        self.inner = inner
        self.delay_seconds = delay_seconds
        self.policy_id = "p41-delayed:" + str(getattr(inner, "policy_id", "unknown"))

    async def choose(self, request: Any, budget: Any) -> Any:
        await asyncio.sleep(self.delay_seconds)
        return await self.inner.choose(request, budget)


def make_window(request: Any, label: str, *, timeout: float = WINDOW_SECONDS) -> ObservedActionWindow:
    """把冻结真实请求转为本次离线应用链窗口，并赋予唯一场次标识。"""

    observation = replace(request.observation, game_id="p41-" + label)
    key = WindowKey(
        game_id=observation.game_id,
        round_no=observation.round_no,
        trigger_seq=observation.snapshot_seq,
        phase=request.window_key.phase,
        seat=observation.seat,
    )
    return ObservedActionWindow(
        observation=observation,
        window_key=key,
        authoritative_seq=observation.snapshot_seq,
        received_at_monotonic=time.monotonic(),
        timeout_seconds=timeout,
    )


async def run_one(
    *,
    request: Any,
    label: str,
    policy: Any,
    rules: HangmaRules,
    ids: SequentialIds,
    session: Any | None = None,
    timeout: float = WINDOW_SECONDS,
) -> dict[str, Any]:
    """执行一个完整应用动作窗口并返回可复算审计摘要。"""

    sink = MemoryAuditSink()
    clock = SystemClock()
    audit = AuditTrail(
        sink,
        run_id="run-r18-p41",
        tournament_id="offline-p41",
        participant_id="offline-seat",
        clock=clock,
    )
    window = make_window(request, label, timeout=timeout)
    actual_session = session if session is not None else AcceptingSession()
    services = RuntimeServices(
        rules=rules,
        policy=policy,
        audit=audit,
        clock=clock,
        ids=ids,
        budget_policy=BudgetPolicy(),
        value_limits=LIMITS,
    )
    started = time.perf_counter_ns()
    result = await run_action_window(
        session=actual_session,
        window=window,
        services=services,
        competition=request.competition,
        stage_attempt_id="sa-" + label,
    )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
    planned = [record for record in sink.records if record.kind.value == "decision_planned"]
    inputs = [record for record in sink.records if record.kind.value == "decision_input"]
    ended = [record for record in sink.records if record.kind.value == "decision_ended"]
    returned = None if not planned else planned[-1].payload.get("returned_plan")
    degraded = [] if not planned else planned[-1].payload.get("degraded_reasons") or []
    submitted = [item.action_key for item in actual_session.submitted]
    return {
        "label": label,
        "result": result,
        "session": actual_session,
        "sink": sink,
        "elapsed_ms": elapsed_ms,
        "submitted": submitted,
        "input_budgets": [record.payload["budget"] for record in inputs],
        "ended": [record.payload for record in ended],
        "returned_plan": returned,
        "degraded_reasons": degraded,
        "audit_degraded": audit.audit_degraded,
        "construction_failures": audit.construction_failures,
    }


def scored_without_failure(row: dict[str, Any]) -> bool:
    """判定应用审计中的候选计划来自冻结 action-value 正常评分路径。"""

    returned = row["returned_plan"]
    reasons = [] if returned is None else returned.get("degraded_reasons") or []
    return (
        returned is not None
        and any(reason.startswith("action_value: ") for reason in reasons)
        and not any("action_value_failed" in reason for reason in reasons)
    )


async def concurrency_probe(requests: list[tuple[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """以真实最大并发 10 分批执行全部当前请求的 1 秒应用链。"""

    policy = build_research_policy(STRATEGY)
    rules = HangmaRules(RULE_CONFIG)
    ids = SequentialIds()
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(requests), CONCURRENCY):
        chunk = requests[offset:offset + CONCURRENCY]
        tasks = [
            run_one(
                request=request,
                label="c{0:03d}".format(offset + index),
                policy=policy,
                rules=rules,
                ids=ids,
            )
            for index, (_original_label, request) in enumerate(chunk)
        ]
        rows.extend(await asyncio.gather(*tasks))
    latencies = [row["elapsed_ms"] for row in rows]
    summary = {
        "requests": len(rows),
        "concurrency": CONCURRENCY,
        "window_seconds": WINDOW_SECONDS,
        "accepted": sum(row["result"].outcome_kind == "accepted" for row in rows),
        "one_submit": sum(len(row["submitted"]) == 1 for row in rows),
        "scored_without_failure": sum(scored_without_failure(row) for row in rows),
        "audit_degraded": sum(row["audit_degraded"] for row in rows),
        "audit_construction_failures": sum(row["construction_failures"] for row in rows),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies),
        },
    }
    return rows, summary


async def restart_probe(requests: list[tuple[str, Any]]) -> dict[str, Any]:
    """用两个全新策略实例重放同一批窗口，核对动作与分数计划一致。"""

    selected = requests[:RESTART_REPLAYS]
    runs = []
    for generation in (1, 2):
        policy = build_research_policy(STRATEGY)
        rules = HangmaRules(RULE_CONFIG)
        ids = SequentialIds()
        rows = []
        for index, (_label, request) in enumerate(selected):
            rows.append(await run_one(
                request=request,
                label="r{0}-{1:03d}".format(generation, index),
                policy=policy,
                rules=rules,
                ids=ids,
            ))
        runs.append(rows)

    def behavior(row: dict[str, Any]) -> dict[str, Any]:
        plan = row["returned_plan"] or {}
        candidates = plan.get("candidates") or []
        return {
            "submitted": row["submitted"],
            "candidates": [
                {
                    "action_key": item["action_key"],
                    "total_score": item["total_score"],
                    "score_parts": item["score_parts"],
                    "reasons": item["reasons"],
                    "is_emergency": item["is_emergency"],
                }
                for item in candidates
            ],
            "degraded_reasons": plan.get("degraded_reasons") or [],
        }

    left = [behavior(row) for row in runs[0]]
    right = [behavior(row) for row in runs[1]]
    return {
        "requests": len(selected),
        "fresh_policy_instances": 2,
        "all_behavior_equal": left == right,
        "all_scored_without_failure": all(
            scored_without_failure(row) for run in runs for row in run
        ),
    }


async def retry_probe(requests: list[tuple[str, Any]]) -> dict[str, Any]:
    """寻找至少两个合法动作的真实请求，验证 409 后原预算重规划。"""

    policy = build_research_policy(STRATEGY)
    rules = HangmaRules(RULE_CONFIG)
    selected = None
    for label, request in requests:
        if len(rules.analyze(request.observation, value_limits=LIMITS).legal_candidates) >= 2:
            selected = (label, request)
            break
    if selected is None:
        raise RuntimeError("P41 没有找到可执行 409 重规划的真实请求")
    label, request = selected
    window = make_window(request, "retry-base")
    session = RetryOnceSession(window)
    # run_one 会创建同构但标识不同的窗口；让 session 的刷新窗口改为该标识。
    row = await run_one(
        request=request,
        label="retry-base",
        policy=policy,
        rules=rules,
        ids=SequentialIds(),
        session=session,
    )
    return {
        "source_label": label,
        "outcome": row["result"].outcome_kind,
        "attempts": len(row["submitted"]),
        "submitted": row["submitted"],
        "rejected_action_not_repeated": (
            len(row["submitted"]) == 2 and row["submitted"][0] != row["submitted"][1]
        ),
        "same_budget_after_refresh": (
            len(row["input_budgets"]) == 2
            and row["input_budgets"][0] == row["input_budgets"][1]
        ),
        "audit_degraded": row["audit_degraded"],
    }


async def timeout_probe(request: Any) -> dict[str, Any]:
    """故意拖慢候选接口，验证应用层在 0.2 秒窗口提交规则紧急动作。"""

    inner = build_research_policy(STRATEGY)
    delayed = DelayedPolicy(inner, delay_seconds=1.0)
    row = await run_one(
        request=request,
        label="forced-timeout",
        policy=delayed,
        rules=HangmaRules(RULE_CONFIG),
        ids=SequentialIds(),
        timeout=0.2,
    )
    return {
        "window_seconds": 0.2,
        "outcome": row["result"].outcome_kind,
        "elapsed_ms": row["elapsed_ms"],
        "attempts": len(row["submitted"]),
        "submitted": row["submitted"],
        "returned_plan_is_null": row["returned_plan"] is None,
        "audit_degraded": row["audit_degraded"],
    }


async def execute() -> dict[str, Any]:
    """执行 P41 四个全链探针并按冻结门槛裁定。"""

    requests = p38.current_requests()
    rows, concurrency = await concurrency_probe(requests)
    restart = await restart_probe(requests)
    retry = await retry_probe(requests)
    timeout = await timeout_probe(requests[0][1])
    checks = {
        "network_registry_closed": STRATEGY not in AVAILABLE_STRATEGIES,
        "all_concurrent_windows_accepted": concurrency["accepted"] == len(requests),
        "all_concurrent_windows_one_submit": concurrency["one_submit"] == len(requests),
        "all_concurrent_windows_scored": concurrency["scored_without_failure"] == len(requests),
        "concurrent_audit_complete": (
            concurrency["audit_degraded"] == 0
            and concurrency["audit_construction_failures"] == 0
        ),
        "concurrent_max_below_send_budget": (
            concurrency["latency_ms"]["max"] < MAX_END_TO_END_MS
        ),
        "restart_behavior_equal": restart["all_behavior_equal"],
        "restart_scoring_complete": restart["all_scored_without_failure"],
        "retry_accepted": retry["outcome"] == "accepted" and retry["attempts"] == 2,
        "retry_excludes_rejected_action": retry["rejected_action_not_repeated"],
        "retry_keeps_original_budget": retry["same_budget_after_refresh"],
        "timeout_uses_emergency": (
            timeout["outcome"] == "accepted"
            and timeout["attempts"] == 1
            and timeout["returned_plan_is_null"]
            and timeout["elapsed_ms"] < timeout["window_seconds"] * 1000.0
        ),
    }
    passed = all(checks.values())
    return {
        "schema": "r18-p41-full-chain-release-preflight-result/1",
        "status": "PASS_P41_FULL_CHAIN_PREFLIGHT" if passed else "FAIL_P41_FULL_CHAIN_PREFLIGHT",
        "candidate_sha256": R18_TWO_WEALTH_BAOTOU_V1_SHA256,
        "requests_source": "P38 冻结的 252 个当前真实 DecisionRequest；P41 重新执行 HangmaRules.analyze",
        "concurrency": concurrency,
        "restart": restart,
        "retry": retry,
        "timeout_fallback": timeout,
        "gate_checks": checks,
        "confirmation_eligible": passed,
        "release_eligible": False,
        "timing_scope": (
            "本机离线内存会话；覆盖规则分析、策略评分、计划审计、合法复核和提交端口，"
            "不含 HTTP/TLS/官方平台时延，也不替代官方测试赛事"
        ),
        "next": (
            "生成只读人工发布审核包；保持真实策略注册关闭"
            if passed else "保持候选离线，按失败探针修复后使用新批次复验"
        ),
        "rows": [
            {
                "label": row["label"],
                "outcome": row["result"].outcome_kind,
                "elapsed_ms": row["elapsed_ms"],
                "submitted": row["submitted"],
                "scored_without_failure": scored_without_failure(row),
            }
            for row in rows
        ],
    }


def run() -> None:
    """校验 P40 前置身份，执行离线预检并冻结结果。"""

    if OUT.exists():
        raise SystemExit("P41 目录已存在；拒绝覆盖")
    p40a = json.loads(P40A.read_text(encoding="utf-8"))
    p40b = json.loads(P40B.read_text(encoding="utf-8"))
    if p40a.get("status") != "PASS_P40A_DIRECTED_CONFIRMATION":
        raise ValueError("P40a 未通过")
    if p40b.get("status") != "PASS_P40B_TABLE_CONFIRMATION":
        raise ValueError("P40b 未通过")
    if p40a.get("candidate_sha256") != R18_TWO_WEALTH_BAOTOU_V1_SHA256:
        raise ValueError("P40a 候选身份漂移")
    if p40b.get("candidate_sha256") != R18_TWO_WEALTH_BAOTOU_V1_SHA256:
        raise ValueError("P40b 候选身份漂移")

    result = asyncio.run(execute())
    if result["status"] != "PASS_P41_FULL_CHAIN_PREFLIGHT":
        raise RuntimeError(json.dumps(result["gate_checks"], ensure_ascii=False))
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    tracked = [Path(__file__), Path(p38.__file__), P40A, P40B]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p41-full-chain-release-preflight-manifest/1",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime": guard.capture(source_paths=tracked),
        "script_sha256": digest(Path(__file__)),
        "p40a_sha256": digest(P40A),
        "p40b_sha256": digest(P40B),
        "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
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
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    globals()[parser.parse_args().operation]()
