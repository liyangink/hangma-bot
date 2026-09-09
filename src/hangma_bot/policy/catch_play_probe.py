"""测试房抓打圈探针：主动弃白增加覆盖，并优先尝试规则已提供的吃碰。

这是动作权限实验，不追求积分。只重排已有计划，不生成新动作、不越过
圈主或窗口限制；运行配置限定为 test_room。基础 V2 评分保留供审计。
"""

from __future__ import annotations

from dataclasses import replace

from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Peng

from .interface import BotPolicy, DecisionBudget, DecisionPlan, DecisionRequest


CATCH_PLAY_PROBE_VERSION = "catch-play-probe-v1"


class CatchPlayProbePolicy:
    """优先合法弃白与响应鸣牌的专用测试策略；不包装普通弃白保护。

    ``base_policy`` 由组合根注入，负责正常评分、已拒动作过滤和时间预算。
    合法弃白优先于胡牌，包括起手已有白板；这会主动牺牲牌效和积分。
    """

    def __init__(self, base_policy: BotPolicy) -> None:
        self.base_policy = base_policy

    async def choose(
        self, request: DecisionRequest, budget: DecisionBudget
    ) -> DecisionPlan:
        """在原始预算内委托排序，再稳定提升试验动作；异常与取消原样传播。"""

        plan = await self.base_policy.choose(request, budget)
        observation = request.observation

        def probe_reason(candidate) -> str:
            action = candidate.action
            if (
                observation.phase == "draw"
                and observation.turn_seat == observation.seat
                and isinstance(action, Discard)
                and action.tile == observation.rule_state.wealth_god
            ):
                return "优先合法弃白以增加抓打圈与换主覆盖，允许为试验放弃本次胡牌"
            if (
                observation.phase in ("response_peng", "response_chi")
                and observation.seat in observation.responding_seats
                and (
                    isinstance(action, (Chi, Peng))
                    or isinstance(action, Gang) and action.kind is GangKind.EXPOSED
                )
            ):
                return "已有响应窗口内优先尝试规则提供的鸣牌；平台开窗与执行结果分别核验"
            return ""

        ordered = sorted(
            plan.candidates,
            key=lambda candidate: (not bool(probe_reason(candidate)), candidate.rank),
        )
        candidates = tuple(
            replace(
                candidate,
                rank=rank,
                reasons=candidate.reasons + (
                    (f"定向测试[{CATCH_PLAY_PROBE_VERSION}]：{probe_reason(candidate)}",)
                    if probe_reason(candidate) else ()
                ),
            )
            for rank, candidate in enumerate(ordered, 1)
        )
        return replace(
            plan,
            candidates=candidates,
            degraded_reasons=plan.degraded_reasons + (
                f"定向测试[{CATCH_PLAY_PROBE_VERSION}]：仅供测试房规则验证，"
                "rank 为执行次序，原 V2 分数不表示试验优先级；不作为策略强度样本",
            ),
        )
