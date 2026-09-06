

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
    script(transport, [(0, first), (100, final)])
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
