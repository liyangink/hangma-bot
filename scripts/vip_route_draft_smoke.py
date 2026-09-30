"""C_draft_M0 全窗口严格模拟烟测；只验机械持续性，不评定强度。"""

from __future__ import annotations

import asyncio
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.offline.evaluate import MatchDriverConfig, drive_match
from hangma_bot.policy.route_vip_draft import RouteVipDraftPolicy
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine


class _AuditPolicy:
    """离线保存每个策略计划的可见输入身份和全合法动作评分。"""

    def __init__(self, inner: RouteVipDraftPolicy) -> None:
        self.inner = inner
        self.name = inner.name
        self.rows: list[dict] = []

    async def choose(self, request, budget):
        """原样返回策略计划；审计不改变排序或驱动动作。"""

        plan = await self.inner.choose(request, budget)
        self.rows.append({
            "schema": "vip-draft-m0-decision/1",
            "decision_id": request.decision_id,
            "game_id": request.window_key.game_id,
            "round_no": request.window_key.round_no,
            "phase": request.window_key.phase.value,
            "seat": request.window_key.seat,
            "trigger_seq": request.trigger_seq,
            "observation_sha256": hashlib.sha256(
                repr(request.observation).encode("utf-8")).hexdigest(),
            "ruleset_version": request.rules.ruleset_version,
            "selected_action_key": plan.candidates[0].action_key,
            "candidates": [{
                "rank": item.rank,
                "action_key": item.action_key,
                "total_score": item.total_score,
                "score_parts": [{"name": part.name, "value": part.value}
                                for part in item.score_parts],
                "score_trace": item.score_trace,
                "is_emergency": item.is_emergency,
            } for item in plan.candidates],
        })
        return plan


async def main() -> None:
    """同一规则源跑所给种子的完整桌；异常桌保留失败行。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--audit-file", type=Path,
                        help="可选 gzip JSONL：逐窗口记录全部候选评分与可见观察摘要")
    args = parser.parse_args()
    if args.start_seed < 0 or args.seeds < 1 or args.rounds < 1:
        raise ValueError("牌山种子、数量与完整桌计划局数必须有效")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    config = TournamentConfig(1, args.rounds, rules.config, TimingConfig(1.0, 1.0, 3.0))
    policy = _AuditPolicy(RouteVipDraftPolicy())
    rows = []
    for seed in range(args.start_seed, args.start_seed + args.seeds):
        spec = MatchSpec(
            f"vip-draft-m0-seed{seed}", f"vip-draft-m0-seed{seed}",
            config, seed, 0, (0, 0, 0, 0),
        )
        outcome = await drive_match(
            engine=SimulationEngine(rules), spec=spec,
            policies_by_seat=(policy, policy, policy, policy), rules=rules,
            choice_factory=lambda key, action: SimulationChoice(key, action),
            config=MatchDriverConfig(
                clock_mode="logical", step_limit=1000 * args.rounds,
                budget_policy=BudgetPolicy(),
                competition_tournament_id=spec.scenario_id,
                strict_policy=True,
                route_limits=ValueAnalysisLimits(max_expansions=8192),
            ),
            now_monotonic=lambda: 800.0,
            wall_clock=None,
        )
        rows.append({
            "seed": seed,
            "status": outcome.status,
            "completed_hands": outcome.completed_hands,
            "steps": outcome.steps,
            "error_reason": outcome.error_reason,
            "runtime_counts": {
                "fallbacks": outcome.runtime_counts.fallbacks,
                "illegal_choices": outcome.runtime_counts.illegal_choices,
                "timeouts": outcome.runtime_counts.timeouts,
            },
            "decision_count": len(outcome.decisions),
            "phase_counts": {
                phase: sum(item.window_key.get("phase") == phase
                           for item in outcome.decisions)
                for phase in ("draw", "response_peng", "response_chi")
            },
            "action_counts": {
                family: sum(item.action_key is not None and
                            item.action_key.split(":")[0] == family
                            for item in outcome.decisions)
                for family in ("discard", "hu", "pass", "chi", "peng", "gang")
            },
            "final_scores": outcome.final_scores,
        })
    completed_decisions = sum(row["decision_count"] for row in rows
                              if row["status"] == "complete")
    if (all(row["status"] == "complete" for row in rows)
            and completed_decisions != len(policy.rows)):
        raise ValueError("完整桌动作窗口与策略计划审计记录数量不一致")
    if args.audit_file is not None:
        args.audit_file.parent.mkdir(parents=True, exist_ok=True)
        payload = ("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True)
                             for row in policy.rows) + "\n").encode("utf-8")
        if args.audit_file.suffix == ".gz":
            with args.audit_file.open("wb") as stream:
                with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0,
                                   compresslevel=9) as zipped:
                    zipped.write(payload)
        else:
            args.audit_file.write_bytes(payload)
    print(json.dumps({
        "run_kind": "C_draft_M0_strict_mechanical_smoke_not_strength",
        "policy": policy.name,
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "planned_rounds_per_table": args.rounds,
        "requested_seeds": args.seeds,
        "complete_tables": sum(row["status"] == "complete" for row in rows),
        "audited_policy_windows": len(policy.rows),
        "rows": rows,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
