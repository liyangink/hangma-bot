"""有界等胡升级候选：用离线校准的等待风险比较立即胡与下一次爆头。

分值和爆头证明完全来自 RuleAnalysis；此模块不计算牌型或预测牌墙。
风险表只针对其记录的模拟对手池，不是官方规则或真实对手的概率保证。
默认空表拒绝放弃立即胡；离线组合入口须显式注入经过校准的表。
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, replace
from typing import Callable, Optional, Tuple

from hangma_bot.hangma.interface import RuleCandidate, RuleCompleteness, ValueCoverage
from hangma_bot.kernel.actions import Discard, Hu, Pass, action_key
from hangma_bot.kernel.observation import PlayerObservation

from .errors import PolicyTimeoutError
from .interface import DecisionBudget, DecisionPlan, DecisionRequest, ScorePart
from .value_one_draw import OneDrawValuePolicy
from .weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1


@dataclass(frozen=True)
class UpgradeRiskCell:
    """一种可见局面的等待风险；概率与损失均为保守校准估计。

    wall_band：0=余牌 24—39，1=40—63，2=64 以上（均包含保留区）。
    threat：有对手最后一弃为白，或已有至少三副公开副露时为 True。
    survival_floor 是活到下一次本人摸牌并能胡的比例下侧估计；
    loss_ceiling 是等待失败造成的无条件平均支付上侧估计，单位为
    当前立即胡的本人净得分倍数，已经包含失败频率，不再次乘失败率。
    """

    wall_band: int
    threat: bool
    survival_floor: float
    loss_ceiling: float

    def __post_init__(self) -> None:
        if type(self.wall_band) is not int or self.wall_band not in (0, 1, 2):
            raise ValueError("wall_band 必须是 0、1 或 2")
        if type(self.threat) is not bool:
            raise ValueError("threat 必须是布尔值")
        for name, value in (("survival_floor", self.survival_floor), ("loss_ceiling", self.loss_ceiling)):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(name + " 必须是非负有限数")
        if self.survival_floor > 1:
            raise ValueError("survival_floor 不能超过 1")


def upgrade_risk_key(observation: PlayerObservation) -> Optional[Tuple[int, bool]]:
    """仅提取当前可见风险分组；未知余牌或观察异常不推断为低风险。

    离线校准与策略共用特征，避免训练/消费分组漂移；不要求事件历史
    完整，因为本组只读取当前权威快照的牌河、副露和剩余牌数。
    """

    wall = observation.remaining_tile_count
    if wall is None or wall < 24 or observation.observation_issues:
        return None
    band = 0 if wall < 40 else 1 if wall < 64 else 2
    opponents = [seat for seat in range(4) if seat != observation.seat]
    threat = any(
        len(observation.melds[seat]) >= 3 or
        bool(observation.discards[seat] and observation.discards[seat][-1].code == "白")
        for seat in opponents
    )
    return band, threat


def _next_baotou_floor(candidate: RuleCandidate, seat: int) -> Optional[float]:
    """读取完整普通摸牌爆头证明，并取所有互斥进张中最低的本人净分。

    普通摸牌的 baotou 条件来自规则模块对摸前手牌的任意进张检查。
    因而不把“若干有效牌”误当作必胡，也不使用未见张数推断概率。
    """

    facts = candidate.value_facts
    if (facts is None or facts.coverage is not ValueCoverage.COMPLETE or
            facts.immediate_settlement is not None or not facts.routes):
        return None
    conditions = facts.routes[0].conditions
    if conditions.draw_kind != "normal" or not conditions.baotou:
        return None
    seen = set()
    scores = []
    for route in facts.routes:
        if (route.conditions != conditions or route.followup_discard is not None or
                route.support != "conditional_witness" or route.shanten != 0):
            return None
        score = route.conditional_settlement.score_delta[seat]
        if type(score) not in (int, float) or not math.isfinite(score) or score <= 0:
            return None
        for useful in route.useful_tiles:
            if useful.code in seen or useful.remaining_estimate <= 0:
                return None
            seen.add(useful.code)
        scores.append(float(score))
    return min(scores) if seen else None


class HuUpgradePolicy:
    """先取得完整一次摸牌基线，再有界比较下一次自摸升级。

    只把规则已证明“下次普通摸任意可见未耗尽牌均爆头”的弃牌提到 Hu
    前面，并要求保守分值估计超过立即胡及 safety_margin。响应窗口
    保留已有爆头等待，防止吃碰改变估值所依赖的摸前手牌。下一摸重新
    决策；再次飘白是另一次有界比较，不预先兑现多次飘的分值。
    """

    def __init__(
        self, weights: HeuristicWeightsV1 = DEFAULT_WEIGHTS_V1,
        monotonic: Callable[[], float] = time.monotonic, *,
        risk_cells: Tuple[UpgradeRiskCell, ...] = (), risk_version: str = "unconfigured",
        safety_margin: float = 0.10, upgrade_weight: float = 1.0,
    ) -> None:
        """由组合入口注入不可变校准表；策略本身不读取文件或其他座位暗牌。"""

        if type(upgrade_weight) not in (int, float) or upgrade_weight not in (0, 1):
            raise ValueError("upgrade_weight 只允许 0 或 1")
        if type(safety_margin) not in (int, float) or not math.isfinite(safety_margin) or safety_margin < 0:
            raise ValueError("safety_margin 必须是非负有限数")
        if not isinstance(risk_cells, tuple) or any(not isinstance(cell, UpgradeRiskCell) for cell in risk_cells):
            raise ValueError("risk_cells 必须是 UpgradeRiskCell 元组")
        if len({(cell.wall_band, cell.threat) for cell in risk_cells}) != len(risk_cells):
            raise ValueError("risk_cells 不能包含重复分组")
        if not isinstance(risk_version, str) or not risk_version:
            raise ValueError("risk_version 必须是非空字符串")
        self._weights = weights
        self._monotonic = monotonic
        self._risk_cells = risk_cells
        self._risk_version = risk_version
        self._safety_margin = safety_margin
        self._upgrade_weight = upgrade_weight
        self._baseline = OneDrawValuePolicy(weights, monotonic)

    async def _check_deadline(self, budget: DecisionBudget) -> None:
        await asyncio.sleep(0)
        if self._monotonic() > budget.enhancement_deadline_monotonic:
            raise PolicyTimeoutError("等胡升级超过增强截止时间")

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """增强缺失/失败保留完整基线；取消向上传播；所有候选仍由规则提供。"""

        baseline = await self._baseline.choose(request, budget)
        try:
            return await self._enhance(request, budget, baseline)
        except Exception as exc:
            return replace(baseline, degraded_reasons=baseline.degraded_reasons + (
                "等胡升级失败，沿用完整一次摸牌计划：{0}：{1}".format(type(exc).__name__, str(exc)[:240]),
            ))

    async def _enhance(self, request: DecisionRequest, budget: DecisionBudget, baseline: DecisionPlan) -> DecisionPlan:
        if (not self._upgrade_weight or not self._risk_cells or not baseline.candidates or
                request.rules.completeness is not RuleCompleteness.COMPLETE):
            return baseline
        await self._check_deadline(budget)
        available = {}
        for candidate in request.rules.legal_candidates:
            try:
                if action_key(candidate.action) == candidate.action_key:
                    available.setdefault(candidate.action_key, candidate)
            except TypeError:
                continue
        obs = request.observation
        selected = None
        explanation = None
        parts = ()
        if obs.phase in ("response_peng", "response_chi") and obs.rule_state.baotou:
            # 续打模型以保持当前等待为条件；声明的 Pass 必须仍合法且未被拒。
            for item in baseline.candidates:
                candidate = available.get(item.action_key)
                if candidate is not None and isinstance(item.action, Pass):
                    if _next_baotou_floor(candidate, obs.seat) is not None:
                        selected = item
                        explanation = "已有爆头等待，过牌保持摸前手牌，使下一摸分值的前提继续成立"
                    break
        elif isinstance(baseline.candidates[0].action, Hu):
            if obs.phase != "draw" or obs.drawn_tile is None:
                return baseline
            key = upgrade_risk_key(obs)
            cell = next((cell for cell in self._risk_cells if (cell.wall_band, cell.threat) == key), None)
            hu = available.get(baseline.candidates[0].action_key)
            if cell is None or hu is None or hu.value_facts is None:
                return baseline
            facts = hu.value_facts
            if facts.coverage is not ValueCoverage.COMPLETE or facts.immediate_settlement is None:
                return baseline
            gain = facts.immediate_settlement.score_delta[obs.seat]
            if type(gain) not in (int, float) or not math.isfinite(gain) or gain <= 0:
                return baseline
            offers = []
            for item in baseline.candidates:
                await self._check_deadline(budget)
                candidate = available.get(item.action_key)
                if candidate is None or not isinstance(item.action, Discard):
                    continue
                floor = _next_baotou_floor(candidate, obs.seat)
                if floor is None or floor <= gain:
                    continue
                conservative = cell.survival_floor * floor - cell.loss_ceiling * gain
                if conservative > gain * (1 + self._safety_margin):
                    offers.append((conservative, floor, item))
            if offers:
                conservative, floor, selected = min(offers, key=lambda offer: (-offer[0], -offer[1], offer[2].action_key))
                parts = (
                    ScorePart("等胡升级-成功分值估计", cell.survival_floor * floor),
                    ScorePart("等胡升级-失败支付估计", -cell.loss_ceiling * gain),
                )
                explanation = (
                    "有界等胡：立即胡 {gain:g}，下一次普通摸牌的最低净分 {floor:g}；"
                    "校准表 {version} 分组 {band}/{threat}：生存下侧估计 {survival:.4f}，"
                    "无条件支付上侧估计 {loss:.4f}×当前胡分，保守分值 {value:g} > 门槛 {threshold:g}；"
                    "只估计下一摸，不是整单局保证"
                ).format(gain=gain, floor=floor, version=self._risk_version, band=cell.wall_band,
                         threat=int(cell.threat), survival=cell.survival_floor, loss=cell.loss_ceiling,
                         value=conservative, threshold=gain * (1 + self._safety_margin))
        if selected is None:
            return baseline
        result = [selected] + [item for item in baseline.candidates if item.action_key != selected.action_key]
        if parts:
            parts = selected.score_parts + (
                ScorePart("等胡升级-抵消基线总分", -sum(part.value for part in selected.score_parts)),
            ) + parts
            result[0] = replace(selected, score_parts=parts, total_score=sum(part.value for part in parts))
        result[0] = replace(result[0], reasons=result[0].reasons + (explanation,))
        await self._check_deadline(budget)
        return replace(baseline, candidates=tuple(replace(item, rank=index + 1) for index, item in enumerate(result)))
