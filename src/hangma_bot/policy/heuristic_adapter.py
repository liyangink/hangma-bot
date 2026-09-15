"""启发式候选适配器：把"只读既有事实的有界评分调整"接进 V2 决策链。

**用途**（README §17 第二步 2.2）：建立一条**候选可插拔的接缝**，使后续每新增一个
机制候选只需**新增一个模块 + 注册表一行**，不必再改 `evaluation_v1/v2`、
`heuristic_v2`、`bootstrap` 或 `scripts/evaluate.py`。

**设计要点**：

1. **候选不复制管线**。适配器只在 `evaluation_v2.score_candidates` 之后追加一个
   有界分项；过滤、可信层级、排序、紧急保底与截止时间检查**全部沿用 V2**。
   这条有实测理由：复制 V2 的过滤分支时曾漏掉一个 `continue`，**会把官方已明确
   拒绝的动作重新提交**。复制决策管线是真实风险，不是洁癖。
2. **消融是构造保证的**。`adjustments=()` 时 V2 行为逐字节不变，
   因此"关闭即等价基线"不依赖测试碰运气。
3. **候选能力边界**：只能读 `candidate.facts`（规则唯一来源）与
   `EvaluationContext`；不得判断合法性、不得重排、不得读时间/随机/文件、
   不得做搜索或重算向听（根 AGENTS.md §6、README §6.1 G-1）。
4. **越界不静默**：|delta| 超过 `spec.bound` 时钳制并**写入审计说明**；
   静默钳制会掩盖候选缺陷，而本项目要求完整评分分解与降级原因可审计。
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace
from typing import Awaitable, Callable, Optional, Tuple

from hangma_bot.hangma.interface import RuleCandidate

from .evaluation_v1 import EvaluationContext, ScoredCandidate
from .heuristic_v2 import ComparableHeuristicPolicyV2
from .interface import BotPolicy, ScorePart
from .weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1

ADJUSTMENT_SCHEMA_VERSION = "heuristic-adjustment-v1"


# 源码指纹**不由本包计算**：policy 模块禁止任何文件副作用。
# tests/unit/policy/test_policy_timeout_and_purity.py 会静态扫描策略源码里
# pathlib 的 Path 构造、内建 open、以及 read_text / write_text 这类痕迹；
# 指纹是**装载期的溯源信息**，由持有 IO 权限的装载方（scripts/evaluate.py）
# 读取候选模块文件后传入，并由契约测试比对，防止声明与实际源码漂移。


@dataclass(frozen=True)
class AdjustmentSpec:
    """候选调整的元数据；缺少触发条件说明的候选不得进入实验队列（G-3）。

    name：写入 ScorePart 的稳定名称，审计可见。
    version：候选版本；与参数、源码指纹共同构成身份。
    thought：中文机制说明（EoH 的"思想"表示），供人工审核与 LLM 反馈。
    trigger：触发条件说明（G-3 准入要求，不许空）。
    scope：受影响的动作类别（`chi`/`peng`/`gang`/`discard`/`pass`/`hu`）。
    bound：|delta| 的上限，由适配器强制。
    """

    name: str
    version: str
    thought: str
    trigger: str
    scope: Tuple[str, ...]
    bound: float

    def __post_init__(self) -> None:
        for field_name in ("name", "version", "thought", "trigger"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("AdjustmentSpec.{0} 必须是非空字符串".format(field_name))
        if not self.scope:
            raise ValueError("AdjustmentSpec.scope 不得为空")
        if type(self.bound) not in (int, float) or not math.isfinite(self.bound):
            raise ValueError("AdjustmentSpec.bound 必须是有限数值")
        if self.bound <= 0:
            raise ValueError("AdjustmentSpec.bound 必须为正")


def action_kind(action_key: Optional[str]) -> str:
    """动作类别名；与产物口径一致（`peng:1w` -> `peng`）。"""

    return action_key.split(":", 1)[0] if action_key else ""


class HeuristicAdjustment:
    """把一个纯函数 `delta` 包装成**有界、按 scope 生效、可审计**的调整。

    `delta` 必须是纯函数：同输入同输出，无 IO、无时间、无随机、无搜索。
    适配器不替候选做合法性判断，也不改变层级与排序。
    """

    def __init__(
        self,
        spec: AdjustmentSpec,
        delta: Callable[[RuleCandidate, EvaluationContext, Tuple[RuleCandidate, ...]], float],
        *,
        source_fingerprint_value: str = "",
        params_json: Optional[str] = None,
    ) -> None:
        if not isinstance(spec, AdjustmentSpec):
            raise TypeError("HeuristicAdjustment 需要 AdjustmentSpec")
        if not callable(delta):
            raise TypeError("HeuristicAdjustment 需要可调用的 delta")
        self._spec = spec
        self._delta = delta
        self._fingerprint = source_fingerprint_value
        self._params_json = params_json
        self.clamped_count = 0

    @property
    def spec(self) -> AdjustmentSpec:
        return self._spec

    def identity(self) -> str:
        """唯一候选身份：schema + 版本 + 参数（+ 装载方传入的源码指纹）。

        指纹缺省时省略该段而不是填占位符——**让"未计算"与"已计算"在字符串上可区分**，
        避免读到一个假的指纹。
        """

        base = "{0}+{1}+{2}".format(
            ADJUSTMENT_SCHEMA_VERSION, self._spec.version,
            self._params_json or "params=-")
        return base + "+src" + self._fingerprint if self._fingerprint else base

    def applies_to(self, key: Optional[str]) -> bool:
        return action_kind(key) in self._spec.scope

    def apply(
        self,
        item: ScoredCandidate,
        ctx: EvaluationContext,
        candidates: Tuple[RuleCandidate, ...],
    ) -> ScoredCandidate:
        """按 scope 计算并追加分项；类别外或 delta 为 0 时原样返回。

        `candidates` 是本窗口**规则给出的全部候选**（只读）。
        有些机制需要跨候选的量——例如"放弃这次鸣牌等于放弃多少等待牌效"要读
        `Pass` 候选的事实——因此协议把它一并给出。它仍然只是规则事实，
        候选不得据此判断合法性，也不得改变候选集合。
        """

        if not self.applies_to(item.action_key):
            return item
        raw = self._delta(item.candidate, ctx, candidates)
        if type(raw) not in (int, float):
            raise TypeError("候选 delta 必须返回数值，得到 {0!r}".format(raw))
        if not math.isfinite(raw):
            raise ValueError("候选 delta 非有限，交由应用层紧急保底")
        if raw == 0.0:
            return item
        clamped = raw
        notes: Tuple[str, ...] = ()
        if abs(raw) > self._spec.bound:
            clamped = math.copysign(self._spec.bound, raw)
            self.clamped_count += 1
            notes = ("候选越界已钳制：实际 {0:.4f}，上限 {1:.4f}".format(raw, self._spec.bound),)
        total = round(item.total + clamped, 6)
        if not math.isfinite(total):
            raise ValueError("调整后评分非有限，交由应用层紧急保底")
        return replace(
            item,
            parts=item.parts + (ScorePart(self._spec.name, clamped),),
            total=total,
            reasons=item.reasons + notes + ("{0}={1}".format(self._spec.name, clamped),),
        )


class HeuristicAdjustmentPolicy:
    """把候选调整接进 V2 的 `BotPolicy` 薄壳。

    本类**不实现**过滤、层级、排序、保底或截止时间——它只把 `adjustments`
    交给 V2。`enabled=False` 时传空元组，于是**逐字节等价基线**。
    """

    def __init__(
        self,
        adjustment: HeuristicAdjustment,
        weights: HeuristicWeightsV1 = DEFAULT_WEIGHTS_V1,
        monotonic: Optional[Callable[[], float]] = None,
        enabled: bool = True,
    ) -> None:
        if not isinstance(adjustment, HeuristicAdjustment):
            raise TypeError("HeuristicAdjustmentPolicy 需要 HeuristicAdjustment")
        if monotonic is None:
            monotonic = time.monotonic
        self.adjustment = adjustment
        self._enabled = bool(enabled)
        self._inner: BotPolicy = ComparableHeuristicPolicyV2(
            weights=weights,
            monotonic=monotonic,
            adjustments=(adjustment,) if self._enabled else (),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def base_policy(self) -> BotPolicy:
        """被包装的 V2，供离线记录有效权重时继续读取（沿用既有装饰器约定）。"""

        return self._inner

    def identity(self) -> str:
        return self.adjustment.identity()

    async def choose(self, request, budget):
        return await self._inner.choose(request, budget)


__all__ = [
    "ADJUSTMENT_SCHEMA_VERSION",
    "AdjustmentSpec",
    "HeuristicAdjustment",
    "HeuristicAdjustmentPolicy",
    "action_kind",
]
