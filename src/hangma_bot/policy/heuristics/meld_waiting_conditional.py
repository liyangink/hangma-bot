"""候选启发式②：鸣牌等待条件校准（**双向**，补 P-3 缺口）。

**为什么需要它**：候选①（`meld_opportunity_cost`）在 β > 0 时只能**降低**鸣牌排序，
结构上不可能产生"过→鸣牌"，因此不满足族定义 P-3 的"两侧均有改选"。
REVIEW-6 R6-2 明确要求：若要检验双向条件校准，**应允许正负调整**。本模块就是那个实例。

**机制**：以参考等待牌效为中心做**双向**条件校准——

`@text
delta = -k × (natural - ref) / ref        # natural 高于参考 ⇒ 扣分（少鸣）
                                          # natural 低于参考 ⇒ 加分（多鸣）
`@

与候选①的区别不只是符号：①是"整体抬高等待偏好"，②是"**以参考点为中心的两侧条件**"，
因此它能在同一批窗口上同时产生两个方向的改选。

**范围**：仍限吃碰（R6-3：明杠也补牌；暗杠/补杠是自摸窗口、无响应 Pass）。

**纯度（G-1）**：纯函数，只读规则给的候选事实；参数为不可变实例状态。
**有界**：由 `bound` 强制；适配器对越界**钳制并写审计**。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.kernel.actions import Chi, Peng

from ..evaluation_v1 import EvaluationContext
from ..heuristic_adapter import AdjustmentSpec, HeuristicAdjustment
from .meld_opportunity_cost import DEFAULT_SCOPE, natural_draw_value

WAITING_CONDITIONAL_VERSION = "meld-waiting-conditional-v1"

DEFAULT_REFERENCE = 21.0
DEFAULT_GAIN = 20.0
DEFAULT_BOUND = 300.0


@dataclass(frozen=True)
class WaitingConditionalParams:
    """不可变候选参数。

    gain：参考点处的斜率幅度（评分点）。正数表示"偏离参考越远、调整越大"。
    reference：等待有效牌剩余估计的**参考点**；高于是扣分、低于是加分。
    bound：单向幅度上限，由适配器强制。
    scope：受影响的动作类别，首版为吃与碰。
    """

    gain: float = DEFAULT_GAIN
    reference: float = DEFAULT_REFERENCE
    bound: float = DEFAULT_BOUND
    scope: Tuple[str, ...] = DEFAULT_SCOPE

    def __post_init__(self) -> None:
        for field_name in ("gain", "reference", "bound"):
            value = getattr(self, field_name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(
                    "WaitingConditionalParams.{0} 必须是有限数值".format(field_name))
        if self.reference <= 0:
            raise ValueError("WaitingConditionalParams.reference 必须为正")
        if self.bound <= 0:
            raise ValueError("WaitingConditionalParams.bound 必须为正")
        if abs(self.gain) > self.bound:
            raise ValueError("gain 的绝对值超过 bound，参数不自洽")
        if not self.scope:
            raise ValueError("WaitingConditionalParams.scope 不得为空")

    def to_json(self) -> str:
        return "gain={0},ref={1},bound={2},scope={3}".format(
            self.gain, self.reference, self.bound, "+".join(self.scope))


def conditional_delta(
    action, natural: Optional[int], params: WaitingConditionalParams
) -> float:
    """以参考点为中心的双向条件调整；等待的事实缺失时返回 0.0（不加不减）。"""

    if natural is None or natural <= 0:
        return 0.0
    if not isinstance(action, (Chi, Peng)):
        return 0.0
    deviation = (natural - params.reference) / params.reference
    raw = -params.gain * deviation
    return round(max(-params.bound, min(params.bound, raw)), 6)


def build_adjustment(
    params: WaitingConditionalParams = WaitingConditionalParams(),
    *,
    source_fingerprint_value: str = "",
) -> HeuristicAdjustment:
    """构造可直接交给适配器的候选调整。"""

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        del ctx
        return conditional_delta(candidate.action, natural_draw_value(candidates), params)

    spec = AdjustmentSpec(
        name="候选②-鸣牌等待条件校准",
        version=WAITING_CONDITIONAL_VERSION,
        thought=(
            "以参考等待牌效为中心做双向条件校准：等待牌效高于参考时少鸣、"
            "低于参考时多鸣。与候选①的单向惩罚不同，本式允许正负调整，"
            "因此同一批窗口上应同时出现两个方向的改选。"),
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
    """从声明参数构造候选；未给参数用默认值，未知键直接报错。"""

    known = {"gain", "reference", "bound", "scope"}
    unknown = set(params) - known
    if unknown:
        raise ValueError("候选②参数含未知键：{0}；可识别：{1}".format(
            sorted(unknown), sorted(known)))
    kwargs = {}
    for key in ("gain", "reference", "bound"):
        if key in params:
            kwargs[key] = float(params[key])
    if "scope" in params:
        parts = tuple(part for part in str(params["scope"]).split("+") if part)
        if not parts:
            raise ValueError("候选②参数 scope 解析为空")
        kwargs["scope"] = parts
    return build_adjustment(
        WaitingConditionalParams(**kwargs), source_fingerprint_value=source_fingerprint_value)


__all__ = [
    "DEFAULT_BOUND",
    "DEFAULT_GAIN",
    "DEFAULT_REFERENCE",
    "WAITING_CONDITIONAL_VERSION",
    "WaitingConditionalParams",
    "build_adjustment",
    "build_adjustment_from_params",
    "conditional_delta",
]
