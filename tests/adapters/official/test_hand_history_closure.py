"""单局结束没有策略动作时，历史和缺口也必须形成独立审计记录。"""
from _official_testkit import FakeAuditSink
from test_sync_repair_regressions import snapshot,event,script,make_game_session
from hangma_bot.application.contracts import GameFinished


async def test_terminal_history_is_sealed_without_another_policy_window(transport,clock):
    audit=FakeAuditSink()
    final=snapshot(102,phase='finished');final['finished']=True
    script(transport,[(0,snapshot(100,turn=2,drawn='7w')),(100,{'events':[event(101,'round_ended',data={'draw':True,'scores':[0,0,0,0]}),event(102,'game_ended',seat=-1,data={'final_scores':[0,0,0,0]})]}),(0,final)])
    session=make_game_session(transport=transport,clock=clock,audit=audit)
    await session.next_item()
    assert isinstance(await session.next_item(),GameFinished)
    await session.aclose('test')
    seals=[r.payload for r in audit.records if r.payload.get('history_closure')]
    assert len(seals)==1
    assert seals[0]['history_closure']=='game_finished'
    assert [e['seq'] for e in seals[0]['public_history']]==[101,102]
    assert seals[0]['public_history'][-1]['final_scores']==[0,0,0,0]


async def test_hand_switch_seals_old_history_before_replacing_it(transport,clock):
    audit=FakeAuditSink()
    script(transport,[(0,snapshot(100,turn=2,drawn='7w')),(100,{'events':[event(101,'round_ended',data={'draw':True,'scores':[0,0,0,0]})]}),(0,snapshot(102,round_no=2,turn=2,drawn='8w'))])
    session=make_game_session(transport=transport,clock=clock,audit=audit)
    await session.next_item()
    next_hand=await session.next_item()
    seals=[r.payload for r in audit.records if r.payload.get('history_closure')=='round_changed']
    assert len(seals)==1 and seals[0]['round_no']==1
    assert [e['seq'] for e in seals[0]['public_history']]==[101]
    assert next_hand.observation.round_no==2 and next_hand.observation.public_history==()
    await session.aclose('test')


async def test_new_hand_packet_old_tail_is_included_only_after_valid_transition(transport,clock):
    audit=FakeAuditSink()
    new=snapshot(104,round_no=2,phase='response_chi',river=('6t',),discard='6t',responders=(2,))
    new['events']=[event(101,'tile_discarded',seat=2,tile='7w'),event(102,'round_ended',data={'draw':True}),event(103,'tile_discarded',tile='6t'),event(104,'pass',seat=1)]
    script(transport,[(0,snapshot(100,turn=2,drawn='7w')),(100,new)])
    session=make_game_session(transport=transport,clock=clock,audit=audit)
    await session.next_item();window=await session.next_item()
    seal=next(r.payload for r in audit.records if r.payload.get('history_closure')=='round_changed')
    assert [e['seq'] for e in seal['public_history']]==[101,102]
    assert seal['history_through_seq']==102
    assert [e.seq for e in window.observation.public_history]==[103,104]
    await session.aclose('test')


async def test_invalid_new_hand_snapshot_does_not_seal_current_hand(transport,clock):
    from hangma_bot.application.contracts import GameFailed
    audit=FakeAuditSink()
    new=snapshot(102,round_no=2,turn=2,drawn='8w')
    new['events']=[event(101,'round_ended',data={'draw':True}),event(101,'round_ended',data={'draw':False})]
    script(transport,[(0,snapshot(100,turn=2,drawn='7w')),(100,new)])
    session=make_game_session(transport=transport,clock=clock,audit=audit)
    await session.next_item()
    assert isinstance(await session.next_item(),GameFailed)
    assert not [r for r in audit.records if r.payload.get('history_closure')]
    await session.aclose('test')


async def test_finished_snapshot_closes_directly_and_records_absent_tail(transport, clock):
    audit = FakeAuditSink()
    final = snapshot(102, phase='finished'); final['finished'] = True
    queue = script(transport, [(0, snapshot(100, turn=2, drawn='7w')), (100, final)])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    await session.next_item()
    assert isinstance(await session.next_item(), GameFinished)
    seal = next(r.payload for r in audit.records if r.payload.get('history_closure') == 'game_finished')
    assert seal['public_history'] == []
    assert 'round_ended_not_observed' in seal['closure_issues']
    assert not queue and len(transport.calls) == 2
    await session.aclose('test')



async def test_terminal_backfill_never_reopens_a_confirmed_finished_game(transport, clock):
    """补历史不能把已确认终态替换成另一张活动快照。"""
    audit = FakeAuditSink()
    final = snapshot(102, phase='finished'); final['finished'] = True
    script(transport, [(0, snapshot(100, turn=2, drawn='7w')), (100, final),
                       (100, snapshot(104, turn=2, drawn='8w'))])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    await session.next_item()
    assert isinstance(await session.next_item(), GameFinished)
    await session.aclose('test')
