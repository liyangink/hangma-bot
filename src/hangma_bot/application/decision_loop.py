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
from dataclasses import dataclass, field

from hangma_bot.application.audit import AuditTrail, audit_error_text, audit_text
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
) -> RuleAnalysis:
    """规则分析异常降级为空候选 + DEGRADED，不吞噬窗口。"""

    try:
        analysis = rules.analyze(observation)
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
            analysis = RuleAnalysis(
                legal_candidates=merged,
                emergency_candidate=analysis.emergency_candidate,
                completeness=analysis.completeness,
                ruleset_version=analysis.ruleset_version,
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
    return RuleAnalysis(
        legal_candidates=analysis.legal_candidates + (emergency,),
        emergency_candidate=emergency,
        completeness=analysis.completeness,
        ruleset_version=analysis.ruleset_version,
        issues=analysis.issues,
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
    """

    audit = services.audit
    clock = services.clock
    decision_id = services.ids.new_decision_id(window.window_key)
    loop_notes: list[str] = []  # 防御路径回收说明，窗口结束时一次性审计
    # 预算只创建一次：原始窗口的到达时刻 + 官方窗口时长；刷新不延长。
    # 适配器给的到达时刻不得晚于本地时钟（防御钳制，防止预算越过官方截止）。
    received_at = window.received_at_monotonic
    if received_at > clock.now():
        loop_notes.append("窗口到达时刻晚于本地时钟，已钳制到当前时刻")
        received_at = clock.now()
    budget = services.budget_policy.build(received_at, window.timeout_seconds)
    current = window
    rejected: list[RejectedAttempt] = []
    attempt_no = 0
    plan_revision = 0
    sent = 0
    planned_records = 0  # 用于识别审计链上零记录的窗口结束

    def _finish(kind: str) -> WindowResult:
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

    while True:
        if clock.now() >= budget.latest_send_at_monotonic:
            return _finish("deadline")

        plan_revision += 1
        emergency = _safe_emergency(services.rules, current.observation, loop_notes)
        analysis = _safe_analyze(services.rules, current.observation, loop_notes)
        analysis = _merge_emergency_into_analysis(analysis, emergency)
        request = DecisionRequest(
            observation=current.observation,
            competition=competition,
            rules=analysis,
            decision_id=decision_id,
            trigger_seq=window.window_key.trigger_seq,
            window_key=window.window_key,
            rejected_attempts=tuple(rejected),
        )
        plan = await _guarded_choose(services, request, budget, loop_notes)
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
        issue_reasons = [issue.area + ":" + audit_text(issue.reason) for issue in analysis.issues]
        if plan is None:
            degraded_reasons = ["策略计划不可用"] + issue_reasons
        else:
            degraded_reasons = [audit_text(reason) for reason in plan.degraded_reasons] + issue_reasons
        planned_records += 1
        audit.emit(
            AuditKind.DECISION_PLANNED,
            {
                "plan_revision": plan_revision,
                "based_on_authoritative_seq": current.authoritative_seq,
                "trigger_seq": window.window_key.trigger_seq,
                "window": _window_payload(window.window_key),
                # 决策观察快照（2026-09-04 增强）：被拒动作可本地复盘的最小可见事实。
                "observation_snapshot": _observation_snapshot(
                    current.observation, window.window_key
                ),
                # 完整候选列表：动作用 kernel 稳定序列化（action_to_json），
                # 保证赛后可用 action_from_json 无损还原并复算规则合法性。
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
                "degraded_reasons": degraded_reasons,
                "rule_completeness": analysis.completeness.value,
            },
            stage_attempt_id=stage_attempt_id,
            game_id=window.window_key.game_id,
            round_no=window.window_key.round_no,
            trigger_seq=window.window_key.trigger_seq,
            decision_id=decision_id,
        )

        replan_needed = False
        for candidate in candidates:
            if clock.now() >= budget.latest_send_at_monotonic:
                return _finish("deadline")
            if candidate.action_key in rejected_keys:
                continue
            try:
                validation = services.rules.validate(current.observation, candidate.action)
            except Exception as exc:  # noqa: BLE001 - 复核分支异常按不合法处理，换下一候选
                loop_notes.append(
                    "提交前复核异常 {}: {}".format(candidate.action_key, audit_error_text(exc))
                )
                continue
            if not validation.legal:
                loop_notes.append(
                    "提交前复核不合法 {}: {}".format(candidate.action_key, validation.reason)
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
                },
                stage_attempt_id=stage_attempt_id,
                game_id=window.window_key.game_id,
                round_no=window.window_key.round_no,
                trigger_seq=window.window_key.trigger_seq,
                decision_id=decision_id,
                attempt_no=attempt_no,
            )
            try:
                outcome: SubmitOutcome = await session.submit(attempt)
            except asyncio.CancelledError:
                # 运行关闭必须穿透，绝不重发；但在途 POST 结果未知，
                # 尽力补一条合成 outcome，避免审计链上 intent 无配对。
                try:
                    audit.emit(
                        AuditKind.SUBMISSION_OUTCOME,
                        {
                            "outcome": "SubmitAmbiguous",
                            "reason": "cancelled_in_flight",
                            "window": _window_payload(window.window_key),
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
                    },
                    stage_attempt_id=stage_attempt_id,
                    game_id=window.window_key.game_id,
                    round_no=window.window_key.round_no,
                    trigger_seq=window.window_key.trigger_seq,
                    decision_id=decision_id,
                    attempt_no=attempt_no,
                )
                sent += 1
                return _finish("ambiguous")

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
                return _finish("accepted")
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
                    return _finish("window_changed")
                # 复用原预算重新规划；只更新观察与权威序号。
                current = refreshed
                rejected_keys = frozenset(item.action_key for item in rejected)
                replan_needed = True
                break
            if isinstance(outcome, SubmitRejectedClosed):
                sent += 1
                return _finish("rejected_closed")
            if isinstance(outcome, SubmitRejectedNoRefresh):
                # POST 已发出且官方明确未执行，但无权威刷新：按实际发送
                # 计数并终结本窗口，不得追加动作（2026-09-04 契约收口）。
                sent += 1
                return _finish("rejected_no_refresh")
            if isinstance(outcome, SubmitAmbiguous):
                sent += 1
                return _finish("ambiguous")
            if isinstance(outcome, SubmitNotSent):
                # 未发 POST，发送计数不增加；"已发出 + 官方明确未执行 + 无刷新"
                # 由 SubmitRejectedNoRefresh 单独表达（2026-09-04 契约收口）。
                return _finish("not_sent")
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
            return _finish("ambiguous")

        if not replan_needed:
            return _finish("exhausted")


def _outcome_payload(outcome: SubmitOutcome, window_key: WindowKey) -> dict:
    """把封闭提交结果转成 JSON 载荷；只保留各类型实际拥有的字段。"""

    payload: dict = {"outcome": type(outcome).__name__, "window": _window_payload(window_key)}
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
