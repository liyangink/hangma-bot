"""R17 固定公开后继归约：候选只评分单叶，不能改搜索或删分支。

本模块不计算牌型、向听、有效牌、合法性或未来概率。全部规则事实来自
``DecisionRequest.rules`` 与 ``PublicSuccessorAnalysis``；后者由
``HangmaRules`` 生成并携带完整正容量边承诺。候选评分器只接收
``LeafView``，返回 [-1, 1] 的有限数。

固定归约分三层：

1. 同一条件摸牌和同一抓打包络中，胡恒优先；否则选择候选评分最高的
   弃牌。未来墙余是否仍允许杠未知，故“无条件杠”和“允许条件杠”形成
   一个上下界，而不是把杠当成必然可用。
2. 抓打圈未来归属未知，受限／不受限两个包络继续合成上下界；候选不能
   选择较有利包络。
3. 有未来摸牌时，每根在全部正公开容量边上计算容量重数加权的上下界。
   该重数不是摸牌概率。最后 20 张保留区已经到达时，完整空图归约为
   全零同层，严格保持稳定 V2 次序。根之间用 (条件胡净分支撑量, 下界,
   上界) 的 Pareto 层排序；同层保持稳定 V2 次序，不引入未经校验的插值权重。

任一事实缺失、容量承诺不一致、工作量超界或候选异常都会使整窗归约
不可用，调用方必须精确回退稳定 V2，不能把未知根当成零分。
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Dict, Optional, Tuple

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    FamilyProgress,
    PublicSuccessorAnalysis,
    PublicSuccessorCoverage,
    PublicSuccessorEnvelope,
    PublicSuccessorEnvelopeKind,
    PublicSuccessorLeaf,
    PublicSuccessorRoot,
    RuleCandidate,
    RuleCompleteness,
    ValueCoverage,
)
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, Discard

from .action_value import CompetitionView
from .action_value_policy import _competition_view
from .evaluation_v1 import build_context
from .interface import DecisionRequest


LEAF_VIEW_SCHEMA_VERSION = "r17-public-successor-leaf/1"
# 结构上限，不再用开发样本分位数充当正确性门：一个摸牌窗口至多有
# 14 个不同弃牌根、34 种条件摸牌、2 个抓打包络；每个包络至多保留
# 14 个弃牌前沿叶和 4 个杠叶。候选的真实计算成本另由逐叶 2,048 与
# 整窗 500,000 计费操作上限约束。
MAX_DISCARD_ROOTS_PER_WINDOW = 14
MAX_DRAW_EDGES_PER_ROOT = 34
MAX_ENVELOPES_PER_EDGE = 2
MAX_NEXT_ACTION_LEAVES_PER_ENVELOPE = 18
MAX_LEAF_EVALUATIONS = (
    MAX_DISCARD_ROOTS_PER_WINDOW
    * MAX_DRAW_EDGES_PER_ROOT
    * MAX_ENVELOPES_PER_EDGE
    * MAX_NEXT_ACTION_LEAVES_PER_ENVELOPE
)
LEAF_SCORE_MIN = -1.0
LEAF_SCORE_MAX = 1.0
TERMINAL_HU_SCORE = 1.0


@dataclass(frozen=True)
class SearchWindowView:
    """一个搜索窗口内共享的可见上下文；不含面板身份或效果标签。"""

    seat: int
    dealer_seat: int
    round_no: int
    table_scores: Tuple[int, int, int, int]
    table_rank: int
    competition: CompetitionView
    chain_count: int
    baotou: bool
    wealth_count: int
    chain_piao: Optional[int]
    remaining_tile_count: Optional[int]
    catch_play: bool
    catch_play_owner_seat: Optional[int]


@dataclass(frozen=True)
class FamilyProgressView:
    """候选根的家族进展枚举；省略人读依据字符串。"""

    family: str
    progress: str
    route_status: str


@dataclass(frozen=True)
class SearchRootView:
    """当前合法弃牌根的原始规则事实。"""

    action_key: str
    discard_code: str
    shanten_after: int
    standard_shanten_after: int
    seven_pairs_shanten_after: Optional[int]
    useful_mask: int
    useful_remaining_packed: int
    useful_tile_count: int
    support_remaining: int
    family_progress: Tuple[FamilyProgressView, ...]
    value_coverage: str


@dataclass(frozen=True)
class LeafView:
    """候选可读的单个后继动作叶；所有字段来自冻结公开事实。"""

    schema_version: str
    window: SearchWindowView
    root: SearchRootView
    draw_code: str
    draw_capacity: int
    draw_is_currently_useful: bool
    envelope_kind: str
    next_action_key: str
    next_action_type: str
    shanten_after: int
    standard_shanten_after: int
    seven_pairs_shanten_after: Optional[int]
    useful_mask: int
    useful_remaining_packed: int
    useful_tile_count: int
    support_remaining: int
    replacement_draw_unknown: bool
    requires_future_wall_gt20: bool


@dataclass(frozen=True)
class RootSearchScore:
    """固定归约后的根区间；support 字样均不表示真实概率。"""

    action_key: str
    lower_support_score: float
    upper_support_score: float
    conditional_hu_net_support: float
    conditional_hu_capacity: int
    capacity_total: int
    leaf_evaluations: int

    @property
    def dominance_vector(self) -> Tuple[float, float, float]:
        return (
            self.conditional_hu_net_support,
            self.lower_support_score,
            self.upper_support_score,
        )


@dataclass(frozen=True)
class SearchReduction:
    """整窗归约结果；``complete=False`` 时 roots 必须为空并回退 V2。"""

    complete: bool
    roots: Tuple[RootSearchScore, ...]
    reason: Optional[str]

    def __post_init__(self) -> None:
        if self.complete:
            if not self.roots or self.reason is not None:
                raise ValueError("完整搜索归约必须携带根且没有失败原因")
        elif self.roots or not self.reason:
            raise ValueError("不完整搜索归约必须为空并说明原因")


LeafScorer = Callable[[LeafView], float]


class _EvaluationCounter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def score(self, scorer: LeafScorer, view: LeafView) -> float:
        if self.used >= self.limit:
            raise ValueError("叶评分次数超过固定上限 {0}".format(self.limit))
        self.used += 1
        value = scorer(view)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("叶评分器必须返回数值")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("叶评分器返回非有限数")
        if not LEAF_SCORE_MIN <= value <= LEAF_SCORE_MAX:
            raise ValueError("叶评分必须在 [-1, 1] 内")
        return value


def _pack_useful_tiles(tiles) -> Tuple[int, int, int, int]:
    mask = 0
    packed = 0
    support = 0
    seen = set()
    for tile in tiles:
        if tile.code in seen:
            raise ValueError("根有效牌不得重复")
        seen.add(tile.code)
        index = CANONICAL_TILE_INDEX[tile.code]
        mask |= 1 << index
        packed |= tile.remaining_estimate << (index * 3)
        support += tile.remaining_estimate
    return mask, packed, len(tiles), support


def _family_view(entries: Tuple[FamilyProgress, ...]) -> Tuple[FamilyProgressView, ...]:
    return tuple(
        FamilyProgressView(
            family=item.family.value,
            progress=item.progress.value,
            route_status=item.route_status.value,
        )
        for item in entries
    )


def _root_view(candidate: RuleCandidate, root: PublicSuccessorRoot) -> SearchRootView:
    facts = candidate.facts
    if (
        facts is None
        or facts.completeness is not RuleCompleteness.COMPLETE
        or facts.fact_kind is not CandidateFactKind.HAND_PROGRESS
        or facts.shanten_after is None
        or facts.standard_shanten_after is None
        or facts.shanten_after != root.shanten_after
    ):
        raise ValueError("弃牌根缺少与后继根一致的完整 HAND_PROGRESS 事实")
    useful_mask, useful_packed, useful_count, support = _pack_useful_tiles(
        facts.useful_tiles
    )
    coverage = (
        "none"
        if candidate.value_facts is None
        else candidate.value_facts.coverage.value
    )
    return SearchRootView(
        action_key=candidate.action_key,
        discard_code=root.discard_code,
        shanten_after=facts.shanten_after,
        standard_shanten_after=facts.standard_shanten_after,
        seven_pairs_shanten_after=facts.seven_pairs_shanten_after,
        useful_mask=useful_mask,
        useful_remaining_packed=useful_packed,
        useful_tile_count=useful_count,
        support_remaining=support,
        family_progress=_family_view(facts.family_progress),
        value_coverage=coverage,
    )


def _window_view(request: DecisionRequest) -> SearchWindowView:
    visible = build_context(request.observation)
    observation = request.observation
    return SearchWindowView(
        seat=observation.seat,
        dealer_seat=observation.dealer_seat,
        round_no=observation.round_no,
        table_scores=tuple(int(item) for item in observation.scores),
        table_rank=visible.table_rank,
        competition=_competition_view(
            request.competition, observation.seat, observation.scores
        ),
        chain_count=visible.chain_count,
        baotou=visible.baotou,
        wealth_count=visible.wealth_count,
        chain_piao=visible.chain_piao,
        remaining_tile_count=visible.remaining_tile_count,
        catch_play=visible.catch_play,
        catch_play_owner_seat=visible.catch_play_owner_seat,
    )


def _leaf_view(
    window: SearchWindowView,
    root: SearchRootView,
    draw_code: str,
    draw_capacity: int,
    draw_is_currently_useful: bool,
    envelope_kind: PublicSuccessorEnvelopeKind,
    leaf: PublicSuccessorLeaf,
) -> LeafView:
    return LeafView(
        schema_version=LEAF_VIEW_SCHEMA_VERSION,
        window=window,
        root=root,
        draw_code=draw_code,
        draw_capacity=draw_capacity,
        draw_is_currently_useful=draw_is_currently_useful,
        envelope_kind=envelope_kind.value,
        next_action_key=leaf.action_key,
        next_action_type=leaf.action_type,
        shanten_after=leaf.shanten_after,
        standard_shanten_after=leaf.standard_shanten_after,
        seven_pairs_shanten_after=leaf.seven_pairs_shanten_after,
        useful_mask=leaf.useful_mask,
        useful_remaining_packed=leaf.useful_remaining_packed,
        useful_tile_count=leaf.useful_tile_count,
        support_remaining=leaf.support_remaining,
        replacement_draw_unknown=leaf.replacement_draw_unknown,
        requires_future_wall_gt20=leaf.requires_future_wall_gt20,
    )


def _envelope_bounds(
    envelope: PublicSuccessorEnvelope,
    *,
    window: SearchWindowView,
    root: SearchRootView,
    draw_code: str,
    draw_capacity: int,
    draw_is_currently_useful: bool,
    scorer: LeafScorer,
    counter: _EvaluationCounter,
) -> Tuple[float, float]:
    if envelope.hu_available:
        return TERMINAL_HU_SCORE, TERMINAL_HU_SCORE
    if not envelope.discard_frontier:
        raise ValueError("非胡后继包络没有弃牌 Pareto 叶")
    discard_scores = tuple(
        counter.score(
            scorer,
            _leaf_view(
                window,
                root,
                draw_code,
                draw_capacity,
                draw_is_currently_useful,
                envelope.kind,
                leaf,
            ),
        )
        for leaf in sorted(envelope.discard_frontier, key=lambda item: item.action_key)
    )
    without_conditional_gang = max(discard_scores)
    with_conditional_gang = without_conditional_gang
    for leaf in sorted(envelope.gang_leaves, key=lambda item: item.action_key):
        if not leaf.requires_future_wall_gt20:
            raise ValueError("后继杠叶缺少未来墙余条件")
        with_conditional_gang = max(
            with_conditional_gang,
            counter.score(
                scorer,
                _leaf_view(
                    window,
                    root,
                    draw_code,
                    draw_capacity,
                    draw_is_currently_useful,
                    envelope.kind,
                    leaf,
                ),
            ),
        )
    return without_conditional_gang, with_conditional_gang


def _hu_routes(
    candidate: RuleCandidate,
    root: PublicSuccessorRoot,
    seat: int,
) -> Dict[str, Tuple[float, int]]:
    hu_edges = {
        edge.draw_tile.code: edge
        for edge in root.edges
        if edge.restricted.hu_available or edge.unrestricted.hu_available
    }
    if not hu_edges:
        return {}
    facts = candidate.value_facts
    if facts is None or facts.coverage is not ValueCoverage.COMPLETE:
        raise ValueError("存在条件胡边但根缺少 COMPLETE ValueRoute")
    result: Dict[str, Tuple[float, int]] = {}
    for route in facts.routes:
        if route.conditions.draw_kind != "normal" or route.followup_discard is not None:
            continue
        winner_score = route.conditional_settlement.score_delta[seat]
        if (
            isinstance(winner_score, bool)
            or not isinstance(winner_score, (int, float))
            or not math.isfinite(winner_score)
            or winner_score <= 0
        ):
            raise ValueError("条件胡路线的本人净分必须为正有限数")
        for tile in route.useful_tiles:
            if tile.remaining_estimate <= 0:
                continue
            if tile.code in result:
                raise ValueError("同一条件摸牌不能跨 ValueRoute 重复")
            result[tile.code] = (float(winner_score), tile.remaining_estimate)
    for code, edge in hu_edges.items():
        matched = result.get(code)
        if matched is None:
            raise ValueError("条件胡边缺少对应 ValueRoute: " + code)
        if matched[1] != edge.draw_tile.remaining_estimate:
            raise ValueError("条件胡边容量与 ValueRoute 不一致: " + code)
        if not (edge.restricted.hu_available and edge.unrestricted.hu_available):
            raise ValueError("同一条件摸牌的双包络胡资格不一致")
    for code in result:
        if code not in hu_edges:
            raise ValueError("ValueRoute 条件胡没有对应后继胡边: " + code)
    return result


def _reduce_root(
    candidate: RuleCandidate,
    root: PublicSuccessorRoot,
    window: SearchWindowView,
    scorer: LeafScorer,
    counter: _EvaluationCounter,
) -> RootSearchScore:
    root_view = _root_view(candidate, root)
    routes = _hu_routes(candidate, root, window.seat)
    edge_rows = []
    hu_net_support = 0.0
    hu_capacity = 0
    start_count = counter.used
    for edge in sorted(root.edges, key=lambda item: CANONICAL_TILE_INDEX[item.draw_tile.code]):
        restricted = _envelope_bounds(
            edge.restricted,
            window=window,
            root=root_view,
            draw_code=edge.draw_tile.code,
            draw_capacity=edge.draw_tile.remaining_estimate,
            draw_is_currently_useful=edge.is_currently_useful,
            scorer=scorer,
            counter=counter,
        )
        unrestricted = _envelope_bounds(
            edge.unrestricted,
            window=window,
            root=root_view,
            draw_code=edge.draw_tile.code,
            draw_capacity=edge.draw_tile.remaining_estimate,
            draw_is_currently_useful=edge.is_currently_useful,
            scorer=scorer,
            counter=counter,
        )
        lower = min(restricted + unrestricted)
        upper = max(restricted + unrestricted)
        capacity = edge.draw_tile.remaining_estimate
        edge_rows.append((edge.draw_tile.code, capacity, lower, upper))
        route = routes.get(edge.draw_tile.code)
        if route is not None:
            hu_net_support += capacity * route[0]
            hu_capacity += capacity
    if not edge_rows:
        if (
            root.edge_capacity_mask
            or root.edge_capacity_packed
            or root.edge_capacity_total
        ):
            raise ValueError("完整空后继根携带非零容量承诺")
        return RootSearchScore(
            action_key=root.action_key,
            lower_support_score=0.0,
            upper_support_score=0.0,
            conditional_hu_net_support=0.0,
            conditional_hu_capacity=0,
            capacity_total=0,
            leaf_evaluations=0,
        )
    if root.edge_capacity_total <= 0:
        raise ValueError("完整非空弃牌根没有正容量边")
    lower_mass = math.fsum(
        capacity * lower for _, capacity, lower, _ in edge_rows
    )
    upper_mass = math.fsum(
        capacity * upper for _, capacity, _, upper in edge_rows
    )
    return RootSearchScore(
        action_key=root.action_key,
        lower_support_score=round(lower_mass / root.edge_capacity_total, 12),
        upper_support_score=round(upper_mass / root.edge_capacity_total, 12),
        conditional_hu_net_support=round(hu_net_support, 6),
        conditional_hu_capacity=hu_capacity,
        capacity_total=root.edge_capacity_total,
        leaf_evaluations=counter.used - start_count,
    )


def reduce_public_successors(
    request: DecisionRequest,
    analysis: PublicSuccessorAnalysis,
    scorer: LeafScorer,
    *,
    max_leaf_evaluations: int = MAX_LEAF_EVALUATIONS,
) -> SearchReduction:
    """按固定合同归约整窗；任何缺口返回不可用并要求精确 V2 回退。"""

    try:
        if not callable(scorer):
            raise TypeError("叶评分器必须可调用")
        if (
            isinstance(max_leaf_evaluations, bool)
            or not isinstance(max_leaf_evaluations, int)
            or max_leaf_evaluations <= 0
        ):
            raise ValueError("max_leaf_evaluations 必须是正整数")
        if analysis.coverage is not PublicSuccessorCoverage.COMPLETE:
            raise ValueError("公开后继分析不完整")
        if analysis.ruleset_version != request.rules.ruleset_version:
            raise ValueError("公开后继与 DecisionRequest 规则版本不一致")
        candidates = {
            item.action_key: item
            for item in request.rules.legal_candidates
            if isinstance(item.action, Discard)
        }
        roots = {item.action_key: item for item in analysis.roots}
        if len(candidates) != len(tuple(
            item for item in request.rules.legal_candidates if isinstance(item.action, Discard)
        )):
            raise ValueError("DecisionRequest 存在重复弃牌动作键")
        if len(roots) != len(analysis.roots) or set(roots) != set(candidates):
            raise ValueError("公开后继根集合与当前合法弃牌集合不一致")
        rejected = {item.action_key for item in request.rejected_attempts}
        active_keys = tuple(sorted(key for key in candidates if key not in rejected))
        if not active_keys:
            raise ValueError("没有未拒绝的合法弃牌根")
        window = _window_view(request)
        counter = _EvaluationCounter(max_leaf_evaluations)
        result = tuple(
            _reduce_root(candidates[key], roots[key], window, scorer, counter)
            for key in active_keys
        )
        return SearchReduction(complete=True, roots=result, reason=None)
    except Exception as exc:
        return SearchReduction(
            complete=False,
            roots=(),
            reason="{0}: {1}".format(type(exc).__name__, str(exc)[:320]),
        )


def _dominates(left: RootSearchScore, right: RootSearchScore) -> bool:
    pairs = tuple(zip(left.dominance_vector, right.dominance_vector))
    return all(a >= b for a, b in pairs) and any(a > b for a, b in pairs)


def order_discard_keys_by_fronts(
    reduction: SearchReduction,
    baseline_keys: Tuple[str, ...],
) -> Tuple[str, ...]:
    """按 Pareto 层重排弃牌键；同层严格保持传入的 V2 顺序。"""

    if not reduction.complete:
        return baseline_keys
    scores = {item.action_key: item for item in reduction.roots}
    if len(scores) != len(reduction.roots) or set(scores) != set(baseline_keys):
        return baseline_keys
    remaining = list(baseline_keys)
    ordered = []
    while remaining:
        front = [
            key
            for key in remaining
            if not any(
                other != key and _dominates(scores[other], scores[key])
                for other in remaining
            )
        ]
        if not front:
            return baseline_keys
        ordered.extend(front)
        front_set = set(front)
        remaining = [key for key in remaining if key not in front_set]
    return tuple(ordered)


__all__ = [
    "LEAF_VIEW_SCHEMA_VERSION",
    "MAX_LEAF_EVALUATIONS",
    "LEAF_SCORE_MIN",
    "LEAF_SCORE_MAX",
    "FamilyProgressView",
    "LeafView",
    "RootSearchScore",
    "SearchReduction",
    "SearchRootView",
    "SearchWindowView",
    "order_discard_keys_by_fronts",
    "reduce_public_successors",
]
