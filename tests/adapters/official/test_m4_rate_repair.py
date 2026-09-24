"""v18 M=4 实测回归：state 的429不能吞掉独立动作窗口。"""
import pytest
from _official_testkit import FakeClock, instant_sleep
from hangma_bot.adapters.official.scheduler import Priority, RequestKind, RequestScheduler, DeadlineExceeded

class NoJitter:
    def uniform(self, lower, upper):
        return 0.0

async def test_state_429_does_not_expire_action_with_775ms_remaining():
    clock = FakeClock(start=0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), jitter_rng=NoJitter())
    scheduler.note_rate_limited(None, request_kind=RequestKind.STATE)
    lease = await scheduler.acquire(Priority.ACTION, deadline_monotonic=.775, request_kind=RequestKind.OTHER)
    lease.release()
    assert clock.monotonic() == 0
    with pytest.raises(DeadlineExceeded):
        await scheduler.acquire(Priority.POLL, deadline_monotonic=.775)
    assert clock.monotonic() == .775


async def test_production_pacing_leaves_margin_and_never_accumulates_a_burst():
    clock = FakeClock(start=0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock),
                                 rate_per_second=14, burst=1)
    granted = []
    for i in range(80):
        if i == 30: clock.advance(2)  # 空闲后也只允许一笔立即发送
        (await scheduler.acquire(Priority.POLL)).release()
        granted.append(clock.monotonic())
    assert all(b-a >= 1/14 - 1e-9 for a,b in zip(granted,granted[1:]))
    assert all(sum(t-1 < x <= t for x in granted) <= 14 for t in granted)


async def test_one_game_state_429_does_not_block_other_game_action_on_same_token():
    """真实会话调用点验证429分类、共享调度、动作成功和审计计时。"""
    import asyncio
    import json
    from _official_testkit import FakeTransport, FakeAuditSink, TIMING, make_audit_context, make_game_session
    from test_sync_repair_regressions import snapshot
    from hangma_bot.adapters.official.errors import RateLimitedError
    from hangma_bot.adapters.official.game import OfficialGameSession
    from hangma_bot.application.contracts import ActionAttempt, SubmitAccepted
    from hangma_bot.kernel.actions import Discard, Tile
    clock, transport, audit = FakeClock(), FakeTransport(), FakeAuditSink()
    blocked = asyncio.Event()
    async def pause(seconds):
        blocked.set()
        await asyncio.Future()
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=pause, jitter_rng=NoJitter())
    def handler(*, method, path, **kwargs):
        if path == '/api/games/poller/state':
            raise RateLimitedError(429, 'RATE_LIMITED', 'state limited', retry_after_seconds=1)
        return 200, json.dumps({'ok': True} if method == 'POST' else snapshot(100, turn=2, drawn='7w'))
    transport.handler = handler
    active = make_game_session(transport=transport, clock=clock, scheduler=scheduler, audit=audit, game_id='active')
    poller = OfficialGameSession(
        game_id='poller', transport=transport, scheduler=scheduler, timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, retry_sleep=pause,
    )
    task = None
    try:
        window = await active.next_item()
        task = asyncio.create_task(poller.next_item())
        await asyncio.wait_for(blocked.wait(), 1)
        attempt = ActionAttempt(decision_id='m4-regression', attempt_no=1, plan_revision=1,
            window_key=window.window_key, based_on_authoritative_seq=window.authoritative_seq,
            action=Discard(Tile('7w')), action_key='discard:7w', latest_send_at_monotonic=clock.monotonic()+.775)
        assert isinstance(await asyncio.wait_for(active.submit(attempt), 1), SubmitAccepted)
        post = next(r.payload for r in audit.records if r.payload.get('source') == 'action_submit_response')
        timing = post['request_timing']
        assert timing['queued_at_monotonic'] <= timing['granted_at_monotonic'] <= timing['transport_started_at_monotonic'] <= timing['completed_at_monotonic']
        state_error = next(r.payload for r in audit.records if r.payload.get('http_status') == 429)
        assert state_error['request_timing']['retry_after_seconds'] == 1
    finally:
        if task:
            task.cancel(); await asyncio.gather(task, return_exceptions=True)
        await active.aclose('test'); await poller.aclose('test')


@pytest.mark.parametrize('retry_after,expected_delay', [(None, .2), (.7, .7)])
async def test_state_429_requeues_only_rejected_game_while_peer_state_continues(
        retry_after, expected_delay):
    """同用户一桌收到 429 时，另一桌照常查询，重试遵守头部或本地退避。"""
    import asyncio
    import json
    from _official_testkit import FakeTransport, FakeAuditSink, TIMING, make_audit_context
    from hangma_bot.adapters.official.errors import RateLimitedError
    from hangma_bot.adapters.official.game import OfficialGameSession

    clock, transport, audit = FakeClock(start=0), FakeTransport(), FakeAuditSink()
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), jitter_rng=NoJitter())
    retry_started = asyncio.Event()
    retry_allowed = asyncio.Event()
    peer_started = asyncio.Event()
    retry_sent = asyncio.Event()
    hold_transport = asyncio.Event()
    attempts = {'rejected': 0}

    async def retry_sleep(seconds):
        retry_started.set()
        await retry_allowed.wait()
        clock.advance(seconds)

    async def handler(*, path, **kwargs):
        if path == '/api/games/rejected/state':
            attempts['rejected'] += 1
            if attempts['rejected'] == 1:
                raise RateLimitedError(429, 'RATE_LIMITED', 'poll rate exceeded', retry_after)
            retry_sent.set()
        else:
            peer_started.set()
        await hold_transport.wait()
        return 200, json.dumps({})

    transport.handler = handler
    def session(game_id, sleep):
        return OfficialGameSession(
            game_id=game_id, transport=transport,
            scheduler=scheduler.for_game(game_id, max_games=10), timing=TIMING,
            monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
            audit=audit, audit_context=make_audit_context, retry_sleep=sleep,
            max_get_retries=1,
        )

    rejected = session('rejected', retry_sleep)
    peer = session('peer', instant_sleep(clock))
    task = asyncio.create_task(rejected.next_item())
    peer_task = None
    try:
        await asyncio.wait_for(retry_started.wait(), 1)
        assert scheduler.cooldown_remaining == 0
        peer_task = asyncio.create_task(peer.next_item())
        await asyncio.wait_for(peer_started.wait(), 1)
        assert clock.monotonic() == 0
        assert scheduler.state_used_count == 2, "被拒 GET 和另一桌 GET 都保留在本地发送账"
        retry_allowed.set()
        await asyncio.wait_for(retry_sent.wait(), 1)
        assert attempts['rejected'] == 2
        assert clock.monotonic() == pytest.approx(expected_delay)
        assert scheduler.state_used_count == 3
        state_calls = [call for call in transport.calls if call.path.endswith('/state')]
        assert [call.path for call in state_calls] == [
            '/api/games/rejected/state', '/api/games/peer/state',
            '/api/games/rejected/state',
        ]
    finally:
        task.cancel()
        if peer_task is not None:
            peer_task.cancel()
        await asyncio.gather(*(item for item in (task, peer_task) if item is not None),
                             return_exceptions=True)
        await rejected.aclose('test')
        await peer.aclose('test')


async def test_state_cooldown_cannot_shorten_global_cooldown_or_affect_another_token():
    clock = FakeClock(start=0)
    first = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), jitter_rng=NoJitter())
    second = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), jitter_rng=NoJitter())
    first.note_rate_limited(3, request_kind=RequestKind.OTHER)
    first.note_rate_limited(1, request_kind=RequestKind.STATE)
    (await second.acquire(Priority.POLL, deadline_monotonic=.1)).release()
    with pytest.raises(DeadlineExceeded):
        await first.acquire(Priority.ACTION, deadline_monotonic=.775, request_kind=RequestKind.OTHER)
    assert first.cooldown_remaining == pytest.approx(3-.775)
