#!/usr/bin/env python3
"""主审：父代在「总分完全并列」时的真实排序依据是什么——量化 action_key 字典序带来的系统性偏好。

驱动按 (score 降序, action_key 升序) 排序，所以在完全并列时，
**父代总是弃掉 action_key 字典序最小的那张牌**。
本脚本在真实窗口上量化这会把弃牌推向哪些牌。
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


def suit_of(key):
    tile = key.split(":", 1)[1] if ":" in key else key
    if tile in ("东", "南", "西", "北", "中", "发", "白"):
        return "字牌"
    last = tile[-1] if tile else "?"
    return {"w": "万", "t": "条", "b": "筒"}.get(last, "未知")


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    c = collections.Counter()
    pair = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        try:
            entries = parent(view)["entries"]
        except Exception:
            continue
        cands = []
        for e in entries:
            t = e.get("trace") or {}
            if t.get("unknown") is True or t.get("hu_sorting_layer") is True:
                continue
            if (t.get("r18_opportunity_overlay") is not None or t.get("r18_gang_dominance_overlay") is not None
                    or t.get("r18_seven_pairs_value_overlay") is not None
                    or t.get("two_wealth_piao_keeps_baotou_cf") is not None):
                continue
            cfb = t.get("hu_vs_nonwealth_baotou_cf")
            if cfb is not None and cfb.get("triggered") is True:
                continue
            if e.get("action_key") is None or e.get("score") is None:
                continue
            cands.append(e)
        if len(cands) < 2:
            continue
        ranked = sorted(cands, key=lambda e: (-float(e["score"]), e["action_key"]))
        c["windows"] += 1
        if kind_of(ranked[0]["action_key"]) != "discard" or kind_of(ranked[1]["action_key"]) != "discard":
            c["not_discard_pair"] += 1
            continue
        if float(ranked[0]["score"]) != float(ranked[1]["score"]):
            c["not_tied"] += 1
            continue
        c["tied"] += 1
        w, l = suit_of(ranked[0]["action_key"]), suit_of(ranked[1]["action_key"])
        pair[(w, l)] += 1
    print("窗口 %d；其中前两名非弃牌对 %d、非并列 %d、**完全并列的弃牌对 %d**"
          % (c["windows"], c["not_discard_pair"], c["not_tied"], c["tied"]))
    if not c["tied"]:
        return 0
    print()
    print("## 并列时「被选中(字典序小)的牌类」× 「被放弃的牌类」\n")
    print("| 选中 | 放弃 | 窗数 | 占比 |")
    print("| --- | --- | --- | --- |")
    for (w, l), n in pair.most_common(12):
        print("| %s | %s | %d | %.1f%% |" % (w, l, n, 100.0 * n / c["tied"]))
    print()
    same = sum(n for (w, l), n in pair.items() if w == l)
    print("选中与放弃**同类**：%d（%.1f%%）；**跨类**：%d（%.1f%%）"
          % (same, 100.0 * same / c["tied"], c["tied"] - same, 100.0 * (c["tied"] - same) / c["tied"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
