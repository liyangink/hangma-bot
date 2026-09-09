"""一次摸牌分值候选：在 V2 的安全计划中比较听牌后的条件结算。

只消费规则模块提供的路线，不枚举牌型，不把未见牌数解释为概率。
首版保留立即胡优先，普通摸牌与杠补分开，线上默认装配保持不变。
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Optional, Tuple

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    RuleCandidate,
    RuleCompleteness,
    ValueCoverage,
)
from hangma_bot.kernel.actions import Chi, Discard, Gang, Hu, Pass, Peng, action_key

from .errors import PolicyTimeoutError
from .heuristic_v2 import ComparableHeuristicPolicyV2
from .interface import DecisionBudget, DecisionPlan, DecisionRequest, ScorePart
from .weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1


@dataclass(frozen=True)
class _WaitingValue:
    """一个实际可执行的等待方案；单位为未见张数乘条件净得分。"""

    score_mass: float
    unseen_count: int
    followup_discard: Optional[str]


def _normal_ready(candidate: RuleCandidate) -> bool:
    """读取可信的听牌事实，不从手牌、动作名称或零值推断听牌。"""

    facts = candidate.facts
    return (
        isinstance(candidate.action, (Discard, Pass, Chi, Peng))
        and facts is not None
        and facts.completeness is RuleCompleteness.COMPLETE
        and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
        and type(facts.shanten_after) is int
        and facts.shanten_after == 0
        and not facts.replacement_draw_unknown
        and (not isinstance(candidate.action, Pass) or facts.best_followup_discard is None)
    )


class OneDrawValuePolicy:
    """普通摸牌听牌组按条件分值质量排序，其余情况完整沿用 V2。

    条件分值质量为同一个后续弃牌方案下的
    ``sum(未见张数 * 条件结算中本人的净得分)``。它只比较下一摸牌
    直接成胡的机会，不含未来生存概率、摸牌顺序或整单局输赢期望。
    ``value_weight`` 仅允许 0/1：0 精确返回 V2，1 启用此候选。
    不做插值，避免吃碰时的后续弃牌估值与实际弃牌使用不同标尺。
    """

    def __init__(
        self,
        weights: HeuristicWeightsV1 = DEFAULT_WEIGHTS_V1,
        monotonic: Callable[[], float] = time.monotonic,
        *,
        value_weight: float = 1.0,
    ) -> None:
        """绑定冻结 V2 基线和单调时钟；不创建规则引擎或外部副作用。"""

        if type(value_weight) not in (int, float) or value_weight not in (0, 1):
            raise ValueError("value_weight 首版只允许 0 或 1")
        self._weights = weights
        self._value_weight = value_weight
        self._monotonic = monotonic
        self._baseline = ComparableHeuristicPolicyV2(weights, monotonic)

    async def _check_deadline(self, budget: DecisionBudget) -> None:
        """在每条有限路线间让出事件循环；增强过期后沿用已完成的 V2。"""

        await asyncio.sleep(0)
        now = self._monotonic()
        if now > budget.enhancement_deadline_monotonic:
            raise PolicyTimeoutError(
                "一次摸牌分值计算超过增强截止时间：{now:.3f} > {deadline:.3f}".format(
                    now=now, deadline=budget.enhancement_deadline_monotonic
                )
            )

    async def _waiting_value(
        self, candidate: RuleCandidate, seat: int, budget: DecisionBudget,
    ) -> Optional[_WaitingValue]:
        """按后续弃牌分组取最好单一方案；缺事实返回未知，不填零。"""

        facts = candidate.value_facts
        if facts is None or facts.coverage is not ValueCoverage.COMPLETE:
            return None
        if facts.immediate_settlement is not None:
            raise ValueError("非立即胡的等待候选不能携带 immediate_settlement")

        groups: Dict[Optional[str], List[Tuple[float, int]]] = {}
        seen: Dict[Optional[str], set] = {}
        hands: Dict[Optional[str], Tuple[str, ...]] = {}
        claimed = isinstance(candidate.action, (Chi, Peng))
        for route in facts.routes:
            await self._check_deadline(budget)
            if route.conditions.draw_kind != "normal":
                # 杠补与普通摸牌没有相同的等待时间，不能混在此标尺内。
                return None
            followup = route.followup_discard
            if claimed != (followup is not None):
                raise ValueError("吃碰等待路线必须指定后续弃牌，其他普通等待不能指定")
            pre_hand = route.conditions.pre_draw_hand
            if followup in hands and hands[followup] != pre_hand:
                raise ValueError("同一后续弃牌的路线不能来自不同摸前手牌")
            hands[followup] = pre_hand
            used_codes = seen.setdefault(followup, set())
            winner_score = route.conditional_settlement.score_delta[seat]
            try:
                valid_score = type(winner_score) in (int, float) and math.isfinite(winner_score) and winner_score > 0
            except OverflowError:
                valid_score = False
            if not valid_score:
                raise ValueError("条件成胡中本人的净得分必须是正的有限数值")
            unseen = 0
            for useful in route.useful_tiles:
                if useful.code in used_codes:
                    raise ValueError("同一后续弃牌的有效牌不能跨路线重复计数")
                used_codes.add(useful.code)
                unseen += useful.remaining_estimate
            groups.setdefault(followup, []).append((unseen * winner_score, unseen))

        if not groups:
            # COMPLETE + 空路线是真实的范围内零值，区别于未计算。
            return _WaitingValue(0.0, 0, None)
        values = [
            _WaitingValue(float(sum(mass for mass, _ in parts)), sum(count for _, count in parts), followup)
            for followup, parts in groups.items()
        ]
        if any(not math.isfinite(value.score_mass) for value in values):
            raise ValueError("一次摸牌条件分值质量必须是有限数值")
        return min(values, key=lambda value: (
            -value.score_mass, -value.unseen_count,
            "" if value.followup_discard is None else "discard:" + value.followup_discard,
        ))

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """先生成完整 V2，再有界增强；增强失败沿用原计划并记录原因。

        V2 自身失败或过期仍抛出原错误，供应用层使用紧急动作；已经得到
        V2 之后的可选增强失败不丢弃这份可靠计划。任务取消始终向上传播。
        """

        baseline = await self._baseline.choose(request, budget)
        try:
            return await self._enhance(request, budget, baseline)
        except Exception as exc:
            # CancelledError 继承 BaseException，不会被此可选计算降级捕获。
            reason = "一次摸牌增强失败，沿用完整 V2 计划：{kind}：{message}".format(
                kind=type(exc).__name__, message=str(exc)[:240],
            )
            return replace(baseline, degraded_reasons=baseline.degraded_reasons + (reason,))

    async def _enhance(
        self, request: DecisionRequest, budget: DecisionBudget, baseline: DecisionPlan,
    ) -> DecisionPlan:
        """只调整已经完成的计划；异常由 choose 统一退回完整基线。"""

        if self._value_weight == 0 or not baseline.candidates:
            return baseline
        if isinstance(baseline.candidates[0].action, (Hu, Gang)):
            return baseline

        # 与 V2 的防御性过滤保持一致：只匹配其实际保留下来的规范动作，
        # 第一个有效重复项拥有事实，不让后来的重复项覆盖它。
        available: Dict[str, RuleCandidate] = {}
        for candidate in request.rules.legal_candidates:
            try:
                canonical = action_key(candidate.action)
            except TypeError:
                continue
            if canonical == candidate.action_key:
                available.setdefault(candidate.action_key, candidate)
        first = available.get(baseline.candidates[0].action_key)
        if first is None or not _normal_ready(first):
            return baseline

        values: Dict[str, _WaitingValue] = {}
        for ranked in baseline.candidates:
            candidate = available.get(ranked.action_key)
            if candidate is None:
                return baseline
            if not _normal_ready(candidate):
                continue
            await self._check_deadline(budget)
            value = await self._waiting_value(candidate, request.observation.seat, budget)
            if value is None:
                # 整个可比组需要完整覆盖，缺失不能成为低分并制造虚假优势。
                return baseline
            values[ranked.action_key] = value
        if len(values) < 2 or not any(value.score_mass > 0 for value in values.values()):
            return baseline

        result = list(baseline.candidates)
        # 杠动作保留原排名，左右两段的普通等待也不越过该位置。
        start = 0
        boundaries = [i for i, item in enumerate(result) if isinstance(item.action, Gang)]
        for end in boundaries + [len(result)]:
            positions = [i for i in range(start, end) if result[i].action_key in values]
            ordered = sorted((result[i] for i in positions), key=lambda item: (
                -values[item.action_key].score_mass,
                -values[item.action_key].unseen_count,
                item.action_key,
            ))
            for index, item in zip(positions, ordered):
                value = values[item.action_key]
                parts = item.score_parts + (
                    ScorePart("一次摸牌-抵消原 V2 组内总分", -sum(part.value for part in item.score_parts)),
                    ScorePart("一次摸牌-条件分值质量", value.score_mass),
                )
                followup = "；先弃" + value.followup_discard if value.followup_discard is not None else ""
                reasons = item.reasons + (
                    "本听牌组改用条件分值质量排序；原 V2 分项保留供对照，不参与本组排序",
                    "一次普通摸牌：未见 {count} 张，Σ(未见张数×本人条件净得分)={mass:g}{followup}；不是成胡概率或整单局期望".format(
                        count=value.unseen_count, mass=value.score_mass, followup=followup,
                    ),
                )
                result[index] = replace(item, rank=index + 1, total_score=sum(part.value for part in parts), score_parts=parts, reasons=reasons)
            start = end + 1
        await self._check_deadline(budget)
        return replace(baseline, candidates=tuple(result))
