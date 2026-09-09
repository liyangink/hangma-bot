"""V2 底座的有界等胡候选；单独验证升级增量，不带入一次摸牌排序。"""

from __future__ import annotations

import time
from typing import Callable, Tuple

from .heuristic_v2 import ComparableHeuristicPolicyV2
from .hu_upgrade import HuUpgradePolicy, UpgradeRiskCell
from .weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1


class V2HuUpgradePolicy(HuUpgradePolicy):
    """保留 V2 普通决策，只复用已验证的等胡比较和保持爆头等待。

    choose 的截止时间、规则证明、已拒动作、完整降级计划和评分审计
    全部继承同一实现；不会重新实现另一套等胡算法或修改冻结 V2。
    """

    def __init__(
        self, weights: HeuristicWeightsV1 = DEFAULT_WEIGHTS_V1,
        monotonic: Callable[[], float] = time.monotonic, *,
        risk_cells: Tuple[UpgradeRiskCell, ...] = (), risk_version: str = "unconfigured",
        safety_margin: float = 0.10, upgrade_weight: float = 1.0,
    ) -> None:
        """使用同一参数校验与增强器，明确选择 V2 作为本实例的保底底座。"""

        super().__init__(weights, monotonic, risk_cells=risk_cells, risk_version=risk_version,
                         safety_margin=safety_margin, upgrade_weight=upgrade_weight)
        # 只替换本实例的组合底座，旧 HuUpgradePolicy 实例及其冻结行为不变。
        self._baseline = ComparableHeuristicPolicyV2(weights, monotonic)
        self._baseline_name = "V2"
