#!/usr/bin/env python3
"""从冻结 R18 v2 机械生成 G88 本人已吃碰后熟牌偏好候选。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from pathlib import Path

from hangma_bot.policy.action_value_executor import static_check
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_SOURCE


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py')
REPLACEMENTS = (
    (
        "    own_meld_count = len(melds[seat])\n",
        "    own_meld_count = len(melds[seat])\n"
        "    has_claimed_meld = False\n"
        "    for own_meld in melds[seat]:\n"
        "        if own_meld.get(\"kind\") == \"chi\" or own_meld.get(\"kind\") == \"peng\":\n"
        "            has_claimed_meld = True\n",
    ),
    (
        "                river_part = 3.0\n",
        "                river_part = 0.0 if has_claimed_meld else 3.0\n",
    ),
    (
        "            if table_rank == 1 and familiar:\n",
        "            if table_rank == 1 and familiar and not has_claimed_meld:\n",
    ),
)


def main() -> None:
    """要求三锚点唯一、候选静态合法，然后写一次性研究源码。"""
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    for before, after in REPLACEMENTS:
        if source.count(before) != 1:
            raise ValueError("G88 父代锚点不是唯一：" + before.strip())
        source = source.replace(before, after, 1)
    compile(source, str(OUT), "exec")
    static_check(source)
    if OUT.exists():
        raise FileExistsError("G88 候选已存在，拒绝覆盖")
    OUT.write_text(source, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
