#!/usr/bin/env python3
"""C37 批次异质性 + 机制隐含分 vs 实测（**纯再分析，只读**）。

预登记（运行前落盘）：review/freematch-deep-dive-20260925/C37-PREREG-BATCH-HETEROGENEITY.md

只做三件事，全部由既有产物重算，**不跑新桌、不写 src/、不发网络请求**：

1. 四批（594 单元）合并 + 批次异质性（Q / I² / τ² / 留一批）+ 批次结构检验（n=4 只报方向）；
2. 机制链条标定（吃碰杠 → 爆头进入 → 爆头胡 → 番 → 分），给出**机制隐含分/桌**（口径 A/B/D）
   与四批实测并排；标定与分重建全部取自 C35 逐局机制行（25,344 局，双臂）；
3. 按根级 SD 与机制隐含效应量算「还要多少根」与成本。

用法：
  .venv/bin/python review/freematch-deep-dive-20260925/c37_heterogeneity.py            # 全部
  .venv/bin/python review/freematch-deep-dive-20260925/c37_heterogeneity.py merge      # 只做一/三
  .venv/bin/python review/freematch-deep-dive-20260925/c37_heterogeneity.py mechanism  # 只做二
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

import hashlib
import json
import math
import random
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
REVIEW = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925')
OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c37-heterogeneity")
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.hangma.settlement import settle_scores  # noqa: E402  唯一规则源（只读导入）

CANDIDATE = ("candidate@review/freematch-deep-dive-20260925/"
             "candidates/OPTY-R18-C27-CELL-R6.py")
BASELINE = "r18_v2"

#: 四批身份（冻结；seed/根区间不得在本文件里改）。
BATCHES = (
    dict(key="C29-screen", label="C29 筛查", rel="c27-gate", seed=2026102311,
         root_start=1, root_count=48, note="根1–48"),
    dict(key="C29-confirm", label="C29 确认", rel="c29-confirm", seed=2026102311,
         root_start=49, root_count=51, note="根49–99"),
    dict(key="C30-third", label="C30 第三批", rel="c30-third", seed=2026102312,
         root_start=1, root_count=99, note="新牌山"),
    dict(key="C35-level2", label="C35 第二级", rel=".team-work/c35-level2", seed=2026110101,
         root_start=1, root_count=99, note="新牌山"),
)

MIXES = ("H", "M")
SEATS = (0, 1, 2, 3)
TABLES_PER_STAGE = 2
ROUNDS_PER_TABLE = 8
TABLES_PER_ROOT_UNIT = 16          # 2 臂 × 4 座 × 2 桌
ACCUMULATED_UNITS = 594            # 四批已积累单元数（预登记 §3）
Z_ALPHA = 1.959963984540054
Z_POWER = 0.8416212335729143
BOOTSTRAP = 2000
MC = 20000
SEED = 20260926


# ---------------------------------------------------------------- 基础统计

def mean(values):
    return statistics.fmean(values)


def clustered(values):
    """既有口径（c29_verdict.py 逐字）：SE = pstdev/√n，CI = 均值 ± 1.96·SE。"""
    n = len(values)
    m = mean(values)
    se = statistics.pstdev(values) / math.sqrt(n) if n > 1 else float("nan")
    return dict(n=n, mean=m, sd=statistics.pstdev(values) if n > 1 else float("nan"),
                se=se, lo=m - Z_ALPHA * se, hi=m + Z_ALPHA * se)


def t_quantile(df, p):
    """t 分位近似（Cornish–Fisher；df≥100 时误差 <1e-3，足够功效迭代用）。"""
    z = _norm_ppf(p)
    g1 = (z ** 3 + z) / 4.0
    g2 = (5 * z ** 5 + 16 * z ** 3 + 3 * z) / 96.0
    g3 = (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / 384.0
    g4 = (79 * z ** 9 + 776 * z ** 7 + 1482 * z ** 5 - 1920 * z ** 3 - 945 * z) / 92160.0
    return z + g1 / df + g2 / df ** 2 + g3 / df ** 3 + g4 / df ** 4


def _norm_ppf(p):
    # Acklam 逆正态近似
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def sign_test(values):
    pos = sum(1 for v in values if v > 0)
    neg = sum(1 for v in values if v < 0)
    n = pos + neg
    if not n:
        return dict(pos=0, neg=0, p=1.0)
    z = (pos - n / 2) / math.sqrt(n * 0.25)
    p = math.erfc(abs(z) / math.sqrt(2))
    return dict(pos=pos, neg=neg, z=z, p=p)


def chi2_sf_df3(x):
    """df=3 的卡方上尾概率（闭式）。"""
    if x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x / 2.0)) + math.sqrt(2.0 * x / math.pi) * math.exp(-x / 2.0)


def pearson(xs, ys):
    n = len(xs)
    mx, my = mean(xs), mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def spearman(xs, ys):
    def rank(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        r = [0.0] * len(vs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    return pearson(rank(xs), rank(ys))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 一、合并与异质性

def load_batch(spec):
    path = (_project_file(_PROJECT_ROOT, REVIEW / spec["rel"] / "result.json")) if not spec["rel"].startswith(".") \
        else (_project_file(_PROJECT_ROOT, ROOT / spec["rel"] / "result.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    # C35 批的 result.json 没有 baseline_arm 字段；按该批 manifest 的 arms[0] 取（与
    # paired_study 的历史约定一致：delta_vs_baseline 的基准恒为 arms[0]）。
    baseline = payload.get("baseline_arm") or payload["manifest"]["arms"][0]
    assert baseline == BASELINE, baseline
    units = []
    for row in payload["root_clusters"]:
        raw = row["delta_vs_baseline_per_table"]
        # C35 批只有候选一条待测臂，该字段退化成标量；C29/C30 批是 {臂: Δ}。
        delta = raw[CANDIDATE] if isinstance(raw, dict) else float(raw)
        scores = row.get("score_per_table") or row.get("table_score_mean_by_arm")
        base = scores[BASELINE]
        cand = scores[CANDIDATE]
        units.append(dict(mix=row["mix"], root=row["root_index"], delta=delta,
                          base_score=base, cand_score=cand))
    units.sort(key=lambda u: (u["mix"], u["root"]))
    return dict(spec=spec, path=str(path.relative_to(ROOT)),
                sha256=sha256(path), units=units,
                # 本对比只涉及两臂：每单元 = 2 臂 × 4 座 × 2 桌 = 16 桌。
                complete_tables=len(units) * TABLES_PER_ROOT_UNIT,
                planned_tables=payload.get("complete_tables"))


def merge_analysis(batches):
    all_units = [(b["spec"]["key"], u) for b in batches for u in b["units"]]
    deltas = [u["delta"] for _, u in all_units]
    merged = clustered(deltas)
    merged["t_lo"] = merged["mean"] - t_quantile(merged["n"] - 1, 0.975) * merged["se"]
    merged["t_hi"] = merged["mean"] + t_quantile(merged["n"] - 1, 0.975) * merged["se"]
    merged["sign"] = sign_test(deltas)

    per_batch = []
    for b in batches:
        vals = [u["delta"] for u in b["units"]]
        s = clustered(vals)
        s["key"] = b["spec"]["key"]
        s["label"] = b["spec"]["label"]
        s["seed"] = b["spec"]["seed"]
        s["root_start"] = b["spec"]["root_start"]
        s["root_count"] = b["spec"]["root_count"]
        s["note"] = b["spec"]["note"]
        s["sign"] = sign_test(vals)
        s["pools"] = {}
        for mix in MIXES:
            cell = [u["delta"] for u in b["units"] if u["mix"] == mix]
            s["pools"][mix] = clustered(cell)
        s["base_level"] = mean([u["base_score"] for u in b["units"]])
        s["base_sd"] = statistics.pstdev([u["base_score"] for u in b["units"]])
        s["cand_level"] = mean([u["cand_score"] for u in b["units"]])
        s["tables"] = b["complete_tables"]
        per_batch.append(s)

    # Cochran's Q / I² / τ²（固定效应权重）
    w = [1.0 / s["se"] ** 2 for s in per_batch]
    theta = [s["mean"] for s in per_batch]
    sw = sum(w)
    theta_fixed = sum(wi * ti for wi, ti in zip(w, theta)) / sw
    Q = sum(wi * (ti - theta_fixed) ** 2 for wi, ti in zip(w, theta))
    df = len(per_batch) - 1
    I2 = max(0.0, (Q - df) / Q) if Q > 0 else 0.0
    tau2 = max(0.0, (Q - df) / (sw - sum(wi ** 2 for wi in w) / sw))
    wstar = [1.0 / (s["se"] ** 2 + tau2) for s in per_batch]
    swstar = sum(wstar)
    theta_re = sum(wi * ti for wi, ti in zip(wstar, theta)) / swstar
    re_se = math.sqrt(1.0 / swstar)
    heterogeneity = dict(
        Q=Q, df=df, p=chi2_sf_df3(Q) if df == 3 else None, I2=I2, tau2=tau2,
        tau=math.sqrt(tau2), theta_fixed=theta_fixed, theta_re=theta_re,
        re_lo=theta_re - Z_ALPHA * re_se, re_hi=theta_re + Z_ALPHA * re_se,
        weights=[dict(key=s["key"], w=wi, pct=100 * wi / sw) for s, wi in zip(per_batch, w)],
    )

    # 留一批
    loo = []
    for drop in per_batch:
        rest = [u["delta"] for b in batches if b["spec"]["key"] != drop["key"] for u in b["units"]]
        s = clustered(rest)
        s["dropped"] = drop["key"]
        s["dropped_mean"] = drop["mean"]
        w_rest = [1.0 / x["se"] ** 2 for x in per_batch if x["key"] != drop["key"]]
        t_rest = [x["mean"] for x in per_batch if x["key"] != drop["key"]]
        s["fixed_effect"] = sum(wi * ti for wi, ti in zip(w_rest, t_rest)) / sum(w_rest)
        loo.append(s)

    # 结构检验（n=4：只报方向）
    feats = dict(
        batch_effect=[s["mean"] for s in per_batch],
        base_level=[s["base_level"] for s in per_batch],
        pool_H=[s["pools"]["H"]["mean"] for s in per_batch],
        pool_M=[s["pools"]["M"]["mean"] for s in per_batch],
        pool_HM_gap=[s["pools"]["H"]["mean"] - s["pools"]["M"]["mean"] for s in per_batch],
        root_start=[s["root_start"] for s in per_batch],
        root_count=[s["root_count"] for s in per_batch],
        base_root_sd=[s["base_sd"] for s in per_batch],
        unit_sd=[s["sd"] for s in per_batch],
    )
    struct = {}
    for name, vals in feats.items():
        if name == "batch_effect":
            continue
        struct[name] = dict(values=vals, pearson=pearson(feats["batch_effect"], vals),
                            spearman=spearman(feats["batch_effect"], vals))

    return dict(merged=merged, per_batch=per_batch, heterogeneity=heterogeneity,
                leave_one_out=loo, structural=struct, features=feats,
                unit_sd_pooled=statistics.pstdev(deltas),
                unit_sd_within_pooled=math.sqrt(
                    sum((s["n"] - 1) * s["sd"] ** 2 for s in per_batch) /
                    sum(s["n"] - 1 for s in per_batch)))


# ---------------------------------------------------------------- 牌山结构（④）

SEED_RE = re.compile(r'"seed":\s*(\d+)')


def seed_structure(batches):
    out = {}
    for b in batches:
        stage_dir = (_project_file(_PROJECT_ROOT, REVIEW / b["spec"]["rel"] / "stages")) if not b["spec"]["rel"].startswith(".") \
            else (_project_file(_PROJECT_ROOT, ROOT / b["spec"]["rel"] / "stages"))
        files = sorted(stage_dir.glob("*.json"))
        per_wall = {}          # (mix, root, seat, table_no) -> {arm: seed}
        all_seeds = set()
        bad = 0
        checked = 0
        for path in files:
            m = re.match(r"([HM])-r(\d+)-s(\d+)-(.+)\.json$", path.name)
            if not m:
                bad += 1
                continue
            mix, root, seat, arm = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            text = path.read_text(encoding="utf-8")
            seeds = SEED_RE.findall(text)
            if checked < 12:   # 抽样与 JSON 解析对拍
                payload = json.loads(text)
                expect = [str(t["seed"]) for t in payload["stage"]["tables"]]
                if seeds != expect:
                    raise SystemExit("seed 正则与 JSON 不一致：{0}".format(path.name))
                checked += 1
            for no, sd in enumerate(seeds):
                per_wall.setdefault((mix, root, seat, no), {})[arm] = int(sd)
                all_seeds.add(int(sd))
        paired = ok = 0
        for key, arms in per_wall.items():
            if len(arms) < 2:
                continue
            paired += 1
            if len(set(arms.values())) == 1:
                ok += 1
        # 同批内 H/M 两池的牌山是否互相独立（根种子按对手派生 ⇒ 期望交集 0）
        hm_overlap = 0
        for key, arms in per_wall.items():
            if key[0] != "H":
                continue
            mirror = ("M", key[1], key[2], key[3])
            if mirror in per_wall:
                hm_overlap += len(set(arms.values()) & set(per_wall[mirror].values()))
        out[b["spec"]["key"]] = dict(
            files=len(files), unparsed=bad, walls=len(per_wall), seeds=len(all_seeds),
            paired_walls=paired, same_wall_arms=ok,
            same_wall_ratio=(ok / paired if paired else float("nan")),
            seed_min=min(all_seeds) if all_seeds else None,
            seed_max=max(all_seeds) if all_seeds else None,
            within_batch_HM_seed_overlap=hm_overlap,
            seed_set=all_seeds)
    cross = {}
    keys = list(out)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            inter = len(out[keys[i]]["seed_set"] & out[keys[j]]["seed_set"])
            cross["{0}|{1}".format(keys[i], keys[j])] = inter
    for k in keys:
        out[k].pop("seed_set")
    return dict(per_batch=out, cross_batch_overlap=cross)


# ---------------------------------------------------------------- 二、机制链条

ACC_KEYS = ("n", "claims", "claims2", "entry", "entry_claims", "entry_win",
            "static", "static_win", "win", "win_entry", "win_noentry",
            "fan_win_entry", "fan_win_noentry", "delta_win_entry", "delta_win_noentry",
            "delta_entry", "delta_noentry", "win_dealer", "fan_win_dealer",
            "delta_win_dealer", "win_idle", "fan_win_idle", "delta_win_idle",
            "delta_all", "delta_notwin", "draw")


def blank_acc():
    return {k: 0.0 for k in ACC_KEYS}


def focal_delta(row, phys_seat):
    """焦点座位在该局的赞失分（由唯一规则源 settle_scores 重建）。

    口径（C37 实测确认）：机制行的 `winner_seat`/`dealer_seat` 是**物理座位**，
    `focal_physical_by_table` 给出焦点策略在每张桌上坐的物理座位；流局取 0。
    """
    if row["is_draw"]:
        return 0.0
    return settle_scores(int(row["fan"] or 0), 1,
                         int(row["winner_seat"]), int(row["dealer_seat"]))[phys_seat]


def add_round(acc, row, delta):
    fan = int(row["fan"] or 0)
    entry = bool(row["baotou_entry"])
    static = bool(row["baotou_static_entry"])
    won = bool(row["won"])          # 焦点事实（已用物理座位核对）
    claims = float(row["claims_made"])
    acc["n"] += 1
    acc["delta_all"] += delta
    if not won:
        acc["delta_notwin"] += delta
    acc["claims"] += claims
    acc["claims2"] += claims * claims
    if entry:
        acc["entry"] += 1
        acc["entry_claims"] += claims
        acc["delta_entry"] += delta
    else:
        acc["delta_noentry"] += delta
    if static:
        acc["static"] += 1
    if won:
        acc["win"] += 1
        if entry:
            acc["entry_win"] += 1
            acc["win_entry"] += 1
            acc["fan_win_entry"] += fan
            acc["delta_win_entry"] += delta
        else:
            acc["win_noentry"] += 1
            acc["fan_win_noentry"] += fan
            acc["delta_win_noentry"] += delta
        if bool(row["is_dealer"]):
            acc["win_dealer"] += 1
            acc["fan_win_dealer"] += fan
            acc["delta_win_dealer"] += delta
        else:
            acc["win_idle"] += 1
            acc["fan_win_idle"] += fan
            acc["delta_win_idle"] += delta
    if static and won:
        acc["static_win"] += 1
    if row["is_draw"]:
        acc["draw"] += 1
    return delta


def sum_acc(accs):
    total = blank_acc()
    for a in accs:
        for k in ACC_KEYS:
            total[k] += a[k]
    return total


def safe(num, den):
    return (num / den) if den else float("nan")


def quantities(agg):
    """从（双臂合并后的）聚合量算出标定因子。"""
    return dict(
        rounds=agg["n"],
        claims_per_round=safe(agg["claims"], agg["n"]),
        entry_rate=safe(agg["entry"], agg["n"]),
        win_rate=safe(agg["win"], agg["n"]),
        p_win_given_entry=safe(agg["entry_win"], agg["entry"]),
        p_win_given_noentry=safe(agg["win_noentry"], agg["n"] - agg["entry"]),
        p_win_given_static=safe(agg["static_win"], agg["static"]),
        fan_win_entry=safe(agg["fan_win_entry"], agg["win_entry"]),
        fan_win_noentry=safe(agg["fan_win_noentry"], agg["win_noentry"]),
        fan_gap=safe(agg["fan_win_entry"], agg["win_entry"]) -
                safe(agg["fan_win_noentry"], agg["win_noentry"]),
        fan_per_win=safe(agg["fan_win_entry"] + agg["fan_win_noentry"], agg["win"]),
        delta_per_win_entry=safe(agg["delta_win_entry"], agg["win_entry"]),
        delta_per_win_noentry=safe(agg["delta_win_noentry"], agg["win_noentry"]),
        delta_per_round_entry=safe(agg["delta_entry"], agg["entry"]),
        delta_per_round_noentry=safe(agg["delta_noentry"], agg["n"] - agg["entry"]),
        value_per_fan_win=safe(agg["delta_win_entry"] + agg["delta_win_noentry"], agg["win"]) /
                          safe(agg["fan_win_entry"] + agg["fan_win_noentry"], agg["win"]),
        value_per_fan_dealer=safe(agg["delta_win_dealer"], agg["win_dealer"]) /
                             safe(agg["fan_win_dealer"], agg["win_dealer"]),
        value_per_fan_idle=safe(agg["delta_win_idle"], agg["win_idle"]) /
                           safe(agg["fan_win_idle"], agg["win_idle"]),
        entry_win_share=safe(agg["win_entry"], agg["win"]),
        # 账本分解（每局平均，单位分）：爆头胡 / 非爆头胡 / 未胡
        score_baotou_win=safe(agg["delta_win_entry"], agg["n"]),
        score_plain_win=safe(agg["delta_win_noentry"], agg["n"]),
        score_notwin=safe(agg["delta_notwin"], agg["n"]),
        score_all=safe(agg["delta_all"], agg["n"]),
        # 胡率分解
        baotou_win_rate=safe(agg["win_entry"], agg["n"]),
        plain_win_rate=safe(agg["win_noentry"], agg["n"]),
    )


def ols_slope(agg, n_clusters=None):
    """逐局 OLS：P(entry) ~ claims_made（用聚合量算点估计）。"""
    n, sc, sc2, se, sec = agg["n"], agg["claims"], agg["claims2"], agg["entry"], agg["entry_claims"]
    den = n * sc2 - sc * sc
    if not den:
        return float("nan")
    return (n * sec - sc * se) / den


def mechanism(stage_dir):
    files = sorted(stage_dir.glob("*.json"))
    clusters = {}          # (mix, root) -> {"cand"/"base": acc}（同单元四座位累加）
    validate = dict(stages=0, rounds=0, table_checks=0, table_mismatch=0, rounds_mismatch=0,
                    won_mismatch=0, dealer_mismatch=0, draws=0, examples=[])
    per_arm_raw = {}
    t0 = time.time()
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        arm = "cand" if payload["arm"] == CANDIDATE else "base"
        mix, root, seat = payload["mix"], payload["root_index"], payload["focal_seat"]
        phys_by_table = payload["mechanics"]["focal_physical_by_table"]
        acc = blank_acc()
        per_table_delta = {}
        rows = payload["mechanics"]["rounds"]
        for row in rows:
            table_no = int(row["table"])
            phys = int(phys_by_table[table_no - 1])
            delta = focal_delta(row, phys)
            add_round(acc, row, delta)
            per_table_delta[table_no] = per_table_delta.get(table_no, 0.0) + delta
            winner = row["winner_seat"]          # 流局时为 None
            if bool(row["won"]) != (winner is not None and int(winner) == phys
                                    and not row["is_draw"]):
                validate["won_mismatch"] += 1
            if bool(row["is_dealer"]) != (int(row["dealer_seat"]) == phys):
                validate["dealer_mismatch"] += 1
            if row["is_draw"]:
                validate["draws"] += 1
        for table_no, table in enumerate(payload["stage"]["tables"], start=1):
            phys = int(phys_by_table[table_no - 1])
            recorded = table["scores_by_seat"][phys]
            validate["table_checks"] += 1
            if abs(recorded - per_table_delta.get(table_no, 0.0)) > 1e-6:
                validate["table_mismatch"] += 1
                if len(validate["examples"]) < 3:
                    validate["examples"].append(dict(
                        file=path.name, table=table_no, phys=phys,
                        rebuilt=per_table_delta.get(table_no, 0.0), recorded=recorded))
        if len(rows) != TABLES_PER_STAGE * ROUNDS_PER_TABLE:
            validate["rounds_mismatch"] += 1
        validate["stages"] += 1
        validate["rounds"] += len(rows)
        bucket = clusters.setdefault((mix, root), {})
        if arm in bucket:
            for k in ACC_KEYS:
                bucket[arm][k] += acc[k]
        else:
            bucket[arm] = dict(acc)   # 拷贝：bucket 后续会累加，不得污染逐阶段聚合
        per_arm_raw.setdefault(arm, []).append(acc)
    validate["seconds"] = round(time.time() - t0, 1)
    validate["clusters"] = len(clusters)

    # 双臂池化 + 分臂
    arm_sum = {arm: sum_acc(accs) for arm, accs in per_arm_raw.items()}
    cal = {arm: quantities(agg) for arm, agg in arm_sum.items()}
    cal["pooled"] = quantities(sum_acc([arm_sum["cand"], arm_sum["base"]]))

    # 差量（C35 冻结读数，交叉核对）
    obs = dict(
        d_claims=cal["cand"]["claims_per_round"] - cal["base"]["claims_per_round"],
        d_entry=cal["cand"]["entry_rate"] - cal["base"]["entry_rate"],
        d_win=cal["cand"]["win_rate"] - cal["base"]["win_rate"],
        d_fan_per_win=cal["cand"]["fan_per_win"] - cal["base"]["fan_per_win"],
    )
    obs["beta_per_meld"] = obs["d_entry"] / obs["d_claims"]
    obs["beta_ols"] = ols_slope(sum_acc([arm_sum["cand"], arm_sum["base"]]))
    # 逐局账本分解：Δ分/桌 必须能由「爆头胡 / 非爆头胡 / 未胡」三段重建（端到端对拍）
    for name in ("score_baotou_win", "score_plain_win", "score_notwin", "score_all",
                 "baotou_win_rate", "plain_win_rate"):
        obs["d_" + name] = cal["cand"][name] - cal["base"][name]
    obs["d_score_per_table_from_rounds"] = ROUNDS_PER_TABLE * obs["d_score_all"]
    obs["d_baotou_win_pp"] = 100 * obs["d_baotou_win_rate"]
    obs["d_plain_win_pp"] = 100 * obs["d_plain_win_rate"]
    obs["d_win_implied_from_entry"] = obs["d_entry"] * cal["pooled"]["p_win_given_entry"]
    obs["implied_baotou_win_pp"] = 100 * obs["d_win_implied_from_entry"]

    # 根单元级聚类 bootstrap（保留配对：同一 (mix,root) 两臂一起重抽）
    rng = random.Random(SEED)
    keys = sorted(clusters)
    draws = dict(p_win_given_entry=[], fan_gap=[], value_per_fan=[], delta_per_win_entry=[],
                 entry_round_gap=[], d_entry=[], beta_ols=[], d_claims=[])
    for _ in range(BOOTSTRAP):
        picked = [clusters[keys[rng.randrange(len(keys))]] for _ in range(len(keys))]
        agg = {}
        for arm in ("cand", "base"):
            agg[arm] = sum_acc([c.get(arm, blank_acc()) for c in picked])
        qc, qb = quantities(agg["cand"]), quantities(agg["base"])
        qp = quantities(sum_acc([agg["cand"], agg["base"]]))
        draws["p_win_given_entry"].append(qp["p_win_given_entry"])
        draws["fan_gap"].append(qp["fan_gap"])
        draws["value_per_fan"].append(qp["value_per_fan_win"])
        draws["delta_per_win_entry"].append(qp["delta_per_win_entry"])
        draws["entry_round_gap"].append(qp["delta_per_round_entry"] - qp["delta_per_round_noentry"])
        draws["d_entry"].append(qc["entry_rate"] - qb["entry_rate"])
        draws["d_claims"].append(qc["claims_per_round"] - qb["claims_per_round"])
        draws["beta_ols"].append(ols_slope(sum_acc([agg["cand"], agg["base"]])))
    boot = {k: dict(mean=mean(v), lo=statistics.quantiles(v, n=40)[0],
                    hi=statistics.quantiles(v, n=40)[-1],
                    sd=statistics.pstdev(v)) for k, v in draws.items()}

    # 分量守恒：单元聚合必须等于逐阶段聚合（防止座位/单元丢失）
    assert abs(sum_acc([c.get("cand", blank_acc()) for c in clusters.values()])["n"]
               - arm_sum["cand"]["n"]) < 1e-9
    assert abs(sum_acc([c.get("base", blank_acc()) for c in clusters.values()])["n"]
               - arm_sum["base"]["n"]) < 1e-9
    return dict(calibration=cal, observed=obs, bootstrap=boot, boot_raw=draws,
                validate=validate,
                per_arm_rounds={k: len(v) for k, v in per_arm_raw.items()})


REAL_MATCH = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')


def real_match_crosscheck():
    """实盘语料交叉核对（只读）：结算规则与「进入→胡」「爆头番差」两个转化因子。

    口径：`review/baotou-anatomy-20260925/rounds.jsonl` 的单局公开记录（官方实盘）。
    逐局用 `settle_scores(fan, 1, winner_seat, dealer_seat)` 对拍记录里的 `scores` 向量；
    座位层统计 `entered_baotou → won` 与「爆头胡 vs 非爆头胡」的番差。
    """
    out = dict(rounds=0, lines=0, score_mismatch=0, draws=0, entry_rounds=0, entry_wins=0,
               baotou_win_fans=[], plain_win_fans=[], by_seat_windows=0)
    if not REAL_MATCH.exists():
        return dict(available=False)
    with REAL_MATCH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out["lines"] += 1
            rounds = rec.get("rounds") if isinstance(rec, dict) and "rounds" in rec else [rec]
            for row in rounds:
                if not isinstance(row, dict) or "scores" not in row:
                    continue
                out["rounds"] += 1
                fan = int(row.get("fan") or 0)
                scores = row["scores"]
                if row.get("is_draw"):
                    out["draws"] += 1
                else:
                    expect = settle_scores(fan, 1, int(row["winner_seat"]), int(row["dealer"]))
                    if list(expect) != list(scores):
                        out["score_mismatch"] += 1
                for seat in row.get("seats", ()):
                    out["by_seat_windows"] += 1
                    if seat.get("entered_baotou"):
                        out["entry_rounds"] += 1
                        if seat.get("won"):
                            out["entry_wins"] += 1
                    if seat.get("won"):
                        (out["baotou_win_fans"] if seat.get("final_baotou")
                         else out["plain_win_fans"]).append(int(row.get("fan") or 0))
    out["p_win_given_entry"] = safe(out["entry_wins"], out["entry_rounds"])
    out["fan_win_entry"] = (mean(out["baotou_win_fans"]) if out["baotou_win_fans"] else float("nan"))
    out["fan_win_noentry"] = (mean(out["plain_win_fans"]) if out["plain_win_fans"] else float("nan"))
    out["fan_gap"] = out["fan_win_entry"] - out["fan_win_noentry"]
    out["available"] = True
    return out


def implied_scores(mech, d_entry_mu, d_entry_se, d_claims_mu, d_claims_se):
    """机制隐含分/桌：口径 A（番差）/ B（毛额）/ D（进入局均值差）。"""
    rng = random.Random(SEED + 1)
    draws = {k: [] for k in ("A", "B", "D", "beta")}
    series = mech["boot_raw"]
    for _ in range(MC):
        de = rng.gauss(d_entry_mu, d_entry_se)
        dc = rng.gauss(d_claims_mu, d_claims_se)
        p = rng.choice(series["p_win_given_entry"])
        gap = rng.choice(series["fan_gap"])
        val = rng.choice(series["value_per_fan"])
        gross = rng.choice(series["delta_per_win_entry"])
        eg = rng.choice(series["entry_round_gap"])
        draws["A"].append(de * p * gap * val * ROUNDS_PER_TABLE)
        draws["B"].append(de * p * gross * ROUNDS_PER_TABLE)
        draws["D"].append(de * eg * ROUNDS_PER_TABLE)
        draws["beta"].append(de / dc if dc else float("nan"))

    def stat(vals):
        q = statistics.quantiles(vals, n=40)
        return dict(mean=mean(vals), lo=q[0], hi=q[-1],
                    sd=statistics.pstdev(vals),
                    p_gt0=sum(1 for v in vals if v > 0) / len(vals))
    return {k: stat(v) for k, v in draws.items()}


# ---------------------------------------------------------------- 三、功效与成本

def required_roots(sigma, delta):
    """配对设计（单位 = 逐根差）：R = (z+z')²σ²/δ²，再做 t 迭代。"""
    z_sum = Z_ALPHA + Z_POWER
    r = z_sum ** 2 * sigma ** 2 / delta ** 2
    for _ in range(40):
        df = max(1.0, r - 1)
        t_sum = t_quantile(df, 0.975) + t_quantile(df, 0.80)
        new = t_sum ** 2 * sigma ** 2 / delta ** 2
        if abs(new - r) < 1e-6:
            r = new
            break
        r = new
    return r


def power_table(sigma_values, deltas, accumulated=ACCUMULATED_UNITS):
    rows = []
    for sname, sigma in sigma_values.items():
        for dname, delta in deltas.items():
            r = required_roots(sigma, delta)
            tables = r * TABLES_PER_ROOT_UNIT
            rows.append(dict(
                sigma=round(sigma, 3), sigma_src=sname, delta=round(delta, 3),
                delta_src=dname, roots=int(math.ceil(r)), roots_z=int(math.ceil(
                    (Z_ALPHA + Z_POWER) ** 2 * sigma ** 2 / delta ** 2)),
                roots_two_arm=int(math.ceil(2 * r)), new_roots=max(0, int(math.ceil(r)) - accumulated),
                tables=int(math.ceil(tables)),
                minutes_local_19=int(math.ceil(tables / 19.0)),
                hours_local_c35=round(tables / 214.0 / 60.0, 1),
                rooms=int(math.ceil(tables / 10.0)),
                hours_platform=round(math.ceil(tables / 10.0) * 13.94 / 60.0, 1),
                # 增量成本（只算「还需新增」的那些单元）
                new_tables=max(0, int(math.ceil(r)) - accumulated) * TABLES_PER_ROOT_UNIT,
                new_minutes_local_19=int(math.ceil(
                    max(0, int(math.ceil(r)) - accumulated) * TABLES_PER_ROOT_UNIT / 19.0)),
                new_hours_platform=round(
                    max(0, int(math.ceil(r)) - accumulated) * TABLES_PER_ROOT_UNIT / 10.0
                    * 13.94 / 60.0, 1)))
    return rows


# ---------------------------------------------------------------- main

def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    which = argv[0] if argv else "all"
    manifest = dict(
        experiment="C37-BATCH-HETEROGENEITY",
        prereg="review/freematch-deep-dive-20260925/C37-PREREG-BATCH-HETEROGENEITY.md",
        started=time.strftime("%Y-%m-%d %H:%M:%S"),
        candidate=CANDIDATE, baseline=BASELINE,
        inputs={}, mode="pure re-analysis (read-only)",
    )

    batches = [load_batch(spec) for spec in BATCHES]
    for b in batches:
        manifest["inputs"][b["path"]] = b["sha256"]
    manifest["inputs"]["c35 stages"] = "1,584 files / {0}".format(
        sum(1 for _ in (_project_file(_PROJECT_ROOT, ROOT / ".team-work/c35-level2/stages")).glob("*.json")))

    summary = {}

    if which in ("all", "merge"):
        merged = merge_analysis(batches)
        seeds = seed_structure(batches)
        (_project_file(_PROJECT_ROOT, OUT / "batches.json")).write_text(json.dumps(
            dict(batches=[dict(key=b["spec"]["key"], label=b["spec"]["label"],
                               seed=b["spec"]["seed"], path=b["path"], sha256=b["sha256"],
                               tables=b["complete_tables"], units=len(b["units"]))
                          for b in batches],
                 merged=merged["merged"]), ensure_ascii=False, indent=1), encoding="utf-8")
        (_project_file(_PROJECT_ROOT, OUT / "heterogeneity.json")).write_text(json.dumps(
            dict(merged=merged["merged"], per_batch=merged["per_batch"],
                 heterogeneity=merged["heterogeneity"], leave_one_out=merged["leave_one_out"],
                 structural=merged["structural"], features=merged["features"],
                 unit_sd_pooled=merged["unit_sd_pooled"],
                 unit_sd_within=merged["unit_sd_within_pooled"], seeds=seeds),
            ensure_ascii=False, indent=1), encoding="utf-8")
        summary["merge"] = merged
        summary["seeds"] = seeds
        print("== 一、合并与异质性 ==")
        for s in merged["per_batch"]:
            print("  {0:<12} seed {1} 根{2} n={3:3d} Δ={4:+.3f} [{5:+.3f},{6:+.3f}] "
                  "H{7:+.3f} M{8:+.3f} 基线{9:.3f} 正/负{10}/{11} 桌{12}".format(
                      s["label"], s["seed"], s["root_start"], s["n"], s["mean"], s["lo"], s["hi"],
                      s["pools"]["H"]["mean"], s["pools"]["M"]["mean"], s["base_level"],
                      s["sign"]["pos"], s["sign"]["neg"], s["tables"]))
        m = merged["merged"]
        print("  合并 n={0} Δ={1:+.3f} [{2:+.3f},{3:+.3f}] (t): [{4:+.3f},{5:+.3f}] SD={6:.3f} "
              "正/负 {7}/{8} p={9:.3f}".format(
                  m["n"], m["mean"], m["lo"], m["hi"], m["t_lo"], m["t_hi"], m["sd"],
                  m["sign"]["pos"], m["sign"]["neg"], m["sign"]["p"]))
        h = merged["heterogeneity"]
        print("  Q={0:.3f} df={1} p={2:.3f} I²={3:.3f} τ²={4:.3f} τ={5:.3f} "
              "θ_FE={6:+.3f} θ_RE={7:+.3f} [{8:+.3f},{9:+.3f}]".format(
                  h["Q"], h["df"], h["p"], h["I2"], h["tau2"], h["tau"], h["theta_fixed"],
                  h["theta_re"], h["re_lo"], h["re_hi"]))
        for r in merged["leave_one_out"]:
            print("  留一批 去{0:<12} n={1:3d} Δ={2:+.3f} [{3:+.3f},{4:+.3f}] FE={5:+.3f}".format(
                r["dropped"], r["n"], r["mean"], r["lo"], r["hi"], r["fixed_effect"]))
        print("  结构检验（n=4，只报方向）：")
        for name, s in merged["structural"].items():
            print("    {0:<14} r={1:+.3f} ρ={2:+.3f} values={3}".format(
                name, s["pearson"], s["spearman"],
                [round(v, 3) for v in s["values"]]))
        print("  牌山：两臂同墙比例 " + ", ".join(
            "{0}={1:.3f}".format(k, v["same_wall_ratio"]) for k, v in seeds["per_batch"].items()))
        print("  跨批 seed 交集：" + json.dumps(seeds["cross_batch_overlap"]))
        print("  单元 SD：合并 {0:.3f}，批内池化 {1:.3f}".format(
            merged["unit_sd_pooled"], merged["unit_sd_within_pooled"]))

    if which in ("all", "mechanism"):
        mech = mechanism(_project_file(_PROJECT_ROOT, ROOT / ".team-work/c35-level2/stages"))
        summary["mech"] = mech
        print("== 二、机制链条（C35 语料）==")
        v = mech["validate"]
        print("  校验：阶段 {0} 局 {1} 桌级对拍 {2} 失配 {3}；回合数异常 {4}；"
              "won 失配 {5} 庄失配 {6} 流局 {7}；用时 {8}s 单元 {9}".format(
                  v["stages"], v["rounds"], v["table_checks"], v["table_mismatch"],
                  v["rounds_mismatch"], v["won_mismatch"], v["dealer_mismatch"],
                  v["draws"], v["seconds"], v["clusters"]))
        for arm, q in mech["calibration"].items():
            print("  [{0}] 局={1} 吃碰/局={2:.4f} 进入率={3:.5f} 胡率={4:.5f} "
                  "P(胡|进入)={5:.4f} 番(进入胡)={6:.3f} 番(非进入胡)={7:.3f} "
                  "番差={8:.3f} 分/番={9:.3f}".format(
                      arm, int(q["rounds"]), q["claims_per_round"], q["entry_rate"],
                      q["win_rate"], q["p_win_given_entry"], q["fan_win_entry"],
                      q["fan_win_noentry"], q["fan_gap"], q["value_per_fan_win"]))
        o = mech["observed"]
        print("  Δ吃碰/局={0:+.5f} Δ进入={1:+.5f}pp β={2:.4f}/次（OLS {3:.4f}）Δ胡率={4:+.5f}pp".format(
            o["d_claims"], o["d_entry"] * 100, o["beta_per_meld"], o["beta_ols"], o["d_win"] * 100))
        print("  账本分解（Δ分/桌，逐局重建 ×8）：爆头胡 {0:+.3f} 非爆头胡 {1:+.3f} 未胡 {2:+.3f} "
              "合计 {3:+.3f}（C35 冻结实测 Δ = −0.153）".format(
                  8 * o["d_score_baotou_win"], 8 * o["d_score_plain_win"],
                  8 * o["d_score_notwin"], o["d_score_per_table_from_rounds"]))
        print("  胡率分解：Δ爆头胡 {0:+.3f}pp Δ非爆头胡 {1:+.3f}pp（合计 {2:+.3f}pp）；"
              "机制隐含的新增爆头胡 {3:+.3f}pp".format(
                  o["d_baotou_win_pp"], o["d_plain_win_pp"], 100 * o["d_win"],
                  o["implied_baotou_win_pp"]))
        b = mech["bootstrap"]
        for k in ("p_win_given_entry", "fan_gap", "value_per_fan", "delta_per_win_entry",
                  "entry_round_gap", "d_entry", "d_claims", "beta_ols"):
            print("  bootstrap {0:<22} {1:+.4f} [{2:+.4f},{3:+.4f}] sd={4:.4f}".format(
                k, b[k]["mean"], b[k]["lo"], b[k]["hi"], b[k]["sd"]))
        cross = real_match_crosscheck()
        mech["real_match_crosscheck"] = cross
        print("  实盘交叉核对：局 {0}（座位窗 {1}）结算失配 {2}；进入局 {3} 进入后胡 {4} "
              "P(胡|进入)={5:.4f}；爆头胡番 {6:.3f} vs 普通胡番 {7:.3f} 番差 {8:.3f}".format(
                  cross.get("rounds"), cross.get("by_seat_windows"), cross.get("score_mismatch"),
                  cross.get("entry_rounds"), cross.get("entry_wins"),
                  cross.get("p_win_given_entry", float("nan")),
                  cross.get("fan_win_entry", float("nan")), cross.get("fan_win_noentry", float("nan")),
                  cross.get("fan_gap", float("nan"))))
        implied = implied_scores(mech, d_entry_mu=0.0076547, d_entry_se=0.0019062,
                                 d_claims_mu=0.1348, d_claims_se=0.005765)
        mech["implied"] = implied
        summary["implied"] = implied
        print("  机制隐含分/桌：")
        for k in ("A", "B", "D"):
            print("    口径 {0}: {1:+.3f} [{2:+.3f},{3:+.3f}] P(>0)={4:.3f}".format(
                k, implied[k]["mean"], implied[k]["lo"], implied[k]["hi"], implied[k]["p_gt0"]))
        (_project_file(_PROJECT_ROOT, OUT / "mechanism.json")).write_text(json.dumps(mech, ensure_ascii=False, indent=1,
                                                       default=str), encoding="utf-8")

    if which in ("all", "merge", "mechanism"):
        if "merge" in summary and "implied" in summary:
            merged = summary["merge"]
            implied = summary["implied"]
            sigmas = dict(pooled_594=merged["unit_sd_pooled"],
                          c35_only=[s for s in merged["per_batch"] if s["key"] == "C35-level2"][0]["sd"])
            deltas = dict(implied_A=implied["A"]["mean"], merged_point=merged["merged"]["mean"],
                          merged_lo=merged["merged"]["lo"])
            for d in (0.5, 0.75, 1.0, 1.5, 2.0):
                deltas["grid_{0}".format(d)] = d
            power = power_table(sigmas, deltas)
            (_project_file(_PROJECT_ROOT, OUT / "power.json")).write_text(json.dumps(power, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
            print("== 三、功效与成本（单位 = mix×根，16 桌/单元，已积累 594）==")
            print("  σ 合并 {0:.3f} / C35 {1:.3f}".format(sigmas["pooled_594"], sigmas["c35_only"]))
            for r in power:
                if r["sigma_src"] != "pooled_594":
                    continue
                print("  δ={0:+.3f} ({1}): 需 {2} 根（z {3}）；新增 {4} 根 = {5} 桌 "
                      "⇒ 本地 19桌/分 {6} 分、官方房 {7} 房 ≈ {8} h".format(
                          r["delta"], r["delta_src"], r["roots"], r["roots_z"], r["new_roots"],
                          r["new_tables"], r["new_minutes_local_19"], r["new_tables"] / 10.0,
                          r["new_hours_platform"]))

    if "merge" in summary and "implied" in summary:
        merged, implied, mech = summary["merge"], summary["implied"], summary["mech"]
        rows = [(s["label"] + " 实测", s["mean"], s["lo"], s["hi"]) for s in merged["per_batch"]]
        rows.append(("四批合并 实测", merged["merged"]["mean"], merged["merged"]["lo"],
                     merged["merged"]["hi"]))
        rows.append(("机制隐含 A 番差", implied["A"]["mean"], implied["A"]["lo"], implied["A"]["hi"]))
        rows.append(("机制隐含 B 毛额", implied["B"]["mean"], implied["B"]["lo"], implied["B"]["hi"]))
        rows.append(("机制隐含 D 进入局差", implied["D"]["mean"], implied["D"]["lo"],
                     implied["D"]["hi"]))
        lo_axis = min(r[2] for r in rows) - 0.4
        hi_axis = max(r[3] for r in rows) + 0.4
        width = 64

        def scale(v):
            return int(round((v - lo_axis) / (hi_axis - lo_axis) * width))

        out = ["机制隐含 vs 四批实测（分/桌；[ ] = 95% 区间，█ = 点估计）",
               "轴：{0:+.2f} → {1:+.2f}".format(lo_axis, hi_axis), ""]
        zero = scale(0.0)
        for name, m, lo, hi in rows:
            a, b, z = scale(lo), scale(hi), scale(m)
            bar = [" "] * (width + 1)
            for i in range(min(a, b), max(a, b) + 1):
                bar[i] = "-"
            bar[z] = "█"
            render = "".join(bar)
            render = render[:zero] + "|" + render[zero + 1:]
            out.append("{0:<16} {1:+.3f} [{2:+.3f},{3:+.3f}] {4}".format(name, m, lo, hi, render))
        out.append("")
        out.append("零线：" + " " * zero + "^")
        out.append("账本分解（C35 逐局重建 ×8，Δ分/桌）：爆头胡 {0:+.3f} / 非爆头胡 {1:+.3f} / "
                   "未胡 {2:+.3f} = {3:+.3f}（C35 冻结实测 −0.153）".format(
                       8 * mech["observed"]["d_score_baotou_win"],
                       8 * mech["observed"]["d_score_plain_win"],
                       8 * mech["observed"]["d_score_notwin"],
                       mech["observed"]["d_score_per_table_from_rounds"]))
        (_project_file(_PROJECT_ROOT, OUT / "mechanism_vs_measured.txt")).write_text("\n".join(out) + "\n", encoding="utf-8")
        print("== 机制隐含 vs 实测 ==")
        for line in out:
            print("  " + line)

    manifest["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (_project_file(_PROJECT_ROOT, OUT / "manifest.json")).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
