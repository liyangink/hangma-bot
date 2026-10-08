#!/usr/bin/env python3
"""C25：把「胡窗 x 爆头态 x 有靶」的列联表补全（P19/P24/P33 只覆盖了其中一格）。

未覆盖的一格：立刻胡番数 >= 2 AND 非爆头态 AND 存在「弃后即爆头」的合法弃牌。
若该格为 0，则「弃胡换爆头」这条轴的取值域是空的，与「阈值该定在哪」无关。
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


def hu_fan_of(actions):
    for action in actions:
        if action.get("action_type") != "hu" or action.get("is_legal") is not True:
            continue
        settlement = action.get("immediate_settlement")
        if settlement is None:
            continue
        fan = settlement.get("fan")
        if fan is None or fan is True or fan is False:
            continue
        return float(fan)
    return None


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    table = collections.Counter()
    windows = 0
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        windows += 1
        actions = view.get("actions") or []
        kinds = {kind_of(a.get("action_key")) for a in actions if a.get("is_legal") is True}
        if "hu" not in kinds:
            continue
        fan = hu_fan_of(actions)
        if fan is None:
            continue
        vis = view.get("visible_state") or {}
        rs = vis.get("rule_state") or {}
        baotou = rs.get("baotou") is True
        wealth = rs.get("wealth_god")
        target = False
        for action in actions:
            key = action.get("action_key")
            if action.get("is_legal") is not True or action.get("action_type") != "discard" or key is None:
                continue
            if wealth is not None and key[8:] == wealth:
                continue
            if action.get("baotou_after") is True and action.get("shanten_after") == 0:
                target = True
                break
        try:
            chosen = kind_of(chosen_entry(parent(view)["entries"])["action_key"])
        except Exception:
            chosen = "?"
        table[(fan, baotou, target, chosen)] += 1
    print("窗口数 =", windows)
    print()
    print("| 立刻胡番数 | 已在爆头态 | 有弃后即爆头靶 | 父代首选 | 窗数 |")
    print("| --- | --- | --- | --- | --- |")
    for (fan, baotou, target, chosen), n in sorted(table.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3])):
        print("| %.0f | %s | %s | %s | %d |" % (fan, "Y" if baotou else "N", "Y" if target else "N", chosen, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
