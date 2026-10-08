#!/usr/bin/env python3
"""主审：v2 期「接线修复前 vs 修复后」的房级对照（同策略，聚类单位＝房）。

修复 = SSE 排队修复（跨局首弃牌 1/14 → 0/112）；修复前 v2 房是 09-25 15:00–17:00 的
r18-v2-sse-* 系列，修复后是 18:28 起的 r18-sse-freematch-campaign-20260925b。
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
import math
import statistics
from collections import defaultdict

SRC = "review/freematch-deep-dive-20260925/room-scores.json"
POST = "r18-sse-freematch-campaign-20260925b"


def cluster_ci(values):
    n = len(values)
    if n < 2:
        return None
    m = statistics.fmean(values)
    sd = statistics.stdev(values)
    se = sd / math.sqrt(n)
    return m, sd, n, m - 1.96 * se, m + 1.96 * se


def main() -> int:
    data = json.load(open(SRC))
    by_room = defaultdict(list)
    tag_of = {}
    for g in data["rooms"]:
        tag_of[g["room_id"]] = g["session_tag"]
    for g in data["games"]:
        by_room[g["room_id"]].append(g["my_total"])

    groups = defaultdict(list)
    for rid, vals in by_room.items():
        tag = tag_of.get(rid, "?")
        if tag == POST:
            groups["修复后（campaign b）"].append(sum(vals))
        elif "20260925" in tag and "campaign-20260925b" not in tag:
            groups["修复前（09-25 v2 各序列）"].append(sum(vals))
        elif tag in ("r18-auto-match-campaign-20260923", "r18-integrated-positive-v1-auto-match"):
            groups["v1 期"].append(sum(vals))
        else:
            groups["其他"].append(sum(vals))

    print("| 组 | 房数 | 场数 | 房均分（10 场） | 房级 SD | 95%% CI | 每场均分 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        c = cluster_ci(v)
        if not c:
            continue
        print("| %s | %d | %d | %+.1f | %.1f | [%+.1f, %+.1f] | %+.3f |"
              % (k, c[2], c[2] * 10, c[0], c[1], c[3], c[4], c[0] / 10.0))

    a = groups.get("修复前（09-25 v2 各序列）") or []
    b = groups.get("修复后（campaign b）") or []
    if len(a) >= 2 and len(b) >= 2:
        diff = statistics.fmean(b) - statistics.fmean(a)
        se = math.sqrt(statistics.variance(a) / len(a) + statistics.variance(b) / len(b))
        print()
        print("修复后 − 修复前 = **%+.1f 分/房**（每局 %+.3f），95%% CI [%+.1f, %+.1f]"
              % (diff, diff / 10.0, diff - 1.96 * se, diff + 1.96 * se))
        print()
        print("**这不是因果对照**：两期时段不同、对手池不同；修复针对的事件（跨局首弃牌）频率极低，")
        print("按机制本身在每局尺度上应当是零附近的效应。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
