"""决策循环 audit-plus-v1 采集与发送截止重检测试（方案 §3.2/§3.4）。

验收（方案 §8 A1 与审查 S2）：
- 每个规划版本各一条 DECISION_INPUT（刷新另存新 revision，预算不变）；
- CANDIDATE_VALIDATED 覆盖 legal=true/false 与复核异常（legal=null）；
- 零提交/取消/错误也落 DECISION_ENDED；
- 发送前同步审计越过截止 → POST 调用为 0、结果 SubmitNotSent、
  原预算不变；
- codec 构造失败只落 producer_failure，不打断保底提交。
"""

from __future__ import annotations

import asyncio
import importlib

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
    InMemoryAuditSink,
    SequencedIds,
)
from hangma_bot.application.contracts import (
    AuditReceipt,
    SubmitAccepted,
    SubmitRejectedRetryable,
    TournamentStatus,
)

pytestmark = pytest.mark.asyncio


def _records_of(sink, kind_value: str):
    return [record for record in sink.records if record.kind.value == kind_value]


class _AdvancingIntentSink(InMemoryAuditSink):
    """SUBmission_INTENT 入队时推进假时钟：复现"同步审计越过发送截止"。"""

    def __init__(self, clock: ManualClock, advance_seconds: float) -> None:
        super().__init__()
        self._clock = clock
        self._advance = advance_seconds

    def emit(self, record):
        if record.kind.value == "submission_intent":
            self._clock.advance(self._advance)
        return super().emit(record)


async def _run_with_window(sink, *, submit_handler=None, policy=None, rules=None, clock=None):
    observation = make_observation(game_id="g1", seq=10)
    window = make_window(observation)
    game = FakeGameSession(items=[window], submit_handler=submit_handler)
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink_out, fake_policy, fake_rules, fake_clock, ids, _sleep = build_runtime(
        session=session, sink=sink, policy=policy, rules=rules, clock=clock
    )
    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: game.drained)
    session.grant_updates(1)
    terminal = await run_task
    return terminal, game, sink_out, fake_policy, fake_rules, fake_clock


async def test_decision_kinds_emitted_in_order_with_profile():
    """完整链路：DECISION_INPUT → CANDIDATE_VALIDATED → INTENT → OUTCOME →
    DECISION_ENDED，增强字段与关联键齐全。"""

    sink = InMemoryAuditSink()
    terminal, game, sink, policy, rules, clock = await _run_with_window(sink)
    assert terminal.reason.value == "tournament_finished"
    kinds = [kind.value for kind in sink.kinds()]
    assert kinds.index("decision_input") < kinds.index("decision_planned")
    assert kinds.index("decision_planned") < kinds.index("candidate_validated")
    assert kinds.index("candidate_validated") < kinds.index("submission_intent")
    assert kinds.index("submission_intent") < kinds.index("submission_outcome")
    assert kinds.index("submission_outcome") < kinds.index("decision_ended")

    inputs = _records_of(sink, "decision_input")
    assert len(inputs) == 1
    payload = inputs[0].payload
    assert payload["capture_profile"] == "audit-plus-v1"
    assert payload["audit_producer"] == "application"
    assert payload["plan_revision"] == 1
    assert payload["budget_origin_monotonic"] == 100.0
    request = payload["request"]
    assert request["codec_version"] == 1
    assert request["observation"]["my_hand"] == ["1w", "2w", "3w"]
    assert payload["budget"]["codec_version"] == 1
    # 窗口接收时刻 100.0 + 3s * 0.85（默认 BudgetPolicy）。
    assert payload["budget"]["latest_send_at_monotonic"] == pytest.approx(102.55)

    validations = _records_of(sink, "candidate_validated")
    assert len(validations) == 1
    assert validations[0].payload["legal"] is True
    assert validations[0].payload["action_key"] == "discard:3w"
    assert validations[0].payload["capture_profile"] == "audit-plus-v1"

    planned = _records_of(sink, "decision_planned")
    assert planned[0].payload["returned_plan"]["candidates"][0]["action_key"] == "discard:3w"
    assert planned[0].payload["effective_candidates"][0]["total_score"] is not None
    assert planned[0].payload["policy_elapsed_ms"] is not None

    ended = _records_of(sink, "decision_ended")
    assert len(ended) == 1
    assert ended[0].payload["end_reason"] == "submitted"
    assert ended[0].payload["attempt_count"] == 1
    assert ended[0].payload["sent_attempts"] == 1
    assert ended[0].context.decision_id == inputs[0].context.decision_id

    intents = _records_of(sink, "submission_intent")
    outcomes = _records_of(sink, "submission_outcome")
    assert intents[0].payload["capture_profile"] == "audit-plus-v1"
    assert outcomes[0].payload["capture_profile"] == "audit-plus-v1"
    assert outcomes[0].payload["audit_producer"] == "application"


async def test_replan_emits_new_revision_input_keeps_budget():
    """409 重规划：两条 DECISION_INPUT（revision 1/2），预算对象不变。"""

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

    sink = InMemoryAuditSink()
    terminal, game, sink, policy, rules, clock = await _run_with_window(
        sink, submit_handler=handler
    )
    inputs = _records_of(sink, "decision_input")
    assert [record.payload["plan_revision"] for record in inputs] == [1, 2]
    # 刷新复用原预算：两次输入的预算完全一致（截止时间不延长）。
    assert inputs[0].payload["budget"] == inputs[1].payload["budget"]
    assert policy.budgets[0] is policy.budgets[1]
    ended = _records_of(sink, "decision_ended")
    assert ended[0].payload["plan_revision"] == 2
    assert ended[0].payload["attempt_count"] == 2
    assert ended[0].payload["end_reason"] == "submitted"
    # 拒绝历史进入第二个 revision 的完整输入。
    rejected = inputs[1].payload["request"]["rejected_attempts"]
    assert [item["action_key"] for item in rejected] == ["discard:3w"]


async def test_illegal_candidate_validated_false_and_skipped():
    """复核不合法：CANDIDATE_VALIDATED legal=false，换下一候选提交。"""

    rules = FakeRules(
        candidates=(DISCARD_3W, PASS),
        emergency=PASS,
        illegal_keys={"discard:3w"},
    )
    sink = InMemoryAuditSink()
    terminal, game, sink, policy, rules, clock = await _run_with_window(
        sink, rules=rules
    )
    validations = _records_of(sink, "candidate_validated")
    assert [record.payload["legal"] for record in validations] == [False, True]
    assert validations[0].payload["action_key"] == "discard:3w"
    assert validations[0].payload["reason"] == "复核不合法（注入）"
    assert [attempt.action_key for attempt in game.submitted] == ["pass"]


async def test_validate_exception_records_legal_null():
    """复核抛错：legal=null 不冒充规则否定，窗口按不合法换候选。"""

    class RaisingRules(FakeRules):
        def validate(self, observation, action):
            raise RuntimeError("复核故障注入")

    rules = RaisingRules(candidates=(DISCARD_3W, PASS), emergency=PASS)
    sink = InMemoryAuditSink()
    terminal, game, sink, policy, rules, clock = await _run_with_window(
        sink, rules=rules
    )
    validations = _records_of(sink, "candidate_validated")
    assert all(record.payload["legal"] is None for record in validations)
    assert all("复核故障注入" in (record.payload["reason"] or "") for record in validations)
    assert len(game.submitted) == 0
    ended = _records_of(sink, "decision_ended")
    assert ended[0].payload["end_reason"] == "exhausted"
    assert ended[0].payload["attempt_count"] == 0


async def test_zero_submission_window_still_ends():
    """无候选窗口：零提交也落 DECISION_ENDED（end_reason=exhausted）。"""

    rules = FakeRules(candidates=(), emergency=None)
    sink = InMemoryAuditSink()
    terminal, game, sink, policy, rules, clock = await _run_with_window(
        sink, rules=rules
    )
    ended = _records_of(sink, "decision_ended")
    assert len(ended) == 1
    assert ended[0].payload["end_reason"] == "exhausted"
    assert ended[0].payload["attempt_count"] == 0
    assert ended[0].payload["sent_attempts"] == 0
    assert len(game.submitted) == 0


async def test_sync_audit_crossing_deadline_sends_zero_posts():
    """S2 验收：同步审计把时间推进过发送截止 → POST 调用为 0、
    结果 SubmitNotSent、原预算不变。"""

    clock = ManualClock()
    sink = _AdvancingIntentSink(clock, advance_seconds=5.0)
    terminal, game, sink, policy, rules, clock = await _run_with_window(
        sink, clock=clock
    )
    assert len(game.submitted) == 0  # 零次 session.submit → 零 POST
    outcomes = _records_of(sink, "submission_outcome")
    assert len(outcomes) == 1
    assert outcomes[0].payload["outcome"] == "SubmitNotSent"
    assert outcomes[0].payload["reason"] == "deadline_passed_after_audit"
    ended = _records_of(sink, "decision_ended")
    assert ended[0].payload["end_reason"] == "deadline"
    # 原预算不变：策略拿到的预算与窗口接收时刻一致。
    assert policy.budgets[0].latest_send_at_monotonic == pytest.approx(102.55)
    assert policy.budgets[0].enhancement_deadline_monotonic == pytest.approx(101.5)


async def test_codec_failure_never_blocks_fallback_submission(monkeypatch):
    """codec-fails-before-emit 行为向量：构造失败只落 producer_failure，
    提交保底路径不受影响，DECISION_ENDED 仍记录。"""

    import hangma_bot.application.decision_loop as loop_module

    def broken(request):
        raise ValueError("codec 故障注入")

    monkeypatch.setattr(loop_module, "decision_request_to_json", broken)
    sink = InMemoryAuditSink()
    terminal, game, sink, policy, rules, clock = await _run_with_window(sink)
    assert terminal.reason.value == "tournament_finished"
    assert len(game.submitted) == 1  # 保底提交不受审计构造失败影响
    assert not _records_of(sink, "decision_input")
    failures = [
        record
        for record in _records_of(sink, "lifecycle_changed")
        if record.payload.get("event") == "producer_failure"
    ]
    assert len(failures) == 1
    assert failures[0].payload["original_kind"] == "decision_input"
    assert failures[0].payload["stage"] == "decision_input_encode"
    ended = _records_of(sink, "decision_ended")
    assert ended[0].payload["end_reason"] == "submitted"
    # 计划记录仍保存有效候选（returned_plan 编码成功）。
    planned = _records_of(sink, "decision_planned")
    assert planned[0].payload["effective_candidates"][0]["action_key"] == "discard:3w"
