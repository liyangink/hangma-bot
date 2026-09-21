"""公开自摸后继投影：为合法弃牌根生成全 34 牌码的有界规则前沿。

首版只接受本人 ``phase=draw`` 窗口。每个合法弃牌完成后，本模块按
本人可见牌计算所有公开容量大于零的普通下一摸；容量是物理上限扣减，
不是概率。下一摸同时给出抓打受限摸切与不受限弃牌两个条件包络，胡、
杠和弃牌都继续复用 ``hangma`` 的唯一规则数学。

本模块不构造未来 ``PlayerObservation``，不模拟对手，不读取牌墙隐藏
顺序，也不访问网络、文件、时钟或 GC。内部会流式计算全部合法弃牌叶，
但公开接口只保留 Pareto 前沿；其余叶在当前边完成后即可释放。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from hangma_bot.kernel.actions import Discard, Gang, Tile
from hangma_bot.kernel.config import RuleConfig

from . import action_families, candidate_facts, hand_analysis
from .candidate_facts import FactsAnalysisError, _remaining, _remove_codes
from .interface import (
    CandidateFactKind,
    PublicSuccessorAnalysis,
    PublicSuccessorCoverage,
    PublicSuccessorDrawEdge,
    PublicSuccessorEnvelope,
    PublicSuccessorEnvelopeKind,
    PublicSuccessorLeaf,
    PublicSuccessorRoot,
    RuleCandidate,
    RuleIssue,
    UsefulTileFact,
)
from .internal_types import (
    TILE_INDEX,
    TILE_ORDER,
    Counts34,
    HandProgressSummary,
    WindowContext,
    counts_from_tiles,
)
from .public_tile_counts import PublicCounts34


_AREA = "public_successor"
_FUTURE_WALL_CONDITION_SENTINEL = action_families.WALL_RESERVE_TILES + 1


@dataclass(frozen=True)
class _RootBasis:
    """当前弃牌完成后的摸前暗牌与公开变化。"""

    hand: Tuple[Tile, ...]
    meld_count: int
    newly_public: Dict[str, int]
    summary: HandProgressSummary


@dataclass(frozen=True)
class _LeafBasis:
    """与动作键无关、可跨对称根复用的弃牌叶事实。"""

    shanten_after: int
    standard_shanten_after: int
    seven_pairs_shanten_after: Optional[int]
    useful_mask: int
    useful_remaining_packed: int
    useful_tile_count: int
    support_remaining: int


@dataclass(frozen=True)
class _DiscardLeafScalar:
    """完整合法弃牌叶的紧凑标量；只有 Pareto 保留者物化公开对象。"""

    action_key: str
    action_type: str
    shanten_after: int
    standard_shanten_after: int
    seven_pairs_shanten_after: Optional[int]
    useful_mask: int
    useful_remaining_packed: int
    useful_tile_count: int
    support_remaining: int


def analyze_public_self_draw_successors(
    context: WindowContext,
    public_counts: PublicCounts34,
    meld_count: int,
    discard_roots: Tuple[RuleCandidate, ...],
    config: RuleConfig,
) -> PublicSuccessorAnalysis:
    """对规则模块同源生成的合法弃牌根投影后继；失败显式返回。

    ``discard_roots`` 只能来自同一次调用内的
    ``action_families.discard_candidates(context)``，公开入口不接收调用方
    缓存的 ``RuleAnalysis``。响应窗口首版固定 ``UNAVAILABLE``，策略
    必须回退稳定 V2。``you_cai_bi_kao`` 开启时，未来摸牌后的爆头状态
    没有权威观察，本版整项 fail-closed，绝不把成牌形状冒充合法胡资格。
    """

    phase = context.phase
    if phase != "draw" or context.turn_seat != context.seat:
        return _unavailable(
            phase,
            config,
            "phase",
            "首版只分析本人 draw 合法弃牌根；响应窗口由策略精确回退稳定 V2",
        )
    if config.you_cai_bi_kao:
        return _unavailable(
            phase,
            config,
            "you_cai_bi_kao",
            "未来摸牌后的爆头资格没有权威 PlayerObservation；有财必拷响开启时首版保守不可用",
        )

    roots = tuple(discard_roots)
    if any(not isinstance(candidate.action, Discard) for candidate in roots):
        return _unavailable(
            phase,
            config,
            "root_type",
            "公开后继入口只接受规则模块同源生成的合法弃牌根",
        )
    if not roots:
        return _unavailable(
            phase,
            config,
            "root",
            "当前规则分析没有合法弃牌根，不能生成公开自摸后继",
        )

    summary_cache: Dict[Tuple[Counts34, int], HandProgressSummary] = {}
    leaf_cache: Dict[
        Tuple[Counts34, PublicCounts34, int], _LeafBasis
    ] = {}
    projected = []
    all_issues = []
    for candidate in roots:
        root = _project_root(
            candidate,
            context,
            public_counts,
            meld_count,
            summary_cache,
            leaf_cache,
        )
        projected.append(root)
        all_issues.extend(root.issues)

    if all(root.coverage is PublicSuccessorCoverage.COMPLETE for root in projected):
        coverage = PublicSuccessorCoverage.COMPLETE
    else:
        coverage = PublicSuccessorCoverage.PARTIAL
    return PublicSuccessorAnalysis(
        phase=phase,
        coverage=coverage,
        roots=tuple(projected),
        ruleset_version=config.ruleset_version,
        issues=tuple(all_issues),
    )


def _unavailable(
    phase: str, config: RuleConfig, suffix: str, reason: str
) -> PublicSuccessorAnalysis:
    return PublicSuccessorAnalysis(
        phase=phase,
        coverage=PublicSuccessorCoverage.UNAVAILABLE,
        roots=(),
        ruleset_version=config.ruleset_version,
        issues=(RuleIssue("{0}.{1}".format(_AREA, suffix), reason),),
    )


def _project_root(
    candidate: RuleCandidate,
    current: WindowContext,
    public_counts: PublicCounts34,
    meld_count: int,
    summary_cache: Dict[Tuple[Counts34, int], HandProgressSummary],
    leaf_cache: Dict[Tuple[Counts34, PublicCounts34, int], _LeafBasis],
) -> PublicSuccessorRoot:
    """生成单根；任一公开容量或规则分支未知时整根不可用于候选。"""

    code = candidate.action.tile.code
    root_summary: Optional[HandProgressSummary] = None
    try:
        basis = _root_basis(candidate, current, meld_count, summary_cache)
        root_summary = basis.summary
        hand_counts = counts_from_tiles(basis.hand)
        capacities = []
        for draw_code in TILE_ORDER:
            capacity = _remaining(
                draw_code, hand_counts, public_counts, basis.newly_public
            )
            if capacity > 0:
                capacities.append((draw_code, capacity))
        public_after_root = _adjust_public_counts(public_counts, basis.newly_public)
        useful_codes = frozenset(basis.summary.useful_codes)
        edges = []
        for draw_code, capacity in capacities:
            edges.append(
                _project_edge(
                    current,
                    basis,
                    public_after_root,
                    draw_code,
                    capacity,
                    draw_code in useful_codes,
                    summary_cache,
                    leaf_cache,
                )
            )
        return PublicSuccessorRoot(
            action_key=candidate.action_key,
            discard_code=code,
            shanten_after=basis.summary.shanten,
            coverage=PublicSuccessorCoverage.COMPLETE,
            edges=tuple(edges),
        )
    except Exception as exc:
        issue = RuleIssue(
            "{0}.root".format(_AREA),
            "根 {0} 后继不可用: {1}: {2}".format(
                candidate.action_key, type(exc).__name__, exc
            ),
        )
        return PublicSuccessorRoot(
            action_key=candidate.action_key,
            discard_code=code,
            shanten_after=(None if root_summary is None else root_summary.shanten),
            coverage=PublicSuccessorCoverage.UNAVAILABLE,
            issues=(issue,),
        )


def _root_basis(
    candidate: RuleCandidate,
    context: WindowContext,
    meld_count: int,
    summary_cache: Dict[Tuple[Counts34, int], HandProgressSummary],
) -> _RootBasis:
    if not isinstance(candidate.action, Discard):
        raise FactsAnalysisError("公开自摸后继首版只接受合法弃牌根")
    code = candidate.action.tile.code
    full_codes = tuple(tile.code for tile in context.full_hand())
    if code not in full_codes:
        raise FactsAnalysisError("合法弃牌根不在当前暗牌全集")
    hand = tuple(
        Tile(item) for item in _remove_codes(full_codes, {code: 1})
    )
    summary = _summary_counts(counts_from_tiles(hand), meld_count, summary_cache)
    return _RootBasis(
        hand=hand,
        meld_count=meld_count,
        newly_public={code: 1},
        summary=summary,
    )


def _project_edge(
    current: WindowContext,
    root: _RootBasis,
    public_after_root: PublicCounts34,
    draw_code: str,
    capacity: int,
    is_currently_useful: bool,
    summary_cache: Dict[Tuple[Counts34, int], HandProgressSummary],
    leaf_cache: Dict[Tuple[Counts34, PublicCounts34, int], _LeafBasis],
) -> PublicSuccessorDrawEdge:
    contexts = {
        PublicSuccessorEnvelopeKind.UNRESTRICTED: _future_context(
            current, root, draw_code, catch_play=False
        ),
        PublicSuccessorEnvelopeKind.RESTRICTED_DRAWN_ONLY: _future_context(
            current, root, draw_code, catch_play=True
        ),
    }
    full_hand = contexts[PublicSuccessorEnvelopeKind.UNRESTRICTED].full_hand()
    full_counts = counts_from_tiles(full_hand)
    drawn_summary = _summary_counts(full_counts, root.meld_count, summary_cache)
    hu_outcome = action_families.hu_candidates(
        contexts[PublicSuccessorEnvelopeKind.UNRESTRICTED], drawn_summary
    )
    if hu_outcome.issues:
        raise FactsAnalysisError(_format_issues(hu_outcome.issues))
    hu_available = bool(hu_outcome.candidates)

    gang_keys = {}
    union_gangs = {}
    discard_codes = {}
    for kind, context in contexts.items():
        gang_outcome = action_families.gang_candidates(context)
        if gang_outcome.issues:
            raise FactsAnalysisError(_format_issues(gang_outcome.issues))
        gang_keys[kind] = tuple(item.action_key for item in gang_outcome.candidates)
        union_gangs.update(
            (item.action_key, item) for item in gang_outcome.candidates
        )
        codes, discard_issues = action_families.discard_tile_codes(context)
        if discard_issues:
            raise FactsAnalysisError(_format_issues(discard_issues))
        discard_codes[kind] = codes

    attached_gangs, fact_issues = candidate_facts.attach_facts(
        contexts[PublicSuccessorEnvelopeKind.UNRESTRICTED],
        public_after_root,
        root.meld_count,
        tuple(union_gangs.values()),
    )
    if fact_issues:
        raise FactsAnalysisError(_format_issues(fact_issues))
    gang_map = {item.action_key: _gang_leaf(item) for item in attached_gangs}

    envelopes = {}
    for kind, codes in discard_codes.items():
        leaves = [
            _discard_leaf_scalar(
                code,
                full_counts,
                public_after_root,
                root.meld_count,
                summary_cache,
                leaf_cache,
            )
            for code in codes
        ]
        envelopes[kind] = PublicSuccessorEnvelope(
            kind=kind,
            hu_available=hu_available,
            legal_discard_count=len(leaves),
            gang_leaves=tuple(gang_map[key] for key in gang_keys[kind]),
            discard_frontier=tuple(
                _materialize_discard_leaf(item)
                for item in _pareto(tuple(leaves))
            ),
        )
    return PublicSuccessorDrawEdge(
        draw_tile=UsefulTileFact(draw_code, capacity),
        is_currently_useful=is_currently_useful,
        restricted=envelopes[PublicSuccessorEnvelopeKind.RESTRICTED_DRAWN_ONLY],
        unrestricted=envelopes[PublicSuccessorEnvelopeKind.UNRESTRICTED],
    )


def _future_context(
    current: WindowContext,
    root: _RootBasis,
    draw_code: str,
    *,
    catch_play: bool,
) -> WindowContext:
    # 本边是“下一次普通摸牌”，当前 21 张时摸后至多剩 20，未来杠条件
    # 必不成立；只有当前 >21 才允许表达“未来实际墙余仍 >20”的条件
    # 形状。哨兵 21 不是对未来牌墙的估计，每个杠叶仍显式携带条件。
    wall = current.remaining_tile_count
    conditional_wall = (
        None
        if wall is None
        else (
            _FUTURE_WALL_CONDITION_SENTINEL
            if wall > action_families.WALL_RESERVE_TILES + 1
            else action_families.WALL_RESERVE_TILES
        )
    )
    return WindowContext(
        seat=current.seat,
        phase="draw",
        turn_seat=current.seat,
        responding_seats=(),
        hand_tiles=root.hand,
        drawn_tile=Tile(draw_code),
        my_chi_count=current.my_chi_count,
        my_peng_codes=current.my_peng_codes,
        last_discard=None,
        catch_play=catch_play,
        remaining_tile_count=conditional_wall,
    )


def _discard_leaf_scalar(
    discard_code: str,
    full_counts: Counts34,
    public_after_root: PublicCounts34,
    meld_count: int,
    summary_cache: Dict[Tuple[Counts34, int], HandProgressSummary],
    leaf_cache: Dict[Tuple[Counts34, PublicCounts34, int], _LeafBasis],
) -> _DiscardLeafScalar:
    code = discard_code
    index = TILE_INDEX[code]
    if full_counts[index] <= 0:
        raise FactsAnalysisError("合法后继弃牌不在摸后暗牌全集")
    after_counts = (
        full_counts[:index]
        + (full_counts[index] - 1,)
        + full_counts[index + 1 :]
    )
    final_public = _adjust_public_counts(public_after_root, {code: 1})
    cache_key = (after_counts, final_public, meld_count)
    basis = leaf_cache.get(cache_key)
    if basis is None:
        # 计数向量由当前规则窗口机械扣牌得到；直接进入同源规则数学，
        # 避免批量前沿为每个叶重复构造、排序 Tile 对象。
        summary = _summary_counts(after_counts, meld_count, summary_cache)
        useful_mask, remaining_packed, useful_count, support = _pack_useful(
            summary.useful_codes,
            tuple(
                _remaining(code, after_counts, final_public, {})
                for code in summary.useful_codes
            ),
        )
        basis = _LeafBasis(
            shanten_after=summary.shanten,
            standard_shanten_after=summary.standard_shanten,
            seven_pairs_shanten_after=summary.chiitoi_shanten,
            useful_mask=useful_mask,
            useful_remaining_packed=remaining_packed,
            useful_tile_count=useful_count,
            support_remaining=support,
        )
        leaf_cache[cache_key] = basis
    return _DiscardLeafScalar(
        action_key="discard:" + code,
        action_type="discard",
        shanten_after=basis.shanten_after,
        standard_shanten_after=basis.standard_shanten_after,
        seven_pairs_shanten_after=basis.seven_pairs_shanten_after,
        useful_mask=basis.useful_mask,
        useful_remaining_packed=basis.useful_remaining_packed,
        useful_tile_count=basis.useful_tile_count,
        support_remaining=basis.support_remaining,
    )


def _materialize_discard_leaf(
    scalar: _DiscardLeafScalar,
) -> PublicSuccessorLeaf:
    """只为有界 Pareto 前沿分配公开类型及 UsefulTileFact。"""

    return PublicSuccessorLeaf(
        action_key=scalar.action_key,
        action_type="discard",
        shanten_after=scalar.shanten_after,
        standard_shanten_after=scalar.standard_shanten_after,
        seven_pairs_shanten_after=scalar.seven_pairs_shanten_after,
        useful_mask=scalar.useful_mask,
        useful_remaining_packed=scalar.useful_remaining_packed,
        useful_tile_count=scalar.useful_tile_count,
        support_remaining=scalar.support_remaining,
        replacement_draw_unknown=False,
    )


def _gang_leaf(candidate: RuleCandidate) -> PublicSuccessorLeaf:
    if not isinstance(candidate.action, Gang):
        raise FactsAnalysisError("杠事实映射收到非杠动作")
    facts = candidate.facts
    if (
        facts is None
        or facts.fact_kind is not CandidateFactKind.HAND_PROGRESS
        or facts.shanten_after is None
        or facts.standard_shanten_after is None
    ):
        raise FactsAnalysisError("杠叶缺少完整 HAND_PROGRESS 事实")
    useful = facts.useful_tiles
    useful_mask, remaining_packed, useful_count, support = _pack_useful(
        tuple(item.code for item in useful),
        tuple(item.remaining_estimate for item in useful),
    )
    return PublicSuccessorLeaf(
        action_key=candidate.action_key,
        action_type="gang",
        shanten_after=facts.shanten_after,
        standard_shanten_after=facts.standard_shanten_after,
        seven_pairs_shanten_after=facts.seven_pairs_shanten_after,
        useful_mask=useful_mask,
        useful_remaining_packed=remaining_packed,
        useful_tile_count=useful_count,
        support_remaining=support,
        replacement_draw_unknown=True,
        requires_future_wall_gt20=True,
    )


def _summary_counts(
    counts: Counts34,
    meld_count: int,
    cache: Dict[Tuple[Counts34, int], HandProgressSummary],
) -> HandProgressSummary:
    """按规范计数缓存同源轻量规则数学。"""

    key = (counts, meld_count)
    summary = cache.get(key)
    if summary is None:
        summary = hand_analysis.analyse_counts_progress(counts, meld_count)
        cache[key] = summary
    return summary


def _pack_useful(
    codes: Tuple[str, ...], remaining: Tuple[int, ...]
) -> Tuple[int, int, int, int]:
    """把有效牌身份与容量打包；牌序和容量仍逐项可逆。"""

    mask = 0
    packed = 0
    support = 0
    for code, value in zip(codes, remaining):
        index = TILE_INDEX[code]
        mask |= 1 << index
        packed |= value << (index * 3)
        support += value
    return mask, packed, len(codes), support


def _adjust_public_counts(
    public_counts: PublicCounts34, newly_public: Dict[str, int]
) -> PublicCounts34:
    adjusted = list(public_counts)
    for code, amount in newly_public.items():
        index = TILE_INDEX[code]
        if adjusted[index] is not None:
            adjusted[index] += amount
    return tuple(adjusted)


def _dominates(left: _DiscardLeafScalar, right: _DiscardLeafScalar) -> bool:
    if left.shanten_after > right.shanten_after:
        return False
    if left.standard_shanten_after > right.standard_shanten_after:
        return False
    strict = (
        left.shanten_after < right.shanten_after
        or left.standard_shanten_after < right.standard_shanten_after
    )
    if left.seven_pairs_shanten_after is not None:
        if left.seven_pairs_shanten_after > right.seven_pairs_shanten_after:
            return False
        strict = strict or (
            left.seven_pairs_shanten_after < right.seven_pairs_shanten_after
        )
    if left.support_remaining < right.support_remaining:
        return False
    return strict or left.support_remaining > right.support_remaining


def _pareto(
    leaves: Tuple[_DiscardLeafScalar, ...]
) -> Tuple[_DiscardLeafScalar, ...]:
    """按冻结支配式保留原规范动作顺序；不以启发权重做规则剪枝。"""

    return tuple(
        leaf
        for index, leaf in enumerate(leaves)
        if not any(
            other_index != index and _dominates(other, leaf)
            for other_index, other in enumerate(leaves)
        )
    )


def _format_issues(issues: Tuple[RuleIssue, ...]) -> str:
    return "；".join("{0}:{1}".format(item.area, item.reason) for item in issues)
