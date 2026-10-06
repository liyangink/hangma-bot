"""审计记录的第二道防御性脱敏。

设计意图（纵深防御）：

1. 第一层脱敏由调用方完成——官方适配器进入 ``AuditSink.emit()`` 前必须已经移除
   ``Authorization``、Token 与 Cookie 原文（见 ``doc/implementation/interface-contracts.md`` §7）。
2. 本模块是记录端的第二层独立防线：不假设调用方可靠，按敏感键名和常见凭证形态
   再扫描一遍。记录器本身不持有任何 Token 原文，因此只能做形态识别，
   不能保证清除任意未知形态的秘密；残余风险由离线验证器的密文扫描兜底报告。

边界条件：

- 结构级扫描替换整个敏感键的值（不递归保留子结构），避免嵌套字符串残留原文。
- 序列化行级扫描只使用不包含引号字符类的正则，替换后仍是合法 JSON，
  不会破坏 JSONL 行的完整性。
- 全部替换幂等：对已脱敏文本重复应用结果不变。
"""

from __future__ import annotations

import re
import json
import math
from typing import Any

# 脱敏后统一写入的占位标记；本身不包含任何触发形态，可安全重复扫描。
REDACTED = "[REDACTED]"

# 敏感键名：出现即整值替换。采用子串匹配以覆盖 access_token / Set-Cookie 等变体。
# 宁可误杀审计字段，也不能把可还原凭证写进磁盘。
_SENSITIVE_KEY_RE = re.compile(r"authorization|cookie|token|secret|password", re.IGNORECASE)

# 常见凭证形态。字符类均排除双引号与控制字符，保证对序列化后的 JSON 行安全。
# 形态集合与 errors.sanitize 对齐（F-01 修复）：除空白分隔的 Bearer 外，
# 还覆盖 "Bearer:" 冒号形态与 40+ 字符裸长串（errors 侧 _LONG_SECRET_PATTERN
# 同款字符类）；两处缺一即可能让"非我方 Token 形态"的凭证随 raw 原文落盘。
_BEARER_RE = re.compile(r"(?i)\bbearer[\s:]+[A-Za-z0-9._~+/=-]{8,}")
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]{4,})?")
_QUERY_SECRET_RE = re.compile(
    r"(?i)\b((?:access_)?refresh_token|(?:access_)?token|authorization|cookie)"
    r"=([^\s&\"'<>]{3,})"
)
_LONG_SECRET_RE = re.compile(r"[A-Za-z0-9._~+/=-]{40,}")
# 注：_LONG_SECRET_RE 对 40+ 连续 base64url 形态文本整体替换（宁杀勿漏）；
# REDACTED 占位符与已替换文本不含该字符类，替换幂等。

# endpoint 字段的键名：raw 事件 payload 保存官方端点原样（接口协议 §7）。
ENDPOINT_KEY = "endpoint"
POLICY_RELEASE_KEY = "policy_release"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")

# 端点豁免裸长串规则的原因：场次 URL 的路径段（如
# /api/games/<40+ 字符 game_id>/state）会误命中 _LONG_SECRET_RE，把
# "官方端点原样"抹成 GET/POST [REDACTED]，丢失端点级证据（如证明未调用
# register/ready）。端点由我方代码生成、不含凭证（Token 在 Header 且
# 传输层已替换），因此端点值只做弱形态扫描（Bearer/JWT/query=），
# 仍保留纵深防御。
_WEAK_SECRET_RES = (_BEARER_RE, _JWT_RE, _QUERY_SECRET_RE)


def _redact_string(text: str) -> str:
    """对单个字符串值做凭证形态扫描；替换均保持文本可读且幂等。"""

    text = _BEARER_RE.sub("Bearer " + REDACTED, text)
    text = _JWT_RE.sub(REDACTED, text)
    text = _QUERY_SECRET_RE.sub(r"\1=" + REDACTED, text)
    text = _LONG_SECRET_RE.sub(REDACTED, text)
    return text


def _redact_string_weak(text: str) -> str:
    """弱形态扫描：不应用裸长串规则（端点等非凭证长字段专用）。"""

    text = _BEARER_RE.sub("Bearer " + REDACTED, text)
    text = _JWT_RE.sub(REDACTED, text)
    text = _QUERY_SECRET_RE.sub(r"\1=" + REDACTED, text)
    return text


class _LegacyAuditShape(Exception):
    """快速路径遇非原生形态立即回旧路径，不能先消费自定义容器再重复消费。"""


def _redact_value(value: Any, path: tuple[str, ...], canonical: bool = False) -> Any:
    """携带结构路径执行脱敏；发布包摘要只在受控清单子树内豁免。"""

    if canonical:
        if type(value) not in (dict, list, tuple, str, int, float, bool, type(None)):
            raise _LegacyAuditShape
        elif type(value) is float and not math.isfinite(value):
            raise _LegacyAuditShape
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if canonical and type(key) is not str:
                raise _LegacyAuditShape
            key_path = path + ((key,) if isinstance(key, str) else ())
            if isinstance(key, str) and _SENSITIVE_KEY_RE.search(key):
                result[key] = REDACTED
            elif key == ENDPOINT_KEY and isinstance(item, str):
                result[key] = _redact_string_weak(item)
            elif (
                POLICY_RELEASE_KEY in path
                and isinstance(item, str)
                and _SHA256_RE.fullmatch(item)
            ):
                # policy_release 由组合根生成；严格 SHA-256 是审计身份而非凭证。
                result[key] = item
            else:
                result[key] = _redact_value(item, key_path, canonical)
        return result
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, path, canonical) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def redact_value(value: Any) -> Any:
    """深拷贝并脱敏任意结构；非 JSON 值原样保留，由序列化阶段统一报错。

    返回全新对象：调用方在此之后修改原结构不会影响已脱敏副本。
    敏感键的整棵子树被 ``REDACTED`` 替换，不做部分保留。
    """

    return _redact_value(value, ())


# 序列化行内的端点值定位：精确匹配 "endpoint": "..."（值内允许转义）。
_ENDPOINT_VALUE_RE = re.compile(r'"endpoint"\s*:\s*"((?:[^"\\]|\\.)*)"')

# 行级兜底扫描时用于掩蔽端点原文的哨兵；\u0000 不属于任何凭证形态字符类，
# 掩蔽后不会被误杀，扫描完精确还原。
_ENDPOINT_SENTINEL = "\u0000{0}\u0000"


def _redact_document_json(document: Any) -> str:
    """复用原结构保护和行级兜底；只省略已结构化输入的首次JSON往返。"""

    masked: list[str] = []

    def _protect(value: Any, path: tuple[str, ...]) -> Any:
        if isinstance(value, dict):
            return {
                key: _protect(item, path + ((key,) if isinstance(key, str) else ()))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [_protect(item, path) for item in value]
        if isinstance(value, str) and (
            (path and path[-1] == ENDPOINT_KEY)
            or (POLICY_RELEASE_KEY in path and _SHA256_RE.fullmatch(value))
        ):
            marker = "[AUDIT-PROTECTED-{0}]".format(len(masked))
            masked.append(value)
            return marker
        return value

    def _restore(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: _restore(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_restore(item) for item in value]
        if isinstance(value, str):
            match = re.fullmatch(r"\[AUDIT-PROTECTED-(\d+)\]", value)
            if match and int(match.group(1)) < len(masked):
                return masked[int(match.group(1))]
        return value

    protected = json.dumps(_protect(document, ()), ensure_ascii=False, allow_nan=False)
    scanned = _redact_string(protected)
    restored = _restore(json.loads(scanned))
    return json.dumps(restored, ensure_ascii=False, allow_nan=False)


def redact_json_line(line: str) -> str:
    """对序列化后的 JSON 行做最后一道形态扫描（纵深防御的兜底层）。

    所有凭证形态正则的字符类都不包含引号，因此替换只发生在字符串值内部，
    不会改变 JSON 结构。返回值仍是一行合法 JSON。

    endpoint 值在结构级已做过弱扫描，行级兜底先用哨兵掩蔽其原文再扫描，
    避免场次 URL 被裸长串规则误杀；掩蔽内容不匹配任何凭证形态，扫描后
    精确还原（对已含 REDACTED 的行同样幂等）。
    """

    try:
        document = redact_value(json.loads(line))
    except (json.JSONDecodeError, TypeError, ValueError):
        document = None

    if document is not None:
        return _redact_document_json(document)

    masked: list[str] = []

    def _mask(match: re.Match[str]) -> str:
        masked.append(match.group(1))
        return '"endpoint": "{0}"'.format(_ENDPOINT_SENTINEL.format(len(masked) - 1))

    protected = _ENDPOINT_VALUE_RE.sub(_mask, line)
    scanned = _redact_string(protected)
    for index, value in enumerate(masked):
        scanned = scanned.replace(
            '"endpoint": "{0}"'.format(_ENDPOINT_SENTINEL.format(index)),
            '"endpoint": "' + value + '"',
        )
    return scanned


def redact_record_line(envelope: dict[str, Any]) -> str | None:
    """同步编码已结构化审计信封；非标准JSON形态返回None走原路径。

    只允许普通字符串键和原生JSON值；tuple由原脱敏器变list。敏感键下
    的非JSON对象仍整值掩码，不遍历秘密。外部时间和context必须是平面
    JSON标量，以免在第一次编码前改变旧路径对坏context的失败语义。
    返回前已有不可变、完整脱敏字符串；不改输入、不排队或写盘。
    """

    context = envelope.get("context")
    if type(context) is not dict or any(type(v) not in (str, int, float, bool, type(None))
                                      or (type(v) is float and not math.isfinite(v))
                                      for v in context.values()):
        return None
    if any(type(envelope.get(k)) is not int for k in
           ("schema_version", "wall_time_unix_ms", "monotonic_ns")):
        return None
    try:
        document = _redact_value(envelope, (), canonical=True)
    except _LegacyAuditShape:
        return None
    return _redact_document_json(document)


def is_sensitive_key(key: str) -> bool:
    """判断键名是否属于敏感凭证键；离线验证器的密文扫描复用同一判定。"""

    return bool(_SENSITIVE_KEY_RE.search(key))


def unredacted_secret_matches(text: str) -> tuple[str, ...]:
    """返回文本中仍未脱敏的凭证形态片段；空元组表示扫描干净。

    已带 ``REDACTED`` 标记的命中（例如 ``"Bearer [REDACTED]"``）视为已处理，
    不再重复报告，保证本函数与写入侧扫描对同一文本幂等一致。
    """

    return _unredacted_matches(text, (_BEARER_RE, _JWT_RE, _QUERY_SECRET_RE, _LONG_SECRET_RE))


def unredacted_secret_matches_weak(text: str) -> tuple[str, ...]:
    """弱形态判定：不应用裸长串规则（验证器扫描 endpoint 值专用）。"""

    return _unredacted_matches(text, _WEAK_SECRET_RES)


def _unredacted_matches(text: str, patterns: tuple[re.Pattern[str], ...]) -> tuple[str, ...]:
    """共享实现：对给定形态集合返回仍未脱敏的命中片段。"""

    matches: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            if REDACTED not in match.group(0):
                matches.append(match.group(0))
    return tuple(matches)
