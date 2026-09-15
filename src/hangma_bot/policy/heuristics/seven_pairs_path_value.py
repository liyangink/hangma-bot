"""价值族（Value-Path Family）第一个基线实例：**七对路径保护**。

## 为什么它属于「价值族」，而不是「动作族」

- **动作族**问：这个动作（吃/碰/杠）该加多少分？——**按动作标签**分档。
- **价值族**问：这条决策把**官方番型表的哪条倍率路径**打掉了？——**按状态变化**分档。

本实例只看一件事：**动作之后，七对这条路径还活着吗**。
官方原文《1.2 胡牌判定》明写「**七对子：禁止吃碰明杠暗杠**」——所以任何副露都会
**永久关闭**七对路径；而结算里七对 **×2**、豪华七对 1/2/3 组 **×4/×8/×16**。

## 为什么它是**安全**的（potential-based）

Ng/Harada/Russell 1999 要求塑形写成 `F(s,a,s') = γΦ(s') − Φ(s)`，γ=1 时退化为
`Φ(s') − Φ(s)`。本实例取

```text
Φ(s) = −(path_log2 + closer_bonus·1[七对是更近路径]) × 1[七对路径在 s 存活]
term(action) = Φ(s') − Φ(s)
```

- `Φ(s)` 里的 `1[七对路径在 s 存活]` 由 **s 本身**决定，与"这是吃还是碰"**无关**；
- 因此 `term` 是**同一个状态势的差**，而不是"给吃加 −X、给碰加 −Y"这类**动作标签加分**。

**与 M4（鸣牌机会成本）的关键区别**：M4 把"过牌那边的等待牌效"`−f(s)` 只加给吃碰候选，
同一状态内不同动作被加了不同的数 ⇒ **它的 argmax 可以改变**，按 Ng 的必要性，
存在使最优策略变差的 T、R。本实例不存在这个问题。

## 与 V2 的关系（为什么这里有头部空间）

`hand_analysis.py:121` 把向听取成 `min(普通型, 七对)`，主评分器**只用这个合成值**，
于是"七对"和"普通型"被当成**可互换**。一次碰若让合成向听不变（普通型追平七对），
V2 会认为"没有损失"而照碰——但它已经把那条 ×2 起（最高 ×16）的路径关掉了。

## 纯度

纯函数；只读规则给的候选事实与不可变参数实例。事实缺失/不完整/WIN 一律返回 0.0
（**不猜**；术语表要求"空与 0 必须区分"）。
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

from ..evaluation_v1 import EvaluationContext
from ..heuristic_adapter import AdjustmentSpec, HeuristicAdjustment

SEVEN_PAIRS_PATH_VERSION = "seven-pairs-path-value-v1"

# 官方番型表：七对 ×2 ⇒ log2 = 1。**这是规则常量，不是调参结果。**
SEVEN_PAIRS_BRANCH_LOG2 = 1.0

# 作用面：**全部动作类别**。这不是"想影响所有动作"，而是安全性的要求——
# 只有当分档依据是**状态变化**（而状态变化可以发生在任何动作上）时，
# 塑形才是同一个状态势的差。用动作类别去卡会退化成动作标签加分。
ALL_KINDS: Tuple[str, ...] = ("chi", "peng", "gang", "discard", "pass", "hu")


@dataclass(frozen=True)
class SevenPairsPathParams:
    """不可变参数实例。

    path_log2：七对分支的 log2 倍率，**由官方番型表确定 = 1.0**；保留为字段只为可审计。
    closer_bonus：当七对是**更近**的路径时额外计入的权重（豪华七对最高 ×16 ⇒ log2 4）。
    bound：幅度上限，由适配器强制。
    """

    path_log2: float = SEVEN_PAIRS_BRANCH_LOG2
    closer_bonus: float = 1.0
    bound: float = 300.0
    scope: Tuple[str, ...] = ALL_KINDS

    def __post_init__(self) -> None:
        for field_name in ("path_log2", "closer_bonus", "bound"):
            value = getattr(self, field_name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(
                    "SevenPairsPathParams.{0} 必须是有限数值".format(field_name))
        if self.path_log2 < 0 or self.closer_bonus < 0:
            raise ValueError("path_log2 与 closer_bonus 必须非负")
        if self.bound <= 0:
            raise ValueError("SevenPairsPathParams.bound 必须为正")

    def to_json(self) -> str:
        return "path_log2={0},closer_bonus={1},bound={2}".format(
            self.path_log2, self.closer_bonus, self.bound)


def _seven_pairs_state(candidate: RuleCandidate):
    """返回 (路径是否存活, 七对向听, 普通型向听)；事实不可用时返回 None。

    术语表口径：`seven_pairs_shanten_after` 为 `None` 表示**不适用或未分析**，
    **不能当 0**。本函数把它解释为"路径不存活"，并且只在事实完整时给出结论。
    """

    facts = candidate.facts
    if facts is None or facts.completeness is not RuleCompleteness.COMPLETE:
        return None
    if facts.fact_kind is CandidateFactKind.WIN:
        return None          # 已胡牌：路径已兑现，不是"被打掉"
    if facts.fact_kind is not CandidateFactKind.HAND_PROGRESS:
        return None
    seven = facts.seven_pairs_shanten_after
    standard = facts.standard_shanten_after
    return (seven is not None, seven, standard)


def path_term(action_candidate: RuleCandidate, before_candidate: RuleCandidate,
              params: SevenPairsPathParams) -> float:
    """`Φ(s') − Φ(s)`：动作把一条存活的七对路径打掉时，扣它的 log2 价值。"""

    before = _seven_pairs_state(before_candidate)
    after = _seven_pairs_state(action_candidate)
    if before is None or after is None:
        return 0.0                       # 事实不可用：不加不减，不猜
    live_before, seven_before, standard_before = before
    live_after = after[0]
    if not live_before or live_after:
        return 0.0                       # 本来就没路径，或路径没被打掉
    closer = (seven_before is not None and standard_before is not None
              and seven_before < standard_before)
    value = params.path_log2 + (params.closer_bonus if closer else 0.0)
    return round(-min(value, params.bound), 6)


def build_adjustment(
    params: SevenPairsPathParams = SevenPairsPathParams(),
    *,
    source_fingerprint_value: str = "",
) -> HeuristicAdjustment:
    """构造可直接交给适配器的候选调整。"""

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        del ctx
        # `s` 用窗口里的"过牌候选"代表（手牌不动）。没有过牌候选时无法确定
        # 动作前状态，按未知处理返回 0.0。
        before = next((c for c in candidates if c.action_key == "pass"), None)
        if before is None:
            return 0.0
        return path_term(candidate, before, params)

    spec = AdjustmentSpec(
        name="价值族①-七对路径保护",
        version=SEVEN_PAIRS_PATH_VERSION,
        thought=(
            "按官方番型路径而非动作类别打分：七对禁止任何副露，因此一次吃碰会永久关闭"
            "一条 ×2 起（豪华最高 ×16）的路径。本项在动作打掉该路径时扣它的 log2 价值，"
            "并按'七对是否本来更近'加权。写成状态势之差，故不改变最优策略。"),
        trigger="窗口内存在过牌候选；该候选的七对路径存活；被评候选会把该路径打掉",
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
    """从声明参数构造候选；未知键直接报错，避免写错却静默用默认值。"""

    known = {"path_log2", "closer_bonus", "bound"}
    unknown = set(params) - known
    if unknown:
        raise ValueError("价值族①参数含未知键：{0}；可识别：{1}".format(
            sorted(unknown), sorted(known)))
    kwargs = {key: float(params[key]) for key in known if key in params}
    return build_adjustment(
        SevenPairsPathParams(**kwargs), source_fingerprint_value=source_fingerprint_value)


__all__ = [
    "ALL_KINDS",
    "SEVEN_PAIRS_BRANCH_LOG2",
    "SEVEN_PAIRS_PATH_VERSION",
    "SevenPairsPathParams",
    "build_adjustment",
    "build_adjustment_from_params",
    "path_term",
]
