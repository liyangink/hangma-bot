"""v24 官方原文：仅 scoped 入口完成审查，未知 breaking 与全局令牌仍受门禁。"""
import json
from pathlib import Path

import pytest

from _official_testkit import load_fixture, make_tournament_session
from hangma_bot.adapters.official.dto import parse_guide_version
from hangma_bot.application.contracts import (
    OperationStatus, ParticipantTerminal, ParticipantTerminalReason, RuntimeMode, RuntimeTarget,
)


REFERENCE = Path(__file__).parents[3] / "doc/references/official-guide-version-v24.json"
TARGET = RuntimeTarget(RuntimeMode.TEST_ROOM, "t_test_room_1", 23)


def guide():
    return json.loads(REFERENCE.read_text())


def test_scoped_review_does_not_change_raw_guide_or_global_default():
    original = guide()
    assert parse_guide_version(original).has_unknown_breaking_change
    parsed = parse_guide_version(original, scoped_tournament=True)
    assert parsed.version == 24 and not parsed.has_unknown_breaking_change
    assert list(parsed.changes) == original["changes"]


@pytest.mark.parametrize("unreviewed", [25, "24", True, None])
def test_reviewed_v24_does_not_mask_future_or_malformed_breaking(unreviewed):
    original = guide()
    original["version"] = 25
    original["changes"].append({"version":unreviewed, "type":"breaking", "summary":"未审查"})
    assert parse_guide_version(original, scoped_tournament=True).has_unknown_breaking_change


@pytest.mark.parametrize("future_breaking", [False, True])
async def test_scoped_start_and_stage_ready_use_the_same_review_boundary(transport, clock, future_breaking):
    state = {"guide":guide(), "detail":"tournament_detail.json"}
    def handler(*, method, path, **kwargs):
        if path == "/portal/api/guide/version":
            value = state["guide"]
        elif path == "/api/me":
            value = load_fixture("me.json")
        elif path.endswith("/rules"):
            value = load_fixture("rules.json")
        elif method == "POST":
            value = {}
        else:
            value = load_fixture(state["detail"])
        return 200, json.dumps(value)
    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    started = await session.initialize(TARGET)
    assert not isinstance(started, ParticipantTerminal)
    assert started.guide.version == 24 and not started.guide.has_unknown_breaking_change
    assert (await session.register()).status is OperationStatus.ACCEPTED
    state["detail"] = "tournament_stage_open.json"
    changed = await session.next_update()
    if future_breaking:
        state["guide"]["version"] = 25
        state["guide"]["changes"].append({"version":25, "type":"breaking", "summary":"未审查"})
    result = await session.ready(changed.stage)
    ready_calls = [c for c in transport.calls if c.method == "POST" and c.path.endswith("/ready")]
    if future_breaking:
        assert isinstance(result, ParticipantTerminal)
        assert result.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE
        assert not ready_calls
    else:
        assert result.status is OperationStatus.ACCEPTED
        assert len(ready_calls) == 1


async def test_scoped_entry_still_rejects_global_token_before_any_post(transport, clock):
    me = load_fixture("me.json")
    me["tournament_id"] = ""
    transport.handler = lambda **kw: (200, json.dumps(guide() if kw["path"].endswith("/version") else me))
    session = make_tournament_session(clock=clock, transport=transport)
    outcome = await session.initialize(TARGET)
    assert outcome.reason is ParticipantTerminalReason.TARGET_MISMATCH
    assert all(c.method == "GET" for c in transport.calls)
