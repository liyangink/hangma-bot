#!/usr/bin/env python3
"""C19 前置：**番值缺口里有多少是「赢得多的选择效应」？**

诊断链一直建立在一条横截面上：「我方胡牌平均番值低于对手」。
但胡牌次数与单次番值可能是同一枚硬币的两面：赢得越多，边际上的胜利越可能是
「容易的小胡」。若如此，「榜上强手番值高」就有一部分是他们**赢得少**的机械后果，
而不是他们更会做牌。

本脚本只用 `review/baotou-anatomy-20260925/rounds.jsonl`（3,920 局，含每座已核实字段）：

  1. 按「该座在该局的胡牌次数」分层，比对我方与对手的单次均番；
  2. 层内配对（同局同胡牌次数）差；
  3. 把总缺口分解成 组成效应（层占比差 × 层均番差）与 层内效应；
  4. 报「爆头明细」占比的同口径分解。

只读脚本，不写任何既有文件。
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

import collections
import json
import statistics
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
ROUNDS = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')


def main() -> int:
    games = collections.defaultdict(list)
    with ROUNDS.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            games[row["game_id"]].append(row)

    # 每 (game, seat) 的胡牌记录
    seat_wins = collections.defaultdict(list)   # (game, seat) -> [fan, ...]
    seat_baotou = collections.defaultdict(list)  # (game, seat) -> [bool, ...]
    seat_is_me = {}
    for game_id, rounds in games.items():
        for row in rounds:
            if row.get("is_draw"):
                continue
            winner = row.get("winner_seat")
            if winner is None:
                continue
            fan = row.get("fan")
            if not isinstance(fan, (int, float)) or fan <= 0:
                continue
            detail = row.get("detail") or []
            is_baotou = any("爆头" in str(item) for item in detail)
            seat_wins[(game_id, winner)].append(float(fan))
            seat_baotou[(game_id, winner)].append(is_baotou)
        for seat_row in rounds[0].get("seats", []):
            seat_is_me[(game_id, seat_row["seat"])] = bool(seat_row.get("is_me"))

    # 分层统计
    strata = collections.defaultdict(lambda: {"me": [], "op": [], "me_bt": [], "op_bt": []})
    for key, fans in seat_wins.items():
        count = len(fans)
        group = "me" if seat_is_me.get(key) else "op"
        strata[count][group].extend(fans)
        strata[count][group + "_bt"].extend(seat_baotou[key])

    total_me = sum(len(v["me"]) for v in strata.values())
    total_op = sum(len(v["op"]) for v in strata.values())
    print("我方胡牌 %d 次；对手三座胡牌 %d 次" % (total_me, total_op))
    print()
    print("| 该局胡牌次数 | 我方 n | 我方均番 | 对手 n | 对手均番 | 差 | 我方爆头占比 | 对手爆头占比 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for count in sorted(strata):
        cell = strata[count]
        if not cell["me"] or not cell["op"]:
            continue
        me_fan = statistics.fmean(cell["me"])
        op_fan = statistics.fmean(cell["op"])
        me_bt = 100.0 * sum(cell["me_bt"]) / max(1, len(cell["me_bt"]))
        op_bt = 100.0 * sum(cell["op_bt"]) / max(1, len(cell["op_bt"]))
        print("| %d | %d | %.4f | %d | %.4f | %+.4f | %.2f%% | %.2f%% |"
              % (count, len(cell["me"]), me_fan, len(cell["op"]), op_fan,
                 me_fan - op_fan, me_bt, op_bt))

    overall_me = statistics.fmean([f for v in strata.values() for f in v["me"]])
    overall_op = statistics.fmean([f for v in strata.values() for f in v["op"]])
    print()
    print("总均番：我方 %.4f，对手 %.4f，差 %+.4f" % (overall_me, overall_op, overall_me - overall_op))

    # 分解：以对手的层占比为权重（直接标准化）
    op_share = {}
    for count, cell in strata.items():
        op_share[count] = len(cell["op"]) / max(1, total_op)
    standardized_me = 0.0
    within = 0.0
    composition = 0.0
    for count, cell in strata.items():
        if not cell["me"] or not cell["op"]:
            continue
        me_fan = statistics.fmean(cell["me"])
        op_fan = statistics.fmean(cell["op"])
        me_share = len(cell["me"]) / max(1, total_me)
        standardized_me += op_share[count] * me_fan
        within += op_share[count] * (me_fan - op_fan)
        composition += (me_share - op_share[count]) * me_fan
    print("按对手层占比直接标准化后，我方均番 = %.4f（原 %.4f）" % (standardized_me, overall_me))
    print("分解：层内效应 %+.4f，组成效应 %+.4f（合计 %+.4f，总差 %+.4f）"
          % (within, composition, within + composition, overall_me - overall_op))
    print()
    print("口径：单一律为「该座在该局胡了几次」；爆头取 detail 里出现「爆头」字样。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
