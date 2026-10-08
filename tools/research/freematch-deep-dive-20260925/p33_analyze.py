#!/usr/bin/env python3
"""P33 步骤 2：异质性分析（分布、分层、子群搜索 + 多重比较控制）。

口径全部来自已冻结的预登记：
review/freematch-deep-dive-20260925/P33-PREREG-DEFERRAL-HETEROGENEITY.md
只读 .team-work/p33-deferral-heterogeneity/ 的抽取产物，输出回同目录。
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

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work/p33-deferral-heterogeneity")
SEED = 20260925
BOOT = 10000
PERM = 10000

# ---------------------------------------------------------------- 统计工具


def betacf(a: float, b: float, x: float) -> float:
    """连分式（Numerical Recipes）。"""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    """正则化不完全贝塔函数 I_x(a, b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * betacf(a, b, x) / a
    return 1.0 - front * betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: int) -> float:
    x = df / (df + t * t)
    p = 0.5 * betai(df / 2.0, 0.5, x)
    return 1.0 - p if t > 0 else p


def t_quantile(p: float, df: int) -> float:
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def boot_ci(values, b=BOOT, seed=SEED, alpha=0.05):
    """根级 percentile bootstrap。"""
    arr = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(b, len(arr)))
    means = arr[idx].mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def t_ci(values, alpha=0.05):
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    if n < 2:
        return None, None
    se = arr.std(ddof=1) / math.sqrt(n)
    tc = t_quantile(1 - alpha / 2, n - 1)
    return float(arr.mean() - tc * se), float(arr.mean() + tc * se)


def f2(v, nd=2):
    return "—" if v is None else f"{v:.{nd}f}"


def desc(values):
    arr = np.asarray(values, dtype=float)
    return {
        "n": int(arr.size),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "sd": float(arr.std(ddof=1)) if arr.size > 1 else None,
        "p05": float(np.quantile(arr, 0.05)),
        "p25": float(np.quantile(arr, 0.25)),
        "p75": float(np.quantile(arr, 0.75)),
        "p95": float(np.quantile(arr, 0.95)),
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def root_summary(root_means, label=""):
    vals = list(root_means.values()) if isinstance(root_means, dict) else list(root_means)
    out = desc(vals)
    out["positive_roots"] = sum(1 for v in vals if v > 0)
    out["negative_roots"] = sum(1 for v in vals if v < 0)
    out["zero_roots"] = sum(1 for v in vals if v == 0)
    lo, hi = boot_ci(vals)
    out["boot_ci95"] = [lo, hi]
    tl, th = t_ci(vals)
    out["t_ci95"] = [tl, th]
    out["t_stat"] = float(np.mean(vals) / (np.std(vals, ddof=1) / math.sqrt(len(vals)))) if len(vals) > 1 else None
    out["label"] = label
    return out


# ---------------------------------------------------------------- 载入


NUM_WALL = ("delta_table_defer_minus_hu", "delta_round_defer_minus_hu", "defer_settlement",
            "hu_settlement", "dealer_seat", "round_no", "defer_fan", "hu_fan")
NUM_STATE = ("dealer_seat_physical", "is_dealer", "remaining_tile_count", "round_no",
             "own_meld_count", "other_meld_sum", "hu_fan", "hu_score", "useful_kinds",
             "wealth_count_in_hand", "route_fan", "route_over_hu_ratio", "hu_settlement_self",
             "defer_has_target", "n_walls", "hu_arm_hu_rate", "hu_arm_mean_fan",
             "hu_arm_settlement_mean", "defer_arm_hu_rate", "defer_arm_mean_fan",
             "defer_arm_settlement_mean", "focal_seat_physical", "source_focal_seat")
NUM_POOL = ("focal_seat", "dealer_seat", "is_dealer", "remaining_tile_count", "round_no",
            "own_meld_count", "other_meld_sum", "hu_fan", "hu_score", "useful_kinds",
            "wealth_count_in_hand", "route_fan")


def _num(v):
    if v in (None, "", "None", "nan"):
        return None
    if v in ("True", "False"):
        return int(v == "True")
    return float(v)


def load():
    walls = list(csv.DictReader(open(_project_file(_PROJECT_ROOT, OUT / "paired_walls.csv"), encoding="utf-8")))
    states = list(csv.DictReader(open(_project_file(_PROJECT_ROOT, OUT / "states.csv"), encoding="utf-8")))
    pool = list(csv.DictReader(open(_project_file(_PROJECT_ROOT, OUT / "pool_rows.csv"), encoding="utf-8")))
    for w in walls:
        for k in NUM_WALL:
            w[k] = _num(w.get(k))
        w["wall_index"] = int(w["wall_index"])
    for s in states:
        for k in NUM_STATE:
            if k in s:
                s[k] = _num(s[k])
    for p in pool:
        for k in NUM_POOL:
            if k in p:
                p[k] = _num(p[k])
    return walls, states, pool


def root_means(walls, batch, key="delta_table_defer_minus_hu"):
    per = defaultdict(list)
    for w in walls:
        if w["batch"] != batch:
            continue
        per[w["root_id"]].append(w[key])
    return {r: float(np.mean(v)) for r, v in per.items()}


# ---------------------------------------------------------------- 特征取用


def feat(states, batch):
    return [s for s in states if s["batch"] == batch]


def rule_mask(rows, name):
    """规则掩码：rows 为 states 或 pool 行（两者共同字段名见预登记 §四）。"""
    if name == "A1_remaining_gt20":
        return [r["remaining_tile_count"] is not None and r["remaining_tile_count"] > 20 for r in rows]
    if name == "A2_other_meld_sum_le1":
        return [r["other_meld_sum"] is not None and r["other_meld_sum"] <= 1 for r in rows]
    if name == "A3_not_dealer":
        return [r["is_dealer"] == 0 for r in rows]
    if name == "A4_A1_and_A2":
        return [a and b for a, b in zip(rule_mask(rows, "A1_remaining_gt20"), rule_mask(rows, "A2_other_meld_sum_le1"))]
    if name == "A5_A1_and_A3":
        return [a and b for a, b in zip(rule_mask(rows, "A1_remaining_gt20"), rule_mask(rows, "A3_not_dealer"))]
    if name == "A6_A2_and_A3":
        return [a and b for a, b in zip(rule_mask(rows, "A2_other_meld_sum_le1"), rule_mask(rows, "A3_not_dealer"))]
    if name == "A7_useful_kinds_ge7":
        return [r["useful_kinds"] is not None and r["useful_kinds"] >= 7 for r in rows]
    if name == "A8_round_le2":
        return [r["round_no"] is not None and r["round_no"] <= 2 for r in rows]
    if name == "mix==H":
        return [r["mix"] == "H" for r in rows]
    if name == "mix==M":
        return [r["mix"] == "M" for r in rows]
    # Family B 通用表达式：'feat<=x' / 'feat>x' / '(f1<=x)&(f2<=y)'
    return _eval_expr(rows, name)


def _is_number(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


def _eval_expr(rows, expr):
    parts = [p.strip() for p in expr.split("&")]
    out = []
    for r in rows:
        ok = True
        for p in parts:
            p = p.strip("()")
            for op in ("<=", ">=", "<", ">", "=="):
                if op in p:
                    k, v = p.split(op)
                    k = k.strip().strip("()")
                    v = v.strip().strip("()")
                    val = r.get(k)
                    if op == "==" and not _is_number(v):
                        ok &= (str(val) == v)
                        break
                    v = float(v)
                    if val is None:
                        ok = False
                    elif op == "<=":
                        ok &= val <= v
                    elif op == ">=":
                        ok &= val >= v
                    elif op == "<":
                        ok &= val < v
                    elif op == ">":
                        ok &= val > v
                    else:
                        ok &= val == v
                    break
            else:
                raise ValueError(expr)
        out.append(ok)
    return out


# ---------------------------------------------------------------- 主流程


def main() -> int:
    walls, states, pool = load()
    report = {}
    lines = []

    def say(msg=""):
        print(msg)
        lines.append(msg)

    # ------- 0. 机械复核（抽取脚本已核对，这里再报一次冻结摘要）
    verify = json.loads((_project_file(_PROJECT_ROOT, OUT / "verify.json")).read_text(encoding="utf-8"))
    say("## 0. 机械复核")
    for b, v in verify["batches"].items():
        say(f"- {b}: 墙 {v['delta_identity_ok']}/{v['targets']*32} delta 恒等；force_ok {v['force_ok']}；"
            f"mechanical_ok {v['mechanical_ok']}；逐墙数组与 result.json 相等 fit {v['fit_arrays_match']}/16、"
            f"recheck {v['recheck_arrays_match']}/16；焦点物理座位唯一 {v['focal_seat_unique_targets']}/16，"
            f"庄位唯一 {v['dealer_seat_unique_targets']}/16")
    say(f"- 覆盖率池：{verify['pool_rows']}，池内 hu_fan 分布 {verify['pool_hu_fan']}")
    report["verify"] = verify

    # ------- 1. 总体分布（P24 主；P86-02 补充）
    say()
    say("## 1. 弃胡收益的总体分布（Δtable = 弃胡 − 立刻胡，分）")
    dist = {}
    for batch in ("P24", "P86-02"):
        w = [x for x in walls if x["batch"] == batch]
        per_wall = desc([x["delta_table_defer_minus_hu"] for x in w])
        rm = root_means(walls, batch)
        per_root = root_summary(rm, batch)
        # 前半墙（fit 1–16）/ 后半墙（recheck 17–32）
        first = root_summary({r: float(np.mean([x["delta_table_defer_minus_hu"] for x in w
                                                if x["root_id"] == r and x["wall_index"] <= 16]))
                              for r in rm})
        last = root_summary({r: float(np.mean([x["delta_table_defer_minus_hu"] for x in w
                                               if x["root_id"] == r and x["wall_index"] > 16]))
                             for r in rm})
        dist[batch] = {"per_wall": per_wall, "per_root": per_root, "fit_roots": first, "recheck_roots": last}
        say(f"### {batch}（{per_root['n']} 根 × 32 墙 = {per_wall['n']} 面墙配对）")
        say(f"- 逐墙 Δtable：均值 {per_wall['mean']:.3f}，中位数 {per_wall['median']:.1f}，"
            f"p05 {per_wall['p05']:.1f} / p25 {per_wall['p25']:.1f} / p75 {per_wall['p75']:.1f} / p95 {per_wall['p95']:.1f}，"
            f"min {per_wall['min']:.0f} max {per_wall['max']:.0f}（**同一根 32 面墙是重复测量，不是独立样本**）")
        say(f"- 逐根 Δ̄：均值 {per_root['mean']:.4f}（95% CI boot [{per_root['boot_ci95'][0]:.3f}, {per_root['boot_ci95'][1]:.3f}]，"
            f"t [{per_root['t_ci95'][0]:.3f}, {per_root['t_ci95'][1]:.3f}]），中位数 {per_root['median']:.3f}，"
            f"p25 {per_root['p25']:.2f} / p75 {per_root['p75']:.2f}，正 {per_root['positive_roots']} / 负 {per_root['negative_roots']}")
        say(f"- 前半墙（1–16）根均 {first['mean']:.4f}；后半墙（17–32）根均 {last['mean']:.4f}")
    report["distributions"] = dist

    # ------- 2. 与 P24 报告的对账
    say()
    say("## 2. 与 P24 报告数字的对账（复现性）")
    p24_recheck = dist["P24"]["recheck_roots"]["mean"]
    p24_all = dist["P24"]["per_root"]["mean"]
    defer_walls = [x for x in walls if x["batch"] == "P24"]
    hu_rate = sum(1 for x in defer_walls if x["defer_terminal"] == "focal_hu") / len(defer_walls)
    dfan = [x["defer_fan"] for x in defer_walls if x["defer_terminal"] == "focal_hu"]
    hu_rate_hu_arm = sum(1 for x in defer_walls if x["hu_terminal"] == "focal_hu") / len(defer_walls)
    say(f"- P24 全 32 墙根均 Δtable {p24_all:.6f}（报告 −10.416015625）；后半墙 {p24_recheck:.6f}（报告 −10.84375）")
    say(f"- P24 弃胡臂先胡率 {hu_rate:.6f}（报告 0.4765625，后半墙口径）；全 32 墙弃胡臂先胡率 {hu_rate:.4f}")
    say(f"- P24 立刻胡臂先胡率（全 32 墙）{hu_rate_hu_arm:.4f}；弃胡臂均番 {np.mean(dfan):.4f}（报告后半墙 1.3667）")
    report["reconciliation"] = {
        "p24_all_walls_root_mean": p24_all,
        "p24_recheck_root_mean": p24_recheck,
        "p24_defer_hu_rate_all_walls": hu_rate,
        "p24_defer_mean_fan_all_walls": float(np.mean(dfan)),
    }

    # ------- 3. 分层（S1–S6）
    say()
    say("## 3. 分层异质性（S1–S6；每条给根数、Δ̄ 均值、两种 95% CI）")
    strata = {}
    for batch in ("P24", "P86-02"):
        st = feat(states, batch)
        rm = root_means(walls, batch)
        rows = []
        for s in st:
            rows.append((s, rm[s["root_id"]]))

        def layer(name, keyfn, order=None):
            groups = defaultdict(list)
            for s, v in rows:
                g = keyfn(s)
                if g is None:
                    continue
                groups[g].append(v)
            out = {}
            for g, vals in sorted(groups.items(), key=lambda kv: str(kv[0])):
                if len(vals) < 1:
                    continue
                entry = root_summary(vals, f"{name}={g}")
                out[str(g)] = entry
                flag = "" if len(vals) >= 4 else "  ⚠根数<4，仅描述"
                say(f"  - [{batch}] {name} = {g}: 根数 {entry['n']}，Δ̄ {f2(entry['mean'], 3)}，"
                    f"boot95 [{f2(entry['boot_ci95'][0])}, {f2(entry['boot_ci95'][1])}]，"
                    f"t95 [{f2(entry['t_ci95'][0])}, {f2(entry['t_ci95'][1])}]，"
                    f"正/负 {entry['positive_roots']}/{entry['negative_roots']}{flag}")
            return out

        say(f"### {batch}")
        s1 = layer("S1_立刻胡番数", lambda s: f"{int(s['hu_fan'])}番" if s["hu_fan"] is not None else None)
        s2 = layer("S2_墙剩余", lambda s: "≤20" if (s["remaining_tile_count"] or 0) <= 20 else
                   ("21–50" if s["remaining_tile_count"] <= 50 else "≥51"))
        s3 = layer("S3_三家副露合计", lambda s: "0–1" if (s["other_meld_sum"] or 0) <= 1 else
                   ("2" if s["other_meld_sum"] == 2 else "≥3"))
        s4 = layer("S4_是否坐庄", lambda s: "坐庄" if s["is_dealer"] else "非坐庄")
        s5 = layer("S5_爆头路线fan÷立刻胡fan", lambda s: (
            "未定义(无靶)" if not s["route_fan"] else f"={int(s['route_over_hu_ratio'])}"))
        s6a = layer("S6a_own_meld", lambda s: str(int(s["own_meld_count"])))
        s6b = layer("S6b_听口宽度", lambda s: None if s["useful_kinds"] is None else
                    ("≤4" if s["useful_kinds"] <= 4 else ("5–8" if s["useful_kinds"] <= 8 else "≥9")))
        s6c = layer("S6c_round_no", lambda s: None if s["round_no"] is None else
                    ("≤2" if s["round_no"] <= 2 else "≥3"))
        s6d = layer("S6d_hu_score", lambda s: None if s["hu_score"] is None else
                    ("<24" if s["hu_score"] < 24 else "≥24"))
        s6e = layer("S6e_mix", lambda s: s["mix"])
        s6f = layer("S6f_焦点座", lambda s: str(int(s["focal_seat_physical"])) if s["focal_seat_physical"] is not None else None)
        strata[batch] = {"S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5,
                         "S6": {"own_meld": s6a, "kinds": s6b, "round": s6c, "hu_score": s6d, "mix": s6e, "seat": s6f}}
    report["strata"] = strata

    # ------- 4. 子群搜索（Family A + B）与多重比较
    say()
    say("## 4. 正收益子群搜索（Family A 机制先验 + Family B 穷举）")
    st24 = feat(states, "P24")
    pool24 = [p for p in pool if p["pool"] == "P24_pool"]
    pool_roots24 = {p["root_id"] for p in pool24}

    featsB = {
        "remaining_tile_count": [s["remaining_tile_count"] for s in st24],
        "other_meld_sum": [s["other_meld_sum"] for s in st24],
        "own_meld_count": [s["own_meld_count"] for s in st24],
        "round_no": [s["round_no"] for s in st24],
        "useful_kinds": [s["useful_kinds"] for s in st24],
        "hu_score": [s["hu_score"] for s in st24],
        "is_dealer": [s["is_dealer"] for s in st24],
    }
    rules = []
    for key, vals in featsB.items():
        uniq = sorted(set(v for v in vals if v is not None))
        for a, b in zip(uniq, uniq[1:]):
            cut = (a + b) / 2
            for direction, expr in (("le", f"{key}<={cut}"), ("gt", f"{key}>{cut}")):
                if expr.endswith(".0") or f"{cut:.6f}".rstrip("0").rstrip(".") == "":
                    pass
                rules.append({"name": expr, "family": "B", "feature": key, "direction": direction})
    # mix 是分类特征，两个方向
    rules.append({"name": "mix==H", "family": "B", "feature": "mix", "direction": "cat"})
    rules.append({"name": "mix==M", "family": "B", "feature": "mix", "direction": "cat"})

    def mask_states(rule, rows=st24):
        return rule_mask(rows, rule["name"])

    # Family B 规模约束 [5, 11]
    B_kept = []
    for rule in rules:
        m = mask_states(rule)
        if 5 <= sum(m) <= 11:
            B_kept.append(rule)
    # 两特征合取
    pairs = []
    for i, r1 in enumerate(B_kept):
        for r2 in B_kept[i + 1:]:
            if r1["feature"] == r2["feature"]:
                continue
            name = f"({r1['name']})&({r2['name']})"
            m = [a and b for a, b in zip(mask_states(r1), mask_states(r2))]
            if 5 <= sum(m) <= 11:
                pairs.append({"name": name, "family": "B2", "feature": f"{r1['feature']}+{r2['feature']}"})
    space = B_kept + pairs
    familyA = [{"name": n, "family": "A"} for n in
               ("A1_remaining_gt20", "A2_other_meld_sum_le1", "A3_not_dealer", "A4_A1_and_A2",
                "A5_A1_and_A3", "A6_A2_and_A3", "A7_useful_kinds_ge7", "A8_round_le2")]
    K = len(familyA) + len(space)
    say(f"- 搜索空间规模：Family A {len(familyA)} 条，Family B 单特征 {len(B_kept)} 条，"
        f"两特征合取 {len(pairs)} 条 ⇒ **K = {K}**（含规模约束 [5,11]）")
    report["search_space"] = {"familyA": len(familyA), "familyB_single": len(B_kept),
                              "familyB_pair": len(pairs), "K": K,
                              "familyB_single_names": [r["name"] for r in B_kept][:60],
                              "familyB_pair_names": [r["name"] for r in pairs]}

    rm24 = root_means(walls, "P24")
    vals24 = {s["root_id"]: rm24[s["root_id"]] for s in st24}

    def evaluate(rule, rows=st24, vals=vals24):
        m = mask_states(rule, rows)
        sub = [vals[r["root_id"]] for r, keep in zip(rows, m) if keep]
        entry = root_summary(sub, rule["name"])
        cov_pool = sum(1 for x in rule_mask(pool24, rule["name"]) if x) / len(pool24)
        entry.update({"rule": rule["name"], "family": rule["family"],
                      "root_coverage": entry["n"] / len(st24), "pool_coverage": cov_pool})
        return entry

    famA_eval = [evaluate(r) for r in familyA]
    famB_eval = [evaluate(r) for r in space]
    say()
    say("### 4.1 Family A（机制先验）")
    for e in sorted(famA_eval, key=lambda x: -x["mean"]):
        say(f"  - {e['rule']}: 根 {e['n']}/16（池覆盖 {e['pool_coverage']*100:.1f}%），Δ̄ {f2(e['mean'], 3)}，"
            f"boot95 [{f2(e['boot_ci95'][0])}, {f2(e['boot_ci95'][1])}]，"
            f"t95 [{f2(e['t_ci95'][0])}, {f2(e['t_ci95'][1])}]")
    say()
    say("### 4.2 Family B 前 12 名（按 t 值）")
    for e in sorted(famB_eval, key=lambda x: -(x["t_stat"] or -99))[:12]:
        say(f"  - {e['rule']}: 根 {e['n']}/16（池覆盖 {e['pool_coverage']*100:.1f}%），Δ̄ {f2(e['mean'], 3)}，"
            f"boot95 [{f2(e['boot_ci95'][0])}, {f2(e['boot_ci95'][1])}]，"
            f"t95 [{f2(e['t_ci95'][0])}, {f2(e['t_ci95'][1])}]")

    # 4.3 max-t 置换 + Bonferroni
    all_rules = familyA + space
    all_names = [r["name"] for r in all_rules]

    observed = []
    for r in all_rules:
        m = mask_states(r)
        sub = [vals24[s["root_id"]] for s, keep in zip(st24, m) if keep]
        if len(sub) < 2:
            observed.append((r["name"], None, None))
            continue
        t = float(np.mean(sub) / (np.std(sub, ddof=1) / math.sqrt(len(sub))))
        observed.append((r["name"], t, len(sub)))
    obs_max = max(t for _, t, _ in observed if t is not None)
    obs_best = max((x for x in observed if x[1] is not None), key=lambda x: x[1])

    rng = np.random.default_rng(SEED)
    delta_vec = np.array([vals24[s["root_id"]] for s in st24])
    base_masks = np.array([mask_states(r) for r in all_rules])  # K x 16
    perm_max = []
    for _ in range(PERM):
        perm = rng.permutation(len(delta_vec))
        shuffled = delta_vec[perm]
        best = -1e9
        for m in base_masks:
            sub = shuffled[m]
            if sub.size < 2:
                continue
            sd = sub.std(ddof=1)
            if sd == 0:
                continue
            t = sub.mean() / (sd / math.sqrt(sub.size))
            if t > best:
                best = t
        perm_max.append(best)
    perm_max = np.array(perm_max)
    adj_p = float((1 + int((perm_max >= obs_max).sum())) / (1 + PERM))
    adj_crit = float(np.quantile(perm_max, 0.95))
    bonf_crit = t_quantile(1 - 0.05 / (2 * K), len(st24) - 1)
    say()
    say("### 4.3 多重比较控制")
    say(f"- 观测最大 t = **{obs_max:.3f}**（规则 `{obs_best[0]}`，子群根数 {obs_best[2]}）")
    say(f"- max-t 置换（{PERM} 次，重排 16 个根的特征向量，seed {SEED}）：调整 p = **{adj_p:.4f}**，"
        f"零分布 95% 临界值 = {adj_crit:.3f}")
    say(f"- Bonferroni 对照：K = {K} ⇒ 单条规则临界 t = {bonf_crit:.3f}")
    report["multiple_comparison"] = {"K": K, "observed_max_t": obs_max, "obs_best_rule": obs_best[0],
                                     "obs_best_roots": obs_best[2], "perm_adjusted_p": adj_p,
                                     "perm_crit_95": adj_crit, "bonferroni_t_crit": bonf_crit}
    report["familyA_eval"] = famA_eval
    report["familyB_eval"] = sorted(famB_eval, key=lambda x: -(x["t_stat"] or -99))
    report["familyB_top"] = report["familyB_eval"][:40]

    # ------- 5. 判定（按预登记 §4.5 三态）
    say()
    say("## 5. 判定（预登记 §4.5 三态规则）")

    def qualifies(e):
        return (e["pool_coverage"] is not None and e["pool_coverage"] >= 0.30
                and e["n"] >= 5
                and e["boot_ci95"][0] > 0 and e["t_ci95"][0] > 0)

    cand = [e for e in famA_eval + famB_eval if qualifies(e)]
    verdict = "关闭"
    detail = ""
    if cand:
        best = max(cand, key=lambda e: e["mean"])
        # 该规则是否就是观测最大 t 的那条（用于置换校正归属）
        is_best_t = best["rule"] == obs_best[0]
        if is_best_t and adj_p < 0.05:
            verdict = "有候选"
            detail = best["rule"]
        else:
            verdict = "观察性候选（未过多重比较）"
            detail = best["rule"]
    say(f"- 满足「池覆盖≥30% + 根数≥5 + 两种 CI 下界>0」的规则数：**{len(cand)}**"
        + (f"，其中 Δ̄ 最高者 `{detail}`" if cand else ""))
    say(f"- **判定 = 「{verdict}」**")
    report["verdict"] = {"verdict": verdict, "rule": detail,
                         "n_qualifying": len(cand),
                         "qualifying": [{k: e[k] for k in ("rule", "n", "mean", "pool_coverage",
                                                           "root_coverage", "boot_ci95", "t_ci95")} for e in cand]}

    # ------- 6. 对手使用率对照（在 p33_opponent.py 里做，这里只留接口）
    (_project_file(_PROJECT_ROOT, OUT / "strata.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "analyze.log")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    say()
    say(f"写出 {_project_file(_PROJECT_ROOT, OUT/'strata.json')} / {_project_file(_PROJECT_ROOT, OUT/'analyze.log')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
