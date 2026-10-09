#!/usr/bin/env python3
"""带完整世界导出的 RF1 面板捕获：视图 + 逐单局 full_world 双记录。

与 capture_rf1_views 相同装配（RF1 对 weighted_heuristic_v2 三家、rounds=16），
另加每完成单局 export_hand 全量导出（初始四家手牌、全序牌墙、完整事件流），
供读牌信号预测门做墙内真值重建。只读装配，不改线上包。
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

RF1_SOURCE_SHA256 = "63125dcea8d88bb30172be8330fa1ac4c5d500d60c0ee79fd51f7b6cd0f6fd16"


class WorldExportEngine:
    """透传模拟器；每完成单局导出 full_world（初始牌+全序墙+事件流）。"""

    def __init__(self, engine, sink) -> None:
        self.engine = engine
        self.sink = sink
        self.context: dict = {}
        self._completed = 0

    def start(self, spec):
        self.context = dict(self.context, match_id=spec.match_id)
        self._completed = 0
        return self.engine.start(spec)

    def frame(self, world):
        frame = self.engine.frame(world)
        for round_no in range(self._completed + 1, frame.completed_hands + 1):
            row = {**self.context, "round_no": round_no, "scope": "completed_hand_full_world"}
            try:
                row["hand_export"] = self.engine.export_hand(world, round_no)
            except Exception as exc:
                row["hand_export_error"] = type(exc).__name__
            self.sink(row)
        self._completed = frame.completed_hands
        return frame

    def advance(self, world, revision, choices):
        return self.engine.advance(world, revision, choices)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    source = (_ROOT / "prebuilt/vip-g37-rf1-compiled-v1/source.py").read_text(encoding="utf-8")
    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest != RF1_SOURCE_SHA256:
        raise SystemExit("源码漂移")

    rules_config = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
    config = TournamentConfig(1, 16, rules_config, TimingConfig(1, 1, 3))
    rules = HangmaRules(rules_config)
    base_engine = SimulationEngine(rules, rules_hash=compute_rules_hash(_ROOT))
    clock = lambda: 800.0  # noqa: E731

    view_stream = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(view_stream, limits=ScoringInputCaptureLimits(
        max_view_json_bytes=16_000_000, max_total_json_bytes=4_000_000_000, max_unique_views=6000))
    decision_stream = gzip.open(out / "decisions.jsonl.gz", "xt", encoding="utf-8")
    hands_stream = (out / "hands.jsonl").open("x", encoding="utf-8")

    def d_sink(row):
        decision_stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        decision_stream.flush()

    def h_sink(row):
        hands_stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        hands_stream.flush()

    engine = WorldExportEngine(base_engine, h_sink)
    started = time.perf_counter()
    summary = {"matches": [], "seeds": list(args.seeds)}
    try:
        for seed in args.seeds:
            rf1 = RouteVipHeuristicPolicy(rules_config, source=source, max_operations=2_000_000)
            holder = {"value": {"match_id": f"panel-w-{seed}", "pool": "panel", "root_id": f"seed-{seed}",
                                "permutation": [0, 1, 2, 3], "source_kind": "simulation"}}

            def ctx():
                return dict(holder["value"])

            wrapped = VipDevelopmentAuditPolicy(rf1, "panel-w", ctx, d_sink, challenger=True, capture=capture)
            opponents = tuple(ComparableHeuristicPolicyV2(weights=DEFAULT_WEIGHTS_V1, monotonic=clock)
                              for _ in range(3))
            spec = MatchSpec(match_id=f"panel-w-{seed}", scenario_id=f"seed-{seed}",
                             config=config, seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0))
            driver_config = MatchDriverConfig(clock_mode="logical", step_limit=200_000,
                                              budget_policy=BudgetPolicy(),
                                              competition_tournament_id="offline-rf1-world-panel",
                                              strict_policy=True, route_limits=ValueAnalysisLimits())
            outcome = asyncio.run(drive_match(
                engine=engine, spec=spec, policies_by_seat=(wrapped, *opponents),
                rules=rules, choice_factory=lambda key, action: SimulationChoice(key, action),
                config=driver_config, now_monotonic=clock, wall_clock=None,
                value_limits=ValueAnalysisLimits()))
            summary["matches"].append({"seed": seed, "status": outcome.status,
                                       "completed_hands": outcome.completed_hands})
            print("seed", seed, outcome.status, flush=True)
    finally:
        costs = capture.finish()
        view_stream.close()
        decision_stream.close()
        hands_stream.close()
    (out / "PANEL-SUMMARY.json").write_text(json.dumps(
        {**summary, "capture_costs": costs, "rf1_source_sha256": digest,
         "wall_seconds": round(time.perf_counter() - started, 1)}, ensure_ascii=False, indent=1))
    print(json.dumps(summary["matches"], ensure_ascii=False))


if __name__ == "__main__":
    main()
