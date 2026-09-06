"""v17 玩家端真实公开字段通过适配器、kernel 和审计编解码的契约。"""
import json
from pathlib import Path
import pytest
from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import public_event, observation
from hangma_bot.kernel.serialization import observation_to_json, observation_from_json

FIXTURES = Path(__file__).parents[1] / 'fixtures/official/v17/live-20260906'


def load(name):
    return json.loads((FIXTURES / (name + '.json')).read_text())


@pytest.mark.parametrize('name', ['masked-other-draw', 'gang-replenish', 'discard-catch-play', 'terminal-mixed'])
def test_real_player_facts_survive_audit_round_trip(name):
    """固定玩家响应片段独立于 runs 目录，保存来源哈希且不连接官方。"""
    parsed = parse_state_response(load(name))
    events = tuple(public_event(e) for e in parsed.events)
    terminal = parse_state_response(load('terminal-mixed'))
    obs = observation(terminal.snapshot, events, 'fixture')
    encoded = observation_to_json(obs)
    assert observation_from_json(encoded) == obs
    if name == 'masked-other-draw':
        assert events[0].tiles == ()
    elif name == 'gang-replenish':
        assert events[0].gang_replenish is True
    elif name == 'discard-catch-play':
        assert events[0].catch_play is False
    else:
        assert len(events) == 2
        assert events[0].result_scores is not None
        assert events[1].final_scores is not None


def test_old_event_record_decodes_new_facts_as_unknown():
    """schema 1 可选字段兼容，不把缺字段假装为 false 或零。"""
    parsed = parse_state_response(load('terminal-mixed'))
    obs = observation(parsed.snapshot, tuple(public_event(e) for e in parsed.events), 'fixture')
    encoded = observation_to_json(obs)
    fields = ('catch_play', 'gang_replenish', 'response_window', 'result_draw', 'result_fan',
              'result_details', 'result_scores', 'final_scores')
    for item in encoded['public_history']:
        for field in fields:
            item.pop(field)
    decoded = observation_from_json(encoded)
    for event in decoded.public_history:
        assert all(getattr(event, field) is None for field in fields)


def test_terminal_event_can_be_encoded_without_constructing_actionable_observation():
    """收尾接口接受公开终局事件，不要求策略窗口或伪造终态行动座位。"""
    from hangma_bot.kernel.serialization import public_event_to_json
    from hangma_bot.kernel.observation import PublicEvent
    event=PublicEvent(seq=42,kind='game_ended',seat=None,final_scores=(15,16,-21,-10))
    encoded=public_event_to_json(event)
    assert encoded['seat'] is None
    assert encoded['final_scores']==[15,16,-21,-10]
    assert encoded['result_scores'] is None
    assert json.loads(json.dumps(encoded))==encoded
