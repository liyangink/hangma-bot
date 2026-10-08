#!/usr/bin/env python3
"""G240：用最小可复算反例检查长路线作者的概率与胡型合并。"""

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

from hangma_bot.hangma import hand_analysis, settlement
from hangma_bot.kernel.actions import Tile


def main() -> None:
    """单次摸牌互斥牌码须求和；可双分解成胡只能按生产分支结算一次。"""
    # 条件未知池四张，其中两个不同的目标牌码各一张。
    # 一次摸牌只能落在一个码上，不能把两个命中事件当独立伯努利。
    exact_union = (1 + 1) / 4
    independent_product = 1 - (1 - 1 / 4) * (1 - 1 / 4)
    if exact_union != 0.5 or independent_product != 0.4375:
        raise AssertionError("单摸互斥事件反例失效")

    # 13 张同时处于普通型、七对听牌；7w 一摸既可作普通型，也可作七对。
    # 官方生产规则只选择一个确定分支并结算一次，不能相加两个路线边际值。
    waiting = tuple(Tile(code) for code in (
        "1w", "1w", "2w", "2w", "3w", "3w", "4w", "4w",
        "5w", "5w", "6w", "6w", "7w"))
    shape = hand_analysis.analyse_hand(waiting, 0)
    split = hand_analysis.win_split(waiting + (Tile("7w"),), 0)
    if (shape.standard_shanten, shape.chiitoi_shanten) != (0, 0):
        raise AssertionError("双路线听牌反例失效")
    if split is None or split.branch != "七对":
        raise AssertionError("生产规则的唯一胡型分支与反例不一致")
    fan = settlement.compute_fan(split, 0, 0, False)
    if fan.fan != 2:
        raise AssertionError("七对结算与官方倍率不一致")

    print(json.dumps({
        "schema": "g240-route-math-counterexamples/1",
        "one_draw_disjoint_union": exact_union,
        "incorrect_independent_product": independent_product,
        "dual_ready_standard_shanten": shape.standard_shanten,
        "dual_ready_seven_shanten": shape.chiitoi_shanten,
        "production_win_branch": split.branch,
        "production_fan": fan.fan,
        "incorrect_sum_of_plain_and_seven_fan": 1 + 2,
    }, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
