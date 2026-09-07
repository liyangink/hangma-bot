"""换手尾部封存的完整性与权限回归；只使用正式GameSession公开入口。

2026-09-06只读评审发现：旧手原本完整时，新手快照附带未知/不完整/违规
私牌的旧尾，不能仅因事件序号连续就把封存标成完整。这些问题须保留在封存原因中。
"""
import pytest

from _official_testkit import FakeAuditSink
from test_sync_repair_regressions import event, make_game_session, script, snapshot


async def seal_old_tail(transport, clock, tail):
    """以规范起点和相邻新手报文触发封存；不接触会话私有状态。"""
    audit = FakeAuditSink()
    first = snapshot(100, turn=2, drawn='7w')
    first['snapshot']['dealer'] = 2
    first['snapshot']['melds'] = [[], [], [], []]
    new = snapshot(103, round_no=2, phase='response_chi', river=('6t',),
                   discard='6t', responders=(2,))
    new['events'] = [tail, event(102, 'round_ended', data={'draw': True}),
                     event(103, 'tile_discarded', tile='6t')]
    script(transport, [(0, first), (100, new)])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        first_window = await session.next_item()
        assert first_window.observation.history_complete
        next_window = await session.next_item()
        assert next_window.observation.round_no == 2
        assert all(e.seq > 102 for e in next_window.observation.public_history)
        closures = [r.payload for r in audit.records
                    if r.payload.get('history_closure') == 'round_changed']
        assert len(closures) == 1
        closure = closures[0]
        assert closure['round_no'] == 1
        assert closure['missing_ranges'] == []  # 本次不是数字序号缺口
        assert [e['seq'] for e in closure['public_history']] == [101, 102]
        return closure
    finally:
        await session.aclose('closure_validation')


async def test_unknown_old_tail_is_retained_but_not_reported_complete(transport, clock):
    closure = await seal_old_tail(transport, clock, event(101, 'future_critical_rule'))
    assert closure['public_history'][0]['kind'] == 'future_critical_rule'
    assert 'unknown_snapshot_event' in closure['closure_issues']
    assert closure['history_complete'] is False


@pytest.mark.parametrize('tail,missing_field', [
    (event(101, 'chi', seat=1, tile='6t'), 'tiles'),
    (event(101, 'gang', seat=1, tile='6t'), 'detail_kind'),
    (event(101, 'timeout', seat=1), 'detail_kind'),
])
async def test_incomplete_known_old_tail_is_not_reported_complete(transport, clock, tail, missing_field):
    closure = await seal_old_tail(transport, clock, tail)
    public = closure['public_history'][0]
    assert public['kind'] == tail['type']
    assert 'event_detail_incomplete:' + tail['type'] in closure['closure_issues']
    if missing_field == 'tiles':
        assert public['tiles'] == ['6t']  # 保留收到的事实，不能拼造三张吃牌组合
    else:
        assert public.get(missing_field) is None  # 不给缺省补一个假定官方类型
    assert closure['history_complete'] is False


async def test_other_players_private_draw_is_masked_and_marks_old_tail_incomplete(transport, clock):
    closure = await seal_old_tail(transport, clock, event(101, 'tile_drawn', seat=1, tile='9b'))
    public = closure['public_history'][0]
    assert public['kind'] == 'tile_drawn' and public['seat'] == 1
    assert 'unexpected_other_draw' in closure['closure_issues']
    assert public['tiles'] == []  # 有摸牌这一事实可保存，他家牌值不可进入公开历史
    assert closure['history_complete'] is False


async def test_hand_closure_without_round_end_keeps_unknown_tail_explicit(transport, clock):
    audit = FakeAuditSink()
    first = snapshot(100, turn=2, drawn='7w')
    first['snapshot']['dealer'] = 2
    first['snapshot']['melds'] = [[], [], [], []]
    next_hand = snapshot(102, round_no=2, turn=2, drawn='8w')
    script(transport, [(0, first), (100, next_hand)])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        assert (await session.next_item()).observation.history_complete
        assert (await session.next_item()).observation.round_no == 2
        closure = next(r.payload for r in audit.records
                       if r.payload.get('history_closure') == 'round_changed')
        assert closure['history_through_seq'] == 100
        assert closure['missing_ranges'] == []  # 已知旧水位内连续，不代表单局末尾已收到
        assert closure['public_history'] == []
        assert closure['history_complete'] is False
        assert any('round_ended' in issue for issue in closure['closure_issues'])
    finally:
        await session.aclose('closure_validation')


async def test_finished_without_terminal_events_keeps_both_tail_reasons(transport, clock):
    from hangma_bot.application.contracts import GameFinished

    audit = FakeAuditSink()
    first = snapshot(100, turn=2, drawn='7w')
    first['snapshot']['dealer'] = 2
    first['snapshot']['melds'] = [[], [], [], []]
    final = snapshot(102, phase='finished')
    final['finished'] = True
    script(transport, [(0, first), (100, final), (100, final)])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        assert (await session.next_item()).observation.history_complete
        assert isinstance(await session.next_item(), GameFinished)
        closure = next(r.payload for r in audit.records
                       if r.payload.get('history_closure') == 'game_finished')
        assert closure['public_history'] == []  # 不从最终积分捏造round/game终局事件
        assert closure['history_complete'] is False
        assert any('round_ended' in issue for issue in closure['closure_issues'])
        assert any('game_ended' in issue for issue in closure['closure_issues'])
    finally:
        await session.aclose('closure_validation')
