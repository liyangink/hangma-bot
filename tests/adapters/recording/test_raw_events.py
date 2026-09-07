"""原始事件词汇与构造器测试：稳定词表、payload 形状与 JSON 可序列化。

锁定 raw_events 的生产口径：官方适配器接线（接线清单见
doc/implementation/notes/audit-raw-retention.md）与验证器共享同一词表，
任何一方的字段漂移都会被这里的契约测试拦截。
"""

import json

import pytest

from hangma_bot.adapters.recording.raw_events import (
    RAW_EVENT_SOURCES,
    RAW_PAYLOAD_SCHEMA_VERSION,
    RAW_SOURCE_ACTION_RESPONSE,
    RAW_SOURCE_SSE_FRAME,
    RAW_SOURCE_STATE_RESPONSE,
    build_action_response_payload,
    build_sse_frame_payload,
    build_state_response_payload,
    is_new_shape_raw_payload,
)


class TestVocabulary:
    def test_sources_are_frozen_vocabulary(self):
        # match_response 为 parallel-v1 契约扩展（§3.3）：自由赛线完整匹配
        # 响应原文的新来源，与既有三种来源同处冻结词表。
        assert RAW_EVENT_SOURCES == frozenset({
            "http_response", "notify_response",
            "state_response",
            "action_submit_response",
            "sse_frame",
            "match_response",
        })
        assert RAW_PAYLOAD_SCHEMA_VERSION == 1

    def test_state_response_payload_shape(self):
        payload = build_state_response_payload(
            endpoint="GET /api/games/G1/state",
            http_status=200,
            seq_requested=0,
            seq_observed=10,
            request_no=3,
            raw='{"seq": 10, "snapshot": {"phase": "draw"}}',
        )
        assert payload == {
            "payload_schema_version": 1,
            "source": "state_response",
            "endpoint": "GET /api/games/G1/state",
            "http_status": 200,
            "seq_requested": 0,
            "seq_observed": 10,
            "request_no": 3,
            "raw": '{"seq": 10, "snapshot": {"phase": "draw"}}',
        }
        # payload 必须可序列化为标准 JSON（入队即编码的硬前提）。
        json.dumps(payload)

    def test_state_response_seq_observed_optional(self):
        # pending/错误体没有权威序号：seq_observed 可空且不落键。
        payload = build_state_response_payload(
            endpoint="GET /api/games/G1/state",
            http_status=200,
            seq_requested=7,
            seq_observed=None,
            request_no=4,
            raw='{"pending": true}',
        )
        assert "seq_observed" not in payload

    def test_action_response_payload_carries_attempt_key(self):
        payload = build_action_response_payload(
            endpoint="POST /api/games/G1/action",
            http_status=409,
            decision_id="dec-1",
            attempt_no=2,
            raw='{"code": "INVALID_ACTION"}',
        )
        assert payload["source"] == RAW_SOURCE_ACTION_RESPONSE
        assert payload["decision_id"] == "dec-1"
        assert payload["attempt_no"] == 2
        assert payload["http_status"] == 409
        assert payload["raw"].startswith("{")  # 409 拒绝体原文完整保留

    def test_sse_frame_reserved_seam(self):
        payload = build_sse_frame_payload(
            endpoint="GET /api/games/G1/notify",
            seq=42,
            closed=False,
            raw='{"seq": 42}',
        )
        assert payload["source"] == RAW_SOURCE_SSE_FRAME
        assert "http_status" not in payload  # SSE 帧不是 HTTP 响应
        assert payload["seq"] == 42
        assert payload["closed"] is False

    def test_sse_closed_frame(self):
        payload = build_sse_frame_payload(
            endpoint="GET /api/games/G1/notify",
            seq=None,
            closed=True,
            raw='{"seq": 9, "closed": true}',
        )
        assert "seq" not in payload
        assert payload["closed"] is True

    def test_raw_must_be_string(self):
        with pytest.raises(TypeError):
            build_state_response_payload(
                endpoint="GET /api/games/G1/state",
                http_status=200,
                seq_requested=0,
                seq_observed=1,
                request_no=1,
                raw={},  # 非字符串原文：序列化层会整条拒绝，这里尽早失败
            )


class TestNewShapeDetection:
    def test_new_shape_detected_by_payload_schema_version(self):
        assert is_new_shape_raw_payload({"payload_schema_version": 1, "source": "sse_frame"})
        assert not is_new_shape_raw_payload({"raw": {"any": ["shape"]}})  # 旧形态容忍
        assert not is_new_shape_raw_payload("不是对象")
        assert not is_new_shape_raw_payload(None)
