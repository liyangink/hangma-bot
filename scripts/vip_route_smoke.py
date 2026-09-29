"""本地复验 VIP P1 的严格失败边界；不连接官方平台。

命令：.venv/bin/python scripts/vip_route_smoke.py
输出是固定牌山种子的一次研发烟测，不用于算法强度结论。
"""

from __future__ import annotations

import asyncio
import json

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.offline.evaluate import MatchDriverConfig, drive_match
from hangma_bot.policy.route_vip_proto import RouteVipPrototypePolicy
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice


async def main() -> None:
    """同一规则源驱动一张模拟桌；正常未接通动作使轨迹停止。"""

    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    tournament = TournamentConfig(
        1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)
    )
    spec = MatchSpec(
        "vip-p1-smoke-seed1", "vip-p1-smoke-seed1", tournament,
        1, 0, (0, 0, 0, 0),
    )
    policy = RouteVipPrototypePolicy()
    outcome = await drive_match(
        engine=SimulationEngine(rules), spec=spec,
        policies_by_seat=(policy, policy, policy, policy),
        rules=rules,
        choice_factory=lambda key, action: SimulationChoice(key, action),
        config=MatchDriverConfig(
            clock_mode="logical", step_limit=100, budget_policy=BudgetPolicy(),
            competition_tournament_id=spec.scenario_id,
            strict_policy=True,
            route_limits=ValueAnalysisLimits(max_expansions=8192),
        ),
        now_monotonic=lambda: 800.0,
        wall_clock=None,
    )
    print(json.dumps({
        "run_kind": "C_proto_P1_smoke_not_strength_evidence",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "seed": spec.seed,
        "status": outcome.status,
        "completed_hands": outcome.completed_hands,
        "steps": outcome.steps,
        "error_reason": outcome.error_reason,
        "decisions": [
            {"action_key": item.action_key, "fallback_reason": item.fallback_reason}
            for item in outcome.decisions
        ],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
