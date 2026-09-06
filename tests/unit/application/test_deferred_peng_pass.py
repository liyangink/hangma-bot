"""碰阶段本地延后 pass：应用层结束该阶段，等待真实吃窗口，不发送下一候选。"""

import asyncio
from dataclasses import replace

from fakes import (
    FakeGameSession, FakePolicy, FakeRules, FakeTournamentSession, ManualClock,
    PASS, build_runtime, make_bootstrap, make_observation, make_snapshot,
    make_window, wait_for_condition,
)
from hangma_bot.application.contracts import SubmitAccepted, SubmitNotSent, TournamentStatus
from hangma_bot.kernel.actions import Chi, Peng, Tile, WindowPhase

CHI = Chi((Tile("1w"), Tile("2w"), Tile("3w")))
PENG = Peng(Tile("2w"))


class StageRules(FakeRules):
    """只提供当前响应阶段候选；碰阶段首选过，但保留碰来检测误追加。"""

    def __init__(self):
        super().__init__(emergency=PASS)

    def analyze(self, observation):
        candidates = (PASS, PENG) if observation.phase == "response_peng" else (CHI, PASS)
        return FakeRules(candidates=candidates, emergency=PASS).analyze(observation)


def _window(phase, *, received=100.0, expires=100.4):
    observation = replace(make_observation(phase=phase.value), responding_seats=(0,), turn_seat=3)
    return replace(make_window(observation, phase=phase, received_at=received, timeout=1.0),
                   expires_at_monotonic=expires, deadline_is_estimated=False)


async def _run(windows, *, cancel=False):
    clock = ManualClock()

    class StageSession(FakeGameSession):
        async def next_item(self):
            item = await super().next_item()
            if item.observation.phase == "response_chi":
                clock.advance(1.0)
            return item

    def submit(attempt):
        if attempt.window_key.phase is WindowPhase.RESPONSE_PENG:
            return SubmitNotSent("pass_deferred_until_chi")
        return SubmitAccepted(None, 11)

    game = StageSession(items=windows, submit_handler=submit)
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)], game_factory=lambda gid: game,
    )
    runtime, sink, policy, *_ = build_runtime(session=session, rules=StageRules(), clock=clock, policy=FakePolicy())
    task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: game.drained)
    if cancel:
        task.cancel()
        outcome = (await asyncio.gather(task, return_exceptions=True))[0]
        assert isinstance(outcome, asyncio.CancelledError)
    else:
        session.grant_updates(1)
        outcome = await task
        assert outcome.reason.value == "tournament_finished"
    return game, sink, policy


async def test_deferred_peng_pass_never_appends_remaining_candidate_or_counts_sent():
    game, sink, policy = await _run([_window(WindowPhase.RESPONSE_PENG)])
    assert len(game.submitted) == 1
    assert game.submitted[0].action_key == "pass"  # 端口调用，不表示已发 HTTP
    assert len(policy.calls) == 1
    ended = [row for row in sink.records if row.kind.value == "decision_ended"]
    assert len(ended) == 1 and ended[0].payload["sent_attempts"] == 0
    outcomes = [row.payload for row in sink.records if row.kind.value == "submission_outcome"]
    assert len(outcomes) == 1
    assert outcomes[0]["outcome"] == "SubmitNotSent"
    assert outcomes[0]["reason"] == "pass_deferred_until_chi"


async def test_real_chi_window_gets_own_budget_and_no_rejected_peng_pass():
    game, sink, policy = await _run([
        _window(WindowPhase.RESPONSE_PENG),
        _window(WindowPhase.RESPONSE_CHI, received=101.0, expires=101.3),
    ])
    assert [attempt.action_key for attempt in game.submitted] == ["pass", "chi:1w,2w,3w"]
    assert [request.window_key.phase for request in policy.calls] == [WindowPhase.RESPONSE_PENG, WindowPhase.RESPONSE_CHI]
    assert policy.calls[0].decision_id != policy.calls[1].decision_id
    assert policy.calls[1].rejected_attempts == ()  # 本地未发送不是官方拒绝
    assert policy.budgets[0].latest_send_at_monotonic < 100.4
    assert 101.0 < policy.budgets[1].latest_send_at_monotonic < 101.3
    ended = [row.payload for row in sink.records if row.kind.value == "decision_ended"]
    assert [row["sent_attempts"] for row in ended] == [0, 1]


async def test_expired_peng_window_does_not_call_policy_or_submit_to_defer():
    game, sink, policy = await _run([_window(WindowPhase.RESPONSE_PENG, expires=99.9)])
    assert not game.submitted
    assert not policy.calls
    ended = [row.payload for row in sink.records if row.kind.value == "decision_ended"]
    assert ended[0]["end_reason"] == "deadline" and ended[0]["sent_attempts"] == 0


async def test_cancelling_wait_after_deferred_pass_does_not_retry_or_submit_next_candidate():
    game, _, policy = await _run([_window(WindowPhase.RESPONSE_PENG)], cancel=True)
    assert len(game.submitted) == 1 and game.submitted[0].action_key == "pass"
    assert len(policy.calls) == 1
    assert game.closed
