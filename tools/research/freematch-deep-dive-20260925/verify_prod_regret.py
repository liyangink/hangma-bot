"""主审独立复算生产批（修正版）：父代值取 baseline_score，而不是 cf["1"]。

第一版只统计 cf 里含 "1" 的行，得到 160 窗——那是「父代自己被采样到」的行。
实际上每一行的 baseline_score 就是父代在该窗口的结果，
而 cf 只装「被强制的替代臂」。修正后应能复现作者的 1,600 窗口径。
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
import json, collections, statistics

rows = json.load(open(".team-work/rollout-regret-v1/prod/rows.json"))

def cf_arms(r):
    out = {}
    for k, v in (r.get("cf") or {}).items():
        if k == "1":
            continue          # 父代自己的值取 baseline_score，避免重复计入
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out

usable = []
for r in rows:
    base = r.get("baseline_score")
    arms = cf_arms(r)
    if not isinstance(base, (int, float)) or not arms:
        continue
    usable.append((r, float(base), arms))

n = len(usable)
print("可比窗口:", n)

hit = 0
regrets = []
Ac, Bc = [], []
for r, base, arms in usable:
    best = max(arms.values())
    if base >= best:
        hit += 1
    regret = best - base
    regrets.append(regret)
    if regret <= 0:
        continue
    pg = r.get("parent_gap") or {}
    gap = pg.get("2", pg.get(2))
    if gap == 0:
        Ac.append(regret)
    else:
        Bc.append(regret)

print("父代命中率（baseline ≥ 最好替代）: %d / %d = %.1f%%" % (hit, n, 100.0*hit/n))
print("regret: 均值 %+.2f 中位 %+.1f 最大 %+.0f" % (statistics.fmean(regrets), statistics.median(regrets), max(regrets)))
print("regret == 0 占比: %.1f%%" % (100.0*sum(1 for v in regrets if v <= 0)/n))
print()
print("A 类（gap 0）: n=%d 均值 %+.2f" % (len(Ac), statistics.fmean(Ac) if Ac else 0))
print("B 类（有分差）: n=%d 均值 %+.2f" % (len(Bc), statistics.fmean(Bc) if Bc else 0))
if Ac and Bc:
    ta, tb = sum(Ac), sum(Bc)
    print("regret 总量占比: A %.1f%% / B %.1f%%" % (100.0*ta/(ta+tb), 100.0*tb/(ta+tb)))
    print("A 占可比窗口 %.2f%%，B 占 %.1f%%" % (100.0*len(Ac)/n, 100.0*len(Bc)/n))
print()
print("按自家副露分层的父代命中率:")
g = collections.defaultdict(lambda: [0, 0])
for r, base, arms in usable:
    m = r.get("self_melds")
    if not isinstance(m, int):
        continue
    k = min(m, 2)
    g[k][1] += 1
    if base >= max(arms.values()):
        g[k][0] += 1
for k in sorted(g):
    h, t = g[k]
    print("   副露 %d: %4d / %4d = %.1f%%" % (k, h, t, 100.0*h/t))