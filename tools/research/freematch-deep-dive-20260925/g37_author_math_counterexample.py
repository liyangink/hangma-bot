#!/usr/bin/env python3
"""G37：用生产规则核对作者“七对同向听蕴含单张数相同”的反例。"""

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

import json

from hangma_bot.hangma.hand_analysis import analyse_counts_progress
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER


FULL_HAND = ("白", "3w", "3w", "7w", "7w", "1w", "1w",
             "北", "北", "9w", "9w", "中", "中", "9b")


def after(discard: str) -> dict[str, int]:
    """同一合法 14 张手牌弃去一张，计数只用于反驳作者的数学蕴含。"""

    hand = list(FULL_HAND)
    hand.remove(discard)
    counts = tuple(hand.count(code) for code in CANONICAL_TILE_ORDER)
    progress = analyse_counts_progress(counts, 0)
    return {"standard_shanten": progress.standard_shanten,
            "seven_pairs_shanten": progress.chiitoi_shanten,
            "combined_shanten": progress.shanten,
            "natural_pairs": sum(value // 2 for value in counts[:33]),
            "natural_singletons": sum(value % 2 for value in counts[:33]),
            "white_count": counts[33]}


def main() -> None:
    """断言两个弃牌满足作者的向听保护，却不满足其对子/单张等价引理。"""

    pair_discard = after("3w")
    singleton_discard = after("9b")
    assert (pair_discard["standard_shanten"], pair_discard["seven_pairs_shanten"]) == (2, 0)
    assert (singleton_discard["standard_shanten"], singleton_discard["seven_pairs_shanten"]) == (2, 0)
    assert pair_discard["natural_pairs"] == 5 and pair_discard["natural_singletons"] == 2
    assert singleton_discard["natural_pairs"] == 6 and singleton_discard["natural_singletons"] == 0
    print(json.dumps({"full_hand": FULL_HAND, "discard_pair_tile_3w": pair_discard,
                      "discard_singleton_9b": singleton_discard},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
