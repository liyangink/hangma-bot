#!/usr/bin/env python3
"""第 6b 步：把「已成胡的摸牌窗口」与真实审计逐窗对齐（seq 容忍 ±4）。

审计侧：phase=draw 且 drawn_tile 非空（= 真摸牌窗口），my_hand 归一成 14-3m
后 win_split 判成胡；再看 hu 是否在真实合法候选里、plan_rank1 是什么。
重建侧：rounds.jsonl 的 hu_windows。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/baotou-anatomy-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import glob
import gzip
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from anatomy_lib import TILE_ORDER  # noqa: E402
from hangma_bot.hangma import hand_analysis  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

P6_CACHE = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route" / "cache")


def main():
    audit = {}
    for path in sorted(glob.glob(str(_project_file(_PROJECT_ROOT, P6_CACHE / "*.jsonl.gz")))):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                view = row["view"]
                v = view["visible_state"]
                if v["seat"] is None or v["phase"] != "draw":
                    continue
                hand = list(v["my_hand"])
                drawn = v["drawn_tile"]
                melds = len(v["melds"][v["seat"]])
                if drawn is None or len(hand) != 14 - 3 * melds:
                    continue
                if any(c not in TILE_ORDER for c in hand):
                    continue
                is_win = hand_analysis.win_split(
                    tuple(Tile(c) for c in hand), melds) is not None
                if not is_win:
                    continue
                audit[(row["game_id"], row["round_no"], row["trigger_seq"])] = {
                    "plan": row["plan_rank1"],
                    "hu_legal": "hu" in [a["action_key"] for a in view["actions"]],
                    "hand": hand, "melds": melds,
                }
    print("审计侧「摸牌窗口已成胡」窗口数：%d" % len(audit))
    plans = Counter(v["plan"] for v in audit.values())
    print("  父代选择分布（前 6）：", plans.most_common(6))
    print("  其中 hu 合法：%d；选 hu：%d；选弃牌：%d" % (
        sum(1 for v in audit.values() if v["hu_legal"]),
        sum(1 for v in audit.values() if v["plan"] == "hu"),
        sum(1 for v in audit.values() if v["plan"] != "hu")))

    matched = counter = 0
    agree = Counter()
    for line in open(_project_file(_PROJECT_ROOT, HERE / "rounds.jsonl"), encoding="utf-8"):
        row = json.loads(line)
        me = next((s for s in row["seats"] if s["is_me"]), None)
        if me is None:
            continue
        for w in me["hu_windows"]:
            seq = w[0]
            hit = None
            for offset in (0, 1, 2, 3, 4, -1, -2, -3, -4):
                hit = audit.get((row["game_id"], row["round_no"], seq + offset))
                if hit:
                    break
            if hit is None:
                continue
            matched += 1
            mine_hu = w[6] == "hu"
            theirs_hu = hit["plan"] == "hu"
            agree["一致" if mine_hu == theirs_hu else "不一致"] += 1
            if mine_hu != theirs_hu and agree["不一致"] <= 5:
                print("  不一致：", row["game_id"], row["round_no"], seq,
                      "重建选择", w[6], "审计选择", hit["plan"], "hu合法", hit["hu_legal"],
                      "靶子数", w[5])
            counter += 1
    print()
    print("可与审计逐窗对齐的重建 hu 窗口：%d" % matched)
    print("其中「重建判为选胡/弃胡」与审计 plan 一致：%s" % dict(agree))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
