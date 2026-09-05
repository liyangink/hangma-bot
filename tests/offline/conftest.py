"""tests/offline 共享配置：把 src 加入 sys.path（与既有测试目录同模式）。"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
