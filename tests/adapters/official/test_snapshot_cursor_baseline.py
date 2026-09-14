"""完整快照直接建立状态基线，不再回退游标补史后才能行动。"""
import pytest

from hangma_bot.application.contracts import ObservedActionWindow
from test_sync_repair_regressions import make_game_session, script, snapshot, event


@pytest.mark.parametrize('initial_seq,next_seq', [(0, 1), (100, 105)])
async def test_snapshot_is_delivered_before_next_regular_history_poll(transport, clock, initial_seq, next_seq):
    queue = script(transport, [
        (0, snapshot(initial_seq, turn=2, drawn='7w')),
        (initial_seq, snapshot(next_seq, turn=2, drawn='8w')),
        (max(1, initial_seq), snapshot(next_seq + 1, turn=2, drawn='9w')),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        windows = [await session.next_item() for _ in range(3)]
        assert all(isinstance(w, ObservedActionWindow) for w in windows)
        assert [w.authoritative_seq for w in windows] == [initial_seq, next_seq, next_seq + 1]
        assert 'history_gap_snapshot' not in windows[1].observation.observation_issues
        assert not queue
    finally:
        await session.aclose('test')


async def test_snapshot_history_is_retained_but_not_reapplied(transport, clock):
    queue = script(transport, [
        (0, snapshot(100)),
        (100, {'events': [event(101, 'tile_drawn', seat=2, tile='7w')]}),
        (101, snapshot(110, turn=2, drawn='8w', river=('6t',))),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        await session.next_item()
        window = await session.next_item()
        assert window.observation.public_history[0].seq == 101
        assert [t.code for t in window.observation.discards[0]] == ['6t']
        assert not window.observation.history_complete
        assert not queue
    finally:
        await session.aclose('test')
