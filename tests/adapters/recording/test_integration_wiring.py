"""端到端集成：真实生产 payload 经 AuditTrail → JsonlAuditSink → 验证器全链路。

背景（返工 blocker）：schema 曾单方面强制必填词表，wiring 后 6/8 种类被拒为
序列化失败，真实运行的 SUBMISSION_OUTCOME 全部丢失、所有尝试悬空、
审计降级恒真。本文件按当前生产代码 emit 点的真实 payload 形态构造记录
（来源以 file:line 注明），锁定整条审计链路：不拒收、不悬空、可判定完整、
双层记录可归并统计。
"""

import json

from hangma_bot.adapters.recording import (
    JsonlAuditSink,
    build_action_response_payload,
    build_state_response_payload,
    validate_run,
)
from hangma_bot.application.audit import AuditTrail
from hangma_bot.application.contracts import AuditKind, AuditReceipt


_WINDOW = {
    "game_id": "G1",
    "round_no": 1,
    "trigger_seq": 10,
    "phase": "response_peng",
    "seat": 2,
}


class _ScriptedClock:
    """受控时钟：满足 RuntimeClock 协议，墙上毫秒按脚本推进（时延可精确断言）。"""

    def __init__(self, start_unix_ms: int = 1_800_000_000_000) -> None:
        self._unix_ms = start_unix_ms

    def now(self) -> float:
        return self._unix_ms / 1000.0

    def unix_ms(self) -> int:
        return self._unix_ms

    def budget_wait_seconds(self, deadline_monotonic: float) -> float:
        return 0.0

    def advance_ms(self, milliseconds: int) -> None:
        self._unix_ms += milliseconds


def _attempt_ctx(decision_id: str, attempt_no: int) -> dict:
    return {
        "stage_attempt_id": "st-1",
        "game_id": "G1",
        "round_no": 1,
        "trigger_seq": 10,
        "decision_id": decision_id,
        "attempt_no": attempt_no,
    }


def _emit_attempt(trail: AuditTrail, clock: _ScriptedClock, decision_id: str, attempt_no: int) -> None:
    """按两个真实生产方（应用层 + 官方适配器）的双层记录顺序发射一次尝试。

    顺序与 wired 运行一致：应用层 intent → 适配器 intent → POST →
    适配器 outcome → 应用层 outcome。
    """

    # 应用层 SUBMISSION_INTENT（decision_loop.py:378）。
    receipts = []
    receipts.append(trail.emit(
        AuditKind.SUBMISSION_INTENT,
        {
            "action_key": "peng:1w",
            "is_emergency": False,
            "based_on_authoritative_seq": 10,
            "plan_revision": 1,
            "latest_send_at_monotonic": clock.now() + 0.5,
            "window": dict(_WINDOW),
        },
        **_attempt_ctx(decision_id, attempt_no),
    ))
    clock.advance_ms(2)
    # 官方适配器 SUBMISSION_INTENT（adapters/official/game.py:342，含请求 body）。
    receipts.append(trail.emit(
        AuditKind.SUBMISSION_INTENT,
        {
            "decision_id": decision_id,
            "attempt_no": attempt_no,
            "plan_revision": 1,
            "action_key": "peng:1w",
            "based_on_authoritative_seq": 10,
            "window": dict(_WINDOW),
            "body": {"action": "peng", "tile": "1w"},
        },
        **_attempt_ctx(decision_id, attempt_no),
    ))
    return receipts


def _emit_adapter_outcome(
    trail: AuditTrail,
    clock: _ScriptedClock,
    decision_id: str,
    attempt_no: int,
    outcome_type: str,
    **extra: str,
) -> tuple[AuditReceipt, AuditReceipt]:
    """官方适配器 SUBMISSION_OUTCOME（adapters/official/game.py:442，outcome_type 键）。

    同时发射 action_submit_response 原始事件（接线清单 E3）：POST 已发出的
    每次尝试都必须有响应原文，验证器的 raw_action_missing 检查以此为对账依据。
    返回 (outcome 回执, 原始事件回执)。
    """

    payload = {
        "decision_id": decision_id,
        "attempt_no": attempt_no,
        "plan_revision": 1,
        "action_key": "peng:1w",
        "outcome_type": outcome_type,
    }
    payload.update(extra)
    outcome_receipt = trail.emit(
        AuditKind.SUBMISSION_OUTCOME, payload, **_attempt_ctx(decision_id, attempt_no)
    )
    raw_receipt = trail.emit(
        AuditKind.RAW_PROTOCOL_STATE,
        build_action_response_payload(
            endpoint="POST /api/games/G1/action",
            http_status=200,
            decision_id=decision_id,
            attempt_no=attempt_no,
            raw='{"ok": true}',
        ),
        **_attempt_ctx(decision_id, attempt_no),
    )
    return outcome_receipt, raw_receipt


async def test_wired_run_passes_end_to_end(tmp_path):
    """真实词表全链路：零拒收、配对完整、词表归并、manifest 单对象、判定完整。"""

    sink = JsonlAuditSink(tmp_path, "run-wired")
    clock = _ScriptedClock()
    trail = AuditTrail(
        sink,
        run_id="run-wired",
        tournament_id="t-1",
        participant_id="P1",
        clock=clock,
    )
    receipts = []

    def emit(kind, payload, **context):
        receipt = trail.emit(kind, payload, **context)
        receipts.append(receipt)
        return receipt

    # RUN_MANIFEST（participant_runtime.py:118 真实形态）。
    emit(
        AuditKind.RUN_MANIFEST,
        {
            "run_id": "run-wired",
            "mode": "test_room",
            "expected_tournament_id": "t-1",
            "known_guide_version": 8,
            "guide_version": 8,
            "guide_updated_at": "2026-09-03T00:00:00Z",
            "participant_id": "P1",
            "ruleset_version": "v1",
            "max_games": 1,
            "rounds_per_game": 1,
            "timing": {"peng_timeout_sec": 1.0, "chi_timeout_sec": 3.0, "discard_timeout_sec": 5.0},
        },
    )

    # 监督层 AUTHORITATIVE_STATE（tournament_supervisor.py:201 快照形态，无场上下文）。
    emit(
        AuditKind.AUTHORITATIVE_STATE,
        {
            "status": "running",
            "stage_no": 1,
            "stage_observed_revision": 1,
            "stage_role": "main",
            "stage_total": 1,
            "stage_crashed": False,
            "qualified": True,
            "qualify_role": "main",
            "active_games": ["G1"],
            "my_games": ["G1"],
            "observed_at_unix_ms": 1800000000000,
        },
    )
    # LIFECYCLE_CHANGED（tournament_supervisor.py:204 的 event/from/to 形态）。
    emit(
        AuditKind.LIFECYCLE_CHANGED,
        {"event": "status_changed", "from": None, "to": "running"},
    )

    # 官方适配器窗口权威状态（adapters/official/game.py:244 的 seq/phase/turn/window 形态）。
    emit(
        AuditKind.AUTHORITATIVE_STATE,
        {
            "seq": 10,
            "phase": "response_peng",
            "turn": 0,
            "window": dict(_WINDOW),
        },
        stage_attempt_id="st-1",
        game_id="G1",
        round_no=1,
        trigger_seq=10,
    )
    # 同一场的 state 响应原文（接线清单 E1/E2）：request_no 连续覆盖
    # "每个状态请求都有原始事件"的完整性对账。
    emit(
        AuditKind.RAW_PROTOCOL_STATE,
        build_state_response_payload(
            endpoint="GET /api/games/G1/state",
            http_status=200,
            seq_requested=0,
            seq_observed=10,
            request_no=1,
            raw='{"seq": 10, "snapshot": {"phase": "response_peng"}}',
        ),
        stage_attempt_id="st-1",
        game_id="G1",
        round_no=1,
        trigger_seq=10,
    )
    emit(
        AuditKind.RAW_PROTOCOL_STATE,
        build_state_response_payload(
            endpoint="GET /api/games/G1/state",
            http_status=200,
            seq_requested=10,
            seq_observed=10,
            request_no=2,
            raw='{"pending": true}',
        ),
        stage_attempt_id="st-1",
        game_id="G1",
        round_no=1,
        trigger_seq=10,
    )

    # 尝试 d1#1： accepted，尝试级时延 102ms（1000 → 1102）。
    emit(
        AuditKind.DECISION_PLANNED,
        {
            "plan_revision": 1,
            "based_on_authoritative_seq": 10,
            "trigger_seq": 10,
            "window": dict(_WINDOW),
            "observation_snapshot": {
                "schema_version": 1,
                "game_id": "G1",
                "seat": 2,
                "round_no": 1,
                "snapshot_seq": 10,
                "phase": "response_peng",
                "turn_seat": 0,
                "responding_seats": [2],
                "responding": True,
                "my_hand": ["1w", "1w", "3w", "东", "东", "南", "白"],
                "drawn_tile": None,
                "target_discard": {"seat": 0, "tile": "1w", "seq": 10},
                "my_melds": [],
                "hand_counts": [10, 10, 13, 10],
                "remaining_tile_count": 40,
                "scores": [10, 4, -2, -12],
                "rule_state": {
                    "wealth_god": "白", "baotou": False, "chain_count": 0, "catch_play": False,
                },
            },
            "candidates": [
                {
                    "action_key": "peng:1w",
                    "is_emergency": False,
                    "rank": 1,
                    "action": {"schema_version": 1, "kind": "peng", "tile": "1w"},
                    "reasons": [],
                }
            ],
            "degraded_reasons": [],
            "rule_completeness": "complete",
        },
        stage_attempt_id="st-1",
        game_id="G1",
        round_no=1,
        trigger_seq=10,
        decision_id="d1",
    )
    receipts.extend(_emit_attempt(trail, clock, "d1", 1))
    clock.advance_ms(98)
    receipts.extend(_emit_adapter_outcome(trail, clock, "d1", 1, "SubmitAccepted"))
    clock.advance_ms(2)
    # 应用层 SUBMISSION_OUTCOME（decision_loop.py:421 → _outcome_payload:483，类名形态）。
    emit(
        AuditKind.SUBMISSION_OUTCOME,
        {"outcome": "SubmitAccepted", "window": dict(_WINDOW)},
        **_attempt_ctx("d1", 1),
    )

    # 尝试 d2#2：409 后同窗重规划被拒，retryable，尝试级时延 301ms（2000 → 2301）。
    emit(
        AuditKind.DECISION_PLANNED,
        {
            "plan_revision": 2,
            "based_on_authoritative_seq": 10,
            "trigger_seq": 10,
            "window": dict(_WINDOW),
            "observation_snapshot": {
                "schema_version": 1,
                "game_id": "G1",
                "seat": 2,
                "round_no": 1,
                "snapshot_seq": 10,
                "phase": "response_peng",
                "turn_seat": 0,
                "responding_seats": [2],
                "responding": True,
                "my_hand": ["5w", "5w", "5w", "东", "东", "南", "白"],
                "drawn_tile": None,
                "target_discard": {"seat": 0, "tile": "5w", "seq": 10},
                "my_melds": [],
                "hand_counts": [10, 10, 13, 10],
                "remaining_tile_count": 40,
                "scores": [10, 4, -2, -12],
                "rule_state": {
                    "wealth_god": "白", "baotou": False, "chain_count": 0, "catch_play": False,
                },
            },
            "candidates": [
                {
                    "action_key": "peng:5w",
                    "is_emergency": False,
                    "rank": 1,
                    "action": {"schema_version": 1, "kind": "peng", "tile": "5w"},
                    "reasons": [],
                }
            ],
            "degraded_reasons": ["peng_family_failed"],
            "rule_completeness": "degraded",
        },
        stage_attempt_id="st-1",
        game_id="G1",
        round_no=1,
        trigger_seq=10,
        decision_id="d2",
    )
    receipts.extend(_emit_attempt(trail, clock, "d2", 1))
    clock.advance_ms(298)
    receipts.extend(_emit_adapter_outcome(
        trail,
        clock,
        "d2",
        1,
        "SubmitRejectedRetryable",
        official_code="409",
        rejected_action_key="peng:5w",
    ))
    clock.advance_ms(1)
    emit(
        AuditKind.SUBMISSION_OUTCOME,
        {
            "outcome": "SubmitRejectedRetryable",
            "window": dict(_WINDOW),
            "official_code": "409",
            "rejected_action_key": "peng:5w",
        },
        **_attempt_ctx("d2", 1),
    )

    # PROTOCOL_RECOVERED 三个真实变体（game_task.py:100 / official/game.py:188 / decision_loop.py:272）。
    emit(
        AuditKind.PROTOCOL_RECOVERED,
        {"area": "game_session", "reason": "next_item 异常: TimeoutError", "retry_delay_seconds": 0.5},
        stage_attempt_id="st-1",
        game_id="G1",
    )
    emit(
        AuditKind.PROTOCOL_RECOVERED,
        {"trigger": "incremental", "reasons": ["unknown_event:x"], "streak": 1},
        stage_attempt_id="st-1",
        game_id="G1",
        trigger_seq=10,
    )
    emit(
        AuditKind.PROTOCOL_RECOVERED,
        {"area": "decision_loop", "reasons": ["提交前复核不合法"], "window": dict(_WINDOW)},
        stage_attempt_id="st-1",
        game_id="G1",
        round_no=1,
        trigger_seq=10,
        decision_id="d1",
    )

    # GAME_FINISHED 双层记录（game_task.py:135 + official/game.py:265）。
    emit(
        AuditKind.GAME_FINISHED,
        {"final_scores": [8, 4, 0, -2], "authoritative_seq": 42},
        stage_attempt_id="st-1",
        game_id="G1",
    )
    emit(
        AuditKind.GAME_FINISHED,
        {"final_scores": [8, 4, 0, -2], "seq": 42},
        stage_attempt_id="st-1",
        game_id="G1",
    )

    # PARTICIPANT_FINISHED（participant_runtime.py:173 的 reason/detail 形态）。
    emit(
        AuditKind.PARTICIPANT_FINISHED,
        {"reason": "tournament_finished", "detail": "赛事进入终态 finished"},
    )

    # 全部入队且无降级：修复前 6/8 种类在这里被拒（blocker 的实测现象）。
    assert len(receipts) == 24
    assert all(receipt.queued for receipt in receipts)
    assert all(not receipt.audit_degraded for receipt in receipts)

    summary = await trail.aclose(timeout_seconds=5.0)
    # 24 条业务记录 + 1 条关闭证据 LIFECYCLE_CHANGED(producer_summary)
    # （audit-plus-v1，2026-09-05：关闭前必发，见 audit.py aclose）。
    assert summary.written == 25
    assert summary.serialization_failures == 0
    assert summary.missing_high_priority == 0
    assert summary.dropped_low_priority == 0
    assert summary.audit_degraded is False

    report = validate_run(tmp_path / "runs" / "run-wired")
    assert report["audit_complete"] is True
    assert report["secret_scan_clean"] is True
    assert report["counts_by_kind"]["submission_intent"] == 4
    assert report["counts_by_kind"]["submission_outcome"] == 4
    assert report["counts_by_kind"]["raw_protocol_state"] == 4
    # 原始事件覆盖统计与严格检查（raw_retention 模式声明后启用）。
    assert report["raw_events"]["retention_mode"] == "per_game_files"
    assert report["raw_events"]["by_source"] == {
        "action_submit_response": 2,
        "state_response": 2,
    }
    assert report["raw_events"]["state_polled_games"] == 1
    assert report["raw_events"]["state_stream_games"] == 1
    assert report["raw_events"]["action_responses"] == 2

    submissions = report["submissions"]
    assert submissions["distinct_attempts"] == 2
    # 两种 outcome 形态（类名 + 规范值）归并进同一词表桶。
    assert submissions["outcome_histogram"] == {"accepted": 2, "rejected_retryable": 2}
    assert submissions["rejected_total"] == 2
    assert submissions["latency_ms"]["attempts"] == 2
    assert submissions["latency_ms"]["p50"] == 102
    assert submissions["latency_ms"]["p95"] == 301
    assert submissions["latency_ms"]["max"] == 301

    coverage = report["coverage"]
    assert coverage["games_finished"] == 1
    assert coverage["participants_finished"] == 1
    assert coverage["decisions_planned"] == 2
    assert coverage["rule_degradations"] == 1
    assert coverage["manifest_present"] is True

    # 双层记录（应用层 + 官方适配器各一次）是正常形态：不得报告为重复，
    # 也不影响完整判定（三条及以上同层重复才识别，见 assembly 裁定测试）。
    warning_codes = {
        finding["code"] for finding in report["findings"] if finding["severity"] == "warning"
    }
    assert "duplicate_intent" not in warning_codes
    assert "duplicate_outcome" not in warning_codes
    assert "duplicate_game_finished" not in warning_codes
    assert report["violation_count"] == 0
