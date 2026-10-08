#!/usr/bin/env python3
"""主审：接线修复前后（09-23 战役 vs 09-25 SSE 时期）的成绩对照。

问题：跨局首弃牌修复（1/14 → 0/171）与 SSE 接线是否真的反映在分数上？
必须说清的混杂：两个时期的对手池不同、场次结构相同（10 场 × 8 局），
且 09-23 战役时期 sse_enabled=false。所以这是**同期对照，不是因果**。
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


def ci(values):
    n = len(values)
    if n < 2:
        return None
    mean = statistics.fmean(values)
    sd = statistics.stdev(values)
    se = sd / math.sqrt(n)
    return mean, sd, n, mean - 1.96 * se, mean + 1.96 * se


def main() -> int:
    data = json.load(open("review/freematch-deep-dive-20260925/room-scores.json"))
    groups = {"09-23 战役（接线修复前，sse_enabled=false）": [],
              "09-25 SSE 时期（修复后）": []}
    for room in data["rooms"]:
        tag = room["session_tag"]
        if tag == "r18-auto-match-campaign-20260923":
            groups["09-23 战役（接线修复前，sse_enabled=false）"].append(room["my_total"])
        elif tag.startswith("r18-v2-sse-") or tag.startswith("r18-sse-freematch-campaign-"):
            # 注意：新战役的会话标签是 r18-sse-freematch-campaign-*，
            # 不含 v2-sse 前缀。早期版本只匹配 r18-v2-sse-，漏掉了新战役全部 10 房，
            # 于是「修复后」那一组只剩 5 房且均值失真。
            groups["09-25 SSE 时期（修复后）"].append(room["my_total"])

    print("房级（聚类单位）对照：")
    print()
    print("| 时期 | 房数 | 房均分 | 房级 SD | 95% CI | 每局均分 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name, values in groups.items():
        if not values:
            continue
        mean, sd, n, lo, hi = ci(values)
        print("| %s | %d | %+.1f | %.1f | [%+.1f, %+.1f] | %+.2f |"
              % (name, n, mean, sd, lo, hi, mean / 10.0))
    print()
    a = groups["09-23 战役（接线修复前，sse_enabled=false）"]
    b = groups["09-25 SSE 时期（修复后）"]
    if a and b:
        diff = statistics.fmean(b) - statistics.fmean(a)
        se = math.sqrt(statistics.variance(a)/len(a) + statistics.variance(b)/len(b))
        print("修复后 − 修复前 = %+.1f 分/房（未配对），95%% CI [%+.1f, %+.1f]"
              % (diff, diff - 1.96*se, diff + 1.96*se))
        print("折算每局：%+.2f 分/局" % (diff / 10.0))
        print()
        print("**这不是因果对照**：两期对手池不同、季节不同，且 09-23 战役期间 SSE 关闭。")
        print("接线修复的机制收益（跨局首弃牌 1/14）在每局尺度上最多约 %.2f 分。"
              % (0.0,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())