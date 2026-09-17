"""action_value_v1 全链装配（B3）：ScoringView 投影器与 BotPolicy 实现。

六步运行顺序（v4 §4.1）：紧急计划已在 request 层备好（应用层既有路径），
本模块负责第 3—6 步——从 DecisionRequest 投影只读视图、经受限执行器调用
候选评分器（种子注册表按名取，不动态扫描）、适配 RankedCandidate 并组装
DecisionPlan（拒绝过滤、紧急候选保留、rank 从 1 连续）。任何整批失败
（ValueError/WorkloadExceeded/ABSTAIN）降级为"仅紧急候选 + 规则合法顺序"
的计划，degraded_reasons 写明 action_value_failed 与原因；绝不拼
weighted_heuristic_v2 分数（合同 compatibility.legacy_delta）。
"""

from __future__ import annotations

from dataclasses import replace
from typing import FrozenSet, Optional, Sequence, Tuple

from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Action, Chi, Discard, Gang, Hu, Pass, Peng
from hangma_bot.kernel.observation import CompetitionContext

from .action_value import (
    CANDIDATE_KIND,
    PROGRESS_STATES,
    SCORING_VIEW_SCHEMA_VERSION,
    ActionView,
    AnalysisProfileView,
    CompetitionView,
    ReferenceFeature,
    ScoringView,
    batch_to_ranked_candidates,
)
from .action_value_executor import WorkloadExceeded
from .action_value_seeds import ActionValueScorer, build_action_value_policy
from .interface import (
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    ScorePart,
)

#: 规则分析语义版本（AnalysisProfileView.semantics_version 的取值来源）；
#: 分值/进展载荷语义变更时必须升级，候选身份随之变化。
VALUE_ANALYSIS_SEMANTICS_VERSION = "hangma-value-analysis/1"

# family_progress 元组坍缩为单一进展的显著性序：最显著的相对变化优先。
# 候选需要完整分家族明细时读 followup_branches/routes 事实；本字段是
# RuleAnalysis 全部家族条目的确定性摘要，同输入同输出。
_PROGRESS_SIGNIFICANCE: Tuple[str, ...] = (
    "ADVANCE", "RETREAT", "CLOSE", "SAME", "UNKNOWN",
)


def _action_type_of(action: Action) -> str:
    """从动作值对象取规则动作类型；封闭联合类型外的动作让投影整批失败。"""
    if isinstance(action, Discard):
        return "discard"
    if isinstance(action, Chi):
        return "chi"
    if isinstance(action, Peng):
        return "peng"
    if isinstance(action, Gang):
        return "gang"
    if isinstance(action, Hu):
        return "hu"
    if isinstance(action, Pass):
        return "pass"
    raise ValueError("未知动作类型: {0!r}".format(type(action).__name__))


def _collapse_family_progress(entries) -> str:
    """把 FamilyProgress 元组坍缩为单一进展字符串（ActionView 字段口径）。

    规则：取显著性最高的进展（ADVANCE>RETREAT>CLOSE>SAME>UNKNOWN）；
    空元组（未分析）保持 UNKNOWN。分家族明细仍在 followup_branches 与
    routes 事实里，本字段只是确定性的动作级摘要。
    """
    seen = {entry.progress.name for entry in entries}
    for state in _PROGRESS_SIGNIFICANCE:
        if state in seen:
            return state
    return "UNKNOWN"


def _competition_view(context: CompetitionContext) -> CompetitionView:
    """从 CompetitionContext 投影可见赛事上下文。

    CompetitionContext 只有按参赛者身份的排名条目（RankingEntry），没有
    按座位 0—3 的阶段/桌赛积分向量，排名到座位的映射也不可推导；首版
    全部投影 None，候选必须显式处理空值（合同 scoring_view.competition：
    无权获知或陈旧则为空），当前桌内积分另经 visible_state.table_scores。
    """
    _ = context
    return CompetitionView()


def build_scoring_view(
    request: DecisionRequest,
    *,
    reference_features: Sequence[ReferenceFeature] = (),
) -> ScoringView:
    """从 DecisionRequest 投影只读 ScoringView（v4 §4.1 第 3 步）。

    - actions 按 action_key 升序，集合只来自 request.rules（不重新判合法）；
    - followup_branches/family_progress 取 B1 载荷（None 保持 None）；
    - 立即结算取 value_facts.immediate_settlement；routes 是条件见证摘要；
    - visible_state 直接持有 request.observation（白名单访问器见 B2）；
    - analysis_profile 由 ruleset_version + ValueAnalysisLimits 默认值构造；
    - reference_features 默认空元组（首版无校准代理）。
    """
    limits = ValueAnalysisLimits()
    actions = []
    for candidate in sorted(
        request.rules.legal_candidates, key=lambda item: item.action_key
    ):
        facts = candidate.facts
        value_facts = candidate.value_facts
        actions.append(
            ActionView(
                action_key=candidate.action_key,
                action=candidate.action,
                action_type=_action_type_of(candidate.action),
                is_legal=True,
                followup_branches=(
                    None if facts is None else facts.followup_branches
                ),
                immediate_settlement=(
                    None if value_facts is None else value_facts.immediate_settlement
                ),
                family_progress=_collapse_family_progress(
                    () if facts is None else facts.family_progress
                ),
                routes=() if value_facts is None else value_facts.routes,
            )
        )
    return ScoringView(
        schema_version=SCORING_VIEW_SCHEMA_VERSION,
        visible_state=request.observation,
        actions=tuple(actions),
        analysis_profile=AnalysisProfileView(
            semantics_version=VALUE_ANALYSIS_SEMANTICS_VERSION,
            max_expansions=limits.max_expansions,
            max_routes_per_candidate=limits.max_routes_per_candidate,
            truncation_note="hangma.interface.ValueAnalysisLimits 默认上限",
            ruleset_version=request.rules.ruleset_version,
        ),
        competition=_competition_view(request.competition),
        reference_features=tuple(reference_features),
    )


class ActionValuePolicy:
    """action_value_v1 线上策略：固定骨架 + 受限执行候选评分器。

    不修改 choose/DecisionRequest/DecisionPlan 对外签名；不读取 WorldState、
    网络、文件或时钟；候选执行在工作量限额内完成，任何整批失败都降级到
    已备紧急计划。policy_id 供离线驱动记录（诊断身份，不进评分）。
    """

    def __init__(self, scorer: ActionValueScorer) -> None:
        self._scorer = scorer
        self.policy_id = "{kind}:{name}".format(kind=CANDIDATE_KIND, name=scorer.name)

    @classmethod
    def from_seed(cls, name: str) -> "ActionValuePolicy":
        """按种子名装配（静态注册表）；未知名字立即失败，不静默换策略。"""
        return cls(build_action_value_policy(name))

    @property
    def scorer_name(self) -> str:
        """候选种子名；进入策略诊断身份。"""
        return self._scorer.name

    async def choose(
        self,
        request: DecisionRequest,
        budget: DecisionBudget,
    ) -> DecisionPlan:
        """按 §4.1 第 3—6 步产出完整计划；budget 仅满足协议，不参与计算。"""
        rejected_keys = frozenset(
            item.action_key for item in request.rejected_attempts
        )
        try:
            view = build_scoring_view(request)
            batch = self._scorer.score(view)
            ranked = batch_to_ranked_candidates(batch, view.actions)
        except (ValueError, WorkloadExceeded) as exc:
            return self._degraded_plan(
                request, rejected_keys,
                "action_value_failed: 候选整批失败 {0}: {1}".format(
                    type(exc).__name__, exc
                ),
            )
        if not ranked:
            return self._degraded_plan(
                request, rejected_keys,
                "action_value_failed: ABSTAIN {0}".format(batch.reason),
            )
        return self._scored_plan(request, rejected_keys, ranked)

    # —— SCORED 路径：拒绝过滤、紧急保留、rank 从 1 连续 ——

    def _scored_plan(
        self,
        request: DecisionRequest,
        rejected_keys: FrozenSet[str],
        ranked: Tuple[RankedCandidate, ...],
    ) -> DecisionPlan:
        emergency = request.rules.emergency_candidate
        emergency_key = None if emergency is None else emergency.action_key
        selected: list[RankedCandidate] = []
        for candidate in ranked:
            if candidate.action_key in rejected_keys:
                continue
            if (
                candidate.action_key == emergency_key
                and not candidate.is_emergency
            ):
                candidate = replace(candidate, is_emergency=True)
            selected.append(candidate)
        if (
            emergency_key is not None
            and emergency_key not in rejected_keys
            and all(item.action_key != emergency_key for item in selected)
        ):
            selected.append(
                RankedCandidate(
                    action=emergency.action,
                    action_key=emergency_key,
                    rank=len(selected) + 1,
                    total_score=0.0,
                    score_parts=(ScorePart(
                        name=CANDIDATE_KIND + ".emergency", value=0.0
                    ),),
                    reasons=("action_value 排序未含紧急候选，追加保底",),
                    is_emergency=True,
                )
            )
        candidates = tuple(
            replace(item, rank=rank) for rank, item in enumerate(selected, start=1)
        )
        reasons = ["action_value: {0} 评分完成".format(self._scorer.name)]
        reasons.extend(
            "规则降级[{0}]：{1}".format(issue.area, issue.reason)
            for issue in request.rules.issues
        )
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=len(request.rejected_attempts) + 1,
            candidates=candidates,
            degraded_reasons=tuple(reasons),
        )

    # —— 失败降级：仅紧急候选 + 规则合法顺序；不拼任何 V2 分数 ——

    def _degraded_plan(
        self,
        request: DecisionRequest,
        rejected_keys: FrozenSet[str],
        reason: str,
    ) -> DecisionPlan:
        reasons = [
            reason,
            "action_value_failed: 降级为紧急候选 + 规则合法顺序，未拼 V2 分数",
        ]
        candidates: list[RankedCandidate] = []
        emergency = request.rules.emergency_candidate

        def _append(action, key, *, is_emergency: bool, why: str) -> None:
            candidates.append(
                RankedCandidate(
                    action=action,
                    action_key=key,
                    rank=len(candidates) + 1,
                    total_score=0.0,
                    score_parts=(ScorePart(
                        name=CANDIDATE_KIND + ".degraded", value=0.0
                    ),),
                    reasons=(why,),
                    is_emergency=is_emergency,
                )
            )

        if emergency is not None and emergency.action_key not in rejected_keys:
            _append(
                emergency.action, emergency.action_key,
                is_emergency=True, why="紧急候选优先（action_value 降级保底）",
            )
        else:
            reasons.append("紧急候选缺失或已被拒绝，降级计划按规则合法顺序")
        for candidate in sorted(
            request.rules.legal_candidates, key=lambda item: item.action_key
        ):
            if candidate.action_key in rejected_keys:
                continue
            if emergency is not None and candidate.action_key == emergency.action_key:
                continue
            _append(
                candidate.action, candidate.action_key,
                is_emergency=False, why="规则合法顺序兜底（action_value 降级）",
            )
        reasons.extend(
            "规则降级[{0}]：{1}".format(issue.area, issue.reason)
            for issue in request.rules.issues
        )
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=len(request.rejected_attempts) + 1,
            candidates=tuple(candidates),
            degraded_reasons=tuple(reasons),
        )


__all__ = [
    "ActionValuePolicy",
    "VALUE_ANALYSIS_SEMANTICS_VERSION",
    "build_scoring_view",
]
