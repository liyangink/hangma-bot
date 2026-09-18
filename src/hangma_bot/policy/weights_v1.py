"""V1 独立权重；从 V0 冻结值复制，校验不改变旧版配置行为。

权重只决定层内评分；合法胡牌/可信/未知的优先层独立于数值大小。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace


@dataclass(frozen=True)
class HeuristicWeightsV1:
    """分层评分权重；所有字段单位都是分，只影响排序，不影响合法性。"""

    win_now: float = 1000.0  # 第一层：规则确认可胡时的立即胡牌加分
    gang_bonus: float = 40.0  # 第二层：杠动作的固定收益（番值潜力，保守取小）
    wealth_god_keep: float = 60.0  # 第二层：打出财神的惩罚（放弃万能牌并触发抓打圈）
    shanten_step: float = 100.0  # 第三层：向听数每差一步的分值
    effective_tile: float = 1.0  # 第四层：每单位加权有效牌的分值（规则事实口径）
    win_potential: float = 5.0  # 第四层：动作后每保留一张财神的成牌收益分
    flexibility: float = 2.0  # 保留字段：CandidateFacts 不携带结构分解，评分暂不使用
    claim_risk_peng: float = 6.0  # 第六层：碰牌暴露信息与节奏的固定风险分
    claim_risk_chi: float = 10.0  # 第六层：吃牌固定风险分（仅上家可吃，随后须弃牌）
    feed_risk: float = 6.0  # 第六层：弃牌喂牌风险每单位分值
    safe_tile_bonus: float = 3.0  # 第六层：熟张（已见于他家牌河）的安全加分
    style_adjust: float = 4.0  # 第七层：名次风格调整的最大幅度

    def __post_init__(self) -> None:
        """拒绝非有限权重；非法配置不进入线上评分或审计 JSON。"""

        for field in fields(self):
            value = getattr(self, field.name)
            try:
                valid = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("V1 权重 {0} 必须是有限数值".format(field.name))


DEFAULT_WEIGHTS_V1 = HeuristicWeightsV1()

#: 2026-09-18 新参数批次（策略 `v2_hu_upgrade_v2`）的权重集。
#:
#: **当前批次内容：`safe_tile_bonus` 3.0 → 0.0（只此一项）**。
#: 依据：本赛制只能自摸、无放铳，「熟张安全」收益恒 0，却压过进张宽度——
#: 2026-09-17 全场 86.7% 的同向听选择偏窄进张都带着这一层加分；离线重放该项归零改变 129 个窗口。
#:
#: 标定纪律：**一次只改一个参数、单独提交**，并通过策略目录门禁后才更新本行，不得混批。
#: 每个参数的差异都必须同步 tests/unit/policy/test_v2_param_batch.py 的 `_TUNED_FIELDS`——
#: 那条断言会强制你把改动写明白，防止悄悄改数。
#: 候选取值与扫描协议见 review/test-tournament-20260917/policy-param-batch-spec-2026-09-18.md。
V2_PARAM_BATCH_WEIGHTS = replace(DEFAULT_WEIGHTS_V1, safe_tile_bonus=0.0)
