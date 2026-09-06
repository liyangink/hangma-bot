"""实现后运行视角交叉审查反例：保留历史与观察缓存。"""

import asyncio

from test_observation_differential_repair import _session, _snapshot
from hangma_bot.application.contracts import ObservedActionWindow
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicDiscard


async def test_retained_old_discard_does_not_override_newer_snapshot_during_draw():
    refreshed = _snapshot(104, phase="response_chi")
    refreshed["snapshot"]["last_discard"]["seq"] = 103
    refreshed["snapshot"]["discards"][0].append("6w")
    session, _, _ = _session([
        _snapshot(),
        {"events": [{"seq": 101, "type": "tile_discarded", "seat": 0, "tile": "6w"}]},
        refreshed,
        {"pending": True},  # 可选补领无历史可用，继续验证保留旧事件不覆盖新桌面
        {"events": [{"seq": 105, "type": "tile_drawn", "seat": 2, "tile": "中"}]},
    ])
    try:
        assert isinstance(await asyncio.wait_for(session.next_item(), 1), ObservedActionWindow)
        drawn = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(drawn, ObservedActionWindow)
        assert drawn.observation.last_discard == PublicDiscard(1, Tile("9t"), 103)
        assert [event.seq for event in drawn.observation.public_history] == [101, 105]
    finally:
        await session.aclose("test_done")


async def test_unknown_event_annotation_reaches_already_prewarmed_observation():
    recovered = _snapshot(101, phase="response_peng")
    session, _, _ = _session([
        _snapshot(),
        {"events": [{"seq": 101, "type": "future_rule_event", "seat": 1, "tile": ""}]},
        recovered,
    ])
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(window, ObservedActionWindow)
        assert "unknown_event:future_rule_event" in window.observation.observation_issues
        assert window.observation.history_complete is False
    finally:
        await session.aclose("test_done")


async def test_unexpected_other_draw_forces_recovery_before_delivering_old_self_draw():
    recovered = _snapshot(103, turn=2)
    recovered["snapshot"].update(drawn_tile="东", hand_counts=[13, 13, 14, 13], wall_remaining=37)
    session, transport, _ = _session([
        _snapshot(),
        {"events": [
            {"seq": 101, "type": "tile_drawn", "seat": 2, "tile": "中"},
            {"seq": 102, "type": "tile_drawn", "seat": 0, "tile": "7w"},
        ]},
        recovered,
        {"pending": True},
    ])
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.trigger_seq == 103
        assert window.observation.drawn_tile == Tile("东")
        assert [call.params["seq"] for call in transport.calls] == [0, 100, 0, 102]
        assert not any(e.seat == 0 and e.kind == "tile_drawn" for e in window.observation.public_history)
    finally:
        await session.aclose("test_done")
