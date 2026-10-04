"""一个动作窗口内的完整决策循环：紧急准备 → 规则分析 → 策略排序 →
复核 → 提交 intent → 单次提交 → outcome，以及仅限明确拒绝的降级重规划。

不变量（接口协议第 4、5 节与 application 模块规范）：
- 预算在窗口到达时创建一次，409 刷新复用原值，绝不延长；
- 只有 SubmitRejectedRetryable 允许排除已拒绝动作后重新规划；
- SubmitAmbiguous / RejectedClosed / RejectedNoRefresh / NotSent /
  候选耗尽 / 截止时间到达都立即结束本窗口的追加提交；
- 同一场次的提交在本循环内串行 await，天然满足“最多一个在途 POST”。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Awaitable, Callable

from hangma_bot.application.audit import AuditTrail, audit_error_text, audit_text

from hangma_bot.application.audit_codec import (
    AUDIT_PRODUCER_APPLICATION,
    CAPTURE_PROFILE_AUDIT_PLUS_V1,
    decision_budget_to_json,
    decision_plan_to_json,
    decision_request_to_json,
)
from hangma_bot.application.contracts import (
    ActionAttempt,
    GameSessionPort,
    ObservedActionWindow,
    ParticipantTerminal,
    ParticipantTerminalReason,
    SubmitAccepted,
    SubmitAmbiguous,
    SubmitFatal,
    SubmitNotSent,
    SubmitOutcome,
    SubmitRejectedClosed,
    SubmitRejectedNoRefresh,
    SubmitRejectedRetryable,
    SubmissionCancelledBeforeSend,
    AuditKind,
)
from hangma_bot.application.deadline import BudgetPolicy, RuntimeClock
from hangma_bot.application.ids import IdGenerator
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import (
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
    ValueAnalysisLimits,
)
from hangma_bot.kernel.actions import WindowKey, action_key
from hangma_bot.kernel.observation import CompetitionContext, PlayerObservation
from hangma_bot.kernel.serialization import KERNEL_VALUE_SCHEMA_VERSION, action_to_json
from hangma_bot.policy.interface import (
    BotPolicy,
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    RejectedAttempt,
    ScorePart,
)


@dataclass(frozen=True)
class RuntimeServices:
    """决策循环依赖的不可变服务束；由组合根一次性注入。"""

    rules: HangmaRules
    policy: BotPolicy
    audit: AuditTrail
    clock: RuntimeClock
    ids: IdGenerator
    budget_policy: BudgetPolicy
    # 硬截止放弃的策略任务注册表：动作路径不等待，运行关闭时限期回收。
    abandoned_tasks: set = field(default_factory=set)
    # 可选分值分析工作量；None 保持普通规则路径，不能延长原始动作预算。
    value_limits: ValueAnalysisLimits | None = None
    # 可选条件路线事实工作量；仅在原增强截止时间前请求，不重新获得预算。
    route_limits: ValueAnalysisLimits | None = None
    # 应用计算服务的桌生命周期；只接收game_id，不扩充BotPolicy或传递隐藏状态。
    compute_game_started: Callable[[str], Awaitable[None]] | None = None
    compute_game_finished: Callable[[str], Awaitable[None]] | None = None
    requires_conditional_roots: bool = False  # 仅依赖条件根的已接线VIP设True；普通策略不被预算跳过

    def __post_init__(self) -> None:
        if type(self.requires_conditional_roots) is not bool:
            raise TypeError("requires_conditional_roots 必须是布尔值")
        if (self.compute_game_started is None) != (self.compute_game_finished is None):
            raise ValueError("计算场次生命周期必须成对注入")
        for name, limits in (("value_limits", self.value_limits), ("route_limits", self.route_limits)):
            if limits is not None and not isinstance(limits, ValueAnalysisLimits):
                raise TypeError(name + " 必须是 ValueAnalysisLimits 或 None")
        if self.value_limits is not None and self.route_limits is not None and self.value_limits != self.route_limits:
            raise ValueError("路线与一次摸牌分析必须使用同一 ValueAnalysisLimits")


@dataclass(frozen=True)
class WindowResult:
    """窗口结束摘要；供监督层记录与测试断言，不进入官方协议。"""

    decision_id: str
    window_key: WindowKey
    sent_attempts: int  # 实际发出的 POST 次数
    outcome_kind: str  # accepted / rejected_closed / rejected_no_refresh / ambiguous / not_sent / deadline / exhausted / window_changed


class FatalIdentityError(Exception):
    """SubmitFatal 等永久故障的载体；监督层转换为参赛者终态。"""

    def __init__(self, terminal: ParticipantTerminal) -> None:
        super().__init__(terminal.detail)
        self.terminal = terminal


def _window_payload(window_key: WindowKey) -> dict:
    """窗口键转 JSON 载荷；phase 用规范枚举值。"""

    return {
        "game_id": window_key.game_id,
        "round_no": window_key.round_no,
        "trigger_seq": window_key.trigger_seq,
        "phase": window_key.phase.value,
        "seat": window_key.seat,
    }


def _observation_snapshot(observation: PlayerObservation, window_key: WindowKey) -> dict:
    """DECISION_PLANNED 的决策观察快照：只含我方依法可见信息。

    为什么存在（2026-09-04 测试赛审计复盘）：旧词表只有候选动作键，
    97 次胡牌被拒无法本地复盘——没有手牌就无法复算规则合法性。
    本快照按 PlayerObservation 口径选取字段，**绝不引入他家手牌、
    未来牌墙或赛后结果**（信息权限与 kernel 观察一致）：

    - ``my_hand`` 保留官方原始顺序（kernel 契约：紧急“最右一张”依赖该顺序）；
    - ``drawn_tile`` 单列、不并入手牌（2026-09-04 kernel 裁决）；
    - ``target_discard`` = 最近公开弃牌（PublicDiscard 座位+牌+事件序号）；
      响应窗口即触发本窗口的弃牌（吃/碰归属复盘必需），draw 窗口为本窗口
      之前的最近公开弃牌、并非触发者（窗口触发者为本人摸牌）；
    - ``rule_state``（爆头/动作链/抓打/财神）与本人副露是胡牌合法性复算输入；
    - ``responding`` 由窗口键与 responding_seats 交叉得出，复盘响应权限。

    体量取舍：不含公开牌河与事件史（完整原始快照由 RAW_PROTOCOL_STATE
    state_response 原文全量保留），单条约数百字节，不会显著增大决策流。
    """

    last_discard = observation.last_discard
    return {
        "schema_version": KERNEL_VALUE_SCHEMA_VERSION,
        "game_id": observation.game_id,
        "seat": observation.seat,
        "round_no": observation.round_no,
        "snapshot_seq": observation.snapshot_seq,
        "phase": observation.phase,
        "turn_seat": observation.turn_seat,
        "responding_seats": list(observation.responding_seats),
        "responding": window_key.seat in observation.responding_seats,
        "my_hand": [tile.code for tile in observation.my_hand],
        "drawn_tile": (
            None if observation.drawn_tile is None else observation.drawn_tile.code
        ),
        "target_discard": (
            None
            if last_discard is None
            else {
                "seat": last_discard.seat,
                "tile": last_discard.tile.code,
                "seq": last_discard.seq,
            }
        ),
        "my_melds": [
            {
                "kind": meld.kind,
                "tiles": [tile.code for tile in meld.tiles],
                "from_seat": meld.from_seat,
            }
            for meld in observation.melds[observation.seat]
        ],
        "hand_counts": list(observation.hand_counts),
        "remaining_tile_count": observation.remaining_tile_count,
        "scores": list(observation.scores),
        "rule_state": {
            "wealth_god": observation.rule_state.wealth_god.code,
            "baotou": observation.rule_state.baotou,
            "chain_count": observation.rule_state.chain_count,
            "catch_play": observation.rule_state.catch_play,
        },
    }


def _safe_emergency(rules: HangmaRules, observation: PlayerObservation, notes: list[str]) -> RuleCandidate | None:
    """紧急路径独立可用：本函数失败不影响后续分析。"""

    try:
        return rules.emergency_action(observation)
    except Exception as exc:  # noqa: BLE001 - 规则模块承诺紧急路径独立，此处再兜底一层
        notes.append("emergency_action 异常: {}".format(audit_error_text(exc)))
        return None


def _safe_analyze(
    rules: HangmaRules,
    observation: PlayerObservation,
    notes: list[str],
    value_limits: ValueAnalysisLimits | None = None,
    route_limits: ValueAnalysisLimits | None = None,
) -> RuleAnalysis:
    """规则分析异常降级为空候选 + DEGRADED，不吞噬窗口。"""

    try:
        # 默认路径不增加关键字参数，保留旧规则实现的调用契约。
        limits = {}
        if value_limits is not None:
            limits["value_limits"] = value_limits
        if route_limits is not None:
            limits["route_limits"] = route_limits
        analysis = rules.analyze(observation, **limits)
    except Exception as exc:  # noqa: BLE001 - 单分支异常不得丢失紧急动作
        notes.append("analyze 异常: {}".format(audit_error_text(exc)))
        return RuleAnalysis(
            legal_candidates=(),
            emergency_candidate=None,
            completeness=RuleCompleteness.DEGRADED,
            ruleset_version=rules.config.ruleset_version,
            issues=(RuleIssue(area="engine", reason="analyze 抛出异常"),),
        )
    if analysis.emergency_candidate is not None:
        known = {candidate.action_key for candidate in analysis.legal_candidates}
        if analysis.emergency_candidate.action_key not in known:
            # 规则引擎违反“紧急候选也在合法候选中”的约定时补齐，
            # 保证策略只能从规则确认的候选中选择。
            merged = analysis.legal_candidates + (analysis.emergency_candidate,)
            issues = analysis.issues + (
                RuleIssue(area="engine", reason="analyze 未包含紧急候选，已按独立紧急路径补齐"),
            )
            analysis = replace(
                analysis,
                legal_candidates=merged,
                issues=issues,
            )
            notes.append("analyze 缺少紧急候选，已补齐")
    return analysis


def _merge_emergency_into_analysis(
    analysis: RuleAnalysis, emergency: RuleCandidate | None
) -> RuleAnalysis:
    """analyze 失败但独立紧急路径成功时，把紧急候选并入合法集合。"""

    if emergency is None or analysis.emergency_candidate is not None:
        return analysis
    if any(candidate.action_key == emergency.action_key for candidate in analysis.legal_candidates):
        return analysis
    return replace(
        analysis,
        legal_candidates=analysis.legal_candidates + (emergency,),
        emergency_candidate=emergency,
    )


async def _guarded_choose(
    services: RuntimeServices,
    request: DecisionRequest,
    budget: DecisionBudget,
    notes: list[str],
) -> DecisionPlan | None:
    """在保底截止时间前竞速策略；超时立即放弃（硬截止）。

    不用 wait_for：策略协程若捕获取消做慢清理，wait_for 会等待其退出，
    无法按截止时间立刻走紧急保底。超时后只请求取消并转入后台回收，
    动作路径绝不等待策略的收尾。
    """

    # 原增强预算已经用尽且未请求条件事实时，不把缺输入交给必须依赖
    # 这些事实的路线策略；明确保留预算降级，由独立规则紧急动作接管。
    # 有完整事实的请求仍能使用剩余保底预算，期限未过但缺输入仍报错。
    if (services.requires_conditional_roots and services.route_limits is not None
            and request.rules.conditional_roots is None
            and services.clock.now() >= budget.enhancement_deadline_monotonic):
        notes.append("路线增强预算已过，条件事实未请求；跳过策略并使用独立紧急动作")
        return None

    choose_task = asyncio.ensure_future(services.policy.choose(request, budget))
    wait_seconds = services.clock.budget_wait_seconds(budget.fallback_deadline_monotonic)
    try:
        done, _pending = await asyncio.wait({choose_task}, timeout=wait_seconds)
    except asyncio.CancelledError:
        # 外部取消（运行关闭）：取消并登记入废弃注册表后传播取消；
        # 不就地无界等待（病态策略可吞取消不返回），收尾由运行出口
        # 限期回收——与硬截止废弃路径完全对称。
        choose_task.cancel()
        registry = services.abandoned_tasks
        registry.add(choose_task)
        choose_task.add_done_callback(
            _make_abandoned_policy_reaper(registry)
        )
        raise
    if choose_task in done:
        try:
            return choose_task.result()
        except asyncio.CancelledError:
            raise  # 运行关闭必须穿透
        except Exception as exc:  # noqa: BLE001 - 策略缺陷不能阻止保底提交
            notes.append("策略异常: {}".format(audit_error_text(exc)))
            return None
    # 硬截止到点：请求取消、登记所有权后立即返回；异常由回调取回并出表，
    # 慢收尾由运行关闭时限期回收，动作路径绝不等待。
    choose_task.cancel()
    registry = services.abandoned_tasks
    registry.add(choose_task)
    choose_task.add_done_callback(
        _make_abandoned_policy_reaper(registry)
    )
    notes.append("策略未在保底截止时间前返回，改用紧急计划")
    return None


def _make_abandoned_policy_reaper(
    registry: set,
):
    """构造回收回调：取回异常避免无人认领，并从注册表移除已完成任务。"""

    def _reap(task: "asyncio.Task[DecisionPlan | None]") -> None:
        registry.discard(task)
        if not task.cancelled() and task.exception() is not None:
            task.exception()

    return _reap


def _sanitize_plan(
    plan: DecisionPlan | None,
    analysis: RuleAnalysis,
    rejected_keys: frozenset[str],
    emergency: RuleCandidate | None,
    decision_id: str,
    window_key: WindowKey,
    based_on_authoritative_seq: int,
    notes: list[str],
) -> list[RankedCandidate]:
    """应用层不盲信策略：校验归属、排除拒绝项、去重并保底紧急候选。"""

    candidates: list[RankedCandidate] = []
    if plan is None:
        notes.append("策略计划不可用，使用紧急保底")
    elif (
        plan.decision_id != decision_id
        or plan.window_key != window_key
        or plan.based_on_authoritative_seq != based_on_authoritative_seq
    ):
        notes.append("策略返回的 decision_id/窗口/序号不匹配，丢弃该计划")
    else:
        legal_by_key = {candidate.action_key: candidate for candidate in analysis.legal_candidates}
        seen: set[str] = set()
        for candidate in plan.candidates:
            key = candidate.action_key
            if key in seen:
                notes.append("丢弃重复候选 {}".format(key))
                continue
            if key in rejected_keys:
                notes.append("策略包含已明确拒绝动作 {}".format(key))
                continue
            legal = legal_by_key.get(key)
            if legal is None:
                notes.append("丢弃不在规则合法集内的候选 {}".format(key))
                continue
            try:
                # action_key 对联合外动作类型抛 TypeError（kernel 承重契约），
                # 值不变量违规抛 ValueError：两类都必须在这里隔离成结构化丢弃，
                # 不得击穿紧急保底路径。
                mismatched = candidate.action != legal.action or action_key(candidate.action) != key
            except (TypeError, ValueError):
                notes.append("丢弃动作键无法计算的畸形候选 {}".format(key))
                continue
            if mismatched:
                # 键合法但动作与键不一致（可伪造字段）：按畸形候选丢弃，
                # 绝不让它在 ActionAttempt 构造处抛异常击穿保底路径。
                notes.append("丢弃动作与键不一致的候选 {}".format(key))
                continue
            seen.add(key)
            candidates.append(candidate)
    if emergency is not None:
        chosen_keys = {candidate.action_key for candidate in candidates}
        if (
            emergency.action_key not in rejected_keys
            and emergency.action_key not in chosen_keys
        ):
            candidates.append(
                RankedCandidate(
                    action=emergency.action,
                    action_key=emergency.action_key,
                    rank=len(candidates) + 1,
                    total_score=0.0,
                    score_parts=(ScorePart(name="emergency_fallback", value=0.0),),
                    reasons=("策略计划缺失或未包含紧急候选，追加保底",),
                    is_emergency=True,
                )
            )
            notes.append("追加紧急保底候选 {}".format(emergency.action_key))
    return candidates


async def run_action_window(
    *,
    session: GameSessionPort,
    window: ObservedActionWindow,
    services: RuntimeServices,
    competition: CompetitionContext,
    stage_attempt_id: str | None,
) -> WindowResult:
    """执行一个动作窗口的完整循环；返回封闭结果摘要。

    抛出 FatalIdentityError 表示当前身份永久故障，由监督层终止运行。

    audit-plus-v1 采集（审计增强方案 §3.2）：每个规划版本各落一条
    DECISION_INPUT（策略调用前）与 DECISION_PLANNED（候选集合复核后）；
    每次最终复核落 CANDIDATE_VALIDATED（复核抛错时 legal=null，不冒充
    规则否定）；无论提交、零提交、取消或错误，finally 尽力落一条
    DECISION_ENDED。所有 codec 编码都经 AuditTrail.emit_safe：构造失败
    只持久化最小 producer_failure，绝不打断动作路径。
    """

    audit = services.audit
    clock = services.clock
    decision_id = services.ids.new_decision_id(window.window_key)
    loop_notes: list[str] = []  # 防御路径回收说明，窗口结束时一次性审计
    # 首次按官方剩余时间创建预算；后续权威刷新只能收紧，不能延长。
    # 适配器给的到达时刻不得晚于本地时钟（防御钳制，防止预算越过官方截止）。
    received_at = window.received_at_monotonic
    if received_at > clock.now():
        loop_notes.append("窗口到达时刻晚于本地时钟，已钳制到当前时刻")
        received_at = clock.now()
    budget = services.budget_policy.build(
        received_at, window.timeout_seconds, window.expires_at_monotonic
    )
    # DECISION_INPUT 的窗口接收单调秒基准：离线以该基准平移全部截止时间。
    budget_origin = received_at
    current = window
    rejected: list[RejectedAttempt] = []
    attempt_no = 0
    plan_revision = 0
    sent = 0
    planned_records = 0  # 用于识别审计链上零记录的窗口结束
    end_reason = "unknown"  # DECISION_ENDED 的终结原因；各出口在 _finish 前改写

    def _finish(kind: str, reason: str) -> WindowResult:
        nonlocal end_reason
        end_reason = reason
        if loop_notes:
            audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {"area": "decision_loop", "reasons": [audit_text(note) for note in loop_notes], "window": _window_payload(window.window_key)},
                stage_attempt_id=stage_attempt_id,
                game_id=window.window_key.game_id,
                round_no=window.window_key.round_no,
                trigger_seq=window.window_key.trigger_seq,
                decision_id=decision_id,
            )
        elif planned_records == 0 and kind == "deadline":
            # 到达截止时窗口在审计链上零记录：服务端会自动代打，
            # 本地必须留痕才能事后对账（无本地动作痕迹的窗口）。
            audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "decision_loop",
                    "reasons": ["窗口在规划前到达截止，零动作尝试"],
                    "window": _window_payload(window.window_key),
                },
                stage_attempt_id=stage_attempt_id,
                game_id=window.window_key.game_id,
                round_no=window.window_key.round_no,
                trigger_seq=window.window_key.trigger_seq,
                decision_id=decision_id,
            )
        return WindowResult(
            decision_id=decision_id,
            window_key=window.window_key,
            sent_attempts=sent,
            outcome_kind=kind,
        )

    def _decision_ended_payload() -> dict:
        """DECISION_ENDED 的最小纯字典：不引用任何 codec，保证 finally 必可写。"""
        return {
            "plan_revision": plan_revision,
            "end_reason": end_reason,
            "attempt_count": attempt_no,
            "sent_attempts": sent,
            "window": _window_payload(window.window_key),
        }

    try:
        while True:
            if clock.now() >= budget.latest_send_at_monotonic:
                return _finish("deadline", "deadline")

            plan_revision += 1
            rules_started_at = clock.now()
            emergency = _safe_emergency(services.rules, current.observation, loop_notes)
            # 紧急动作准备后才启用增强；迟到窗口及 409 刷新不重新获得预算。
            enhancement_available = clock.now() < budget.enhancement_deadline_monotonic
            value_limits = services.value_limits if enhancement_available else None
            route_limits = services.route_limits if enhancement_available else None
            analysis = _safe_analyze(
                services.rules, current.observation, loop_notes, value_limits, route_limits,
            )
            analysis = _merge_emergency_into_analysis(analysis, emergency)
            rule_elapsed_ms = (clock.now() - rules_started_at) * 1000.0
            request = DecisionRequest(
                observation=current.observation,
                competition=competition,
                rules=analysis,
                decision_id=decision_id,
                trigger_seq=window.window_key.trigger_seq,
                window_key=window.window_key,
                rejected_attempts=tuple(rejected),
            )
            # DECISION_INPUT：分析完成、策略调用前落完整当时输入。
            # 刷新后另存新 plan_revision，截止时间（原预算）不变。
            audit.emit_safe(
                AuditKind.DECISION_INPUT,
                payload_factory=lambda: {
                    "plan_revision": plan_revision,
                    "budget_origin_monotonic": budget_origin,
                    "rule_elapsed_ms": round(rule_elapsed_ms, 3),
                    "request": decision_request_to_json(request),
                    "budget": decision_budget_to_json(budget),
                    "budget_policy": {
                        "version": "fixed-post-reserve-v1",
                        "post_reserve_seconds": services.budget_policy.post_reserve_seconds,
                        "enhancement_fraction": services.budget_policy.enhancement_fraction,
                        "fallback_fraction": services.budget_policy.fallback_fraction,
                    },
                    "window_deadline": {
                        "expires_at_monotonic": current.expires_at_monotonic,
                        "deadline_is_estimated": current.deadline_is_estimated,
                    },
                    "window": _window_payload(window.window_key),
                },
                stage="decision_input_encode",
                stage_attempt_id=stage_attempt_id,
                game_id=window.window_key.game_id,
                round_no=window.window_key.round_no,
                trigger_seq=window.window_key.trigger_seq,
                decision_id=decision_id,
            )
            policy_started_at = clock.now()
            plan = await _guarded_choose(services, request, budget, loop_notes)
            policy_elapsed_ms = (clock.now() - policy_started_at) * 1000.0
            filter_start = len(loop_notes)
            rejected_keys = frozenset(item.action_key for item in rejected)
            candidates = _sanitize_plan(
                plan,
                analysis,
                rejected_keys,
                emergency,
                decision_id,
                window.window_key,
                current.authoritative_seq,
                loop_notes,
            )
            filter_reasons = [audit_text(note) for note in loop_notes[filter_start:]]
            issue_reasons = [issue.area + ":" + audit_text(issue.reason) for issue in analysis.issues]
            if plan is None:
                degraded_reasons = ["策略计划不可用"] + issue_reasons
            else:
                degraded_reasons = [audit_text(reason) for reason in plan.degraded_reasons] + issue_reasons
            planned_records += 1

            def _planned_payload() -> dict:
                """DECISION_PLANNED 载荷：returned_plan 编码失败单独留痕，不放弃有效候选。"""
                returned = None
                returned_error = None
                if plan is not None:
                    try:
                        returned = decision_plan_to_json(plan)
                    except (TypeError, ValueError) as exc:
                        returned_error = audit_error_text(exc)
                        loop_notes.append("returned_plan 编码失败: {}".format(returned_error))
                effective = []
                for candidate in candidates:
                    effective.append(
                        {
                            "action_key": candidate.action_key,
                            "is_emergency": candidate.is_emergency,
                            "rank": candidate.rank,
                            "total_score": candidate.total_score,
                            "score_parts": [
                                {"name": part.name, "value": part.value}
                                for part in candidate.score_parts
                            ],
                            "reasons": [audit_text(reason) for reason in candidate.reasons],
                            "action": action_to_json(candidate.action),
                        }
                    )
                return {
                    "plan_revision": plan_revision,
                    "based_on_authoritative_seq": current.authoritative_seq,
                    "trigger_seq": window.window_key.trigger_seq,
                    "window": _window_payload(window.window_key),
                    # 决策观察快照（2026-09-04 增强）：被拒动作可本地复盘的最小可见事实。
                    "observation_snapshot": _observation_snapshot(
                        current.observation, window.window_key
                    ),
                    # 既有字段（v1 兼容读取）：完整候选列表。
                    "candidates": [
                        {
                            "action_key": candidate.action_key,
                            "is_emergency": candidate.is_emergency,
                            "rank": candidate.rank,
                            "action": action_to_json(candidate.action),
                            "reasons": [
                                audit_text(reason) for reason in candidate.reasons
                            ],
                        }
                        for candidate in candidates
                    ],
                    # audit-plus-v1 新增：原计划（可空，不覆盖实际采用候选）、
                    # 实际采用候选（含评分分项）、过滤/保底原因与策略耗时。
                    "returned_plan": returned,
                    "returned_plan_encode_error": returned_error,
                    "effective_candidates": effective,
                    "filter_reasons": filter_reasons,
                    "policy_elapsed_ms": round(policy_elapsed_ms, 3),
                    "degraded_reasons": degraded_reasons,
                    "rule_completeness": analysis.completeness.value,
                }

            audit.emit_safe(
                AuditKind.DECISION_PLANNED,
                payload_factory=_planned_payload,
                stage="decision_planned_encode",
                stage_attempt_id=stage_attempt_id,
                game_id=window.window_key.game_id,
                round_no=window.window_key.round_no,
                trigger_seq=window.window_key.trigger_seq,
                decision_id=decision_id,
            )

            replan_needed = False
            for candidate in candidates:
                if clock.now() >= budget.latest_send_at_monotonic:
                    return _finish("deadline", "deadline")
                if candidate.action_key in rejected_keys:
                    continue
                validation_started_at = clock.now()
                legal: bool | None
                validation_reason: str | None = None
                try:
                    validation = services.rules.validate(current.observation, candidate.action)
                    legal = validation.legal
                    validation_reason = validation.reason
                except Exception as exc:  # noqa: BLE001 - 复核分支异常按不合法处理，换下一候选
                    # legal=null：复核抛出异常不等于规则否定（方案 §3.2），
                    # 离线验证器据此区分"明确不合法"与"复核失败"。
                    legal = None
                    validation_reason = audit_error_text(exc)
                    loop_notes.append(
                        "提交前复核异常 {}: {}".format(candidate.action_key, validation_reason)
                    )
                audit.emit_safe(
                    AuditKind.CANDIDATE_VALIDATED,
                    payload_factory=lambda: {
                        "plan_revision": plan_revision,
                        "action_key": candidate.action_key,
                        "action": action_to_json(candidate.action),
                        "legal": legal,
                        "reason": audit_text(validation_reason) if validation_reason else None,
                        "elapsed_ms": round((clock.now() - validation_started_at) * 1000.0, 3),
                        "window": _window_payload(window.window_key),
                    },
                    stage="candidate_validated_encode",
                    stage_attempt_id=stage_attempt_id,
                    game_id=window.window_key.game_id,
                    round_no=window.window_key.round_no,
                    trigger_seq=window.window_key.trigger_seq,
                    decision_id=decision_id,
                )
                if not legal:
                    if legal is False:
                        loop_notes.append(
                            "提交前复核不合法 {}: {}".format(candidate.action_key, validation_reason)
                        )
                    continue

                attempt_no += 1
                try:
                    attempt = ActionAttempt(
                        decision_id=decision_id,
                        attempt_no=attempt_no,
                        plan_revision=plan_revision,
                        window_key=window.window_key,
                        based_on_authoritative_seq=current.authoritative_seq,
                        action=candidate.action,
                        action_key=candidate.action_key,
                        latest_send_at_monotonic=budget.latest_send_at_monotonic,
                    )
                except (TypeError, ValueError) as exc:
                    # 兜底：ActionAttempt 构造内的 action_key（联合外类型抛
                    # TypeError）与值不变量（ValueError）同样降级为换下一候选。
                    loop_notes.append("动作尝试构造被拒 {}: {}".format(candidate.action_key, exc))
                    attempt_no -= 1
                    continue
                audit.emit(
                    AuditKind.SUBMISSION_INTENT,
                    {
                        "action_key": candidate.action_key,
                        "is_emergency": candidate.is_emergency,
                        "based_on_authoritative_seq": current.authoritative_seq,
                        "plan_revision": plan_revision,
                        "latest_send_at_monotonic": budget.latest_send_at_monotonic,
                        "window": _window_payload(window.window_key),
                        "capture_profile": CAPTURE_PROFILE_AUDIT_PLUS_V1,
                        "audit_producer": AUDIT_PRODUCER_APPLICATION,
                    },
                    stage_attempt_id=stage_attempt_id,
                    game_id=window.window_key.game_id,
                    round_no=window.window_key.round_no,
                    trigger_seq=window.window_key.trigger_seq,
                    decision_id=decision_id,
                    attempt_no=attempt_no,
                )
                if clock.now() >= budget.latest_send_at_monotonic:
                    # S2（前次审查）：发送前同步审计已消耗时间，调用 HTTP 前
                    # 必须重检原 latest_send_at_monotonic——越界时 POST 调用
                    # 为 0，按 SubmitNotSent 语义终结窗口，预算不延长。
                    audit.emit(
                        AuditKind.SUBMISSION_OUTCOME,
                        {
                            "outcome": "SubmitNotSent",
                            "reason": "deadline_passed_after_audit",
                            "window": _window_payload(window.window_key),
                            "capture_profile": CAPTURE_PROFILE_AUDIT_PLUS_V1,
                            "audit_producer": AUDIT_PRODUCER_APPLICATION,
                        },
                        stage_attempt_id=stage_attempt_id,
                        game_id=window.window_key.game_id,
                        round_no=window.window_key.round_no,
                        trigger_seq=window.window_key.trigger_seq,
                        decision_id=decision_id,
                        attempt_no=attempt_no,
                    )
                    return _finish("not_sent", "deadline")
                try:
                    outcome: SubmitOutcome = await session.submit(attempt)
                except asyncio.CancelledError as exc:
                    # 运行关闭必须穿透，绝不重发；适配器明确保证未发送的
                    # 等待取消不应误记在途不确定，其余取消仍保守按未知处理。
                    before_send = isinstance(exc, SubmissionCancelledBeforeSend)
                    try:
                        audit.emit(
                            AuditKind.SUBMISSION_OUTCOME,
                            {
                                "outcome": "SubmitNotSent" if before_send else "SubmitAmbiguous",
                                "reason": "cancelled_before_send" if before_send else "cancelled_in_flight",
                                "window": _window_payload(window.window_key),
                                "capture_profile": CAPTURE_PROFILE_AUDIT_PLUS_V1,
                                "audit_producer": AUDIT_PRODUCER_APPLICATION,
                            },
                            stage_attempt_id=stage_attempt_id,
                            game_id=window.window_key.game_id,
                            round_no=window.window_key.round_no,
                            trigger_seq=window.window_key.trigger_seq,
                            decision_id=decision_id,
                            attempt_no=attempt_no,
                        )
                    except Exception:  # noqa: BLE001 - 审计失败不得干扰取消
                        pass
                    raise
                except Exception as exc:  # noqa: BLE001 - POST 中途异常视为结果不确定
                    loop_notes.append(
                        "submit 抛出异常，按模糊结果封锁本窗口: {}".format(audit_error_text(exc))
                    )
                    audit.emit(
                        AuditKind.SUBMISSION_OUTCOME,
                        {
                            "outcome": "SubmitAmbiguous",
                            "reason": audit_error_text(exc),
                            "window": _window_payload(window.window_key),
                            "capture_profile": CAPTURE_PROFILE_AUDIT_PLUS_V1,
                            "audit_producer": AUDIT_PRODUCER_APPLICATION,
                        },
                        stage_attempt_id=stage_attempt_id,
                        game_id=window.window_key.game_id,
                        round_no=window.window_key.round_no,
                        trigger_seq=window.window_key.trigger_seq,
                        decision_id=decision_id,
                        attempt_no=attempt_no,
                    )
                    sent += 1
                    return _finish("ambiguous", "unknown")

                audit.emit(
                    AuditKind.SUBMISSION_OUTCOME,
                    _outcome_payload(outcome, window.window_key),
                    stage_attempt_id=stage_attempt_id,
                    game_id=window.window_key.game_id,
                    round_no=window.window_key.round_no,
                    trigger_seq=window.window_key.trigger_seq,
                    decision_id=decision_id,
                    attempt_no=attempt_no,
                )

                if isinstance(outcome, SubmitAccepted):
                    sent += 1
                    return _finish("accepted", "submitted")
                if isinstance(outcome, SubmitRejectedRetryable):
                    sent += 1
                    rejected_key = outcome.rejected_action_key
                    if rejected_key != attempt.action_key:
                        # 适配器回传的拒绝键与本次尝试不一致：以我方实际发出的
                        # 尝试键为准排除，防止把未尝试的动作错误排除或重发已拒动作。
                        loop_notes.append(
                            "拒绝键不一致：适配器回报 {}，本次尝试 {}，按尝试键排除".format(
                                rejected_key, attempt.action_key
                            )
                        )
                        rejected_key = attempt.action_key
                    rejected.append(
                        RejectedAttempt(
                            action_key=rejected_key,
                            official_code=outcome.official_code,
                            attempt_no=attempt_no,
                            based_on_authoritative_seq=current.authoritative_seq,
                        )
                    )
                    refreshed = outcome.refreshed_window
                    if refreshed.window_key != window.window_key:
                        # 适配器契约之外的异常现象：明确拒绝却带回不同窗口，
                        # 为安全起见结束本窗口，等待权威状态迁移。
                        loop_notes.append("retryable 拒绝携带了不同窗口键，放弃本窗口")
                        return _finish("window_changed", "unknown")
                    # 官方更早截止必须收紧；更晚截止、晚到快照不得重开预算。
                    budget = services.budget_policy.tighten(
                        budget,
                        min(refreshed.received_at_monotonic, clock.now()),
                        refreshed.timeout_seconds,
                        refreshed.expires_at_monotonic,
                    )
                    current = refreshed
                    rejected_keys = frozenset(item.action_key for item in rejected)
                    replan_needed = True
                    break
                if isinstance(outcome, SubmitRejectedClosed):
                    sent += 1
                    return _finish("rejected_closed", "submitted")
                if isinstance(outcome, SubmitRejectedNoRefresh):
                    # POST 已发出且官方明确未执行，但无权威刷新：按实际发送
                    # 计数并终结本窗口，不得追加动作（2026-09-04 契约收口）。
                    sent += 1
                    return _finish("rejected_no_refresh", "submitted")
                if isinstance(outcome, SubmitAmbiguous):
                    sent += 1
                    return _finish("ambiguous", "unknown")
                if isinstance(outcome, SubmitNotSent):
                    # 未发 POST，发送计数不增加；"已发出 + 官方明确未执行 + 无刷新"
                    # 由 SubmitRejectedNoRefresh 单独表达（2026-09-04 契约收口）。
                    return _finish("not_sent", _not_sent_end_reason(outcome.reason))
                if isinstance(outcome, SubmitFatal):
                    sent += 1
                    reason = (
                        ParticipantTerminalReason.AUTHENTICATION_FAILED
                        if outcome.official_code == "401"
                        else ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
                    )
                    raise FatalIdentityError(
                        ParticipantTerminal(
                            reason=reason,
                            last_snapshot=None,
                            detail="动作提交永久失败: code={} reason={}".format(
                                outcome.official_code, outcome.reason
                            ),
                        )
                    )
                # 未知结果类型（协议演进或适配器缺陷）：按结果不确定封锁本窗口。
                loop_notes.append(
                    "未知提交结果类型 {}，按模糊结果封锁本窗口".format(type(outcome).__name__)
                )
                sent += 1
                return _finish("ambiguous", "unknown")

            if not replan_needed:
                return _finish("exhausted", "exhausted")
    except asyncio.CancelledError:
        end_reason = "cancelled"
        raise
    except FatalIdentityError:
        end_reason = "error"
        raise
    except Exception:  # noqa: BLE001 - 循环缺陷不能阻止终结证据落盘
        end_reason = "error"
        raise
    finally:
        # DECISION_ENDED：即使零提交、取消或错误也尽力记录（方案 §3.2）。
        audit.emit_safe(
            AuditKind.DECISION_ENDED,
            payload_factory=_decision_ended_payload,
            stage="decision_ended_encode",
            stage_attempt_id=stage_attempt_id,
            game_id=window.window_key.game_id,
            round_no=window.window_key.round_no,
            trigger_seq=window.window_key.trigger_seq,
            decision_id=decision_id,
        )


def _not_sent_end_reason(reason: str) -> str:
    """SubmitNotSent 到 DECISION_ENDED end_reason 的映射。

    契约词表（parallel §5.1）：submitted/exhausted/deadline/cancelled/
    error/unknown。not_sent 只可能由截止时间或窗口不再可提交导致，
    按原因文本归并：deadline 类归 deadline，其余归 exhausted
    （窗口已无可提交机会，无 POST 发出）。
    """

    if "deadline" in reason:
        return "deadline"
    return "exhausted"


def _outcome_payload(outcome: SubmitOutcome, window_key: WindowKey) -> dict:
    """把封闭提交结果转成 JSON 载荷；只保留各类型实际拥有的字段。"""

    payload: dict = {
        "outcome": type(outcome).__name__,
        "window": _window_payload(window_key),
        "capture_profile": CAPTURE_PROFILE_AUDIT_PLUS_V1,
        "audit_producer": AUDIT_PRODUCER_APPLICATION,
    }
    official_code = getattr(outcome, "official_code", None)
    if official_code is not None:
        payload["official_code"] = official_code
    for field in (
        "reason",
        "recovery_id",
        "rejected_action_key",
        "latest_authoritative_seq",
        "latest_local_seq",
    ):
        value = getattr(outcome, field, None)
        if value is not None:
            payload[field] = audit_text(str(value))
    authoritative_seq = getattr(outcome, "authoritative_seq", None)
    if authoritative_seq is not None:
        payload["authoritative_seq"] = authoritative_seq
    return payload
