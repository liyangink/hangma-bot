"""审计链封装：统一构造信封、追踪降级状态，隔离磁盘失败。

约束来源：application 模块规范——“审计失败不阻塞动作但运行标记
audit_degraded”。因此 emit 捕获一切 sink 异常并转换为降级标记。
"""

from __future__ import annotations

import re
from typing import Optional

from hangma_bot.application.contracts import (
    AuditContext,
    AuditKind,
    AuditReceipt,
    AuditRecord,
    AuditSink,
    AuditSummary,
)
from hangma_bot.application.deadline import RuntimeClock

AUDIT_SCHEMA_VERSION = 1  # 第一阶段信封结构版本；字段变化必须升版本

_ERROR_TEXT_LIMIT = 200  # 异常文本入审计的最大长度，防止 URL/凭证片段整段落盘

# 凭证样式的轻量模式：Authorization/Cookie 头、键值对、长十六进制/基串。
# Authorization 头不限方案（Basic/Bearer/Digest…）整值脱敏，Cookie 同理；
# 通用 KV 兜底其余键值对（含 session）。
_AUTH_HEADER = re.compile(r"(?i)(authorization\s*[:=]\s*)([^\n]+)")
_COOKIE_HEADER = re.compile(r"(?i)(cookie\s*[:=]\s*)([^\n]+)")
_SECRET_KV = re.compile(
    r"(?i)(token|key|secret|authorization|auth|password|bearer|session)([=:\s]+)(\S+)"
)
_LONG_OPAQUE = re.compile(r"(?i)\b[a-f0-9]{20,}\b|\b[A-Za-z0-9+/]{20,}={0,2}\b")


def _redact(raw: str) -> str:
    raw = _AUTH_HEADER.sub(lambda m: m.group(1) + "<redacted>", raw)
    raw = _COOKIE_HEADER.sub(lambda m: m.group(1) + "<redacted>", raw)
    raw = _SECRET_KV.sub(lambda m: m.group(1) + m.group(2) + "<redacted>", raw)
    raw = _LONG_OPAQUE.sub("<redacted>", raw)
    return raw


def audit_error_text(exc: BaseException, limit: int = _ERROR_TEXT_LIMIT) -> str:
    """把异常转成可入审计的消毒文本：类型名 + 截断并脱敏的消息。

    HTTP 客户端异常常内嵌完整 URL/查询串；截断加凭证模式脱敏构成
    应用层第一道防线，记录器的防御性脱敏仍是最终防线。
    """

    raw = _redact("{}: {}".format(type(exc).__name__, str(exc)))
    if len(raw) > limit:
        raw = raw[: limit - 3] + "..."
    # 去除控制字符，避免破坏 JSONL 行结构。
    return "".join(ch if ch >= " " else " " for ch in raw)


def audit_text(value: str, limit: int = _ERROR_TEXT_LIMIT) -> str:
    """一般文本入审计前的截断与脱敏消毒。"""

    raw = _redact(value)
    if len(raw) > limit:
        raw = raw[: limit - 3] + "..."
    return "".join(ch if ch >= " " else " " for ch in raw)


class AuditTrail:
    """把业务事实转成已脱敏审计信封的唯一入口。

    payload 必须只含 JSON 值（dict/list/str/int/float/bool/None），
    由调用方在构造时保证；本类不做递归序列化。
    """

    def __init__(
        self,
        sink: AuditSink,
        *,
        run_id: str,
        tournament_id: str,
        participant_id: str,
        clock: RuntimeClock,
    ) -> None:
        self._sink = sink
        self._run_id = run_id
        self._tournament_id = tournament_id
        self._participant_id = participant_id
        self._clock = clock
        self._degraded = False
        self._degraded_reasons: list[str] = []

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def audit_degraded(self) -> bool:
        """任一事件丢失或 sink 异常后保持 True，直到运行结束。"""

        return self._degraded

    def emit(
        self,
        kind: AuditKind,
        payload: dict,
        *,
        stage_attempt_id: Optional[str] = None,
        game_id: Optional[str] = None,
        round_no: Optional[int] = None,
        trigger_seq: Optional[int] = None,
        decision_id: Optional[str] = None,
        attempt_no: Optional[int] = None,
    ) -> AuditReceipt:
        """非阻塞写一条审计；任何失败只反映在回执和降级标记里。"""

        record = AuditRecord(
            schema_version=AUDIT_SCHEMA_VERSION,
            kind=kind,
            context=AuditContext(
                run_id=self._run_id,
                tournament_id=self._tournament_id,
                participant_id=self._participant_id,
                stage_attempt_id=stage_attempt_id,
                game_id=game_id,
                round_no=round_no,
                trigger_seq=trigger_seq,
                decision_id=decision_id,
                attempt_no=attempt_no,
            ),
            wall_time_unix_ms=self._clock.unix_ms(),
            monotonic_ns=int(self._clock.now() * 1_000_000_000),
            payload=payload,
        )
        try:
            receipt = self._sink.emit(record)
        except Exception as exc:  # noqa: BLE001 - 审计失败绝不能打断动作路径
            self._mark_degraded("sink.emit 异常: {}: {}".format(type(exc).__name__, exc))
            return AuditReceipt(queued=False, audit_degraded=True, reason="sink.emit raised")

        if (not receipt.queued) or receipt.audit_degraded:
            self._mark_degraded(receipt.reason or "审计入队未成功")
        return receipt

    def mark_degraded(self, reason: str) -> None:
        """记录与 sink 无关的审计降级事实（例如关键事件构造失败）。"""

        self._mark_degraded(reason)

    async def aclose(self, timeout_seconds: float) -> AuditSummary:
        """在限定秒数内尽力刷新；失败合成为诚实的降级汇总。"""

        try:
            summary = await self._sink.aclose(timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - 关闭失败同样不能掩盖运行结果
            self._mark_degraded("sink.aclose 异常: {}".format(exc))
            return AuditSummary(
                written=0,
                dropped_low_priority=0,
                missing_high_priority=0,
                serialization_failures=0,
                audit_degraded=True,
            )
        if summary.audit_degraded:
            self._mark_degraded("记录器报告审计降级")
        return summary

    def _mark_degraded(self, reason: str) -> None:
        self._degraded = True
        if reason not in self._degraded_reasons:
            self._degraded_reasons.append(reason)

    @property
    def degraded_reasons(self) -> tuple[str, ...]:
        return tuple(self._degraded_reasons)
