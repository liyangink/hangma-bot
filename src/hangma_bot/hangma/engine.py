"""杭麻规则深模块公开实现：组装子模块并施加故障隔离与最终复核。

职责（模块 AGENTS.md 主 Agent 独占）：
- 从 `PlayerObservation` 提取机械事实构造 `WindowContext`；
- 先取独立紧急路径，再隔离地执行手牌分析与六动作族生成；
- 应用有财必拷响过滤（special_rules 判定，保守方向宁漏胡不 409）；
- 保证 `RuleAnalysis` 接口不变量（action_key 唯一、紧急候选成员性、
  降级显式可审计）；
- `validate` 以"重新分析 + 候选成员关系"实现单一规则源复核；
- `score` 委托 settlement，爆头/链以 `rule_state` 平台权威状态为准。

故障隔离设计：`hand_analysis` 在方法内延迟导入——该子模块缺失或
import 期损坏时，`analyze` 降级为 RuleIssue（其余候选与紧急路径照常），
而不是整个模块不可用；这与"任一复杂分支异常不得丢失紧急动作"的
模块约束一致。规则依据：`RULES_EVIDENCE.md`（官方指南 v9）。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Action, Discard, Tile, action_key
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation

from . import action_families, settlement, special_rules
from .catch_play import analyze_catch_play
from .emergency import emergency_action
from .progression_payload import ProgressionPayloadError
from .observation_rules import enrich_observation
from .interface import (
    ActionValidation,
    CandidateValueFacts,
    PublicSuccessorAnalysis,
    PublicSuccessorCoverage,
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
    Settlement,
    ValueAnalysisLimits,
    ValueCoverage,
    WinDescription,
)
from .internal_types import WEALTH_CODE, WindowContext

# 稳定 RuleIssue.area：与子模块命名（action_families.<族> / hand_analysis / candidate_facts）对齐。
_AREA_CONTEXT = "engine.context"
_AREA_EMERGENCY = "engine.emergency"
_AREA_HAND = "hand_analysis"
_AREA_FAMILY = "action_families"
_AREA_YOUCAI = "special_rules.youcai"
_AREA_FACTS = "candidate_facts"

_DRAW_PHASE = "draw"


class HangmaRules:
    """杭麻合法动作、胡牌、向听、有效牌和结算的唯一规则深模块。"""

    def __init__(self, config: RuleConfig) -> None:
        """把不可变赛事规则绑定到实例；运行中不得替换。"""

        self.config = config

    # ------------------------------------------------------------------
    # analyze：一个动作窗口的完整规则分析
    # ------------------------------------------------------------------

    def analyze(
        self, observation: PlayerObservation, *,
        value_limits: Optional[ValueAnalysisLimits] = None,
        route_limits: Optional[ValueAnalysisLimits] = None,
    ) -> RuleAnalysis:
        """先构造紧急动作，再隔离分析各动作族；不访问网络或时钟。

        value_limits 默认关闭；显式启用后补充一次未来摸牌的条件结算。
        增强失败只标记 value_facts，不改变已生成的合法候选和基础牌效。
        route_limits 显式开启 P1 条件前沿；其工作上限当前复用一次摸牌
        资格检查上限，公开后继投影的工作量另在研发证据中报告。
        """

        if value_limits is not None and not isinstance(value_limits, ValueAnalysisLimits):
            raise ValueError("value_limits 必须是 ValueAnalysisLimits 或 None")
        if route_limits is not None and not isinstance(route_limits, ValueAnalysisLimits):
            raise ValueError("route_limits 必须是 ValueAnalysisLimits 或 None")
        if value_limits is not None and route_limits is not None and value_limits != route_limits:
            raise ValueError("路线与一次摸牌分析必须使用同一 ValueAnalysisLimits")
        effective_value_limits = route_limits if route_limits is not None else value_limits

        issues: list = [
            RuleIssue("observation", message) for message in observation.observation_issues
        ]
        observation = enrich_observation(observation)
        circle = analyze_catch_play(observation)
        if circle.issue is not None:
            issues.append(RuleIssue("catch_play.owner", circle.issue))
        if observation.rule_state.chain_count > 0 and observation.chain_piao is None:
            issues.append(RuleIssue("observation.chain_piao", "当前链历史不足，链内飘次数未知，结算不可核验"))

        emergency = self._safe_emergency(observation, issues)
        context = self._safe_context(observation, issues)
        if _concealed_missing_drawn_instance(observation):
            # P2-N1：官方「含摸牌」形态长度命中但 my_hand 缺 drawn 同码实例——
            # 归一化静默跳过会把判定留在幻影双计口径。显式记 RuleIssue
            # （DEGRADED 可审计），宁让消费方降级处理也不无标记通过。
            issues.append(
                RuleIssue(
                    _AREA_CONTEXT,
                    "手牌形态异常：my_hand 长度符合官方含摸牌形态（14−3×副露数）"
                    "但未找到与 drawn_tile 同码实例，防双计归一化未生效，"
                    "胡候选按未归一化口径判定（_concealed_missing_drawn_instance）",
                )
            )

        candidates: Tuple[RuleCandidate, ...] = ()
        if context is not None:
            hand = self._safe_hand_summary(observation, context, issues)
            try:
                outcome = action_families.generate_candidates(context, hand)
                candidates = outcome.candidates
                issues.extend(outcome.issues)
            except Exception as exc:  # 故障边界：组合器异常不得整体崩溃
                issues.append(
                    RuleIssue(
                        _AREA_FAMILY,
                        "动作族组合器异常: {0}: {1}".format(type(exc).__name__, exc),
                    )
                )
                candidates = ()
            candidates = self._filter_youcai(observation, context, candidates, issues)
            candidates = self._attach_facts(observation, context, candidates, issues)
            if effective_value_limits is not None:
                candidates = self._attach_value_facts(
                    observation, context, candidates, effective_value_limits, issues
                )

        candidates = _ensure_emergency_membership(candidates, emergency)
        if circle.active and circle.owner_seat is not None:
            evidence = "抓打圈:圈主={0},开圈seq={1},本人受限={2},依据={3}".format(
                circle.owner_seat, circle.started_seq, circle.restricts(observation.seat), circle.source,
            )
            candidates = tuple(replace(candidate, evidence=candidate.evidence + (evidence,)) for candidate in candidates)
            if emergency is not None:
                emergency = next(candidate for candidate in candidates if candidate.action_key == emergency.action_key)

        completeness = (
            RuleCompleteness.DEGRADED if issues else RuleCompleteness.COMPLETE
        )
        route_frontier = None
        conditional_roots = None
        if route_limits is not None:
            route_frontier = self._analyze_route_frontier(
                observation, context, candidates, completeness
            )
            conditional_roots = self._analyze_conditional_roots(
                observation, context, candidates, completeness,
            )
        return RuleAnalysis(
            legal_candidates=candidates,
            emergency_candidate=emergency,
            completeness=completeness,
            ruleset_version=self.config.ruleset_version,
            issues=tuple(issues),
            route_frontier=route_frontier,
            conditional_roots=conditional_roots,
        )

    def _analyze_conditional_roots(
        self,
        observation: PlayerObservation,
        context: Optional[WindowContext],
        candidates: Tuple[RuleCandidate, ...],
        completeness: RuleCompleteness,
    ):
        """显式研发根逐一保留；投影异常不得破坏合法集或紧急候选。"""

        from .route_frontier import RouteGapKind
        from .route_transition import ConditionalRoot, project_legal_roots

        reason = None
        kind = RouteGapKind.INPUT_EVIDENCE_GAP
        if context is None or completeness is not RuleCompleteness.COMPLETE:
            reason = "当前规则输入或合法动作分析未完整，不能建立 P2 条件根"
        elif self.config.base_score != 1 or self.config.you_cai_bi_kao:
            kind = RouteGapKind.MECHANICAL_GAP
            reason = "P2 条件根尚未覆盖该规则配置"
        if reason is not None:
            return tuple(ConditionalRoot(
                candidate.action_key, (), gap_kind=kind,
                issues=(RuleIssue("route_transition.root", reason),),
            ) for candidate in candidates)
        try:
            roots = project_legal_roots(
                observation, context, candidates, config=self.config,
            )
            if tuple(root.action_key for root in roots) != tuple(
                candidate.action_key for candidate in candidates
            ):
                raise ValueError("P2 条件根与同次合法候选顺序或集合不一致")
            return roots
        except Exception as exc:
            reason = "条件根投影异常: {0}: {1}".format(type(exc).__name__, exc)
            return tuple(ConditionalRoot(
                candidate.action_key, (), gap_kind=RouteGapKind.MECHANICAL_GAP,
                issues=(RuleIssue("route_transition.root", reason),),
            ) for candidate in candidates)

    def _analyze_route_frontier(
        self,
        observation: PlayerObservation,
        context: Optional[WindowContext],
        candidates: Tuple[RuleCandidate, ...],
        completeness: RuleCompleteness,
    ):
        """用本次合法候选拼接 P1 事实；研究故障不得改变合法候选。"""

        from .public_successor import analyze_public_self_draw_successors
        from .route_frontier import RouteFrontierDraft, RouteFrontierRoot, RouteGapKind, join_one_draw_frontier

        if context is None or completeness is not RuleCompleteness.COMPLETE:
            reason = "当前规则输入/合法候选未完整，路线资格不能确证"
            return RouteFrontierDraft(
                roots=tuple(RouteFrontierRoot(
                    action_key=candidate.action_key,
                    gap_kind=RouteGapKind.INPUT_EVIDENCE_GAP,
                    issues=(RuleIssue("route_frontier.input_evidence_gap", reason),),
                ) for candidate in candidates),
                ruleset_version=self.config.ruleset_version,
            )
        if context.phase != _DRAW_PHASE or context.turn_seat != context.seat or observation.gang_draw is True:
            reason = (
                "P2 尚未闭合响应动作或杠补已落地后的连续条件转移；"
                "这是正常机械待办，不能由旧策略续打"
            )
            return RouteFrontierDraft(
                roots=tuple(RouteFrontierRoot(
                    action_key=candidate.action_key,
                    gap_kind=RouteGapKind.MECHANICAL_GAP,
                    issues=(RuleIssue("route_frontier.mechanical_gap", reason),),
                ) for candidate in candidates),
                ruleset_version=self.config.ruleset_version,
            )
        try:
            public_counts = _public_counts(observation)
            successors = analyze_public_self_draw_successors(
                context,
                public_counts,
                len(observation.melds[observation.seat]),
                tuple(candidate for candidate in candidates if isinstance(candidate.action, Discard)),
                self.config,
            )
            return join_one_draw_frontier(
                candidates,
                successors,
                expected_ruleset_version=self.config.ruleset_version,
                ordinary_draw_source_proven=observation.gang_draw is False,
                white_capacity_evidence_complete=(
                    observation.rule_state.chain_count == 0
                    or (
                        observation.chain_piao is not None
                        and observation.chain_piao <= sum(
                            tile.code == WEALTH_CODE
                            for tile in observation.discards[observation.seat]
                        )
                    )
                ),
                you_cai_bi_kao=self.config.you_cai_bi_kao,
            )
        except Exception as exc:
            reason = "路线前沿组合异常: {0}: {1}".format(type(exc).__name__, exc)
            return RouteFrontierDraft(
                roots=tuple(RouteFrontierRoot(
                    action_key=candidate.action_key,
                    gap_kind=RouteGapKind.MECHANICAL_GAP,
                    issues=(RuleIssue("route_frontier.mechanical_gap", reason),),
                ) for candidate in candidates),
                ruleset_version=self.config.ruleset_version,
            )

    def validate(self, observation: PlayerObservation, action: Action) -> ActionValidation:
        """按当前观察重新复核动作；无副作用且不调用官方 API。

        复核语义是"重新分析 + 候选成员关系"：合法候选由同一规则源生成，
        避免在 validate 中出现第二套合法性判断。
        """

        try:
            key = action_key(action)
        except TypeError as exc:
            return ActionValidation(legal=False, reason="未知动作类型: {0}".format(exc))
        analysis = self.analyze(observation)
        if any(candidate.action_key == key for candidate in analysis.legal_candidates):
            return ActionValidation(legal=True, reason=None)
        return ActionValidation(
            legal=False,
            reason=(
                "动作 {0} 不在当前窗口合法候选中（phase={1}, turn={2}, "
                "responding={3}, 候选 {4} 个）".format(
                    key,
                    observation.phase,
                    observation.turn_seat,
                    tuple(observation.responding_seats),
                    len(analysis.legal_candidates),
                )
            ),
        )

    def emergency_action(self, observation: PlayerObservation) -> Optional[RuleCandidate]:
        """以独立最小路径返回过、受限摸切或优先非财弃牌；不调用牌型搜索。"""

        return emergency_action(observation)

    def analyze_public_self_draw_successors(
        self,
        observation: PlayerObservation,
    ) -> PublicSuccessorAnalysis:
        """批量分析合法弃牌根的公开自摸后继；不构造未来观察。

        首版只覆盖本人摸牌出牌窗口。响应窗口返回显式
        ``UNAVAILABLE``，策略应回退稳定 V2。合法弃牌根始终由本实例
        针对本次 ``PlayerObservation`` 内部生成；公开契约不接收外部
        ``RuleAnalysis``，避免同规则版本的旧窗口分析被错误复用。

        返回的公开未见张数只是容量，不是概率。方法不读取时钟、GC、
        文件、网络或 ``WorldState``；任何未来规则资格未知都写入 issues。
        """

        observation = enrich_observation(observation)
        try:
            context = _build_context(observation)
            public_counts = _public_counts(observation)
            meld_count = len(observation.melds[observation.seat])
            discard_outcome = action_families.discard_candidates(context)
        except Exception as exc:
            return PublicSuccessorAnalysis(
                phase=observation.phase,
                coverage=PublicSuccessorCoverage.UNAVAILABLE,
                roots=(),
                ruleset_version=self.config.ruleset_version,
                issues=(
                    RuleIssue(
                        "public_successor.context",
                        "公开后继上下文提取异常: {0}: {1}".format(
                            type(exc).__name__, exc
                        ),
                    ),
                ),
            )
        if discard_outcome.issues:
            return PublicSuccessorAnalysis(
                phase=observation.phase,
                coverage=PublicSuccessorCoverage.UNAVAILABLE,
                roots=(),
                ruleset_version=self.config.ruleset_version,
                issues=tuple(
                    RuleIssue(
                        "public_successor.root",
                        "合法弃牌根生成不完整: {0}: {1}".format(
                            issue.area, issue.reason
                        ),
                    )
                    for issue in discard_outcome.issues
                ),
            )
        from .public_successor import analyze_public_self_draw_successors

        return analyze_public_self_draw_successors(
            context,
            public_counts,
            meld_count,
            discard_outcome.candidates,
            self.config,
        )

    def score(self, win: WinDescription) -> Settlement:
        """按绑定规则计算四家结算；不读取运行时外部状态。

        爆头与链计数取 `rule_state` 平台权威状态；链内飘次数须有明确
        观察事实或连续历史后缀证据，未知时抛 ValueError，不臆造分数。
        未成胡（分解为空）返回流局口径的
        全零结算，供审计路径防御性调用。
        """

        observation = enrich_observation(win.observation)
        full_hand = _full_hand(observation)
        meld_count = len(observation.melds[observation.seat])
        split = None
        try:
            from . import hand_analysis

            split = hand_analysis.win_split(full_hand, meld_count)
        except Exception:  # 分解失败按未确认胡处理，不臆造番数
            split = None
        if split is None:
            return Settlement(score_delta=(0, 0, 0, 0), fan=0, details=())

        chain_count = observation.rule_state.chain_count
        piao = observation.chain_piao
        if piao is None:
            raise ValueError("当前链内飘次数未知，不能给出确定结算")
        return settlement.settle_win(
            split,
            chain_count,
            piao,
            observation.rule_state.baotou,
            self.config.base_score,
            win.winner_seat,
            observation.dealer_seat,
            pre_draw_hand=_concealed_without_drawn(observation),
            meld_set_count=meld_count,
        )

    # ------------------------------------------------------------------
    # 内部装配与故障边界
    # ------------------------------------------------------------------

    def _safe_emergency(
        self, observation: PlayerObservation, issues: list
    ) -> Optional[RuleCandidate]:
        """紧急路径独立可用；其自身异常不得影响候选生成。"""

        try:
            return emergency_action(observation)
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_EMERGENCY,
                    "紧急路径异常: {0}: {1}".format(type(exc).__name__, exc),
                )
            )
            return None

    def _safe_context(
        self, observation: PlayerObservation, issues: list
    ) -> Optional[WindowContext]:
        """观察 → 机械事实；提取失败时保留紧急路径、放弃候选生成。"""

        try:
            return _build_context(observation)
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_CONTEXT,
                    "窗口上下文提取异常: {0}: {1}".format(type(exc).__name__, exc),
                )
            )
            return None

    def _safe_hand_summary(
        self,
        observation: PlayerObservation,
        context: WindowContext,
        issues: list,
    ):
        """摸牌出牌窗口才需要手牌分析；失败降级为 None（胡族保守降级）。"""

        if not _is_own_draw(context):
            return None
        try:
            from . import hand_analysis

            return hand_analysis.analyse_hand(
                context.full_hand(), len(observation.melds[observation.seat])
            )
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_HAND,
                    "手牌分析异常: {0}: {1}".format(type(exc).__name__, exc),
                )
            )
            return None

    def _filter_youcai(
        self,
        observation: PlayerObservation,
        context: WindowContext,
        candidates: Tuple[RuleCandidate, ...],
        issues: list,
    ) -> Tuple[RuleCandidate, ...]:
        """按赛事开关要求有财必须爆头；杠补只影响计番，不豁免资格。

        正常规则排除的原因进入剩余候选证据；只有分解失败才记降级。
        依据 RULES_EVIDENCE §7 的用户确认与两次官方拒胡反例。
        """

        if not self.config.you_cai_bi_kao:
            return candidates
        if not any(candidate.action_key == "hu" for candidate in candidates):
            return candidates
        whites_held = sum(
            1 for tile in _full_hand(observation) if tile.code == WEALTH_CODE
        )
        if whites_held == 0:
            return candidates
        try:
            from . import hand_analysis

            split = hand_analysis.win_split(
                _full_hand(observation), len(observation.melds[observation.seat])
            )
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_YOUCAI,
                    "有财必拷响判定所需分解异常: {0}: {1}".format(
                        type(exc).__name__, exc
                    ),
                )
            )
            split = None
        if split is None:
            issues.append(
                RuleIssue(
                    _AREA_YOUCAI,
                    "有财必拷响：手留财神 {0} 张但无法完成资格核验，保守排除胡候选（§7）".format(
                        whites_held
                    ),
                )
            )
            return tuple(c for c in candidates if c.action_key != "hu")
        block = special_rules.you_cai_bi_kao_block(
            self.config.you_cai_bi_kao,
            split,
            observation.rule_state.baotou,
        )
        if block is None:
            return candidates
        return tuple(
            replace(c, evidence=c.evidence + (block,))
            for c in candidates if c.action_key != "hu"
        )

    def _attach_facts(
        self,
        observation: PlayerObservation,
        context: WindowContext,
        candidates: Tuple[RuleCandidate, ...],
        issues: list,
    ) -> Tuple[RuleCandidate, ...]:
        """给合法候选附加动作后牌效事实（契约 §4.1）；失败兜底为未生产。

        事实模块延迟导入（与 hand_analysis 同一故障隔离思路）：模块缺失
        或整体异常时保留原候选（facts=None）并记 RuleIssue——消费方按
        未知处理，不影响候选合法性与紧急路径。单个候选的分析失败由
        candidate_facts 内部收敛为 ANALYSIS_FAILED 事实与对应 Issue。
        """

        try:
            from . import candidate_facts

            attached, fact_issues = candidate_facts.attach_facts(
                context,
                _public_counts(observation),
                len(observation.melds[observation.seat]),
                candidates,
            )
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_FACTS,
                    "牌效事实生产异常: {0}: {1}".format(type(exc).__name__, exc),
                )
            )
            return candidates
        issues.extend(fact_issues)
        return attached

    def _attach_value_facts(
        self, observation: PlayerObservation, context: WindowContext,
        candidates: Tuple[RuleCandidate, ...], limits: ValueAnalysisLimits,
        issues: list,
    ) -> Tuple[RuleCandidate, ...]:
        """有限分值分析与进展载荷的独立故障边界；异常不使合法动作族退化或丢失紧急动作。

        两条口径（模块规范）：进展载荷（facts 家族进展）失败计入 issues
        并显式 DEGRADED；可选分值分析自身失败只收敛到各候选
        value_facts.issues，不降低 RuleAnalysis.completeness（契约行为）。
        """
        try:
            from .value_analysis import attach_value_facts

            return attach_value_facts(
                observation, context, _public_counts(observation),
                len(observation.melds[observation.seat]), self.config, candidates, limits,
            )
        except ProgressionPayloadError as exc:
            issues.append(
                RuleIssue(
                    "progression_payload",
                    "进展载荷异常: {0}: {1}".format(type(exc).__name__, exc),
                )
            )
            failed = CandidateValueFacts(
                coverage=ValueCoverage.UNAVAILABLE,
                issues=(RuleIssue("progression_payload", str(exc)),),
            )
            return tuple(replace(candidate, value_facts=failed) for candidate in candidates)
        except Exception as exc:
            failed = CandidateValueFacts(
                coverage=ValueCoverage.UNAVAILABLE,
                issues=(RuleIssue("value_analysis", "分值分析异常: {0}: {1}".format(type(exc).__name__, exc)),),
            )
            return tuple(replace(candidate, value_facts=failed) for candidate in candidates)


# ---------------------------------------------------------------------------
# 纯装配助手
# ---------------------------------------------------------------------------


def _build_context(observation: PlayerObservation) -> WindowContext:
    """从观察提取动作族生成所需机械事实（信息权限不变）。

    副露种类按 kernel 约定（`PublicMeld.kind` 为 chi/peng/gang 前缀
    字符串，适配器负责映射）统计：吃次数用于两摊上限，碰牌值用于补杠。
    hand_tiles 先经 _concealed_without_drawn 归一化（防御官方快照
    「my_hand 含摸牌」形态的重复计数，见该函数 docstring）。
    """

    seat = observation.seat
    my_melds = observation.melds[seat]
    chi_count = sum(1 for meld in my_melds if meld.kind.startswith("chi"))
    peng_codes = tuple(
        meld.tiles[0].code for meld in my_melds if meld.kind.startswith("peng")
    )
    return WindowContext(
        seat=seat,
        phase=observation.phase,
        turn_seat=observation.turn_seat,
        responding_seats=tuple(observation.responding_seats),
        hand_tiles=_concealed_without_drawn(observation),
        drawn_tile=observation.drawn_tile,
        my_chi_count=chi_count,
        my_peng_codes=peng_codes,
        last_discard=observation.last_discard,
        catch_play=analyze_catch_play(observation).restricts(seat),
        remaining_tile_count=observation.remaining_tile_count,
    )


def _public_counts(observation: PlayerObservation) -> Tuple[Optional[int], ...]:
    """仅在候选事实隔离区计算公开牌重叠；未知计数不影响动作合法性。"""
    from .public_tile_counts import count_public_tiles

    return count_public_tiles(observation)


def _is_own_draw(context: WindowContext) -> bool:
    """本人摸牌出牌窗口（与 action_families._own_draw 同语义的机械判定）。"""

    return context.phase == _DRAW_PHASE and context.turn_seat == context.seat


def _full_hand(observation: PlayerObservation) -> Tuple[Tile, ...]:
    """暗牌全集 = 手牌 + 刚摸牌；保留官方顺序，摸牌置尾。

    手牌先经 _concealed_without_drawn 归一化：官方快照实测形态
    「my_hand 含摸牌」与契约形态「my_hand 不含摸牌」并存时，
    避免摸牌被重复计数（重复计数会把胡牌判定放宽出 409 误报）。
    """

    hand = _concealed_without_drawn(observation)
    if observation.drawn_tile is None:
        return hand
    return hand + (observation.drawn_tile,)


def _concealed_without_drawn(observation: PlayerObservation) -> Tuple[Tile, ...]:
    """把 my_hand 归一化为「不含单列摸牌」的暗牌元组（防御性兼容两种官方形态）。

    官方依据与为什么（2026-09-04 实测，tests/fixtures/official/captures/
    state-draw-phase-t_714a42392cba.json）：官方快照在摸牌窗口把刚摸的牌
    同时放进 my_hand 末尾（该形态下 my_hand 长度 = 14 - 3×副露数）并
    单列 drawn_tile；而契约形态（interface-contracts §10.1）要求 my_hand
    不含摸牌（长度 = 13 - 3×副露数）。引擎若不归一化，`my_hand + drawn_tile`
    会把摸牌双计为 15 - 3×副露数 张暗牌——胡牌判定的「多余牌视为可弃」
    语义会把摸牌幻影副本当作可用的对/刻/顺，产生官方不认可的胡候选
    （2026-09-04 测试赛 97 次 409 INVALID_ACTION 的根因之一，差分复现见
    tests/unit/hangma/test_hu_differential_replay.py）。

    判定规则：drawn_tile 存在且 my_hand 长度恰为 14 - 3×副露数（即官方
    「含摸牌」形态）时，从 my_hand 移除一个与摸牌同码的实例（物理张数
    不因移除位置而变）；长度不符或未找到同码实例时原样返回（契约形态
    或防御性兜底）。该归一化只影响计数，不改变牌面信息权限。
    """

    hand = tuple(observation.my_hand)
    drawn = observation.drawn_tile
    if drawn is None:
        return hand
    expected_concealed = 14 - 3 * len(observation.melds[observation.seat])
    if len(hand) != expected_concealed:
        return hand  # 契约形态（不含摸牌）或观察不完整：不做改动
    for index in range(len(hand) - 1, -1, -1):
        if hand[index].code == drawn.code:
            return hand[:index] + hand[index + 1 :]
    return hand  # 防御：长度吻合但无同码实例，原样返回（异常由
    # _concealed_missing_drawn_instance 检出并在 analyze 层记 RuleIssue）


def _concealed_missing_drawn_instance(observation: PlayerObservation) -> bool:
    """长度命中官方「含摸牌」形态（14−3×副露数）但 my_hand 中没有与
    drawn_tile 同码的实例（P2-N1）：官方形态假设被破坏、归一化静默跳过会
    回到 15−3×副露数的幻影双计口径。analyze 层据此记 RuleIssue（DEGRADED），
    不让异常形态无标记通过。
    """

    drawn = observation.drawn_tile
    if drawn is None:
        return False
    expected = 14 - 3 * len(observation.melds[observation.seat])
    if len(observation.my_hand) != expected:
        return False
    return not any(tile.code == drawn.code for tile in observation.my_hand)


def _ensure_emergency_membership(
    candidates: Tuple[RuleCandidate, ...], emergency: Optional[RuleCandidate]
) -> Tuple[RuleCandidate, ...]:
    """接口不变量：紧急候选存在时必须出现在合法候选中。

    紧急路径按最小规则构造（响应过 / 抓打牌 / 官方顺序最右一张），
    其合法性由构造保证；正常情况下动作族已包含同一候选，此函数只在
    出牌族整体降级等边界补齐成员关系。
    """

    if emergency is None:
        return candidates
    if any(candidate.action_key == emergency.action_key for candidate in candidates):
        return candidates
    return candidates + (emergency,)
