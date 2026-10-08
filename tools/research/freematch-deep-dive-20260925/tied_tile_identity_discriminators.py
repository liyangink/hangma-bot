"""主审：并列候选的有效牌集合「只是牌不同」时，它们还有哪些可观测的差别。

已知（11968 窗口）：前两名同分 2970 个；其中 1804 个有效牌集合不同，
而这 1804 个里 1599 个**种数相同、总数相同**——差别纯在「是哪几张牌」。
本脚本检验：这些牌的身份里有没有可用的判别量。
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
wins = collections.Counter()   # 每一项：a 比 b 多（+）或少（-）

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
    actions = {c["action_key"]: c for c in (view.get("actions") or [])}
    fa = actions.get(a["action_key"]) or {}
    fb = actions.get(b["action_key"]) or {}
    ua = {t.get("code") for t in (fa.get("useful_tiles") or [])}
    ub = {t.get("code") for t in (fb.get("useful_tiles") or [])}
    if ua == ub or len(ua) != len(ub):
        continue          # 只看「同总数同种数、只是牌不同」的那一类
    stats["pairs"] += 1
    visible = view.get("visible_state") or {}
    discards = visible.get("discards") or []
    seat = visible.get("seat")
    others = [d for i, d in enumerate(discards) if i != seat]
    seen = collections.Counter()
    for river in others:
        for tile in river or []:
            seen[tile] += 1
    wealth = (visible.get("rule_state") or {}).get("wealth_god")
    for name, key in (("别人打过的牌多", lambda s: sum(seen[t] for t in s)),
                      ("含财神", lambda s: 1 if wealth in s else 0),
                      ("含字牌", lambda s: sum(1 for t in s if t in "东南西北中发白"))):
        da = key(ua) - key(ub)
        if da > 0:
            wins[name + ":a多"] += 1
        elif da < 0:
            wins[name + ":b多"] += 1
        else:
            wins[name + ":相同"] += 1

p = max(1, stats["pairs"])
print("同总数同种数、仅牌不同的并列对: %d" % stats["pairs"])
print()
for suffix in ("a多", "b多", "相同"):
    print("-- %s" % suffix)
    for name in ("别人打过的牌多", "含财神", "含字牌"):
        print("   %-16s %5d (%.1f%%)" % (name, wins[name + ":" + suffix], 100.0*wins[name + ":" + suffix]/p))
print()
print("注：a = 父代按 action_key 挑中的那个，b = 另一个。")