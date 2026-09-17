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

# —— P11（M1 闭环）：赛事基准的掩码词表（冻结；变更即候选身份变化）——
#: freshness_masks 的**位置序**：下标 0/1 分别对应 stage_scores / table_scores。
#: 第三概念 current_stage_scores 不单列掩码位：它的可用性与 stage_scores 同掩码
#: （masks[0] == stage_account:complete 才非空），见 _current_stage_scores。
COMPETITION_MASK_BASES: Tuple[str, ...] = ("stage_scores", "table_scores")
#: stage_scores 的可用状态（freshness_masks[0] 取值，闭集）。
STAGE_ACCOUNT_COMPLETE = "stage_account:complete"      # 桌内座位序账完整可用
STAGE_ACCOUNT_ABSENT = "stage_account:absent"          # 尚无阶段账事实（无帐 ≠ 零）
STAGE_ACCOUNT_UNMAPPABLE = "stage_account:unmappable"  # 有排名事实但身份→座位不可映射
#: table_scores 的可用状态（freshness_masks[1] 取值，闭集）。
TABLE_ACCOUNT_LIVE = "table_account:live"              # 本桌进行中积分，恒可用
#: 闭集词表（合同 scoring_view.competition_bases.freshness_masks.values 逐字一致）。
COMPETITION_MASK_VALUES: Tuple[str, ...] = (
    STAGE_ACCOUNT_COMPLETE,
    STAGE_ACCOUNT_ABSENT,
    STAGE_ACCOUNT_UNMAPPABLE,
    TABLE_ACCOUNT_LIVE,
)

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


def _stage_account_vector(
    context: CompetitionContext, seat: int
) -> Tuple[Optional[Tuple[int, int, int, int]], str]:
    """把排名事实投影为**桌内座位序账**（阶段基准），不可映射即未知。

    契约（合同 scoring_view.competition_bases，P11/R7）：

    - **单位与顺序**：返回四元组的元素是「坐在物理座位 0—3 的身份在本阶段
      **已完成各完整桌赛**的积分之和」，单位与 `PlayerObservation.scores`、
      `RankingEntry.total_score` 一致（整数积分点，允许负分）；不含当前桌
      进行中的积分，不含名次分，不含未来桌赛结果。
    - **身份→座位映射**：唯一承认「桌内座位序账」——`ranking[i]` 是坐在
      物理座位 i 的参赛者的账（驱动 `offline.evaluate.StageSituationProjection
      .competition_context()` 逐位置构造，位置 i 与 `participant_ids_by_seat[i]`
      一一对应；面板侧由 `plan.seats()` 生成，换座后身份随座位搬移）。
      策略没有 `participant_id`（`DecisionRequest` 不含我方身份，kernel 契约
      不改），因此**我方身份的锚点是 `context.participant_rank`（我方名次，由
      驱动/适配器按座位发布）**：我方座位上的条目名次必须等于我方名次。
    - **可空条件**：`context.ranking` 为空 ⇒ 无阶段账事实（官方未提供或本
      阶段尚无已完成桌），返回 None + `stage_account:absent`；有排名事实但
      不满足下列任一必要条件 ⇒ 无法映射，返回 None +
      `stage_account:unmappable`。
    - **未知 ≠ 零**：任何缺失/不可映射一律 None，绝不补零、绝不把「无账」
      当成「四家同分」；反过来，`StageSituationProjection` 在无已完成桌时
      注入的**四座全 0 账**是已知的零，按 complete 投影（两者由掩码区分）。
    - **陈旧**：策略不读时钟，本投影不判陈旧；上游若判定排名陈旧，应注入
      空 ranking/None 名次（→ absent），不得注入陈旧数值冒充可用。

    准入必要条件（全部满足才是座位序账；逐条都在代码里，不靠注释约定）：

    1. 恰 4 条 —— 一桌四座；阶段级榜单（人数 ≠ 4）无法映射到本桌座位；
    2. 四个 `participant_id` 互不相同 —— 一席一身份；
    3. `participant_rank` 非空且 `ranking[seat].rank == participant_rank`
       —— 我方身份必须位于我方物理座位（唯一可核验的锚点）；
    4. 四条 `games_played` 相同 —— 四个座位覆盖同一批已完成桌；
    5. 名次与已知键 (total_score, place_points) 不矛盾 —— 名次是该键降序的
       单调函数（严格更大者名次不得更大）。

    残留风险（如实记录，见 FIX-REPORT §2.6）：平台级 4 人榜单恰好在 `seat` 位
    携带我方名次、且已完成局数一致时，与座位序账在结构上不可区分；此时
    投影会把榜单名次序误当作座位序。当前该通道的唯一生产者是离线驱动的
    桌内投影（P2 面板侧），并已由验收用例固定；若将来在线路径也要读该字段，
    必须先给 `CompetitionContext` 增加显式的座位序声明（属 kernel 契约变更）。
    """

    ranking = context.ranking
    if not ranking:
        return None, STAGE_ACCOUNT_ABSENT
    if not 0 <= seat < 4 or len(ranking) != 4:
        return None, STAGE_ACCOUNT_UNMAPPABLE
    identities = {entry.participant_id for entry in ranking}
    if len(identities) != 4:
        return None, STAGE_ACCOUNT_UNMAPPABLE
    if len({entry.games_played for entry in ranking}) != 1:
        return None, STAGE_ACCOUNT_UNMAPPABLE
    if context.participant_rank is None:
        return None, STAGE_ACCOUNT_UNMAPPABLE
    if ranking[seat].rank != context.participant_rank:
        return None, STAGE_ACCOUNT_UNMAPPABLE
    known_key = tuple(
        (entry.total_score, entry.place_points) for entry in ranking
    )
    for index in range(4):
        for other in range(4):
            if index == other:
                continue
            if known_key[index] > known_key[other] and (
                ranking[index].rank > ranking[other].rank
            ):
                return None, STAGE_ACCOUNT_UNMAPPABLE
    return tuple(int(entry.total_score) for entry in ranking), STAGE_ACCOUNT_COMPLETE


def _current_stage_scores(
    stage_scores: Optional[Tuple[int, int, int, int]],
    stage_mask: str,
    table_scores: Tuple[int, ...],
) -> Optional[Tuple[int, int, int, int]]:
    """三概念之三：当前阶段合计 = 已完成账 + 当前桌账（逐座位相加）。

    - **为什么可以相加**：两项同座位序（物理座位 0—3）、同单位（积分点）、
      **互不重叠**——`stage_scores` 只含本阶段**已完成各桌赛**的积分和，
      `table_scores` 只含**本桌进行中**积分。相加是重建完整当前阶段分数，
      不是重复累计，因此是阶段门线的唯一正确基准。
    - **唯一禁止的重复累计**：`table_scores` 与同一份
      `visible_state.table_scores` 相加（同一事实的两个基准名，相加即翻倍）；
      该禁令在 `CompetitionView.__post_init__` 由一致性检查兜底。
    - **未知 ≠ 零**：`stage_scores` 缺账（absent/unmappable）时它同时为 None，
      不得用 `table_scores` 顶替当阶段账，也不得补零。
    """
    if stage_mask != STAGE_ACCOUNT_COMPLETE or stage_scores is None:
        return None
    return tuple(
        int(completed) + int(live)
        for completed, live in zip(stage_scores, table_scores)
    )


def _competition_view(
    context: CompetitionContext, seat: int, table_scores: Tuple[int, ...]
) -> CompetitionView:
    """从 CompetitionContext + 本桌观察座位投影可见赛事上下文（P11/M1 + R8 E3）。

    三份账分别命名、各自可空（机器合同 scoring_view.competition_bases）：

    - `stage_scores`（**已完成账**）：本阶段**已完成桌**的座位序阶段账
      （单位：积分点；顺序：物理座位 0—3），经 `_stage_account_vector` 投影；
      无账/不可映射时为 None（未知，不是全 0）。
    - `table_scores`（**当前桌账**）：本桌**进行中**积分，直接来自本窗口
      `PlayerObservation.scores`（座位 0—3；与候选可见的
      `visible_state.table_scores` 是同一事实的两个基准名）；本桌积分对本人
      恒可见，故恒投影、不报未知。
    - `current_stage_scores`（**当前阶段合计**）：前两账逐座位相加，见
      `_current_stage_scores`；相加合法（同座位序、同单位、互不重叠），
      被禁止的只有「同一份本桌积分按两个基准名相加」。
    - `freshness_masks`：固定两元组，位置序 `COMPETITION_MASK_BASES`
      （下标 0 = stage_scores、1 = table_scores），取值来自闭集
      `COMPETITION_MASK_VALUES`；基准不可用时掩码说明原因，掩码本身仍然
      给出（缺账的原因是可核事实，不是未知）。`current_stage_scores` 的
      可用性与 `stage_scores` 同掩码（masks[0] == complete 才非空），
      故不单列第三个掩码位。
    - **未投影的可见事实**（合同 `residual_gaps` 显式登记）：剩余赛程
      （`CompetitionContext.stage_no`/`stage_total`）不进候选视图——把剩余
      桌数从 0 改为 6，候选视图逐字不变；不得默认它已可见。
    """
    stage_scores, stage_mask = _stage_account_vector(context, seat)
    live_scores = tuple(int(score) for score in table_scores)
    return CompetitionView(
        stage_scores=stage_scores,
        table_scores=live_scores,
        freshness_masks=(stage_mask, TABLE_ACCOUNT_LIVE),
        current_stage_scores=_current_stage_scores(
            stage_scores, stage_mask, live_scores
        ),
    )


def build_scoring_view(
    request: DecisionRequest,
    *,
    reference_features: Sequence[ReferenceFeature] = (),
    value_limits: Optional[ValueAnalysisLimits] = None,
) -> ScoringView:
    """从 DecisionRequest 投影只读 ScoringView（v4 §4.1 第 3 步；R2/S2 补全事实）。

    - actions 按 action_key 升序，集合只来自 request.rules（不重新判合法）；
    - followup_branches/family_progress 取 B1 载荷（None 保持 None），完整
      分家族明细经 family_progress_entries 透传（单串摘要字段并存）；
    - 普通弃牌/过牌的显式牌效事实（fact_kind/shanten_after/useful_tiles/
      standard/seven_pairs 向听与推进牌/杠补未知/最佳后续弃牌）直投影自
      CandidateFacts——不重新实现规则数学，也不为普通弃牌伪造分支；
    - 立即结算取 value_facts.immediate_settlement；routes 是条件见证摘要，
      value_coverage/value_issues 透传覆盖状态与截断/缺证据原因；
    - visible_state 直接持有 request.observation（白名单访问器见 B2）；
    - competition 由 `_competition_view` 投影：stage_scores = 已完成桌的座位序
      阶段账（无账/不可映射为 None），table_scores = 本桌进行中积分，
      freshness_masks 位置序 [stage_scores, table_scores]（P11/M1 闭环）；
    - analysis_profile 由 ruleset_version + 实际 ValueAnalysisLimits 构造：
      value_limits 由调用方传入实际分析配置；缺省时按默认上限快照并在
      truncation_note 明示（不冒充实际配置）；
    - reference_features 默认空元组（首版无校准代理）。
    """
    limits = value_limits if value_limits is not None else ValueAnalysisLimits()
    truncation_note = (
        "实际分析配置 ValueAnalysisLimits(max_expansions={0},"
        " max_routes_per_candidate={1})；动作级覆盖见 value_coverage/value_issues".format(
            limits.max_expansions, limits.max_routes_per_candidate
        )
        if value_limits is not None
        else "未显式提供分析配置，按 ValueAnalysisLimits 默认上限快照"
             "（max_expansions={0}, max_routes_per_candidate={1}）；"
             "动作级覆盖见 value_coverage/value_issues".format(
                 limits.max_expansions, limits.max_routes_per_candidate
             )
    )
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
                fact_kind=(
                    None if facts is None else facts.fact_kind.value
                ),
                shanten_after=None if facts is None else facts.shanten_after,
                useful_tiles=() if facts is None else facts.useful_tiles,
                replacement_draw_unknown=(
                    None if facts is None else facts.replacement_draw_unknown
                ),
                best_followup_discard=(
                    None if facts is None else facts.best_followup_discard
                ),
                standard_shanten_after=(
                    None if facts is None else facts.standard_shanten_after
                ),
                seven_pairs_shanten_after=(
                    None if facts is None else facts.seven_pairs_shanten_after
                ),
                standard_useful_tiles=(
                    None if facts is None else facts.standard_useful_tiles
                ),
                seven_pairs_useful_tiles=(
                    None if facts is None else facts.seven_pairs_useful_tiles
                ),
                pattern_progress_note=(
                    None if facts is None else facts.pattern_progress_note
                ),
                family_progress_entries=(
                    () if facts is None else facts.family_progress
                ),
                value_coverage=(
                    None if value_facts is None else value_facts.coverage.value
                ),
                value_issues=(
                    () if value_facts is None else value_facts.issues
                ),
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
            truncation_note=truncation_note,
            ruleset_version=request.rules.ruleset_version,
        ),
        competition=_competition_view(
            request.competition, request.observation.seat, request.observation.scores
        ),
        reference_features=tuple(reference_features),
    )


class ActionValuePolicy:
    """action_value_v1 线上策略：固定骨架 + 受限执行候选评分器。

    不修改 choose/DecisionRequest/DecisionPlan 对外签名；不读取 WorldState、
    网络、文件或时钟；候选执行在工作量限额内完成，任何整批失败都降级到
    已备紧急计划。policy_id 供离线驱动记录（诊断身份，不进评分）。
    """

    def __init__(
        self,
        scorer: ActionValueScorer,
        *,
        value_limits: Optional[ValueAnalysisLimits] = None,
    ) -> None:
        self._scorer = scorer
        # R2/S2：实际分析配置快照——组合根/离线驱动把与 rules.analyze 同一
        # 口径的 ValueAnalysisLimits 传入，analysis_profile 透传实际值；
        # 缺省 None 时投影按默认上限快照并明示（见 build_scoring_view）。
        self._value_limits = value_limits
        self.policy_id = "{kind}:{name}".format(kind=CANDIDATE_KIND, name=scorer.name)

    @classmethod
    def from_seed(
        cls, name: str, *, value_limits: Optional[ValueAnalysisLimits] = None
    ) -> "ActionValuePolicy":
        """按种子名装配（静态注册表）；未知名字立即失败，不静默换策略。"""
        return cls(build_action_value_policy(name), value_limits=value_limits)

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
            view = build_scoring_view(request, value_limits=self._value_limits)
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
    "COMPETITION_MASK_BASES",
    "COMPETITION_MASK_VALUES",
    "STAGE_ACCOUNT_ABSENT",
    "STAGE_ACCOUNT_COMPLETE",
    "STAGE_ACCOUNT_UNMAPPABLE",
    "TABLE_ACCOUNT_LIVE",
    "VALUE_ANALYSIS_SEMANTICS_VERSION",
    "build_scoring_view",
]
