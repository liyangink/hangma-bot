"""通过公开适配器内部接口验证期限区间；服务器时钟与本机墙钟独立。"""
import json
from dataclasses import replace

import pytest

from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.application.contracts import SubmitNotSent
from _official_testkit import TIMING, instant_sleep
from test_window_deadline_repair import peng_snapshot, peng_attempt


async def test_shared_snapshot_bounds_stop_late_post_despite_slow_local_wall(transport, clock):
    """两个真实GET建立边界，第三场不能按慢100ms的墙钟继续发送过晚动作。"""
    start, wall = clock.monotonic(), clock.wall_ms()
    root = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock))
    sessions = []
    def make(name):
        session = OfficialGameSession(game_id=name, transport=transport,
            scheduler=root.for_game(name, max_games=10), timing=TIMING,
            monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms)
        sessions.append(session)
        return session
    # 服务端墙钟快100ms；第一份快照在阶段刚开始，第二份在同期限结束前10ms。
    transport.handler = lambda **kw: (200, json.dumps(peng_snapshot(wall + 1100)))
    try:
        await make('first').next_item()
        clock.advance(.99)
        await make('second').next_item()
        clock.advance(.01)
        third = make('third')
        # 新碰窗始于start+1，真实结束start+2，本机原换算会误认为+2.1。
        transport.handler = lambda **kw: (200, json.dumps(peng_snapshot(wall + 2100)))
        window = await third.next_item()
        assert window.expires_at_monotonic <= start + 2.001
        clock.advance(start + 1.95 - clock.monotonic())
        result = await third.submit(replace(peng_attempt(window, clock),
            latest_send_at_monotonic=start + 2.1))
        assert isinstance(result, SubmitNotSent)
        assert all(call.method == 'GET' for call in transport.calls)
    finally:
        for session in sessions:
            await session.aclose('test_completed')


def calibrated_clock():
    """服务器Unix秒=本机单调秒+100，仅用阶段开始/结束附近两个快照约束。"""
    from hangma_bot.adapters.official.deadline_clock import DeadlineClock
    mapping = DeadlineClock()
    mapping.observe(deadline_unix_ms=101000, duration_sec=1, started_at=0, completed_at=.01)
    mapping.observe(deadline_unix_ms=101000, duration_sec=1, started_at=.99, completed_at=1)
    return mapping


def test_interval_contains_true_deadline_and_keeps_submit_and_boundary_distinct():
    mapping = calibrated_clock()
    bound = mapping.deadline(102000, 1)
    assert 1.97 < bound.earliest < 2 < bound.latest < 2.03
    # 墙钟完全不参与计算；长期无数据时不沿用陈旧校准。
    assert mapping.deadline(162000, 62) is None


def test_clock_jump_invalidates_old_interval_until_new_samples_agree():
    mapping = calibrated_clock()
    mapping.observe(deadline_unix_ms=113000, duration_sec=1, started_at=2, completed_at=2.01)
    assert mapping.deadline(113000, 2.01) is None
    assert mapping.metadata(2.01)['resets'] == 1
    mapping.observe(deadline_unix_ms=113000, duration_sec=1, started_at=2.99, completed_at=3)
    interval = mapping.deadline(114000, 3)
    assert interval.earliest < 4 < interval.latest


@pytest.mark.parametrize('overrides', [
    {'deadline_unix_ms': None}, {'deadline_unix_ms': True},
    {'duration_sec': 0}, {'duration_sec': float('nan')},
    {'started_at': 2, 'completed_at': 1}, {'completed_at': float('inf')},
])
def test_invalid_sample_never_establishes_clock(overrides):
    from hangma_bot.adapters.official.deadline_clock import DeadlineClock
    mapping = DeadlineClock()
    args = dict(deadline_unix_ms=101000, duration_sec=1, started_at=0, completed_at=.01)
    args.update(overrides)
    assert mapping.observe(**args) is False
    assert mapping.deadline(101000, .01) is None


def test_different_users_do_not_share_calibration(clock):
    first = RequestScheduler(clock=clock.monotonic)
    second = RequestScheduler(clock=clock.monotonic)
    assert first.for_game('one', max_games=10).deadline_clock is first.for_game('two', max_games=10).deadline_clock
    assert first.deadline_clock is not second.deadline_clock


async def test_calibrated_phase_refresh_uses_late_boundary_not_submit_early_bound(transport, clock):
    import asyncio
    from _official_testkit import load_fixture
    start, wall = clock.monotonic(), clock.wall_ms()
    root = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock))
    # 同身份已有两个快照样本；这里只单独检验真实会话的边界定时接线。
    root.deadline_clock.observe(deadline_unix_ms=wall+1100, duration_sec=1,
        started_at=start, completed_at=start+.02)
    root.deadline_clock.observe(deadline_unix_ms=wall+1100, duration_sec=1,
        started_at=start+.98, completed_at=start+.99)
    clock.advance(1)
    refresh_at=[]
    async def timer(seconds):
        await asyncio.sleep(0)
        clock.advance(seconds)
    async def handler(*,long_poll,**kwargs):
        if len(transport.calls)==1:
            return 200,json.dumps(peng_snapshot(wall+2100))
        if long_poll:
            await asyncio.Future()
        refresh_at.append(clock.monotonic())
        doc=peng_snapshot(wall+3100)
        doc['snapshot']['phase']='response_chi'
        doc['snapshot']['window_deadline_ms']=wall+3100
        return 200,json.dumps(doc)
    transport.handler=handler
    session=OfficialGameSession(game_id='boundary-clock',transport=transport,
        scheduler=root.for_game('boundary-clock',max_games=10),timing=TIMING,
        monotonic_clock=clock.monotonic,wall_clock_unix_ms=clock.wall_ms,retry_sleep=timer)
    try:
        peng=await session.next_item()
        chi=await asyncio.wait_for(session.next_item(),.5)
        assert chi.window_key.phase.value=='response_chi'
        assert peng.expires_at_monotonic < start+2
        assert start+2.05 < refresh_at[0] < start+2.09
    finally:
        await session.aclose('test_completed')


def test_asymmetric_network_samples_never_exclude_true_monotonic_deadline():
    """独立生成服务器观测时刻，覆盖长上行/长回程与毫秒取整，禁止RTT除2假设。"""
    import random
    from hangma_bot.adapters.official.deadline_clock import DeadlineClock
    rng = random.Random(20260909)
    mapping = DeadlineClock()
    offset = 1_788_000_000.083
    now = 1_500_000.0
    ready = 0
    for index in range(500):
        duration = 1 if index % 2 else 3
        now += rng.uniform(.05, .2)
        uplink = rng.uniform(0, .04)
        observation = now + uplink
        # 在窗口开始或结束附近采样，不从客户端误差反推服务器事实。
        left = rng.uniform(0, .02) if index % 3 else duration-rng.uniform(0,.02)
        deadline = observation+left
        completed = observation+rng.uniform(0,.3)
        assert mapping.observe(deadline_unix_ms=int((deadline+offset)*1000),
            duration_sec=duration, started_at=now, completed_at=completed)
        now = completed
        interval = mapping.deadline(int((deadline+offset)*1000), now)
        if interval:
            true_mapped = int((deadline+offset)*1000)/1000-offset
            assert interval.earliest <= true_mapped <= interval.latest
            ready += 1
    assert ready > 450
    assert mapping.metadata(now)['resets'] == 0
    assert mapping.metadata(now)['samples'] <= 256


def test_out_of_order_completion_cannot_pollute_newer_clock_samples():
    mapping = calibrated_clock()
    before = mapping.deadline(102000,1)
    assert not mapping.observe(deadline_unix_ms=999999999, duration_sec=1,
        started_at=.1, completed_at=.2)
    assert mapping.deadline(102000,1)==before
