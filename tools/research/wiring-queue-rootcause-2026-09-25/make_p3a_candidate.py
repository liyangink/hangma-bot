"""从冻结的 R18 v2 源码生成 P3-A 消融候选：只把熟张加分 3.0 改成 0.0。

为什么用生成而不是手抄：本项的唯一改动必须可机械核对。生成器断言目标片段
在源码里恰好出现一次，并输出改动前后的 SHA-256，使"除这一处外完全相同"可复算。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/wiring-queue-rootcause-2026-09-25'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
    R18_INTEGRATED_POSITIVE_V2_SHA256,
)

OLD = "river_part = 3.0"
NEW = "river_part = 0.0"
OUT = _project_file(_PROJECT_ROOT, 'review/wiring-queue-rootcause-2026-09-25/candidates/OPTY-R18-C03-RIVER0.py')


def main() -> int:
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    actual = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if actual != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise SystemExit("父代源码摘要与冻结值不符，拒绝生成消融候选")
    hits = source.count(OLD)
    if hits != 1:
        raise SystemExit("目标片段出现 %d 次，预期恰好 1 次；拒绝生成" % hits)
    mutated = source.replace(OLD, NEW)
    # "river_part = 0.0" 本来就是初始化行，因此不能用出现次数判断；改为逐字符比对，
    # 断言改动后与父代**恰好相差 1 个字符**（就是那个 3 -> 0）。
    if len(mutated) != len(source):
        raise SystemExit("替换改变了源码长度")
    diff = [i for i, (a, b) in enumerate(zip(source, mutated)) if a != b]
    if diff != [source.index(OLD) + len("river_part = ")]:
        raise SystemExit("改动位置不符合预期：%s" % diff)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(mutated, encoding="utf-8")
    print("父代源码 SHA-256:", actual)
    print("候选源码 SHA-256:", hashlib.sha256(mutated.encode("utf-8")).hexdigest())
    print("唯一改动:", OLD, "->", NEW)
    print("输出:", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
