"""hangma 单元测试共享配置：把 src 加入 sys.path，便于无 pyproject 时直接运行。"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
