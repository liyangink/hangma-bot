"""价值族（Value-Path Family）第二个实例：**动作链路径价值**。

## 为什么它属于「价值族」，而不是「动作族」

官方《1.3》原文（doc/references/official-guide-v34-content.txt 第 29 / 57 行）：

    总番 = 1 × 分支因子 × 2^动作链次数 ×（4 白板 ×2）×（爆头 ×2）
    动作链：飘与杠可连续、可组合，每个飘/杠动作 ×2；
    打出非飘非杠的牌（含非爆头态打白板）→ 链断重新计数。

本实例只问一件事：**这个动作让链前进了几步**。它不看"这是吃还是碰"——
吃碰在本规则下**不改变链**（正因如此，"圈内吃碰后再打财神 = 财飘链 +1" 才成立）。

## 它修掉了 M4 的分层错误（规则级证据）

M4（`meld_opportunity_cost`）把吃碰建模成**纯机会成本**：把"过牌那边的等待牌效"
`−f(s)` 只加给吃碰候选。官方明文规定吃碰之后**可以**再打财神续飘（链 +1、番 ×2），
所以吃碰既可能是链投资、也可能只是过渡，**不能无条件按动作标签扣分**。
本实例对吃碰给出 0（链不变），把链的价值交给"链实际怎么变"来决定。

## 为什么它是**安全**的（potential-based）

Ng/Harada/Russell 1999 要求塑形写成 `F(s,a,s') = γΦ(s') − Φ(s)`，γ=1 时退化为
`Φ(s') − Φ(s)`。本实例取

    Φ(s) = scale · chain_count(s)                     # 状态势，只依赖状态
    term(a) = Φ(s') − Φ(s) = scale · (链次数增量)

动作后的链次数**不由本模块重算**，而是调用 `hangma.progression` 的规则转移函数
（`chain_after_discard` / `chain_after_gang`）——单一规则来源，policy 不复制规则。
于是 term 恒是**同一个状态势的差**，不是"给杠 +40、给吃 −60"这类动作标签加分。

**由此得到的自动性质**（都有测试）：沿任意闭环求和为 0（Ng §3 环判据）；
吃/碰/过三项恒为 0，只有链真的动了才给分。

## 单位与自由参数（必须显式声明，方案 §16.3 G-BS-3）

- `step_log2 = 1.0`：每个飘/杠动作 ×2 ⇒ log2 番 +1。**规则常量，不是调参结果。**
- `scale`：把 log2 番换算成启发式评分点的比例，**单位 = 评分点 / log2 番**。
  相对结构（各项系数是否相等）由规则唯一确定；**只有这一个整体尺度是自由的**，
  它是本族在"便宜参数搜索臂"里的主旋钮。
  默认 40.0 的锚点：冻结的 V1 权重里 `gang_bonus = 40.0` 已经是"一次杠的番值潜力"，
  而一次杠在官方口径里正是 ×2 = log2 +1。注意本项与该 `gang_bonus` **会叠加**
  （V1 按动作标签给分、本项按状态势给分），"叠加是否更优"属待检验假设。

## 一处**有意**偏离严格势差的地方（必须写明）

胡牌动作：按严格势差应为 `Φ(吸收态) − Φ(s) = −Φ(s)`（Ng 的吸收态约定）。
本实例对胡返回 0.0，理由是：

1. 链在胡牌时**兑现**（`fan` 已含 `2^chain_count`），不是断链；
2. 合法胡恒为 `priority = 0`（`evaluation_v1._priority`），**评分不参与它的排序**，
   因此"0 还是 −Φ(s)"**不可能改变任何计划**；
3. 写入 −Φ(s) 会让审计里最好的那个动作带一个大负数，误导人工复核。

这不是"不满足充分条件"：差异只落在 win 动作上，而同状态内其余动作仍共享同一势差。

## 纯度

纯函数；只读 `EvaluationContext`（规则状态）与候选的动作标签，不读时间/随机/文件，
不做搜索。链次数未知（`chain_piao` 为空且需要它）时不猜。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.hangma.progression import chain_after_discard, chain_after_gang
from hangma_bot.kernel.actions import Action, Discard, Gang, Hu

from ..evaluation_v1 import EvaluationContext
from ..heuristic_adapter import AdjustmentSpec, HeuristicAdjustment

CHAIN_PATH_VERSION = "chain-path-value-v1"

# 官方《1.3》：每个飘/杠动作 ×2 ⇒ 链每步 +1 个 log2 番。**规则常量。**
CHAIN_STEP_LOG2 = 1.0

# 官方快照 `chain.count` 取值范围 0—6（guide 第 106 行）。用于默认幅度的量级说明。
MAX_CHAIN_COUNT = 6

# 作用面：**全部动作类别**。理由同价值族①——分档依据是**状态变化**，
# 而状态变化可以发生在任何动作上；用动作类别去卡就退化成动作标签加分。
ALL_KINDS: Tuple[str, ...] = ("chi", "peng", "gang", "discard", "pass", "hu")


@dataclass(frozen=True)
class ChainPathParams:
    """不可变参数实例。

    scale：单位 **评分点 / log2 番**，见模块 docstring 的锚点说明。
    step_log2：每链步的 log2 番，**由官方规则确定 = 1.0**；保留为字段只为可审计。
    bound：|delta| 上限，由适配器强制（本模块不预先钳制，保持单一强制点与越界审计）。
    """

    scale: float = 40.0
    step_log2: float = CHAIN_STEP_LOG2
    bound: float = 300.0
    scope: Tuple[str, ...] = ALL_KINDS

    def __post_init__(self) -> None:
        for field_name in ("scale", "step_log2", "bound"):
            value = getattr(self, field_name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(
                    "ChainPathParams.{0} 必须是有限数值".format(field_name))
        if self.scale < 0 or self.step_log2 < 0:
            raise ValueError("scale 与 step_log2 必须非负")
        if self.bound <= 0:
            raise ValueError("ChainPathParams.bound 必须为正")

    def to_json(self) -> str:
        return "scale={0},step_log2={1},bound={2}".format(
            self.scale, self.step_log2, self.bound)


def chain_count_after(ctx: EvaluationContext, action: Action) -> int:
    """动作后的链次数；复用 hangma 的规则转移，不在此重写规则。

    规则依据（guide 第 57 行）：飘与杠每个动作 ×2；打出非飘非杠的牌（含非爆头态
    打白板）→ 链断重新计数。吃/碰/过/胡按本转移保持不变（吃碰后的**强制弃牌**
    才可能断链，那次断链在它自己的决策窗口被计价）。

    实现说明：只消费规则转移函数的**第 0 项**（链次数）。同函数的第 1 项是链内
    飘次数，本模块不需要，故传入 0 不影响链次数结果；需要飘次数的是价值族③。
    """

    if isinstance(action, Gang):
        return chain_after_gang(ctx.chain_count, 0)[0]
    if isinstance(action, Discard):
        return chain_after_discard(ctx.chain_count, 0, ctx.baotou, action.tile)[0]
    return ctx.chain_count


def path_term(candidate: RuleCandidate, ctx: EvaluationContext,
              params: ChainPathParams) -> float:
    """`Φ(s') − Φ(s)`：按链次数增量给分（前进为正、断链为负）。

    胡牌动作返回 0.0（见模块 docstring 的偏离说明）；差额只落在 win 动作上，
    而 win 恒为 priority 0，评分不参与其排序。
    """

    action = candidate.action
    if isinstance(action, Hu):
        return 0.0
    delta = chain_count_after(ctx, action) - ctx.chain_count
    if delta == 0:
        return 0.0
    return round(params.scale * params.step_log2 * delta, 6)


def build_adjustment(
    params: ChainPathParams = ChainPathParams(),
    *,
    source_fingerprint_value: str = "",
) -> HeuristicAdjustment:
    """构造可直接交给适配器的候选调整。"""

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        del candidates        # 本项是纯状态势，不需要跨候选的量
        return path_term(candidate, ctx, params)

    spec = AdjustmentSpec(
        name="价值族②-链路径价值",
        version=CHAIN_PATH_VERSION,
        thought=(
            "按官方动作链而非动作类别打分：飘与杠每个动作使总番 ×2，打出非飘非杠的牌"
            "（含非爆头态打白板）则链断清零。本项给链前进 +scale、按断链前层数扣"
            "scale×层数，写成状态势之差。吃碰本身不改链，故不受罚——这修正了把吃碰"
            "当纯机会成本的处理；官方明文允许圈内吃碰后再打财神续飘（链 +1）。"),
        trigger=("动作改变本人动作链次数：杠（任意种类）或爆头态打出财神使链 +1；"
                 "链次数大于 0 时打出非飘非杠的牌使链清零"),
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

    known = {"scale", "step_log2", "bound"}
    unknown = set(params) - known
    if unknown:
        raise ValueError("价值族②参数含未知键：{0}；可识别：{1}".format(
            sorted(unknown), sorted(known)))
    kwargs = {key: float(params[key]) for key in known if key in params}
    return build_adjustment(
        ChainPathParams(**kwargs), source_fingerprint_value=source_fingerprint_value)


__all__ = [
    "ALL_KINDS",
    "CHAIN_PATH_VERSION",
    "CHAIN_STEP_LOG2",
    "MAX_CHAIN_COUNT",
    "ChainPathParams",
    "build_adjustment",
    "build_adjustment_from_params",
    "chain_count_after",
    "path_term",
]
