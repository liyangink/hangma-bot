"""产物元数据事实：指南版本与规则源哈希（parallel-v1 契约 §4.2）。

compute_rules_hash 读取 hangma 包源码文件——这是离线产物工具，不是
SimulationEngine 的方法（engine 保持无文件/网络/时钟副作用），组合根
（bootstrap）启动时计算一次传入引擎。

集成裁定（2026-09-05）：compute_rules_hash 全仓唯一实现位于本文件，
口径按契约 §4.2 逐字执行——路径为「仓库相对 POSIX 路径」
（如 src/hangma_bot/hangma/engine.py），范围是 src/hangma_bot/hangma
下全部 .py/.c/.h 文件（2026-09-07 增补原生规则源）。评估线与组合根都从这里
导入，不再保留同义副本（旧版曾有「包内相对路径」变体，与契约不符）。
"""

from __future__ import annotations

from pathlib import Path

from hangma_bot.kernel.identity import identity_digest

GUIDE_VERSION = 27
"""2026-09-09抓取v27：继承四白修正，v26圈主响应取代v24旧平台兼容。"""

GUIDE_CAPTURED_AT = "2026-09-09"
"""指南来源采集日期（YYYY-MM-DD）；见官方 v23/fan-calc/guide.json 夹具。"""


def compute_rules_hash(repo_root) -> str:
    """规则源文件清单的稳定哈希（契约 §4.2，无前缀全量十六进制）。

    取 src/hangma_bot/hangma 下全部 .py/.c/.h 文件，按仓库相对 POSIX 路径
    排序，将 [path, 文件字节 SHA-256] 数组按 §4.1 编码
    （ensure_ascii=False、separators=(comma,colon)、allow_nan=False）
    再哈希；规则配置与实际二进制摘要另存，不混入源文件 hash。
    跨机器复制不受 mtime 影响，Python/C 同语义实现共享规则源指纹。
    """
    rules_dir = Path(repo_root) / "src" / "hangma_bot" / "hangma"
    entries = []
    for path in sorted(p for p in rules_dir.rglob("*") if p.suffix in {".py", ".c", ".h"} and p.is_file()):
        relative = path.relative_to(Path(repo_root)).as_posix()
        file_hash = _sha256_hex(path.read_bytes())
        entries.append([relative, file_hash])
    if not entries:
        raise ValueError("规则源文件清单为空: {0}".format(rules_dir))
    return identity_digest(entries)


def hand_math_runtime_metadata() -> dict:
    """启动期记录实际数学实现与已加载原生文件摘要，不影响规则计算。

    返回可序列化版本事实；纯 Python 的 native_sha256 为空。导入或
    读取失败如实记录，不能因此禁用独立紧急动作或启动动态编译。
    """
    try:
        from hangma_bot.hangma.hand_analysis import math_backend_info

        facts = dict(math_backend_info())
    except Exception as exc:
        return {"implementation": "unavailable", "semantics_version": None,
            "fallback_reason": type(exc).__name__ + ": " + str(exc), "native_sha256": None}
    native_path = facts.pop("native_path", None)
    facts["native_sha256"] = None
    if native_path is not None:
        try:
            facts["native_sha256"] = _sha256_hex(Path(native_path).read_bytes())
        except OSError as exc:
            facts["artifact_error"] = type(exc).__name__ + ": " + str(exc)
    return facts


def _sha256_hex(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()
