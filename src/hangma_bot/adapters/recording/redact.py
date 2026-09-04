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
from typing import Any

# 脱敏后统一写入的占位标记；本身不包含任何触发形态，可安全重复扫描。
REDACTED = "[REDACTED]"

# 敏感键名：出现即整值替换。采用子串匹配以覆盖 access_token / Set-Cookie 等变体。
# 宁可误杀审计字段，也不能把可还原凭证写进磁盘。
_SENSITIVE_KEY_RE = re.compile(r"authorization|cookie|token|secret|password", re.IGNORECASE)

# 常见凭证形态。字符类均排除双引号与控制字符，保证对序列化后的 JSON 行安全。
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{4,}")
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]{4,})?")
_QUERY_SECRET_RE = re.compile(
    r"(?i)\b((?:access_)?refresh_token|(?:access_)?token|authorization|cookie)"
    r"=([^\s&\"'<>]{3,})"
)


def _redact_string(text: str) -> str:
    """对单个字符串值做凭证形态扫描；替换均保持文本可读且幂等。"""

    text = _BEARER_RE.sub("Bearer " + REDACTED, text)
    text = _JWT_RE.sub(REDACTED, text)
    text = _QUERY_SECRET_RE.sub(r"\1=" + REDACTED, text)
    return text


def redact_value(value: Any) -> Any:
    """深拷贝并脱敏任意结构；非 JSON 值原样保留，由序列化阶段统一报错。

    返回全新对象：调用方在此之后修改原结构不会影响已脱敏副本。
    敏感键的整棵子树被 ``REDACTED`` 替换，不做部分保留。
    """

    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SENSITIVE_KEY_RE.search(key):
                result[key] = REDACTED
            else:
                result[key] = redact_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def redact_json_line(line: str) -> str:
    """对序列化后的 JSON 行做最后一道形态扫描（纵深防御的兜底层）。

    所有三条正则的字符类都不包含引号，因此替换只发生在字符串值内部，
    不会改变 JSON 结构。返回值仍是一行合法 JSON。
    """

    return _redact_string(line)


def is_sensitive_key(key: str) -> bool:
    """判断键名是否属于敏感凭证键；离线验证器的密文扫描复用同一判定。"""

    return bool(_SENSITIVE_KEY_RE.search(key))


def unredacted_secret_matches(text: str) -> tuple[str, ...]:
    """返回文本中仍未脱敏的凭证形态片段；空元组表示扫描干净。

    已带 ``REDACTED`` 标记的命中（例如 ``"Bearer [REDACTED]"``）视为已处理，
    不再重复报告，保证本函数与写入侧扫描对同一文本幂等一致。
    """

    matches: list[str] = []
    for pattern in (_BEARER_RE, _JWT_RE, _QUERY_SECRET_RE):
        for match in pattern.finditer(text):
            if REDACTED not in match.group(0):
                matches.append(match.group(0))
    return tuple(matches)
