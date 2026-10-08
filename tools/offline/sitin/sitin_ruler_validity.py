"""尺子效度检验：能力分能不能预测真实强度？

数据全部来自既有产物（本分支探针 + R10 文档），零新实验：
  能力分（构造位点，各 120 个杠位点 / 42 个近听位点）：
    - 杠选择率：positions-v5
    - 链深敏感度（120 副里改变选择的次数）：positions-v5
    - k 巡精确 regret（越低越好）：lookahead-v3 的 A_gang_chain
  真实强度（完整阶段 H/M 等权效用差，来自 R10 结案文档）：
    - 旧清单 strong-seeds-20260920
    - 新清单 strong-seeds-unseen-dev-20260920（换牌山，只复核了 3 个来源）
判据：Spearman 秩相关。n 很小（旧 6、新 3），只作方向性判断。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import os

# 能力分（本分支产物）
CAPABILITY = {
    # 名称: (杠选择率/120, 链敏感度/120, k巡 regret)
    "V2": (59, 0, 0.009679),
    "hard-astra-high": (0, 0, 0.004839),
    "hard-sol-high": (16, 0, 0.0),
    "hard-sol-max": (45, 6, 0.0),
    "hard-terra-max": (20, 2, 0.007646),
    "river-sol-high": (59, 0, 0.009679),
    "route-terra-max": (118, 0, 0.009679),
}
# 真实强度（R10 文档：完整阶段 H/M 等权效用差）
STRENGTH_OLD = {
    "route-terra-max": 0.125,
    "hard-terra-max": 0.109375,
    "hard-sol-high": 0.09375,
    "hard-astra-high": 0.0625,
    "river-sol-high": 0.023438,
    "hard-sol-max": 0.015625,
}
STRENGTH_NEW = {
    "hard-terra-max": -0.007812,
    "route-terra-max": -0.085938,
}


def spearman(pairs):
    """秩相关；并列取平均秩。"""
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        index = 0
        while index < len(order):
            stop = index
            while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
                stop += 1
            average = (index + stop) / 2.0 + 1.0
            for position in range(index, stop + 1):
                out[order[position]] = average
            index = stop + 1
        return out
    xs = ranks([pair[0] for pair in pairs])
    ys = ranks([pair[1] for pair in pairs])
    n = len(pairs)
    if n < 3:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    numerator = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    denominator = (sum((x - mean_x) ** 2 for x in xs)
                   * sum((y - mean_y) ** 2 for y in ys)) ** 0.5
    return None if denominator == 0 else numerator / denominator


def main() -> int:
    print("== 能力分 vs 真实强度（旧清单，n=6）==")
    for label, index, sign in (("杠选择率", 0, 1), ("链敏感度", 1, 1), ("k巡 regret", 2, -1)):
        pairs = []
        for name, strength in STRENGTH_OLD.items():
            capability = CAPABILITY[name][index]
            pairs.append((sign * capability, strength))
        rho = spearman(pairs)
        print("  %-12s Spearman = %s" % (label, "n/a" if rho is None else round(rho, 4)))
        for name in sorted(STRENGTH_OLD, key=lambda n: -STRENGTH_OLD[n]):
            print("      %-18s 能力 %-8s 强度 %+.4f" % (
                name, CAPABILITY[name][index] * sign, STRENGTH_OLD[name]))

    print()
    print("== 能力分 vs 真实强度（新清单，n=2 不计算相关）==")
    for name, strength in sorted(STRENGTH_NEW.items(), key=lambda kv: -kv[1]):
        print("  %-18s 杠 %-4d 链敏 %-3d regret %-9s 强度 %+.4f" % (
            name, CAPABILITY[name][0], CAPABILITY[name][1], CAPABILITY[name][2], strength))

    print()
    print("== 关键对照：把候选按「regret 从低到高」排，看真实强度是否同序 ==")
    order = sorted(STRENGTH_OLD, key=lambda n: CAPABILITY[n][2])
    for name in order:
        print("  regret %-9s 杠 %-4d 链敏 %-3d 强度(旧) %+.4f" % (
            CAPABILITY[name][2], CAPABILITY[name][0], CAPABILITY[name][1],
            STRENGTH_OLD[name]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
