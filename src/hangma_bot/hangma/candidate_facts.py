"""候选牌效事实（CandidateFacts）生产：把已确认合法的候选映射为规则引擎口径的动作后牌效。

2026-09-04 集成阶段契约收口（doc/implementation/interface-contracts.md §4.1）：
向听与有效牌数学只允许存在于 hangma。本模块是候选事实的唯一生产点——
按动作族的机械语义把候选映射为「动作后暗牌状态」，调用 hand_analysis
得到向听与有效牌，再用「本人视角」的公开信息把有效牌折算成剩余张数估计
（4 张物理上限 - 本人手牌 - 去重的公开牌 - 动作新公开的牌），组装成
不可变 CandidateFacts 挂到 RuleCandidate.facts。

关键不变量（与受控契约一致）：

- 事实与 RuleCandidate.action_key 一一对应，随候选一起传递；
- 胡 → WIN（shanten_after=-1）；响应过牌与其余动作族 → HAND_PROGRESS；
- 吃/碰必须给出采用最佳合法后续弃牌后的最佳等待状态（best_followup_discard
  即该弃牌的规范牌值）；选择键 (向听, -剩余张数估计和, 规范牌序下标) 完全确定；
- 杠候选 replacement_draw_unknown=True：杠上补牌未知，shanten_after 与
  有效牌按补牌前余牌口径，不假设具体未来摸牌；
- 单个候选分析失败 → ANALYSIS_FAILED（数值字段为空、携带 note 与 RuleIssue），
  不伪造数值；紧急路径按设计不运行复杂分析（facts 保持 None），整个模块
  故障由 engine 兜底为「未生产事实」。

模块边界：不判断动作合法性（合法性由 action_families 负责）；不访问网络、
文件、时钟或随机源；全部函数为纯函数。规则依据见 RULES_EVIDENCE.md
（官方指南 v9）与 interface-contracts §4.1。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile

from . import hand_analysis
from .interface import (
    CandidateFactKind,
    CandidateFacts,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
    UsefulTileFact,
)
from .internal_types import TILE_INDEX, Counts34, WindowContext, counts_from_tiles
from .public_tile_counts import PublicCounts34

_AREA = "candidate_facts"
"""稳定 RuleIssue.area；engine 聚合时据此区分事实生产降级。"""


class FactsAnalysisError(Exception):
    """单个候选的动作后状态无法可靠分析（观察与动作形状矛盾等）。

    engine 把本异常收敛为该候选的 ANALYSIS_FAILED 事实与一条 RuleIssue；
    不向上传播，保证一个候选的事实失败不影响其他候选。
    """


@dataclass(frozen=True)
class _WaitingBasis:
    """一个等待状态的最小描述：暗牌、折算面子数与刚公开的牌。"""

    hand_after: Tuple[Tile, ...]
    melds: int
    newly_hidden: Dict[str, int]  # 动作中离开手牌、进入牌河/新副露的牌计数


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


def _remaining(
    code: str,
    hand_after_counts: Counts34,
    public_counts: PublicCounts34,
    newly_hidden: Dict[str, int],
) -> int:
    """从本人视角估计某牌种在牌墙/他家手牌中的剩余张数（0-4）。

    口径：4 张物理上限 - 动作后本人手牌 - 去重的牌河与副露（公开可见）
    - 本动作新公开的牌（弃牌进入本人牌河、吃碰杠进入本人副露）。
    不含对他家手牌的推测，未来牌墙不可见（契约 §4.1）。
    """

    index = TILE_INDEX[code]
    if public_counts[index] is None:
        raise FactsAnalysisError("公开牌 {0} 的牌河/副露重叠缺少供牌证据，剩余张数未知".format(code))
    return max(
        0,
        4 - hand_after_counts[index] - public_counts[index] - newly_hidden.get(code, 0),
    )


def _useful_facts(
    summary,
    hand_after: Tuple[Tile, ...],
    public_counts: PublicCounts34,
    newly_hidden: Dict[str, int],
) -> Tuple[UsefulTileFact, ...]:
    """把 hand_analysis 的有效牌按公开信息折算成剩余张数估计。"""

    hand_after_counts = counts_from_tiles(hand_after)
    entries: List[UsefulTileFact] = []
    for useful in summary.useful_tiles:
        entries.append(
            UsefulTileFact(
                code=useful.code,
                remaining_estimate=_remaining(
                    useful.code, hand_after_counts, public_counts, newly_hidden
                ),
            )
        )
    return tuple(entries)


def _waiting_facts(
    hand_after: Tuple[Tile, ...],
    melds: int,
    public_counts: PublicCounts34,
    newly_hidden: Dict[str, int],
    followup: Optional[str],
    replacement_unknown: bool,
) -> CandidateFacts:
    """对「动作后等待状态」调用 hand_analysis 并组装完整事实。

    hand_after 是动作后的暗牌（吃/碰为最佳后续弃牌后的暗牌）；任何张数
    都能被 hand_analysis 按折算面子数精确处理（10/11/13 张等效口径，
    见 hand_analysis 模块说明）。
    """

    summary = hand_analysis.analyse_hand(hand_after, melds)
    useful = _useful_facts(summary, hand_after, public_counts, newly_hidden)
    return CandidateFacts(
        fact_kind=CandidateFactKind.HAND_PROGRESS,
        shanten_after=summary.shanten,
        useful_tiles=useful,
        best_followup_discard=followup,
        replacement_draw_unknown=replacement_unknown,
        completeness=RuleCompleteness.COMPLETE,
        note=(
            "杠上补牌未知：向听与有效牌按补牌前余牌口径"
            if replacement_unknown
            else None
        ),
    )


def _claim_removal(action, context: WindowContext) -> Dict[str, int]:
    """吃/碰从手牌移出的牌计数；被吃/碰牌来自他家弃牌，不在手牌中。"""

    if isinstance(action, Peng):
        return {action.tile.code: 2}
    if isinstance(action, Chi):
        claimed = context.last_discard
        if claimed is None:
            raise FactsAnalysisError("吃窗口缺少触发弃牌，无法确定被吃牌")
        partners = [tile.code for tile in action.tiles if tile.code != claimed.tile.code]
        removal: Dict[str, int] = {}
        for code in partners:
            removal[code] = removal.get(code, 0) + 1
        return removal
    raise FactsAnalysisError("非吃/碰动作: {0}".format(type(action).__name__))


def _claim_basis(action, context: WindowContext, meld_blocks: int) -> _WaitingBasis:
    """吃/碰后的暗牌状态（尚未执行后续弃牌）；折算面子数 +1。"""

    removal = _claim_removal(action, context)
    full_counts = counts_from_tiles(context.full_hand())
    for code, needed in removal.items():
        if full_counts[TILE_INDEX[code]] < needed:
            raise FactsAnalysisError(
                "动作形状与手牌矛盾：{0} 需移除 {1} 张，手牌只有 {2} 张".format(
                    code, needed, full_counts[TILE_INDEX[code]]
                )
            )
    hand_codes = _remove_codes(
        tuple(tile.code for tile in context.full_hand()), removal
    )
    return _WaitingBasis(
        hand_after=tuple(Tile(code) for code in hand_codes),
        melds=meld_blocks + 1,
        newly_hidden=dict(removal),
    )


def _best_followup(
    basis: _WaitingBasis, public_counts: PublicCounts34, action_key: str
) -> Tuple[CandidateFacts, str]:
    """枚举全部合法后续弃牌，选最佳等待状态并组装事实。

    选择键 (向听, -剩余张数估计和, 规范牌序下标) 完全确定；后续弃牌进入
    本人牌河，计入 newly_hidden。
    """

    distinct = sorted({tile.code for tile in basis.hand_after}, key=TILE_INDEX.get)
    if not distinct:
        raise FactsAnalysisError(
            "候选 {key} 鸣牌后手牌为空，无法估计后续弃牌".format(key=action_key)
        )
    best: Optional[Tuple[Tuple[int, int, int], CandidateFacts, str]] = None
    for code in distinct:
        after = tuple(
            Tile(c) for c in _remove_codes(
                tuple(t.code for t in basis.hand_after), {code: 1}
            )
        )
        newly_hidden = dict(basis.newly_hidden)
        newly_hidden[code] = newly_hidden.get(code, 0) + 1
        summary = hand_analysis.analyse_hand(after, basis.melds)
        weight = sum(
            _remaining(u.code, counts_from_tiles(after), public_counts, newly_hidden)
            for u in summary.useful_tiles
        )
        order_key = (summary.shanten, -weight, TILE_INDEX[code])
        facts = _waiting_facts(
            after,
            basis.melds,
            public_counts,
            newly_hidden,
            followup=code,
            replacement_unknown=False,
        )
        if best is None or order_key < best[0]:
            best = (order_key, facts, code)
    if best is None:
        raise FactsAnalysisError(
            "候选 {key} 无任何合法后续弃牌".format(key=action_key)
        )
    return best[1], best[2]


def _gang_basis(action: Gang, context: WindowContext, meld_blocks: int) -> _WaitingBasis:
    """杠后的暗牌状态；补牌未知，向听按补牌前余牌口径。"""

    code = action.tile.code
    if action.kind is GangKind.CONCEALED:
        removal, extra_meld = {code: 4}, 1
    elif action.kind is GangKind.EXPOSED:
        removal, extra_meld = {code: 3}, 1
    else:
        removal, extra_meld = {code: 1}, 0
    full_counts = counts_from_tiles(context.full_hand())
    if full_counts[TILE_INDEX[code]] < removal[code]:
        raise FactsAnalysisError(
            "杠动作形状与手牌矛盾：{0} 需 {1} 张，手牌只有 {2} 张".format(
                code, removal[code], full_counts[TILE_INDEX[code]]
            )
        )
    hand_codes = _remove_codes(
        tuple(tile.code for tile in context.full_hand()), removal
    )
    return _WaitingBasis(
        hand_after=tuple(Tile(code) for code in hand_codes),
        melds=meld_blocks + extra_meld,
        newly_hidden=dict(removal),
    )


def _facts_for_candidate(
    candidate: RuleCandidate,
    context: WindowContext,
    public_counts: PublicCounts34,
    meld_blocks: int,
) -> CandidateFacts:
    """单个候选的事实；无法可靠分析时抛 FactsAnalysisError。"""

    action = candidate.action
    if isinstance(action, Hu):
        return CandidateFacts(
            fact_kind=CandidateFactKind.WIN,
            shanten_after=-1,
            completeness=RuleCompleteness.COMPLETE,
        )
    if isinstance(action, Pass):
        # 本地候选分析语义 v2（interface-contracts §4.3）：过保留当前等待手牌。
        # 沿用吃碰的公开计数来源；不把 last_discard 加入手牌或再次扣减。
        if context.phase not in ("response_peng", "response_chi") or context.seat not in context.responding_seats:
            raise FactsAnalysisError("过牌缺少响应窗口等待语义")
        if context.drawn_tile is not None:
            raise FactsAnalysisError("响应过牌仍携带摸牌，无法确认等待手牌")
        if len(context.hand_tiles) != 13 - 3 * meld_blocks:
            raise FactsAnalysisError("响应过牌暗牌张数与副露数不符")
        return _waiting_facts(
            context.hand_tiles, meld_blocks, public_counts, {},
            followup=None, replacement_unknown=False,
        )
    if isinstance(action, Discard):
        code = action.tile.code
        full_counts = counts_from_tiles(context.full_hand())
        if full_counts[TILE_INDEX[code]] < 1:
            # 与吃/碰/杠路径同款形状校验：弃牌不在手牌时 _remove_codes
            # 会静默空转并产出"未弃牌"口径的事实，属于伪造——必须拒绝。
            raise FactsAnalysisError(
                "动作形状与手牌矛盾：弃牌 {0} 不在手牌中".format(code)
            )
        hand_codes = _remove_codes(
            tuple(tile.code for tile in context.full_hand()), {code: 1}
        )
        return _waiting_facts(
            tuple(Tile(c) for c in hand_codes),
            meld_blocks,
            public_counts,
            {code: 1},
            followup=None,
            replacement_unknown=False,
        )
    if isinstance(action, (Peng, Chi)):
        basis = _claim_basis(action, context, meld_blocks)
        facts, _followup = _best_followup(basis, public_counts, candidate.action_key)
        return facts
    if isinstance(action, Gang):
        basis = _gang_basis(action, context, meld_blocks)
        return _waiting_facts(
            basis.hand_after,
            basis.melds,
            public_counts,
            basis.newly_hidden,
            followup=None,
            replacement_unknown=True,
        )
    raise FactsAnalysisError("未知动作类型: {0}".format(type(action).__name__))


def attach_facts(
    context: WindowContext,
    public_counts: PublicCounts34,
    meld_blocks: int,
    candidates: Tuple[RuleCandidate, ...],
) -> Tuple[Tuple[RuleCandidate, ...], Tuple[RuleIssue, ...]]:
    """给全部候选附加事实；单候选失败收敛为 ANALYSIS_FAILED + RuleIssue。

    public_counts 是四家牌河与副露去重后的 34 维可见牌计数；None表示
    某牌种重叠缺证据，消费时逐候选降级。meld_blocks 是本人已副露面子数（吃/碰/杠
    各计 1，补杠不增加）。返回的新候选保持输入顺序与动作键不变。
    """

    issues: List[RuleIssue] = []
    attached: List[RuleCandidate] = []
    for candidate in candidates:
        try:
            facts = _facts_for_candidate(candidate, context, public_counts, meld_blocks)
        except FactsAnalysisError as exc:
            issues.append(
                RuleIssue(
                    _AREA,
                    "候选 {key} 牌效分析失败: {message}".format(
                        key=candidate.action_key, message=exc
                    ),
                )
            )
            facts = CandidateFacts(
                fact_kind=CandidateFactKind.ANALYSIS_FAILED,
                shanten_after=None,
                completeness=RuleCompleteness.DEGRADED,
                note=str(exc),
            )
        except Exception as exc:  # 故障边界：未知异常同样只降级该候选
            issues.append(
                RuleIssue(
                    _AREA,
                    "候选 {key} 牌效分析异常: {etype}: {message}".format(
                        key=candidate.action_key,
                        etype=type(exc).__name__,
                        message=exc,
                    ),
                )
            )
            facts = CandidateFacts(
                fact_kind=CandidateFactKind.ANALYSIS_FAILED,
                shanten_after=None,
                completeness=RuleCompleteness.DEGRADED,
                note="{0}: {1}".format(type(exc).__name__, exc),
            )
        attached.append(
            RuleCandidate(
                action=candidate.action,
                action_key=candidate.action_key,
                evidence=candidate.evidence,
                facts=facts,
            )
        )
    return tuple(attached), tuple(issues)
