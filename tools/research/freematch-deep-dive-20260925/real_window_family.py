#!/usr/bin/env python3
"""主审：真实审计里的窗口族分布与「父代靠常数否掉鸣牌」的真实占比。

regret 批次的面板是**分层抽样**（800 DRAW / 800 响应），所以它给出的
「(pass,chi) 占 16.4%」不能直接外推到线上决策分布。本脚本在**全部真实窗口**上重算同一张表。
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
import math
import statistics
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))

import p6_lib  # noqa: E402


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def chosen_entry(entries):
    return min(entries, key=lambda e: (-float(e["score"]), e["action_key"]))


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    cell = collections.Counter()
    gap_by_cell = collections.defaultdict(list)
    phase_counts = collections.Counter()
    total = 0
    errors = 0
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        total += 1
        try:
            entries = parent(view)["entries"]
        except Exception:
            errors += 1
            continue
        if len(entries) < 2:
            phase_counts["单候选"] += 1
            continue
        ranked = sorted(entries, key=lambda e: (-float(e["score"]), e["action_key"]))
        phase = str(row.get("phase") or (view.get("window") or {}).get("phase") or "?")
        phase_counts[phase] += 1
        k1, k2 = kind_of(ranked[0]["action_key"]), kind_of(ranked[1]["action_key"])
        cell[(k1, k2)] += 1
        gap_by_cell[(k1, k2)].append(float(ranked[1]["score"]) - float(ranked[0]["score"]))

    print("真实窗口总数：%d（评分异常 %d）" % (total, errors))
    print("phase 分布：%s" % dict(phase_counts.most_common()))
    print()
    print("## (首选族, 次选族) 的真实占比与前 6\n")
    print("| (首选,次选) | 窗数 | 占全部 | 分差中位 | 分差 Q1 | 分差 Q3 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for (k1, k2), n in cell.most_common(14):
        gaps = gap_by_cell[(k1, k2)]
        s = sorted(gaps)
        q1 = s[len(s) // 4]
        q3 = s[3 * len(s) // 4]
        print("| (%s,%s) | %d | %.2f%% | %+.1f | %+.1f | %+.1f |"
              % (k1, k2, n, 100.0 * n / total, statistics.median(gaps), q1, q3))

    print()
    print("## 关键可达性：父代「只靠常数」否掉鸣牌的窗口占比\n")
    for label, k2 in (("次选=chi", "chi"), ("次选=peng", "peng")):
        sub = [(k1, k2) for k1 in cell if False]
        n_any = sum(n for (k1, kk), n in cell.items() if kk == k2)
        n_close = 0
        for (k1, kk), gaps in gap_by_cell.items():
            if kk != k2:
                continue
            n_close += sum(1 for g in gaps if -12.5 < g < 0)
        print("- 首选族任意、%s：窗 %d（%.2f%%）；其中分差在 (−12.5, 0) 的 %d（%.2f%%）"
              % (label, n_any, 100.0 * n_any / total, n_close, 100.0 * n_close / total))

    print()
    print("## 响应窗（首选=pass）分差分布\n")
    gaps = gap_by_cell.get(("pass", "chi"), []) + gap_by_cell.get(("pass", "peng"), [])
    if gaps:
        s = sorted(gaps)
        print("- (pass,chi)+(pass,peng)：窗 %d，中位 %+.1f，Q1 %+.1f，Q3 %+.1f"
              % (len(s), statistics.median(s), s[len(s) // 4], s[3 * len(s) // 4]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
