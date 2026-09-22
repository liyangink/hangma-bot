"""有限一次摸牌分值事实；只在显式开启时为合法候选附加条件见证。

“候选生效、指定弃牌完成、单局未结束且本人未再行动”是共同前提。
本模块只检查随后一次普通摸牌或本次杠补能否立即胡；未见张数不是摸牌
概率。牌型、爆头生命周期、有财必拷响和结算分别复用既有规则源。
不构造未来 PlayerObservation 或 WinDescription，避免把假设伪装成事实。

固定工作量口径：每个等待手牌计一节点，任意听最多 34 次内部检查保守
预留 34 节点，每个未来牌值检查另计一节点。按整个 analyze 请求共用上限，
不访问时钟；截断或缺少链证据只影响可选分值事实，不改变合法候选。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Iterator, Optional, Tuple

from hangma_bot.kernel.actions import Chi, Discard, Gang, Hu, Pass, Peng, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation

from . import hand_analysis, progression, progression_payload, settlement, special_rules
from .action_families import WALL_RESERVE_TILES
from .candidate_facts import (
    FactsAnalysisError,
    _WaitingBasis,
    _claim_basis,
    _gang_basis,
    _remaining,
    _remove_codes,
)
from .interface import (
    CandidateFactKind,
    CandidateValueFacts,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
    Settlement,
    UsefulTileFact,
    ValueAnalysisLimits,
    ValueConditions,
    ValueCoverage,
    ValueRoute,
)
from .internal_types import Counts34, TILE_INDEX, TILE_ORDER, WindowContext, counts_from_tiles
from .public_tile_counts import PublicCounts34


class _LimitReached(Exception):
    """固定工作量或结果数量用尽；已证明的路线仍可保留为 PARTIAL。"""


class _Unavailable(Exception):
    """没有足够权威事实给候选作确定的条件结算。"""


@dataclass
class _ExpansionBudget:
    """一次请求共享的计数器；节点仅衡量规则工作量，不是时间或概率。"""

    limit: int
    used: int = 0

    def consume(self, count: int = 1) -> None:
        if self.used + count > self.limit:
            raise _LimitReached(
                "等待手牌/成胡检查达到上限；已用 {0}，请求 {1}，上限 {2}".format(
                    self.used, count, self.limit
                )
            )
        self.used += count


@dataclass(frozen=True)
class _ConditionalBasis:
    """动作完成后的一个摸前状态；不同吃碰后弃牌必须分别计值。"""

    waiting: _WaitingBasis
    followup: Optional[str]
    replacement: bool
    chain_count: int
    chain_piao: int


class _RouteGroups:
    """按同一弃牌、摸前状态和相同结算合并互斥进张；不合并不同选择。"""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.groups: Dict[Tuple[Settlement, ValueConditions, Optional[str]], list] = {}

    def add(
        self, result: Settlement, conditions: ValueConditions,
        followup: Optional[str], tile: UsefulTileFact,
    ) -> None:
        key = (result, conditions, followup)
        if key not in self.groups:
            if len(self.groups) >= self.limit:
                raise _LimitReached("本候选条件结算分组达到上限 {0}".format(self.limit))
            self.groups[key] = []
        self.groups[key].append(tile)

    def routes(self) -> Tuple[ValueRoute, ...]:
        return tuple(
            ValueRoute(
                conditional_settlement=result,
                shanten=0,
                useful_tiles=tuple(tiles),
                followup_discard=followup,
                conditions=conditions,
            )
            for (result, conditions, followup), tiles in self.groups.items()
        )


def _known_chain(observation: PlayerObservation) -> Tuple[int, int]:
    """链内飘次数必须已被观察补全，零链可直接证明 piao 为零。"""
    count = observation.rule_state.chain_count
    piao = observation.chain_piao
    if count == 0:
        return 0, 0
    if piao is None:
        raise _Unavailable("当前链内飘次数未知，无法确定保留该链的条件分值")
    return count, piao


def _discard_chain(observation: PlayerObservation, code: str) -> Tuple[int, int]:
    """普通弃牌能消除旧链的未知；飘白则必须保留精确旧链证据。"""
    tile = Tile(code)
    if special_rules.chain_breaks_on_discard(tile, observation.rule_state.baotou):
        return progression.chain_after_discard(
            observation.rule_state.chain_count, 0, observation.rule_state.baotou, tile
        )
    count, piao = _known_chain(observation)
    return progression.chain_after_discard(count, piao, observation.rule_state.baotou, tile)


def _bases(
    observation: PlayerObservation, context: WindowContext, meld_count: int,
    candidate: RuleCandidate,
) -> Iterator[_ConditionalBasis]:
    """只执行本人已选动作的机械移牌；不会读取或生成他家暗牌。"""
    action = candidate.action
    if isinstance(action, Discard):
        code = action.tile.code
        full = tuple(tile.code for tile in context.full_hand())
        if code not in full:
            raise FactsAnalysisError("弃牌不在当前暗牌全集中")
        count, piao = _discard_chain(observation, code)
        yield _ConditionalBasis(
            _WaitingBasis(
                tuple(Tile(c) for c in _remove_codes(full, {code: 1})), meld_count, {code: 1}
            ), None, False, count, piao,
        )
        return
    if isinstance(action, Pass):
        if (context.phase not in ("response_peng", "response_chi")
                or context.seat not in context.responding_seats
                or context.drawn_tile is not None):
            raise _Unavailable("过牌缺少本人响应窗口的摸前手牌语义")
        count, piao = _known_chain(observation)
        yield _ConditionalBasis(
            _WaitingBasis(context.hand_tiles, meld_count, {}), None, False, count, piao
        )
        return
    if isinstance(action, (Chi, Peng)):
        basis = _claim_basis(action, context, meld_count)
        codes = tuple(tile.code for tile in basis.hand_after)
        # v26 圈主有真实窗口即可吃碰；动作后直接是本人弃牌窗口，
        # 其间没有他家插入打白换主。本人仍是圈主，每个暗牌均可弃。
        # 吃碰保持原爆头与链；随后每个合法弃牌分别走同源弃牌边界。
        for code in sorted(set(codes), key=TILE_INDEX.get):
            count, piao = _discard_chain(observation, code)
            newly_public = dict(basis.newly_hidden)
            newly_public[code] = newly_public.get(code, 0) + 1
            yield _ConditionalBasis(
                _WaitingBasis(
                    tuple(Tile(c) for c in _remove_codes(codes, {code: 1})),
                    basis.melds, newly_public,
                ), code, False, count, piao,
            )
        return
    if isinstance(action, Gang):
        count, piao = progression.chain_after_gang(*_known_chain(observation))
        yield _ConditionalBasis(
            _gang_basis(action, context, meld_count), None, True, count, piao,
        )
        return
    raise _Unavailable("候选动作没有已支持的一次摸牌语义")


def _validate_basis(basis: _ConditionalBasis) -> Counts34:
    hand = basis.waiting.hand_after
    if len(hand) != 13 - 3 * basis.waiting.melds:
        raise FactsAnalysisError("摸前暗牌张数与动作后副露数不符")
    counts = counts_from_tiles(hand)
    if any(count > 4 for count in counts):
        raise FactsAnalysisError("摸前暗牌存在第五张同牌")
    if counts[TILE_INDEX["白"]] + basis.chain_piao > 4:
        raise FactsAnalysisError("摸前手留白板与链内飘白总数超过四张")
    return counts


def _known_not_ready(candidate: RuleCandidate) -> bool:
    """证明候选至少还差两次摸牌；吃碰仍逐一检查后续弃牌。

    杭麻白板是万能牌，且自然牌受四张物理上限约束。于是可能出现
    ``shanten_after == 1``、自然第五张不可得，但下一摸白板即可补成胡的
    状态；这类候选不能用根向听提前跳过，仍须枚举一次摸牌。只有向听
    严格大于 1 时，单张白板也不可能一次补齐。
    """
    facts = candidate.facts
    return (
        not isinstance(candidate.action, (Chi, Peng))
        and facts is not None
        and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
        and facts.completeness is RuleCompleteness.COMPLETE
        and facts.shanten_after is not None
        and facts.shanten_after > 1
    )


def _analyze_basis(
    basis: _ConditionalBasis, observation: PlayerObservation,
    public_counts: PublicCounts34, config: RuleConfig, budget: _ExpansionBudget,
    groups: _RouteGroups,
) -> None:
    counts = _validate_basis(basis)
    hand = basis.waiting.hand_after
    # baotou_after_draw 经 any_tile_win 最多做 34 次成胡检查；一次预留全部
    # 工作量，不能把内部循环藏在单个节点中。当前生命周期的爆头结果不随
    # 未来牌值改变，因此只调用一次；仍由该规则函数处理杠补继承。
    budget.consume(len(TILE_ORDER))
    representative = next(code for code in TILE_ORDER if counts[TILE_INDEX[code]] < 4)
    baotou = progression.baotou_after_draw(
        observation.rule_state.baotou, hand, basis.waiting.melds,
        Tile(representative), replacement=basis.replacement,
    )
    conditions = ValueConditions(
        draw_kind="replacement" if basis.replacement else "normal",
        pre_draw_hand=tuple(sorted((tile.code for tile in hand), key=TILE_INDEX.get)),
        meld_count=basis.waiting.melds,
        chain_count=basis.chain_count,
        chain_piao=basis.chain_piao,
        baotou=baotou,
    )
    # 本人已飘白与他家弃白必然是不同物理牌，只用本人旧牌河去重。
    # 取动作前的 piao：普通弃牌虽断链，也不能抹掉已经看见的白板；
    # 本动作新弃白已由 newly_hidden 扣除，不得抵消旧牌河中缺失的飘白。
    own_visible_whites = sum(tile.code == "白" for tile in observation.discards[observation.seat])
    missing_own_piao = max(0, (observation.chain_piao or 0) - own_visible_whites)
    for code in TILE_ORDER:
        budget.consume()
        # 未知公开重叠只影响需要该进张的路线，不能让无关牌种使整候选失效。
        # 已知耗尽仍先跳过，避免增加正常完整观察的成胡检查工作量。
        unseen = None
        if public_counts[TILE_INDEX[code]] is not None:
            unseen = _remaining(code, counts, public_counts, basis.waiting.newly_hidden)
            if code == "白":
                unseen -= missing_own_piao
            if unseen <= 0:
                continue
        elif counts[TILE_INDEX[code]] >= 4:
            continue
        split = hand_analysis.win_split(hand + (Tile(code),), basis.waiting.melds)
        if split is None or special_rules.you_cai_bi_kao_block(
            config.you_cai_bi_kao, split, baotou
        ):
            continue
        if unseen is None:
            raise _Unavailable("成胡进张 {0} 的牌河/副露重叠缺少供牌证据，剩余张数未知".format(code))
        result = settlement.settle_win(
            split, basis.chain_count, basis.chain_piao, baotou,
            config.base_score, observation.seat, observation.dealer_seat,
        )
        groups.add(result, conditions, basis.followup, UsefulTileFact(code, unseen))


def _for_candidate(
    observation: PlayerObservation, context: WindowContext, public_counts: PublicCounts34,
    meld_count: int, config: RuleConfig, candidate: RuleCandidate,
    limits: ValueAnalysisLimits, budget: _ExpansionBudget,
) -> CandidateValueFacts:
    groups = _RouteGroups(limits.max_routes_per_candidate)
    try:
        if isinstance(candidate.action, Hu):
            budget.consume()
            count, piao = _known_chain(observation)
            hand = context.full_hand()
            if len(hand) != 14 - 3 * meld_count:
                raise FactsAnalysisError("当前胡牌暗牌张数与副露数不符")
            split = hand_analysis.win_split(hand, meld_count)
            if split is None:
                raise FactsAnalysisError("合法 Hu 候选无法还原当前成胡分解")
            return CandidateValueFacts(
                immediate_settlement=settlement.settle_win(
                    split, count, piao, observation.rule_state.baotou,
                    config.base_score, observation.seat, observation.dealer_seat,
                ),
                coverage=ValueCoverage.COMPLETE,
            )
        # 与动作族及模拟推进共用保留区口径；最后可摸牌已摸完时，
        # 当前 Hu 仍可结算，但任何需要再摸一张的条件都不可能成立。
        if (observation.remaining_tile_count is not None
                and observation.remaining_tile_count <= WALL_RESERVE_TILES):
            return CandidateValueFacts(coverage=ValueCoverage.COMPLETE)
        # 非吃碰候选只有一个摸前状态，既有准确向听 >0 足以排除本范围，
        # 无须索取未来结算用不到的链细节。仍计一个等待手牌节点。
        if _known_not_ready(candidate):
            budget.consume()
            return CandidateValueFacts(coverage=ValueCoverage.COMPLETE)
        for basis in _bases(observation, context, meld_count, candidate):
            budget.consume()
            _analyze_basis(basis, observation, public_counts, config, budget, groups)
        return CandidateValueFacts(routes=groups.routes(), coverage=ValueCoverage.COMPLETE)
    except _LimitReached as exc:
        return CandidateValueFacts(
            routes=groups.routes(), coverage=ValueCoverage.PARTIAL,
            issues=(RuleIssue("value_analysis.limit", str(exc)),),
        )
    except _Unavailable as exc:
        return CandidateValueFacts(
            coverage=ValueCoverage.UNAVAILABLE,
            issues=(RuleIssue("value_analysis.missing_evidence", str(exc)),),
        )
    except Exception as exc:
        return CandidateValueFacts(
            coverage=ValueCoverage.UNAVAILABLE,
            issues=(RuleIssue(
                "value_analysis.failed", "{0}: {1}".format(type(exc).__name__, exc)
            ),),
        )


def attach_value_facts(
    observation: PlayerObservation, context: WindowContext, public_counts: PublicCounts34,
    meld_count: int, config: RuleConfig, candidates: Tuple[RuleCandidate, ...],
    limits: ValueAnalysisLimits,
) -> Tuple[RuleCandidate, ...]:
    """附加有界分值事实与分支进展载荷；保持动作、动作键、证据不变。

    输入必须是同一观察生成的候选及已归一化上下文；全请求共享固定预算。
    各候选分别隔离异常，缺失证据与截断原因保存在 value_facts.issues。
    进展载荷（family_progress）与分值分析共享同一预算：动作前状态一次
    手牌分析计 1 节点、每候选载荷计 1 节点，超限降级为 UNKNOWN 条目并
    追加 progression_payload.limit RuleIssue，不截断冒充完整；载荷异常
    向上传播，由 engine 故障边界收敛（合法候选与紧急动作保留）。
    本函数无外部副作用，故障不影响规则合法性或独立紧急动作。
    """
    budget = _ExpansionBudget(limits.max_expansions)
    payload_state = None
    payload_state_error = None
    attached = []
    for candidate in candidates:
        value_facts = _for_candidate(
            observation, context, public_counts, meld_count, config,
            candidate, limits, budget,
        )
        # ---- 分支进展载荷（v4 §7.3）：先建一次共享的动作前状态 ----
        # 意外异常包装为 ProgressionPayloadError：engine 对载荷失败单独记
        # RuleIssue（DEGRADED）；可选分值分析自身的失败口径保持不变。
        if payload_state is None and payload_state_error is None:
            try:
                budget.consume()
                payload_state = progression_payload.BeforeState(
                    observation, context, meld_count
                )
            except _LimitReached as exc:
                payload_state_error = str(exc)
            except Exception as exc:
                raise progression_payload.ProgressionPayloadError(
                    "动作前状态构建失败: {0}: {1}".format(type(exc).__name__, exc)
                ) from exc
        if payload_state is not None:
            try:
                budget.consume()
            except _LimitReached as exc:
                value_facts, facts = progression_payload.attach_unknown_payload(
                    candidate, value_facts, str(exc)
                )
            else:
                try:
                    value_facts, facts = progression_payload.attach_payload(
                        payload_state, candidate, value_facts
                    )
                except _LimitReached as exc:
                    value_facts, facts = progression_payload.attach_unknown_payload(
                        candidate, value_facts, str(exc)
                    )
                except Exception as exc:
                    raise progression_payload.ProgressionPayloadError(
                        "候选 {key} 进展计算失败: {t}: {m}".format(
                            key=candidate.action_key, t=type(exc).__name__, m=exc
                        )
                    ) from exc
        else:
            value_facts, facts = progression_payload.attach_unknown_payload(
                candidate, value_facts,
                payload_state_error or "动作前状态未建立（预算超限）",
            )
        if facts is candidate.facts:
            attached.append(replace(candidate, value_facts=value_facts))
        else:
            attached.append(
                replace(candidate, value_facts=value_facts, facts=facts)
            )
    return tuple(attached)
