"""固定网络预算经真实会话出口核验；上行与返回延迟分开，不发真实请求。"""
from dataclasses import replace
import json

import pytest

from hangma_bot.application.contracts import SubmitAccepted, SubmitNotSent, SubmitRejectedNoRefresh
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.adapters.official.errors import ConflictError
from test_window_deadline_repair import make_session, peng_attempt, peng_snapshot


@pytest.mark.parametrize('remaining', [.05, .1])
async def test_adapter_rejects_overwide_caller_budget_without_post(transport, clock, remaining):
    transport.handler = lambda **kw: (200, json.dumps(peng_snapshot(clock.wall_ms() + round(remaining * 1000))))
    session = make_session(transport, clock)
    try:
        window = await session.next_item()
        attempt = replace(peng_attempt(window, clock), latest_send_at_monotonic=clock.monotonic() + 10)
        result = await session.submit(attempt)
        assert isinstance(result, SubmitNotSent)
        assert [c.method for c in transport.calls] == ['GET']
    finally:
        await session.aclose('test_completed')


@pytest.mark.parametrize('uplink,downlink,clock_lag,expected', [
    (.02, .02, 0, SubmitAccepted),
    (.08, .02, 0, SubmitAccepted),
    (.01, .52, 0, SubmitAccepted),  # 响应晚不能冒充请求执行失败，更不能重发
    (.12, .01, 0, SubmitRejectedNoRefresh),  # 超出固定预算的长尾不保证成功
    (.05, .01, .10, SubmitRejectedNoRefresh),  # 网络预算不冒充时钟校正
])
async def test_network_arrival_and_response_are_distinct(transport, clock, uplink, downlink, clock_lag, expected):
    start, wall = clock.monotonic(), clock.wall_ms()
    arrival = []

    def handler(*, method, **kwargs):
        if method == 'GET':
            assert len(transport.calls) == 1, '迟到拒绝不应追加超预算刷新'
            # 服务端期限固定在start+1；本机钟慢会把换算结果错误推迟。
            return 200, json.dumps(peng_snapshot(wall + 1000 + round(clock_lag * 1000)))
        clock.advance(uplink)
        arrival.append(clock.monotonic())
        expired = clock.monotonic() >= start + 1
        clock.advance(downlink)
        if expired:
            raise ConflictError(409, 'INVALID_ACTION', 'response window closed')
        return 200, json.dumps({'ok': True, 'seq': 121})

    transport.handler = handler
    session = make_session(transport, clock)
    try:
        window = await session.next_item()
        budget = BudgetPolicy().build(window.received_at_monotonic, window.timeout_seconds, window.expires_at_monotonic)
        # 明确模拟上层仍使用偏差后的期限，避免timeout上界刚好抵消钟差。
        if clock_lag:
            clock.advance(clock_lag)
            budget = BudgetPolicy().build(clock.monotonic(), 1, window.expires_at_monotonic)
        clock.advance(budget.latest_send_at_monotonic - clock.monotonic() - .001)
        attempt = replace(peng_attempt(window, clock), latest_send_at_monotonic=budget.latest_send_at_monotonic)
        result = await session.submit(attempt)
        assert isinstance(result, expected), result
        assert (arrival[0] < start + 1) == (expected is SubmitAccepted)
        assert sum(c.method == 'POST' for c in transport.calls) == 1
        again = await session.submit(attempt)
        assert isinstance(again, SubmitNotSent)
        assert sum(c.method == 'POST' for c in transport.calls) == 1
    finally:
        await session.aclose('test_completed')


async def test_three_second_hu_transport_tail_closes_attempt_without_blind_retry(transport, clock):
    """实测r2/b8模式：早发胡牌的HTTP返回超过3秒，拒绝后不得追加或续预算。"""
    from hangma_bot.kernel.actions import Hu
    from _official_testkit import load_fixture
    from hangma_bot.application.contracts import GameFinished
    start = clock.monotonic()
    draw = load_fixture('state_response_snapshot_draw.json')
    draw['snapshot']['window_deadline_ms'] = clock.wall_ms() + 3000
    count = 0
    def handler(*, method, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return 200, json.dumps(draw)
        if method == 'POST':
            clock.advance(3.545)
            raise ConflictError(409, 'INVALID_ACTION', 'hu only after draw')
        finished = load_fixture('state_response_finished.json')
        return 200, json.dumps(finished)
    transport.handler = handler
    session = make_session(transport, clock)
    try:
        window = await session.next_item()
        attempt = replace(peng_attempt(window, clock), action=Hu(), action_key='hu',
            latest_send_at_monotonic=start+2.9)
        result = await session.submit(attempt)
        assert isinstance(result, SubmitRejectedNoRefresh)
        assert [c.method for c in transport.calls] == ['GET','POST']
        assert isinstance(await session.submit(attempt), SubmitNotSent)
        assert len(transport.calls) == 2
        assert isinstance(await session.next_item(), GameFinished)
        assert [c.method for c in transport.calls] == ['GET','POST','GET']
    finally:
        await session.aclose('test_completed')
