#!/usr/bin/env python3
"""RF1 v3 评分视图面板捕获：模拟器真实对局中录制我方 RF1 座位的全部评分输入。

用途：为 SINGLEWHITE-160 第 1 步报价层探针（κ/VARREF/PURPOSES[1]）提供真实
v3 评分视图面板（GAP §5）。装配只读：RouteVipHeuristicPolicy 载入冻结 RF1
source.py（SHA256 钉住），VipDevelopmentAuditPolicy 记录逐窗公开观察与已选
动作，ScoringInputCapture 按整图 SHA 去重保存 candidate_view。对手为
weighted_heuristic_v2 三家，rounds=16、底分1、有财必拷关；种子显式给定。
不比较策略、不改线上包、不发布；面板仅供离线重评分。
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

_ROOT = next(p for p in Path(__file__).resolve().parents
             if (p / "src/hangma_bot/bootstrap.py").is_file())
sys.path.insert(0, str(_ROOT / "src"))

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.offline.evaluate import MatchDriverConfig, drive_match
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine
from hangma_bot.simulation.artifacts import compute_rules_hash

RF1_SOURCE_SHA256 = '63125dcea8d88bb30172be8330fa1ac4c5d500d60c0ee79fd51f7b6cd0f6fd16'
RULESET = "hangma-mvp-v10-public-counts"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(_ROOT / "prebuilt/vip-g37-rf1-compiled-v1/source.py"))
    parser.add_argument("--out", required=True, help="输出目录（须不存在）")
    parser.add_argument("--seeds", type=int, nargs="+", default=[1101, 1102, 1103, 1104])
    parser.add_argument("--rounds", type=int, default=16)
    args = parser.parse_args()

    source = Path(args.source).read_text(encoding="utf-8")
    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest != RF1_SOURCE_SHA256:
        raise SystemExit("RF1 源码摘要漂移: " + digest)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    rules_config = RuleConfig(RULESET, 1, False)
    config = TournamentConfig(1, args.rounds, rules_config, TimingConfig(1, 1, 3))
    rules = HangmaRules(rules_config)
    engine = SimulationEngine(rules, rules_hash=compute_rules_hash(_ROOT))

    view_stream = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(view_stream, limits=ScoringInputCaptureLimits(
        max_view_json_bytes=16_000_000, max_total_json_bytes=4_000_000_000, max_unique_views=6000))
    decision_stream = gzip.open(out / "decisions.jsonl.gz", "xt", encoding="utf-8")
    clock = lambda: 800.0  # noqa: E731 逻辑时钟，与开发批一致

    def sink(row: dict) -> None:
        decision_stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        decision_stream.flush()

    started = time.perf_counter()
    summary = {"matches": [], "seeds": list(args.seeds), "rounds": args.rounds}
    costs = {}
    try:
        for seed in args.seeds:
            rf1 = RouteVipHeuristicPolicy(rules_config, source=source, max_operations=2_000_000)
            context = {"match_id": f"panel-rf1-{seed}", "pool": "panel", "root_id": f"seed-{seed}",
                       "permutation": [0, 1, 2, 3], "source_kind": "simulation"}
            context_holder = {"value": context}

            def ctx() -> dict:
                return dict(context_holder["value"])

            wrapped = VipDevelopmentAuditPolicy(rf1, "panel-rf1", ctx, sink,
                                                challenger=True, capture=capture)
            opponents = tuple(ComparableHeuristicPolicyV2(weights=DEFAULT_WEIGHTS_V1, monotonic=clock)
                              for _ in range(3))
            spec = MatchSpec(match_id=f"panel-rf1-{seed}", scenario_id=f"seed-{seed}",
                             config=config, seed=seed, initial_dealer=0,
                             initial_scores=(0, 0, 0, 0))
            driver_config = MatchDriverConfig(clock_mode="logical", step_limit=200_000,
                                              budget_policy=BudgetPolicy(),
                                              competition_tournament_id="offline-rf1-view-panel",
                                              strict_policy=True, route_limits=ValueAnalysisLimits())
            outcome = asyncio.run(drive_match(
                engine=engine, spec=spec,
                policies_by_seat=(wrapped, *opponents),
                rules=rules, choice_factory=lambda key, action: SimulationChoice(key, action),
                config=driver_config, now_monotonic=clock, wall_clock=None,
                value_limits=ValueAnalysisLimits()))
            counts = outcome.runtime_counts
            summary["matches"].append({
                "seed": seed, "status": outcome.status,
                "completed_hands": outcome.completed_hands,
                "final_scores": None if outcome.final_scores is None else list(outcome.final_scores),
                "error_reason": outcome.error_reason,
                "timeouts": counts.timeouts, "illegal_choices": counts.illegal_choices,
                "fallbacks": counts.fallbacks, "auto_actions": counts.auto_actions,
                "audit_missing": counts.audit_missing,
            })
            print("seed", seed, "status", outcome.status, flush=True)
    finally:
        costs = capture.finish()
        view_stream.close()
        decision_stream.write(json.dumps({"summary": summary, "capture_costs": costs},
                                         ensure_ascii=False, sort_keys=True) + "\n")
        decision_stream.close()
    (out / "PANEL-SUMMARY.json").write_text(json.dumps(
        {**summary, "capture_costs": costs, "rf1_source_sha256": digest,
         "wall_seconds": round(time.perf_counter() - started, 1),
         "scope": "RF1自评分视图面板，仅离线重评分用途"},
        ensure_ascii=False, indent=1))
    print(json.dumps(summary["matches"], ensure_ascii=False))


if __name__ == "__main__":
    main()
