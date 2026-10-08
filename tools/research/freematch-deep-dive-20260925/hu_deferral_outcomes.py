#!/usr/bin/env python3
"""主审：自然牌局里的「弃胡续打」到底赚不赚——56 个真实弃胡窗的结局。

父代有一个 hu_vs_nonwealth_baotou_cf 覆盖（r18_integrated_positive_v2.py:658-817）：
当首选是 hu、且存在一个「非财神弃牌能建的爆头路线」且该路线 min_route_fan > 立即胡番数时，
把那张弃牌提到 hu 分 + 1，**即主动放弃立即胡去追更大的牌**。

本脚本在 8 房 / 1,120 局的真实审计上找出全部这类窗口，并把结局与「当场就胡」的窗口对照。
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
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))

import p6_lib  # noqa: E402

BT = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def chosen_entry(entries):
    return min(entries, key=lambda e: (-float(e["score"]), e["action_key"]))


def main() -> int:
    rounds = {}
    with open(BT) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            rounds[(d.get("game_id"), d.get("round_no"))] = d

    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    decisions = collections.defaultdict(list)
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        try:
            entries = parent(view)["entries"]
        except Exception:
            continue
        if not entries:
            continue
        kinds = {kind_of(e["action_key"]) for e in entries}
        if "hu" not in kinds:
            continue
        chosen = chosen_entry(entries)
        hu_entry = None
        for e in entries:
            if kind_of(e["action_key"]) == "hu":
                hu_entry = e
        decisions[(row["game_id"], row["round_no"])].append({
            "took": kind_of(chosen["action_key"]) == "hu",
            "chosen": chosen["action_key"],
            "chosen_score": float(chosen["score"]),
            "hu_score": float(hu_entry["score"]) if hu_entry else None,
            "trace": (chosen.get("trace") or {}).get("hu_vs_nonwealth_baotou_cf"),
        })

    print("含 hu 合法窗的单局：%d" % len(decisions))
    rows_out = []
    for key, items in decisions.items():
        rec = rounds.get(key)
        if rec is None:
            continue
        me = None
        for s in rec.get("seats") or []:
            if s.get("is_me"):
                me = s
        if me is None:
            continue
        winner = rec.get("winner_seat")
        scores = rec.get("scores") or [0, 0, 0, 0]
        declined = [x for x in items if not x["took"]]
        rows_out.append({
            "key": key,
            "declined": bool(declined),
            "n_hu_windows": len(items),
            "i_won": winner == me.get("seat"),
            "fan": rec.get("fan"),
            "detail": rec.get("detail") or [],
            "my_pts": scores[me.get("seat")],
            "hu_fan_at_decline": (declined[0]["trace"] or {}).get("hu_fan") if declined else None,
            "target": (declined[0]["trace"] or {}).get("target_action") if declined else None,
        })

    dec = [r for r in rows_out if r["declined"]]
    took = [r for r in rows_out if not r["declined"]]
    print()
    print("## 有 hu 合法窗的单局结局")
    print()
    print("| 组 | 单局 | 我方胡 | 胡率 | 均番 | 均我方分 | 爆头占比 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for label, sub in (("当场就胡", took), ("**弃胡续打**", dec)):
        n = len(sub)
        if n == 0:
            continue
        w = sum(1 for r in sub if r["i_won"])
        fans = [r["fan"] for r in sub if r["i_won"] and r["fan"] is not None]
        pts = [r["my_pts"] for r in sub]
        bt = sum(1 for r in sub if r["i_won"] and "爆头" in (r["detail"] or []))
        print("| %s | %d | %d | %.1f%% | %.3f | %+.2f | %.1f%% |"
              % (label, n, w, 100.0 * w / n,
                 statistics.fmean(fans) if fans else float("nan"),
                 statistics.fmean(pts) if pts else float("nan"),
                 100.0 * bt / max(1, w)))
    print()
    print("## 弃胡窗逐例（前 25）")
    print()
    print("| 局 | 立刻胡的番 | 改追的弃牌 | 最终胡 | 最终番 | 牌型 | 本局分 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for r in dec[:25]:
        print("| %s#%s | %s | %s | %s | %s | %s | %+d |"
              % (r["key"][0][-12:], r["key"][1], r["hu_fan_at_decline"], r["target"],
                 "是" if r["i_won"] else "否", r["fan"], "+".join(r["detail"] or []), r["my_pts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
