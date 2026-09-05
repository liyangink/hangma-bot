"""产物元数据事实：指南版本与规则源哈希（parallel-v1 契约 §4.2）。

compute_rules_hash 读取 hangma 包源码文件——这是离线产物工具，不是
SimulationEngine 的方法（engine 保持无文件/网络/时钟副作用），组合根
（bootstrap）启动时计算一次传入引擎。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Tuple

GUIDE_VERSION = 15
"""官方接入指南版本（parallel-v1.json guide_evidence；v15/2026-09-05 快照）。"""

GUIDE_CAPTURED_AT = "2026-09-05"
"""指南来源采集日期（YYYY-MM-DD）。"""


def compute_rules_hash(hangma_package_dir) -> str:
    """规则源文件清单的稳定哈希（契约 §4.2）。

    取 hangma 目录下全部 .py 文件，按仓库相对 POSIX 路径排序，将
    [path, 文件字节 SHA-256] 数组按 §4.1 编码（ensure_ascii=False、
    separators=(comma,colon)、allow_nan=False）再哈希，返回全长十六进制。
    跨机器复制不受 mtime 影响。
    """
    root = Path(hangma_package_dir)
    entries: List[Tuple[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append((relative, file_hash))
    if not entries:
        raise ValueError("hangma 包内没有 .py 文件：{0}".format(root))
    payload = json.dumps(
        entries, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
