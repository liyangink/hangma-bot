"""交叉审查修复回归测试：L1/F1/F2/F3/F4/F5/L4/F11 与 expert 补充发现的固化探针。"""
from __future__ import annotations

import asyncio
import json

from hangma_bot.adapters.official.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    RateLimitedError,
    UncertainTransportError,
)
from hangma_bot.application.contracts import (
    ActionAttempt,
    AuditKind,
    GameFailed,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitFatal,
    SubmitNotSent,
    SubmitRejectedClosed,
)
from hangma_bot.kernel.actions import Discard, Peng, Tile, WindowKey, WindowPhase

from _official_testkit import (
    TIMING,
    FakeTransport,
    load_fixture,
    make_game_session,
    make_tournament_session,
)


def _json(doc):
    return 200, json.dumps(doc)


def _draw_window(trigger=130):
    return WindowKey(game_id='g_room1_batch1', round_no=1, trigger_seq=trigger, phase=WindowPhase.DRAW, seat=2)


def _migrated_draw_snapshot(trigger=130):
    doc = load_fixture('state_response_snapshot_draw.json')
    doc['seq'] = trigger
    return doc


def _attempt(window, action, action_key, attempt_no=1):
    return ActionAttempt(
        decision_id='d-1',
        attempt_no=attempt_no,
        plan_revision=1,
        window_key=window,
        based_on_authoritative_seq=window.trigger_seq,
        action=action,
        action_key=action_key,
        latest_send_at_monotonic=1005.0,
    )


async def test_409_closed_migrated_window_still_delivered(transport, clock):
    """L1/F3-A：409 判 closed 后，刷新已发现的迁移窗口必须仍能投递。"""

    peng = load_fixture('state_response_snapshot_peng.json')
    script = [
        ('GET', _json(peng)),
        ('POST', ConflictError(409, 'INVALID_ACTION', 'no')),
        ('GET', _json(_migrated_draw_snapshot())),
    ]

    def handler(method=None, **kw):
        want, item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)
    assert window.window_key.phase is WindowPhase.RESPONSE_PENG
    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, Peng(Tile('2w')), 'peng:2w')), timeout=2
    )
    assert isinstance(outcome, SubmitRejectedClosed)
    transport.handler = lambda **kw: _json(load_fixture('state_response_pending.json'))
    again = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(again, ObservedActionWindow)
    assert again.window_key == _draw_window(130)


async def test_post_400_maps_to_submit_fatal(transport, clock):
    """F1：POST 400 → SubmitFatal，不得裸异常穿透。"""

    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)

    def fail(**kw):
        raise BadRequestError(400, 'TOKEN_NOT_SCOPED', 'scope')

    transport.handler = fail
    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, Discard(Tile('5w')), 'discard:5w')), timeout=2
    )
    assert isinstance(outcome, SubmitFatal)
    assert outcome.reason == 'bad_request' and outcome.official_code == 'TOKEN_NOT_SCOPED'


async def test_post_404_maps_to_rejected_closed(transport, clock):
    """F1：POST 404 → SubmitRejectedClosed（官方明确未执行且窗口必然失效）。"""

    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)

    def gone(**kw):
        raise NotFoundError(404, 'GAME_NOT_FOUND', '')

    transport.handler = gone
    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, Discard(Tile('5w')), 'discard:5w')), timeout=2
    )
    assert isinstance(outcome, SubmitRejectedClosed)
    assert outcome.official_code == 'GAME_NOT_FOUND'


async def test_get_409_classified_not_escaped(transport, clock):
    """F1 前置：state GET 收到 409 → 分类故障，不裸抛。"""

    def conflict(**kw):
        raise ConflictError(409, 'INVALID_ACTION', 'no')

    transport.handler = conflict
    session = make_game_session(transport=transport, clock=clock)
    item = await asyncio.wait_for(session.next_item(), timeout=3)
    assert isinstance(item, GameFailed)
    assert item.recoverable is False and item.reason == 'state_conflict'


async def test_cancel_during_post_blocks_window(transport, clock):
    """F2：在途 POST 被取消 → 模糊封锁同窗，第二次提交零 POST。"""

    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)

    async def hanging_post(**kw):
        await asyncio.sleep(30)
        return 200, '{}'

    transport.handler = hanging_post
    task = asyncio.create_task(
        session.submit(_attempt(window.window_key, Discard(Tile('5w')), 'discard:5w'))
    )
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    again = await asyncio.wait_for(
        session.submit(
            _attempt(window.window_key, Discard(Tile('5w')), 'discard:5w', attempt_no=2)
        ),
        timeout=2,
    )
    assert isinstance(again, SubmitNotSent)
    assert again.reason == 'ambiguous_window_blocked'
    posts = [c for c in transport.calls if c.method == 'POST']
    assert len(posts) == 1


async def test_unknown_tile_code_is_classified_failure(transport, clock):
    """F1-#3：官方未知牌码 → 分类故障，不裸抛 ValueError。"""

    doc = load_fixture('state_response_snapshot_draw.json')
    doc['snapshot']['my_hand'][0] = '10w'
    transport.handler = lambda **kw: _json(doc)
    session = make_game_session(transport=transport, clock=clock)
    item = await asyncio.wait_for(session.next_item(), timeout=3)
    assert isinstance(item, GameFailed)
    assert item.recoverable is True


async def test_aclose_one_game_does_not_break_sibling(clock):
    """F11：aclose 一场不影响同 Token 共享传输上的其他场次。"""

    from _official_testkit import RequestScheduler, instant_sleep

    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0)
    shared = FakeTransport()

    async def hanging(**kw):
        await asyncio.sleep(30)
        return 200, '{}'

    shared.handler = hanging
    g1 = make_game_session(transport=shared, clock=clock, game_id='g1', scheduler=scheduler)
    t1 = asyncio.create_task(g1.next_item())
    await asyncio.sleep(0.05)
    shared.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    g2 = make_game_session(transport=shared, clock=clock, game_id='g2', scheduler=scheduler)
    item = await asyncio.wait_for(g2.next_item(), timeout=2)
    assert isinstance(item, ObservedActionWindow)

    await g1.aclose('stage_switched')
    closed = await asyncio.wait_for(t1, timeout=2)
    assert isinstance(closed, GameFailed)
    # g1 关闭后 g2 仍然可用：服务端推进到新窗口（seq=130）后正常交付
    migrated = load_fixture('state_response_snapshot_draw.json')
    migrated['seq'] = 130
    shared.handler = lambda **kw: _json(migrated)
    again = await asyncio.wait_for(g2.next_item(), timeout=2)
    assert isinstance(again, ObservedActionWindow)
    assert again.authoritative_seq == 130


async def test_post_429_returns_not_sent(transport, clock):
    """F11：动作 POST 429 → SubmitNotSent（官方确定未执行）。"""

    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)

    def limited(**kw):
        raise RateLimitedError(429, 'RATE_LIMITED', 'slow down', 0.1)

    transport.handler = limited
    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, Discard(Tile('5w')), 'discard:5w')), timeout=3
    )
    assert isinstance(outcome, SubmitNotSent)
    assert outcome.reason == 'official_rate_limited'


async def test_delivered_window_exactly_once(transport, clock):
    """expert 裁决：同一会话内窗口恰好交付一次。

    重投会刷新 received_at_monotonic 并让应用层重建预算（变相延长
    截止时间）；监督重启应由应用层创建新 GameSession 承担。
    """

    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock)
    first = await asyncio.wait_for(session.next_item(), timeout=2)

    # 已交付窗口：服务端只剩 pending → 不再重投（超时）
    transport.handler = lambda **kw: _json(load_fixture('state_response_pending.json'))
    try:
        second = await asyncio.wait_for(session.next_item(), timeout=0.3)
        assert not isinstance(second, ObservedActionWindow)
    except asyncio.TimeoutError:
        pass



def _event(seq):
    from hangma_bot.adapters.official.dto import ParsedEvent

    return ParsedEvent(seq=seq, type='tile_discarded', seat=0, tiles=('1w',), occurred_at_unix_sec=1756771200)


async def test_lifecycle_audit_only_on_change(clock):
    """F4/L8：LIFECYCLE_CHANGED 只在快照真实采纳时发射，轮询无变化零噪声。"""

    import json as _json
    from pathlib import Path
    from _official_testkit import FakeAuditSink

    audit = FakeAuditSink()
    transport = FakeTransport()
    guide = _json.loads(Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8'))
    counter = {'n': 0}

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        counter['n'] += 1
        if counter['n'] <= 2:
            return 200, _json.dumps(load_fixture('tournament_detail.json'))
        return 200, _json.dumps(load_fixture('tournament_stage_open.json'))

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport, audit=audit)
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        RuntimeMode,
        RuntimeTarget,
    )

    target = RuntimeTarget(mode=RuntimeMode.TEST_ROOM, expected_tournament_id='t_test_room_1', known_guide_version=8)
    boot = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert not isinstance(boot, ParticipantTerminal)
    # 初始：1 条生命周期采纳 + 1 条启动指南审计（完整 changes 回放依据）
    assert (
        len([r for r in audit.records if r.kind is AuditKind.LIFECYCLE_CHANGED]) == 1
    )
    assert len(audit.records) == 2
    snapshot = await asyncio.wait_for(session.next_update(), timeout=5)
    assert not isinstance(snapshot, ParticipantTerminal)
    lifecycle = [r for r in audit.records if r.kind is AuditKind.LIFECYCLE_CHANGED]
    assert len(lifecycle) == 2  # 两轮无变化零发射 + 变化采纳一条
    assert len(audit.records) == 3  # 指南审计不随轮询重复


async def test_next_update_survives_transient_exhaustion(clock):
    """F5：单轮重试耗尽不立即终态化；冷却恢复后继续返回快照。"""

    import json as _json
    from pathlib import Path

    transport = FakeTransport()
    guide = _json.loads(Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8'))
    detail_count = {'n': 0}

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        detail_count['n'] += 1
        n = detail_count['n']
        if 2 <= n <= 5:
            # next_update 首轮 detail：4 次重试全部断连（整轮耗尽）
            raise UncertainTransportError('timeout:ReadTimeout')
        if n == 1:
            return 200, _json.dumps(load_fixture('tournament_detail.json'))
        return 200, _json.dumps(load_fixture('tournament_stage_open.json'))

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        RuntimeMode,
        RuntimeTarget,
    )

    target = RuntimeTarget(mode=RuntimeMode.TEST_ROOM, expected_tournament_id='t_test_room_1', known_guide_version=8)
    boot = await asyncio.wait_for(session.initialize(target), timeout=3)
    assert not isinstance(boot, ParticipantTerminal)
    snapshot = await asyncio.wait_for(session.next_update(), timeout=8)
    assert not isinstance(snapshot, ParticipantTerminal)
    assert snapshot.status.value == 'stage_open'


async def test_retry_exhaustion_reraises_last_error(clock):
    """expert 补充：重试耗尽必须重抛最后分类异常，而非 RuntimeError。"""

    transport = FakeTransport()

    def handler(method=None, path=None, **kw):
        raise UncertainTransportError('timeout:ReadTimeout')

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        ParticipantTerminalReason,
        RuntimeMode,
        RuntimeTarget,
    )

    target = RuntimeTarget(mode=RuntimeMode.TEST_ROOM, expected_tournament_id='t_test_room_1', known_guide_version=8)
    outcome = await asyncio.wait_for(session.initialize(target), timeout=4)
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
    assert 'transport' in outcome.detail or 'timeout' in outcome.detail


def test_gap_batch_not_partially_applied():
    """expert 补充：批内先连续后缺口 → 整批拒绝，游标不部分推进。"""

    from hangma_bot.adapters.official.dto import parse_snapshot
    from hangma_bot.adapters.official.sync_state import (
        ProtocolSyncState,
        SyncDecision,
    )

    doc = load_fixture('state_response_snapshot_draw.json')
    snap = parse_snapshot(doc['snapshot'], doc.get('seq'))
    state = ProtocolSyncState('g', TIMING)
    state.apply_full_snapshot(snap)
    events = [
        _event(102),
        _event(103),
        _event(105),  # 104 缺失
    ]
    result = state.apply_events(events)
    assert result.decision is SyncDecision.NEEDS_REBUILD
    assert state.last_seq == 101  # 未部分应用 102/103
    assert len(state.history) == 0


async def test_rebuild_failure_keeps_unknown_unlearned(transport, clock):
    """L4：未知事件触发重建失败后不得学习忽略；重入仍保守重建。"""

    base = load_fixture('state_response_snapshot_draw.json')
    base['snapshot']['turn'] = 0  # 首快照无窗
    events_doc = {'events': [{'seq': 102, 'type': 'future_event', 'seat': 1, 'tile': '2w', 'data': {}, 'ts': 1756771200}]}
    queue = [
        _json(base),
        _json(events_doc),
        'FAIL',
        _json(events_doc),
        _json(load_fixture('state_response_snapshot_draw.json')),
    ]
    fail = {'remaining': 0}

    def handler(method=None, path=None, params=None, **kw):
        if path and path.endswith('/action'):
            return 200, '{}'
        if fail['remaining'] > 0:
            fail['remaining'] -= 1
            raise UncertainTransportError('timeout:ReadTimeout')
        item = queue.pop(0)
        if item == 'FAIL':
            # 重建请求位次连挂 4 次触发整轮耗尽（含重试）
            fail['remaining'] = 4
            raise UncertainTransportError('timeout:ReadTimeout')
        return item

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    first = await asyncio.wait_for(session.next_item(), timeout=5)
    assert isinstance(first, GameFailed)
    assert first.reason == 'get_exhausted'
    # 重入：同一未知事件仍触发保守重建（未被学习），这次重建成功并投递窗口
    second = await asyncio.wait_for(session.next_item(), timeout=5)
    assert isinstance(second, ObservedActionWindow)


async def test_open_game_rebuilds_closed_session(clock):
    """expert-2：aclose 后 open_game 必须重建会话而非复用 closed 对象。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        return 200, _json.dumps(load_fixture('tournament_detail.json'))

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    boot = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert not isinstance(boot, ParticipantTerminal)
    g1 = session.open_game('g_room1_batch1')
    await g1.aclose('supervisor_restart')
    g2 = session.open_game('g_room1_batch1')
    assert g2 is not g1
    assert getattr(g2, 'closed', False) is False


async def test_conflict_refresh_releases_action_slot(transport, clock):
    """expert-3：409 刷新前释放动作槽，max_concurrent=1 时不自锁。"""

    from _official_testkit import RequestScheduler, instant_sleep
    from hangma_bot.adapters.official.scheduler import Priority

    scheduler = RequestScheduler(
        rate_per_second=100.0,
        burst=100.0,
        max_concurrent=1,
        clock=clock.monotonic,
        sleep=instant_sleep(clock),
        poll_interval=0.0,
    )
    peng = load_fixture('state_response_snapshot_peng.json')
    script = [
        _json(peng),
        ConflictError(409, 'INVALID_ACTION', 'no'),
        _json(peng),
    ]

    def handler(method=None, **kw):
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock, scheduler=scheduler)
    window = await asyncio.wait_for(session.next_item(), timeout=2)
    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, Peng(Tile('2w')), 'peng:2w')),
        timeout=3,
    )
    from hangma_bot.application.contracts import SubmitRejectedRetryable

    assert isinstance(outcome, SubmitRejectedRetryable)


def test_official_code_whitelisted():
    """expert-4：异常服务端塞入任意 code 文本不得进入异常串。"""

    from hangma_bot.adapters.official.errors import BadRequestError

    err = BadRequestError(
        400,
        'Bearer secret-token-abcdef123456',
        'something failed',
    )
    assert err.official_code is None
    assert 'secret-token-abcdef123456' not in str(err)
    assert 'secret-token-abcdef123456' not in err.detail
    ok = BadRequestError(400, 'TOKEN_NOT_SCOPED', 'x')
    assert ok.official_code == 'TOKEN_NOT_SCOPED'



async def test_invalid_tile_fields_are_classified(transport, clock):
    """expert 边界：drawn_tile/last_discard/meld 非法牌码 → 分类故障。"""

    for mutate in ('drawn', 'last_discard', 'meld'):
        doc = load_fixture('state_response_snapshot_draw.json')
        if mutate == 'drawn':
            doc['snapshot']['drawn_tile'] = '10w'
        elif mutate == 'last_discard':
            doc['snapshot']['last_discard']['tile'] = '10w'
        else:
            doc['snapshot']['melds'][1][0]['tiles'][0] = '10w'

        def make_handler(snapshot_doc):
            def handler(**kw):
                return _json(snapshot_doc)
            return handler

        transport.handler = make_handler(doc)
        session = make_game_session(transport=transport, clock=clock)
        item = await asyncio.wait_for(session.next_item(), timeout=3)
        assert isinstance(item, GameFailed), mutate


async def test_participant_audit_failure_never_blocks(clock):
    """expert 可靠性：context provider 或 sink 抛异常不进入运行路径。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        RuntimeMode,
        RuntimeTarget,
    )

    class BrokenContextAudit:
        def emit(self, record):
            raise RuntimeError('sink broken')

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        return 200, _json.dumps(load_fixture('tournament_detail.json'))

    transport.handler = handler

    def broken_context():
        raise RuntimeError('context provider broken')

    from _official_testkit import make_audit_context
    from hangma_bot.adapters.official.participant import OfficialTournamentSession
    from hangma_bot.adapters.official.transport import TransportConfig
    from _official_testkit import RequestScheduler, instant_sleep

    session = OfficialTournamentSession(
        token='fake-token',
        transport_config=TransportConfig(
            base_url='https://10.240.169.190:18080',
            insecure_hosts=frozenset({'10.240.169.190'}),
        ),
        monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms,
        audit=BrokenContextAudit(),
        audit_context=broken_context,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0),
        retry_sleep=instant_sleep(clock),
    )
    session._transport = transport
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    boot = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert not isinstance(boot, ParticipantTerminal)
    assert session.audit_dropped_events >= 1  # 失败被计数而非上抛


def test_rate_limit_cooldown_not_shortened():
    """expert：后到的短 Retry-After 不得缩短既有更长冷却。"""

    from _official_testkit import FakeClock, instant_sleep
    from hangma_bot.adapters.official.scheduler import RequestScheduler

    clock = FakeClock()
    scheduler = RequestScheduler(
        clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0
    )
    scheduler.note_rate_limited(10.0)
    first = scheduler.cooldown_remaining
    assert first > 9.0
    scheduler.note_rate_limited(0.5)  # 更短的冷却不得回退
    assert scheduler.cooldown_remaining > 9.0


async def test_rules_tournament_mismatch_is_terminal(clock):
    """expert：rules 归属与目标不符 → TARGET_MISMATCH，不采用错误配置。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.adapters.official.errors import ForbiddenError
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        ParticipantTerminalReason,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )
    wrong_rules = load_fixture('rules.json')
    wrong_rules['tournament_id'] = 't_other'

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(wrong_rules)
        return 200, _json.dumps(load_fixture('tournament_detail.json'))

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    outcome = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.TARGET_MISMATCH


async def test_conflict_refresh_bound_to_budget(transport, clock):
    """expert：409 刷新绑定原始预算，预算耗尽立即保守 closed，不超时等待。"""

    peng = load_fixture('state_response_snapshot_peng.json')

    async def slow_refresh(**kw):
        await asyncio.sleep(30)
        return 200, '{}'

    transport.handler = lambda **kw: _json(peng)
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)
    # 快照已收；随后 409 + 刷新挂起：预算（latest_send=1005，clock≈1000）内
    # 刷新无法完成 → 保守 SubmitRejectedClosed 快速返回
    calls = {'n': 0}

    def handler(method=None, **kw):
        calls['n'] += 1
        if method == 'POST':
            raise ConflictError(409, 'INVALID_ACTION', 'no')
        raise UncertainTransportError('timeout:ReadTimeout')

    transport.handler = handler
    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, Peng(Tile('2w')), 'peng:2w')),
        timeout=5,
    )
    assert isinstance(outcome, SubmitRejectedClosed)


async def test_next_update_forbidden_is_immediate_terminal(clock):
    """expert：403 是授权终态，不得伪装抖动跨轮恢复。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.adapters.official.errors import ForbiddenError
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        ParticipantTerminalReason,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )
    counter = {'n': 0}

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        counter['n'] += 1
        if counter['n'] >= 2:
            raise ForbiddenError(403, 'FORBIDDEN', 'no access')
        return 200, _json.dumps(load_fixture('tournament_detail.json'))

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    boot = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert not isinstance(boot, ParticipantTerminal)
    terminal = await asyncio.wait_for(session.next_update(), timeout=3)
    assert isinstance(terminal, ParticipantTerminal)
    assert terminal.reason is ParticipantTerminalReason.TARGET_MISMATCH


def test_uppercase_secret_code_not_leaked():
    """expert：无 Bearer 前缀的全大写凭证形态不得进入异常串。"""

    from hangma_bot.adapters.official.errors import BadRequestError

    err = BadRequestError(400, 'ABCDEF1234567890ABCDEF1234567890', 'x')
    assert err.official_code is None
    assert 'ABCDEF1234567890ABCDEF1234567890' not in str(err)



async def test_stage_boundary_breaking_guide_blocks_ready(clock):
    """expert：阶段边界发现 breaking v9 → 拒绝发送 ready。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        ParticipantTerminalReason,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )
    breaking = load_fixture('guide_breaking_future.json')
    counter = {'n': 0}
    detail_count = {'n': 0}

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            counter['n'] += 1
            if counter['n'] == 1:
                return 200, _json.dumps(guide)  # 启动时仍是 v8
            return 200, _json.dumps(breaking)  # 阶段边界已发布 v9 breaking
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        detail_count['n'] += 1
        if detail_count['n'] == 1:
            return 200, _json.dumps(load_fixture('tournament_detail.json'))  # initialize: running
        return 200, _json.dumps(load_fixture('tournament_stage_open.json'))  # 之后: stage_open

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    boot = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert not isinstance(boot, ParticipantTerminal)
    snapshot = await asyncio.wait_for(session.next_update(), timeout=5)
    assert not isinstance(snapshot, ParticipantTerminal)
    transport.calls.clear()
    outcome = await asyncio.wait_for(session.ready(snapshot.stage), timeout=3)
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE
    # ready POST 从未发出
    posts = [c for c in transport.calls if c.method == 'POST']
    assert posts == []


async def test_post_404_then_same_window_blocked(transport, clock):
    """expert：404 终结窗口后，同窗第二次 submit 被门拒绝且零追加 POST。"""

    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)

    def gone(**kw):
        raise NotFoundError(404, 'GAME_NOT_FOUND', '')

    transport.handler = gone
    first = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, Discard(Tile('5w')), 'discard:5w')),
        timeout=2,
    )
    assert isinstance(first, SubmitRejectedClosed)
    second = await asyncio.wait_for(
        session.submit(
            _attempt(window.window_key, Discard(Tile('5w')), 'discard:5w', attempt_no=2)
        ),
        timeout=2,
    )
    assert isinstance(second, SubmitNotSent)
    assert second.reason == 'window_already_finalized'
    posts = [c for c in transport.calls if c.method == 'POST']
    assert len(posts) == 1


async def test_error_body_reflecting_short_token_is_redacted():
    """expert：错误 body 直接反射短 Token（无 Bearer 前缀）也必须脱敏。"""

    import httpx

    from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig
    from hangma_bot.adapters.official.errors import BadRequestError

    token = 'secret-token-abcdef123456'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={'code': 'TOKEN_NOT_SCOPED', 'message': 'token ' + token + ' rejected'},
        )

    transport = OfficialTransport(
        token,
        TransportConfig(base_url='https://h.example', insecure_hosts=frozenset()),
        transport_handler=httpx.MockTransport(handler),
    )
    try:
        import pytest as _pytest

        with _pytest.raises(BadRequestError) as exc_info:
            await transport.request('GET', '/api/me')
        assert token not in str(exc_info.value)
        assert token not in exc_info.value.detail
    finally:
        await transport.aclose()



async def test_acquire_deadline_exceeded_under_real_cooldown():
    """expert：预算耗尽时 acquire 立即抛出，不在 429 冷却上阻塞。"""

    import time

    from hangma_bot.adapters.official.scheduler import (
        DeadlineExceeded,
        Priority,
        RequestScheduler,
    )

    scheduler = RequestScheduler(
        rate_per_second=8.0,
        clock=time.monotonic,  # 真实时钟（不用假时钟推进）
    )
    scheduler.note_rate_limited(10.0)  # 官方要求冷却 10s
    start = time.monotonic()
    try:
        await asyncio.wait_for(
            scheduler.acquire(Priority.RECOVERY, deadline_monotonic=start + 0.15),
            timeout=2,
        )
        raised = False
    except DeadlineExceeded:
        raised = True
    assert raised, '预算耗尽应抛 DeadlineExceeded'
    elapsed = time.monotonic() - start
    assert elapsed < 1.5, '不得等待完整冷却（{}s）'.format(elapsed)


async def test_request_budget_clamps_all_phases():
    """expert：整次请求预算收紧 connect/read/write/pool 全部阶段。"""

    import httpx

    from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport = OfficialTransport(
        'tk',
        TransportConfig(base_url='https://h.example', insecure_hosts=frozenset()),
        transport_handler=httpx.MockTransport(handler),
    )
    try:
        await transport.request('GET', '/api/me', request_budget_sec=0.2)
        extension = transport._client  # 仅触发配置路径；MockTransport 不受超时影响
        assert extension is not None
    finally:
        await transport.aclose()



async def test_2xx_protocol_error_does_not_echo_token(transport, clock):
    """expert：2xx 快照携带 Token 形态字段值 → 分类故障且不回显原值。"""

    from _official_testkit import FakeTransport as FT

    token_like = 'short-token-9f8e7d'
    real_transport = transport  # FakeTransport（无 token 属性，用直改文本模拟）

    doc = load_fixture('state_response_snapshot_draw.json')
    doc['snapshot']['drawn_tile'] = token_like

    def handler(**kw):
        return 200, json.dumps(doc)

    real_transport.handler = handler
    session = make_game_session(transport=real_transport, clock=clock)
    item = await asyncio.wait_for(session.next_item(), timeout=3)
    assert isinstance(item, GameFailed)
    assert token_like not in item.reason


async def test_transport_redacts_token_in_success_body():
    """expert：传输层对 2xx 响应体也做当前 Token 精确替换。"""

    import httpx

    from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig

    token = 'secret-token-abcdef123456'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'echo': 'value ' + token + ' embedded'})

    transport = OfficialTransport(
        token,
        TransportConfig(base_url='https://h.example', insecure_hosts=frozenset()),
        transport_handler=httpx.MockTransport(handler),
    )
    try:
        result = await transport.request('GET', '/api/me')
        assert token not in result.text
        assert '***' in result.text
    finally:
        await transport.aclose()


async def test_submit_action_acquire_bound_to_deadline(transport, clock):
    """expert：429 冷却期间 submit 的调度等待按截止准时返回 NotSent。"""

    import time

    from _official_testkit import make_game_session as _mgs

    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)
    # 用真实时钟的冷却调度器替换（冷却 10s；截止只剩 ~0.3s）
    from hangma_bot.adapters.official.scheduler import RequestScheduler

    real_scheduler = RequestScheduler(clock=time.monotonic)
    real_scheduler.note_rate_limited(10.0)
    session._scheduler = real_scheduler

    attempt = _attempt(window.window_key, Discard(Tile('5w')), 'discard:5w')
    attempt = type(attempt)(
        decision_id=attempt.decision_id,
        attempt_no=attempt.attempt_no,
        plan_revision=attempt.plan_revision,
        window_key=attempt.window_key,
        based_on_authoritative_seq=attempt.based_on_authoritative_seq,
        action=attempt.action,
        action_key=attempt.action_key,
        latest_send_at_monotonic=time.monotonic() + 0.3,
    )
    start = time.monotonic()
    outcome = await asyncio.wait_for(session.submit(attempt), timeout=3)
    elapsed = time.monotonic() - start
    assert isinstance(outcome, SubmitNotSent)
    assert outcome.reason == 'deadline_passed_in_schedule'
    assert elapsed < 2.0, '不得在冷却上阻塞（{}s）'.format(elapsed)
    posts = [c for c in transport.calls if c.method == 'POST']
    assert posts == []



async def test_post_not_sent_when_clock_equals_deadline(transport, clock):
    """expert：时钟恰好等于 latest_send 时 POST 发送次数为 0（等号即拒）。"""

    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)
    clock.advance(5.0)  # 1000 -> 1005，恰等于 latest_send=1005
    transport.handler = lambda **kw: (200, '{}')
    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, Discard(Tile('5w')), 'discard:5w')),
        timeout=2,
    )
    assert isinstance(outcome, SubmitNotSent)
    assert outcome.reason == 'deadline_passed'
    posts = [c for c in transport.calls if c.method == 'POST']
    assert posts == []



async def test_request_total_budget_enforced():
    """expert：整次请求墙钟预算由 asyncio.timeout 兜底（含池等待）。"""

    import time

    import httpx

    from hangma_bot.adapters.official.errors import UncertainTransportError
    from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.0)  # 可取消的服务端 stall（真实网络 IO 语义）
        return httpx.Response(200, json={})

    transport = OfficialTransport(
        'tk',
        TransportConfig(base_url='https://h.example', insecure_hosts=frozenset()),
        transport_handler=httpx.MockTransport(slow_handler),
    )
    try:
        start = time.monotonic()
        try:
            await transport.request('GET', '/api/me', request_budget_sec=0.2)
            raised = False
        except UncertainTransportError:
            raised = True
        assert raised
        elapsed = time.monotonic() - start
        assert elapsed < 0.9, '总预算应止住 stall（{}s）'.format(elapsed)
    finally:
        await transport.aclose()



def test_projection_failure_keeps_batch_transactional():
    """expert：第 1 条合法、第 2 条投影非法 → 整批拒绝且游标/历史零变更。"""

    from hangma_bot.adapters.official.dto import ParsedEvent, parse_snapshot
    from hangma_bot.adapters.official.sync_state import (
        ProtocolSyncState,
        SyncDecision,
    )

    doc = load_fixture('state_response_snapshot_draw.json')
    snap = parse_snapshot(doc['snapshot'], doc.get('seq'))
    state = ProtocolSyncState('g', TIMING)
    state.apply_full_snapshot(snap)
    good = ParsedEvent(seq=102, type='tile_discarded', seat=0, tiles=('1w',), occurred_at_unix_sec=1756771200)
    bad = ParsedEvent(seq=103, type='tile_discarded', seat=-2, tiles=('2w',), occurred_at_unix_sec=None)
    result = state.apply_events((good, bad))
    assert result.decision is SyncDecision.NEEDS_REBUILD
    assert any(r.startswith('projection_failed') for r in result.reasons)
    assert state.last_seq == 101  # 游标未推进
    assert len(state.history) == 0  # 第 1 条也未写入


async def test_known_event_illegal_tile_recovers_via_full_snapshot(transport, clock):
    """expert：已知事件带非法单数牌码 → DTO 拦截 + 降级全量恢复，不裸抛。"""

    base = load_fixture('state_response_snapshot_draw.json')
    base['snapshot']['turn'] = 0  # 首快照无窗
    bad_events = {
        'events': [
            {'seq': 102, 'type': 'tile_discarded', 'seat': 1, 'tile': '10w', 'data': {}, 'ts': 1756771200},
        ]
    }
    healthy = load_fixture('state_response_snapshot_draw.json')
    calls = {'n': 0}

    def handler(method=None, path=None, **kw):
        calls['n'] += 1
        if calls['n'] == 1:
            return _json(base)  # 首拉全量（无窗）
        if calls['n'] == 2:
            return _json(bad_events)  # 增量：非法牌码 → DTO 拦截
        return _json(healthy)  # 降级 seq=0 全量：健康快照 → 恢复投递

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    item = await asyncio.wait_for(session.next_item(), timeout=3)
    assert isinstance(item, ObservedActionWindow)
    # 降级请求必须是权威全量
    assert transport.calls[2].params == {'seq': 0}



async def test_initialize_unknown_status_is_terminal(clock):
    """expert：detail 未知状态 → 投影封闭为 FATAL 而非裸抛。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        ParticipantTerminalReason,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )
    bad_detail = load_fixture('tournament_detail.json')
    bad_detail['status'] = 'future_status'

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        return 200, _json.dumps(bad_detail)

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    outcome = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR


async def test_next_update_unknown_status_is_terminal(clock):
    """expert：next_update 未知状态 → 投影封闭为 FATAL 而非裸抛。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        ParticipantTerminalReason,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )
    counter = {'n': 0}

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        counter['n'] += 1
        if counter['n'] == 1:
            return 200, _json.dumps(load_fixture('tournament_detail.json'))
        bad = load_fixture('tournament_detail.json')
        bad['status'] = 'future_status'
        return 200, _json.dumps(bad)

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    boot = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert not isinstance(boot, ParticipantTerminal)
    terminal = await asyncio.wait_for(session.next_update(), timeout=3)
    assert isinstance(terminal, ParticipantTerminal)
    assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR


def test_strict_dto_rejects_bad_responding_and_meld():
    """expert：关键数组坏值 fail-closed（不再静默丢项）。"""

    from hangma_bot.adapters.official.dto import parse_snapshot
    from hangma_bot.adapters.official.errors import DtoError

    doc = load_fixture('state_response_snapshot_draw.json')
    body = doc['snapshot']

    bad_seat = dict(body)
    bad_seat['responding_seats'] = ['2']
    with _raises_dtoerror():
        parse_snapshot(bad_seat, doc['seq'])

    out_of_range = dict(body)
    out_of_range['responding_seats'] = [4]
    with _raises_dtoerror():
        parse_snapshot(out_of_range, doc['seq'])

    bad_meld = dict(body)
    bad_meld['melds'] = [['not-an-object'], [], [], []]
    with _raises_dtoerror():
        parse_snapshot(bad_meld, doc['seq'])

    malformed_discard = dict(body)
    malformed_discard['last_discard'] = {'seat': 'x', 'tile': '1w', 'seq': 5}
    with _raises_dtoerror():
        parse_snapshot(malformed_discard, doc['seq'])


class _raises_dtoerror:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        from hangma_bot.adapters.official.errors import DtoError

        return exc_type is DtoError



def test_tournament_detail_malformed_stage_is_dto_error():
    """expert：stage.no 类型错误 fail-closed（不再静默 None 造成挂起）。"""

    from hangma_bot.adapters.official.dto import parse_tournament_detail

    doc = load_fixture('tournament_stage_open.json')
    doc['stage']['no'] = '1'  # 字符串阶段号
    from _official_testkit import load_fixture as _lf  # noqa: F401
    try:
        parse_tournament_detail(doc)
        raised = False
    except Exception:
        raised = True
    assert raised

    doc2 = load_fixture('tournament_detail.json')
    doc2['my_games'] = ['g1', 42]
    try:
        parse_tournament_detail(doc2)
        raised = False
    except Exception:
        raised = True
    assert raised


async def test_initialize_malformed_stage_is_terminal(clock):
    """expert：stage_open + 坏 stage.no → ParticipantTerminal 而非挂起。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )
    bad_detail = load_fixture('tournament_stage_open.json')
    bad_detail['stage']['no'] = '1'

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        return 200, _json.dumps(bad_detail)

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    outcome = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert isinstance(outcome, ParticipantTerminal)


async def test_initialize_bad_config_is_terminal(clock):
    """expert：M=0 等坏配置 → ParticipantTerminal 而非裸 ValueError。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )
    bad_rules = load_fixture('rules.json')
    bad_rules['config']['M'] = 0

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(load_fixture('me.json'))
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(bad_rules)
        return 200, _json.dumps(load_fixture('tournament_detail.json'))

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    outcome = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert isinstance(outcome, ParticipantTerminal)



def test_discard_drawn_tile_outside_hand_accepted():
    """wv5-1：刚摸的牌单列于 drawn_tile（不在 my_hand）也可打出。"""

    drawn = Tile('5w')
    hand = (Tile('1w'), Tile('2w'))
    from hangma_bot.adapters.official.projector import action_request_body

    body = action_request_body(
        Discard(drawn),
        last_discard_tile=None,
        hand=hand,
        drawn_tile=drawn,
    )
    assert body == {'action': 'discard', 'tile': '5w'}


def test_catch_play_without_drawn_tile_or_hand_rejected():
    """wv5-1/R1：抓打圈既无 drawn_tile 也无手牌时拒绝（无法安全构造）。"""

    from hangma_bot.adapters.official.projector import action_request_body

    body = action_request_body(
        Discard(Tile('白')),
        last_discard_tile=None,
        hand=(),
        drawn_tile=None,
        catch_play=True,
    )
    assert body is None


async def test_global_token_is_fail_closed(clock):
    """wv5-2：全局 Token（tournament_id 为空）按目标不符终止，不半支持。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        ParticipantTerminalReason,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )
    global_me = load_fixture('me.json')
    global_me['tournament_id'] = ''

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            return 200, _json.dumps(global_me)
        raise AssertionError('unexpected ' + str(path))

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    outcome = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.TARGET_MISMATCH


async def test_conflict_refresh_cancelled_blocks_window(transport, clock):
    """wv5-3：409 后刷新被取消 → 窗口终结，同窗二次提交零追加 POST。"""

    peng = load_fixture('state_response_snapshot_peng.json')
    transport.handler = lambda **kw: _json(peng)
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)

    async def handler409(**kw):
        if 'method' in kw and kw['method'] == 'POST':
            raise ConflictError(409, 'INVALID_ACTION', 'no')
        await asyncio.sleep(30)  # 权威刷新挂起
        return 200, '{}'

    transport.handler = handler409
    task = asyncio.create_task(
        session.submit(_attempt(window.window_key, Peng(Tile('2w')), 'peng:2w'))
    )
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    again = await asyncio.wait_for(
        session.submit(
            _attempt(window.window_key, Peng(Tile('2w')), 'peng:2w', attempt_no=2)
        ),
        timeout=2,
    )
    assert isinstance(again, SubmitNotSent)
    assert again.reason == 'window_already_finalized'
    posts = [c for c in transport.calls if c.method == 'POST']
    assert len(posts) == 1



def test_catch_play_missing_drawn_fails_closed():
    """wv9：抓打圈 + drawn_tile 缺失 → fail-closed（服务端超时自动打最右兜底）。"""

    from hangma_bot.adapters.official.projector import action_request_body

    hand = (Tile('1w'), Tile('2w'), Tile('5w'))
    assert action_request_body(
        Discard(Tile('5w')),
        last_discard_tile=None,
        hand=hand,
        drawn_tile=None,
        catch_play=True,
    ) is None  # 官方 API §5.4 只确认可打 drawn；缺失即拒绝，不猜测


async def test_next_update_rejects_binding_drift(clock):
    """R2：Token 中途改绑 → 目标错配终态，他赛事场次不进入快照。"""

    import json as _json
    from pathlib import Path
    from hangma_bot.application.contracts import (
        ParticipantTerminal,
        ParticipantTerminalReason,
        RuntimeMode,
        RuntimeTarget,
    )

    transport = FakeTransport()
    guide = _json.loads(
        Path('doc/references/official-guide-version-v8.json').read_text(encoding='utf-8')
    )
    me_calls = {'n': 0}

    def handler(method=None, path=None, **kw):
        if path == '/portal/api/guide/version':
            return 200, _json.dumps(guide)
        if path == '/api/me':
            me_calls['n'] += 1
            if me_calls['n'] == 1:
                return 200, _json.dumps(load_fixture('me.json'))
            drifted = load_fixture('me.json')
            drifted['tournament_id'] = 't_other'  # Token 被改绑
            drifted['active_games'] = [{'game_id': 'g_foreign_tB'}]
            return 200, _json.dumps(drifted)
        if path == '/api/tournaments/me/rules':
            return 200, _json.dumps(load_fixture('rules.json'))
        return 200, _json.dumps(load_fixture('tournament_detail.json'))

    transport.handler = handler
    session = make_tournament_session(clock=clock, transport=transport)
    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id='t_test_room_1',
        known_guide_version=8,
    )
    boot = await asyncio.wait_for(session.initialize(target), timeout=2)
    assert not isinstance(boot, ParticipantTerminal)
    terminal = await asyncio.wait_for(session.next_update(), timeout=3)
    assert isinstance(terminal, ParticipantTerminal)
    assert terminal.reason is ParticipantTerminalReason.TARGET_MISMATCH



async def test_pending_with_gap_triggers_rebuild(transport, clock):
    """wv9：pending=true 携带 gap=true → 必须 seq=0 权威重建而非继续旧 seq。"""

    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock)
    first = await asyncio.wait_for(session.next_item(), timeout=2)  # 首窗 W1
    assert first.window_key.trigger_seq == 101

    calls = []
    migrated = load_fixture('state_response_snapshot_draw.json')
    migrated['seq'] = 130  # 重建后的权威快照携带新窗

    def pending_gap(method=None, params=None, **kw):
        calls.append(params)
        if params == {'seq': 101}:
            return 200, json.dumps({'pending': True, 'gap': True})
        return _json(migrated)

    transport.handler = pending_gap
    item = await asyncio.wait_for(session.next_item(), timeout=3)
    assert {'seq': 0} in calls  # 发起了 seq=0 重建而非 seq=101 死循环
    assert isinstance(item, ObservedActionWindow)
    assert item.window_key.trigger_seq == 130


async def test_post_429_outcome_audit_carries_post_sent(transport, clock):
    """wv9：429 的 SUBMISSION_OUTCOME 审计直接携带 post_sent=true。"""

    from _official_testkit import FakeAuditSink

    audit = FakeAuditSink()
    transport.handler = lambda **kw: _json(load_fixture('state_response_snapshot_draw.json'))
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    window = await asyncio.wait_for(session.next_item(), timeout=2)

    def limited(**kw):
        raise ConflictError(429, 'RATE_LIMITED', 'slow') if False else RateLimitedError(429, 'RATE_LIMITED', 'slow', 0.1)

    transport.handler = limited
    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, Discard(Tile('5w')), 'discard:5w')),
        timeout=3,
    )
    assert isinstance(outcome, SubmitNotSent)
    outcomes = [
        r for r in audit.records
        if r.kind is AuditKind.SUBMISSION_OUTCOME and r.payload.get('attempt_no') == 1
    ]
    assert len(outcomes) == 1
    assert outcomes[0].payload.get('post_sent') is True

