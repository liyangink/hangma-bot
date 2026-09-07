"""普通他家弃牌可由连续增量投影；抓打或缺字段仍用权威快照。"""
from hangma_bot.application.contracts import ObservedActionWindow
from hangma_bot.kernel.actions import WindowPhase
from test_sync_repair_regressions import event, make_game_session, script, snapshot


async def test_plain_discard_delivers_peng_without_second_state_get(transport, clock):
    before = snapshot(100)
    before['snapshot']['god']['catch_play'] = False
    queue = script(transport, [
        (0, before),
        (100, {'events': [event(101, 'tile_drawn', seat=0),
                         event(102, 'tile_discarded', seat=0, tile='6t', data={'catch_play': False})]}),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.phase is WindowPhase.RESPONSE_PENG
        assert window.window_key.trigger_seq == 102
        assert window.observation.consumed_seq == 102
        assert window.observation.snapshot_seq == 100
        assert [t.code for t in window.observation.discards[0]] == ['6t']
        assert window.observation.hand_counts[0] == before['snapshot']['hand_counts'][0]
        assert window.observation.remaining_tile_count == before['snapshot']['wall_remaining'] - 1
        assert not queue and len(transport.calls) == 2
    finally:
        await session.aclose('test')


async def test_coarse_event_timestamp_uses_previous_state_query_as_proven_lower_bound(transport, clock):
    import json
    clock.advance(.8)
    baseline_start = clock.monotonic()
    before = snapshot(100)
    before['snapshot']['god']['catch_play'] = False
    calls = 0
    def handler(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return 200, json.dumps(before)
        assert calls == 2
        clock.advance(.1)
        discard = event(101, 'tile_discarded', tile='6t', data={'catch_play': False})
        discard['ts'] = clock.wall_ms() // 1000
        return 200, json.dumps({'events': [discard]})
    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        # 新事件在旧水位快照形成之后发生，不可能早于旧 GET 开始。
        assert window.expires_at_monotonic >= baseline_start + 1 - 1e-6
        assert window.expires_at_monotonic <= clock.monotonic() + 1
    finally:
        await session.aclose('test')
