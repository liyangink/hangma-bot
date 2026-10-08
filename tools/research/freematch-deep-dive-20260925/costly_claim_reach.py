#!/usr/bin/env python3
"""主审：给爆头路线做「代价鸣牌」的可达性测量。

动机：P19 已证明爆头缺口的决策空间是 0.0000%，而进入率低一半，
且 **75% 的「成形窗口」来自鸣牌之后**。P14 只测了「改鸣牌常数」——
那只能翻转**同向听**的过牌；它没有回答「**为了凑副露而接受一次向听退化的鸣牌**」有多少窗口。

本脚本在全部真实窗口上量这一条：
    过牌窗 ∩ 存在「向听恰好差 1」的鸣牌候选 ∩ 手上至少一张财神
分档给出改选率。
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


def shanten_of(entry):
    trace = entry.get("trace") or {}
    for key in ("shanten_after", "combined_shanten", "shanten"):
        value = trace.get(key)
        if type(value) is int:
            return value
    return None


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    stats = collections.Counter()
    by_cost = collections.Counter()
    by_whites = collections.Counter()
    by_melds = collections.Counter()
    total = 0
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        total += 1
        try:
            entries = parent(view)["entries"]
        except Exception:
            continue
        if len(entries) < 2:
            continue
        chosen = chosen_entry(entries)
        if kind_of(chosen["action_key"]) != "pass":
            continue
        stats["pass_windows"] += 1
        base_shanten = shanten_of(chosen)
        if base_shanten is None:
            stats["pass_shanten_unknown"] += 1
            continue
        vis = view.get("visible_state") or {}
        hand = vis.get("my_hand") or []
        wealth = (vis.get("rule_state") or {}).get("wealth_god")
        whites = hand.count(wealth) if wealth is not None else 0
        melds = vis.get("melds") or []
        seat = vis.get("seat")
        my_melds = len(melds[seat]) if isinstance(seat, int) and isinstance(melds, list) and len(melds) == 4 else 0
        best_gain = None
        for entry in entries:
            kind = kind_of(entry["action_key"])
            if kind not in ("chi", "peng", "gang"):
                continue
            sh = shanten_of(entry)
            if sh is None:
                continue
            cost = sh - base_shanten
            if best_gain is None or cost < best_gain:
                best_gain = cost
        if best_gain is None:
            continue
        by_cost[best_gain] += 1
        if best_gain <= 0:
            stats["claim_ok"] += 1
        if best_gain == 1:
            stats["claim_cost1"] += 1
            by_whites["whites>=1" if whites >= 1 else "whites=0"] += 1
            by_melds[str(my_melds)] += 1
            if whites >= 1 and my_melds >= 1:
                stats["claim_cost1_white_meld"] += 1
            if whites >= 1 and my_melds >= 2:
                stats["claim_cost1_white_2meld"] += 1
    print("真实窗口 %d" % total)
    print("父代选过的窗口(过牌)：%d（向听未知 %d）" % (stats["pass_windows"], stats["pass_shanten_unknown"]))
    print()
    print("## 过牌窗内，最优鸣牌候选相对过牌的向听代价分布（负数=更好）\n")
    tot = sum(by_cost.values()) or 1
    for k in sorted(by_cost):
        print("- 代价 %+d：%6d（%.2f%%）" % (k, by_cost[k], 100.0 * by_cost[k] / tot))
    print()
    print("## 关键可达性（分母 = 全部真实窗口 %d）\n" % total)
    for k in ("claim_ok", "claim_cost1", "claim_cost1_white_meld", "claim_cost1_white_2meld"):
        print("- %-28s %6d  %.4f%%" % (k, stats[k], 100.0 * stats[k] / total))
    print()
    print("代价 1 的窗口里，手持财神分布：%s" % dict(by_whites))
    print("代价 1 的窗口里，我方现有副露数：%s" % dict(sorted(by_melds.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
