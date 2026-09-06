"""由官方补牌轨迹构造摸前边界，核查公开同步接口的生命周期。"""
import json
from pathlib import Path

import pytest

from _official_testkit import TIMING
from hangma_bot.adapters.official.dto import parse_snapshot, parse_state_response
from hangma_bot.adapters.official.sync_state import ProtocolSyncState


@pytest.mark.parametrize("source,expected", [(True, True), (False, False), (None, None)])
def test_incremental_draw_does_not_guess_or_erase_continuous_baotou(source, expected):
    fixture = Path(__file__).parents[2] / "fixtures/official/v18/action-chain/chi-gang-draw.json"
    trace = json.loads(fixture.read_text())
    body = trace["snapshots"]["2269"]["snapshot"]
    drawn = body["drawn_tile"]
    # 从真实补牌后暗牌撤回这张摸牌，构造 seq2268 摸前快照；并非额外实测样本。
    body["my_hand"].remove(drawn)
    body["drawn_tile"] = ""
    body["hand_counts"][body["seat"]] -= 1
    state = ProtocolSyncState(body["game_id"], TIMING)
    state.apply_full_snapshot(parse_snapshot(body, 2268))
    event = next(e for e in trace["events"] if e["seq"] == 2269)
    if source is None:
        event["data"].pop("gang_replenish", None)
    else:
        event["data"]["gang_replenish"] = source
    events = parse_state_response({"events": [event]}).events
    state.apply_events(events)
    assert state.events_need_authoritative_refresh(events) is (source is None)
    if source is None:
        with pytest.raises(ValueError, match="摸牌来源未知"):
            state.current_observation()
    else:
        result = state.current_observation()
        assert result.rule_state.baotou is expected
        assert result.gang_draw is source
        assert result.rule_state.chain_count == body["god"]["chain_count"]
