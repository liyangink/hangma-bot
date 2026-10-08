#!/usr/bin/env python3
"""主审：爆头进入率按「跑的策略版本」分组——v1 与 v2 的自然对照。"""
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
from collections import defaultdict

BT = "review/baotou-anatomy-20260925/rounds.jsonl"
V1 = ("r18-auto-match-campaign-20260923", "r18-integrated-positive-v1-auto-match")


def main() -> int:
    groups = defaultdict(lambda: {"rounds": 0, "me_enter": 0, "opp_rounds": 0, "opp_enter": 0,
                                  "me_win": 0, "me_bt_win": 0, "opp_win": 0, "opp_bt_win": 0})
    with open(BT) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            sess = d.get("session") or "?"
            key = "v1" if sess in V1 else ("v2" if "v2" in sess or "20260925b" in sess else "其他")
            g = groups[key]
            g["rounds"] += 1
            winner = d.get("winner_seat")
            for s in d.get("seats") or []:
                if s.get("is_me"):
                    g["me_enter"] += 1 if s.get("entered_baotou") else 0
                    if winner == s.get("seat"):
                        g["me_win"] += 1
                        g["me_bt_win"] += 1 if s.get("final_baotou") else 0
                else:
                    g["opp_rounds"] += 1
                    g["opp_enter"] += 1 if s.get("entered_baotou") else 0
                    if winner == s.get("seat"):
                        g["opp_win"] += 1
                        g["opp_bt_win"] += 1 if s.get("final_baotou") else 0
    print("| 策略组 | 局数 | 我方进入率 | 对手进入率 | 我方胡率 | 我方爆头占胡 | 对手胡率 | 对手爆头占胡 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for key in ("v1", "v2", "其他"):
        g = groups.get(key)
        if not g:
            continue
        r = g["rounds"]
        print("| %s | %d | %.2f%% | %.2f%% | %.2f%% | %.2f%% | %.2f%% | %.2f%% |"
              % (key, r, 100.0 * g["me_enter"] / r, 100.0 * g["opp_enter"] / max(1, g["opp_rounds"]),
                 100.0 * g["me_win"] / r, 100.0 * g["me_bt_win"] / max(1, g["me_win"]),
                 100.0 * g["opp_win"] / max(1, g["opp_rounds"]),
                 100.0 * g["opp_bt_win"] / max(1, g["opp_win"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
