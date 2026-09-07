"""POST 在途取消（Expert 必修 2）：封锁语义、审计 shape 与验证器对账例外。

背景：task.cancel 落在 POST 发出后、响应到达前（在途取消）时，适配器以
gate.block + SUBMISSION_OUTCOME(SubmitAmbiguous, reason=SUBMISSION_CANCELLED_
IN_FLIGHT) 落审计且不发射响应原文（响应是否到达不可知）。game.py 生产与
validator.py 的 raw_action_missing 例外必须引用同一共享常量（契约钉死），
任一侧漂移本测试即红。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.application.contracts import (
    SUBMISSION_CANCELLED_IN_FLIGHT,
    ActionAttempt,
    AuditKind,
    ObservedActionWindow,
    SubmitNotSent,
)
from hangma_bot.kernel.actions import Discard, Tile

from _official_testkit import FakeClock, FakeTransport, load_fixture, make_game_session


def _attempt(window_key, attempt_no: int = 1, decision_id: str = "d-cancel-1") -> ActionAttempt:
    return ActionAttempt(
        decision_id=decision_id,
        attempt_no=attempt_no,
        plan_revision=1,
        window_key=window_key,
        based_on_authoritative_seq=window_key.trigger_seq,
        action=Discard(Tile("5w")),
        action_key="discard:5w",
        latest_send_at_monotonic=1005.0,
    )


async def _expect_cancelled(task: asyncio.Task) -> None:
    """取消任务并检索 CancelledError（取消语义必须向外传播，不得吞掉）。"""

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _hang_post_handler(snapshot: str, started: asyncio.Event):
    async def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            started.set()  # POST 已发出、响应未到达：挂起在途
            await asyncio.Event().wait()
        return 200, snapshot

    return handler


async def test_inflight_cancel_blocks_window_and_audits_shared_reason(transport, clock, audit):
    """取消后：同窗零次追加提交（gate 封锁）、SUBMISSION_OUTCOME 以共享常量
    落审计、无 action 响应原文记录。"""

    snapshot = json.dumps(load_fixture("state_response_snapshot_draw.json"))
    started = asyncio.Event()
    transport.handler = _hang_post_handler(snapshot, started)
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    window = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(window, ObservedActionWindow)

    task = asyncio.ensure_future(session.submit(_attempt(window.window_key)))
    await asyncio.wait_for(started.wait(), timeout=2)  # POST 已发出
    await _expect_cancelled(task)

    # 1) 同窗零次追加提交：gate.block 后 try_enter 拒绝（模糊封锁语义）
    again = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, attempt_no=2)), timeout=2
    )
    assert isinstance(again, SubmitNotSent)
    assert again.reason == "ambiguous_window_blocked"

    # 2) SUBMISSION_OUTCOME 以共享常量落审计；无 POST 原文记录
    outcomes = [
        r for r in audit.records
        if r.kind is AuditKind.SUBMISSION_OUTCOME
        and r.payload.get("outcome_type") == "SubmitAmbiguous"
    ]
    assert outcomes, "在途取消必须有 outcome 审计记录"
    assert outcomes[0].payload.get("reason") == SUBMISSION_CANCELLED_IN_FLIGHT
    raws = [
        r for r in audit.records
        if r.kind is AuditKind.RAW_PROTOCOL_STATE
        and str(r.payload.get("endpoint", "")).startswith("POST")
    ]
    assert len(raws) == 1
    assert raws[0].payload["raw"] == ""
    assert raws[0].payload["request_timing"]["outcome"] == "cancelled"


async def test_inflight_cancel_passes_validator_raw_accounting(tmp_path):
    """真实链：在途取消后 validate_run 不报 raw_action_missing（例外与常量对齐）。"""

    from hangma_bot.adapters.recording import JsonlAuditSink, validate_run

    sink = JsonlAuditSink(tmp_path, "run-cancel")
    clock = FakeClock()
    transport = FakeTransport()
    snapshot = json.dumps(load_fixture("state_response_snapshot_draw.json"))
    started = asyncio.Event()
    transport.handler = _hang_post_handler(snapshot, started)
    session = make_game_session(
        transport=transport, clock=clock, audit=sink,  # type: ignore[arg-type]
    )
    window = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(window, ObservedActionWindow)
    task = asyncio.ensure_future(session.submit(_attempt(window.window_key)))
    await asyncio.wait_for(started.wait(), timeout=2)
    await _expect_cancelled(task)
    await asyncio.wait_for(sink.aclose(timeout_seconds=5.0), timeout=6)

    report = validate_run(str(tmp_path / "runs" / "run-cancel"))
    codes = {f["code"] for f in report["findings"]}
    assert "raw_action_missing" not in codes, "在途取消不得误报缺响应原文"
    assert report["raw_events"]["action_responses"] == 1