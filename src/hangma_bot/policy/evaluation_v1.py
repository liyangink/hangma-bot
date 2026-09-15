"""V1 独立评分：保留 V0 权重偏好，区分可信与未知候选。

从冻结的 evaluation.py 复制；不得反向让 V0 导入本文件。
只消费规则事实，不重新计算向听、有效牌或动作合法性。

修订说明（2026-09-15，S1c 事实接线，最小改动）
------------------------------------------------
本文件在 tests/offline/evidence/v1-acceptance-2026-09-06/freeze.json 的冻结清单内。
本次只做一件事：为 EvaluationContext 追加四个**带默认值**的规则状态字段
（chain_count / baotou / wealth_count / chain_piao），并在 build_context 中填充。
chain_piao 是官方「手留白 + 链内飘出 ≤ 4」口径（guide 第 106 行）里除手留白外的另一半，
缺它就无法判定「四白 ×2」这条倍率；它与 chain_count 同属观察层已有事实。

为什么必须加（官方规则依据）：总番 = 1 × 分支因子 × 2^动作链次数 ×（4 白板 ×2）×（爆头 ×2）
（doc/references/official-guide-v34-content.txt 第 29 行）。链与爆头都直接乘 2 的幂，
属于决定同一局面真实价值的状态量；候选要写出涉及它们的评分项，就必须先能读到它们。

**更正（2026-09-15，由独立复核撞出）**：本文件初版把这件事写成"安全性前提"，并称
"势的输入漏掉这些量 ⇒ 充分条件失效"。**那是错的，已改。**
potential-based 塑形（Ng, Harada & Russell 1999, "Policy invariance under reward
transformations", ICML, 定理 1，https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/
readings/NgHaradaRussell-ICML99.pdf ）只要求加分能写成 F(s,a,s') = γΦ(s') − Φ(s)，
其中 Φ 是**某一个**状态函数——**并不要求 Φ 涵盖全部影响价值的量**。
Φ 漏掉某个 ×2 状态量的后果是**那一项没有被塑形**（该项无效果），不是"不合规"。
真正会让充分条件失效的是**按动作标签加分**（F 不是任何 Φ 的差）。
所以本文件新增字段的正当理由是**可表达性**，比"安全性前提"弱，但依然充分。
（本候选价值族②的 Φ 就只含 chain_count，不含 baotou/chain_piao——按更正后的读法
这只说明它没有塑形那两个乘子，不构成缺陷。）

**限定（必须与上面一起引用）**：该定理的原始设定假设**状态对决策者可见**；
本项目是隐藏信息局，把定理直接搬到"信息状态"上是【推导·未一手核实】。
仓库笔记 refs/REF-DECOMP-game-abstraction.md §3.5/§6 记录了这条限定。

为什么是行为中性的（三条等价证据，2026-09-15 实测）：
1. 三个字段都有默认值；本文件内 EvaluationContext 的构造点只有 build_context 一处；
2. 全仓 grep：EvaluationContext 的 __eq__ / __hash__ 使用点为 0；
3. V0/V1/V2 的评分函数不读这三个字段，故评分分项、排序与计划不变。
   改动前的对照运行中，全仓测试只有冻结哈希断言一条失败。
   唯一可见差异是 repr（审计文本），不属于行为。

代价与边界：冻结清单中本文件的 sha256 随之更新，修订原因记录在同一 freeze.json；
**不**新建并行的上下文类型，也不为历史版本做兼容设计（用户已裁定：补充说明即可）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Awaitable, Callable, FrozenSet, List, Optional, Tuple

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    RuleCandidate,
    RuleCompleteness,
)
from hangma_bot.kernel.actions import Action, Chi, Discard, Gang, GangKind, Hu, Pass, Peng
from hangma_bot.kernel.observation import PlayerObservation

from .interface import ScorePart
from .weights_v1 import HeuristicWeightsV1

_GANG_KIND_NAMES = {
    GangKind.CONCEALED: "暗杠",
    GangKind.EXPOSED: "明杠",
    GangKind.ADDED: "补杠",
}


@dataclass(frozen=True)
class EvaluationContext:
    """一次决策窗口内不变的评分上下文；全部来自玩家可见信息。"""

    combined_codes: Tuple[str, ...]  # my_hand + drawn_tile 的牌码，保留官方顺序
    wealth_code: str  # 财神牌码（本项目规则为白板）
    safe_codes: FrozenSet[str]  # 已见于他家牌河的牌码（熟张）
    my_seat: int
    next_seat: int  # 下家座位 = (本座位 + 1) % 4
    next_seat_meld_codes: Tuple[str, ...]  # 下家副露全部牌码
    dealer_seat: int
    dealer_meld_codes: Tuple[str, ...]  # 庄家副露全部牌码
    table_rank: int  # 桌内名次，1 为领先；同分时并列名次按严格大于计数
    catch_play: bool  # 是否处于抓打圈
    # 以下三项为 2026-09-15 追加的规则状态；带默认值以保证旧构造点行为不变。
    # 三者都是"直接乘 2 的幂"的状态量，是 potential-based 塑形的前提（见模块 docstring）。
    chain_count: int = 0  # 本人飘/杠动作链次数（官方 god.chain_count）；断链清零，非负，每步总番 ×2
    baotou: bool = False  # 本人是否爆头（官方 god.baotou）；总番 ×2，且是"飘"的前置条件
    wealth_count: int = 0  # 动作前本人手留财神张数；四白还须叠加链内飘出张数，不得只用本字段
    chain_piao: Optional[int] = None  # 当前链内飘出白板数（官方 chain.piao）；依据不足时为空，**不等于零**


@dataclass(frozen=True)
class ScoredCandidate:
    """单候选的评分中间结果；由策略层补齐排名并组装计划。"""

    priority: int  # 0=合法胡，1=可信评分，2=未知；内部排序层
    candidate: RuleCandidate
    action_key: str
    parts: Tuple[ScorePart, ...]
    reasons: Tuple[str, ...]
    total: float
    shanten: Optional[int]  # 动作后向听（来自规则事实）；未知为 None
    is_safe_discard: bool  # 是否为熟张弃牌，供名次风格层加成


def build_context(observation: PlayerObservation) -> EvaluationContext:
    """从玩家观察构建评分上下文；不做任何合法性判断。"""

    combined: List[str] = _hand_codes_without_double_count(observation)

    meld_codes_by_seat: List[Tuple[str, ...]] = []
    for seat_melds in observation.melds:
        seat_codes: List[str] = []
        for meld in seat_melds:
            for tile in meld.tiles:
                seat_codes.append(tile.code)
        meld_codes_by_seat.append(tuple(seat_codes))

    my_seat = observation.seat
    next_seat = (my_seat + 1) % 4
    my_score = observation.scores[my_seat]
    table_rank = 1 + sum(1 for score in observation.scores if score > my_score)

    safe_codes = frozenset(
        tile.code
        for seat_index, river in enumerate(observation.discards)
        if seat_index != my_seat
        for tile in river
    )

    wealth_code = observation.rule_state.wealth_god.code
    # 手留财神张数按 combined_codes 机械计数，与 _wealth_after 同口径。
    # 吃/碰/杠组合按规则不含财神（白不可被吃碰杠），故这里只数手牌。
    wealth_count = sum(1 for code in combined if code == wealth_code)

    return EvaluationContext(
        combined_codes=tuple(combined),
        wealth_code=wealth_code,
        safe_codes=safe_codes,
        my_seat=my_seat,
        next_seat=next_seat,
        next_seat_meld_codes=meld_codes_by_seat[next_seat],
        dealer_seat=observation.dealer_seat,
        dealer_meld_codes=meld_codes_by_seat[observation.dealer_seat],
        table_rank=table_rank,
        catch_play=observation.rule_state.catch_play,
        chain_count=observation.rule_state.chain_count,
        baotou=observation.rule_state.baotou,
        wealth_count=wealth_count,
        # 官方 chain.piao 的依据不足时为空，原样透传（空与 0 必须区分）。
        chain_piao=observation.chain_piao,
    )


def _hand_codes_without_double_count(observation: PlayerObservation) -> List[str]:
    """本人暗牌牌码（含刚摸牌，摸牌置尾），按两种官方形态归一化计数。

    N-1 修复（与 hangma 引擎 _concealed_without_drawn 同口径，依据
    doc/implementation/notes/rules-hu-gate-and-win-detection.md）：官方快照
    实测形态「my_hand 已含刚摸牌」（长度 = 14−3×副露数）与契约形态
    「my_hand 不含摸牌」（长度 = 13−3×副露数）并存；不归一化时 combined
    会把刚摸牌双计（幻影副本）送进评分上下文（牌效计数、财神保留计数
    失真）。归一化只做计数/顺序整理，不做任何合法性判断（模块边界不变）。
    """

    codes: List[str] = [tile.code for tile in observation.my_hand]
    drawn = observation.drawn_tile
    if drawn is None:
        return codes
    expected = 14 - 3 * len(observation.melds[observation.seat])
    if len(codes) == expected:
        # 官方形态：移除末尾同码实例（=刚摸的牌），下方再统一置尾
        for index in range(len(codes) - 1, -1, -1):
            if codes[index] == drawn.code:
                del codes[index]
                break
    codes.append(drawn.code)
    return codes


def _near_meld(codes: Tuple[str, ...], target: str) -> bool:
    """判断目标数牌与副露牌码同花色且序数差不超过 2（吃牌范围近似）。"""

    if len(target) != 2 or target[1] not in "btw" or target[0] not in "123456789":
        return False
    rank = int(target[0])
    suit = target[1]
    for code in codes:
        if len(code) == 2 and code[1] == suit and code[0] in "123456789":
            if abs(int(code[0]) - rank) <= 2:
                return True
    return False


def _wealth_after(action: Action, ctx: EvaluationContext) -> int:
    """动作后本人保留的财神张数（机械计数，不涉及向听/有效牌推演）。

    吃/碰/杠组合按规则不含财神（白不可被吃/碰/杠），因此只有打出财神
    的弃牌会减少计数；过与鸣牌保持不变。
    """

    wealth = sum(1 for code in ctx.combined_codes if code == ctx.wealth_code)
    if isinstance(action, Discard) and action.tile.code == ctx.wealth_code:
        wealth -= 1
    return max(0, wealth)


def _progress_parts(
    facts: CandidateFacts, weights: HeuristicWeightsV1
) -> Tuple[List[ScorePart], List[str], Optional[int]]:
    """HAND_PROGRESS 事实的第三/四层分项：向听与有效牌加权。"""

    shanten = facts.shanten_after
    if shanten is None:
        # 契约防御：HAND_PROGRESS 必须携带向听；缺少数值按未知处理。
        return (
            [ScorePart("第二层-保守兜底", 0.0)],
            ["牌效事实缺少向听数值：按未知处理，不推断向听或有效牌"],
            None,
        )
    parts: List[ScorePart] = [
        ScorePart("第三层-向听数", -weights.shanten_step * shanten),
    ]
    effective_weight = sum(item.remaining_estimate for item in facts.useful_tiles)
    parts.append(
        ScorePart("第四层-有效牌", round(weights.effective_tile * effective_weight, 1))
    )
    reasons: List[str] = [
        "动作后向听数 {0}；有效牌{1}种、剩余估计 {2} 张".format(
            shanten, len(facts.useful_tiles), effective_weight
        ),
    ]
    if facts.useful_tiles:
        samples = "、".join(item.code for item in facts.useful_tiles[:8])
        ellipsis = "…" if len(facts.useful_tiles) > 8 else ""
        reasons.append("有效牌样例：{0}{1}".format(samples, ellipsis))
    if facts.replacement_draw_unknown:
        reasons.append("杠上补牌未知：向听与有效牌按补牌前余牌口径")
    return parts, reasons, shanten


def _priority(candidate: RuleCandidate) -> int:
    """按动作与单候选事实决定排序层；整体规则降级不抹去可信候选。"""

    if isinstance(candidate.action, Hu):
        return 0
    facts = candidate.facts
    if facts is None or facts.completeness is not RuleCompleteness.COMPLETE:
        return 2
    if isinstance(candidate.action, Pass) and facts.fact_kind is CandidateFactKind.NOT_APPLICABLE:
        return 1
    if facts.fact_kind is CandidateFactKind.HAND_PROGRESS:
        # 历史构造器不校验向听类型；不把布尔值、负值或缺失值当牌效。
        if type(facts.shanten_after) is int and facts.shanten_after >= 0:
            return 1
    return 2


def _score_one(
    candidate: RuleCandidate,
    ctx: EvaluationContext,
    weights: HeuristicWeightsV1,
) -> ScoredCandidate:
    """给单个规则候选打分；合法性由规则模块保证，本函数不复判。

    牌效数值一律来自 candidate.facts；facts=None 时不推断任何向听或
    有效牌数值，只保留保守兜底与可见信息分项。
    """

    action = candidate.action
    facts = candidate.facts
    parts: List[ScorePart] = []
    reasons: List[str] = []
    shanten: Optional[int] = None
    is_safe_discard = False

    priority = _priority(candidate)
    if priority == 0:
        parts.append(ScorePart("第一层-立即胡牌", weights.win_now))
        reasons.append("V1 排序层：合法胡牌优先，不依赖加权分数大小")
        reasons.extend(candidate.evidence[:2])
        shanten = -1
    elif priority == 2:
        parts.append(ScorePart("第二层-未知事实", 0.0))
        reasons.append("V1 排序层：未知事实，排在可信候选之后；零分不代表良好牌效")
        if facts is not None:
            kind = facts.fact_kind.value if isinstance(facts.fact_kind, CandidateFactKind) else "未知分类"
            reasons.append("事实不完整、不适用或不可信：{0}".format(kind))
            if facts.note:
                reasons.append(facts.note)
        else:
            reasons.append("牌效事实未生产")
        # 下游原因也不能引用不可信的后续弃牌或补牌信息。
        facts = None
    elif isinstance(action, Pass):
        parts.append(ScorePart("第二层-保守兜底", 0.0))
        reasons.append("V1 排序层：可信候选；过保留 V0 中性基线，不消费新增等待牌效")
    else:
        reasons.append("V1 排序层：可信候选，按原权重评分")
        progress_parts, progress_reasons, shanten = _progress_parts(facts, weights)
        parts.extend(progress_parts)
        reasons.extend(progress_reasons)

    # 第四层-成牌收益：动作后保留财神张数的机械计数（可见信息，非规则推演）。
    parts.append(
        ScorePart("第四层-成牌收益", weights.win_potential * _wealth_after(action, ctx))
    )

    # 第六层-鸣牌风险 / 财神保留 / 熟张与喂牌风险：全部为可见信息分项。
    if isinstance(action, Discard):
        code = action.tile.code
        if code == ctx.wealth_code:
            parts.append(ScorePart("第二层-财神保留", -weights.wealth_god_keep))
            reasons.append("打出财神：放弃万能牌并触发抓打圈，仅规则允许时保守接受")
        if code in ctx.safe_codes:
            is_safe_discard = True
            parts.append(ScorePart("第六层-熟张安全", weights.safe_tile_bonus))
            reasons.append("熟张：{code} 已见于他家牌河".format(code=code))
        else:
            risk_units = 0.0
            risk_notes: List[str] = []
            if _near_meld(ctx.next_seat_meld_codes, code):
                risk_units += 1.0
                risk_notes.append("接近下家副露吃牌范围")
            if ctx.dealer_seat != ctx.my_seat and _near_meld(ctx.dealer_meld_codes, code):
                risk_units += 0.5
                risk_notes.append("接近庄家副露")
            if risk_units > 0:
                parts.append(
                    ScorePart("第六层-喂牌风险", -round(weights.feed_risk * risk_units, 1))
                )
                reasons.append(
                    "生张{code}：{notes}".format(code=code, notes="、".join(risk_notes))
                )
        if ctx.catch_play:
            reasons.append("抓打圈生效：仅规则允许的弃牌参与排序")
    elif isinstance(action, Peng):
        parts.append(ScorePart("第六层-鸣牌风险", -weights.claim_risk_peng))
        followup = (
            facts.best_followup_discard
            if facts is not None and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
            else None
        )
        if followup is not None:
            reasons.append(
                "碰{code}后按规则最佳后续弃牌{followup}估计".format(
                    code=action.tile.code, followup=followup
                )
            )
        else:
            reasons.append("碰{code}：缺少最佳后续弃牌事实，按保守风险分参与排序".format(
                code=action.tile.code))
    elif isinstance(action, Chi):
        parts.append(ScorePart("第六层-鸣牌风险", -weights.claim_risk_chi))
        followup = (
            facts.best_followup_discard
            if facts is not None and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
            else None
        )
        tiles = "、".join(tile.code for tile in action.tiles)
        if followup is not None:
            reasons.append(
                "吃{tiles}后按规则最佳后续弃牌{followup}估计".format(
                    tiles=tiles, followup=followup
                )
            )
        else:
            reasons.append(
                "吃{tiles}：缺少最佳后续弃牌事实，按保守风险分参与排序".format(tiles=tiles)
            )
    elif isinstance(action, Gang):
        parts.append(ScorePart("第二层-杠收益", weights.gang_bonus))
        label = "{kind}{code}".format(
            kind=_GANG_KIND_NAMES[action.kind], code=action.tile.code
        )
        if (
            facts is not None
            and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
            and facts.replacement_draw_unknown
        ):
            reasons.append(
                "{label}：按杠后余牌保守估计（杠上补牌未知，补牌前口径）".format(label=label)
            )
        else:
            reasons.append("{label}：保留结构并积累番值潜力".format(label=label))
    elif isinstance(action, Pass):
        if facts is None:
            reasons.append("过：牌效事实未生产，保持手牌不暴露信息")

    total = round(sum(part.value for part in parts), 6)
    return ScoredCandidate(
        priority=priority,
        candidate=candidate,
        action_key=candidate.action_key,
        parts=tuple(parts),
        reasons=tuple(reasons),
        total=total,
        shanten=shanten,
        is_safe_discard=is_safe_discard,
    )


async def score_candidates(
    candidates: Tuple[RuleCandidate, ...],
    ctx: EvaluationContext,
    weights: HeuristicWeightsV1,
    check_deadline: Callable[[], Awaitable[None]],
) -> Tuple[ScoredCandidate, ...]:
    """给全部入围候选打分，并应用第七层名次风格调整。

    check_deadline 是异步截止检查：每个候选评分前等待一次事件循环，
    保证应用层的 wait_for 能在保底截止时间抢占本协程，超时抛
    PolicyTimeoutError。
    """

    scored = []
    for candidate in candidates:
        await check_deadline()
        scored.append(_score_one(candidate, ctx, weights))

    if scored:
        known = [item.shanten for item in scored if item.shanten is not None]
        best_shanten = min(known) if known else None
        adjusted: List[ScoredCandidate] = []
        for item in scored:
            if not isinstance(item.candidate.action, Discard):
                adjusted.append(item)
                continue
            bonus = 0.0
            note = ""
            if ctx.table_rank == 1 and item.is_safe_discard:
                bonus, note = weights.style_adjust, "桌内领先：保守风格优先熟张"
            elif (
                ctx.table_rank == 4
                and best_shanten is not None
                and item.shanten == best_shanten
            ):
                bonus, note = weights.style_adjust * 0.5, "桌内落后：进取风格优先向听最优路线"
            if bonus == 0.0:
                adjusted.append(item)
                continue
            parts = list(item.parts)
            parts.append(ScorePart("第七层-名次风格", bonus))
            reasons = list(item.reasons)
            reasons.append(note)
            adjusted.append(
                ScoredCandidate(
                    priority=item.priority,
                    candidate=item.candidate,
                    action_key=item.action_key,
                    parts=tuple(parts),
                    reasons=tuple(reasons),
                    total=round(item.total + bonus, 6),
                    shanten=item.shanten,
                    is_safe_discard=item.is_safe_discard,
                )
            )
        scored = adjusted
    for item in scored:
        if not math.isfinite(item.total) or any(not math.isfinite(part.value) for part in item.parts):
            raise ValueError("V1 评分非有限：{0}".format(item.action_key))
    return tuple(scored)
