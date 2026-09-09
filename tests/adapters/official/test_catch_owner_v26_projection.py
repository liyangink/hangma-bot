"""v26新增god字段解析、旧版本兼容及真实会话对策略的圈主事实交付。"""

import json

import pytest

from _official_testkit import load_fixture, make_game_session
from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.errors import DtoError
from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitAccepted
from hangma_bot.hangma.catch_play import analyze_catch_play
from hangma_bot.kernel.actions import Discard, Tile


def snapshot(owner=2, active=True):
    """以旧官方报文为结构底稿，按v26文档注入新字段；不是线上抓取样本。"""
    doc = load_fixture("state_response_snapshot_draw.json")
    doc["snapshot"]["god"].update(catch_play=active, god_discarder_seat=owner)
    return doc


@pytest.mark.parametrize("owner,active", [(0, True), (1, True), (2, True), (3, True), (-1, False)])
def test_v26_owner_field_parses_without_guessing(owner, active):
    assert parse_state_response(snapshot(owner, active)).snapshot.god_discarder_seat == owner


@pytest.mark.parametrize("owner", [True, 4, -2, "2", 2.5, None])
def test_invalid_present_owner_triggers_rebuild_eligible_dto_failure(owner):
    with pytest.raises(DtoError):
        parse_state_response(snapshot(owner))


def test_active_circle_with_explicit_no_owner_is_not_silently_treated_as_legacy():
    with pytest.raises(DtoError):
        parse_state_response(snapshot(-1, True))


def test_older_response_without_field_remains_supported():
    assert parse_state_response(load_fixture("state_response_snapshot_draw.json")).snapshot.god_discarder_seat is None


async def test_session_delivers_authoritative_owner_and_allows_hand_discard_without_white_history(transport, clock, audit):
    transport.handler = lambda **kwargs: (200, json.dumps(snapshot()))
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.observation.rule_state.catch_play_owner_seat == 2
        assert not analyze_catch_play(window.observation).restricts(2)
        transport.handler = lambda **kwargs: (200, '{"ok":true}')
        attempt = ActionAttempt("v26", 1, 1, window.window_key, window.authoritative_seq,
                                Discard(Tile("1w")), "discard:1w", clock.monotonic()+.5)
        assert isinstance(await session.submit(attempt), SubmitAccepted)
        assert transport.calls[-1].json_body == {"action": "discard", "tile": "1w"}
    finally:
        await session.aclose("test")
