#!/usr/bin/env python3
"""主审：庄家 8 倍杠杆下，我方坐庄表现 vs 对手坐庄表现。

崩盘局解剖独立复算确认结算结构：得分 = 底分1 × 番 ×（庄家 8 / 闲家 1），
即自摸时庄家付 8、闲家各付 1（庄胡则三家各付 8）。
⇒ **庄家是 8 倍杠杆位，庄家表现的一点点差距都会被放大。**
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

import json
import statistics
from collections import Counter, defaultdict

BT = "review/baotou-anatomy-20260925/rounds.jsonl"


def main() -> int:
    rows = []
    with open(BT) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            me = None
            for s in d.get("seats") or []:
                if s.get("is_me"):
                    me = s
            if me is None:
                continue
            rows.append((d, me))
    print("含我方座位局数 %d" % len(rows))

    dealer_rounds = 0
    dealer_wins = 0
    nondealer_rounds = 0
    nondealer_wins = 0
    opp_dealer_rounds = 0
    opp_dealer_wins = 0
    pts_dealer = []
    pts_non = []
    for d, me in rows:
        dealer = d.get("dealer")
        winner = d.get("winner_seat")
        draw = bool(d.get("is_draw"))
        scores = d.get("scores") or [0, 0, 0, 0]
        my_pts = scores[me["seat"]]
        if dealer == me["seat"]:
            dealer_rounds += 1
            if winner == me["seat"]:
                dealer_wins += 1
            pts_dealer.append(my_pts)
        else:
            nondealer_rounds += 1
            if winner == me["seat"]:
                nondealer_wins += 1
            pts_non.append(my_pts)
            if not draw and winner is not None and winner != me["seat"]:
                opp_dealer_rounds += 1
                if winner == dealer:
                    opp_dealer_wins += 1

    print()
    print("## 1. 座位杠杆")
    print()
    print("| 组 | 局数 | 我方胡率 | 均我方分 |")
    print("| --- | --- | --- | --- |")
    print("| 我方坐庄 | %d (%.1f%%) | %.2f%% | %+.2f |"
          % (dealer_rounds, 100.0 * dealer_rounds / len(rows), 100.0 * dealer_wins / dealer_rounds,
             statistics.fmean(pts_dealer)))
    print("| 我方不坐庄 | %d | %.2f%% | %+.2f |"
          % (nondealer_rounds, 100.0 * nondealer_wins / nondealer_rounds, statistics.fmean(pts_non)))
    print()
    print("## 2. 对手坐庄时，庄家胡不胡")
    print()
    print("- 对手坐庄且有人胡（非我方胡）：%d 局；其中**庄家自己胡** %d = %.2f%%"
          % (opp_dealer_rounds, opp_dealer_wins, 100.0 * opp_dealer_wins / max(1, opp_dealer_rounds)))
    print("- 说明：庄家和闲家在同一局里的胡率基准不同（庄家多摸一张）。")

    print()
    print("## 3. 每局净分按「我方是否坐庄」分解")
    print()
    dsum = sum(pts_dealer)
    nsum = sum(pts_non)
    print("- 我方坐庄贡献 %+d 分 / %d 局 = %+.2f 分/局" % (dsum, dealer_rounds, dsum / max(1, dealer_rounds)))
    print("- 我方不坐庄贡献 %+d 分 / %d 局 = %+.2f 分/局" % (nsum, nondealer_rounds, nsum / max(1, nondealer_rounds)))

    print()
    print("## 4. 结算形态分布（验证 8:1:1 / 8:8:8）")
    print()
    shape = Counter()
    for d, me in rows:
        if d.get("is_draw"):
            shape["流局"] += 1
            continue
        scores = tuple(sorted(d.get("scores") or []))
        shape[str(scores)] += 1
    for k, v in shape.most_common(8):
        print("- %s：%d" % (k, v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
