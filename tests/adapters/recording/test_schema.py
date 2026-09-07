"""审计种类优先级、payload 校验基准与文件路由的静态契约测试。

校验基准遵循最小校验原则（返工定案）：只校验"payload 是对象"与
"验证器实际消费字段存在时类型正确"，不强制必填词表；
本文件用当前生产代码的真实 payload 形态作通过样本锁定该原则。
"""

from hangma_bot.adapters.recording.schema import (
    AUDIT_SCHEMA_VERSION,
    CANONICAL_OUTCOME_VALUES,
    PAYLOAD_SCHEMA_VERSIONS,
    RUN_MANIFEST_PATH,
    canonical_outcome,
    is_high_priority,
    relative_path_for,
    sanitize_component,
    validate_payload,
)
from hangma_bot.application.contracts import AuditKind

# 真实生产方 payload 形态（来源见 schema.py 模块 docstring 的生产形态清单；
# 锁定"真实生产记录必须通过校验"，防止再次单方面发明必填词表）。
_REAL_PRODUCER_PAYLOADS = {
    AuditKind.RUN_MANIFEST: {
        "run_id": "run-1",
        "mode": "test_room",
        "expected_tournament_id": "t-9",
        "known_guide_version": 8,
        "guide_version": 8,
        "guide_updated_at": "2026-09-03T00:00:00Z",
        "participant_id": "P1",
        "ruleset_version": "v1",
        "max_games": 1,
        "rounds_per_game": 1,
        "timing": {"peng_timeout_sec": 1.0, "chi_timeout_sec": 3.0, "discard_timeout_sec": 5.0},
    },
    AuditKind.LIFECYCLE_CHANGED: {"event": "status_changed", "from": None, "to": "running"},
    AuditKind.AUTHORITATIVE_STATE: {
        "status": "running",
        "stage_no": 1,
        "stage_observed_revision": 3,
        "stage_role": "main",
        "stage_total": 2,
        "stage_crashed": False,
        "qualified": True,
        "qualify_role": "main",
        "active_games": ["G1"],
        "my_games": ["G1"],
        "observed_at_unix_ms": 1800000000000,
    },
    # 2026-09-04 审计增强后的新形态（raw_events 构造器）；旧形态照常放行。
    AuditKind.RAW_PROTOCOL_STATE: {
        "payload_schema_version": 1,
        "source": "state_response",
        "endpoint": "GET /api/games/G1/state",
        "http_status": 200,
        "seq_requested": 0,
        "seq_observed": 10,
        "request_no": 1,
        "raw": '{"seq": 10}',
    },
    AuditKind.DECISION_PLANNED: {
        "plan_revision": 1,
        "based_on_authoritative_seq": 10,
        "trigger_seq": 10,
        "window": {"game_id": "G1", "round_no": 1, "trigger_seq": 10, "phase": "response_peng", "seat": 2},
        "candidates": [{"action_key": "peng:1w", "is_emergency": False}],
        "degraded_reasons": [],
        "rule_completeness": "complete",
    },
    AuditKind.SUBMISSION_INTENT: {
        "action_key": "peng:1w",
        "is_emergency": False,
        "based_on_authoritative_seq": 10,
        "plan_revision": 1,
        "latest_send_at_monotonic": 103.0,
        "window": {"game_id": "G1", "round_no": 1, "trigger_seq": 10, "phase": "response_peng", "seat": 2},
    },
    # 应用层 _outcome_payload 用封闭结果类名；适配器 _finish_submit 用 outcome_type。
    AuditKind.SUBMISSION_OUTCOME: {
        "outcome": "SubmitRejectedRetryable",
        "window": {"game_id": "G1", "round_no": 1, "trigger_seq": 10, "phase": "response_peng", "seat": 2},
        "official_code": "409",
        "rejected_action_key": "peng:1w",
    },
    AuditKind.PROTOCOL_RECOVERED: {
        "area": "game_session",
        "reason": "next_item 异常: TimeoutError",
        "retry_delay_seconds": 0.5,
    },
    AuditKind.GAME_FINISHED: {"final_scores": [8, 4, 0, -2], "authoritative_seq": 42},
    AuditKind.PARTICIPANT_FINISHED: {"reason": "tournament_finished", "detail": "赛事进入终态"},
}


class TestPriority:
    """优先级由记录器固定：除 RAW_PROTOCOL_STATE 外全部高优先级。"""

    def test_every_kind_has_fixed_priority(self):
        for kind in AuditKind:
            assert is_high_priority(kind) in (True, False)

    def test_only_raw_protocol_state_is_low_priority(self):
        low = {kind for kind in AuditKind if not is_high_priority(kind)}
        assert low == {AuditKind.RAW_PROTOCOL_STATE}

    def test_payload_schema_versions_cover_all_kinds(self):
        assert set(PAYLOAD_SCHEMA_VERSIONS) == set(AuditKind)
        assert set(PAYLOAD_SCHEMA_VERSIONS.values()) == {1}
        assert AUDIT_SCHEMA_VERSION == 1


class TestMinimalPayloadValidation:
    """最小校验基准：真实生产 payload 全部通过；只查对象性与消费字段类型。"""

    def test_real_producer_payloads_all_pass(self):
        for kind, payload in _REAL_PRODUCER_PAYLOADS.items():
            assert validate_payload(kind, payload) == (), kind.value

    def test_missing_and_extra_fields_are_accepted(self):
        # 不强制必填词表：空对象与任意额外字段都放行。
        for kind in AuditKind:
            assert validate_payload(kind, {}) == ()
        assert validate_payload(AuditKind.LIFECYCLE_CHANGED, {"event": "x", "任意": 1}) == ()

    def test_payload_must_be_mapping(self):
        assert validate_payload(AuditKind.LIFECYCLE_CHANGED, ["not", "a", "dict"])
        assert validate_payload(AuditKind.LIFECYCLE_CHANGED, "text")

    def test_consumed_fields_type_checked_only_when_present(self):
        # outcome/outcome_type 存在时必须是字符串（验证器做词表归并的主字段）。
        assert validate_payload(AuditKind.SUBMISSION_OUTCOME, {"outcome": "SubmitAccepted"}) == ()
        assert validate_payload(AuditKind.SUBMISSION_OUTCOME, {"outcome_type": "SubmitFatal"}) == ()
        assert validate_payload(AuditKind.SUBMISSION_OUTCOME, {"outcome": 409})
        assert validate_payload(AuditKind.SUBMISSION_OUTCOME, {"outcome_type": None})
        # degraded_reasons 存在时必须是数组（计划提示统计消费，不等同规则降级）。
        assert validate_payload(AuditKind.DECISION_PLANNED, {"degraded_reasons": ["x"]}) == ()
        assert validate_payload(AuditKind.DECISION_PLANNED, {"degraded_reasons": "x"})
        # 缺省一律放行。
        assert validate_payload(AuditKind.SUBMISSION_OUTCOME, {}) == ()


class TestCanonicalOutcome:
    """提交结果词表归并：规范小写值与封闭结果类名两种生产形态等价。"""

    def test_class_names_map_to_canonical_values(self):
        mapping = {
            "SubmitAccepted": "accepted",
            "SubmitRejectedRetryable": "rejected_retryable",
            "SubmitRejectedClosed": "rejected_closed",
            "SubmitAmbiguous": "ambiguous",
            "SubmitNotSent": "not_sent",
            "SubmitFatal": "fatal",
        }
        for class_name, canonical in mapping.items():
            assert canonical_outcome(class_name) == canonical

    def test_canonical_values_pass_through(self):
        for value in CANONICAL_OUTCOME_VALUES:
            assert canonical_outcome(value) == value

    def test_unknown_values_pass_through_for_counting(self):
        assert canonical_outcome("maybe") == "maybe"
        assert canonical_outcome("SubmitWeird") == "SubmitWeird"


class TestRoutingAndSanitize:
    """路由必须包含参赛身份；组件消毒阻断路径穿越。"""

    def test_run_level_paths(self):
        assert RUN_MANIFEST_PATH == "manifest.json"
        assert relative_path_for(AuditKind.RUN_MANIFEST, "P1", None) == "manifest.json"
        assert relative_path_for(AuditKind.LIFECYCLE_CHANGED, "P1", None) == "lifecycle.jsonl"

    def test_decision_and_game_paths_include_participant(self):
        assert (
            relative_path_for(AuditKind.SUBMISSION_INTENT, "P1", "G1")
            == "participants/P1/decisions.jsonl"
        )
        assert (
            relative_path_for(AuditKind.AUTHORITATIVE_STATE, "P1", "G1")
            == "participants/P1/games/G1.jsonl"
        )
        assert (
            relative_path_for(AuditKind.GAME_FINISHED, "P2", "G9")
            == "participants/P2/games/G9.jsonl"
        )

    def test_game_scoped_without_game_id_falls_back_to_decisions(self):
        # 场内种类缺 game_id 时记录不丢失，落到身份级文件。
        assert (
            relative_path_for(AuditKind.AUTHORITATIVE_STATE, "P1", None)
            == "participants/P1/decisions.jsonl"
        )

    def test_raw_protocol_state_routes_to_raw_directory(self):
        # 原始事件全量保留：与关键事实流分文件，便于 gzip 轮转与按需备份。
        assert (
            relative_path_for(AuditKind.RAW_PROTOCOL_STATE, "P1", "G1")
            == "participants/P1/raw/G1.jsonl"
        )
        assert (
            relative_path_for(AuditKind.RAW_PROTOCOL_STATE, "P1", None)
            == "participants/P1/raw/global.jsonl"
        )
        # 路径穿越防护对 raw 组件同样生效。
        assert (
            relative_path_for(AuditKind.RAW_PROTOCOL_STATE, "../../x", "..")
            == "participants/.._.._x/raw/unnamed.jsonl"
        )

    def test_raw_source_field_type_checked_only_when_present(self):
        # 验证器按 source 分组统计：存在时必须是字符串，缺失（旧形态）放行。
        assert validate_payload(AuditKind.RAW_PROTOCOL_STATE, {"source": "sse_frame"}) == ()
        assert validate_payload(AuditKind.RAW_PROTOCOL_STATE, {"source": 7})
        assert validate_payload(AuditKind.RAW_PROTOCOL_STATE, {"raw": "legacy"}) == ()

    def test_sanitize_blocks_traversal_and_empty(self):
        assert sanitize_component("../../etc") == ".._.._etc"
        assert "/" not in sanitize_component("a/b\\c")
        assert sanitize_component("") == "unnamed"
        assert sanitize_component(".") == "unnamed"
        assert sanitize_component("..") == "unnamed"
        assert len(sanitize_component("x" * 500)) == 120

    def test_sanitize_keeps_plain_official_ids(self):
        assert sanitize_component("g-20260903_01") == "g-20260903_01"
