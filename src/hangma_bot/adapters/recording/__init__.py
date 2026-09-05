"""结构化审计记录适配器。

公开面：

- ``JsonlAuditSink``：``AuditSink`` 的第一阶段真实实现（``jsonl_sink``）。
- ``validate_run`` / ``main``：离线审计验证器及其命令行入口（``validator``）。
- ``redact_value`` / ``redact_json_line``：第二道防御性脱敏（``redact``）。
- ``schema`` 中的静态契约：优先级、payload 校验、文件路由与版本常量。
- ``summary`` 的纯函数汇总组装器。

依赖方向：本包只依赖 ``kernel`` 与 ``application.contracts`` 的冻结类型，
不反向被任何线上决策模块依赖；具体实例只能由 ``bootstrap`` 组合根创建。
"""

from hangma_bot.adapters.recording.jsonl_sink import JsonlAuditSink
from hangma_bot.adapters.recording.raw_events import (
    RAW_EVENT_SOURCES,
    RAW_PAYLOAD_SCHEMA_VERSION,
    RAW_SOURCE_ACTION_RESPONSE,
    RAW_SOURCE_MATCH_RESPONSE,
    RAW_SOURCE_SSE_FRAME,
    RAW_SOURCE_STATE_RESPONSE,
    build_action_response_payload,
    build_match_response_payload,
    build_sse_frame_payload,
    build_state_response_payload,
    is_new_shape_raw_payload,
)
from hangma_bot.adapters.recording.redact import (
    REDACTED,
    redact_json_line,
    redact_value,
)
from hangma_bot.adapters.recording.schema import (
    AUDIT_SCHEMA_VERSION,
    is_high_priority,
    relative_path_for,
    sanitize_component,
    validate_payload,
)
from hangma_bot.adapters.recording.summary import (
    build_participant_summary,
    build_run_summary,
)
from hangma_bot.adapters.recording.validator import main, validate_run

__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "JsonlAuditSink",
    "RAW_EVENT_SOURCES",
    "RAW_PAYLOAD_SCHEMA_VERSION",
    "RAW_SOURCE_ACTION_RESPONSE",
    "RAW_SOURCE_MATCH_RESPONSE",
    "RAW_SOURCE_SSE_FRAME",
    "RAW_SOURCE_STATE_RESPONSE",
    "REDACTED",
    "build_action_response_payload",
    "build_match_response_payload",
    "build_participant_summary",
    "build_run_summary",
    "build_sse_frame_payload",
    "build_state_response_payload",
    "is_high_priority",
    "is_new_shape_raw_payload",
    "main",
    "redact_json_line",
    "redact_value",
    "relative_path_for",
    "sanitize_component",
    "validate_payload",
    "validate_run",
]
