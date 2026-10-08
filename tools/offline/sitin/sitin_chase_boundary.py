"""能力尺 · 第六阶段：「追 vs 收」的精确边界（独立小脚本，避免与主探针流程耦合）。

对每个构造局点，在**同一个精确口径**下并列三个量：
  fan(收)              —— 现在收胡的番值（确定）；
  E(追) = P(追后再胡) × fan(新链)  —— 打白（爆头态即飘，链 +1）后恢复「能胡就胡」；
  盈亏平衡所需概率 = fan(收) / fan(新链)。
判据：追划算 ⟺ P(追后再胡) > 平衡概率。链每层 ×2 ⇒ 平衡概率 ≈ **50%** 是常数门槛。
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
import json
import os
import sys

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

import sitin_k_turn_exact as kt  # noqa: E402
import sitin_opportunity_positions as opp  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", default="4,8,12")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    turns_list = [int(x) for x in args.turns.split(",") if x.strip()]

    hands = list(opp.baotou_templates())
    rows = []
    for index, hand in enumerate(hands):
        world = kt.world_of(hand)
        draw = next((code for code in kt.ALL_CODES if world.get(code, 0) > 0), None)
        if draw is None or kt.WHITE not in hand:
            continue
        for chain in (0, 2):
            entry = {"index": index, "hand": "".join(hand), "chain": chain, "draw": draw}
            for turns in turns_list:
                row = kt.chase_versus_take(hand, world, draw, True, chain, turns)
                entry["k%d" % turns] = {
                    "fan_take": row.get("fan_take"),
                    "E_chase": (None if row.get("expectation_chase") is None
                                else round(row["expectation_chase"], 4)),
                    "P_chase": (None if row.get("probability_chase") is None
                                else round(row["probability_chase"], 4)),
                    "breakeven": row.get("breakeven_probability"),
                    "chase_better": bool(row.get("expectation_chase") is not None
                                         and row.get("fan_take") is not None
                                         and row["expectation_chase"] > row["fan_take"]),
                }
            rows.append(entry)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "chase.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": "sitin-chase-boundary/1", "turns": turns_list, "rows": rows},
                  fh, ensure_ascii=False, indent=1)

    print("%-4s %-6s %-5s %-8s %-9s %-9s %-9s %-6s" % (
        "hand", "chain", "k", "fan(收)", "E(追)", "P(追再胡)", "平衡概率", "追更优"))
    for row in rows:
        for turns in turns_list:
            cell = row["k%d" % turns]
            print("%-4d %-6d %-5d %-8s %-9s %-9s %-9s %-6s" % (
                row["index"], row["chain"], turns, cell["fan_take"], cell["E_chase"],
                cell["P_chase"], cell["breakeven"], cell["chase_better"]))
    verdicts = [c["chase_better"] for row in rows for c in
                (row["k%d" % t] for t in turns_list)]
    print()
    print("组合数 %d，其中「追更优」的 %d 个" % (len(verdicts), sum(verdicts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
