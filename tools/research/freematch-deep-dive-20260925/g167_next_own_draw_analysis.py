#!/usr/bin/env python3
"""G167 事后描述：按池×根统计下一摸牌形前沿，不把相关世界当独立桌。"""

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

from collections import Counter
import json
from pathlib import Path
import random
from statistics import correlation, mean, pstdev

import g167_next_own_draw_route as source


BASE = source.OUT
OUT = BASE / "analysis.json"
BOOTSTRAP_SEED = 20260928167
REPLICATES = 20_000


def order(arm: dict, *, frontier: bool) -> tuple[int, int] | None:
    """普通型向听优先、同向听有效码数次之；数字越小表示牌形越好。"""
    if arm["next_draw"] is None:
        return None
    record = arm["next_draw"]
    shanten = record["best_standard_shanten_after" if frontier
                      else "chosen_standard_shanten_after"]
    types = record["frontier_max_standard_useful_types" if frontier
                   else "chosen_standard_useful_types"]
    if shanten is None or types is None:
        return None
    return shanten, -types


def interval(values: list[float], seed: int) -> list[float] | None:
    """每池×根窗口先求相关世界差，再等权 bootstrap 根。"""
    if not values:
        return None
    rng = random.Random(seed)
    samples = sorted(mean(rng.choice(values) for _ in values)
                     for _ in range(REPLICATES))
    return [samples[int(0.025 * REPLICATES)], samples[int(0.975 * REPLICATES)]]


def group(rows: list[dict], seed: int) -> dict:
    """同时报告截尾、实际续打动作与可达最优前沿，二者不混。"""
    if len({(row["mix"], row["root_index"]) for row in rows}) != len(rows):
        raise ValueError("G167 一个池×根出现多个窗口")
    counts = Counter()
    root_advantage = []
    root_score = []
    for row in rows:
        local = Counter()
        for pair in row["world_pairs"]:
            p, a = pair["parent"], pair["alternate"]
            if not p["reached"] or not a["reached"]:
                counts["censored_pairs"] += 1
                continue
            counts["both_reached"] += 1
            for name, frontier in (("frontier", True), ("chosen", False)):
                pv, av = order(p, frontier=frontier), order(a, frontier=frontier)
                if pv is None or av is None:
                    counts[name + "_not_comparable"] += 1
                    continue
                if av < pv:
                    counts[name + "_alternate_better"] += 1
                    local[name + "_alternate_better"] += 1
                elif av > pv:
                    counts[name + "_parent_better"] += 1
                    local[name + "_parent_better"] += 1
                else:
                    counts[name + "_tie"] += 1
                    local[name + "_tie"] += 1
        denominator = sum(local["frontier_" + name] for name in (
            "alternate_better", "parent_better", "tie"))
        if denominator:
            root_advantage.append((local["frontier_alternate_better"]
                                   - local["frontier_parent_better"]) / denominator)
            root_score.append(mean(pair["focal_delta_alt_minus_parent"]
                                   for pair in row["world_pairs"]))
    corr = (correlation(root_advantage, root_score)
            if len(root_advantage) >= 3 and pstdev(root_advantage) > 0
            and pstdev(root_score) > 0 else None)
    return {
        "windows": len(rows),
        "related_world_pairs": len(rows) * len(source.prior.WORLD_KEYS),
        "counts": dict(sorted(counts.items())),
        "root_equal_frontier_advantage": mean(root_advantage)
        if root_advantage else None,
        "root_bootstrap_95_frontier_advantage": interval(root_advantage, seed),
        "frontier_advantage_vs_paired_score_window_correlation": corr,
        "boundary": "下一摸后验前沿是机制描述，不是线上可读事实或积分代理。",
    }


def main() -> None:
    """结果已看后的固定口径脚本；不能把输出称为事前验证。"""
    if OUT.exists():
        raise FileExistsError("G167 事后分析已存在，拒绝覆盖")
    result = json.loads((BASE / "result.json").read_text(encoding="utf-8"))
    rows_path = BASE / "rows.jsonl"
    if (result["status"] != "complete" or result["windows_completed"] != 64
            or result["rows_sha256"] != source.sha(rows_path)):
        raise ValueError("G167 下一摸来源未完成或摘要漂移")
    rows = [json.loads(line) for line in rows_path.read_text(
        encoding="utf-8").splitlines()]
    groups = {}
    for mix in ("H", "M"):
        for white in (0, 1):
            key = f"{mix}/{white}"
            subset = [row for row in rows if row["mix"] == mix
                      and row["white_before"] == white]
            if len(subset) != 16:
                raise ValueError("G167 固定四层窗口覆盖不守恒")
            groups[key] = group(subset, BOOTSTRAP_SEED + len(groups))
    payload = {
        "schema": "g167-next-own-draw-analysis/1",
        "source_rows_sha256": source.sha(rows_path),
        "source_result_sha256": source.sha(BASE / "result.json"),
        "analysis_script_sha256": source.sha(Path(__file__)),
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_replicates": REPLICATES,
        "groups": groups,
        "boundary": "G166 积分已看后的下一摸描述；非独立候选确认。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(groups, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
