"""提交安全验收：明确拒绝降级、模糊封锁、截止时间、保底与复核。"""

from __future__ import annotations

import asyncio

import pytest

from fakes import (
    DISCARD_3W,
    PASS,
    FakeGameSession,
    FakePolicy,
    FakeRules,
    FakeTournamentSession,
    ManualClock,
    build_runtime,
    make_bootstrap,
    make_observation,
    make_refreshed_window,
    make_snapshot,
    make_window,
)
from hangma_bot.application.contracts import (
    SubmitAccepted,
    SubmitAmbiguous,
    SubmitFatal,
    SubmitNotSent,
    SubmitRejectedClosed,
    SubmitRejectedNoRefresh,
    SubmitRejectedRetryable,
    TournamentStatus,
)
from hangma_bot.kernel.actions import Discard, Tile

pytestmark = pytest.mark.asyncio


async def _run_with_window(
    *,
    submit_handler=None,
    policy=None,
    rules=None,
    clock=None,
    done=None,
    grant_terminal=True,
):
    """单场单窗口的公共脚手架：RUNNING(g1) → 窗口 → FINISHED。

    终态更新在窗口处理完成后才放行，避免调度竞态。
    """

    observation = make_observation(game_id="g1", seq=10)
    window = make_window(observation)
    game = FakeGameSession(items=[window], submit_handler=submit_handler)
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, fake_policy, fake_rules, fake_clock, ids, _sleep = build_runtime(
        session=session, policy=policy, rules=rules, clock=clock
    )
    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(done if done is not None else lambda: game.drained)
    if grant_terminal:
        session.grant_updates(1)
    terminal = await run_task
    return terminal, game, sink, fake_policy, fake_rules, fake_clock, session


async def test_accepted_flow_audits_intent_before_outcome():
    """正常路径：先 intent 后 outcome，尝试携带完整关联键。"""

    terminal, game, sink, *_ = await _run_with_window()
    assert terminal.reason.value == "tournament_finished"
    assert len(game.submitted) == 1
    attempt = game.submitted[0]
    assert attempt.attempt_no == 1 and attempt.plan_revision == 1
    assert attempt.based_on_authoritative_seq == 10
    assert attempt.action_key == "discard:3w"

    kinds = [kind.value for kind in sink.kinds()]
    assert kinds.index("submission_intent") < kinds.index("submission_outcome")
    intents = [
        record for record in sink.records if record.kind.value == "submission_intent"
    ]
    context = intents[0].context
    assert context.game_id == "g1" and context.round_no == 1
    assert context.trigger_seq == 10 and context.attempt_no == 1
    assert context.decision_id == attempt.decision_id
    assert context.stage_attempt_id is not None  # 第一阶段直接开跑也有尝试标识
    assert context.run_id and context.tournament_id and context.participant_id


async def test_retryable_rejection_replans_within_original_budget():
    """409 明确拒绝后排除已拒动作、复用原预算并递增尝试序号。"""

    calls = {"count": 0}
    base_window = make_window(make_observation(game_id="g1", seq=10))

    def handler(attempt):
        calls["count"] += 1
        if calls["count"] == 1:
            refreshed = make_refreshed_window(base_window, seq=11)
            return SubmitRejectedRetryable(
                official_code="CONFLICT",
                rejected_action_key=attempt.action_key,
                refreshed_window=refreshed,
            )
        return SubmitAccepted(official_code="200", authoritative_seq=12)

    terminal, game, sink, policy, rules, clock, _ = await _run_with_window(
        submit_handler=handler
    )
    assert terminal.reason.value == "tournament_finished"
    assert len(game.submitted) == 2
    first, second = game.submitted
    assert first.decision_id == second.decision_id  # 同一窗口同一决策
    assert second.attempt_no == 2 and second.plan_revision == 2
    assert second.based_on_authoritative_seq == 11  # 基于刷新后的权威序号
    assert policy.budgets[0] is policy.budgets[1]  # 预算对象复用，未重建
    assert policy.calls[1].rejected_attempts[0].action_key == "discard:3w"
    assert policy.calls[1].observation.snapshot_seq == 11
    assert second.action_key == "pass"  # 第二候选


async def test_rejected_closed_ends_window_without_resubmit():
    """刷新后窗口已关闭：不再追加动作。"""

    terminal, game, sink, *_ = await _run_with_window(
        submit_handler=lambda attempt: SubmitRejectedClosed(
            official_code="CONFLICT", latest_authoritative_seq=99
        )
    )
    assert len(game.submitted) == 1
    outcomes = [
        record for record in sink.records if record.kind.value == "submission_outcome"
    ]
    assert outcomes[0].payload["outcome"] == "SubmitRejectedClosed"


async def test_ambiguous_never_appends_same_window():
    """模糊结果后即使还有候选也绝不再提交。"""

    counter = {"n": 0}

    def handler(attempt):
        counter["n"] += 1
        if counter["n"] == 1:
            return SubmitAmbiguous(recovery_id="r1", reason="timeout")
        return SubmitAccepted(official_code="200", authoritative_seq=12)

    terminal, game, sink, *_ = await _run_with_window(submit_handler=handler)
    assert len(game.submitted) == 1
    outcomes = [
        record.payload
        for record in sink.records
        if record.kind.value == "submission_outcome"
    ]
    assert outcomes[-1]["outcome"] == "SubmitAmbiguous"


async def test_not_sent_stops_window():
    """适配器未发出 POST 时窗口结束，不换候选硬试。"""

    terminal, game, *_ = await _run_with_window(
        submit_handler=lambda attempt: SubmitNotSent(reason="window closed")
    )
    assert len(game.submitted) == 1


async def test_malformed_candidate_action_does_not_break_fallback():
    """策略返回联合外动作类型的候选：action_key 抛 TypeError 被隔离丢弃，

    紧急保底候选仍被提交，窗口不因畸形候选击穿。
    """

    from hangma_bot.policy.interface import DecisionPlan, RankedCandidate

    class MalformedAction:
        def __eq__(self, other):
            return True  # 穿透键/动作一致性首层比较，迫使 action_key 计算

    def bad_plan(request):
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=1,
            candidates=(
                RankedCandidate(
                    action=MalformedAction(),
                    action_key="discard:3w",  # 伪造为合法键
                    rank=1,
                    total_score=99.0,
                    score_parts=(),
                    reasons=(),
                ),
            ),
            degraded_reasons=(),
        )

    terminal, game, sink, *_ = await _run_with_window(
        policy=FakePolicy(plan_factory=bad_plan)
    )
    assert terminal.reason.value == "tournament_finished"
    assert len(game.submitted) == 1
    assert game.submitted[0].action_key == "pass"  # 紧急保底
    planned = [
        record.payload
        for record in sink.records
        if record.kind.value == "decision_planned"
    ]
    assert planned and planned[-1]["candidates"][0]["is_emergency"] is True


async def test_submit_exception_is_treated_as_ambiguous():
    """submit 中途异常视为结果不确定：同窗封锁而非重发。"""

    terminal, game, sink, *_ = await _run_with_window(
        submit_handler=lambda attempt: RuntimeError("连接中断")
    )
    assert len(game.submitted) == 1
    outcomes = [
        record.payload
        for record in sink.records
        if record.kind.value == "submission_outcome"
    ]
    assert outcomes[-1]["outcome"] == "SubmitAmbiguous"
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    ]
    assert any("模糊结果封锁" in str(item.get("reasons")) for item in recovered)


async def test_submit_fatal_terminates_identity():
    """SubmitFatal(401) 结束当前身份。"""

    submitted = []

    def handler(attempt):
        submitted.append(attempt)
        return SubmitFatal(official_code="401", reason="unauthorized")

    terminal, game, *_, session = await _run_with_window(
        submit_handler=handler,
        done=lambda: len(submitted) >= 1,
        grant_terminal=False,  # FATAL 自行终止运行，不需要终态更新
    )
    assert terminal.reason.value == "authentication_failed"
    assert session.closed is True


async def test_candidates_exhausted_ends_window():
    """全部候选被明确拒绝后候选耗尽，不再提交。"""

    def handler(attempt):
        refreshed = make_refreshed_window(base_window, seq=11)
        return SubmitRejectedRetryable(
            official_code="CONFLICT",
            rejected_action_key=attempt.action_key,
            refreshed_window=refreshed,
        )

    rules = FakeRules(candidates=(DISCARD_3W,), emergency=None)
    base_window = make_window(make_observation(game_id="g1", seq=10))
    terminal, game, sink, policy, *_ = await _run_with_window(
        submit_handler=handler, rules=rules
    )
    assert len(game.submitted) == 1
    assert len(policy.calls) == 2  # 拒绝后重新规划了一次
    planned = [
        record
        for record in sink.records
        if record.kind.value == "decision_planned"
    ]
    assert planned[-1].payload["candidates"] == []


async def test_deadline_prevents_any_post():
    """到达最晚发送时刻后不再发出 POST。"""

    clock = ManualClock(start_monotonic=105.0)
    terminal, game, sink, *_ = await _run_with_window(clock=clock)
    assert len(game.submitted) == 0
    assert not any(kind.value == "submission_intent" for kind in sink.kinds())


async def test_policy_failure_falls_back_to_emergency():
    """策略异常时仍提交紧急保底动作。"""

    rules = FakeRules(candidates=(DISCARD_3W,), emergency=PASS)
    policy = FakePolicy(error=RuntimeError("策略故障注入"))
    terminal, game, sink, *_ = await _run_with_window(policy=policy, rules=rules)
    assert len(game.submitted) == 1
    assert game.submitted[0].action_key == "pass"
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    ]
    assert any("策略异常" in str(item.get("reasons")) for item in recovered)


async def test_policy_hang_stopped_by_fallback_deadline():
    """策略挂起时在保底截止时间被打断并改用紧急候选。"""

    rules = FakeRules(candidates=(DISCARD_3W,), emergency=PASS)
    policy = FakePolicy(hang=True)
    terminal, game, *_ = await _run_with_window(policy=policy, rules=rules)
    assert len(game.submitted) == 1
    assert game.submitted[0].action_key == "pass"


async def test_foreign_candidate_dropped():
    """策略返回规则未确认的候选时被丢弃，只发合法候选。"""

    policy = FakePolicy(extra_first_candidate=Discard(Tile("9w")))
    terminal, game, sink, *_ = await _run_with_window(policy=policy)
    assert game.submitted[0].action_key == "discard:3w"
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    ]
    assert any("不在规则合法集" in str(item.get("reasons")) for item in recovered)


async def test_final_validation_failure_skips_to_next_candidate():
    """提交前复核不合法的候选被跳过，改发下一候选。"""

    rules = FakeRules(
        candidates=(DISCARD_3W, PASS), emergency=PASS, illegal_keys={"discard:3w"}
    )
    terminal, game, sink, *_ = await _run_with_window(rules=rules)
    assert [attempt.action_key for attempt in game.submitted] == ["pass"]
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    ]
    assert any("复核不合法" in str(item.get("reasons")) for item in recovered)


async def test_no_candidates_and_no_emergency_submits_nothing():
    """无动作权或观察不完整时不得伪造动作。"""

    rules = FakeRules(candidates=(), emergency=None)
    terminal, game, sink, *_ = await _run_with_window(rules=rules)
    assert len(game.submitted) == 0
    assert not any(kind.value == "submission_intent" for kind in sink.kinds())

async def test_refreshed_window_with_different_key_ends_window():
    """明确拒绝却带回不同窗口键时放弃本窗口，等待权威迁移。"""

    def handler(attempt):
        other_obs = make_observation(game_id="g1", seq=11, seat=1)
        other = make_window(other_obs, received_at=100.5)
        return SubmitRejectedRetryable(
            official_code="CONFLICT",
            rejected_action_key=attempt.action_key,
            refreshed_window=other,
        )

    terminal, game, sink, *_ = await _run_with_window(submit_handler=handler)
    assert len(game.submitted) == 1
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    ]
    assert any("不同窗口键" in str(item.get("reasons")) for item in recovered)

async def test_malformed_action_key_pair_dropped():
    """策略候选的 action 与 action_key 不一致时丢弃，保底不受影响。"""

    def plan_factory(request):
        from hangma_bot.policy.interface import DecisionPlan, RankedCandidate

        malformed = RankedCandidate(
            action=Discard(Tile("2w")),  # 动作是 2w
            action_key="discard:3w",  # 却冒用合法键 3w
            rank=1,
            total_score=99.0,
            score_parts=(),
            reasons=(),
        )
        good = RankedCandidate(
            action=PASS,
            action_key="pass",
            rank=2,
            total_score=1.0,
            score_parts=(),
            reasons=(),
        )
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=1,
            candidates=(malformed, good),
            degraded_reasons=(),
        )

    policy = FakePolicy(plan_factory=plan_factory)
    terminal, game, sink, *_ = await _run_with_window(policy=policy)
    assert [attempt.action_key for attempt in game.submitted] == ["pass"]
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    ]
    assert any("动作与键不一致" in str(item.get("reasons")) for item in recovered)


async def test_midwindow_deadline_after_rejection_stops():
    """409 拒绝后重新规划前到达截止：不再发出第二个 POST。"""

    clock = ManualClock()
    base_window = make_window(make_observation(game_id="g1", seq=10))
    counter = {"n": 0}

    def handler(attempt):
        counter["n"] += 1
        if counter["n"] == 1:
            clock.advance(5.0)  # 刷新窗口返回前越过最晚发送时刻
            return SubmitRejectedRetryable(
                official_code="CONFLICT",
                rejected_action_key=attempt.action_key,
                refreshed_window=make_refreshed_window(base_window, seq=11),
            )
        return SubmitAccepted(official_code="200", authoritative_seq=12)

    terminal, game, sink, *_ = await _run_with_window(
        submit_handler=handler, clock=clock
    )
    assert len(game.submitted) == 1
    intents = [
        record for record in sink.records if record.kind.value == "submission_intent"
    ]
    assert len(intents) == 1
    summaries = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
        and record.payload.get("area") == "decision_window"
    ]
    assert summaries and summaries[-1]["reason"] == "窗口结束: deadline"
    assert summaries[-1]["sent_attempts"] == 1


async def test_not_sent_window_summary_counts_zero():
    """明确未发送的提交不计入发送数，窗口摘要如实记录。"""

    terminal, game, sink, *_ = await _run_with_window(
        submit_handler=lambda attempt: SubmitNotSent(reason="动作门拒绝")
    )
    assert len(game.submitted) == 1
    summaries = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
        and record.payload.get("area") == "decision_window"
    ]
    assert summaries and summaries[-1]["sent_attempts"] == 0
    assert summaries[-1]["reason"] == "窗口结束: not_sent"


async def test_budget_clamps_future_received_at():
    """适配器报告的未来到达时刻被钳制到本地时钟并留痕。"""

    observation = make_observation(game_id="g1", seq=10)
    window = make_window(observation, received_at=200.0)
    game = FakeGameSession(items=[window])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)  # 时钟起点 100
    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: game.drained)
    session.grant_updates(1)
    terminal = await run_task

    assert len(game.submitted) == 1
    assert game.submitted[0].latest_send_at_monotonic < 200.0  # 按钳制后时刻计算
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    ]
    assert any("钳制" in str(item.get("reasons")) for item in recovered)


async def test_cancel_during_submit_emits_ambiguous_outcome():
    """在途 POST 被取消：补一条合成模糊 outcome 再传播取消。"""

    class HangingSubmitGame(FakeGameSession):
        def __init__(self, items):
            super().__init__(items=items)
            self.gate = asyncio.Future()

        async def submit(self, attempt):
            self.submitted.append(attempt)
            await self.gate  # 模拟在途 POST 挂起

    game = HangingSubmitGame(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(game.submitted) >= 1)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass
    outcomes = [
        record
        for record in sink.records
        if record.kind.value == "submission_outcome"
    ]
    assert outcomes and outcomes[-1].payload["outcome"] == "SubmitAmbiguous"
    assert outcomes[-1].payload["reason"] == "cancelled_in_flight"
    assert sink.closed is True


async def test_deadline_zero_record_window_is_audited():
    """窗口在规划前到达截止也必须在审计链留痕。"""

    clock = ManualClock(start_monotonic=105.0)
    terminal, game, sink, *_ = await _run_with_window(clock=clock)
    assert len(game.submitted) == 0
    assert any(
        record.kind.value == "protocol_recovered"
        and "零动作尝试" in str(record.payload.get("reasons"))
        for record in sink.records
    )



async def test_no_refresh_counts_as_sent_and_ends_window():
    """SubmitRejectedNoRefresh：已发出 POST 按实际发送计数，窗口终结不追加。"""

    terminal, game, sink, *_ = await _run_with_window(
        submit_handler=lambda attempt: SubmitRejectedNoRefresh(
            official_code="RATE_LIMITED",
            rejected_action_key=attempt.action_key,
            latest_local_seq=10,
            reason="official_rate_limited",
        )
    )
    assert len(game.submitted) == 1
    outcomes = [
        record.payload for record in sink.records if record.kind.value == "submission_outcome"
    ]
    assert outcomes[-1]["outcome"] == "SubmitRejectedNoRefresh"
    assert outcomes[-1]["rejected_action_key"] == "discard:3w"
    assert outcomes[-1]["latest_local_seq"] == "10"
    summaries = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
        and record.payload.get("area") == "decision_window"
    ]
    assert summaries and summaries[-1]["sent_attempts"] == 1


async def test_not_sent_does_not_count_as_sent():
    """未发出 POST 的 NotSent 不增加实际发送计数（与 NoRefresh 严格区分）。"""

    terminal, game, sink, *_ = await _run_with_window(
        submit_handler=lambda attempt: SubmitNotSent(reason="deadline passed")
    )
    assert len(game.submitted) == 1
    summaries = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
        and record.payload.get("area") == "decision_window"
    ]
    assert summaries and summaries[-1]["sent_attempts"] == 0



async def test_v1_rank_drives_submission_even_when_total_score_is_lower():
    """应用层遵守 V1 的 rank，不把未知候选的较高数值分重新排到第一。"""
    from hangma_bot.hangma.interface import CandidateFacts, CandidateFactKind, RuleCandidate
    from hangma_bot.policy import ReliableHeuristicPolicyV1
    known = RuleCandidate(DISCARD_3W, 'discard:3w', (), CandidateFacts(CandidateFactKind.HAND_PROGRESS, 4))
    unknown = RuleCandidate(PASS, 'pass', (), None)
    rules = FakeRules(candidates=(unknown,known),emergency=unknown)
    _, game, *_ = await _run_with_window(
        policy=ReliableHeuristicPolicyV1(monotonic=lambda:0),rules=rules,
    )
    assert [a.action_key for a in game.submitted] == ['discard:3w']


async def test_v1_numeric_overflow_uses_existing_emergency_path():
    """真实 V1 数值失败可被现有应用层接住；不更改提交或审计协议。"""
    from hangma_bot.hangma.interface import CandidateFacts, CandidateFactKind, RuleCandidate
    from hangma_bot.policy import ReliableHeuristicPolicyV1, HeuristicWeightsV1
    known = RuleCandidate(DISCARD_3W, 'discard:3w', (), CandidateFacts(CandidateFactKind.HAND_PROGRESS, 4))
    rules = FakeRules(candidates=(known,),emergency=PASS)
    policy = ReliableHeuristicPolicyV1(HeuristicWeightsV1(shanten_step=1e308),monotonic=lambda:0)
    _, game, sink, *_ = await _run_with_window(policy=policy,rules=rules)
    assert [a.action_key for a in game.submitted] == ['pass']
    recovered = [r.payload for r in sink.records if r.kind.value == 'protocol_recovered']
    assert any('策略异常' in str(p.get('reasons')) for p in recovered)
