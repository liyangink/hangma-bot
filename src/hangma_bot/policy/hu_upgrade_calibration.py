"""等胡候选的冻结模拟校准参数，由离线组合入口显式注入。

证据：review/hu-upgrade-2026-09-08/risk-table.json；512 个独立根桌赛，
764 个分支。分组须至少 50 个根、100 个机会；按根聚类重采样后，
生存比例向下取整、无条件支付向上取整，并加概率上限/支付下限。
仅适用于所列规则和 V2 模拟对手池；不是线上风险保证或正式运行预设。
"""

from .hu_upgrade import UpgradeRiskCell

RISK_RULESET_VERSION = "hangma-mvp-v5-four-white"
RISK_VERSION = "hu-upgrade-risk-v1"
RISK_CELLS = (
    UpgradeRiskCell(wall_band=1, threat=False, survival_floor=0.82, loss_ceiling=0.10),
    UpgradeRiskCell(wall_band=2, threat=False, survival_floor=0.89, loss_ceiling=0.10),
)
SAFETY_MARGIN = 0.10
