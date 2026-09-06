"""V2 只补过牌的可比等待评分；其余候选复用冻结 V1 的公开评分函数。

不执行向听或有效牌算法；所有等待数值来自 HangmaRules。
权重复用冻结的 HeuristicWeightsV1，默认值和其他动作偏好均不调整。
"""

import math
from dataclasses import replace
from typing import Awaitable, Callable, Tuple

from hangma_bot.hangma.interface import CandidateFactKind, RuleCandidate, RuleCompleteness
from hangma_bot.kernel.actions import Pass

from .evaluation_v1 import EvaluationContext, ScoredCandidate, build_context
from .evaluation_v1 import score_candidates as score_v1_candidates
from .interface import ScorePart
from .weights_v1 import HeuristicWeightsV1


def has_waiting_baseline(candidate: RuleCandidate) -> bool:
    """只识别可消费的过牌等待事实；这是可信度检查，不声明动作合法性。"""
    facts = candidate.facts
    return (
        isinstance(candidate.action, Pass)
        and facts is not None
        and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
        and facts.completeness is RuleCompleteness.COMPLETE
        and type(facts.shanten_after) is int and facts.shanten_after >= 0
        and facts.best_followup_discard is None
        and not facts.replacement_draw_unknown
    )


async def score_candidates(
    candidates: Tuple[RuleCandidate, ...],
    ctx: EvaluationContext,
    weights: HeuristicWeightsV1,
    check_deadline: Callable[[], Awaitable[None]],
) -> Tuple[ScoredCandidate, ...]:
    """只替换过牌的中性分项；其他候选保留 V1 分数和可信层级。

    输入都是规则合法候选。异常及非有限结果向上传播，交给应用已有保底。
    返回值不含模拟完整信息；缺过牌基线时由 V2 入口调整响应退路次序。
    """
    original = await score_v1_candidates(candidates, ctx, weights, check_deadline)
    result = []
    for item in original:
        await check_deadline()
        reasons = tuple(r.replace("V1 排序层", "V2 排序层") for r in item.reasons)
        if not isinstance(item.candidate.action, Pass):
            result.append(replace(item, reasons=reasons))
            continue
        reasons = tuple(r for r in reasons if "过保留 V0 中性基线" not in r)
        if not has_waiting_baseline(item.candidate):
            result.append(replace(item, priority=2, shanten=None, reasons=reasons + (
                "V2 缺可比等待基线：过牌事实为旧版、失败或等待形状不符，不伪造等待数值",
            )))
            continue
        facts = item.candidate.facts
        remaining = sum(u.remaining_estimate for u in facts.useful_tiles)
        parts = (
            ScorePart("第三层-向听数", -weights.shanten_step * facts.shanten_after),
            ScorePart("第四层-有效牌", round(weights.effective_tile * remaining, 1)),
        ) + tuple(p for p in item.parts if p.name != "第二层-保守兜底")
        total = round(sum(p.value for p in parts), 6)
        if not math.isfinite(total) or any(not math.isfinite(p.value) for p in parts):
            raise ValueError("V2 过牌评分非有限，交由应用层紧急保底")
        result.append(replace(item, priority=1, parts=parts, total=total,
                              shanten=facts.shanten_after, reasons=reasons + (
            f"V2 过牌等待：当前向听 {facts.shanten_after}，有效牌剩余估计 {remaining} 张；与吃碰使用同一牌效基准",
        )))
    return tuple(result)
