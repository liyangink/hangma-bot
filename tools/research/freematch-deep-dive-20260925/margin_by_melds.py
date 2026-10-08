"""主审：在真实观测（32,374 窗口）上检验「无副露局面父代信息更少」这条线索的一个分量。

线索来自先导：排错窗口 79.3% 无副露，排对窗口只有 60.4%；且排错窗口的父代分差更小
（14.41 vs 23.81）。若两条同源，则大样本上应当看到：
    **无副露窗口的「父代前两名分差」系统性小于有副露窗口。**
若看到相反的结论（无副露时父代更自信），线索作废。
"""

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
import sys, collections, statistics
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))
import p6_lib

namespace = {"__name__": "frozen"}
exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
parent = namespace["score_actions"]

by_melds = collections.defaultdict(list)
by_melds_tied = collections.Counter()
total = collections.Counter()

for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
    view = row["view"]
    try:
        out = parent(view)
    except Exception:
        continue
    if out.get("status") != "SCORED":
        continue
    entries = out["entries"]
    if len(entries) < 2:
        continue
    ordered = sorted(entries, key=lambda e: (-float(e["score"]), e["action_key"]))
    margin = float(ordered[0]["score"]) - float(ordered[1]["score"])
    visible = view.get("visible_state") or {}
    seat = visible.get("seat")
    melds = visible.get("melds") or []
    try:
        own = len(melds[seat])
    except Exception:
        continue
    key = min(own, 2)
    by_melds[key].append(margin)
    total[key] += 1
    if margin == 0.0:
        by_melds_tied[key] += 1

print("真实观测上的「父代前两名分差」（按自家副露数分层）：")
print()
print("| 自家副露 | 窗口 | 分差中位 | 分差均值 | 完全并列占比 |")
print("| --- | --- | --- | --- | --- |")
for key in sorted(by_melds):
    xs = by_melds[key]
    if not xs:
        continue
    print("| %d | %d | %.1f | %.1f | %.2f%% |"
          % (key, len(xs), statistics.median(xs), statistics.fmean(xs),
             100.0 * by_melds_tied[key] / len(xs)))
print()
no = by_melds.get(0, [])
yes = by_melds.get(1, []) + by_melds.get(2, [])
if no and yes:
    print("无副露 中位 %.1f（n=%d） vs 有副露 中位 %.1f（n=%d）"
          % (statistics.median(no), len(no), statistics.median(yes), len(yes)))
    print("无副露 均值 %.1f vs 有副露 均值 %.1f" % (statistics.fmean(no), statistics.fmean(yes)))