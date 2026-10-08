"""主审：route_value_seed 原版 vs 去掉路线项版的**直接**逐窗口比较。

上面两个候选各自对父代的改选率都在 30.7%，但那不能说明它们彼此是否相同。
本脚本直接比 A 与 B 在同一个窗口选了什么。
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

CAND = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
a = p6_lib.compile_candidate(_project_file(_PROJECT_ROOT, CAND / "OPTY-R18-C11-ROUTESEED-ORIGINAL.py"))
b = p6_lib.compile_candidate(_project_file(_PROJECT_ROOT, CAND / "OPTY-R18-C11-ROUTESEED-NOROUTE.py"))

stats = collections.Counter()
for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
    view = row["view"]
    stats["windows"] += 1
    try:
        oa = a(view); ob = b(view)
    except Exception:
        stats["error"] += 1
        continue
    if oa.get("status") != "SCORED" or ob.get("status") != "SCORED":
        stats["abstain"] += 1
        continue
    if p6_lib.pick(oa["entries"]) != p6_lib.pick(ob["entries"]):
        stats["differ"] += 1

w = max(1, stats["windows"])
print("窗口 %d" % stats["windows"])
print("原版与去路线项版**逐窗口不同**的比例: %d / %d = %.2f%%"
      % (stats["differ"], w, 100.0 * stats["differ"] / w))
print("异常 %d，弃权 %d" % (stats["error"], stats["abstain"]))