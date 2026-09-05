"""RAW_PROTOCOL_STATE 原始协议事件的产生词汇与 payload 构造器。

背景（2026-09-04 测试赛审计复盘）：决策侧审计只能证明“我们做了什么”，
不能证明“官方当时说了什么”。97 次胡牌被拒无法本地复盘，根因是
decision_planned 没有手牌、审计目录也没有任何 /state 响应原文。
本模块把 adapter 层收发原始事件的生产口径集中成一套稳定词汇，
供官方适配器（接线清单见 doc/implementation/notes/audit-raw-retention.md）
与验证器共享，避免生产方各自发明字段。

设计约束：

1. **全量保留**：每个 /state 响应、每次动作 POST 响应（含 409/429 拒绝体）
   都应当各产生一条记录，不抽样、不按体积丢弃；压力下的计数丢弃只能由
   记录器既有低优先级淘汰语义发生（见 jsonl_sink），丢弃数与
   audit_degraded 保证可见。
2. **脱敏分层**：raw 字段必须是传输层已经完成 Token 原文替换的响应
   文本（OfficialTransport.request 对响应体做 token → *** 精确替换）；
   记录器在入队前还会做第二道防御性脱敏（redact_value/redact_json_line）。
3. **信息权限**：/state 响应是官方按我方座位返回的玩家视图，只含本人
   手牌与公开事实；原文落盘不改变信息权限边界（他家手牌、未来牌墙不会
   出现在玩家接口，API 文档 §2.3 私有信息规则）。
4. **原文不解析**：raw 保存序列化后的协议文本原样，解析由
   dto.parse_state_response 在另一条数据流完成——审计存证与业务解析
   互不耦合，坏报文仍可落盘供赛后诊断。
"""

from __future__ import annotations

from typing import Any

# 原始事件来源词表：payload.source 的规范取值。验证器按该词表做
# 完整性检查与覆盖统计；新增来源必须同步验证器与文档。
RAW_SOURCE_STATE_RESPONSE = "state_response"  # GET /api/games/{id}/state 响应原文（含全量快照/增量事件/pending）
RAW_SOURCE_ACTION_RESPONSE = "action_submit_response"  # POST /api/games/{id}/action 响应原文（含 409/429 拒绝体）
RAW_SOURCE_SSE_FRAME = "sse_frame"  # 预留：GET /api/games/{id}/notify SSE 帧（另一工作线 notify 客户端接入）

# 原始事件 payload 子结构版本：未来收紧/新增必填字段时递增，
# 与信封 schema_version（=1）解耦——信封兼容旧读取器，子结构自演进。
RAW_PAYLOAD_SCHEMA_VERSION = 1

RAW_EVENT_SOURCES = frozenset(
    {
        RAW_SOURCE_STATE_RESPONSE,
        RAW_SOURCE_ACTION_RESPONSE,
        RAW_SOURCE_SSE_FRAME,
    }
)

_FIELD_PAYLOAD_SCHEMA_VERSION = "payload_schema_version"
_FIELD_SOURCE = "source"
_FIELD_ENDPOINT = "endpoint"
_FIELD_HTTP_STATUS = "http_status"
_FIELD_RAW = "raw"

def _base(
    *,
    source: str,
    endpoint: str,
    http_status: int | None,
    raw: str,
) -> dict[str, Any]:
    """组装公共字段；raw 必须是字符串原文，否则序列化层会整条拒绝。"""

    if not isinstance(raw, str):
        raise TypeError("raw 必须是原始响应文本字符串")
    payload: dict[str, Any] = {
        _FIELD_PAYLOAD_SCHEMA_VERSION: RAW_PAYLOAD_SCHEMA_VERSION,
        _FIELD_SOURCE: source,
        _FIELD_ENDPOINT: endpoint,
        _FIELD_RAW: raw,
    }
    if http_status is not None:
        payload[_FIELD_HTTP_STATUS] = http_status
    return payload

def build_state_response_payload(
    *,
    endpoint: str,
    http_status: int,
    seq_requested: int,
    seq_observed: int | None,
    request_no: int,
    raw: str,
) -> dict[str, Any]:
    """构造一条 /state 响应的原始事件 payload。

    - endpoint：官方端点原样，形如 "GET /api/games/{game_id}/state"；
    - seq_requested：本次请求携带的 seq 参数（0 = seq=0 全量快照，API §2.3）；
    - seq_observed：响应顶层 seq（权威水位）；pending/错误体没有则传 None；
    - request_no：**本场次内** state 请求的单调计数（从 1 起）。跨会话重启
      可以从 1 重新计数——验证器的缺口检查按“取值集合的连续性”判定，
      两次 1..N 的并集仍是连续的，重启不会造成误报；
    - raw：响应文本原文（Token 已由传输层替换）。
    """

    payload = _base(
        source=RAW_SOURCE_STATE_RESPONSE,
        endpoint=endpoint,
        http_status=http_status,
        raw=raw,
    )
    payload["seq_requested"] = seq_requested
    if seq_observed is not None:
        payload["seq_observed"] = seq_observed
    payload["request_no"] = request_no
    return payload

def build_action_response_payload(
    *,
    endpoint: str,
    http_status: int | None,
    decision_id: str,
    attempt_no: int,
    raw: str,
) -> dict[str, Any]:
    """构造一条动作提交响应的原始事件 payload。

    - 关联键 decision_id + attempt_no 与 SUBMISSION_INTENT/OUTCOME 同键：
      验证器据此检查“每个实际发出的 POST 都有响应原文”；
    - http_status 可为 None（响应从未到达，如 POST 超时）：此时 raw 传空串，
      记录本身证明“本次尝试的响应原文不存在”，对账不悬空；
    - raw：响应文本原文（409/429 拒绝体完整保留，Token 已由传输层替换）。
    """

    payload = _base(
        source=RAW_SOURCE_ACTION_RESPONSE,
        endpoint=endpoint,
        http_status=http_status,
        raw=raw,
    )
    payload["decision_id"] = decision_id
    payload["attempt_no"] = attempt_no
    return payload

def build_sse_frame_payload(
    *,
    endpoint: str,
    seq: int | None,
    closed: bool | None,
    raw: str,
) -> dict[str, Any]:
    """构造一条 SSE 通知帧的原始事件 payload（预留接缝）。

    官方 SSE 帧协议（指南 v12，API 文档 §2.3）：初始帧 {"seq": N}、
    变化帧 {"seq": 新水位}、场终帧 {"seq": N, "closed": true}，
    另有 : keepalive 注释行。当前实现不采纳 SSE（工程决策 2026-09-05），
    本构造器为另一工作线的 notify 客户端预留：帧接入后即可与 /state
    原文同文件留存，验证器按 source 统计、不要求帧完整性。
    """

    payload = _base(
        source=RAW_SOURCE_SSE_FRAME,
        endpoint=endpoint,
        http_status=None,
        raw=raw,
    )
    if seq is not None:
        payload["seq"] = seq
    if closed is not None:
        payload["closed"] = closed
    return payload

def is_new_shape_raw_payload(payload: object) -> bool:
    """判断 payload 是否为新版原始事件形态（携带子结构版本号）。

    旧形态（如历史冗余原始快照）没有 payload_schema_version，验证器
    按 legacy 容忍：照常统计与脱敏扫描，但不参与 request_no 缺口检查。
    """

    return (
        isinstance(payload, dict)
        and isinstance(payload.get(_FIELD_PAYLOAD_SCHEMA_VERSION), int)
    )
