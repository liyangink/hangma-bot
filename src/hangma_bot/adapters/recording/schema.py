"""审计种类的优先级、payload 校验基准与文件路由。

职责（对应模块说明 ``jsonl_sink`` 之外的静态契约）：

1. 优先级由记录器按 ``AuditKind`` 固定：除冗余 ``RAW_PROTOCOL_STATE`` 外全部高优先级，
   调用方不能自行降级（接口协议 §7）。
2. payload 校验基准。**最小校验原则（返工定案）**：信封必须可序列化为 JSON 对象；
   只对离线验证器实际消费的字段做"存在即类型正确"的检查，
   **不强制必填词表**。原因：payload 词表的第一手生产方是 application 层与
   官方适配器（``AuditTrail`` 与 ``official/game.py``），二者已经按各自事实
   发射记录；记录器单方面强制必填词表会把 6/8 种类拒为序列化失败，
   端到端斩断审计链路。词表演进的登记属于总体架构对 interface-contracts.md
   的维护职责，不在本模块范围内强加。
3. 提交结果词表的**规范化归并**：生产方既可能写规范小写值（历史约定），
   也可能写封闭结果类名（``_outcome_payload`` 用 ``type(outcome).__name__``），
   验证器用 :func:`canonical_outcome` 把两者归并到同一词表；未知值原样
   进入直方图计数，不拒绝记录。
4. 审计文件路由：``runs/{run_id}/`` 下的相对路径；路径必须包含参赛身份，
   保证四身份并发写同一 ``game_id`` 时互不冲突。

各种类 payload 的真实生产形态（供维护者对照，来源为当前生产代码）：

- ``RUN_MANIFEST``：participant_runtime 启动时发射一次，含 mode、guide、规则与时间配置。
- ``LIFECYCLE_CHANGED``：``{"event": "status_changed", "from", "to"}``（状态迁移时）。
- ``AUTHORITATIVE_STATE``：监督层发赛事快照（status/stage/qualified 等），
  官方场次适配器发窗口权威序号（seq/phase/turn/window）。
- ``DECISION_PLANNED``：``{"plan_revision", "based_on_authoritative_seq", "window",
  "candidates": [{"action_key", "is_emergency"}], "degraded_reasons", "rule_completeness"}``。
- ``SUBMISSION_INTENT``：双方各发一条（应用层含预算事实，适配器含请求 body），
  同一 ``(decision_id, attempt_no)`` 出现两条属双层记录常态。
- ``SUBMISSION_OUTCOME``：应用层 ``{"outcome": <规范值或类名>, "official_code"?,
  "reason"?...}``；适配器 ``{"outcome_type": <类名>, "official_code"?, "reason"?...}``。
- ``PROTOCOL_RECOVERED``：``{"area"/"trigger", "reason"/"reasons", ...}``，字段随事实而定。
- ``GAME_FINISHED``：``{"final_scores": [座位 0—3], "authoritative_seq"|"seq"}``；
  应用层与适配器各发一条。
- ``PARTICIPANT_FINISHED``：``{"reason": <ParticipantTerminalReason 值>, "detail"}``。

版本语义：信封 ``schema_version`` 当前为 1，同时约束本文件描述的校验基准。
未来收紧某个种类时，应先按 README §4 完成契约登记，再引入强制字段并升版本。
"""

from __future__ import annotations

import re
from typing import Mapping

from hangma_bot.application.contracts import AuditKind

AUDIT_SCHEMA_VERSION = 1  # 信封结构与校验基准的当前版本；升级属于受控变更

# 各审计种类当前校验基准版本；当前全部为 1，留作逐种类演进的登记表。
PAYLOAD_SCHEMA_VERSIONS: Mapping[AuditKind, int] = {
    kind: 1 for kind in AuditKind
}

# 运行级清单文件的固定名；记录器按"单对象、后写覆盖"维护（见 jsonl_sink）。
RUN_MANIFEST_PATH = "manifest.json"

# 低优先级：唯一允许在队列压力下计数丢弃的冗余种类。
# 其规范权威信息必须以 AUTHORITATIVE_STATE 高优先级另存，丢弃不损失可审计性。
_LOW_PRIORITY_KINDS = frozenset({AuditKind.RAW_PROTOCOL_STATE})


def is_high_priority(kind: AuditKind) -> bool:
    """返回该审计种类的固定优先级；调用方无法改变。"""

    return kind not in _LOW_PRIORITY_KINDS


# 提交结果的规范词表，与 ``SubmitOutcome`` 七种分类一一对应；
# ``canonical_outcome`` 同时接受封闭结果类名作为别名。
# ``rejected_no_refresh``：POST 已发出、官方明确未执行、无权威刷新、
# 原窗口终结不追加（2026-09-04 契约收口新增）。
CANONICAL_OUTCOME_VALUES = frozenset(
    {
        "accepted",
        "rejected_retryable",
        "rejected_closed",
        "rejected_no_refresh",
        "ambiguous",
        "not_sent",
        "fatal",
    }
)

_CAMEL_BOUNDARY_RE = re.compile(r"(?<!^)(?=[A-Z])")


def canonical_outcome(value: str) -> str:
    """把提交结果值归并到规范词表；未知值原样返回由验证器计数。

    接受两种真实生产形态：规范小写值（``"accepted"``）与封闭结果类名
    （``"SubmitRejectedRetryable"``）。归并是纯字符串变换，不抛异常。
    """

    text = value.strip()
    if text in CANONICAL_OUTCOME_VALUES:
        return text
    if text.startswith("Submit") and len(text) > len("Submit"):
        snake = _CAMEL_BOUNDARY_RE.sub("_", text[len("Submit"):]).lower()
        if snake in CANONICAL_OUTCOME_VALUES:
            return snake
    return text


# 验证器实际消费、因此"存在即必须类型正确"的字段；缺省一律放行。
# 这份表刻意保持最小：收紧前必须先确认离线验证器确实消费该字段，
# 否则任何新必填都会把生产方尚未对齐的种类拒为序列化失败。
_VALIDATOR_CONSUMED_FIELD_TYPES: Mapping[AuditKind, Mapping[str, type]] = {
    # 提交结果分类与 409/模糊/超时统计的主字段。
    AuditKind.SUBMISSION_OUTCOME: {"outcome": str, "outcome_type": str},
    # 规则降级覆盖率统计消费该字段；存在时必须是数组。
    AuditKind.DECISION_PLANNED: {"degraded_reasons": list},
}

_FIELD_TYPE_NAMES: Mapping[type, str] = {str: "字符串", list: "数组"}


def validate_payload(kind: AuditKind, payload: object) -> tuple[str, ...]:
    """按最小校验基准检查 payload；返回中文错误列表，空表示通过。

    规则：

    1. payload 必须是映射（JSONL 每行是一个 JSON 对象）；
    2. 表中列出的验证器消费字段，一旦出现就必须是约定类型；
    3. 其余任何字段、任何缺失都放行——词表的第一手定义权在生产方。

    校验失败的记录不会入队：宁可显式计数为序列化失败并标记审计降级，
    也不能把无法离线消费的记录伪装成有效审计。
    """

    if not isinstance(payload, Mapping):
        return (f"{kind.value} 的 payload 必须是对象",)
    errors: list[str] = []
    for field, expected in _VALIDATOR_CONSUMED_FIELD_TYPES.get(kind, {}).items():
        if field in payload and not isinstance(payload[field], expected):
            errors.append(f"字段 {field} 存在时必须是{_FIELD_TYPE_NAMES[expected]}")
    return tuple(errors)


# 属于单场文件的种类；这些种类缺少 game_id 时回退到身份级 decisions.jsonl，
# 记录不丢失，验证器仍可按信封内的 game_id 关联。
_GAME_SCOPED_KINDS = frozenset(
    {
        AuditKind.AUTHORITATIVE_STATE,
        AuditKind.RAW_PROTOCOL_STATE,
        AuditKind.GAME_FINISHED,
        AuditKind.PROTOCOL_RECOVERED,
    }
)

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_MAX_COMPONENT_LENGTH = 120


def sanitize_component(value: str) -> str:
    """把官方返回的 id 消毒成单一路径组件，防止路径穿越与非法字符。

    消毒可能把不同原始 id 折叠成同一文件名；官方 ``game_id`` 为短字母数字串，
    实际不会发生，此残余风险在此显式声明。
    """

    cleaned = _FILENAME_SAFE_RE.sub("_", value)[:_MAX_COMPONENT_LENGTH]
    if cleaned in {"", ".", ".."}:
        return "unnamed"
    return cleaned


def relative_path_for(kind: AuditKind, participant_id: str, game_id: str | None) -> str:
    """返回记录在 ``runs/{run_id}/`` 下的相对路径。

    路由规则（与接口协议 §7 的目录树一致）：

    - ``RUN_MANIFEST`` → ``manifest.json``（运行级单对象文件，后写覆盖）
    - ``LIFECYCLE_CHANGED`` → ``lifecycle.jsonl``（运行级生命周期流）
    - 决策与提交流 → ``participants/{pid}/decisions.jsonl``
    - 场内事实 → ``participants/{pid}/games/{game_id}.jsonl``
    - 场内种类缺 ``game_id`` 时回退到 ``decisions.jsonl``，不丢弃记录
    - ``PARTICIPANT_FINISHED`` 属于身份级终局，写入 ``decisions.jsonl``
    """

    if kind is AuditKind.RUN_MANIFEST:
        return RUN_MANIFEST_PATH
    if kind is AuditKind.LIFECYCLE_CHANGED:
        return "lifecycle.jsonl"
    participant = sanitize_component(participant_id)
    if kind in _GAME_SCOPED_KINDS and game_id:
        return f"participants/{participant}/games/{sanitize_component(game_id)}.jsonl"
    return f"participants/{participant}/decisions.jsonl"
