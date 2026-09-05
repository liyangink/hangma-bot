"""产物元数据事实：指南版本与规则源哈希（parallel-v1 契约 §4.2）。

compute_rules_hash 读取 hangma 包源码文件——这是离线产物工具，不是
SimulationEngine 的方法（engine 保持无文件/网络/时钟副作用），组合根
（bootstrap）启动时计算一次传入引擎。

集成裁定（2026-09-05）：compute_rules_hash 全仓唯一实现位于本文件，
口径按契约 §4.2 逐字执行——路径为「仓库相对 POSIX 路径」
（如 src/hangma_bot/hangma/engine.py），范围是 src/hangma_bot/hangma
下全部 .py 文件。评估线（offline.evaluation_results）与组合根都从这里
导入，不再保留同义副本（旧版曾有「包内相对路径」变体，与契约不符）。
"""

from __future__ import annotations

from pathlib import Path

from hangma_bot.kernel.identity import identity_digest

GUIDE_VERSION = 15
"""官方接入指南版本（parallel-v1.json guide_evidence；v15/2026-09-05 快照）。"""

GUIDE_CAPTURED_AT = "2026-09-05"
"""指南来源采集日期（YYYY-MM-DD）。"""


def compute_rules_hash(repo_root) -> str:
    """规则源文件清单的稳定哈希（契约 §4.2，无前缀全量十六进制）。

    取 src/hangma_bot/hangma 下全部 .py 文件，按仓库相对 POSIX 路径
    排序，将 [path, 文件字节 SHA-256] 数组按 §4.1 编码
    （ensure_ascii=False、separators=(comma,colon)、allow_nan=False）
    再哈希；规则配置另存，不混入源文件 hash。跨机器复制不受 mtime 影响。
    """
    rules_dir = Path(repo_root) / "src" / "hangma_bot" / "hangma"
    entries = []
    for path in sorted(rules_dir.rglob("*.py")):
        relative = path.relative_to(Path(repo_root)).as_posix()
        file_hash = _sha256_hex(path.read_bytes())
        entries.append([relative, file_hash])
    if not entries:
        raise ValueError("规则源文件清单为空: {0}".format(rules_dir))
    return identity_digest(entries)


def _sha256_hex(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()
