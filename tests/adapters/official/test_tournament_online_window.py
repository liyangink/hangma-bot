"""官方90秒在线条件的健康传输模拟；只验证认证轮询持续性，不冒称联网验收。"""

import asyncio
import json
from pathlib import Path

from _official_testkit import load_fixture, make_tournament_session
from hangma_bot.application.contracts import ParticipantTerminal, RuntimeMode, RuntimeTarget, TournamentStatus


async def test_stage_done_empty_games_polls_authenticated_me_for_over_ninety_seconds(transport, clock):
    """假单调钟跨过100秒空档，默认2秒轮询仍持续，finished才结束等待。"""
    me = load_fixture("me.json")
    me["active_games"] = []
    detail = load_fixture("tournament_detail.json")
    detail.update(status="stage_done", stage_status="done", my_games=[])
    guide = json.loads((Path(__file__).parents[3] / "doc/references/official-guide-version-v35.json").read_text())
    authenticated_times = []
    began = clock.monotonic()

    def handler(*, method, path, **kwargs):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(guide)
        if path == "/api/me":
            authenticated_times.append(clock.monotonic())
            return 200, json.dumps(me)
        if path == "/api/tournaments/me/rules":
            return 200, json.dumps(load_fixture("rules.json"))
        if path == "/api/tournaments/t_test_room_1":
            current = dict(detail)
            if clock.monotonic() - began >= 100:
                current.update(status="finished", stage_status="done")
            return 200, json.dumps(current)
        raise AssertionError(method + " " + path)

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(RuntimeMode.TEST_TOURNAMENT, "t_test_room_1", 35)
    try:
        initial = await asyncio.wait_for(session.initialize(target), timeout=3)
        assert not isinstance(initial, ParticipantTerminal)
        assert initial.initial_snapshot.status is TournamentStatus.STAGE_DONE
        assert not initial.initial_snapshot.active_games
        final = await asyncio.wait_for(session.next_update(), timeout=3)
        assert not isinstance(final, ParticipantTerminal)
        assert final.status is TournamentStatus.FINISHED
        assert authenticated_times[-1] - authenticated_times[0] >= 100
        assert max(second - first for first, second in zip(authenticated_times, authenticated_times[1:])) <= 2.01
        assert len(authenticated_times) >= 50
        assert all(call.method == "GET" for call in transport.calls)
    finally:
        await session.aclose()
