"""候选启发式①：鸣牌机会成本（机制族 M4，接缝的第一个实例）。

**命题（按 REVIEW-6 R6-1 更正）**：V2 已经用可比牌效给 `Pass` 评分
（`-shanten_step × 向听 + effective_tile × 有效牌剩余`，默认 100 / 1.0）。
本候选研究的**不是**"补上完全缺失的等待价值"，而是：
**在 V2 已有可比牌效的基础上，吃碰的统一偏置是否需要按等待牌效作条件校准。**

因此本项与 V2 既有项**共线**——`natural` 就是 V2 `Pass` 分项里那个
`Σ remaining_estimate`。β 直接表示"把鸣牌-vs-Pass 的有效牌系数抬高多少"：

    β = 20  ⇔  有效牌系数 1.0 → 1.0 + 20/21 ≈ 1.95（约翻倍）

**这是一项有界重加权，不是新增事实维度。** 解释结果时必须这样说。

**范围（按 REVIEW-6 R6-3 收窄）**：只作用 `chi` 与 `peng`。三类杠语义不同——
明杠也会补牌，自摸暗杠与补杠是**自摸窗口、没有响应 `Pass`**，
"放弃一次摸牌"对它们不成立。杠的补牌前后与"不杠退路"另行定义后再纳入。

**方向（按 REVIEW-6 R6-2）**：本式在 β > 0 时**只能降低**鸣牌排序，
结构上不可能让原本首选 `Pass` 的窗口改选鸣牌 ⇒ 它是**单向增加等待偏好**的
对照候选，不满足族定义里"两侧均有改选"的 P-3 描述。双向条件校准需要另写实例。

**纯度（G-1）**：`delta` 是纯函数——只读规则给的候选事实，不读时间/随机/文件，
不做搜索，不重算向听，不判断合法性。参数是**构造时固定的不可变实例状态**。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    RuleCandidate,
    RuleCompleteness,
)
from hangma_bot.kernel.actions import Chi, Pass, Peng

from ..evaluation_v1 import EvaluationContext
from ..evaluation_v2 import has_waiting_baseline
from ..heuristic_adapter import AdjustmentSpec, HeuristicAdjustment

MELD_COST_VERSION = "meld-opportunity-cost-v1"

# 影响面类别名。与适配器的 scope 口径一致（见 AdjustmentSpec）。
DEFAULT_SCOPE: Tuple[str, ...] = ("chi", "peng")

# 等待有效牌剩余估计的参考值：用于归一化，使 β 的含义是"参考收益下的鸣牌代价点数"
# （单位是启发式**评分点**，不是桌赛积分），可直接与分差比较。
DEFAULT_NATURAL_REF = 21.0
DEFAULT_BOUND = 300.0


@dataclass(frozen=True)
class MeldCostParams:
    """不可变候选参数；随实例固定，不随调用变化（REVIEW-6 S6-2 的要求）。

    beta：机会成本幅度，单位是评分点。beta <= 0 表示不改变行为（仅作对照）。
    natural_ref：等待有效牌剩余估计的参考值。
    bound：追加项幅度上限；适配器据此钳制并留审计。
    scope：受影响的动作类别，首版为吃与碰。
    """

    beta: float = 0.25
    natural_ref: float = DEFAULT_NATURAL_REF
    bound: float = DEFAULT_BOUND
    scope: Tuple[str, ...] = DEFAULT_SCOPE

    def __post_init__(self) -> None:
        for field_name in ("beta", "natural_ref", "bound"):
            value = getattr(self, field_name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("MeldCostParams.{0} 必须是有限数值".format(field_name))
        if self.natural_ref <= 0:
            raise ValueError("MeldCostParams.natural_ref 必须为正")
        if self.bound <= 0:
            raise ValueError("MeldCostParams.bound 必须为正")
        if not self.scope:
            raise ValueError("MeldCostParams.scope 不得为空")
        if self.beta < 0 and abs(self.beta) > self.bound:
            raise ValueError("beta 为负且绝对值超过 bound，参数不自洽")

    def to_json(self) -> str:
        """稳定序列化；进候选身份，使产物可复现到具体参数。"""

        return "beta={0},ref={1},bound={2},scope={3}".format(
            self.beta, self.natural_ref, self.bound, "+".join(self.scope))

    def effective_tile_multiplier(self, effective_tile: float = 1.0) -> float:
        """参考收益处，鸣牌-vs-Pass 的等效有效牌系数；用于向读者说明 β 的真实含义。"""

        return effective_tile + self.beta / self.natural_ref


def natural_draw_value(candidates: Sequence[RuleCandidate]) -> Optional[int]:
    """本手牌的**等待有效牌剩余估计**：`Pass` 候选的 `remaining_estimate` 之和。

    事实缺失、不完整或非 HAND_PROGRESS 时返回 None（**按未知处理，不填 0**——
    填 0 会假装"摸牌没有价值"并放大鸣牌）。

    口径：这是**未见有效牌张数估计**，不是摸到概率、不是轮到我方前的存活概率、
    也不是未来和牌价值或支付风险。函数名保留历史，语义以本 docstring 为准。
    """

    for candidate in candidates:
        if not isinstance(candidate.action, Pass):
            continue
        facts = candidate.facts
        if facts is None or facts.completeness is not RuleCompleteness.COMPLETE:
            continue
        if facts.fact_kind is not CandidateFactKind.HAND_PROGRESS:
            continue
        if not has_waiting_baseline(candidate):
            continue
        return sum(item.remaining_estimate for item in facts.useful_tiles)
    return None


def opportunity_cost(action, natural: Optional[int], params: MeldCostParams) -> float:
    """鸣牌的机会成本（非正数）：等待牌效越高，鸣牌越贵。

    `natural` 为空或 <= 0 时返回 0.0——**不加不减**，退回基线行为，
    而不是猜一个方向。
    """

    if natural is None or natural <= 0:
        return 0.0
    if not isinstance(action, (Chi, Peng)):
        return 0.0
    scale = natural / params.natural_ref
    raw = params.beta * scale
    return round(-min(raw, params.bound), 6)


def build_adjustment(
    params: MeldCostParams = MeldCostParams(),
    *,
    source_fingerprint_value: str = "",
) -> HeuristicAdjustment:
    """构造可直接交给适配器的候选调整。

    `source_fingerprint_value` 由**装载方**传入（policy 包不做文件 IO）；
    缺省为空表示未计算，候选身份里会省略该段而不是填占位符。
    """

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        # 纯函数：只用规则给的候选事实，不用 ctx 中的任何可变状态。
        del ctx
        return opportunity_cost(candidate.action, natural_draw_value(candidates), params)

    spec = AdjustmentSpec(
        name="候选①-鸣牌机会成本",
        version=MELD_COST_VERSION,
        thought=(
            "在 V2 已有可比牌效之上，按等待有效牌剩余估计对吃碰做有界重加权："
            "等待牌效越高，鸣牌越贵。与 V2 既有项共线，β 即抬高有效牌系数的幅度。"),
        trigger="窗口内存在带完整等待事实的 Pass 候选，且候选为吃或碰",
        scope=params.scope,
        bound=params.bound,
    )
    return HeuristicAdjustment(
        spec, delta,
        source_fingerprint_value=source_fingerprint_value,
        params_json=params.to_json(),
    )


def build_adjustment_from_params(
    params: Mapping[str, float], source_fingerprint_value: str = ""
) -> HeuristicAdjustment:
    """从声明参数构造候选；未给的参数用默认值。

    可识别键：`beta` / `natural_ref` / `bound` / `scope`
    （`scope` 用 `+` 连接，如 `chi+peng`）。未知键直接报错，
    避免"参数写错却静默用默认值"。
    """

    known = {"beta", "natural_ref", "bound", "scope"}
    unknown = set(params) - known
    if unknown:
        raise ValueError("候选参数含未知键：{0}；可识别：{1}".format(
            sorted(unknown), sorted(known)))
    kwargs = {}
    for key in ("beta", "natural_ref", "bound"):
        if key in params:
            kwargs[key] = float(params[key])
    if "scope" in params:
        raw_scope = params["scope"]
        parts = tuple(part for part in str(raw_scope).split("+") if part)
        if not parts:
            raise ValueError("候选参数 scope 解析为空")
        kwargs["scope"] = parts
    return build_adjustment(
        MeldCostParams(**kwargs), source_fingerprint_value=source_fingerprint_value)


__all__ = [
    "DEFAULT_BOUND",
    "DEFAULT_NATURAL_REF",
    "DEFAULT_SCOPE",
    "MELD_COST_VERSION",
    "MeldCostParams",
    "build_adjustment",
    "build_adjustment_from_params",
    "natural_draw_value",
    "opportunity_cost",
]
