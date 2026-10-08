#!/usr/bin/env python3
"""主审：把 regret 的 +2.49 拆成「窗口族 × 动作族」——它到底住在哪里。

join：regret 逐桌产物里的 task.window_record.window（game_id/phase/round_no/seat/trigger_seq）
与 prod/rows.json 的 (unit, round_no, trigger_seq, phase)。
候选全表取任一臂的 prefix_plan.candidates（与 rank1 的 window_record 同源，已抽样核对一致）。
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

import glob
import json
import math
import os
import statistics
from collections import Counter, defaultdict

CF = ".team-work/rollout-regret-v1/prod/cf"
ROWS = ".team-work/rollout-regret-v1/prod/rows.json"
ARMS = ("2", "3", "worst")
RANK_TAG = {"rank1": "1", "rank2": "2", "rank3": "3", "worst": "worst"}


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def load_cf():
    """返回 {(unit, phase, round_no, trigger_seq): {rank: payload}}。"""
    out = defaultdict(dict)
    for path in glob.glob(os.path.join(CF, "*.json")):
        name = os.path.basename(path)[:-5]
        if name.endswith("-worst"):
            tag, base = "worst", name[:-6]
        else:
            base, _, tag = name.rpartition("-")
        rank = RANK_TAG.get(tag)
        if rank is None:
            continue
        try:
            payload = json.load(open(path))
        except Exception:
            continue
        w = payload.get("task", {}).get("window_record", {}).get("window")
        if not w:
            continue
        unit = payload.get("unit")
        key = (unit, w.get("phase"), w.get("round_no"), w.get("trigger_seq"))
        out[key][rank] = payload
    return out


def unit_cluster(rows_pairs):
    """rows_pairs: [(unit, value)] → 单位聚类均值与 95% CI。"""
    per = defaultdict(list)
    for u, v in rows_pairs:
        per[u].append(v)
    vals = [statistics.fmean(v) for v in per.values()]
    n = len(vals)
    if n < 2:
        return None
    m = statistics.fmean(vals)
    se = statistics.stdev(vals) / math.sqrt(n)
    return m, n, m - 1.96 * se, m + 1.96 * se


def main() -> int:
    rows = json.load(open(ROWS))
    cf = load_cf()
    print("cf 窗口键 %d 个；rows.json %d 行" % (len(cf), len(rows)))

    joined = []
    for r in rows:
        key = (r["unit"], r["phase"], r["round_no"], r["trigger_seq"])
        recs = cf.get(key)
        if not recs:
            continue
        anyrec = None
        for a in ARMS:
            if a in recs:
                anyrec = recs[a]
                break
        if anyrec is None:
            continue
        plan = anyrec["prefix_plan"]["candidates"]
        if not plan:
            continue
        joined.append((r, plan, recs))
    print("成功 join %d / %d 窗" % (len(joined), len(rows)))

    print()
    print("## 1. 窗口族规模与 +2.49 的分布\n")
    print("| 分层 | 臂 | 窗数 | unit | Δ 均值 | unit 聚类 95% CI |")
    print("| --- | --- | --- | --- | --- | --- |")
    groups = {
        "全部": lambda r, plan: True,
        "二元响应窗(n_plan=2)": lambda r, plan: len(plan) == 2,
        "多元窗(n_plan>2)": lambda r, plan: len(plan) > 2,
        "DRAW": lambda r, plan: r["phase"] == "DRAW",
        "RESPONSE_CHI": lambda r, plan: r["phase"] == "RESPONSE_CHI",
        "RESPONSE_PENG": lambda r, plan: r["phase"] == "RESPONSE_PENG",
    }
    for gname, pred in groups.items():
        for arm in ARMS:
            pairs = []
            for r, plan, recs in joined:
                if arm not in recs or not pred(r, plan):
                    continue
                pairs.append((r["unit"], r["cf"][arm] - r["baseline_score"]))
            if len(pairs) < 20:
                continue
            res = unit_cluster(pairs)
            print("| %s | %s | %d | %d | %+.2f | [%+.2f, %+.2f] |"
                  % (gname, arm, len(pairs), res[1], res[0], res[2], res[3]))

    print()
    print("## 2. 父代首选动作族 vs 替代动作族（臂 2）\n")
    top_kind = Counter()
    pair_kind = Counter()
    for r, plan, recs in joined:
        if "2" not in recs:
            continue
        tk = kind_of(plan[0]["action_key"])
        alt_key = recs["2"]["forced_action_key"]
        ak = kind_of(alt_key)
        top_kind[tk] += 1
        pair_kind[(tk, ak)] += 1
    print("- 父代首选动作族：%s" % dict(top_kind.most_common()))
    print("- (首选族, 替代族) 前 10：%s" % dict(pair_kind.most_common(10)))

    print()
    print("## 3. 二元响应窗里「首选=过」vs「首选=鸣」的 Δ\n")
    print("| 首选族 | 替代族 | 窗数 | unit | Δ 均值 | 95% CI |")
    print("| --- | --- | --- | --- | --- | --- |")
    table = defaultdict(list)
    for r, plan, recs in joined:
        if "2" not in recs:
            continue
        tk = kind_of(plan[0]["action_key"])
        ak = kind_of(recs["2"]["forced_action_key"])
        table[(tk, ak)].append((r["unit"], r["cf"]["2"] - r["baseline_score"]))
    for (tk, ak), pairs in sorted(table.items(), key=lambda kv: -len(kv[1])):
        if len(pairs) < 30:
            continue
        res = unit_cluster(pairs)
        print("| %s | %s | %d | %d | %+.2f | [%+.2f, %+.2f] |"
              % (tk, ak, len(pairs), res[1], res[0], res[2], res[3]))

    print()
    print("## 4. 按 (首选是过, 替代是鸣) 二分再按 phase 分层\n")
    for label, want_pass in (("首选=过", True), ("首选=非过", False)):
        for phase in ("DRAW", "RESPONSE_CHI", "RESPONSE_PENG"):
            pairs = []
            for r, plan, recs in joined:
                if "2" not in recs or r["phase"] != phase:
                    continue
                tk = kind_of(plan[0]["action_key"])
                if (tk == "pass") != want_pass:
                    continue
                pairs.append((r["unit"], r["cf"]["2"] - r["baseline_score"]))
            if len(pairs) < 30:
                continue
            res = unit_cluster(pairs)
            print("- %s / %s：窗 %d，unit %d，Δ %+.2f [%+.2f, %+.2f]"
                  % (label, phase, len(pairs), res[1], res[0], res[2], res[3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
