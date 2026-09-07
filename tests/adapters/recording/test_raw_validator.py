"""原始事件完整性检查的验证器测试：缺口、流缺失、动作响应缺失与旧目录门控。

门控语义（audit-raw-retention 设计）：严格检查只在运行级 summary.json
声明 raw_retention 模式时启用；旧目录（如 2026-09-04 测试赛基线
run-29a71a10ad12441eb15e0ac4cfb55c1d）没有该键，检查整体跳过，
验证结论与升级前一致。
"""

import json

from hangma_bot.adapters.recording import (
    JsonlAuditSink,
    build_action_response_payload,
    build_state_response_payload,
    validate_run,
)
from hangma_bot.application.contracts import AuditKind

from recording._helpers import make_record


def _adapter_window_state(game_id: str = "G1", seq: int = 10):
    """官方场次适配器的窗口权威状态（official/game.py 投递形态）。"""

    return make_record(
        AuditKind.AUTHORITATIVE_STATE,
        {
            "seq": seq,
            "phase": "draw",
            "turn": 0,
            "window": {"game_id": game_id, "round_no": 1, "trigger_seq": seq, "phase": "draw", "seat": 0},
        },
        game_id=game_id,
        round_no=1,
        trigger_seq=seq,
    )


def _state_raw(request_no: int, game_id: str = "G1"):
    return make_record(
        AuditKind.RAW_PROTOCOL_STATE,
        build_state_response_payload(
            endpoint=f"GET /api/games/{game_id}/state",
            http_status=200,
            seq_requested=0,
            seq_observed=10,
            request_no=request_no,
            raw='{"seq": 10}',
        ),
        game_id=game_id,
        round_no=1,
        trigger_seq=10,
    )


def _adapter_attempt(decision_id: str, attempt_no: int, outcome_type: str, **extra):
    """官方适配器 SUBMISSION_OUTCOME（outcome_type 键，POST 已发出形态）。"""

    payload = {
        "decision_id": decision_id,
        "attempt_no": attempt_no,
        "outcome_type": outcome_type,
    }
    payload.update(extra)
    return make_record(
        AuditKind.SUBMISSION_OUTCOME,
        payload,
        game_id="G1",
        round_no=1,
        trigger_seq=10,
        decision_id=decision_id,
        attempt_no=attempt_no,
    )


def _action_raw(decision_id: str, attempt_no: int, http_status: int = 200):
    return make_record(
        AuditKind.RAW_PROTOCOL_STATE,
        build_action_response_payload(
            endpoint="POST /api/games/G1/action",
            http_status=http_status,
            decision_id=decision_id,
            attempt_no=attempt_no,
            raw='{"ok": true}',
        ),
        game_id="G1",
        round_no=1,
        trigger_seq=10,
        decision_id=decision_id,
        attempt_no=attempt_no,
    )


async def _build_raw_run(base, *, request_nos, adapter_outcomes, action_raw_keys):
    sink = JsonlAuditSink(base, "run-raw")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"}))
    sink.emit(_adapter_window_state())
    for no in request_nos:
        sink.emit(_state_raw(no))
    for decision_id, attempt_no, outcome_type, extra in adapter_outcomes:
        sink.emit(
            make_record(
                AuditKind.SUBMISSION_INTENT,
                {"action_key": "discard:1w", "based_on_authoritative_seq": 10},
                game_id="G1",
                round_no=1,
                trigger_seq=10,
                decision_id=decision_id,
                attempt_no=attempt_no,
            )
        )
        sink.emit(_adapter_attempt(decision_id, attempt_no, outcome_type, **extra))
    for decision_id, attempt_no in action_raw_keys:
        sink.emit(_action_raw(decision_id, attempt_no))
    sink.emit(make_record(AuditKind.GAME_FINISHED, {"final_scores": [1, 2, 3, 4]}, game_id="G1"))
    sink.emit(make_record(AuditKind.PARTICIPANT_FINISHED, {"reason": "tournament_finished", "detail": "done"}))
    await sink.aclose(timeout_seconds=5.0)
    return base / "runs" / "run-raw"


async def test_complete_raw_stream_passes(tmp_path):
    """request_no 连续 + 每个已发 POST 有响应原文：判定完整。"""

    run_dir = await _build_raw_run(
        tmp_path,
        request_nos=(1, 2, 3),
        adapter_outcomes=[("d1", 1, "SubmitAccepted", {})],
        action_raw_keys=[("d1", 1)],
    )
    report = validate_run(run_dir)
    assert report["audit_complete"] is True
    assert report["raw_events"]["retention_mode"] == "per_game_files"
    assert report["raw_events"]["state_stream_games"] == 1
    assert report["raw_events"]["action_responses"] == 1


async def test_state_request_no_gap_is_violation(tmp_path):
    """request_no 缺中间值 = 该次响应原文丢失：violation。"""

    run_dir = await _build_raw_run(
        tmp_path,
        request_nos=(1, 2, 4, 5),
        adapter_outcomes=[("d1", 1, "SubmitAccepted", {})],
        action_raw_keys=[("d1", 1)],
    )
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "raw_state_gap" in codes
    # F-21：violation 附注背压丢弃计数，接线缺失与背压丢弃两种红因可区分
    gap = next(f for f in report["findings"] if f["code"] == "raw_state_gap")
    assert "raw_retention.dropped=" in gap["detail"]
    assert report["audit_complete"] is False


async def test_session_restart_renumbering_is_not_a_gap(tmp_path):
    """会话重启从 1 重新计数：按会话段对账，完整段不得误报缺口。

    （官方适配器在监督重开会话时创建新 OfficialGameSession，计数器归零；
    记录顺序中严格回退 = 新会话段起点，段内 1..N 完整即干净。）
    """

    run_dir = await _build_raw_run(
        tmp_path,
        request_nos=(1, 2, 3, 1, 2),
        adapter_outcomes=[("d1", 1, "SubmitAccepted", {})],
        action_raw_keys=[("d1", 1)],
    )
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "raw_state_gap" not in codes
    assert report["audit_complete"] is True


async def test_restart_segment_head_loss_is_violation(tmp_path):
    """重启后新会话段首条记录整体丢失（数值恰被上一段覆盖）必须检出。

    第一段 1..30 完整；重启后第二段前 5 条成功响应的原文丢失，只记录到
    6..15。旧"全局取值集合连续"看到 1..30 ∪ 6..15 = 1..30 会漏报；按
    会话段对账后第二段不从 1 起 = 段首缺失（d6 登记项盲区 b）。
    """

    run_dir = await _build_raw_run(
        tmp_path,
        request_nos=tuple(range(1, 31)) + tuple(range(6, 16)),
        adapter_outcomes=[("d1", 1, "SubmitAccepted", {})],
        action_raw_keys=[("d1", 1)],
    )
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "raw_state_gap" in codes
    gap = next(f for f in report["findings"] if f["code"] == "raw_state_gap")
    assert "第2会话段段首缺失" in gap["detail"]
    assert "request_no 缺失 [1, 2, 3, 4, 5]" in gap["detail"]
    assert "raw_retention.dropped=" in gap["detail"]
    assert report["audit_complete"] is False


async def test_restart_with_error_placeholder_zeros_is_not_a_gap(tmp_path):
    """重启段先落 request_no=0 的错误占位、成功后从 1 计数：不得误报。

    official/game.py 非 2xx 失败用当前计数发射错误原文、不递增；新会话
    首批请求失败时占位为 0，随后成功才从 1 编号。0 占位既不是段首缺失
    也不产生缺号（正常重启不误报的补充形态：回退目标可能是 0 而非 1）。
    """

    run_dir = await _build_raw_run(
        tmp_path,
        request_nos=(1, 2, 3, 0, 0, 1, 2, 3),
        adapter_outcomes=[("d1", 1, "SubmitAccepted", {})],
        action_raw_keys=[("d1", 1)],
    )
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "raw_state_gap" not in codes
    assert report["audit_complete"] is True


async def test_mid_segment_gap_after_restart_still_reported(tmp_path):
    """重启后的新段内真缺仍报：段对账只放宽"回退"，不放宽"缺号"。

    第二段 1..2、4..5 中缺 3（该次响应原文丢失），跨会话段也必须是
    violation（登记项盲区 a 的反面：段内真缺仍报）。
    """

    run_dir = await _build_raw_run(
        tmp_path,
        request_nos=(1, 2, 3, 1, 2, 4, 5),
        adapter_outcomes=[("d1", 1, "SubmitAccepted", {})],
        action_raw_keys=[("d1", 1)],
    )
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "raw_state_gap" in codes
    gap = next(f for f in report["findings"] if f["code"] == "raw_state_gap")
    assert "第2会话段段内缺号" in gap["detail"]
    assert "request_no 缺失 [3]" in gap["detail"]
    assert report["audit_complete"] is False


async def test_multiple_complete_restart_segments_pass(tmp_path):
    """多次重启且各段都完整（长短不一）：按段对账全部干净。"""

    run_dir = await _build_raw_run(
        tmp_path,
        request_nos=(1, 2, 1, 2, 3, 4, 5, 1, 2, 3),
        adapter_outcomes=[("d1", 1, "SubmitAccepted", {})],
        action_raw_keys=[("d1", 1)],
    )
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "raw_state_gap" not in codes
    assert report["audit_complete"] is True


async def test_missing_state_stream_is_violation(tmp_path):
    """场次有状态请求证据但没有 state_response 原文流：violation。

    auto-evidence 门控：本运行有另一场（G2）的原始事件证据 → 汇总声明
    raw_retention → 严格检查启用 → G1 有轮询证据却零原文被揪出。
    """

    sink = JsonlAuditSink(tmp_path, "run-nostream")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"}))
    sink.emit(_adapter_window_state(game_id="G1"))  # 证明 G1 做过状态请求
    # G2 有原始事件证据：让运行整体进入 raw_retention 严格模式。
    sink.emit(_adapter_window_state(game_id="G2", seq=20))
    sink.emit(_state_raw(1, game_id="G2"))
    sink.emit(make_record(AuditKind.PARTICIPANT_FINISHED, {"reason": "tournament_finished", "detail": "done"}))
    await sink.aclose(timeout_seconds=5.0)
    report = validate_run(tmp_path / "runs" / "run-nostream")
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "raw_state_stream_empty" in codes
    assert report["audit_complete"] is False


async def test_run_without_any_raw_evidence_stays_legacy(tmp_path):
    """auto-evidence：完全没有新形态原始事件 → 不声明模式、严格检查跳过。

    这保证"适配器尚未接线"的过渡期运行（以及历史旧目录）不会被误报：
    接线缺失在接线完成后由主会话按接线清单保证，验证器不制造假阳性。
    """

    sink = JsonlAuditSink(tmp_path, "run-prewire")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"}))
    sink.emit(_adapter_window_state())  # 有轮询证据但没有原始事件（未接线形态）
    sink.emit(make_record(AuditKind.PARTICIPANT_FINISHED, {"reason": "tournament_finished", "detail": "done"}))
    await sink.aclose(timeout_seconds=5.0)
    report = validate_run(tmp_path / "runs" / "run-prewire")
    assert report["raw_events"]["retention_mode"] == "legacy"
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert not {"raw_state_gap", "raw_state_stream_empty", "raw_action_missing"} & codes
    assert report["audit_complete"] is True


async def test_missing_action_response_is_violation(tmp_path):
    """POST 已发出但没有 action_submit_response 原文：violation。"""

    run_dir = await _build_raw_run(
        tmp_path,
        request_nos=(1, 2),
        adapter_outcomes=[
            ("d1", 1, "SubmitAccepted", {}),
            ("d2", 1, "SubmitRejectedRetryable", {"official_code": "409"}),
        ],
        action_raw_keys=[("d1", 1)],  # d2 缺原文
    )
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "raw_action_missing" in codes
    assert report["audit_complete"] is False


async def test_not_sent_and_in_flight_cancel_do_not_require_raw(tmp_path):
    """未发 POST 与在途取消没有响应可录：不要求原文，判定完整。"""

    run_dir = await _build_raw_run(
        tmp_path,
        request_nos=(1, 2),
        adapter_outcomes=[
            ("d1", 1, "SubmitNotSent", {"reason": "deadline_passed"}),
            ("d2", 1, "SubmitAmbiguous", {"reason": "submit_cancelled_in_flight"}),
        ],
        action_raw_keys=[],
    )
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "raw_action_missing" not in codes
    assert report["audit_complete"] is True


async def test_legacy_run_without_retention_declaration_skips_checks(tmp_path):
    """旧目录：summary.json 无 raw_retention 键，严格检查整体跳过。

    构造一个"升级前形态"的目录：raw 记录缺失、有 adapter 层 outcome，
    升级前这类目录只要核心链完整就判定 ok——门控保证结论不漂移。
    """

    sink = JsonlAuditSink(tmp_path, "run-legacy")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"}))
    sink.emit(_adapter_window_state())
    sink.emit(
        make_record(
            AuditKind.SUBMISSION_INTENT,
            {"action_key": "discard:1w", "based_on_authoritative_seq": 10},
            game_id="G1",
            round_no=1,
            trigger_seq=10,
            decision_id="d1",
            attempt_no=1,
        )
    )
    sink.emit(_adapter_attempt("d1", 1, "SubmitAccepted"))
    sink.emit(make_record(AuditKind.PARTICIPANT_FINISHED, {"reason": "tournament_finished", "detail": "done"}))
    await sink.aclose(timeout_seconds=5.0)

    run_dir = tmp_path / "runs" / "run-legacy"
    # 模拟升级前目录：剥掉 summary.json 里的 raw_retention 声明。
    summary_path = run_dir / "summary.json"
    document = json.loads(summary_path.read_text(encoding="utf-8"))
    document.pop("raw_retention", None)
    summary_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    report = validate_run(run_dir)
    assert report["raw_events"]["retention_mode"] == "legacy"
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert not {"raw_state_gap", "raw_state_stream_empty", "raw_action_missing"} & codes
    assert report["audit_complete"] is True


async def test_raw_payloads_are_covered_by_secret_scan(tmp_path):
    """新记录类型同样经受脱敏扫描：原文残留凭证形态必须被拦截。"""

    sink = JsonlAuditSink(tmp_path, "run-secret")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"}))
    # 写入侧第二道防御性脱敏：Bearer 形态在入队前被替换。
    sink.emit(
        make_record(
            AuditKind.RAW_PROTOCOL_STATE,
            build_state_response_payload(
                endpoint="GET /api/games/G1/state",
                http_status=200,
                seq_requested=0,
                seq_observed=1,
                request_no=1,
                raw='{"header": "Authorization: Bearer realshouldneverland"}',
            ),
            game_id="G1",
        )
    )
    await sink.aclose(timeout_seconds=5.0)
    report = validate_run(tmp_path / "runs" / "run-secret")
    assert report["secret_scan_clean"] is True
    raw_file = (
        tmp_path / "runs" / "run-secret" / "participants" / "P1" / "raw" / "G1.jsonl"
    )
    text = raw_file.read_text(encoding="utf-8")
    assert "realshouldneverland" not in text

    # 注入一条绕过写入侧脱敏的旧记录（模拟旧版记录器污染）：扫描必须命中。
    leaked = {
        "schema_version": 1,
        "kind": "raw_protocol_state",
        "context": {
            "run_id": "run-secret",
            "tournament_id": "t-1",
            "participant_id": "P1",
            "game_id": "G1",
        },
        "wall_time_unix_ms": 1,
        "monotonic_ns": 1,
        "payload": {
            "payload_schema_version": 1,
            "source": "state_response",
            "raw": '{"auth": "Bearer leaked99"}',
        },
    }
    with raw_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(leaked, ensure_ascii=False) + "\n")
    report = validate_run(tmp_path / "runs" / "run-secret")
    assert report["secret_scan_clean"] is False


async def test_request_id_detects_dropped_body_even_when_success_counters_look_contiguous(tmp_path):
    sink = JsonlAuditSink(tmp_path, 'http-missing')
    for request_id in ('kept', 'cancelled-missing'):
        for phase in ('started', 'finished'):
            sink.emit(make_record(AuditKind.HTTP_REQUEST, {
                'request_id': request_id, 'phase': phase, 'endpoint': 'GET /api/me',
                'outcome': 'cancelled' if request_id == 'cancelled-missing' else 'response',
            }))
    sink.emit(make_record(AuditKind.RAW_PROTOCOL_STATE, {
        'payload_schema_version': 1, 'source': 'http_response', 'request_id': 'kept',
        'endpoint': 'GET /api/me', 'http_status': 200, 'raw': '{}',
    }))
    await sink.aclose(timeout_seconds=2)
    report = validate_run(tmp_path / 'runs' / 'http-missing')
    issues = [f for f in report['findings'] if f['code'] == 'http_request_incomplete']
    assert len(issues) == 1 and 'cancelled-missing' in issues[0]['detail']
