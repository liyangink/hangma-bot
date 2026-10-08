#!/usr/bin/env python3
"""机械生成「番值加权进张」候选（C18）：在父代 base 上叠加**按路线番值加权的进张数**。

动机（本轮新增）：父代的核心打分是

    base = -100 * shanten + round(support, 1)        # support = 全部进张的剩余张数合计

**它只看「有多少张牌能让手牌前进」，完全不看「前进之后这手牌值多少番」。**
自由赛诊断的结论恰恰是「我们胡得最多、但赢得最小」：番值缺口几乎完全由爆头占比
解释（我方胡牌带爆头 13.3% vs 对手 25.5%），而 P19 证明弃牌层已经没有改选空间、
弃胡层是一条硬币取舍（P24 盲弃胡 −10.84 分/桌、P86 一律收胡 −13.13 分/桌）。
⇒ 唯一没被测过的方向是**在同等向听下把进张引向番值更高的路线**，这正是本候选。

规则事实已经现成：动作的 `routes` 每条带 `conditional_settlement.fan` 与
`useful_tiles[].remaining_estimate`（父代自己的 v2 覆盖就在用这两个字段），
所以本候选不引入任何新规则、新模型或新先验，只是把既有事实乘起来。

两个变体：
  FANW    ：把**所有**路线的 进张数 ×（番 − 1）求和（＝番值加权的总宽度）
  FANMAX  ：只取**单条最好路线**的 进张数 ×（番 − 1）（＝把手牌引向那一条路线）

用法：
    .venv/bin/python make_fan_weight_candidates.py --weights 0.25,1,4
"""
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

import argparse
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
ANCHOR = "                base = -100.0 * float(shanten) + round(support, 1)\n"

FANW_BLOCK = [
    "                fan_weighted = 0.0",
    "                routes_for_fan = action.get(\"routes\")",
    "                if routes_for_fan is not None and len(routes_for_fan) > 0 and action.get(\"value_coverage\") == \"complete\":",
    "                    for route in routes_for_fan:",
    "                        route_fan = 1.0",
    "                        route_settlement = route.get(\"conditional_settlement\")",
    "                        if route_settlement is not None:",
    "                            raw_route_fan = route_settlement.get(\"fan\")",
    "                            if raw_route_fan is not None and raw_route_fan is not True and raw_route_fan is not False:",
    "                                converted_route_fan = float(raw_route_fan)",
    "                                if converted_route_fan - converted_route_fan == 0 and converted_route_fan > 1.0:",
    "                                    route_fan = converted_route_fan",
    "                        route_tiles = route.get(\"useful_tiles\")",
    "                        if route_tiles is not None:",
    "                            for route_tile in route_tiles:",
    "                                route_remaining = route_tile.get(\"remaining_estimate\")",
    "                                if route_remaining is not None and route_remaining is not True and route_remaining is not False:",
    "                                    route_amount = float(route_remaining)",
    "                                    if route_amount - route_amount == 0:",
    "                                        fan_weighted += route_amount * (route_fan - 1.0)",
    "                base = base + __WEIGHT__ * round(fan_weighted, 1)",
]

FANMAX_BLOCK = [
    "                fan_best = 0.0",
    "                routes_for_fan = action.get(\"routes\")",
    "                if routes_for_fan is not None and len(routes_for_fan) > 0 and action.get(\"value_coverage\") == \"complete\":",
    "                    for route in routes_for_fan:",
    "                        route_fan = 1.0",
    "                        route_settlement = route.get(\"conditional_settlement\")",
    "                        if route_settlement is not None:",
    "                            raw_route_fan = route_settlement.get(\"fan\")",
    "                            if raw_route_fan is not None and raw_route_fan is not True and raw_route_fan is not False:",
    "                                converted_route_fan = float(raw_route_fan)",
    "                                if converted_route_fan - converted_route_fan == 0 and converted_route_fan > 1.0:",
    "                                    route_fan = converted_route_fan",
    "                        route_support = 0.0",
    "                        route_tiles = route.get(\"useful_tiles\")",
    "                        if route_tiles is not None:",
    "                            for route_tile in route_tiles:",
    "                                route_remaining = route_tile.get(\"remaining_estimate\")",
    "                                if route_remaining is not None and route_remaining is not True and route_remaining is not False:",
    "                                    route_amount = float(route_remaining)",
    "                                    if route_amount - route_amount == 0:",
    "                                        route_support += route_amount",
    "                        route_value = route_support * (route_fan - 1.0)",
    "                        if route_value > fan_best:",
    "                            fan_best = route_value",
    "                base = base + __WEIGHT__ * round(fan_best, 1)",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="0.25,1,4")
    args = ap.parse_args()
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)
    names = []
    for variant, block_lines in (("FANW", FANW_BLOCK), ("FANMAX", FANMAX_BLOCK)):
        for token in args.weights.split(","):
            weight = token.strip()
            if not weight:
                continue
            block = "\n".join(line.replace("__WEIGHT__", weight) for line in block_lines) + "\n"
            candidate = source.replace(ANCHOR, ANCHOR + block)
            added = len(block.splitlines())
            assert len(candidate.splitlines()) - len(source.splitlines()) == added, "插入行数不符"
            assert candidate.count(ANCHOR) == 1, "锚点被破坏"
            name = "OPTY-R18-C18-%s%s.py" % (variant, weight.replace(".", "_"))
            path = _project_file(_PROJECT_ROOT, OUT / name)
            path.write_text(candidate, encoding="utf-8")
            compile(candidate, str(path), "exec")
            names.append(name)
    print("生成 %d 个候选：" % len(names))
    for name in names:
        print("  candidates/" + name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
