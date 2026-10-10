#!/usr/bin/env python3
"""速胡克制实验：RF1 对三席"纯速胡"变体 vs RF1 对三席启发式基线，同种子配对。

速胡变体=RF1 源码常数补丁：PURPOSES 全零（不保白）、PAIRPRIORWEIGHT=0（弃七对先验）、
PREPBASE=0（弃自然准备加成）、NETUPGRADEWEIGHT/ANCHOROPTIONBASE/ANCHOROPTIONSTEP=0
（不弃胡等升级）——即"能推进就推进、能胡就胡、不留白不留七对"的贪心速胡形态。
输出每种子两臂的四座终分与 RF1 座位分差；判据=配对 Δ=速胡臂RF1−基线臂RF1。
逻辑时钟；单臂对打不是官方赛制结论。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

_ROOT = next(p for p in Path(__file__).resolve().parents
             if (p / "src/hangma_bot/bootstrap.py").is_file())
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tools/research/white-count-audit-2026-10-09"))

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.offline.evaluate import MatchDriverConfig, drive_match
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine
from hangma_bot.simulation.artifacts import compute_rules_hash
from probe_quote_variants import flexcost_source as protected_flexcost_source

BASE_SOURCE = (_ROOT / "prebuilt/vip-g37-rf1-compiled-v1/source.py").read_text(encoding="utf-8")
SPEED_PATCHES = [
    ("PURPOSES = (0.0, 2.5, 6.0, 13.0, 26.0)", "PURPOSES = (0.0, 0.0, 0.0, 0.0, 0.0)"),
    ("PAIRPRIORWEIGHT = 0.30", "PAIRPRIORWEIGHT = 0.0"),
    ("PREPBASE = 0.60", "PREPBASE = 0.0"),
    ("NETUPGRADEWEIGHT = 1.40", "NETUPGRADEWEIGHT = 0.0"),
    ("ANCHOROPTIONBASE = 0.14", "ANCHOROPTIONBASE = 0.0"),
    ("ANCHOROPTIONSTEP = 0.10", "ANCHOROPTIONSTEP = 0.0"),
]

_OLD_ADJ = '''        if kind == "chi" or kind == "peng":
            adjustment = SKIPVALUE * float(action["skipped_seats"]) * drawscale - CLAIMCOST'''


def flexcost_source(flexcost: float = 1.0) -> str:
    """复用同一保护源码：仅无白／单白普通响应窗，当前多白沿用父版。"""
    return protected_flexcost_source(BASE_SOURCE, flexcost)


def speeder_source() -> str:
    text = BASE_SOURCE
    for old, new in SPEED_PATCHES:
        if text.count(old) != 1:
            raise SystemExit("速胡补丁位置不唯一: " + old)
        text = text.replace(old, new, 1)
    return text


def run_match(seed, arm, rules_config, config, rules, engine, fast_src):
    clock = lambda: 800.0  # noqa: E731
    rf1 = RouteVipHeuristicPolicy(rules_config, source=BASE_SOURCE, max_operations=2_000_000)
    if arm == "baseline":
        opponents = tuple(ComparableHeuristicPolicyV2(weights=DEFAULT_WEIGHTS_V1, monotonic=clock)
                          for _ in range(3))
    elif arm == "flexcost":
        opponents = tuple(ComparableHeuristicPolicyV2(weights=DEFAULT_WEIGHTS_V1, monotonic=clock)
                          for _ in range(3))
        rf1 = RouteVipHeuristicPolicy(rules_config, source=fast_src, max_operations=2_000_000)
    else:
        opponents = tuple(RouteVipHeuristicPolicy(rules_config, source=fast_src,
                                                  max_operations=2_000_000) for _ in range(3))
    spec = MatchSpec(match_id=f"speed-{arm}-{seed}", scenario_id=f"speed-{seed}",
                     config=config, seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0))
    driver_config = MatchDriverConfig(clock_mode="logical", step_limit=200_000,
                                      budget_policy=BudgetPolicy(),
                                      competition_tournament_id="offline-speeder-test",
                                      strict_policy=True, route_limits=ValueAnalysisLimits())
    outcome = asyncio.run(drive_match(
        engine=engine, spec=spec, policies_by_seat=(rf1, *opponents),
        rules=rules, choice_factory=lambda key, action: SimulationChoice(key, action),
        config=driver_config, now_monotonic=clock, wall_clock=None,
        value_limits=ValueAnalysisLimits()))
    return {"seed": seed, "arm": arm, "status": outcome.status,
            "final": list(outcome.final_scores or ()) if outcome.final_scores else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--arm", choices=("baseline", "speeder", "flexcost"), required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rules_config = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
    config = TournamentConfig(1, 16, rules_config, TimingConfig(1, 1, 3))
    rules = HangmaRules(rules_config)
    engine = SimulationEngine(rules, rules_hash=compute_rules_hash(_ROOT))
    fast = flexcost_source(1.0) if args.arm == "flexcost" else speeder_source()
    rows = []
    started = time.perf_counter()
    for seed in args.seeds:
        row = run_match(seed, args.arm, rules_config, config, rules, engine, fast)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(
        {"arm": args.arm, "rows": rows,
         "rf1_mean": (round(statistics.mean(r["final"][0] for r in rows if r["final"]), 2)
                      if any(r["final"] for r in rows) else None),
         "wall_seconds": round(time.perf_counter() - started, 1)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
