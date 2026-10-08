"""坐隐 1.7 前置：在记录决策上测量 M4 的机制达成率与分差分布。

用途（族定义 §4）：
  - **鸣牌窗口改选率**：候选与基线首选动作不同的比例（机制达成率主指标）
  - **弃牌窗口改选率**：应为 0，否则说明跑偏（P-2）
  - **改选方向分布**：鸣牌→过 / 过→鸣牌（P-3）
  - **分差分布**：基线第一名与第二名的总分差 → **M4 幅度的经验校准依据**

输入是项目既有决策语料（`decisions.jsonl`）。它记录当时的**观察与候选事实**，
因此两个策略看到**完全相同的输入**，差异只来自评分。

**边界**：
  - 这是**决策级**信号，按 README §4.2 **只作机制达成诊断，不得作适应度排序**。
  - 语料的 `rules` 是当时记录的事实，与当前规则版本可能不同；本工具只比较
    **两个策略在同一记录输入上的差异**，不从它推断强度。
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

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))

from hangma_bot.application.deadline import BudgetPolicy, ManualClock  # noqa: E402
from hangma_bot.bootstrap import build_decision_codec  # noqa: E402
from hangma_bot.offline.evaluate import translate_budget  # noqa: E402
from hangma_bot.hangma.interface import RuleCompleteness  # noqa: E402
from hangma_bot.kernel.actions import Chi, Gang, Peng  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "sitin_m4_policy", _project_file(_PROJECT_ROOT, Path(__file__).resolve().parent / "sitin_m4_policy.py"))
m4mod = importlib.util.module_from_spec(_spec)
sys.modules["sitin_m4_policy"] = m4mod
assert _spec.loader is not None
_spec.loader.exec_module(m4mod)

MELD_ACTIONS = ("chi:", "peng:", "gang:")


def _is_meld(action_key: str) -> bool:
    return action_key.startswith(MELD_ACTIONS)


def _load(path: Path, limit: Optional[int]) -> list:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
        if limit and len(rows) >= limit:
            break
    return rows


def measure(rows: Sequence[Mapping[str, Any]]) -> dict:
    codec = build_decision_codec()
    decode_request = codec["decode_request"]
    decode_budget = codec["decode_budget"]

    # 记录的预算使用**历史单调时钟**，不能直接与当前时钟比较——
    # 按项目既有做法把预算平移到新基准，并让策略使用同一基准的 ManualClock
    # （与 offline.evaluate 的 decisions 模式同一处理）。
    NEW_ORIGIN = 100.0
    clock = ManualClock(start_monotonic=NEW_ORIGIN)
    v2 = ComparableHeuristicPolicyV2(monotonic=clock.now)
    m4 = m4mod.M4OpportunityCostPolicy(monotonic=clock.now)
    m4_off = m4mod.M4OpportunityCostPolicy(monotonic=clock.now, enabled=False)

    counts = {
        "windows": 0, "meld_windows": 0, "other_windows": 0,
        "meld_changed": 0, "other_changed": 0,
        "meld_to_other": 0, "other_to_meld": 0,
        "m4_vs_off_changed": 0, "degraded": 0,
    }
    gaps: list = []          # 基线第一名与第二名的总分差（全部窗口）
    gaps_meld: list = []     # 仅鸣牌窗口
    # **M4 真正有机会翻转的空间**：基线首选是鸣牌时，它与第二名的分差。
    # 分差越小，越可能被机会成本项翻转；这决定了 M4 在这批语料上是否可行。
    gaps_meld_first: list = []
    meld_first_count = 0
    natural_values: list = []

    for row in rows:
        request_payload = row.get("request")
        if not isinstance(request_payload, Mapping):
            continue
        try:
            request = decode_request(request_payload)
            recorded = decode_budget(row.get("budget"), row.get("budget_origin_monotonic", 0.0))
            budget = translate_budget(
                recorded, row.get("budget_origin_monotonic", 0.0), NEW_ORIGIN)
        except Exception:
            counts["degraded"] += 1
            continue

        is_meld_window = any(_is_meld(c.action_key) for c in request.rules.legal_candidates)
        try:
            plan_v2 = asyncio.run(v2.choose(request, budget))
            plan_m4 = asyncio.run(m4.choose(request, budget))
            plan_off = asyncio.run(m4_off.choose(request, budget))
        except Exception:
            counts["degraded"] += 1
            continue

        first = lambda plan: plan.candidates[0].action_key if plan.candidates else None  # noqa: E731
        k_v2, k_m4, k_off = first(plan_v2), first(plan_m4), first(plan_off)
        if k_v2 is None:
            continue
        counts["windows"] += 1
        # 消融开关自检：关闭时必须与基线完全一致
        if k_off != k_v2:
            counts["m4_vs_off_changed"] += 1   # 期望 0；非 0 即为缺陷
        if is_meld_window:
            counts["meld_windows"] += 1
            if k_m4 != k_v2:
                counts["meld_changed"] += 1
                if _is_meld(k_v2) and not _is_meld(k_m4):
                    counts["meld_to_other"] += 1
                elif not _is_meld(k_v2) and _is_meld(k_m4):
                    counts["other_to_meld"] += 1
        else:
            counts["other_windows"] += 1
            if k_m4 != k_v2:
                counts["other_changed"] += 1

        totals = [c.total_score for c in plan_v2.candidates if c.total_score is not None]
        if len(totals) >= 2:
            ordered = sorted(totals, reverse=True)
            gap = ordered[0] - ordered[1]
            gaps.append(gap)
            if is_meld_window:
                gaps_meld.append(gap)
                if k_v2 is not None and _is_meld(k_v2):
                    meld_first_count += 1
                    gaps_meld_first.append(gap)
        if is_meld_window:
            natural = m4mod.natural_draw_value(request.rules.legal_candidates)
            if natural is not None:
                natural_values.append(natural)

    def q(values: Sequence[float], frac: float) -> Optional[float]:
        if not values:
            return None
        ordered = sorted(values)
        return round(ordered[min(int(frac * (len(ordered) - 1)), len(ordered) - 1)], 2)

    return {
        "schema": "sitin-mechanism-rate/1",
        "counts": counts,
        "rates": {
            "meld_window_change_rate": (round(counts["meld_changed"] / counts["meld_windows"], 4)
                                        if counts["meld_windows"] else None),
            "other_window_change_rate": (round(counts["other_changed"] / counts["other_windows"], 4)
                                         if counts["other_windows"] else None),
        },
        "top_gap": {
            "n": len(gaps),
            "q10": q(gaps, 0.10), "q25": q(gaps, 0.25), "median": q(gaps, 0.50),
            "q75": q(gaps, 0.75), "q90": q(gaps, 0.90),
            "mean": round(statistics.fmean(gaps), 2) if gaps else None,
            "meld_window_median": q(gaps_meld, 0.50),
        },
        # M4 的机会窗口：基线首选鸣牌时的分差分布 + 自然摸牌收益分布
        "m4_openings": {
            "meld_first_count": meld_first_count,
            "meld_first_gap_median": q(gaps_meld_first, 0.50),
            "meld_first_gap_min": min(gaps_meld_first) if gaps_meld_first else None,
            "meld_first_gap_max": max(gaps_meld_first) if gaps_meld_first else None,
            "meld_first_gap_below_20": sum(1 for g in gaps_meld_first if g < 20),
            "natural_n": len(natural_values),
            "natural_min": min(natural_values) if natural_values else None,
            "natural_median": q([float(v) for v in natural_values], 0.50),
            "natural_max": max(natural_values) if natural_values else None,
        },
    }


def render(report: Mapping[str, Any]) -> str:
    c, r, g = report["counts"], report["rates"], report["top_gap"]
    o = report["m4_openings"]
    return "\n".join([
        "# 坐隐 M4 机制达成率与分差分布", "",
        "统计单位：记录决策窗口。**决策级信号只作机制诊断，不作适应度排序**（README §4.2）。", "",
        "## 机制达成率（族定义 §4）", "",
        "| 指标 | 值 |", "| --- | ---: |",
        "| 可评分窗口 | {0} |".format(c["windows"]),
        "| 鸣牌窗口 | {0} |".format(c["meld_windows"]),
        "| **鸣牌窗口改选率** | **{0}** |".format(r["meld_window_change_rate"]),
        "| 非鸣牌窗口 | {0} |".format(c["other_windows"]),
        "| **非鸣牌窗口改选率**（应为 0） | **{0}** |".format(r["other_window_change_rate"]),
        "| 改选：鸣牌→过 | {0} |".format(c["meld_to_other"]),
        "| 改选：过→鸣牌 | {0} |".format(c["other_to_meld"]),
        "| 消融关闭时与基线不一致（应为 0） | {0} |".format(c["m4_vs_off_changed"]),
        "| 无法评分 | {0} |".format(c["degraded"]), "",
        "## 基线第一名与第二名分差（**M4 幅度的校准依据**）", "",
        "| 分位 | 全部窗口 | 鸣牌窗口 |", "| --- | ---: | ---: |",
        "| n | {0} | — |".format(g["n"]),
        "| Q10 | {0} | — |".format(g["q10"]),
        "| Q25 | {0} | — |".format(g["q25"]),
        "| **中位** | **{0}** | **{1}** |".format(g["median"], g["meld_window_median"]),
        "| Q75 | {0} | — |".format(g["q75"]),
        "| Q90 | {0} | — |".format(g["q90"]),
        "| 均值 | {0} | — |".format(g["mean"]), "",
        "> M4 的追加项若**小于这里的中位分差**，就几乎改变不了首选动作。", "",
        "## M4 的机会窗口（基线首选鸣牌时）", "",
        "| 指标 | 值 |", "| --- | ---: |",
        "| 基线首选为鸣牌的窗口数 | {0} → {1} |".format(
            o["meld_first_count"], o["meld_first_gap_median"]),
        "| 这些窗口的分差最小值 | {0} |".format(o["meld_first_gap_min"]),
        "| 这些窗口的分差最大值 | {0} |".format(o["meld_first_gap_max"]),
        "| 分差 < 20 的窗口数 | {0} |".format(o["meld_first_gap_below_20"]),
        "| 自然摸牌收益 n / 中位 / 范围 | {0} / {1} / {2}–{3} |".format(
            o["natural_n"], o["natural_median"], o["natural_min"], o["natural_max"]), "",
        "> 只有分差接近追加项量级的窗口才可能被翻转；上表决定 M4 在这批语料上是否可行。", "",
    ]) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="坐隐 M4 机制达成率与分差分布")
    parser.add_argument("decisions", help="decisions.jsonl 路径")
    parser.add_argument("--limit", type=int, help="只读前 N 行（调试用）")
    parser.add_argument("--out", help="产物目录")
    args = parser.parse_args(argv)

    report = measure(_load(Path(args.decisions), args.limit))
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "mechanism-rate.json").write_text(text + "\n", encoding="utf-8")
        (out / "mechanism-rate.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
