"""坐隐 M4 候选：鸣牌机会成本（机制族定义见 evidence/2.1-M4-family/README.md）。

**命题（REVIEW-6 R6-1 更正后）**：V2 已经用可比牌效给 `Pass` 评分
（`-shanten_step × 向听 + effective_tile × 有效牌剩余`，默认 100 / 1.0）。
本族研究的**不是**"补上完全缺失的等待价值"，而是：
**在 V2 已有可比牌效基础上，吃碰的统一偏置是否需要按等待牌效作条件校准。**

因此本模块的追加项与 V2 既有项**共线**：`natural` 就是 V2 `Pass` 已消费的
`sum(remaining_estimate)`。β 直接表示"把鸣牌-vs-Pass 的有效牌系数抬高多少"：

    β = 20  ⇔  有效牌系数 1.0 → 1.0 + 20/21 ≈ 1.95（约翻倍）

这一点必须在解释结果时说清：**β 扫描是既有权重的一维扫描，不是新增事实维度。**
据此，REVIEW-6 R6-4 要求保留的"常数/线性/分段"对照确实必要——
本族的线性版本只是"抬高既有系数"的一种形状。

**不改冻结基线**：复用 V2 的上下文与逐候选评分，只在 `params.scope`
指定的鸣牌类别上追加一个有界分项，然后**照抄 V2 的排序与审计规则**。

参数（REVIEW-6 S6-2 更正后）：**全部固化在不可变的 `M4Params` 实例上**，
不再使用模块级全局变量。理由：模块全局在异常分支无法保证复位，
且同进程并行调用会互相覆盖，违反"同输入、同配置输出确定"。

**单向声明（REVIEW-6 R6-2）**：β > 0 时本项只能**降低**鸣牌排序，
不可能让原本首选 `Pass` 的窗口改选鸣牌。它是"单向增加等待偏好"的对照候选。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
import hashlib
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    RuleCandidate,
    RuleCompleteness,
)
from hangma_bot.kernel.actions import Chi, Gang, Hu, Pass, Peng, action_key

# 绝对导入：本模块放在 review/ 下（不是 hangma_bot 包成员），
# 由调用方把仓库 src/ 放进 sys.path。**不复制评分实现**，只复用生产函数。
from hangma_bot.policy.errors import PolicyTimeoutError
from hangma_bot.policy.evaluation_v1 import build_context
from hangma_bot.policy.evaluation_v2 import has_waiting_baseline, score_candidates
from hangma_bot.policy.interface import (
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    ScorePart,
)
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1

M4_OPPORTUNITY_COST_VERSION = "sitin-m4-opportunity-cost-v2"

# 影响面类别名 → 动作类型。首版按 REVIEW-6 R6-3 收窄为响应吃碰：
# 明杠也会补牌、暗杠与补杠是自摸窗口（没有响应 Pass），
# 三类杠的"放弃摸牌"语义与本项不一致，另有定义后再纳入。
_KIND_BY_NAME = {"chi": Chi, "peng": Peng, "gang": Gang}


def source_fingerprint() -> str:
    """本模块源码的 sha256 前 16 位；用于候选身份与产物可追溯。"""

    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


@dataclass(frozen=True)
class M4Params:
    """不可变候选参数；随策略实例固定，不随调用变化。

    beta：机会成本幅度，单位是启发式**评分点**，不是桌赛积分。
    natural_ref：等待有效牌剩余估计的参考值；用它归一化，使 β 可直接与分差比较。
    cap：追加项幅度上限，保证有界。
    scope：受影响的动作类别名元组；首版为 ("chi", "peng")。
    """

    beta: float = 0.25
    natural_ref: float = 21.0
    cap: float = 300.0
    scope: Tuple[str, ...] = ("chi", "peng")

    def __post_init__(self) -> None:
        unknown = set(self.scope) - set(_KIND_BY_NAME)
        if unknown:
            raise ValueError("M4 scope 含未知类别：{0}".format(sorted(unknown)))
        if self.natural_ref <= 0:
            raise ValueError("M4 natural_ref 必须为正")

    @property
    def action_types(self) -> Tuple[type, ...]:
        """受影响的动作类型元组，供 isinstance 判断。"""

        return tuple(_KIND_BY_NAME[name] for name in self.scope)

    def to_json(self) -> Dict[str, object]:
        """稳定序列化；用于产物与候选身份。"""

        return {"beta": self.beta, "natural_ref": self.natural_ref,
                "cap": self.cap, "scope": list(self.scope)}

    def effective_tile_multiplier(self, effective_tile: float = 1.0) -> float:
        """参考收益处，鸣牌-vs-Pass 的等效有效牌系数。

        用于向读者说明 β 的真实含义：V2 的系数是 1.0，
        本项把它抬到 1.0 + β/natural_ref。**不是新增事实维度。**
        """

        return effective_tile + self.beta / self.natural_ref


DEFAULT_PARAMS = M4Params()


def natural_draw_value(candidates: Sequence[RuleCandidate]) -> Optional[int]:
    """本手牌的等待有效牌剩余估计：`Pass` 候选的 `remaining_estimate` 之和。

    同一窗口内可读；缺事实、不完整或非 HAND_PROGRESS 时返回 None（**按未知处理**，
    不填 0——填 0 会假装"摸牌没有价值"并放大鸣牌）。

    口径（REVIEW-6 R6-1）：这是**未见有效牌张数估计**，不是摸到概率、
    不是轮到我方前的存活概率、也不是未来和牌价值或支付风险。
    函数名保留历史，语义以本 docstring 为准。
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


def opportunity_cost(action, natural: Optional[int],
                     params: M4Params = DEFAULT_PARAMS) -> float:
    """鸣牌的机会成本（非正分项）：手牌牌效越高，鸣牌越贵。

    `natural` 为 None 或 <= 0 时返回 0.0——**不加不减**，退回基线行为。
    不在 `params.scope` 内的动作返回 0.0。

    线性标定：以 `params.natural_ref` 归一化，β 表示参考收益下的代价点数。
    log1p 与线性是**形状选择**，不是实现正确性；β 乘系数同样能扩大 log1p
    未饱和区间的跨度（REVIEW-6 R6-4）。
    """

    if natural is None or natural <= 0:
        return 0.0
    if not isinstance(action, params.action_types):
        return 0.0
    scale = natural / params.natural_ref
    raw = params.beta * scale
    return round(-min(raw, params.cap), 3)


def adjust(candidates: Sequence[RuleCandidate], natural: Optional[int],
           params: M4Params = DEFAULT_PARAMS) -> Dict[str, float]:
    """对受影响候选追加机会成本分项；返回 (action_key -> delta)。"""

    out: Dict[str, float] = {}
    for candidate in candidates:
        delta = opportunity_cost(candidate.action, natural, params)
        if delta == 0.0:
            continue
        out[candidate.action_key] = delta
    return out


class M4OpportunityCostPolicy:
    """配置名 `sitin_m4_opportunity_cost`。

    与 V2 的唯一差别：`params.scope` 内的鸣牌候选总分追加一个机会成本项。
    排序规则、保底、超时行为、**过滤与候选耗尽的审计说明**全部沿用 V2。

    参数是**构造时固定的不可变实例状态**；同一实例在任意并发或异常路径下
    都使用同一组参数（REVIEW-6 S6-2）。
    """

    def __init__(
        self,
        weights: HeuristicWeightsV1 = DEFAULT_WEIGHTS_V1,
        monotonic: Callable[[], float] = None,
        enabled: bool = True,
        params: M4Params = DEFAULT_PARAMS,
    ) -> None:
        if not isinstance(weights, HeuristicWeightsV1):
            raise TypeError("M4 候选复用冻结的 HeuristicWeightsV1 配置")
        if not isinstance(params, M4Params):
            raise TypeError("M4 参数必须是不可变的 M4Params 实例")
        if monotonic is None:
            import time
            monotonic = time.monotonic
        self._weights = weights
        self._monotonic = monotonic
        self._enabled = bool(enabled)
        self._params = params

    @property
    def params(self) -> M4Params:
        """本实例固定的候选参数。"""

        return self._params

    def candidate_identity(self) -> str:
        """唯一候选身份：版本 + 参数 + 源码指纹（REVIEW-6 S6-3 与 2.2）。"""

        return "{0}+src{1}+{2}".format(
            M4_OPPORTUNITY_COST_VERSION, source_fingerprint(),
            "beta={0},ref={1},cap={2},scope={3}".format(
                self._params.beta, self._params.natural_ref, self._params.cap,
                "+".join(self._params.scope)))

    async def _check_deadline(self, budget: DecisionBudget) -> None:
        await asyncio.sleep(0)
        if self._monotonic() > budget.enhancement_deadline_monotonic:
            raise PolicyTimeoutError(
                "增强计算超过截止时间：单调时钟 {now:.3f} > {deadline:.3f}".format(
                    now=self._monotonic(),
                    deadline=budget.enhancement_deadline_monotonic,
                )
            )

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        await self._check_deadline(budget)
        rules = request.rules
        rejected_keys = frozenset(item.action_key for item in request.rejected_attempts)
        notes: List[str] = []
        audit_reasons: List[str] = []

        for issue in rules.issues:
            audit_reasons.append("规则降级[{area}]：{reason}".format(
                area=issue.area, reason=issue.reason))
        if rules.completeness is RuleCompleteness.DEGRADED:
            audit_reasons.append("规则分析不完整（DEGRADED）：策略按保守排序继续")
        if getattr(request.observation, "catch_play", False):
            audit_reasons.append("抓打圈生效：排序仅在规则允许的硬约束候选内进行")

        # 过滤审计与 V2 保持一致（REVIEW-6 S6-3）：不能静默丢弃候选，
        # 必须留下"为什么被丢"的说明，否则诊断看不到信息损失。
        seen: Set[str] = set()
        intake: List[RuleCandidate] = []
        for candidate in rules.legal_candidates:
            key = candidate.action_key
            if key in rejected_keys:
                audit_reasons.append("过滤已拒绝候选：{key}".format(key=key))
                continue
            if key in seen:
                audit_reasons.append("过滤重复候选：{key}".format(key=key))
                continue
            try:
                canonical = action_key(candidate.action)
            except TypeError:
                audit_reasons.append("过滤未知动作类型候选：{key}".format(key=key))
                continue
            if canonical != key:
                audit_reasons.append("过滤动作键不一致候选：{key}".format(key=key))
                continue
            seen.add(key)
            intake.append(candidate)

        emergency = rules.emergency_candidate
        emergency_key = emergency.action_key if emergency is not None else None
        if emergency is None and rules.legal_candidates:
            notes.append("规则未提供紧急候选，主策略计划未包含保底动作")
        elif emergency_key is not None and emergency_key in rejected_keys:
            notes.append("紧急候选已被官方拒绝：{key}".format(key=emergency_key))

        candidates: Tuple[RankedCandidate, ...] = ()
        if intake:
            context = build_context(request.observation)
            scored = await score_candidates(
                tuple(intake), context, self._weights, lambda: self._check_deadline(budget)
            )
            if self._enabled:
                natural = natural_draw_value(tuple(intake))
                deltas = adjust(tuple(intake), natural, self._params)
                adjusted = []
                for item in scored:
                    delta = deltas.get(item.action_key)
                    if delta is None:
                        adjusted.append(item)
                        continue
                    parts = item.parts + (ScorePart("M4-鸣牌机会成本", delta),)
                    total = round(item.total + delta, 6)
                    if not math.isfinite(total):
                        raise ValueError("M4 机会成本评分非有限，交由应用层紧急保底")
                    adjusted.append(replace(
                        item, parts=parts, total=total,
                        reasons=item.reasons + (
                            "M4 机会成本：等待有效牌剩余估计 {0}，追加 {1}".format(
                                natural, delta),
                        )))
                scored = tuple(adjusted)
                audit_reasons.append(
                    "M4 机会成本启用：{identity}；等待有效牌剩余估计={natural}，受影响候选 {n} 个".format(
                        identity=self.candidate_identity(), natural=natural, n=len(deltas)))

            pass_candidates = [c for c in intake if isinstance(c.action, Pass)]
            missing_baseline = bool(pass_candidates) and not any(
                has_waiting_baseline(c) for c in pass_candidates)
            if missing_baseline:
                ordered = sorted(scored, key=lambda item: (
                    0 if isinstance(item.candidate.action, Hu)
                    else 1 if isinstance(item.candidate.action, Pass) else 2,
                    item.priority, -item.total if item.priority < 2 else 0.0, item.action_key,
                ))
                audit_reasons.append("M4 缺可比等待基线：合法胡优先，其次使用未拒绝的过牌退路")
            elif all(item.priority == 2 for item in scored):
                ordered = sorted(scored, key=lambda item: (
                    item.action_key != emergency_key, item.action_key))
                audit_reasons.append("全部候选事实未知：紧急候选优先，其余按 action_key 排列")
            else:
                # 按 V2 层内规则排序：同层按总分降序；**不得跨层按总分重排**。
                ordered = sorted(scored, key=lambda item: (
                    item.priority, -item.total if item.priority < 2 else 0.0, item.action_key))
            await self._check_deadline(budget)
            if emergency_key is not None and emergency_key in seen:
                if not any(item.action_key == emergency_key for item in ordered):
                    notes.append("防御检查：紧急候选意外缺失于计划")
            candidates = tuple(
                RankedCandidate(
                    action=item.candidate.action,
                    action_key=item.action_key,
                    rank=index + 1,
                    total_score=item.total,
                    score_parts=item.parts,
                    reasons=item.reasons,
                    is_emergency=(item.action_key == emergency_key),
                )
                for index, item in enumerate(ordered)
            )
        else:
            if not rules.legal_candidates:
                notes.append("规则未产生任何合法候选，计划为空")
            elif rejected_keys:
                notes.append("候选耗尽：全部合法候选均已被官方拒绝")
            else:
                notes.append("候选耗尽：全部候选被防御性过滤，计划为空")
        await self._check_deadline(budget)
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=len(request.rejected_attempts) + 1,
            candidates=candidates,
            degraded_reasons=tuple(audit_reasons + notes),
        )
