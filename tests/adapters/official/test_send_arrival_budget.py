"""真实调度/审计入口复现发送时刻漂移及服务端到达聚集；不联网。"""
import pytest

from hangma_bot.adapters.official.request_audit import audited_request
from hangma_bot.adapters.official.scheduler import Priority, RequestKind, RequestScheduler
from hangma_bot.adapters.official.transport import TransportResult
from _virtual_clock import VirtualClock
from test_default_state_budget import MODES, default_session, GAMES, state_sends


@pytest.mark.parametrize('mode', MODES)
async def test_production_refill_keeps_fifty_ms_arrival_margin(monkeypatch, mode):
    clock = VirtualClock()
    session, target, transport = default_session(monkeypatch, clock, mode)
    try:
        await clock.run(session.initialize(target))
        games = [session.open_game(g) for g in GAMES]
        for i in range(32):
            await clock.run(games[i % 10].next_item())
        starts = [r[0] for r in state_sends(transport)]
        # 第一批上行40ms，下一批零延迟：即使本机16/s，服务端仍会挤入32笔。
        arrivals = [t + (.04 if i < 16 else 0) for i,t in enumerate(starts)]
        assert all(sum(at - 1 < t <= at for t in arrivals) <= 16 for at in arrivals)
        assert starts[16] - starts[0] == pytest.approx(1.05)
    finally:
        await session.aclose()


async def test_audit_and_lease_use_one_send_timestamp_after_reservation():
    clock = VirtualClock()
    root = RequestScheduler(clock=clock.monotonic, sleep=clock.sleep)
    scope = root.for_game('g', max_games=10)
    records = []
    class Transport:
        async def request(self, *args, **kwargs):
            return TransportResult(200, '{}')
    for i in range(16):
        lease = await clock.run(scope.acquire(Priority.POLL, request_kind=RequestKind.STATE, reserve_only=True))
        if i == 0:
            # 预占后、真正传输前耗时；预占不能先开始按秒过期。
            await clock.run(clock.sleep(.0001))
        try:
            await audited_request(Transport(), lambda k,p: records.append(p), clock.monotonic,
                'GET', '/api/games/g/state', on_start=lease.mark_sent)
        finally:
            lease.release()
    await clock.run(clock.sleep(.99991))
    lease = await clock.run(scope.acquire(Priority.POLL, request_kind=RequestKind.STATE, reserve_only=True))
    try:
        await audited_request(Transport(), lambda k,p: records.append(p), clock.monotonic,
            'GET', '/api/games/g/state', on_start=lease.mark_sent)
    finally:
        lease.release()
    starts = [p['request_timing']['transport_started_at_monotonic'] for p in records if p.get('phase')=='started']
    assert len(starts)==17
    assert starts[-1] - starts[0] >= 1.0
    assert root.state_used_count == 1


async def test_guard_discards_expired_query_without_delaying_action():
    from hangma_bot.adapters.official.scheduler import DeadlineExceeded
    clock = VirtualClock()
    root = RequestScheduler(clock=clock.monotonic, sleep=clock.sleep, state_arrival_guard_sec=.05)
    game = root.for_game('g', max_games=10)
    for _ in range(16):
        (await clock.run(game.acquire(Priority.POLL))).release()
    # 动作不消费state账；50ms余量只影响下一份state许可。
    (await clock.run(game.acquire(Priority.ACTION, request_kind=RequestKind.OTHER))).release()
    assert clock.monotonic() == 0
    with pytest.raises(DeadlineExceeded):
        await clock.run(game.acquire(Priority.RECOVERY, deadline_monotonic=1.02, reserve_only=True))
    assert root.state_used_count == 16
    lease = await clock.run(game.acquire(Priority.POLL, reserve_only=True))
    assert clock.monotonic() == pytest.approx(1.05)
    lease.release()
    assert root.state_used_count == 0, '过期及未发取消均没有追加发送账'


@pytest.mark.parametrize('guard', [-1, float('nan'), float('inf')])
def test_invalid_guard_is_rejected(guard):
    with pytest.raises(ValueError, match='state_arrival_guard_sec'):
        RequestScheduler(clock=lambda: 0, state_arrival_guard_sec=guard)


async def test_direct_clock_samples_are_present_on_error_without_extra_request():
    from hangma_bot.adapters.official.errors import ConflictError
    clock = VirtualClock()
    records = []
    class Transport:
        async def request(self, *args, **kwargs):
            clock.advance(.02)
            raise ConflictError(409, 'INVALID_ACTION', 'closed')
    with pytest.raises(ConflictError):
        await audited_request(Transport(), lambda k,p: records.append(p), clock.monotonic,
            'POST', '/api/games/g/action', wall_clock=clock.wall_ms)
    finished = next(p for p in records if p.get('phase') == 'finished')
    t = finished['request_timing']
    assert t['completed_wall_unix_ms'] - t['started_wall_unix_ms'] == 20
    assert t['started_clock_sample_end_monotonic'] == 0
    assert t['completed_clock_sample_end_monotonic'] == .02
    assert finished['http_status'] == 409
