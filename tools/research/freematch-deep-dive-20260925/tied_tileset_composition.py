"""主审：并列窗口里，两个候选的「有效牌集合」到底差在哪一维。

父代 support = Σ remaining，把「4 种各 3 张」与「3 种各 4 张」视为相同。
本脚本量化这种「同总数、不同构成」的规模，并与 P13（宽度项）的结论对账。
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
import sys, collections
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))
import p6_lib

namespace = {"__name__": "frozen"}
exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
parent = namespace["score_actions"]

stats = collections.Counter()
breadth_delta = collections.Counter()

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
    stats["windows"] += 1
    ordered = sorted(entries, key=lambda e: (-float(e["score"]), e["action_key"]))
    a, b = ordered[0], ordered[1]
    if float(a["score"]) != float(b["score"]):
        continue
    stats["tied"] += 1
    actions = {c["action_key"]: c for c in (view.get("actions") or [])}
    fa = actions.get(a["action_key"]) or {}
    fb = actions.get(b["action_key"]) or {}
    ua = fa.get("useful_tiles") or []
    ub = fb.get("useful_tiles") or []
    sa = {(t.get("code"), t.get("remaining_estimate")) for t in ua}
    sb = {(t.get("code"), t.get("remaining_estimate")) for t in ub}
    if sa == sb:
        stats["identical_tileset"] += 1
        continue
    stats["different_tileset"] += 1
    ka = {t.get("code") for t in ua}
    kb = {t.get("code") for t in ub}
    if ka != kb:
        stats["different_kinds"] += 1
        breadth_delta[len(ka) - len(kb)] += 1
    else:
        stats["same_kinds_diff_counts"] += 1

w = max(1, stats["windows"])
t = max(1, stats["tied"])
print("计分窗口 %d；前两名完全同分 %d (%.1f%%)" % (stats["windows"], stats["tied"], 100.0*stats["tied"]/w))
print()
print("并列窗口里：")
print("  有效牌集合完全相同     %5d (%.1f%% of 并列, %.1f%% of 全部)"
      % (stats["identical_tileset"], 100.0*stats["identical_tileset"]/t, 100.0*stats["identical_tileset"]/w))
print("  有效牌集合不同         %5d (%.1f%% of 并列, %.1f%% of 全部)"
      % (stats["different_tileset"], 100.0*stats["different_tileset"]/t, 100.0*stats["different_tileset"]/w))
print("    ├ 有效牌**种数**不同   %5d (%.1f%% of 全部)"
      % (stats["different_kinds"], 100.0*stats["different_kinds"]/w))
print("    └ 种数相同、张数不同   %5d (%.1f%% of 全部)"
      % (stats["same_kinds_diff_counts"], 100.0*stats["same_kinds_diff_counts"]/w))
print()
if breadth_delta:
    print("种数差的分布（a的种数 - b的种数）：", dict(sorted(breadth_delta.items())))