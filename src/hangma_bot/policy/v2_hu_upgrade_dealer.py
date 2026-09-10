"""庄位节奏变体：作为庄家时，用"更快听牌"的权重跑 V2 底座，其余座位完全沿用 V2 + 等胡。

依据（真实自由赛数据，见 review/.../README.md 的能力缺口语料）：

- 连庄长度由庄胜率决定：实测平均连庄 = 1/(1−庄胜率)（我方 1.36 对应 27.3%）；
- 庄位胡牌每番 24 分（闲家 10 分）且**赢则保庄**，因此"更快听牌"在庄位的边际价值约为闲位的 2.4 倍；
- 同伴（对手池）作为庄家时吃牌强度高于我方（509 vs 421 每千座位局），而我方庄胜率 27.3% 等于甚至低于自身闲胜率 28.0%。

本变体只改一处：**本人坐庄时降低吃碰的固定风险分并略增向听推进权重**，其余所有窗口
（含闲家窗口、等胡增强、响应窗口保等待、降级路径）与 Tier-A 完全一致，便于归因。
"""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable, Optional, Tuple

from .heuristic_v2 import ComparableHeuristicPolicyV2
from .hu_upgrade import UpgradeRiskCell
from .interface import DecisionBudget, DecisionPlan, DecisionRequest
from .v2_hu_upgrade import V2HuUpgradePolicy
from .weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1

# 庄位权重：吃碰固定风险归零（V2 的固定惩罚在庄位与"赢则保庄"的经济性相反）、
# 向听推进 +15%；其余权重逐项不变，便于把行为差异归因到庄位节奏。
# 强度按真实数据锚定：对手坐庄时吃牌 509/千座位局，我方仅 421/千座位局。
DEALER_WEIGHTS_V1 = replace(DEFAULT_WEIGHTS_V1, claim_risk_peng=0.0, claim_risk_chi=0.0,
                            shanten_step=115.0)


class V2HuUpgradeDealerPolicy(V2HuUpgradePolicy):
    """本人坐庄时用节奏偏置底座，其余座位与 Tier-A 逐字一致。"""

    VERSION = "v2_hu_upgrade_dealer_v1"

    def __init__(
        self, weights: HeuristicWeightsV1 = DEFAULT_WEIGHTS_V1,
        monotonic: Callable[[], float] = time.monotonic, *,
        risk_cells: Tuple[UpgradeRiskCell, ...] = (), risk_version: str = "unconfigured",
        safety_margin: float = 0.10, upgrade_weight: float = 1.0,
        dealer_weights: Optional[HeuristicWeightsV1] = None,
    ) -> None:
        super().__init__(weights, monotonic, risk_cells=risk_cells, risk_version=risk_version,
                         safety_margin=safety_margin, upgrade_weight=upgrade_weight)
        self._dealer_weights = dealer_weights or DEALER_WEIGHTS_V1
        # 另建一个庄位底座实例；不改动父类底座，也不在请求间共享可变状态。
        self._dealer_baseline = ComparableHeuristicPolicyV2(self._dealer_weights, monotonic)

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """庄位用节奏底座，其余走父类路径；增强与降级逻辑复用父类实现。"""

        observation = request.observation
        if observation.dealer_seat != observation.seat:
            return await super().choose(request, budget)
        baseline = await self._dealer_baseline.choose(request, budget)
        try:
            return await self._enhance(request, budget, baseline)
        except Exception as exc:  # 与父类同口径：增强失败保留完整底座计划
            return replace(baseline, degraded_reasons=baseline.degraded_reasons + (
                "庄位节奏增强失败，沿用完整{0}计划：{1}：{2}".format(
                    "V2(庄位权重)", type(exc).__name__, str(exc)[:240]),
            ))
