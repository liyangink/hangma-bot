"""官方平台错误分类。

分类只服务于封闭结果契约（SubmitOutcome / ParticipantTerminal / 有界重试判定），
不把官方错误文本原样透传给上层。所有 detail 都经过 :func:'sanitize' 脱敏，
保证 Token 与 Authorization 原文不会进入异常、日志或审计。
"""

from __future__ import annotations

import re
from typing import Optional

# 可能携带 Token 的模式：Authorization 头、超长随机串。命中即整体替换。
_BEARER_PATTERN = re.compile(r"(?i)bearer[\s:]+[A-Za-z0-9._~+/=-]{8,}")
_LONG_SECRET_PATTERN = re.compile(r"[A-Za-z0-9._~+/=-]{40,}")

# 已知官方错误码集合（API 文档 §8 错误表，指南 v8，抓取 2026-09-03）。
# 异常服务端响应可能把任意文本塞进 code 字段（包括全大写凭证形态，
# 形态正则无法区分），因此只放行已确认的官方码；未知值不进入异常与
# 审计，只以脱敏形式并入 detail。官方新增错误码时同步维护此集合。
KNOWN_OFFICIAL_CODES = frozenset({
    "TOKEN_NOT_SCOPED",
    "UNAUTHORIZED",
    "FORBIDDEN",
    "GAME_NOT_FINISHED",
    "TOURNAMENT_NOT_FOUND",
    "GAME_NOT_FOUND",
    "INVALID_ACTION",
    "INVALID_INPUT",
    "NOT_QUALIFIED",
    "TOURNAMENT_STARTED",
    "TOURNAMENT_CLOSED",
    "NOT_REGISTERED",
    "MATCH_LIMIT_REACHED",
    "RATE_LIMITED",
})

_MAX_DETAIL_LENGTH = 300


def sanitize_official_code(code):
    """白名单化官方错误码；未知值返回 None，原值经脱敏进 detail。"""

    if code is None:
        return None
    if isinstance(code, str) and code in KNOWN_OFFICIAL_CODES:
        return code
    return None


def sanitize(text: str) -> str:
    """脱敏文本：移除 Bearer 凭证和超长随机串，并截断到固定长度。"""

    redacted = _BEARER_PATTERN.sub("Bearer ***", text)
    redacted = _LONG_SECRET_PATTERN.sub("***", redacted)
    if len(redacted) > _MAX_DETAIL_LENGTH:
        redacted = redacted[: _MAX_DETAIL_LENGTH - 3] + "..."
    return redacted


class OfficialError(Exception):
    """官方 HTTP 错误基类；detail 已脱敏、official_code 已白名单化。

    code 字段来自服务端响应，异常服务端可塞入任意文本（含凭证），
    因此非官方码形态（大写/数字/下划线）的值不进入异常串与审计，
    只以脱敏形式并入 detail。
    """

    def __init__(
        self,
        http_status: Optional[int],
        official_code: Optional[str],
        detail: str,
        raw_text: Optional[str] = None,
    ) -> None:
        self.http_status = http_status
        # 未知 code 值不并入 detail：全大写凭证等任意文本即使脱敏后
        # 也无审计价值，直接丢弃（安全优先于信息保留）
        self.official_code = sanitize_official_code(official_code)
        self.detail = sanitize(detail)
        # 错误响应原文（已由传输层完成 Token 替换）：仅供审计原始事件全量
        # 保留（接线清单 E2），不进入异常串与日志。此处刻意不再过 sanitize——
        # 其 300 字符截断会破坏"原文完整保留"；记录层入队前另有第二层脱敏。
        self.raw_text = raw_text
        super().__init__(
            "status={} code={} detail={}".format(http_status, self.official_code, self.detail)
        )


class AuthError(OfficialError):
    """401：Token 无效或被吊销；必须形成参赛者终态或 SubmitFatal，不允许循环重试。"""


class ForbiddenError(OfficialError):
    """403：无访问权（作用域不符或 game_id 不属于本身份）。"""


class NotFoundError(OfficialError):
    """404：赛事或对局不存在；调用方按语义重新发现或安全停止。"""


class ConflictError(OfficialError):
    """409：官方明确拒绝（INVALID_ACTION / NOT_QUALIFIED / TOURNAMENT_* 等）。

    409 表示官方已明确未执行该请求，与传输结果不确定
    （UncertainTransportError）必须严格区分。
    """


class BadRequestError(OfficialError):
    """400：请求或 Token 作用域不合法（如 TOKEN_NOT_SCOPED）。"""


class RateLimitedError(OfficialError):
    """429：官方限速；带建议冷却秒数（官方未给 Retry-After 时为默认值）。"""

    def __init__(
        self,
        http_status: Optional[int],
        official_code: Optional[str],
        detail: str,
        retry_after_seconds: Optional[float] = None,
        raw_text: Optional[str] = None,
    ) -> None:
        super().__init__(http_status, official_code, detail, raw_text=raw_text)
        self.retry_after_seconds = retry_after_seconds


class UncertainTransportError(OfficialError):
    """请求结果不确定：本地超时、断连或响应不完整。

    对非幂等动作 POST，该类错误禁止重放，必须进入 SubmitAmbiguous；
    对 GET 只是有界重试的一个分类。
    """

    def __init__(self, detail: str) -> None:
        super().__init__(None, None, detail)


class RecoverableServerError(OfficialError):
    """可恢复 5xx：服务器给出明确错误响应（非断连），GET 可有界重试。"""


class FatalProtocolError(OfficialError):
    """响应结构不可解析且无法用快照重建修复；形成身份级终态。"""


class DtoError(ValueError):
    """官方 JSON 与已知契约不符；recoverable=True 时可用 seq=0 快照重建修复。"""

    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        self.recoverable = recoverable
        super().__init__(message)

