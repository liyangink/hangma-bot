"""C_proto：仅供 P1 普通自摸条件前沿研究的独立排序策略。

每个弃牌根在同一“下一次本人普通摸牌，随后立即胡或保留续行”
终点计分。公开未见容量按交换性假设归一化，是工程近似，绝非真实
牌墙概率；固定机会折减和末端分值均未校准，不能用作完整桌赛效果。
未实现的正常转移或输入证据缺口抛研发异常，不由线上父代补全。
"""

from __future__ import annotations

from dataclasses import dataclass

from hangma_bot.hangma.interface import (
    PublicSuccessorEnvelope,
    PublicSuccessorLeaf,
    RuleCompleteness,
)
from hangma_bot.hangma.route_frontier import RouteDrawEdge, RouteFrontierRoot
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, Discard, Hu, action_key

from .errors import PolicyError
from .interface import DecisionBudget, DecisionPlan, DecisionRequest, RankedCandidate, ScorePart


class RoutePrototypeError(PolicyError):
    """P1 研发停止原因；``category`` 是稳定的大写故障类别。"""

    def __init__(self, category: str, reason: str, *, action_key: str | None = None) -> None:
        self.category = category
        self.action_key = action_key
        self.reason = reason
        super().__init__(f"C_proto {category} [{action_key or 'request'}]: {reason}")


@dataclass(frozen=True)
class _BranchValue:
    win_net: float
    tail_progress: float
    tail_width: float
    tail_white: float
    source: str

    @property
    def total(self) -> float:
        return self.win_net + self.tail_progress + self.tail_width + self.tail_white


class RouteVipPrototypePolicy:
    """只消费公开观察与规则前沿的 P1 ``BotPolicy`` 实现。

    不访问完整世界、网络或 R18。两条无校准假设固定在代码中以便复算：
    未见牌交换性容量权重，以及下一次本人机会的 0.5 保守折减。
    """

    name = "C_proto"
    _NEXT_OPPORTUNITY_WEIGHT = 0.5  # 研究折减系数；不是观测到的存活概率。

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """排序所有未拒绝的合法候选；缺机械或证据时停止并保留类别。"""

        del budget  # P1 离线研究档不声明动作窗口内的部署时限。
        rules = request.rules
        if rules.completeness is RuleCompleteness.DEGRADED:
            raise RoutePrototypeError(
                "RULES_DEGRADED", "; ".join(issue.reason for issue in rules.issues)
                or "规则分析已降级",
            )
        frontier = rules.route_frontier
        if frontier is None:
            raise RoutePrototypeError("INPUT_EVIDENCE_GAP", "未请求 P1 路线前沿")
        if frontier.ruleset_version != rules.ruleset_version:
            raise RoutePrototypeError("INPUT_EVIDENCE_GAP", "路线前沿与规则版本不一致")
        if frontier.top_level_gap is not None:
            raise RoutePrototypeError(
                frontier.top_level_gap.name,
                "; ".join(issue.reason for issue in frontier.issues) or "路线前沿整体不完整",
            )

        legal = rules.legal_candidates
        keys = tuple(candidate.action_key for candidate in legal)
        roots = frontier.roots
        if not keys or len(set(keys)) != len(keys) or len({root.action_key for root in roots}) != len(roots):
            raise RoutePrototypeError("MECHANICAL_GAP", "合法根为空或动作键重复")
        if set(keys) != {root.action_key for root in roots}:
            raise RoutePrototypeError("MECHANICAL_GAP", "路线前沿与全部合法根未一一对应")
        by_key = {root.action_key: root for root in roots}
        for root in roots:
            if root.gap_kind is not None:
                raise RoutePrototypeError(
                    root.gap_kind.name,
                    "; ".join(issue.reason for issue in root.issues),
                    action_key=root.action_key,
                )
            if not root.structure_complete or not root.qualification_complete:
                raise RoutePrototypeError("MECHANICAL_GAP", "根结构或资格未完整", action_key=root.action_key)

        emergency = rules.emergency_candidate
        emergency_key = emergency.action_key if emergency is not None else None
        if emergency_key is not None and emergency_key not in by_key:
            raise RoutePrototypeError("MECHANICAL_GAP", "紧急候选未登记为合法根", action_key=emergency_key)
        rejected = {attempt.action_key for attempt in request.rejected_attempts}
        scored: list[RankedCandidate] = []
        for candidate in legal:
            key = candidate.action_key
            if action_key(candidate.action) != key:
                raise RoutePrototypeError("MECHANICAL_GAP", "合法动作键不一致", action_key=key)
            if key in rejected:
                continue
            root = by_key[key]
            if isinstance(candidate.action, Hu):
                if root.immediate_settlement is None or root.draw_edges:
                    raise RoutePrototypeError("MECHANICAL_GAP", "合法胡根缺当前结算或混入摸牌边", action_key=key)
                net = float(root.immediate_settlement.score_delta[request.observation.seat])
                parts = (ScorePart("C_proto.current_hu_net_points", net),)
                reasons = ("当前合法胡使用规则结算的本人净积分；不另加番数奖励",)
            elif isinstance(candidate.action, Discard):
                if root.immediate_settlement is not None:
                    raise RoutePrototypeError("MECHANICAL_GAP", "弃牌根混入当前结算", action_key=key)
                parts, reasons = self._score_discard(request, root)
            else:
                raise RoutePrototypeError("MECHANICAL_GAP", "P1 未覆盖该正常动作族", action_key=key)
            scored.append(RankedCandidate(
                action=candidate.action,
                action_key=key,
                rank=0,
                total_score=sum(part.value for part in parts),
                score_parts=parts,
                reasons=reasons,
                is_emergency=(key == emergency_key),
            ))

        scored.sort(key=lambda item: (-item.total_score, item.action_key))
        ranked = tuple(RankedCandidate(
            action=item.action,
            action_key=item.action_key,
            rank=index + 1,
            total_score=item.total_score,
            score_parts=item.score_parts,
            reasons=item.reasons,
            is_emergency=item.is_emergency,
        ) for index, item in enumerate(scored))
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=len(request.rejected_attempts) + 1,
            candidates=ranked,
            degraded_reasons=(),
        )

    def _score_discard(
        self, request: DecisionRequest, root: RouteFrontierRoot,
    ) -> tuple[tuple[ScorePart, ...], tuple[str, ...]]:
        """每个互斥摸牌码只进入一次条件期望，胡与续行只选一个。"""

        edges = root.draw_edges
        codes = tuple(edge.draw_code for edge in edges)
        if len(set(codes)) != len(codes):
            raise RoutePrototypeError("MECHANICAL_GAP", "同一码重复摸牌边", action_key=root.action_key)
        capacity_total = sum(edge.support_capacity for edge in edges)
        if any(edge.support_capacity <= 0 for edge in edges):
            raise RoutePrototypeError("INPUT_EVIDENCE_GAP", "非正公开容量", action_key=root.action_key)
        if capacity_total == 0:
            # 官方保留区已到达时，完整弃牌根可以没有下一次普通摸牌。
            return (ScorePart("C_proto.no_next_draw_proxy", 0.0),), (
                "无下一普通摸牌边；当前弃牌的 P1 代理值为零",)

        win_sum = 0.0
        progress_sum = 0.0
        width_sum = 0.0
        white_sum = 0.0
        selected_wins = 0
        for edge in edges:
            # 两种抓打包络的未来触发权重未知，取较低者作为保守代理。
            alternatives = (
                self._branch_value(request, root, edge, edge.successor.restricted, capacity_total),
                self._branch_value(request, root, edge, edge.successor.unrestricted, capacity_total),
            )
            chosen = min(alternatives, key=lambda value: (value.total, value.source))
            weight = edge.support_capacity / capacity_total
            win_sum += weight * chosen.win_net
            progress_sum += weight * chosen.tail_progress
            width_sum += weight * chosen.tail_width
            white_sum += weight * chosen.tail_white
            selected_wins += chosen.source == "hu"

        discount = self._NEXT_OPPORTUNITY_WEIGHT
        return (
            ScorePart("C_proto.one_draw_hu_net_proxy", discount * win_sum),
            ScorePart("C_proto.tail_shape_proxy_uncalibrated", discount * progress_sum),
            ScorePart("C_proto.tail_width_proxy_uncalibrated", discount * width_sum),
            ScorePart("C_proto.tail_white_useful_width_proxy_uncalibrated", discount * white_sum),
        ), (
            f"公开未见容量交换性近似：{len(edges)} 个互斥牌码、容量总数 {capacity_total}；非真实牌墙概率",
            f"一次普通摸牌后按较保守抓打包络择胡或续行；条件排序中选择胡的牌码 {selected_wins} 个，不代表实际胡牌频率",
            "下一本人机会固定折减 0.5 是未校准研究假设；非胡末端从规则叶保留普通型、七对与白板有效牌宽度",
        )

    def _branch_value(
        self,
        request: DecisionRequest,
        root: RouteFrontierRoot,
        edge: RouteDrawEdge,
        envelope: PublicSuccessorEnvelope,
        capacity_total: int,
    ) -> _BranchValue:
        win = edge.immediate_win
        choices: list[_BranchValue] = []
        if envelope.hu_available:
            if win is None:
                raise RoutePrototypeError("MECHANICAL_GAP", "可胡包络缺合法结算见证", action_key=root.action_key)
            choices.append(_BranchValue(
                float(win.settlement.score_delta[request.observation.seat]), 0.0, 0.0, 0.0, "hu",
            ))
        for leaf in envelope.discard_frontier:
            progress, width, white = self._tail_parts(request, root, leaf, capacity_total)
            choices.append(_BranchValue(
                0.0, progress, width, white,
                leaf.action_key,
            ))
        if not choices:
            if envelope.legal_discard_count:
                raise RoutePrototypeError("MECHANICAL_GAP", "存在合法弃牌但续行前沿为空", action_key=root.action_key)
            return _BranchValue(0.0, 0.0, 0.0, 0.0, "no_followup")
        return max(choices, key=lambda value: (value.total, value.source))

    @staticmethod
    def _tail_parts(
        request: DecisionRequest,
        root: RouteFrontierRoot,
        leaf: PublicSuccessorLeaf,
        capacity_total: int,
    ) -> tuple[float, float, float]:
        """本人积分单位的未校准结构代理，不调用 R18 或第二套规则。"""

        if leaf.action_type != "discard":
            raise RoutePrototypeError("MECHANICAL_GAP", "末端前沿包含非弃牌动作", action_key=root.action_key)
        standard = 4.0 / (1 + max(0, leaf.standard_shanten_after))
        seven = (
            0.0 if leaf.seven_pairs_shanten_after is None
            else 4.0 / (1 + max(0, leaf.seven_pairs_shanten_after))
        )
        # 普通与七对是互斥兑现出口，取较好者；同一码不能按两个胡牌机会求和。
        route_progress = max(standard, seven)
        if leaf.support_remaining > capacity_total:
            raise RoutePrototypeError("MECHANICAL_GAP", "规则叶进张容量超过根的公开容量", action_key=root.action_key)
        white_index = CANONICAL_TILE_INDEX[request.observation.rule_state.wealth_god.code]
        white_support = leaf.useful_remaining(white_index)
        if white_support > leaf.support_remaining:
            raise RoutePrototypeError("MECHANICAL_GAP", "规则叶的白板有效容量超过总进张容量", action_key=root.action_key)
        # 总宽度只拆账一次；白板容量由 hangma 规则叶给出，策略不重算手牌。
        other_width = 1.5 * (leaf.support_remaining - white_support) / capacity_total
        white_width = 1.5 * white_support / capacity_total
        return route_progress, other_width, white_width
