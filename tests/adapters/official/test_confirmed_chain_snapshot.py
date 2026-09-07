"""v20真实明杠→完整快照轨迹：通过会话公开端口验证链事实，不增补历史请求。"""
import asyncio
import json
from pathlib import Path

import pytest

from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.errors import ConflictError, UncertainTransportError
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitAccepted, SubmitAmbiguous
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.actions import action_key
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import action_from_json

from _official_testkit import TIMING, make_audit_context

CASES = json.loads((Path(__file__).parents[2] / 'fixtures/official/v20/snapshot-chain.json').read_text())['cases']


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
@pytest.mark.parametrize('submit_result', ['accepted', 'ambiguous', 'rejected'])
async def test_real_confirmed_gang_then_snapshot_keeps_precise_facts(case, submit_result, transport, clock):
    """只喂实际3次GET和1次POST；多查一次或回退增量游标即失败。"""
    queue = [('GET', row) for row in case['before_requests']]
    queue += [('POST', case['action_response']), ('GET', case['after_request'])]
    clock.advance((case['before_requests'][0]['wall_time_unix_ms'] - clock.wall_ms()) / 1000)

    async def sleep(seconds):
        clock.advance(seconds)
        await asyncio.sleep(0)

    def handler(*, method, params=None, **kwargs):
        assert queue, '出现了轨迹以外的额外请求'
        expected_method, row = queue.pop(0)
        assert method == expected_method
        if method == 'GET':
            assert params == row['params']
        clock.advance(max(0, (row['wall_time_unix_ms'] - clock.wall_ms()) / 1000))
        # 故障注入只改变提交结果；即使后来出现相似牌面，也不能把已发送
        # 或已拒绝的动作充当成功确认，更不能盲重发同一个POST。
        if method == 'POST' and submit_result == 'ambiguous':
            raise UncertainTransportError('injected_reply_lost')
        if method == 'POST' and submit_result == 'rejected':
            raise ConflictError(409, 'INVALID_ACTION', 'injected_rejection')
        return 200, json.dumps(row['response'])

    transport.handler = handler
    session = OfficialGameSession(
        game_id=case['game_id'], transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=sleep, rate_per_second=2,
                                   burst=1, max_concurrent=2, max_state_concurrent=1),
        timing=TIMING, monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit_context=make_audit_context, retry_sleep=sleep,
    )
    try:
        before = await asyncio.wait_for(session.next_item(), 2)
        assert isinstance(before, ObservedActionWindow)
        assert before.observation.chain_piao == 0
        action = action_from_json(case['accepted_action'])
        attempt = ActionAttempt(
            decision_id=case['action_response']['decision_id'], attempt_no=1, plan_revision=1,
            window_key=before.window_key, based_on_authoritative_seq=before.authoritative_seq,
            action=action, action_key=action_key(action),
            latest_send_at_monotonic=clock.monotonic() + .5,
        )
        submitted = await session.submit(attempt)
        if submit_result == 'accepted':
            assert isinstance(submitted, SubmitAccepted)
        elif submit_result == 'ambiguous':
            assert isinstance(submitted, SubmitAmbiguous)
        else:
            assert not isinstance(submitted, (SubmitAccepted, SubmitAmbiguous))
        after = await asyncio.wait_for(session.next_item(), 2)
        assert isinstance(after, ObservedActionWindow)
        assert not queue
        assert after.observation.consumed_seq == case['expected_seq']
        if submit_result == 'accepted':
            assert after.observation.chain_piao == 0
            assert after.observation.gang_draw is True
            for enabled in (False, True):
                analysis = HangmaRules(RuleConfig('snapshot-chain-regression', 1, enabled)).analyze(after.observation)
                assert analysis.completeness is RuleCompleteness.COMPLETE
                assert analysis.emergency_candidate is not None
                # 10例中只有玄武seq504静态成胡：有财非爆头，按房规开关
                # 判断资格；其余9例未成牌。补足链事实不能放宽开启时的资格。
                has_hu = any(candidate.action_key == 'hu' for candidate in analysis.legal_candidates)
                assert has_hu is (case['expected_seq'] == 504 and not enabled)
        else:
            assert after.observation.chain_piao is None
            assert after.observation.gang_draw is None
            analysis = HangmaRules(RuleConfig('snapshot-chain-regression', 1, True)).analyze(after.observation)
            assert analysis.completeness is RuleCompleteness.DEGRADED
            assert any(issue.area == 'observation.chain_piao' for issue in analysis.issues)
        assert sum(call.method == 'POST' for call in transport.calls) == 1
        assert not after.observation.history_complete
        assert all(e.seq < case['expected_seq'] - 1 for e in after.observation.public_history)
    finally:
        await session.aclose('test_complete')
