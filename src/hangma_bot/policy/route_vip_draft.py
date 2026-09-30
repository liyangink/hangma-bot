"""VIP C_draft_M0：独立全动作纵切面，供严格离线续打暴露价值缺口。

合法性和动作后状态只来自同次 HangmaRules。当前非胡末端仍是未校准
的积分单位代理，不能把本策略称作通用期望积分模型或 C_alg。
"""

from __future__ import annotations

from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Discard, Hu, action_key

from .errors import PolicyError
from .interface import DecisionBudget, DecisionPlan, DecisionRequest, RankedCandidate, ScorePart
from .route_vip_proto import RouteVipPrototypePolicy


class RouteDraftError(PolicyError):
    """正常机械、输入事实或草案估值缺口；严格离线驱动必须停止。"""

    def __init__(self, category: str, reason: str, *, action_key: str | None = None) -> None:
        self.category = category
        self.reason = reason
        self.action_key = action_key
        super().__init__(f"C_draft_M0 {category} [{action_key or 'request'}]: {reason}")


class RouteVipDraftPolicy:
    """逐一排序全部合法动作，不调用 R18，也不读取隐藏世界。

    P1 完整的普通弃牌复用其同积分轴的一摸代理；其他非胡动作先
    使用规则给出的动作后向听和公开有效牌宽度。后一估值只供机械
    纵切面与行动差诊断，必须由 P3 条件价值模型替换。
    """

    name = "C_draft_M0"

    def __init__(self) -> None:
        self._one_draw = RouteVipPrototypePolicy()

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """返回全合法动作计划；已知机械失败与缺事实均显式停机。"""

        del budget  # 逻辑时钟研究档，不能据此宣称满足官方动作时限。
        rules = request.rules
        if rules.completeness is not RuleCompleteness.COMPLETE:
            raise RouteDraftError("RULES_DEGRADED", "同次规则分析不完整")
        legal = rules.legal_candidates
        roots = rules.conditional_roots
        if roots is None:
            raise RouteDraftError("INPUT_EVIDENCE_GAP", "未请求同次全合法条件根")
        keys = tuple(candidate.action_key for candidate in legal)
        if (not keys or len(set(keys)) != len(keys)
                or tuple(root.action_key for root in roots) != keys):
            raise RouteDraftError("MECHANICAL_GAP", "条件根未与全部合法动作同序一一对应")
        for root in roots:
            if root.gap_kind is not None:
                raise RouteDraftError(
                    root.gap_kind.name,
                    "; ".join(issue.reason for issue in root.issues) or "条件根投影失败",
                    action_key=root.action_key,
                )
        emergency = rules.emergency_candidate
        emergency_key = emergency.action_key if emergency is not None else None
        if emergency_key is not None and emergency_key not in keys:
            raise RouteDraftError("MECHANICAL_GAP", "紧急候选不属于同次合法动作")
        route_roots = {}
        if rules.route_frontier is not None and rules.route_frontier.top_level_gap is None:
            route_roots = {root.action_key: root for root in rules.route_frontier.roots}
        rejected = {item.action_key for item in request.rejected_attempts}
        scored = []
        for candidate, root in zip(legal, roots):
            key = candidate.action_key
            if action_key(candidate.action) != key:
                raise RouteDraftError("MECHANICAL_GAP", "规则动作键不一致", action_key=key)
            if key in rejected:
                continue
            if isinstance(candidate.action, Hu):
                if root.settlement is None or root.pending_condition is not None:
                    raise RouteDraftError("MECHANICAL_GAP", "当前胡缺同源即时结算", action_key=key)
                parts = (ScorePart("C_draft_M0.immediate_net_points",
                                   float(root.settlement.score_delta[request.observation.seat])),)
                source = "exact_current_hu"
            elif isinstance(candidate.action, Discard):
                if root.settlement is not None:
                    raise RouteDraftError("MECHANICAL_GAP", "非胡动作混入即时结算", action_key=key)
                route = route_roots.get(key)
                if route is not None and route.gap_kind is None:
                    parts, _ = self._one_draw._score_discard(request, route)
                    source = "P1_one_draw_uncalibrated"
                else:
                    parts = self._fact_tail(candidate, request)
                    source = "fact_tail_uncalibrated"
            else:
                if root.settlement is not None:
                    raise RouteDraftError("MECHANICAL_GAP", "非胡动作混入即时结算", action_key=key)
                parts = self._fact_tail(candidate, request)
                source = "fact_tail_uncalibrated"
            total = sum(part.value for part in parts)
            scored.append(RankedCandidate(
                action=candidate.action, action_key=key, rank=0,
                total_score=total, score_parts=parts,
                reasons=(
                    "同次条件根机械投影完整；非胡未来兑现概率尚未校准",
                    "当前评分源：" + source,
                    "赛事阶段和排名仅记录，不改变第一版动作排序",
                ),
                is_emergency=key == emergency_key,
                score_trace={
                    "candidate_version": self.name,
                    "value_status": ("exact" if isinstance(candidate.action, Hu)
                                     else "uncalibrated_tail"),
                    "source": source,
                    "competition": {
                        "stage_no": request.competition.stage_no,
                        "stage_role": request.competition.stage_role,
                        "participant_rank": request.competition.participant_rank,
                        "observed_at_unix_ms": request.competition.observed_at_unix_ms,
                    },
                },
            ))
        if not scored:
            raise RouteDraftError("NO_CANDIDATE", "全部合法动作已明确拒绝")
        # 未校准代理浮点累加可能比真实胡净分高约 1e-14；近似同分时
        # 选确定已结算的胡，不能把数值尾差解释成有证据的等待优势。
        scored.sort(key=lambda item: (
            -round(item.total_score, 8),
            not isinstance(item.action, Hu),
            item.action_key,
        ))
        ranked = tuple(RankedCandidate(
            action=item.action, action_key=item.action_key, rank=index,
            total_score=item.total_score, score_parts=item.score_parts,
            reasons=item.reasons, is_emergency=item.is_emergency,
            score_trace=item.score_trace,
        ) for index, item in enumerate(scored, start=1))
        return DecisionPlan(
            decision_id=request.decision_id, window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=len(request.rejected_attempts) + 1,
            candidates=ranked, degraded_reasons=(),
        )

    @staticmethod
    def _fact_tail(candidate, request: DecisionRequest) -> tuple[ScorePart, ...]:
        """动作后牌效代理；不用未给定补摸或他家暗牌伪造兑现概率。"""

        facts = candidate.facts
        if (facts is None or facts.completeness is not RuleCompleteness.COMPLETE
                or facts.fact_kind is not CandidateFactKind.HAND_PROGRESS
                or facts.shanten_after is None):
            raise RouteDraftError("INPUT_EVIDENCE_GAP", "非胡动作缺完整牌效事实",
                                  action_key=candidate.action_key)
        if facts.followup_branches:
            branches = []
            for branch in facts.followup_branches:
                if branch.combined_shanten is None or branch.support_remaining is None:
                    raise RouteDraftError("INPUT_EVIDENCE_GAP", "吃碰后续弃牌缺向听或进张容量",
                                          action_key=candidate.action_key)
                branches.append((branch.combined_shanten, branch.support_remaining,
                                 branch.followup_key))
            shanten, support, _ = min(branches, key=lambda row: (
                row[0], -row[1], row[2]))
        else:
            shanten = facts.shanten_after
            support = sum(tile.remaining_estimate for tile in facts.useful_tiles)
        if shanten < 0 or support < 0:
            raise RouteDraftError("MECHANICAL_GAP", "非胡动作出现无效等待事实",
                                  action_key=candidate.action_key)
        # 与 P1 末端相同的积分单位代理；只为纵切面能比较动作。
        # 不以公开未见张数冒充未来真实牌墙概率。
        progress = 4.0 / (1 + shanten)
        width = 1.5 * support / max(1, request.observation.remaining_tile_count)
        return (ScorePart("C_draft_M0.tail_progress_uncalibrated", progress),
                ScorePart("C_draft_M0.tail_width_uncalibrated", width))
