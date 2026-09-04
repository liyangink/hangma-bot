"""合法鸣牌优先策略：合法 peng/chi/明杠候选排序提升至过之前。

用于官方测试房验收（配置项选择）：官方 1 秒响应窗口内，吃/碰/明杠的
价值判断必须立即做出，错过窗口即永久失去机会；加权启发式按分数排序时
鸣牌风险罚项可能把合法鸣牌压在"过"之后（过是保底，永不失去），
导致整场只打过。本策略把规则确认合法的 peng/chi/明杠候选稳定提升到
过之前，其余候选顺序完全沿用 WeightedHeuristicPolicy 口径：

- 候选来源、被拒过滤、评分与降级说明全部委托 WeightedHeuristicPolicy；
- 只做一次稳定重排：把鸣牌候选整体移动到过之前的第一个位置（无过时
  追加到末尾），组内相对顺序保持加权启发式的排名；
- 过永远保留在计划中兜底（除非已被官方明确拒绝）；胡牌候选位置不变
  （仍高于鸣牌）；
- 决策不变量：rank 升序重编、同输入同输出完全确定、不含已拒绝动作。

默认策略不变：本策略不修改 WeightedHeuristicPolicy 的任何行为。
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from hangma_bot.kernel.actions import Chi, Gang, GangKind, Pass, Peng

from .interface import DecisionBudget, DecisionPlan, DecisionRequest, RankedCandidate
from .weighted_heuristic import WeightedHeuristicPolicy
from .weights import DEFAULT_WEIGHTS, HeuristicWeights


def _is_claim(action) -> bool:
    """是否为响应窗口的合法鸣牌：碰、吃、明杠（暗杠/补杠不属于认领弃牌）。"""

    if isinstance(action, (Peng, Chi)):
        return True
    return isinstance(action, Gang) and action.kind is GangKind.EXPOSED


class ClaimIfLegalPolicy:
    """合法鸣牌优先的测试房验收策略；委托加权启发式做全部评分与过滤。"""

    def __init__(
        self,
        weights: HeuristicWeights = DEFAULT_WEIGHTS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = WeightedHeuristicPolicy(weights=weights, monotonic=monotonic)

    async def choose(
        self,
        request: DecisionRequest,
        budget: DecisionBudget,
    ) -> DecisionPlan:
        """先按加权启发式产出完整计划，再把合法鸣牌候选提升至过之前。"""

        plan = await self._inner.choose(request, budget)
        return _promote_claims(plan)


def _promote_claims(plan: DecisionPlan) -> DecisionPlan:
    """把合法鸣牌候选稳定移动到过之前；无鸣牌候选时原样返回计划。

    其余候选（胡、弃牌、暗杠、补杠、过……）的相对顺序不变；鸣牌候选
    之间的相对顺序保持加权启发式排名。rank 重编为 1..N 升序，排序
    变化时在 degraded_reasons 中留痕（可审计、确定性）。
    """

    claims: List[RankedCandidate] = [
        item for item in plan.candidates if _is_claim(item.action)
    ]
    if not claims:
        return plan
    rest: List[RankedCandidate] = [
        item for item in plan.candidates if not _is_claim(item.action)
    ]
    anchor: Optional[int] = next(
        (index for index, item in enumerate(rest) if isinstance(item.action, Pass)),
        None,
    )
    if anchor is None:
        ordered = rest + claims
    else:
        ordered = rest[:anchor] + claims + rest[anchor:]
    changed = [item.action_key for item in ordered] != [
        item.action_key for item in plan.candidates
    ]
    candidates = tuple(
        RankedCandidate(
            action=item.action,
            action_key=item.action_key,
            rank=index + 1,
            total_score=item.total_score,
            score_parts=item.score_parts,
            reasons=item.reasons,
            is_emergency=item.is_emergency,
        )
        for index, item in enumerate(ordered)
    )
    reasons = plan.degraded_reasons
    if changed:
        reasons = reasons + (
            "claim_if_legal：合法鸣牌候选（peng/chi/明杠）排序提升至过之前",
        )
    return DecisionPlan(
        decision_id=plan.decision_id,
        window_key=plan.window_key,
        based_on_authoritative_seq=plan.based_on_authoritative_seq,
        revision=plan.revision,
        candidates=candidates,
        degraded_reasons=reasons,
    )


__all__ = ["ClaimIfLegalPolicy"]
