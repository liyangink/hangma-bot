#!/usr/bin/env python3
"""主审：爆头与副露/财神的关系——对手的爆头从哪来，我们的从哪来。"""
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
from collections import Counter, defaultdict

BT = "review/baotou-anatomy-20260925/rounds.jsonl"


def main() -> int:
    wins = []
    with open(BT) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            winner = d.get("winner_seat")
            if d.get("is_draw") or winner is None:
                continue
            scores = d.get("scores") or [0, 0, 0, 0]
            for s in d.get("seats") or []:
                if s.get("seat") != winner:
                    continue
                wins.append({
                    "is_me": bool(s.get("is_me")),
                    "melds": s.get("melds_end"),
                    "fan": d.get("fan"),
                    "pts": scores[winner],
                    "baotou": bool(s.get("final_baotou")),
                    "entered": bool(s.get("entered_baotou")),
                    "whites_drawn": s.get("whites_drawn"),
                    "whites_end": s.get("whites_end"),
                    "whites_discarded": s.get("whites_discarded"),
                    "details": d.get("detail") or [],
                    "start": s.get("first_std_tenpai_turn"),
                })
    print("胡牌座位-局 %d（我方 %d）" % (len(wins), sum(1 for w in wins if w["is_me"])))

    print()
    print("## 1. 按结束副露数分层：爆头率 / 均番 / 均分\n")
    print("| 副露数 | 组 | 胡牌数 | 爆头率 | 均番 | 均分 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for m in (0, 1, 2, 3, 4):
        for label, pred in (("我方", True), ("对手", False)):
            sub = [w for w in wins if w["is_me"] == pred and w["melds"] == m]
            if len(sub) < 30:
                continue
            bt = sum(1 for w in sub if w["baotou"]) / len(sub)
            print("| %d | %s | %d | %.1f%% | %.3f | %.2f |"
                  % (m, label, len(sub), 100 * bt,
                     statistics.fmean(w["fan"] for w in sub if w["fan"] is not None),
                     statistics.fmean(w["pts"] for w in sub if w["pts"] is not None)))

    print()
    print("## 2. 副露分布（占各自胡牌的比例）\n")
    for label, pred in (("我方", True), ("对手", False)):
        sub = [w for w in wins if w["is_me"] == pred]
        c = Counter(w["melds"] for w in sub)
        print("- %s：%s" % (label, {k: "%.1f%%" % (100 * v / len(sub)) for k, v in sorted(c.items())}))

    print()
    print("## 3. 财神账（每胡牌局）\n")
    print("| 组 | 平均摸到白板 | 平均打掉白板 | 终局持白 | 终局持白>=1 占比 |")
    print("| --- | --- | --- | --- | --- |")
    for label, pred in (("我方", True), ("对手", False)):
        sub = [w for w in wins if w["is_me"] == pred]
        d = [w["whites_drawn"] for w in sub if w["whites_drawn"] is not None]
        dd = [w["whites_discarded"] for w in sub if w["whites_discarded"] is not None]
        e = [w["whites_end"] for w in sub if w["whites_end"] is not None]
        ge1 = sum(1 for x in e if x >= 1) / len(e) if e else float("nan")
        print("| %s | %.3f | %.3f | %.3f | %.1f%% |" % (
            label, statistics.fmean(d) if d else float("nan"),
            statistics.fmean(dd) if dd else float("nan"),
            statistics.fmean(e) if e else float("nan"), 100 * ge1))

    print()
    print("## 4. 爆头胡的牌型构成（detail 集合）\n")
    for label, pred in (("我方", True), ("对手", False)):
        sub = [w for w in wins if w["is_me"] == pred and w["baotou"]]
        c = Counter("+".join(sorted(w["details"])) for w in sub)
        print("- %s（%d 次）：%s" % (label, len(sub), dict(c.most_common(8))))

    print()
    print("## 5. 未爆头胡的牌型构成\n")
    for label, pred in (("我方", True), ("对手", False)):
        sub = [w for w in wins if w["is_me"] == pred and not w["baotou"]]
        c = Counter("+".join(sorted(w["details"])) for w in sub)
        print("- %s（%d 次）：%s" % (label, len(sub), dict(c.most_common(8))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
