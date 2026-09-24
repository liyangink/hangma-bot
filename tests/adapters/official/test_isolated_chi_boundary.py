"""共享状态额度的边界回归：另一桌 429 不冻结当前吃窗。"""
import asyncio
import json

import pytest

from _virtual_clock import VirtualClock
from _official_testkit import FakeTransport, FakeAuditSink, make_audit_context, TIMING
from test_sync_repair_regressions import snapshot, event
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.adapters.official.errors import RateLimitedError
from hangma_bot.application.contracts import ActionAttempt, SubmitNotSent
from hangma_bot.kernel.actions import Pass, WindowPhase


class NoJitter:
    def uniform(self, low, high):
        return 0


@pytest.mark.parametrize("max_games", [4, 10, 16])
@pytest.mark.parametrize("other_game_rate_limited", [False, True])
async def test_chi_boundary_survives_other_game_state_429(other_game_rate_limited, max_games):
    clock, transport, audit = VirtualClock(), FakeTransport(), FakeAuditSink()
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=clock.sleep,
                                 rate_per_second=14, burst=1, jitter_rng=NoJitter())
    wall_start = clock.wall_ms()
    # 弃 5w：本方手牌（万子全型）与上家弃牌构成吃形保守超集——
    # 2026-09-18 起只有对我校有鸣牌兴趣的周期才挂边界看门狗
    initial = snapshot(179, turn=1, phase="response_peng", river=("5w",),
                       discard={"seat": 1, "tile": "5w", "seq": 179}, responders=(2,))
    initial["snapshot"]["window_deadline_ms"] = wall_start + 1000
    initial["snapshot"]["discards"] = [[], ["5w"], [], []]
    calls = 0
    async def handler(*, path, params, long_poll, **kwargs):
        nonlocal calls
        if "peer" in path:
            raise RateLimitedError(429, "RATE_LIMITED", "poll rate exceeded", retry_after_seconds=None)
        calls += 1
        if calls == 1:
            return 200, json.dumps(initial)
        if long_poll:
            await asyncio.Future()  # 边界定时器取消此挂起请求，再抓权威快照。
        phase = "response_chi" if clock.monotonic() < 2 else "draw"
        seq = 182 if phase == "response_chi" else 184
        doc = snapshot(seq, turn=1 if phase == "response_chi" else 2, phase=phase,
                       drawn="" if phase == "response_chi" else "7w", river=("5w",),
                       discard={"seat": 1, "tile": "5w", "seq": 179}, responders=(2,))
        doc["snapshot"]["discards"] = [[], ["5w"], [], []]
        doc["snapshot"]["window_deadline_ms"] = wall_start + (2000 if phase == "response_chi" else 5000)
        doc["events"] = [event(n, "timeout", seat=seat, data={"kind":"response", "window":"peng"})
                         for n, seat in ((180, 0), (181, 2), (182, 3))]
        if seq == 184:
            doc["events"] += [event(183, "timeout", seat=2, data={"kind":"response", "window":"chi"}),
                              event(184, "tile_drawn", seat=2, tile="7w")]
        return 200, json.dumps(doc)

    transport.handler = handler
    def session(game):
        chosen_scheduler = scheduler.for_game(game, max_games=max_games)
        return OfficialGameSession(game_id=game, transport=transport, scheduler=chosen_scheduler,
            timing=TIMING, monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
            audit=audit, audit_context=make_audit_context, retry_sleep=clock.sleep)
    active, peer = session("active"), session("peer")
    peer_task = None
    async def start_peer_at_boundary():
        await clock.sleep(1.02)
        return await peer.next_item()
    try:
        first = await clock.run(active.next_item())
        outcome = await active.submit(ActionAttempt(decision_id="chi-probe", attempt_no=1, plan_revision=1,
            window_key=first.window_key, based_on_authoritative_seq=first.authoritative_seq,
            action=Pass(), action_key="pass", latest_send_at_monotonic=.5))
        assert isinstance(outcome, SubmitNotSent) and outcome.reason == "pass_deferred_until_chi"
        if other_game_rate_limited:
            peer_task = asyncio.create_task(start_peer_at_boundary())
        second = await clock.run(active.next_item())
        response_queries = [
            r.payload for r in audit.records
            if r.kind.value == "http_request"
            and r.payload.get("endpoint") == "GET /api/games/active/state"
            and (r.payload.get("request_timing") or {}).get("query_purpose") == "response_progress"
        ]
        assert response_queries, "已知响应阶段的状态长轮询须单独标记并优先于普通场次轮询"
        assert second.window_key.phase is WindowPhase.RESPONSE_CHI, (
            f"M={max_games}; 其他场429={other_game_rate_limited}; 下次可见阶段={second.window_key.phase}; "
            f"单调时间={clock.monotonic():.3f}s，chi在2.000s结束")
        if other_game_rate_limited:
            # 被拒请求单独退避，当前场仍应在原吃窗截止前领取共享额度。
            cancelled = [r.payload for r in audit.records
                         if r.payload.get("state_query_cancel_reason") == "expired_window_purpose"]
            assert not cancelled
            assert clock.monotonic() < 2.0
    finally:
        if peer_task:
            peer_task.cancel()
            await asyncio.gather(peer_task, return_exceptions=True)
        await active.aclose("probe_complete")
        await peer.aclose("probe_complete")
