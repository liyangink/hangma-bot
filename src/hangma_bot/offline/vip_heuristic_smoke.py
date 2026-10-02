"""VIP 独立启发式的身份冻结与严格机械桌赛，不评定比赛强度。"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma._standard import backend_info
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.natural_preparation import NATURAL_PREPARATION_SEMANTICS_VERSION
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json
from hangma_bot.policy.route_heuristic_view import (
    VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION, VIP_ROUTE_GRAPH_SCHEMA_VERSION,
    VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION,
)
from hangma_bot.policy.route_vip_heuristic import (
    VIP_ROUTE_HEURISTIC_SEED_SOURCE, RouteVipHeuristicPolicy,
    VipRouteProjectionLimits, compute_vip_candidate_identity,
)
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine

from .evaluate import MatchDriverConfig, drive_match
from .scoring_sources import REPO_ROOT, digest_of_file, source_manifest, write_code_snapshot

VIP_IDENTITY_ROOTS = (
    "hangma_bot.policy.route_vip_heuristic",
    "hangma_bot.policy.route_heuristic_view",
    "hangma_bot.hangma.engine",
)
VIP_SMOKE_ROOTS = VIP_IDENTITY_ROOTS + (
    "hangma_bot.offline.vip_heuristic_smoke",
    "hangma_bot.simulation.engine",
)


def _digest(value: Any) -> str:
    """对可序列化身份材料取完整 SHA256；非有限数及未知类型直接拒绝。"""

    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def freeze_vip_identity(
    source: str, *, max_operations: int = 100_000,
    projection_limits: VipRouteProjectionLimits | None = None,
    rule_config: RuleConfig | None = None,
    route_limits: ValueAnalysisLimits | None = None,
) -> dict[str, Any]:
    """冻结真实 VIP 源码、合同、依赖闭包及数学后端；仅在离线读文件。

    candidate_id 不含作者模型或父代关系。原生实现的源码和已加载二进制
    都纳入身份，避免仅凭语义标签沿用另一份实现的成绩。无网络副作用。
    """

    contract = REPO_ROOT / "review/vip-route-2026-09-30/FIXED-FRAMEWORK-CONTRACT-V3-NATURAL-PREPARATION.md"
    manifest = source_manifest(VIP_IDENTITY_ROOTS)
    native_source = "src/hangma_bot/hangma/_grouped_native.c"
    manifest[native_source] = digest_of_file(REPO_ROOT / native_source)
    backend = dict(backend_info())
    native_path = backend.pop("native_path")
    backend["native_binary"] = None if native_path is None else digest_of_file(Path(native_path))
    deps = _digest({"source_manifest": manifest, "math_backend": backend})
    params = {
        "max_operations": max_operations,
        "projection_limits": asdict(projection_limits or VipRouteProjectionLimits()),
        "max_local_collection_size": (projection_limits or VipRouteProjectionLimits()).max_nodes,
        "rule_config": asdict(rule_config or RuleConfig("hangma-mvp-v10-public-counts", 1, False)),
        "route_limits": asdict(route_limits or ValueAnalysisLimits(max_expansions=8192)),
    }
    contract_sha = digest_of_file(contract)["sha256"]
    return {
        "candidate_id": compute_vip_candidate_identity(source, contract_sha, deps, params),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "contract_path": str(contract.relative_to(REPO_ROOT)),
        "contract_sha256": contract_sha, "deps_digest": deps,
        "source_manifest": manifest, "math_backend": backend, "params": params,
        "view_schema_version": VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION,
        "graph_schema_version": VIP_ROUTE_GRAPH_SCHEMA_VERSION,
        "normal_draw_hu_payment_semantics_version": VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION,
        "natural_preparation_semantics_version": NATURAL_PREPARATION_SEMANTICS_VERSION,
    }


class _AuditPolicy:
    """仅离线记录可见输入、全合法评分与失败；不改变策略选择。"""

    def __init__(self, inner: RouteVipHeuristicPolicy, stream) -> None:
        self.inner = inner
        self.name = inner.name
        self.stream = stream
        self.attempts = 0

    async def choose(self, request, budget):
        """成功和抛错都写一行；毫秒仅是策略计算观察，不证明官方时限。"""

        observation = observation_to_json(request.observation)
        row = {
            "schema": "vip-heuristic-smoke-decision/1",
            "decision_id": request.decision_id,
            "window_key": window_key_to_json(request.window_key),
            "observation": observation,
            "observation_sha256": _digest(observation),
            "legal_action_keys": [item.action_key for item in request.rules.legal_candidates],
            "competition_audit_only": asdict(request.competition),
        }
        self.attempts += 1
        started = time.perf_counter()
        try:
            plan = await self.inner.choose(request, budget)
            row["status"] = "scored"
            row["selected_action_key"] = plan.candidates[0].action_key
            row["candidates"] = [{
                "rank": item.rank, "action_key": item.action_key,
                "score": item.total_score, "trace": item.score_trace,
                "is_emergency": item.is_emergency,
            } for item in plan.candidates]
            return plan
        except Exception as exc:
            row["status"] = "failed"
            row["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            row["policy_compute_ms_observed"] = (time.perf_counter() - started) * 1000
            row["candidate_counted_operations"] = self.inner.executor.last_operation_count
            self.stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            self.stream.flush()


async def run_vip_smoke(
    out_dir: Path, *, start_seed: int, seeds: int, rounds: int,
    source: str = VIP_ROUTE_HEURISTIC_SEED_SOURCE,
    max_operations: int = 100_000,
    projection_limits: VipRouteProjectionLimits | None = None,
) -> dict[str, Any]:
    """四席同候选，严格完成给定完整桌；失败保留分母和观察，不续打保底。

    out_dir 必须不存在以免覆盖冻结证据。逻辑时钟只验机械持续性，真实
    计算时间单独记录。开跑前后重新核验身份；运行中变更实现使本批失效。
    """

    if any(type(v) is not int for v in (start_seed, seeds, rounds)) or start_seed < 0 or min(seeds, rounds) < 1:
        raise ValueError("种子须为非负整数；数量和完整桌局数须为正整数")
    out_dir.mkdir(parents=True, exist_ok=False)
    config = TournamentConfig(1, rounds, RuleConfig("hangma-mvp-v10-public-counts", 1, False), TimingConfig(1, 1, 3))
    analysis_limits = ValueAnalysisLimits(max_expansions=8192)
    identity = freeze_vip_identity(
        source, max_operations=max_operations, projection_limits=projection_limits,
        rule_config=config.rules, route_limits=analysis_limits,
    )
    manifest = source_manifest(VIP_SMOKE_ROOTS)
    manifest.update(identity["source_manifest"])
    write_code_snapshot(out_dir, manifest)
    (out_dir / "contract.md").write_bytes((REPO_ROOT / identity["contract_path"]).read_bytes())
    native_path = backend_info()["native_path"]
    if native_path is not None:
        (out_dir / "math-native.bin").write_bytes(Path(native_path).read_bytes())
    (out_dir / "candidate.py").write_text(source, encoding="utf-8")
    prereg = {
        "schema": "vip-heuristic-smoke-manifest/1",
        "kind": "mechanical_smoke_not_strength_or_runtime_gate",
        "identity": identity, "evaluation_source_manifest": manifest,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "config": asdict(config), "start_seed": start_seed, "seeds": seeds,
        "strict_policy": True, "normal_fallback_allowed": False,
        "clock_mode": "logical", "timing_scope": "policy_compute_only_observed",
    }
    (out_dir / "manifest.json").write_text(json.dumps(prereg, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rules = HangmaRules(config.rules)
    rows = []
    started = time.perf_counter()
    with gzip.open(out_dir / "decisions.jsonl.gz", "wt", encoding="utf-8") as stream:
        policy = _AuditPolicy(RouteVipHeuristicPolicy(
            config.rules, source=source, max_operations=max_operations,
            projection_limits=projection_limits,
        ), stream)
        for seed in range(start_seed, start_seed + seeds):
            spec = MatchSpec(f"vip-heuristic-smoke-{seed}", f"vip-heuristic-smoke-{seed}", config, seed, 0, (0, 0, 0, 0))
            outcome = await drive_match(
                engine=SimulationEngine(rules), spec=spec,
                policies_by_seat=(policy, policy, policy, policy), rules=rules,
                choice_factory=lambda key, action: SimulationChoice(key, action),
                config=MatchDriverConfig(
                    clock_mode="logical", step_limit=1000 * rounds, budget_policy=BudgetPolicy(),
                    competition_tournament_id=spec.scenario_id, strict_policy=True,
                    route_limits=analysis_limits,
                ), now_monotonic=lambda: 800.0, wall_clock=None,
            )
            row = {"seed": seed, **outcome.to_json()}
            rows.append(row)
            (out_dir / f"table-{seed}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    final_identity = freeze_vip_identity(
        source, max_operations=max_operations, projection_limits=projection_limits,
        rule_config=config.rules, route_limits=analysis_limits,
    )
    completed = sum(row["status"] == "complete" and row["completed_hands"] == rounds for row in rows)
    stable = identity == final_identity and manifest == {**source_manifest(VIP_SMOKE_ROOTS), **final_identity["source_manifest"]}
    summary = {
        "schema": "vip-heuristic-smoke-result/1", "candidate_id": identity["candidate_id"],
        "identity_stable": stable, "requested_tables": seeds, "complete_tables": completed,
        "planned_rounds": rounds, "audited_attempts": policy.attempts,
        "status": "mechanical_smoke_pass" if stable and completed == seeds else "failed",
        "wall_clock_seconds_observed": time.perf_counter() - started,
        "rows": [{key: value for key, value in row.items() if key != "decisions"} for row in rows],
        "strength_or_release_claim": False,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
