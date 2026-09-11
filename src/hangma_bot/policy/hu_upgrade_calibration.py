"""等胡候选的冻结模拟校准参数，由离线组合入口显式注入。

证据：review/v2-hu-upgrade-v10-2026-09-09/risk-table.json；512 个独立根桌赛，
729 个分支。分组须至少 50 个根、100 个机会；按根聚类重采样后，
生存比例向下取整、无条件支付向上取整，并加概率上限/支付下限。
仅适用于所列规则和 V2 模拟对手池；自由赛仅供显式实验，不是线上风险保证。
"""

from .hu_upgrade import UpgradeRiskCell

RISK_RULESET_VERSION = "hangma-mvp-v10-public-counts"
RISK_VERSION = "hu-upgrade-risk-v2-v10"
RISK_CELLS = (
    UpgradeRiskCell(wall_band=1, threat=False, survival_floor=0.83, loss_ceiling=0.10),
    UpgradeRiskCell(wall_band=2, threat=False, survival_floor=0.92, loss_ceiling=0.10),
)
SAFETY_MARGIN = 0.10

# ---------------------------------------------------------------------------
# 【已淘汰·保留结论】方向 B 风险表 v3（庄闲分离 + 实测校准）
#
# 2026-09-11 结论：该表相对 v2 表**不改变任何决策**（差分 0 / 10,769 窗口）。
# 把 loss_absolute 归零（比 v2 更宽松）后差异**仍然为 0** ⇒ 不是数值标定问题，
# 而是**风险参数根本不是瓶颈**：上游 `_next_draw_value`（默认 `_next_baotou_floor`）
# 先要求"能证明弃牌后任意下一摸必翻倍"，不满足就 continue；风险表只在之后的
# 比较式 `survival_floor × floor − loss > gain × (1 + margin)` 里起作用，
# 而 Tier-A 的 floor >= 2 × gain 使其**恒松弛**。这解释了它为什么是结构性空操作。
#
# ⇒ 风险表 v3、以及依赖它的两个实验臂（risk_v3 / tierb_v3）已移出可用策略清单。
# `UpgradeRiskCell` 的 `dealer` 与 `loss_absolute` 扩展点保留（类型安全、v2 表
# 逐字兼容、有回归用例 test_hu_upgrade_risk_extension.py），供**先解锁可证明性**
# 之后再定价；顺序反过来的话，调表永远是空操作。
#
# 实测数据留档（真实平台两池 27,824 个"我方弃牌后摸牌"样本，不受本项目模拟器影响）：
#
#   墙余带   实测生存率(v10 我方)   实测失败均付 庄/闲   冻结 v2 表
#   40–63    83.7%（庄 84.9%）      10.75 / 4.78         floor 0.83 ✓、loss=0.10×胡分
#   >=64     96.8%（庄 96.5%）      9.59 / 4.62          floor 0.92（过保守 4.7pp）
#
# 不含 band 0（墙余 24–39）：实测生存率 67% 贴近 p>0.6 红线，明确"研究过并拒绝"。
