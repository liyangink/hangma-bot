"""分层评分：把规则候选映射为可审计的分项与中文原因。

2026-09-04 集成阶段契约收口（doc/implementation/interface-contracts.md §4.1）：
向听与有效牌数学只存在于 hangma。本模块只消费 RuleCandidate.facts
（规则引擎生产的 CandidateFacts）做第三/四层加权，不重新推演手牌合法性、
向听或有效牌；facts=None（紧急路径或未覆盖动作族）按未知处理，不推断
任何数值。熟张/喂牌风险/财神保留等可见信息的机械计数与名次风格调整
照常在此计算，不涉及规则数学。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, FrozenSet, List, Optional, Tuple

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    RuleCandidate,
)
from hangma_bot.kernel.actions import Action, Chi, Discard, Gang, GangKind, Hu, Pass, Peng
from hangma_bot.kernel.observation import PlayerObservation

from .interface import ScorePart
from .weights import HeuristicWeights

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


@dataclass(frozen=True)
class ScoredCandidate:
    """单候选的评分中间结果；由策略层补齐排名并组装计划。"""

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

    return EvaluationContext(
        combined_codes=tuple(combined),
        wealth_code=observation.rule_state.wealth_god.code,
        safe_codes=safe_codes,
        my_seat=my_seat,
        next_seat=next_seat,
        next_seat_meld_codes=meld_codes_by_seat[next_seat],
        dealer_seat=observation.dealer_seat,
        dealer_meld_codes=meld_codes_by_seat[observation.dealer_seat],
        table_rank=table_rank,
        catch_play=observation.rule_state.catch_play,
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
    facts: CandidateFacts, weights: HeuristicWeights
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


def _score_one(
    candidate: RuleCandidate,
    ctx: EvaluationContext,
    weights: HeuristicWeights,
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

    if isinstance(action, Hu):
        # 胡牌候选的存在本身就是规则确认的事实；立即胡牌无需牌效数值。
        parts.append(ScorePart("第一层-立即胡牌", weights.win_now))
        reasons.append("规则确认当前可胡：第一阶段保守策略立即胡牌")
        if candidate.evidence:
            reasons.append(
                "胡牌证据：{evidence}".format(
                    evidence="；".join(candidate.evidence[:2])
                )
            )
        shanten = -1
    elif facts is None:
        parts.append(ScorePart("第二层-保守兜底", 0.0))
        reasons.append(
            "牌效事实未生产（紧急路径或动作族未覆盖）：按未知处理，不推断向听/有效牌"
        )
    elif facts.fact_kind is CandidateFactKind.WIN:
        parts.append(ScorePart("第一层-立即胡牌", weights.win_now))
        reasons.append("规则确认当前可胡（WIN 事实）：第一阶段保守策略立即胡牌")
        shanten = -1
    elif facts.fact_kind is CandidateFactKind.HAND_PROGRESS:
        progress_parts, progress_reasons, shanten = _progress_parts(facts, weights)
        parts.extend(progress_parts)
        reasons.extend(progress_reasons)
    elif facts.fact_kind is CandidateFactKind.NOT_APPLICABLE:
        parts.append(ScorePart("第二层-保守兜底", 0.0))
        reasons.append("过：无动作后等待语义（NOT_APPLICABLE），保持手牌不暴露信息")
    elif facts.fact_kind is CandidateFactKind.ANALYSIS_FAILED:
        parts.append(ScorePart("第二层-保守兜底", 0.0))
        reasons.append(
            "牌效分析失败：{note}".format(note=facts.note or "未给出原因")
        )
    else:
        parts.append(ScorePart("第二层-保守兜底", 0.0))
        reasons.append("未知牌效事实种类：按保守零分参与排序")

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
    weights: HeuristicWeights,
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
    return tuple(scored)

