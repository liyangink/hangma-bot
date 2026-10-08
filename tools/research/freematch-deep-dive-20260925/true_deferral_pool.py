#!/usr/bin/env python3
"""主审：量出「真正的弃胡取舍池」在自然样本上有多大。

收紧谓词（见 P24 更正）：
  摸牌窗 ∧ hu 是当前首选 ∧ 立刻胡番数 == 1 ∧ 当前不在爆头态
  ∧ 存在合法非财神弃牌使 baotou_after is True 且 shanten_after == 0
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

    c = collections.Counter()
    rooms = set()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        c["windows"] += 1
        rooms.add(row["room"])
        try:
            entries = parent(view)["entries"]
        except Exception:
            c["error"] += 1
            continue
        if not entries:
            continue
        kinds = {kind_of(e["action_key"]) for e in entries}
        if "hu" not in kinds:
            continue
        chosen = chosen_entry(entries)
        if kind_of(chosen["action_key"]) != "hu":
            continue
        c["hu_top"] += 1
        info = (chosen.get("trace") or {}).get("hu_vs_nonwealth_baotou_cf") or {}
        fan = info.get("hu_fan")
        if fan != 1.0:
            continue
        c["hu_fan1"] += 1
        vis = view.get("visible_state") or {}
        rs = vis.get("rule_state") or {}
        if rs.get("baotou") is True:
            c["already_baotou"] += 1
            continue
        c["fan1_not_baotou"] += 1
        wealth = rs.get("wealth_god")
        actions = view.get("actions") or []
        found = None
        for action in actions:
            key = action.get("action_key")
            if action.get("is_legal") is not True or action.get("action_type") != "discard" or key is None:
                continue
            if wealth is not None and key[8:] == wealth:
                continue
            if action.get("baotou_after") is not True:
                continue
            if action.get("shanten_after") != 0:
                continue
            if found is None or key < found:
                found = key
        if found is not None:
            c["target"] += 1
            c["target_" + str(row["room"])] += 0
    print("房 %d，窗口 %d，异常 %d" % (len(rooms), c["windows"], c["error"]))
    print()
    print("| 层 | 窗数 |")
    print("| --- | --- |")
    print("| hu 是当前首选 | %d |" % c["hu_top"])
    print("| 立刻胡番数 = 1 | %d |" % c["hu_fan1"])
    print("| 且当前**不在**爆头态 | %d |" % c["fan1_not_baotou"])
    print("| 且存在「弃后即爆头」的合法非财神弃牌（**真正的取舍池**） | **%d** |" % c["target"])
    print()
    print("（已处于爆头态的 %d 个窗口是空转窗：弃胡番值不变，必须排除）" % c["already_baotou"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
