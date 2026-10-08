"""多白飘的爆头存活检验：两个（三个）白时打一张，弃后是否仍是爆头？

按 RULES_EVIDENCE §8：飘之后爆头**用弃后暗牌重算**。因此"飘=爆头×2 换链×2"只对
**单白**成立；多白时可能**爆头与链同时保住**，追的门槛回到 50%。
本脚本用规则引擎逐个重算，并给出精确的追/收对照。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import json
import os
import sys

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

import sitin_k_turn_exact as kt  # noqa: E402
import sitin_opportunity_positions as opp  # noqa: E402
from hangma_bot.hangma.progression import recompute_baotou  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

WHITE = "白"


def templates():
    """模板 = (名称, 摸牌前 13 张手牌, 要摸的那张)。

    关键对照（用户指出的情形）：**四副面子 + 一张白，摸到第二张白** ⇒ 打一张白（飘）后
    仍是「四副面子 + 一张白」，按弃后暗牌重算**依然是任意听**，爆头存活 ⇒ 爆头 ×2 与链 ×2
    可以同时拿到。其余模板作为反例（摸非白、或结构不满足任意听）。
    """
    melds = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b"]
    four_melds = tuple(melds + [WHITE])                      # 四副面子 + 白（13 张）
    three_melds = tuple(melds[:9] + [WHITE, WHITE, "1b", "3b"])  # 三副面子 + 双白 + 散张
    return [
        ("4m+W draw W", four_melds, WHITE),                  # ★ 用户指出的情形
        ("4m+W draw 5t", four_melds, "5t"),                  # 反例：摸非白
        ("3m+2W draw W", three_melds, WHITE),                # 反例：双白但结构非任意听
        ("3m+2W draw 2b", three_melds, "2b"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", default="4,8,12")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    turns_list = [int(x) for x in args.turns.split(",") if x.strip()]

    rows = []
    for name, hand, draw in templates():
        world = kt.world_of(hand)
        if world.get(draw, 0) <= 0:
            continue
        # 飘发生在**摸牌后的 14 张**上：先加摸到的牌，再去掉一张白（修正上一版从 13 张里去的错误）
        hand14 = list(hand) + [draw]
        post = list(hand14)
        post.remove(WHITE)
        post = tuple(post)
        whites_after = sum(1 for code in post if code == WHITE)
        baotou_after = recompute_baotou(tuple(Tile(c) for c in post), 0, whites_after)
        record = {"name": name, "hand": "".join(hand), "draw": draw,
                  "whites_before": sum(1 for c in hand if c == WHITE),
                  "whites_after": whites_after, "baotou_after_piao": bool(baotou_after)}
        for turns in turns_list:
            row = kt.chase_versus_take(hand, world, draw, True, 0, turns)
            record["k%d" % turns] = {
                "fan_take": row.get("fan_take"),
                "fan_chase_per_hit": row.get("fan_chase_per_hit"),
                "E_chase": (None if row.get("expectation_chase") is None
                            else round(row["expectation_chase"], 4)),
                "P_chase": (None if row.get("probability_chase") is None
                            else round(row["probability_chase"], 4)),
                "breakeven": row.get("breakeven_probability"),
                "chase_better": bool(row.get("expectation_chase") is not None
                                     and row.get("fan_take") is not None
                                     and row["expectation_chase"] > row["fan_take"]),
            }
        rows.append(record)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "multi-white.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": "sitin-multi-white-piao/1", "rows": rows}, fh,
                  ensure_ascii=False, indent=1)

    print("%-14s %-5s %-6s %-9s %-8s %-9s %-9s %-9s %-6s" % (
        "模板", "白前", "白后", "弃后爆头", "k", "fan(收)", "E(追)", "P(追再胡)", "平衡"))
    for row in rows:
        for turns in turns_list:
            cell = row["k%d" % turns]
            print("%-14s %-5d %-6d %-9s %-8d %-9s %-9s %-9s %-6s" % (
                row["name"], row["whites_before"], row["whites_after"],
                row["baotou_after_piao"], turns, cell["fan_take"], cell["E_chase"],
                cell["P_chase"], cell["breakeven"]))
    survived = [r for r in rows if r["baotou_after_piao"]]
    print()
    print("弃后仍爆头的模板数：%d / %d" % (len(survived), len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
