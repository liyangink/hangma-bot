"""2026-09-06 v17测试房真实协议形态回归，来源见live-validation报告。"""
import pytest
from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import public_event
from hangma_bot.application.contracts import ObservedActionWindow, SubmitNotSent
from hangma_bot.kernel.actions import WindowPhase
from test_sync_repair_regressions import snapshot, event, script, make_game_session, attempt


def test_snapshot_keeps_simultaneous_terminal_events():
    doc=snapshot(102,phase='finished')
    doc['finished']=True
    doc['events']=[event(101,'round_ended',seat=0,data={'draw':False,'fan':2,'detail':['平胡','爆头'],'scores':[48,-16,-16,-16]}),event(102,'game_ended',seat=-1,data={'final_scores':[48,-16,-16,-16]})]
    parsed=parse_state_response(doc)
    assert [e.seq for e in parsed.events]==[101,102]
    assert public_event(parsed.events[0]).result_scores==(48,-16,-16,-16)
    assert public_event(parsed.events[1]).final_scores==(48,-16,-16,-16)


@pytest.mark.parametrize('kind,tile,data,field,expected',[
    ('tile_discarded','1b',{'catch_play':False},'catch_play',False),
    ('tile_drawn','1b',{'gang_replenish':True},'gang_replenish',True),
    ('timeout','',{'kind':'response','window':'chi'},'response_window','chi'),
])
def test_public_event_retains_known_data(kind,tile,data,field,expected):
    parsed=parse_state_response({'events':[event(101,kind,tile=tile,data=data)]})
    assert getattr(public_event(parsed.events[0]),field,None)==expected


async def test_masked_other_draw_remains_in_public_history(transport,clock):
    # 弃东：本方手牌持东×2（碰兴趣超集）——2026-09-18 起有兴趣才刷新
    script(transport,[(0,snapshot(100)),(100,{'events':[event(101,'tile_drawn'),event(102,'tile_discarded',tile='东')]}),(0,snapshot(102,phase='response_peng',river=('东',),discard='东',responders=(1,2,3)))])
    session=make_game_session(transport=transport,clock=clock)
    try:
        window=await session.next_item()
        assert isinstance(window,ObservedActionWindow)
        assert [(e.seq,e.kind,len(e.tiles)) for e in window.observation.public_history]==[(101,'tile_drawn',0),(102,'tile_discarded',1)]
        assert 'unexpected_other_draw' not in window.observation.observation_issues
    finally:await session.aclose('test')


async def test_peng_pass_is_deferred_and_real_chi_window_is_delivered(transport,clock):
    script(transport,[(0,snapshot(100,phase='response_peng',river=('6t',),discard='6t',responders=(1,2,3))),(100,snapshot(100,phase='response_chi',river=('6t',),discard='6t',responders=(2,)))])
    session=make_game_session(transport=transport,clock=clock)
    try:
        first=await session.next_item()
        result=await session.submit(attempt(first,clock))
        assert isinstance(result,SubmitNotSent)
        assert not [c for c in transport.calls if c.method=='POST']
        second=await session.next_item()
        assert second.window_key.phase is WindowPhase.RESPONSE_CHI
    finally:await session.aclose('test')


async def test_snapshot_ahead_preserves_received_history_and_advances_cursor(transport, clock):
    queue = script(transport, [(0, snapshot(100)),
        (100, {'events': [event(101, 'tile_discarded', tile='东')]}),
        (0, snapshot(103, phase='response_peng', river=('东',), discard='东', responders=(1,2,3)))])
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        assert [e.seq for e in window.observation.public_history] == [101]
        assert window.observation.consumed_seq == 103
        assert len(window.observation.discards[0]) == 1
        assert not queue
    finally:
        await session.aclose('test')



async def test_next_regular_poll_recovers_old_events_and_delivers_new_draw(transport, clock):
    queue = script(transport, [(0, snapshot(100)),
        (100, snapshot(102, phase='response_peng', river=('6t',), discard='6t', responders=(1,2,3))),
        (100, {'events': [event(101, 'tile_discarded', tile='6t'), event(102, 'pass', seat=1), event(103, 'tile_drawn', seat=2, tile='7w')]})])
    session = make_game_session(transport=transport, clock=clock)
    try:
        first = await session.next_item()
        assert first.window_key.phase is WindowPhase.RESPONSE_PENG
        window = await session.next_item()
        assert window.window_key.phase is WindowPhase.DRAW
        assert window.window_key.trigger_seq == 103
        assert [e.seq for e in window.observation.public_history] == [101, 102, 103]
        assert not queue
    finally:
        await session.aclose('test')



def test_masked_draw_closes_old_response_and_updates_public_counts():
    from hangma_bot.adapters.official.sync_state import ProtocolSyncState
    from _official_testkit import TIMING
    state=ProtocolSyncState('g',TIMING)
    state.apply_full_snapshot(parse_state_response(snapshot(100,phase='response_chi',responders=(2,))).snapshot)
    before=state.current_observation()
    state.apply_events(parse_state_response({'events':[event(101,'tile_drawn',seat=1)]}).events)
    assert state.current_window() is None
    after=state.current_observation()
    assert after.phase=='draw' and after.turn_seat==1
    assert after.responding_seats==()
    assert after.hand_counts[1]==before.hand_counts[1]+1
    assert after.remaining_tile_count==before.remaining_tile_count-1


@pytest.mark.parametrize('kind,tile,data',[
    ('tile_discarded','1b',{'catch_play':0}),
    ('tile_drawn','1b',{'gang_replenish':None}),
    ('timeout','',{'window':False}),
    ('round_ended','',{'fan':False}),
    ('round_ended','',{'scores':[0,0,0]}),
    ('game_ended','',{'final_scores':[0,0,0,False]}),
])
def test_malformed_known_event_facts_do_not_become_normal_values(kind,tile,data):
    from hangma_bot.adapters.official.errors import DtoError
    with pytest.raises(DtoError):parse_state_response({'events':[event(101,kind,tile=tile,data=data)]})


def test_public_facts_round_trip_through_complete_observation():
    from dataclasses import replace
    from hangma_bot.adapters.official.projector import observation
    from hangma_bot.kernel.serialization import observation_to_json, observation_from_json
    raw = [event(101,'tile_discarded',tile='1b',data={'catch_play':False,'private_future':'ignored'}),
           event(102,'tile_drawn',seat=2,tile='1b',data={'gang_replenish':True}),
           event(103,'timeout',data={'kind':'response','window':'chi'}),
           event(104,'round_ended',data={'draw':False,'fan':0,'detail':['平胡'],'scores':[3,-1,-1,-1]}),
           event(105,'game_ended',seat=-1,data={'final_scores':[3,-1,-1,-1]})]
    events=tuple(public_event(e) for e in parse_state_response({'events':raw}).events)
    obs=replace(observation(parse_state_response(snapshot(105)).snapshot,events,'g'),consumed_seq=105)
    encoded=observation_to_json(obs)
    assert observation_from_json(encoded)==obs
    assert 'private_future' not in str(encoded)
    assert obs.public_history[0].catch_play is False
    assert obs.public_history[3].result_fan == 0


def test_terminal_event_pair_is_preserved_before_final_snapshot():
    from hangma_bot.adapters.official.sync_state import ProtocolSyncState, SyncDecision
    from _official_testkit import TIMING
    state=ProtocolSyncState('g',TIMING)
    state.apply_full_snapshot(parse_state_response(snapshot(100)).snapshot)
    events=parse_state_response({'events':[event(101,'round_ended',data={'draw':True,'scores':[0,0,0,0]}),event(102,'game_ended',seat=-1,data={'final_scores':[1,-1,0,0]})]}).events
    assert state.apply_events(events).decision is SyncDecision.ACCEPTED
    state.apply_full_snapshot(parse_state_response(snapshot(102,phase='finished')).snapshot,finished=True)
    assert [e.seq for e in state.current_observation().public_history]==[101,102]


def test_snapshot_attached_pass_prevents_duplicate_response():
    from hangma_bot.adapters.official.sync_state import ProtocolSyncState
    from _official_testkit import TIMING
    state=ProtocolSyncState('g',TIMING)
    state.apply_full_snapshot(parse_state_response(snapshot(100)).snapshot)
    doc=snapshot(102,phase='response_chi',responders=(2,),discard='6t',river=('6t',))
    events=parse_state_response({'events':[event(101,'tile_discarded',tile='6t'),event(102,'pass',seat=2)]}).events
    state.apply_full_snapshot(parse_state_response(doc).snapshot,events=events)
    assert state.response_suppressed_for_self


def test_new_hand_snapshot_does_not_inherit_previous_hand_ending():
    from hangma_bot.adapters.official.sync_state import ProtocolSyncState
    from _official_testkit import TIMING
    state=ProtocolSyncState('g',TIMING)
    state.apply_full_snapshot(parse_state_response(snapshot(100)).snapshot)
    events=parse_state_response({'events':[event(101,'round_ended',data={'draw':True})]}).events
    state.apply_full_snapshot(parse_state_response(snapshot(101,round_no=2)).snapshot,events=events)
    assert state.current_observation().round_no==2
    assert state.current_observation().public_history==()


async def test_incremental_gap_after_snapshot_still_requires_recovery(transport, clock):
    queue = script(transport, [(0, snapshot(100)),
        (100, snapshot(102, phase='response_peng', river=('6t',), discard='6t', responders=(1,2,3))),
        (100, {'pending': True, 'gap': True}),
        (0, snapshot(103, phase='response_chi', river=('6t',), discard='6t', responders=(2,)))])
    session = make_game_session(transport=transport, clock=clock)
    try:
        await session.next_item()
        window = await session.next_item()
        assert window.window_key.phase is WindowPhase.RESPONSE_CHI
        assert window.observation.snapshot_seq == 103
        assert not queue
    finally:
        await session.aclose('test')
