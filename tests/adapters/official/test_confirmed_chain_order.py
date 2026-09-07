"""成功回执晚于新快照时，同水位的公开审计读取仍须获得已核实链事实。"""

import asyncio
import json
from pathlib import Path

from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitAccepted
from hangma_bot.kernel.actions import action_key
from hangma_bot.kernel.serialization import action_from_json

from _official_testkit import TIMING, make_audit_context


async def test_late_success_reply_reconciles_already_cached_snapshot(transport, clock, audit):
    """真实报文只改变到达顺序；不访问会话私有状态、不增加状态查询。

    next_item 与 submit 并发，使杠后快照先到、成功回执后到。窗口值对象
    保持不可变；随后 aclose 的公开审计输出在相同水位重新读取当前观察，
    应补全经成功动作核实的事实，且不能等待另一份快照才生效。
    """
    fixture = Path(__file__).parents[2] / "fixtures/official/v20/snapshot-chain.json"
    case = json.loads(fixture.read_text())["cases"][0]
    queue = [("GET", row) for row in case["before_requests"]]
    queue += [("POST", case["action_response"]), ("GET", case["after_request"])]
    first_wall_ms = case["before_requests"][0]["wall_time_unix_ms"]
    clock.advance((first_wall_ms - clock.wall_ms()) / 1000)
    post_started = asyncio.Event()
    release_success = asyncio.Event()

    async def sleep(seconds):
        clock.advance(seconds)
        await asyncio.sleep(0)

    async def handler(*, method, params=None, **kwargs):
        assert queue, "出现真实轨迹之外的额外请求"
        expected_method, row = queue.pop(0)
        assert method == expected_method
        if method == "GET":
            assert params == row["params"]
        clock.advance(max(0, (row["wall_time_unix_ms"] - clock.wall_ms()) / 1000))
        if method == "POST":
            post_started.set()
            await release_success.wait()
        return 200, json.dumps(row["response"])

    transport.handler = handler
    session = OfficialGameSession(
        game_id=case["game_id"], transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=sleep, rate_per_second=2,
                                   burst=1, max_concurrent=2, max_state_concurrent=1),
        timing=TIMING, monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, retry_sleep=sleep,
    )
    posting = None
    try:
        before = await asyncio.wait_for(session.next_item(), 2)
        assert isinstance(before, ObservedActionWindow)
        action = action_from_json(case["accepted_action"])
        attempt = ActionAttempt(
            decision_id=case["action_response"]["decision_id"], attempt_no=1, plan_revision=1,
            window_key=before.window_key, based_on_authoritative_seq=before.authoritative_seq,
            action=action, action_key=action_key(action),
            latest_send_at_monotonic=clock.monotonic() + .5,
        )
        posting = asyncio.create_task(session.submit(attempt))
        await asyncio.wait_for(post_started.wait(), 2)
        earlier_window = await asyncio.wait_for(session.next_item(), 2)
        assert isinstance(earlier_window, ObservedActionWindow)
        assert not posting.done(), "快照必须先于成功回执到达，否则没有覆盖缓存失效边界"
        assert earlier_window.observation.consumed_seq == case["expected_seq"]
        assert earlier_window.observation.chain_piao is None
        assert earlier_window.observation.gang_draw is None

        release_success.set()
        assert isinstance(await asyncio.wait_for(posting, 2), SubmitAccepted)
        assert not queue
        await session.aclose("same_watermark_read")
        closure = next(record.payload for record in audit.records
                       if record.payload.get("history_closure") == "session_closed:same_watermark_read")
        current = closure["observation"]
        assert current["consumed_seq"] == earlier_window.observation.consumed_seq
        assert current["chain_piao"] == 0
        assert current["gang_draw"] is True
        assert sum(call.method == "POST" for call in transport.calls) == 1
        assert sum(call.method == "GET" for call in transport.calls) == len(case["before_requests"]) + 1
        # 成功回执没有改写已经投递的旧值对象，也没有补造杠/补牌事件。
        assert earlier_window.observation.chain_piao is None
        assert current["public_history"] == closure["public_history"]
    finally:
        release_success.set()
        if posting is not None and not posting.done():
            posting.cancel()
            await asyncio.gather(posting, return_exceptions=True)
        await session.aclose("test_complete")
