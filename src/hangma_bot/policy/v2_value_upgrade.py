"""一摸价值层 + 有界等胡的组合候选：把两条各自"点估计为正、区间未确认"的机制合并。

两条机制的既有证据（均为主仓离线评估，V2 对手）：

- **一次摸牌分值**（`one_draw_value_v1`，2026-09-08 独立确认）：512 对桌赛，
  候选减基线每桌 **+3.859**，95% 区间 [−1.805, +10.031]；独占第一率 **+7.81pp**，
  区间 [−0.78, +16.41]pp —— 点估计为正、区间含 0，未切换默认。
- **有界等胡**（`v2_hu_upgrade_v1`，现行自由赛实验版）：夜间真实战役 127 个弃胡窗口
  净增 +1,914 分（+4.1/场），29 个 ×4+ 大番中 27 个由该路径产出。

**两者从未组合**：现行实验版的底座是纯 V2（`V2HuUpgradePolicy` 把底座换成
`ComparableHeuristicPolicyV2`），价值层只存在于 `OneDrawValuePolicy` 与本文档的底座里。
本候选即"底座 = 一次摸牌价值层（V2 权重 + 听牌弃牌按 Σ未见×条件净分比价）+ Tier-A 有界等胡"，
用于回答：把"同一听牌距离下的分值选择"与"已可胡时的一次升级"叠加，收益是否相加。

风险与边界：价值层的听牌比价以未见张数估计命中，未建多步生存模型；等胡门槛沿用同一
风险表；全部候选仍由规则模块提供，紧急动作、截止时间、降级路径与既有实现一致。
"""
from __future__ import annotations

import time
from typing import Callable, Tuple

from .hu_upgrade import HuUpgradePolicy, UpgradeRiskCell
from .weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1


class V2ValueUpgradePolicy(HuUpgradePolicy):
    """底座保留一次摸牌价值层，再叠加有界等胡升级（与现行实验版的唯一差别）。"""

    VERSION = "v2_value_upgrade_v1"

    def __init__(
        self, weights: HeuristicWeightsV1 = DEFAULT_WEIGHTS_V1,
        monotonic: Callable[[], float] = time.monotonic, *,
        risk_cells: Tuple[UpgradeRiskCell, ...] = (), risk_version: str = "unconfigured",
        safety_margin: float = 0.10, upgrade_weight: float = 1.0,
    ) -> None:
        super().__init__(weights, monotonic, risk_cells=risk_cells, risk_version=risk_version,
                         safety_margin=safety_margin, upgrade_weight=upgrade_weight)
        # 父类底座即 OneDrawValuePolicy（一次摸牌价值层）；此处只改名以便审计区分，
        # 不替换、不包装，确保与 HuUpgradePolicy 的行为逐字一致。
        self._baseline_name = "一次摸牌价值层"
