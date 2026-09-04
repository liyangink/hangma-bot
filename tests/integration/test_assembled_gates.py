"""端到端组装门禁：C3 生命周期、C4 提交安全、C8 审计完整。

全部经过 bootstrap.build_runtime 的组合路径：脚本化端口 + 真实 HangmaRules +
真实 WeightedHeuristicPolicy + 真实 JsonlAuditSink + 离线验证器，证明组装产物
在本地门禁口径下可运行、可降级、可审计；提交语义逐条对接口协议第 5 节：

- 只有 SubmitRejectedRetryable 允许在原预算内排除已拒绝动作重新规划；
- SubmitRejectedNoRefresh / SubmitAmbiguous 终结原窗口且不追加动作；
- 审计磁盘故障不阻断动作，运行诚实标记 audit_degraded。
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress

import pytest

from hangma_bot.adapters.recording import validate_run
from hangma_bot.application.contracts import (
    AuditContext,
    GameFinished,
    OperationStatus,
    ParticipantTerminalReason,
    ReadyResult,
    RegistrationResult,
    SubmitAccepted,
    SubmitAmbiguous,
    SubmitRejectedNoRefresh,
    SubmitRejectedRetryable,
    TournamentStatus,
)
from hangma_bot.bootstrap import build_runtime, runtime_config_from_mapping

from _integration_helpers import (
    ScriptedGameSession,
    ScriptedTournamentSession,
    make_bootstrap,
    make_config,
    make_observation,
    make_refreshed_window,
    make_snapshot,
    make_window,
)


SECRET_TOKEN = "integration-secret-token-0123456789abcdef"


def _draw_window(game_id: str = "g1", seq: int = 10):
    """普通摸牌出牌窗口；到达时刻用真实单调时钟，预算在窗口内有效。"""

    observation = make_observation(game_id=game_id, seat=0, seq=seq)
    return make_window(observation, timeout=3.0, received_at=time.monotonic())


def _finished_game() -> GameFinished:
    return GameFinished(game_id="g1", final_scores=(8, 4, 0, -2), authoritative_seq=42)


def _single_game(tmp_path, *, game_items, submit_outcomes, audit_root=None):
    """组装只有 g1 一场的运行时；返回 (assembled, session, game)。"""

    game = ScriptedGameSession(items=game_items, submit_outcomes=submit_outcomes)
    assembled, session = _assemble(
        tmp_path,
        updates=_updates(("g1",)),
        games={"g1": game},
        audit_root=audit_root,
        max_games=1,
    )
    return assembled, session, game


def _assemble(
    tmp_path,
    *,
    updates,
    games,
    audit_root=None,
    max_games: int = 2,
    initial_snapshot=None,
    register_results=None,
    ready_results=None,
):
    """经组合根组装脚本化端口的完整运行时（与生产唯一差异：会话是脚本化的）。

    每个脚本化场次会话都复刻官方适配器的双层记录接线（窗口权威状态
    无 stage_attempt_id），与真实运行的审计形态一致。initial_snapshot
    覆盖 initialize 返回的初始快照（默认 registering），用于测试房间
    finished 冷启动等启动形态。
    """

    root = audit_root if audit_root is not None else tmp_path
    snapshot0 = (
        initial_snapshot
        if initial_snapshot is not None
        else make_snapshot(TournamentStatus.REGISTERING)
    )
    config = make_config(max_games=max_games)
    bootstrap = make_bootstrap(snapshot0, config=config)
    session = ScriptedTournamentSession(
        bootstrap=bootstrap,
        updates=updates,
        game_sessions=games,
        register_results=register_results,
        ready_results=ready_results,
    )
    runtime_config = runtime_config_from_mapping(
        {
            "mode": "test_room",
            "base_url": "https://platform.invalid",
            "expected_tournament_id": "t1",
            "known_guide_version": 8,
            "token": SECRET_TOKEN,
            "token_kind": "test",
            "audit_root": str(root),
            "strategy": "weighted_heuristic",
        }
    )
    assembled = build_runtime(runtime_config, session_factory=lambda: session)
    for game in games.values():
        game.attach_audit(
            assembled.sink,
            lambda: AuditContext(
                run_id=assembled.run_id, tournament_id="t1", participant_id="p1"
            ),
        )
    return assembled, session


def _updates(game_ids: tuple) -> list:
    my_games = tuple(game_ids)
    return [
        make_snapshot(
            TournamentStatus.RUNNING, active_games=my_games, my_games=my_games
        ),
        make_snapshot(
            TournamentStatus.FINISHED, active_games=(), my_games=my_games
        ),
    ]


async def test_assembled_lifecycle_completes_with_clean_audit(tmp_path):
    """C3/C8：报名→running→一场→赛事终态，验证器判定完整可审计。"""

    assembled, session, game = _single_game(
        tmp_path,
        game_items=[_draw_window(), _finished_game()],
        submit_outcomes=[SubmitAccepted(official_code="200", authoritative_seq=11)],
    )

    terminal = await assembled.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(game.submitted) == 1
    assert game.submitted[0].attempt_no == 1
    assert assembled.audit_degraded is False
    summary = assembled.last_audit_summary
    assert summary is not None and summary.audit_degraded is False
    assert summary.missing_high_priority == 0

    report = validate_run(assembled.sink.run_dir)
    assert report["audit_complete"] is True
    assert report["secret_scan_clean"] is True
    assert report["coverage"]["manifest_present"] is True
    assert report["coverage"]["games_finished"] == 1
    assert report["coverage"]["final_scores_by_game"] == {"p1/g1": [8, 4, 0, -2]}
    assert report["submissions"]["distinct_attempts"] == 1
    assert report["submissions"]["outcome_histogram"].get("accepted") == 1
    # 双层记录（脚本化适配器 + 应用层）不触发阶段混用违规。
    violations = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "stage_attempt_mixing" not in violations
    # 生命周期链路存在：报名/到位由注册快照直达 running 阶段。
    assert session.register_calls >= 1
    # 组合根的身份发现装配：初始化后 participant_id 可被启动脚本读取。
    assert assembled.participant_id == "p1"
    # Token 原文扫描为零：独立于验证器直接扫描全部落盘文件。
    for audit_file in assembled.sink.run_dir.rglob("*"):
        if audit_file.is_file():
            assert SECRET_TOKEN not in audit_file.read_text(
                encoding="utf-8", errors="replace"
            )


async def test_409_replan_submits_second_candidate_in_same_window(tmp_path):
    """C4：明确拒绝 + 权威刷新确认同窗仍开放 → 原预算内换下一候选。"""

    window = _draw_window()

    def submit_handler(attempt):
        if attempt.attempt_no == 1:
            return SubmitRejectedRetryable(
                official_code="409",
                rejected_action_key=attempt.action_key,
                refreshed_window=make_refreshed_window(window, seq=11),
            )
        return SubmitAccepted(official_code="200", authoritative_seq=12)

    assembled, _session, game = _single_game(
        tmp_path,
        game_items=[window, _finished_game()],
        submit_outcomes=submit_handler,
    )
    terminal = await assembled.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(game.submitted) == 2
    first, second = game.submitted
    assert first.decision_id == second.decision_id
    assert first.attempt_no == 1 and second.attempt_no == 2
    assert first.plan_revision == 1 and second.plan_revision == 2
    assert first.window_key == second.window_key
    assert first.action_key != second.action_key

    report = validate_run(assembled.sink.run_dir)
    assert report["audit_complete"] is True
    histogram = report["submissions"]["outcome_histogram"]
    assert histogram["rejected_retryable"] == 1
    assert histogram["accepted"] == 1
    assert report["submissions"]["rejected_total"] == 1


async def test_rejected_no_refresh_ends_window_without_retry(tmp_path):
    """C4：官方明确未执行但无权威刷新 → 终结原窗口，不追加动作。"""

    def submit_handler(attempt):
        return SubmitRejectedNoRefresh(
            official_code="429",
            rejected_action_key=attempt.action_key,
            latest_local_seq=attempt.based_on_authoritative_seq,
            reason="official_rate_limited",
        )

    assembled, _session, game = _single_game(
        tmp_path,
        game_items=[_draw_window(), _finished_game()],
        submit_outcomes=submit_handler,
    )
    terminal = await assembled.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(game.submitted) == 1  # POST 已发出但窗口终结，零追加
    report = validate_run(assembled.sink.run_dir)
    assert report["audit_complete"] is True
    histogram = report["submissions"]["outcome_histogram"]
    assert histogram["rejected_no_refresh"] == 1
    assert report["submissions"]["rejected_total"] == 1


async def test_ambiguous_submission_blocks_window(tmp_path):
    """C4：结果不确定 → 封锁同窗，零追加提交，等待权威迁移。"""

    assembled, _session, game = _single_game(
        tmp_path,
        game_items=[_draw_window(), _finished_game()],
        submit_outcomes=[SubmitAmbiguous(recovery_id="r1", reason="request_timeout")],
    )
    terminal = await assembled.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(game.submitted) == 1
    report = validate_run(assembled.sink.run_dir)
    assert report["audit_complete"] is True
    assert report["submissions"]["outcome_histogram"]["ambiguous"] == 1


async def test_audit_disk_failure_degrades_honestly_and_actions_continue(tmp_path):
    """可降级：审计目录不可写不阻断动作，运行诚实标记 audit_degraded。"""

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "runs").write_text("占位文件：目录创建必然失败", encoding="utf-8")
    assembled, _session, game = _single_game(
        tmp_path,
        game_items=[_draw_window(), _finished_game()],
        submit_outcomes=[SubmitAccepted(official_code="200", authoritative_seq=11)],
        audit_root=blocked,
    )
    terminal = await assembled.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(game.submitted) == 1  # 动作提交不受磁盘故障影响
    assert assembled.audit_degraded is True
    summary = assembled.last_audit_summary
    assert summary is not None and summary.audit_degraded is True
    assert summary.missing_high_priority > 0


async def test_multi_game_lifecycle_two_games_with_409(tmp_path):
    """C3/C4：active_games 两场并发，每场规则→策略→提交（g1 含 409 降级）→终局，
    全程无需人工决策；验证器完整可审计。"""

    window1 = _draw_window(game_id="g1", seq=10)
    window2 = _draw_window(game_id="g2", seq=20)
    finish1 = GameFinished(game_id="g1", final_scores=(8, 4, 0, -2), authoritative_seq=42)
    finish2 = GameFinished(game_id="g2", final_scores=(5, 5, 5, -5), authoritative_seq=43)

    def g1_handler(attempt):
        if attempt.attempt_no == 1:
            return SubmitRejectedRetryable(
                official_code="409",
                rejected_action_key=attempt.action_key,
                refreshed_window=make_refreshed_window(window1, seq=11),
            )
        return SubmitAccepted(official_code="200", authoritative_seq=12)

    game1 = ScriptedGameSession(items=[window1, finish1], submit_outcomes=g1_handler)
    game2 = ScriptedGameSession(
        items=[window2, finish2],
        submit_outcomes=[SubmitAccepted(official_code="200", authoritative_seq=21)],
    )
    assembled, session = _assemble(
        tmp_path,
        updates=_updates(("g1", "g2")),
        games={"g1": game1, "g2": game2},
        max_games=2,
    )

    terminal = await assembled.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(game1.submitted) == 2  # g1: 409 拒绝降级后换下一候选
    assert len(game2.submitted) == 1
    first, second = game1.submitted
    assert first.decision_id == second.decision_id
    assert first.attempt_no == 1 and second.attempt_no == 2
    assert first.action_key != second.action_key

    report = validate_run(assembled.sink.run_dir)
    assert report["audit_complete"] is True
    assert report["secret_scan_clean"] is True
    assert report["coverage"]["games_finished"] == 2
    assert report["coverage"]["final_scores_by_game"] == {
        "p1/g1": [8, 4, 0, -2],
        "p1/g2": [5, 5, 5, -5],
    }
    submissions = report["submissions"]
    assert submissions["distinct_attempts"] == 3
    assert submissions["outcome_histogram"]["rejected_retryable"] == 1
    assert submissions["outcome_histogram"]["accepted"] == 2


async def test_test_room_finished_cold_start_reuses_and_joins_next_round(tmp_path):
    """测试房间 finished 冷启动：supervisor 跨轮复用分支（register+ready）可达，
    下一轮 running 到来后加入对局并正常完赛（对应 Challenger 返工意见）。"""

    finished0 = make_snapshot(TournamentStatus.FINISHED, active_games=(), my_games=())
    game = ScriptedGameSession(
        items=[_draw_window(game_id="g1", seq=10), _finished_game()],
        submit_outcomes=[SubmitAccepted(official_code="200", authoritative_seq=11)],
    )
    assembled, session = _assemble(
        tmp_path,
        updates=[
            make_snapshot(TournamentStatus.RUNNING, active_games=("g1",), my_games=("g1",)),
            make_snapshot(TournamentStatus.FINISHED, active_games=(), my_games=("g1",)),
        ],
        games={"g1": game},
        max_games=1,
        initial_snapshot=finished0,
        register_results=[RegistrationResult(status=OperationStatus.ACCEPTED)],
        ready_results=[ReadyResult(status=OperationStatus.ACCEPTED)],
    )
    # 确定性时序：报名与到位完成前不发放下一张快照。
    session.update_gate = (
        lambda: session.register_calls >= 1 and len(session.ready_calls) >= 1
    )

    terminal = await assembled.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.register_calls >= 1  # finished 冷启动仍幂等报名
    assert len(session.ready_calls) >= 1  # 跨轮复用分支发出下一轮到位
    assert len(game.submitted) == 1
    report = validate_run(assembled.sink.run_dir)
    assert report["audit_complete"] is True
    assert report["coverage"]["games_finished"] == 1


async def test_test_room_finished_cold_start_stays_alive_waiting_next_round(tmp_path):
    """测试房间 finished 冷启动不提前终态化：register+ready 后存活轮询，
    等待下一轮（运行时未结束），直到外部取消。"""

    finished0 = make_snapshot(TournamentStatus.FINISHED, active_games=(), my_games=())
    assembled, session = _assemble(
        tmp_path,
        updates=[],  # 脚本耗尽后挂起：模拟房间持续 finished 的空窗
        games={},
        max_games=1,
        initial_snapshot=finished0,
        register_results=[RegistrationResult(status=OperationStatus.ACCEPTED)],
        ready_results=[ReadyResult(status=OperationStatus.ACCEPTED)],
    )
    task = asyncio.ensure_future(assembled.run())
    try:
        for _ in range(2000):
            if session.register_calls >= 1 and len(session.ready_calls) >= 1:
                break
            await asyncio.sleep(0.001)
        else:
            pytest.fail("报名/到位在 finished 冷启动窗口内未发生")
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.3)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


if __name__ == "__main__":
    pytest.main([__file__])
