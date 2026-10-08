#!/usr/bin/env python3
"""C19 第二步：**赢牌那一刻，财神是「浮着的」还是「吃进面子里的」？**

C19 第一步已排除选择效应：同局同胡牌次数分层后，我方均番仍低 0.13 番、
爆头占比仍低 ~10 个百分点（层内效应 −0.1328 / 组成效应 +0.0053）。
所以缺口是真实的，问题变成「为什么」。

爆头的定义（官方 v23 §1.2 + `hand_analysis.any_tile_win`）：摸前 13 张接任意可得牌均成胡。
最常见的形态是「4 面子 + 一张浮着的财神」——此时摸到的任何牌都当将。
⇒ **财神必须浮着；若财神被吃进面子（白搭顺子/白作将/白白自对），就没有爆头。**

`rounds.jsonl` 的每座记录里已经有 `white_float` / `white_in_face` / `white_in_pair`
（赢牌分解口径），本脚本据此直接比对**我方 vs 对手在赢牌时的财神用法**。

只读脚本。
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
    stats = collections.defaultdict(lambda: collections.Counter())
    fan_by_group = collections.defaultdict(list)
    float_by_group = collections.defaultdict(list)
    rows = 0
    with ROUNDS.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("is_draw"):
                continue
            winner = row.get("winner_seat")
            if winner is None:
                continue
            group = None
            for seat_row in row.get("seats") or ():
                if seat_row.get("seat") != winner:
                    continue
                group = "me" if seat_row.get("is_me") else "op"
                if not seat_row.get("won"):
                    continue
                rows += 1
                detail = row.get("detail") or []
                is_baotou = any("爆头" in str(item) for item in detail)
                float_count = seat_row.get("white_float")
                face_count = seat_row.get("white_in_face")
                pair_count = seat_row.get("white_in_pair")
                whites_end = seat_row.get("whites_end")
                melds = seat_row.get("melds_end")
                key = (group, bool(is_baotou))
                stats[key]["n"] += 1
                stats[key]["melds"] += int(melds or 0)
                stats[key]["whites_end"] += int(whites_end or 0)
                if isinstance(float_count, int):
                    stats[key]["float_%d" % min(float_count, 2)] += 1
                if isinstance(face_count, int):
                    stats[key]["face_%d" % min(face_count, 2)] += 1
                if isinstance(pair_count, int):
                    stats[key]["pair_%d" % min(pair_count, 2)] += 1
                if isinstance(float_count, int):
                    float_by_group[group].append(float_count)
                fan = row.get("fan")
                if isinstance(fan, (int, float)):
                    fan_by_group[group].append(float(fan))
            _ = group
    print("参与统计的赢牌次数 =", rows)
    print()
    print("| 组 | 是否爆头 | n | 均番 | 均浮财神 | 均副露 | 浮=0 | 浮≥1 | 财神进面子≥1 | 财神作将≥1 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for group in ("me", "op"):
        for baotou in (True, False):
            cell = stats[(group, baotou)]
            n = max(1, cell["n"])
            print("| %s | %s | %d | %.4f | %.4f | %.4f | %d | %d | %d | %d |"
                  % ("我方" if group == "me" else "对手",
                     "是" if baotou else "否", cell["n"],
                     statistics.fmean(fan_by_group[group]) if fan_by_group[group] else 0.0,
                     cell["float_0"] * 0.0 + (cell["float_1"] + 2 * cell["float_2"]) / n,
                     cell["melds"] / n,
                     cell["float_0"], cell["float_1"] + cell["float_2"],
                     cell["face_1"] + cell["face_2"], cell["pair_1"] + cell["pair_2"]))
    print()
    for group in ("me", "op"):
        values = float_by_group[group]
        if values:
            print("%s：赢牌时浮财神张数 均值 %.4f，浮=0 占比 %.2f%%，浮≥2 占比 %.2f%%"
                  % ("我方" if group == "me" else "对手",
                     statistics.fmean(values),
                     100.0 * sum(1 for v in values if v == 0) / len(values),
                     100.0 * sum(1 for v in values if v >= 2) / len(values)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
