#!/usr/bin/env python3
"""统计助手：按聚类（房）的均值/比例置信区间。

纪律：本会话已多次出现「看起来有差异、实际不可分辨」，因此所有比例与均值
一律给出**按房聚类**的置信区间；聚类单位是「房」（room_id），不是单局，
因为同一房内的单局共享牌山、对手池与同一批会话配置。

两种口径都算并对照：
- CR0 聚类稳健标准误（G/(G-1) 小样本修正）+ t(G-1) 分位；
- 房级 bootstrap 百分位区间（重抽样单位=房）。
两者差异明显时说明聚类数不足以支撑正态近似，报告中必须写明。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/baotou-anatomy-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import math
import random


def _betacf(a: float, b: float, x: float) -> float:
    """正则化不完全贝塔函数的连分式（Lentz 法）。"""

    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
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
        if abs(delta - 1.0) < 3e-14:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """正则化不完全贝塔函数 I_x(a,b)。"""

    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_cdf(value: float, df: int) -> float:
    """学生 t 分布 CDF。"""

    if value == 0.0:
        return 0.5
    x = df / (df + value * value)
    tail = 0.5 * _betai(df / 2.0, 0.5, x)
    return 1.0 - tail if value > 0 else tail


def t_ppf(p: float, df: int) -> float:
    """学生 t 分布分位数（二分法，精度 1e-10）。"""

    low, high = -1e4, 1e4
    for _ in range(200):
        mid = (low + high) / 2.0
        if t_cdf(mid, df) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def cluster_ci(values, clusters, alpha: float = 0.05):
    """均值 + CR0 聚类稳健置信区间。

    values: 每个观测单位的取值（如每局的配对差 0/1/-1）；
    clusters: 与 values 等长的聚类标签（房）。
    返回 dict：n、clusters、mean、se、lo、hi、tcrit。
    """

    n = len(values)
    if n == 0:
        return {"n": 0, "clusters": 0, "mean": None, "se": None, "lo": None, "hi": None}
    total = sum(values)
    mean = total / n
    groups: dict = {}
    for value, key in zip(values, clusters):
        item = groups.setdefault(key, [0.0, 0])
        item[0] += value
        item[1] += 1
    g = len(groups)
    if g < 2:
        return {"n": n, "clusters": g, "mean": mean, "se": None, "lo": None, "hi": None}
    acc = 0.0
    for key, (sub_total, sub_n) in groups.items():
        acc += (sub_total - sub_n * mean) ** 2
    se = math.sqrt(g / (g - 1.0) * acc) / n
    crit = t_ppf(1.0 - alpha / 2.0, g - 1)
    return {
        "n": n, "clusters": g, "mean": mean, "se": se,
        "lo": mean - crit * se, "hi": mean + crit * se, "tcrit": crit,
    }


def cluster_bootstrap(values, clusters, draws: int = 10000, seed: int = 20260925, alpha: float = 0.05):
    """房级 bootstrap 百分位区间（重抽样单位=房）。"""

    groups: dict = {}
    for value, key in zip(values, clusters):
        groups.setdefault(key, []).append(value)
    keys = sorted(groups)
    rng = random.Random(seed)
    means = []
    for _ in range(draws):
        pool = []
        for _ in keys:
            pool.extend(groups[keys[rng.randrange(len(keys))]])
        if pool:
            means.append(sum(pool) / len(pool))
    means.sort()
    lo = means[int(alpha / 2 * len(means))]
    hi = means[min(len(means) - 1, int((1 - alpha / 2) * len(means)))]
    return {"lo": lo, "hi": hi, "draws": draws}


def group_ratio_diff_ci(group_a, group_b, draws: int = 5000, seed: int = 20260926, alpha: float = 0.05):
    """两组 0/1 观测的比例差（A − B），按房重抽样的百分位区间。

    用于「我方 vs 对手」在**不同分母**上的比例比较（条件比例无法按局配对时）。
    group_x 是 (取值, 房) 的列表；重抽样单位仍是房。
    """

    def ratio(items):
        if not items:
            return None
        total = 0.0
        for item in items:
            total += item[0] if isinstance(item, tuple) else item
        return total / len(items)

    point = None
    ra, rb = ratio(group_a), ratio(group_b)
    if ra is not None and rb is not None:
        point = ra - rb
    by_group_a: dict = {}
    by_group_b: dict = {}
    for value, key in group_a:
        by_group_a.setdefault(key, []).append(value)
    for value, key in group_b:
        by_group_b.setdefault(key, []).append(value)
    keys = sorted(set(by_group_a) | set(by_group_b))
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        picked = [keys[rng.randrange(len(keys))] for _ in keys]
        pool_a = [v for key in picked for v in by_group_a.get(key, ())]
        pool_b = [v for key in picked for v in by_group_b.get(key, ())]
        ra, rb = ratio(pool_a), ratio(pool_b)
        if ra is not None and rb is not None:
            samples.append(ra - rb)
    samples.sort()
    if not samples:
        return {"mean": point, "lo": None, "hi": None}
    return {
        "mean": point,
        "lo": samples[int(alpha / 2 * len(samples))],
        "hi": samples[min(len(samples) - 1, int((1 - alpha / 2) * len(samples)))],
        "draws": draws,
    }


def paired_difference(pairs, clusters, alpha: float = 0.05):
    """配对差（我方 − 对手三座均值）的聚类置信区间。"""

    values = [float(x) if isinstance(x, (int, float)) else float(x[0] - x[1]) for x in pairs]
    return cluster_ci(values, clusters, alpha)


def fmt_ci(result, digits: int = 4) -> str:
    """把区间渲染成可读字符串；样本不足时明确写「不可估计」。"""

    if result.get("mean") is None:
        return "n=0"
    if result.get("lo") is None:
        return "%.*f（聚类不足，无 CI）" % (digits, result["mean"])
    return "%.*f [%.*f, %.*f]" % (digits, result["mean"], digits, result["lo"], digits, result["hi"])
