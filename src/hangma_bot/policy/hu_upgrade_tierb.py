"""概率档等胡（Tier-B）：把"下一摸必翻倍证明"放宽为一摸期望增益比较。

与 Tier-A（`hu_upgrade.py`）的**唯一差别**是"下一摸价值"的口径：

- Tier-A 要求规则证明"弃牌后任意普通摸均爆头成胡"，并取各互斥进张净分的**最小值**；
- Tier-B 不要求路线覆盖全部未见牌：按每个进张的**未见张数**加权累加条件结算净分，
  未命中进张按**零增益**计（保守），再除以剩余牌数得到下一摸的期望增益。

风险表、门槛（`survival_floor`、`loss_ceiling`、`safety_margin`）、截止时间检查、
响应窗口"保等待"分支与降级路径**完全沿用父类**，因此本档位的消融差异可归因到
价值口径这一处。仍未估计多步链、他家行为变化与牌墙顺序，也不预支多次飘的分值。
"""
from __future__ import annotations

import math
from typing import Optional

from hangma_bot.hangma.interface import RuleCandidate, ValueCoverage
from hangma_bot.kernel.observation import PlayerObservation

from .hu_upgrade import UpgradeRiskCell, upgrade_reason
from .v2_hu_upgrade import V2HuUpgradePolicy


class HuUpgradeTierBPolicy(V2HuUpgradePolicy):
    """概率档等胡：候选的下一摸期望增益超过立即胡与安全边际时，才把弃牌排在胡前。

    必须继承 V2HuUpgradePolicy 而不是 HuUpgradePolicy：后者的构造会把保底底座换成
    一次摸牌层（OneDrawValuePolicy），而 V2 档位使用 V2 底座。若误继承基类，Tier-B
    与 Tier-A 会同时出现底座不同与价值口径不同两处差异，消融无法归因（首版即踩此坑，
    由策略差分测量的理由文本不一致发现）。
    """

    VERSION = "v2_hu_upgrade_tierb_v1"

    def _next_draw_value(self, candidate: RuleCandidate, obs: PlayerObservation,
                         gain: float) -> Optional[float]:
        """未见张数加权的一摸期望增益；未命中按零增益，缺证据整条候选作废。

        分母用当前剩余牌数：`Σ(未见张数 × 条件净分) / 剩余牌数`。未见张数按本项目惯例
        包含可能在他家暗牌中的牌，因此该比值是**乐观上界**的命中率估计；与"未命中零增益"
        的保守项相抵，仍属条件估计而非真实概率保证。
        """

        facts = candidate.value_facts
        if (facts is None or facts.coverage is not ValueCoverage.COMPLETE
                or facts.immediate_settlement is not None or not facts.routes):
            return None
        wall = obs.remaining_tile_count
        if not isinstance(wall, int) or wall <= 0:
            return None
        mass = 0.0
        for route in facts.routes:
            if route.support != "conditional_witness" or route.shanten != 0:
                return None
            score = route.conditional_settlement.score_delta[obs.seat]
            if type(score) not in (int, float) or not math.isfinite(score) or score <= 0:
                return None
            for useful in route.useful_tiles:
                if useful.remaining_estimate > 0:
                    mass += useful.remaining_estimate * float(score)
        if mass <= 0:
            return None
        return mass / wall

    def _explain(self, cell: UpgradeRiskCell, gain: float, value: float) -> str:
        """概率档文案。必须复用基类的共享格式化器：本方法此前自行拼串，导致决策已用
        绝对支付而文案仍按倍数口径算分，审计复算会得到与代码不同的数值。"""

        return upgrade_reason(
            "有界等胡（概率档）：", self._risk_version, cell, gain, value,
            self._safety_margin, "下一摸期望增益（Σ未见×条件净分 / 剩余牌数，未命中按零增益）")
