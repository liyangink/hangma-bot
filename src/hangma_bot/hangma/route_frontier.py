"""首版路线前沿的规则事实对账，不实现第二套牌型或番数算法。

公开自摸后继提供全部正容量条件摸牌（包括不能立即胡的分支）；
一次摸牌分值事实提供这些条件下的合法胡和真实结算。本模块只按同一
动作键、牌码关联两者，并把缺边、冲突或截断显式留在结果中。容量是
本人视角公开未见物理张数，不是摸牌概率。

这是 P1 研究纵切面的内部结果。未接通的正常动作族是机械待办，不能
把其空路线解释为零价值，也不能用父代续打充作新策略的完整成绩。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Discard, Hu

from .interface import (
    PublicSuccessorAnalysis,
    PublicSuccessorCoverage,
    PublicSuccessorDrawEdge,
    RuleCandidate,
    RuleIssue,
    Settlement,
    ValueConditions,
    ValueCoverage,
)


class RouteGapKind(str, Enum):
    """研发故障类别；未来兑现未知不在故障之列。"""

    MECHANICAL_GAP = "mechanical_gap"
    INPUT_EVIDENCE_GAP = "input_evidence_gap"
    SEARCH_TRUNCATED = "search_truncated"


@dataclass(frozen=True)
class ConditionalWin:
    """指定条件摸牌后可立即胡的规则见证；分数顺序为座位 0—3。"""

    conditions: ValueConditions
    settlement: Settlement


@dataclass(frozen=True)
class RouteDrawEdge:
    """一次普通摸牌条件边，含不能立即胡但仍可继续发展的边。"""

    successor: PublicSuccessorDrawEdge
    immediate_win: Optional[ConditionalWin]

    @property
    def draw_code(self) -> str:
        return self.successor.draw_tile.code

    @property
    def support_capacity(self) -> int:
        """公开未见的物理张数上限，绝不作为条件边概率。"""

        return self.successor.draw_tile.remaining_estimate


@dataclass(frozen=True)
class RouteFrontierRoot:
    """同次合法候选的一条根；不完整根仍必须保留动作键。"""

    action_key: str
    immediate_settlement: Optional[Settlement] = None
    draw_edges: Tuple[RouteDrawEdge, ...] = ()
    structure_complete: bool = False
    qualification_complete: bool = False
    gap_kind: Optional[RouteGapKind] = None
    issues: Tuple[RuleIssue, ...] = ()

    def __post_init__(self) -> None:
        if self.gap_kind is None:
            if not self.structure_complete or not self.qualification_complete:
                raise ValueError("无故障根必须同时完成结构和资格范围")
            if self.issues:
                raise ValueError("完整根不能携带故障说明")
        elif not self.issues:
            raise ValueError("不完整根必须说明原因")


@dataclass(frozen=True)
class RouteFrontierDraft:
    """所有合法根的 P1 机械证据；不能直接宣称是完整独立策略。"""

    roots: Tuple[RouteFrontierRoot, ...]
    ruleset_version: str
    top_level_gap: Optional[RouteGapKind] = None
    issues: Tuple[RuleIssue, ...] = ()

    @property
    def complete(self) -> bool:
        return bool(self.roots) and self.top_level_gap is None and all(
            root.gap_kind is None for root in self.roots
        )


def _gap(candidate: RuleCandidate, kind: RouteGapKind, reason: str) -> RouteFrontierRoot:
    return RouteFrontierRoot(
        action_key=candidate.action_key,
        gap_kind=kind,
        issues=(RuleIssue("route_frontier." + kind.value, reason),),
    )


def _value_gap(candidate: RuleCandidate) -> RouteFrontierRoot:
    facts = candidate.value_facts
    if facts is None:
        return _gap(candidate, RouteGapKind.MECHANICAL_GAP, "一次摸牌合法结算事实未请求")
    if facts.coverage is ValueCoverage.PARTIAL:
        kind = RouteGapKind.SEARCH_TRUNCATED
    elif any(issue.area == "value_analysis.missing_evidence" for issue in facts.issues):
        kind = RouteGapKind.INPUT_EVIDENCE_GAP
    else:
        kind = RouteGapKind.MECHANICAL_GAP
    reason = "; ".join(issue.reason for issue in facts.issues) or "一次摸牌资格未完整"
    return _gap(candidate, kind, reason)


def join_one_draw_frontier(
    candidates: Tuple[RuleCandidate, ...],
    successors: PublicSuccessorAnalysis,
    *,
    expected_ruleset_version: str,
    ordinary_draw_source_proven: bool,
    white_capacity_evidence_complete: bool,
    you_cai_bi_kao: bool,
) -> RouteFrontierDraft:
    """按同次合法候选顺序关联结构边与条件结算；绝不删除失败根。

    仅完成 P1 的本人普通自摸、立即胡和弃牌后下一普通自摸范围。
    来源证据不明、未来杠补、吃碰与响应格显式留待 P2。调用方必须
    保证 `successors` 和 `candidates` 来自同一观察及规则配置；本函数
    再逐根检查动作键和条件资格，冲突直接报告机械缺口。
    """

    if not isinstance(candidates, tuple):
        raise TypeError("candidates 必须是同次规则分析的 tuple")
    if not expected_ruleset_version:
        raise ValueError("expected_ruleset_version 必须非空")
    if type(white_capacity_evidence_complete) is not bool:
        raise TypeError("white_capacity_evidence_complete 必须为 bool")
    if len({item.action_key for item in candidates}) != len(candidates):
        raise ValueError("同次合法候选存在重复 action_key")
    structural = {root.action_key: root for root in successors.roots}
    if len(structural) != len(successors.roots):
        raise ValueError("公开后继存在重复 action_key")
    candidate_keys = {item.action_key for item in candidates}
    if not set(structural).issubset(candidate_keys):
        raise ValueError("公开后继包含本次合法候选之外的动作键")

    top_level_gap = None
    top_level_issues = ()
    if not candidates:
        top_level_gap = RouteGapKind.INPUT_EVIDENCE_GAP
        top_level_issues = (RuleIssue("route_frontier.empty", "没有合法候选根，不能声称完整"),)
    elif successors.ruleset_version != expected_ruleset_version:
        top_level_gap = RouteGapKind.INPUT_EVIDENCE_GAP
        top_level_issues = (RuleIssue("route_frontier.ruleset_version", "公开后继规则版本与本次规则实例不符"),)
    elif successors.coverage is not PublicSuccessorCoverage.COMPLETE:
        # 结构投影异常通常是实现/规则覆盖缺口；只有明确的输入上下文
        # 缺失才归输入证据。不能把任意根失败概括为“未来不确定”。
        top_level_gap = (
            RouteGapKind.INPUT_EVIDENCE_GAP
            if any(issue.area == "public_successor.context" for issue in successors.issues)
            else RouteGapKind.MECHANICAL_GAP
        )
        top_level_issues = successors.issues or (RuleIssue(
            "route_frontier.successors", "公开后继整体范围未完整",
        ),)

    roots = []
    for candidate in candidates:
        if top_level_gap is not None:
            roots.append(_gap(candidate, top_level_gap, top_level_issues[0].reason))
            continue
        action = candidate.action
        facts = candidate.value_facts
        if isinstance(action, Hu):
            if facts is None or facts.coverage is not ValueCoverage.COMPLETE:
                roots.append(_value_gap(candidate))
            elif facts.immediate_settlement is None:
                roots.append(_gap(candidate, RouteGapKind.MECHANICAL_GAP, "合法胡根缺当前结算"))
            else:
                roots.append(RouteFrontierRoot(
                    action_key=candidate.action_key,
                    immediate_settlement=facts.immediate_settlement,
                    structure_complete=True,
                    qualification_complete=True,
                ))
            continue
        if not isinstance(action, Discard):
            roots.append(_gap(candidate, RouteGapKind.MECHANICAL_GAP,
                              "P1 尚未接通该正常动作族的条件转移"))
            continue
        if not ordinary_draw_source_proven:
            roots.append(_gap(candidate, RouteGapKind.INPUT_EVIDENCE_GAP,
                              "当前摸牌来源未证实为普通自摸"))
            continue
        if not white_capacity_evidence_complete:
            roots.append(_gap(candidate, RouteGapKind.INPUT_EVIDENCE_GAP,
                              "链内飘白未完整反映在本人牌河，公开容量两入口口径不可对账"))
            continue
        if you_cai_bi_kao:
            roots.append(_gap(candidate, RouteGapKind.MECHANICAL_GAP,
                              "P1 未覆盖有财必拷响的未来资格"))
            continue
        if facts is None or facts.coverage is not ValueCoverage.COMPLETE:
            roots.append(_value_gap(candidate))
            continue
        structural_root = structural.get(candidate.action_key)
        if structural_root is None:
            roots.append(_gap(candidate, RouteGapKind.MECHANICAL_GAP,
                              "合法弃牌根缺公开后继登记"))
            continue
        if structural_root.coverage is not PublicSuccessorCoverage.COMPLETE:
            reason = "; ".join(issue.reason for issue in structural_root.issues)
            roots.append(_gap(candidate, RouteGapKind.MECHANICAL_GAP,
                              reason or "公开后继未完整"))
            continue
        wins = {}
        conflict = None
        for route in facts.routes:
            if route.followup_discard is not None or route.conditions.draw_kind != "normal":
                conflict = "弃牌根出现不符的一次摸牌资格前缀"
                break
            for tile in route.useful_tiles:
                if tile.code in wins:
                    conflict = "同一摸牌码出现重复条件胡见证"
                    break
                wins[tile.code] = (tile.remaining_estimate, ConditionalWin(
                    route.conditions, route.conditional_settlement,
                ))
            if conflict is not None:
                break
        if conflict is None:
            edge_codes = {edge.draw_tile.code for edge in structural_root.edges}
            if not set(wins).issubset(edge_codes):
                conflict = "条件胡见证没有对应的正容量摸牌边"
        draw_edges = []
        if conflict is None:
            for edge in structural_root.edges:
                code = edge.draw_tile.code
                witness = wins.get(code)
                if witness is not None and witness[0] != edge.draw_tile.remaining_estimate:
                    conflict = "条件胡与结构边的公开容量不一致: " + code
                    break
                has_shape_hu = edge.unrestricted.hu_available
                if has_shape_hu != (witness is not None):
                    conflict = "条件胡资格与公开后继胡牌候选冲突: " + code
                    break
                draw_edges.append(RouteDrawEdge(edge, None if witness is None else witness[1]))
        if conflict is not None:
            roots.append(_gap(candidate, RouteGapKind.MECHANICAL_GAP, conflict))
            continue
        roots.append(RouteFrontierRoot(
            action_key=candidate.action_key,
            draw_edges=tuple(draw_edges),
            structure_complete=True,
            qualification_complete=True,
        ))
    return RouteFrontierDraft(
        tuple(roots), expected_ruleset_version,
        top_level_gap=top_level_gap, issues=top_level_issues,
    )
