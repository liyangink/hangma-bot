"""分层评分：把规则候选映射为可审计的分项与中文原因。

只消费 PlayerObservation 与规则候选，不判断合法性；
动作后状态一律用“等待状态估计”表达（弃牌后 13 张等效、
鸣牌/杠后按最佳后续弃牌估计），保证各动作族可公平比较。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, FrozenSet, List, Optional, Tuple

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.kernel.actions import Action, Chi, Discard, Gang, GangKind, Hu, Pass, Peng
from hangma_bot.kernel.observation import PlayerObservation

from .errors import PolicyError
from .hand_estimate import ALL_CODES, HandEstimate, estimate_hand, effective_tiles, tile_sort_key
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
    meld_blocks: int  # 本人已副露面子数（吃/碰/杠各 1 个，补杠不增加）
    wealth_code: str  # 财神牌码（本项目规则为白板）
    visible_others: Dict[str, int]  # 四家牌河与副露中的可见牌计数（不含本人手牌）
    safe_codes: FrozenSet[str]  # 已见于他家牌河的牌码（熟张）
    my_seat: int
    next_seat: int  # 下家座位 = (本座位 + 1) % 4
    next_seat_meld_codes: Tuple[str, ...]  # 下家副露全部牌码
    dealer_seat: int
    dealer_meld_codes: Tuple[str, ...]  # 庄家副露全部牌码
    table_rank: int  # 桌内名次，1 为领先；同分时并列名次按严格大于计数
    catch_play: bool  # 是否处于抓打圈


@dataclass(frozen=True)
class WaitingEstimate:
    """动作后等待状态的完整估计。"""

    estimate: HandEstimate
    effective_kinds: int
    effective_weight: float
    effective_samples: Tuple[str, ...]


@dataclass(frozen=True)
class ScoredCandidate:
    """单候选的评分中间结果；由策略层补齐排名并组装计划。"""

    candidate: RuleCandidate
    action_key: str
    parts: Tuple[ScorePart, ...]
    reasons: Tuple[str, ...]
    total: float
    shanten: int  # 动作后向听估计；胡牌记 -1，供名次风格层比较
    is_safe_discard: bool  # 是否为熟张弃牌，供名次风格层加成


def build_context(observation: PlayerObservation) -> EvaluationContext:
    """从玩家观察构建评分上下文；不做任何合法性判断。"""

    combined: List[str] = [tile.code for tile in observation.my_hand]
    if observation.drawn_tile is not None:
        combined.append(observation.drawn_tile.code)

    visible: Dict[str, int] = {}
    for river in observation.discards:
        for tile in river:
            visible[tile.code] = visible.get(tile.code, 0) + 1
    meld_codes_by_seat: List[Tuple[str, ...]] = []
    for seat_melds in observation.melds:
        seat_codes: List[str] = []
        for meld in seat_melds:
            for tile in meld.tiles:
                visible[tile.code] = visible.get(tile.code, 0) + 1
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
        meld_blocks=len(observation.melds[my_seat]),
        wealth_code=observation.rule_state.wealth_god.code,
        visible_others=visible,
        safe_codes=safe_codes,
        my_seat=my_seat,
        next_seat=next_seat,
        next_seat_meld_codes=meld_codes_by_seat[next_seat],
        dealer_seat=observation.dealer_seat,
        dealer_meld_codes=meld_codes_by_seat[observation.dealer_seat],
        table_rank=table_rank,
        catch_play=observation.rule_state.catch_play,
    )


def _remove_codes(codes: Tuple[str, ...], removal: Dict[str, int]) -> Tuple[str, ...]:
    """按牌码计数从序列中移除指定张数；调用方保证数量充足。"""

    pending = dict(removal)
    kept: List[str] = []
    for code in codes:
        leave = pending.get(code, 0)
        if leave > 0:
            pending[code] = leave - 1
            continue
        kept.append(code)
    return tuple(kept)


def _remaining_for_state(
    ctx: EvaluationContext,
    hand_after: Tuple[str, ...],
    newly_hidden: Dict[str, int],
) -> Dict[str, int]:
    """计算动作后每种牌对我方仍可摸到的剩余张数（0-4）。

    newly_hidden 是动作中离开手牌、但尚未出现在旧公开区 snapshot 里的牌：
    候选弃牌进入本人牌河、吃/碰/杠移出的自有牌进入新副露。
    漏扣会把已公开的牌误当成仍在牌墙（专家审查 F6）。
    """

    hand_counts: Dict[str, int] = {}
    for code in hand_after:
        hand_counts[code] = hand_counts.get(code, 0) + 1
    remaining: Dict[str, int] = {}
    # 必须覆盖全部 34 种牌码：完全未见的牌剩余张数是 4，而不是 0。
    for code in ALL_CODES:
        hidden = (
            ctx.visible_others.get(code, 0)
            + hand_counts.get(code, 0)
            + newly_hidden.get(code, 0)
        )
        remaining[code] = max(0, 4 - hidden)
    return remaining


def _waiting_estimate(
    ctx: EvaluationContext,
    hand_after: Tuple[str, ...],
    meld_blocks: int,
    newly_hidden: Dict[str, int],
) -> WaitingEstimate:
    """估计一个等待状态（13 张等效）的向听、有效牌与结构。"""

    estimate = estimate_hand(hand_after, meld_blocks, ctx.wealth_code)
    remaining = _remaining_for_state(ctx, hand_after, newly_hidden)
    kinds, weight, samples = effective_tiles(hand_after, meld_blocks, ctx.wealth_code, remaining)
    return WaitingEstimate(
        estimate=estimate,
        effective_kinds=kinds,
        effective_weight=round(weight, 1),
        effective_samples=samples,
    )


def _best_followup(
    ctx: EvaluationContext,
    hand: Tuple[str, ...],
    meld_blocks: int,
    action_key: str,
) -> Tuple[WaitingEstimate, str]:
    """为碰/吃后的手牌估计最佳后续弃牌；用于与直接弃牌公平比较。

    选择键为 (向听, -有效牌权重, 牌码)，完全确定。
    碰/吃后手牌为 14 张等效（必然再弃一张），因此估计后续弃牌；
    杠后手牌已是 13 张等效等待态，不再假设弃牌（专家审查 F7）。
    """

    best: Optional[Tuple[Tuple[int, float, str], WaitingEstimate, str]] = None
    for code in sorted(set(hand), key=tile_sort_key):
        after = _remove_codes(hand, {code: 1})
        estimate = _waiting_estimate(ctx, after, meld_blocks, {code: 1})
        order_key = (estimate.estimate.shanten, -estimate.effective_weight, code)
        if best is None or order_key < best[0]:
            best = (order_key, estimate, code)
    if best is None:
        raise PolicyError(
            "候选 {key} 鸣牌后手牌为空，无法估计后续弃牌".format(key=action_key)
        )
    return best[1], best[2]


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


def _chi_removal(action: Chi, claimed_code: Optional[str]) -> Dict[str, int]:
    """计算吃牌需要从手牌移除的牌：顺子三张中除去被吃牌。"""

    counts: Dict[str, int] = {}
    for tile in action.tiles:
        counts[tile.code] = counts.get(tile.code, 0) + 1
    if claimed_code is not None and counts.get(claimed_code, 0) > 0:
        counts[claimed_code] -= 1
    else:
        # 无法确定被吃牌时按字典序最大牌码扣除一张，保持确定性。
        counts[sorted(counts)[-1]] -= 1
    return {code: count for code, count in counts.items() if count > 0}


def _after_state(
    action: Action,
    ctx: EvaluationContext,
    claimed_code: Optional[str],
) -> Optional[Tuple[Tuple[str, ...], int, Dict[str, int], bool]]:
    """把动作映射为动作后状态。

    返回 (手牌牌码, 面子数, 新离开手牌的隐藏牌计数, 是否需要后续弃牌估计)；
    返回 None 表示该动作不适用等待状态框架（当前只有胡牌）。
    杠后手牌已是 13 张等效等待态（替换摸牌未知），直接评估、
    不再假设先弃一张（专家审查 F7）。
    """

    if isinstance(action, Discard):
        return (
            _remove_codes(ctx.combined_codes, {action.tile.code: 1}),
            ctx.meld_blocks,
            {action.tile.code: 1},
            False,
        )
    if isinstance(action, Peng):
        return (
            _remove_codes(ctx.combined_codes, {action.tile.code: 2}),
            ctx.meld_blocks + 1,
            {action.tile.code: 2},
            True,
        )
    if isinstance(action, Chi):
        removal = _chi_removal(action, claimed_code)
        return (
            _remove_codes(ctx.combined_codes, removal),
            ctx.meld_blocks + 1,
            dict(removal),
            True,
        )
    if isinstance(action, Gang):
        if action.kind == GangKind.CONCEALED:
            removal, melds = {action.tile.code: 4}, ctx.meld_blocks + 1
        elif action.kind == GangKind.EXPOSED:
            removal, melds = {action.tile.code: 3}, ctx.meld_blocks + 1
        else:
            # 补杠是碰的升级，面子数不变，只从手牌移除一张。
            removal, melds = {action.tile.code: 1}, ctx.meld_blocks
        return _remove_codes(ctx.combined_codes, removal), melds, dict(removal), False
    if isinstance(action, Pass):
        return ctx.combined_codes, ctx.meld_blocks, {}, False
    return None


def _common_parts(
    weights: HeuristicWeights,
    waiting: WaitingEstimate,
) -> Tuple[List[ScorePart], List[str]]:
    """第三到第五层的公共分项：向听、有效牌、成牌收益与灵活度。"""

    parts = [
        ScorePart("第三层-向听数", -weights.shanten_step * waiting.estimate.shanten),
        ScorePart("第四层-有效牌", round(weights.effective_tile * waiting.effective_weight, 1)),
        ScorePart("第四层-成牌收益", weights.win_potential * waiting.estimate.wildcard_count),
        ScorePart("第五层-灵活度", weights.flexibility * waiting.estimate.flexibility),
    ]
    reasons = [waiting.estimate.summary]
    if waiting.effective_kinds > 0:
        reasons.append(
            "有效牌{kinds}种、加权{weight:.1f}张（样例：{samples}）".format(
                kinds=waiting.effective_kinds,
                weight=waiting.effective_weight,
                samples="、".join(waiting.effective_samples),
            )
        )
    return parts, reasons


def _score_one(
    candidate: RuleCandidate,
    ctx: EvaluationContext,
    weights: HeuristicWeights,
    claimed_code: Optional[str],
) -> ScoredCandidate:
    """给单个规则候选打分；合法性由规则模块保证，本函数不复判。"""

    action = candidate.action
    parts: List[ScorePart] = []
    reasons: List[str] = []
    shanten = 8
    is_safe_discard = False

    if isinstance(action, Hu):
        parts.append(ScorePart("第一层-立即胡牌", weights.win_now))
        reasons.append("规则确认当前可胡：第一阶段保守策略立即胡牌")
        if candidate.evidence:
            reasons.append("胡牌证据：{evidence}".format(evidence="；".join(candidate.evidence[:2])))
        shanten = -1
    else:
        after = _after_state(action, ctx, claimed_code)
        if after is None:
            # 未知动作族按保守零分参与排序，不丢弃候选。
            parts.append(ScorePart("第二层-保守兜底", 0.0))
            reasons.append("未知动作族：按保守零分参与排序")
        else:
            hand_after, meld_blocks, newly_hidden, needs_followup = after
            if needs_followup:
                waiting, followup = _best_followup(ctx, hand_after, meld_blocks, candidate.action_key)
            else:
                waiting = _waiting_estimate(ctx, hand_after, meld_blocks, newly_hidden)
                followup = None
            shanten = waiting.estimate.shanten
            common_parts, common_reasons = _common_parts(weights, waiting)
            parts.extend(common_parts)
            reasons.extend(common_reasons)

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
                        parts.append(ScorePart("第六层-喂牌风险", -round(weights.feed_risk * risk_units, 1)))
                        reasons.append("生张{code}：{notes}".format(code=code, notes="、".join(risk_notes)))
                if ctx.catch_play:
                    reasons.append("抓打圈生效：仅规则允许的弃牌参与排序")
            elif isinstance(action, Peng):
                parts.append(ScorePart("第六层-鸣牌风险", -weights.claim_risk_peng))
                reasons.append(
                    "碰{code}后按最佳弃牌{followup}估计".format(code=action.tile.code, followup=followup)
                )
            elif isinstance(action, Chi):
                parts.append(ScorePart("第六层-鸣牌风险", -weights.claim_risk_chi))
                reasons.append(
                    "吃{tiles}后按最佳弃牌{followup}估计".format(
                        tiles="、".join(tile.code for tile in action.tiles),
                        followup=followup,
                    )
                )
            elif isinstance(action, Gang):
                parts.append(ScorePart("第二层-杠收益", weights.gang_bonus))
                reasons.append(
                    "{kind}{code}：保留结构并积累番值潜力，按杠后余牌保守估计（替换摸牌未知）".format(
                        kind=_GANG_KIND_NAMES[action.kind],
                        code=action.tile.code,
                    )
                )
            elif isinstance(action, Pass):
                reasons.append("过：保持手牌不暴露信息")

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
    last_discard_code: Optional[str],
    check_deadline: Callable[[], Awaitable[None]],
) -> Tuple[ScoredCandidate, ...]:
    """给全部入围候选打分，并应用第七层名次风格调整。

    last_discard_code 是最近公开弃牌牌码（响应窗口吃/碰/明杠的标的）。
    check_deadline 是异步截止检查：每个候选评分前等待一次事件循环，
    保证应用层的 wait_for 能在保底截止时间抢占本协程（专家审查 F1），
    超时抛 PolicyTimeoutError。
    """

    scored = []
    for candidate in candidates:
        await check_deadline()
        scored.append(_score_one(candidate, ctx, weights, last_discard_code))

    if scored:
        best_shanten = min(item.shanten for item in scored)
        adjusted: List[ScoredCandidate] = []
        for item in scored:
            if not isinstance(item.candidate.action, Discard):
                adjusted.append(item)
                continue
            bonus = 0.0
            note = ""
            if ctx.table_rank == 1 and item.is_safe_discard:
                bonus, note = weights.style_adjust, "桌内领先：保守风格优先熟张"
            elif ctx.table_rank == 4 and item.shanten == best_shanten:
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
