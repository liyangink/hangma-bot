#!/usr/bin/env python3
"""C20：**多财神手牌（用户点名的 2 白 / 3 白）**——我们和对手各自换到了什么？

用户问题：「对于有较大番期望的手牌，如 2 白板 3 白板，分析是否延迟胡有更大牌期望」。

本脚本用 `rounds.jsonl` 的每座字段（`hand_end` / `white_in_face` / `white_in_pair` /
`white_float` / `whites_end` / `melds_end` / `won`）按「赢牌时手上财神张数」分层，
比对我方与对手的：胜率（该层出现次数 / 该层所在局数）、均番、爆头占比。

注意口径：这里统计的是**赢牌那一刻**的财神张数，属于条件在已赢样本上的观察，
不是「持有 2 白就该怎样」的因果结论——因果只能由 P24/P86 那类完整桌实验给。
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
    rows = 0
    wins = collections.defaultdict(list)      # (group, whites) -> [fan]
    baotou = collections.defaultdict(list)    # (group, whites) -> [bool]
    seat_rounds = collections.Counter()       # group -> 家-局数
    with ROUNDS.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            detail = row.get("detail") or []
            is_baotou = any("爆头" in str(item) for item in detail)
            fan = row.get("fan")
            for seat_row in row.get("seats") or ():
                group = "me" if seat_row.get("is_me") else "op"
                seat_rounds[group] += 1
                if not seat_row.get("won"):
                    continue
                hand_end = seat_row.get("hand_end") or []
                whites = sum(1 for tile in hand_end if str(tile).strip() == "白")
                # 手上没有但有副露里的财神时，用 white_in_face / white_in_pair 兜底
                whites += int(seat_row.get("white_in_face") or 0) + int(seat_row.get("white_in_pair") or 0)
                key = (group, whites)
                if isinstance(fan, (int, float)):
                    wins[key].append(float(fan))
                baotou[key].append(is_baotou)
                rows += 1
    print("赢牌记录 =", rows, "；家-局数：我方", seat_rounds["me"], "对手", seat_rounds["op"])
    print()
    print("| 赢牌时手上财神 | 我方 n | 我方均番 | 我方爆头 | 对手 n | 对手均番 | 对手爆头 | 番差 | 爆头差 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for whites in range(0, 5):
        me = wins[("me", whites)]
        op = wins[("op", whites)]
        if not me and not op:
            continue
        me_fan = statistics.fmean(me) if me else float("nan")
        op_fan = statistics.fmean(op) if op else float("nan")
        me_bt = 100.0 * sum(baotou[("me", whites)]) / max(1, len(me))
        op_bt = 100.0 * sum(baotou[("op", whites)]) / max(1, len(op))
        print("| %d | %d | %.4f | %.2f%% | %d | %.4f | %.2f%% | %+.4f | %+.2f pp |"
              % (whites, len(me), me_fan, me_bt, len(op), op_fan, op_bt, me_fan - op_fan, me_bt - op_bt))
    print()
    for group in ("me", "op"):
        total = sum(len(v) for (g, _), v in wins.items() if g == group)
        multi = sum(len(v) for (g, w), v in wins.items() if g == group and w >= 2)
        print("%s：赢牌 %d 次，其中赢牌时手上 ≥2 财神 %d 次（%.2f%%）"
              % ("我方" if group == "me" else "对手", total, multi, 100.0 * multi / max(1, total)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
