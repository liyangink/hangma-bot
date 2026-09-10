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
# 方向 B：风险表 v3（庄闲分离 + 实测校准）
#
# 依据 review/auto-match-v10-2026-09-10/optimization-proposals.md 方向 B；
# 实测来自两池 27,824 个"我方弃牌后摸牌"样本（**真实平台**，不受本项目模拟器影响）：
#
#   墙余带   实测生存率(v10 我方)   实测失败均付 庄/闲   冻结 v2 表
#   40–63    83.7%（庄 84.9%）      10.75 / 4.78         floor 0.83 ✓、loss=0.10×胡分
#   >=64     96.8%（庄 96.5%）      9.59 / 4.62          floor 0.92（过保守 4.7pp）
#
# 三项修正：
# 1. **加 dealer 维**——支付结构不对称（庄胡 +24 番、庄输给闲 -8 番；闲胡 +10 番、
#    输给另一闲 -1 番），旧表把两种状态混在一起定价，对庄位大番场景失真 3 倍以上。
# 2. **band 2 生存下侧 0.92 -> 0.95**（实测 96.5–96.8%，留 >=1.5pp 边际）。
#    band 1 维持 0.83（实测 83.7%，已贴边，保守保留）。
# 3. **失败支付改绝对值**（分），替代 0.10×立即胡净分：庄 11.5 / 闲 5.2
#    （两带实测上侧的保守取值）。
#
# 不含 band 0（墙余 24–39）：实测生存率 67% 贴近 p>0.6 红线，明确"研究过并拒绝"。
#
# 【实测结论 2026-09-11】该表相对 v2 表**不改变任何决策**：差分 0 / 10,769 窗口
# （measure_policy_differential.py，32 根、前缀 gate）。把 loss_absolute 归零（比 v2
# 更宽松）后差异**仍然为 0**，因此不是数值标定问题，而是**风险参数根本不是瓶颈**：
# 上游 _next_draw_value（默认 _next_baotou_floor）先要求"能证明弃牌后任意下一摸必翻倍"，
# 不满足就直接 continue，风险表只在这之后的比较式里起作用。
# 这与 optimization-proposals.md §0-2 的判断一致（"单纯调表解放不了那 89% 的窗口"）。
# 保留 dealer 维与 loss_absolute 机制（类型安全、v2 表逐字兼容、有回归用例），供未来
# 若解锁可证明性后再定价；但**不要**再把该表当作独立候选上线。
RISK_VERSION_V3 = "hu-upgrade-risk-v3-dealer-v10"
RISK_CELLS_V3 = (
    UpgradeRiskCell(wall_band=1, threat=False, dealer=False, survival_floor=0.83,
                    loss_ceiling=0.10, loss_absolute=5.2),
    UpgradeRiskCell(wall_band=1, threat=False, dealer=True, survival_floor=0.83,
                    loss_ceiling=0.10, loss_absolute=11.5),
    UpgradeRiskCell(wall_band=2, threat=False, dealer=False, survival_floor=0.95,
                    loss_ceiling=0.10, loss_absolute=5.2),
    UpgradeRiskCell(wall_band=2, threat=False, dealer=True, survival_floor=0.95,
                    loss_ceiling=0.10, loss_absolute=11.5),
)
SAFETY_MARGIN_V3 = 0.10
