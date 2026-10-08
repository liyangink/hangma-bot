"""主审：父代前两名完全同分时，这两个候选在其它事实上是否有差别。

这是「无副露并列里有没有可预测优劣」的直接检验：
- 若并列的两个候选在**所有**其他事实上都相同 → 并列是不可约的，换任何破并列规则都没有靶子；
- 若它们在某些事实上系统性不同 → 那个事实就是缺失的比较量，是可写的候选。
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

FEATURES = ("shanten_after", "standard_shanten_after", "seven_pairs_shanten_after",
            "baotou_after")

tied = 0
diff = collections.Counter()
same_all = 0
by_melds_tied = collections.Counter()
diff_by_melds = collections.defaultdict(collections.Counter)

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
    a, b = ordered[0], ordered[1]
    if float(a["score"]) != float(b["score"]):
        continue
    tied += 1
    visible = view.get("visible_state") or {}
    seat = visible.get("seat")
    melds = visible.get("melds") or []
    try:
        own = min(len(melds[seat]), 2)
    except Exception:
        own = 0
    by_melds_tied[own] += 1
    actions = {c["action_key"]: c for c in (view.get("actions") or [])}
    fa = actions.get(a["action_key"]) or {}
    fb = actions.get(b["action_key"]) or {}
    any_diff = False
    for name in FEATURES:
        if fa.get(name) != fb.get(name):
            diff[name] += 1
            diff_by_melds[own][name] += 1
            any_diff = True
    # 有效牌集合是否不同
    ua = tuple(sorted((t.get("code"), t.get("remaining_estimate")) for t in (fa.get("useful_tiles") or [])))
    ub = tuple(sorted((t.get("code"), t.get("remaining_estimate")) for t in (fb.get("useful_tiles") or [])))
    if ua != ub:
        diff["useful_tiles"] += 1
        diff_by_melds[own]["useful_tiles"] += 1
        any_diff = True
    fam_a = str(fa.get("family_progress_entries"))
    fam_b = str(fb.get("family_progress_entries"))
    if fam_a != fam_b:
        diff["family_progress"] += 1
        diff_by_melds[own]["family_progress"] += 1
        any_diff = True
    if not any_diff:
        same_all += 1

print("父代前两名完全同分的窗口: %d" % tied)
print("  其中两个候选在**所有**被检事实上都相同: %d (%.1f%%)" % (same_all, 100.0*same_all/max(1,tied)))
print()
print("至少有一项不同的窗口里，各项差异出现的次数（可多项同时差）：")
for name, count in diff.most_common():
    print("   %-28s %5d (%.1f%%)" % (name, count, 100.0*count/max(1,tied)))
print()
print("按副露分层（并列窗口数 / 全同数）：")
for k in sorted(by_melds_tied):
    print("   副露 %d: %d 个并列窗口" % (k, by_melds_tied[k]))