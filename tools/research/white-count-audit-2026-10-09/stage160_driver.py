#!/usr/bin/env python3
"""160 单局阶段评估最小装配：10桌×16局驱动 + 逐局导出 sink + 阶段聚合。

对应交叉审查三 §3 的装配项 1/2/5 最小版：
- 每个阶段种子派生 10 个桌赛种子，每桌 rounds=16，RF1 在座位 0 对三家
  weighted_heuristic_v2（对手池第②层声明：旧策略池；不含 P0 参照臂与自
  play 家族，待候选出现后扩展）。
- 逐局导出：settlement（export_hand_settlement）+ 完整轨迹（export_hand）
  双写 JSONL，供 A-E 聚合器事后重建（聚合器另行交付）。
- 阶段聚合：净分、桌名次→名次分（+3/+1/−1/−3，并列共享区间平均的简化
  版：无并列处理，出现并列在输出中单独标记）、阶段配对差 SD 与粗 MDE
  （1.96·2·SD/√n，探索性上界口径）。
单臂运行只验装配与基线分布，不构成任何强度结论。逻辑时钟，不证明在线时限。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
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
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine
from hangma_bot.simulation.artifacts import compute_rules_hash

RF1_SOURCE = (_ROOT / "prebuilt/vip-g37-rf1-compiled-v1/source.py").read_text(encoding="utf-8")
RULESET = "hangma-mvp-v10-public-counts"
PLACE_POINTS = (3, 1, -1, -3)


class StageAuditEngine:
    """透传模拟器；每完成一局双写 settlement 与完整轨迹导出。"""

    def __init__(self, engine, sink) -> None:
        self.engine = engine
        self.sink = sink
        self.context: dict = {}
        self._completed = 0

    def start(self, spec):
        self.context = dict(self.context, match_id=spec.match_id,
                            stage_seed=self.context.get("stage_seed"),
                            table_index=self.context.get("table_index"))
        self._completed = 0
        return self.engine.start(spec)

    def frame(self, world):
        frame = self.engine.frame(world)
        for round_no in range(self._completed + 1, frame.completed_hands + 1):
            row = {**self.context, "round_no": round_no, "observation_scope": "completed_hand_only"}
            try:
                row["settlement"] = self.engine.export_hand_settlement(world, round_no)
            except Exception as exc:  # 导出失败显式 unknown，不猜
                row["settlement_error"] = type(exc).__name__
            try:
                row["hand_export"] = self.engine.export_hand(world, round_no)
            except Exception as exc:
                row["hand_export_error"] = type(exc).__name__
            self.sink(row)
        self._completed = frame.completed_hands
        return frame

    def advance(self, world, revision, choices):
        return self.engine.advance(world, revision, choices)


def place_points(scores):
    """桌名次→名次分；并列时返回 None 并标记（并列裁决属识别区间）。"""
    ours = scores[0]
    others = scores[1:]
    strictly_worse = sum(1 for s in others if s < ours)
    tied = sum(1 for s in others if s == ours)
    if tied:
        return None
    return PLACE_POINTS[strictly_worse]


def run_table(engine, rules, config, seed, stage_seed, table_index, sink):
    rules_config = config.rules
    rf1 = RouteVipHeuristicPolicy(rules_config, source=RF1_SOURCE, max_operations=2_000_000)
    clock = lambda: 800.0  # noqa: E731
    opponents = tuple(ComparableHeuristicPolicyV2(weights=DEFAULT_WEIGHTS_V1, monotonic=clock)
                      for _ in range(3))
    spec = MatchSpec(match_id=f"stage{stage_seed}-t{table_index}", scenario_id=f"stage-{stage_seed}",
                     config=config, seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0))
    driver_config = MatchDriverConfig(clock_mode="logical", step_limit=400_000,
                                      budget_policy=BudgetPolicy(),
                                      competition_tournament_id="offline-stage160",
                                      strict_policy=True, route_limits=ValueAnalysisLimits())
    engine.context = {"stage_seed": stage_seed, "table_index": table_index}
    outcome = asyncio.run(drive_match(
        engine=engine, spec=spec, policies_by_seat=(rf1, *opponents),
        rules=rules, choice_factory=lambda key, action: SimulationChoice(key, action),
        config=driver_config, now_monotonic=clock, wall_clock=None,
        value_limits=ValueAnalysisLimits()))
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-seeds", type=int, nargs="+", required=True)
    parser.add_argument("--out", required=True, help="输出目录（须不存在）")
    parser.add_argument("--tables", type=int, default=10)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    rules_config = RuleConfig(RULESET, 1, False)
    config = TournamentConfig(1, 16, rules_config, TimingConfig(1, 1, 3))
    rules = HangmaRules(rules_config)
    base_engine = SimulationEngine(rules, rules_hash=compute_rules_hash(_ROOT))
    hands_path = out / "hands.jsonl"
    started = time.perf_counter()
    stage_rows = []
    with hands_path.open("w", encoding="utf-8") as stream:
        def sink(row):
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()

        engine = StageAuditEngine(base_engine, sink)
        for stage_seed in args.stage_seeds:
            tables = []
            for table_index in range(args.tables):
                seed = stage_seed * 1000 + table_index
                outcome = run_table(engine, rules, config, seed, stage_seed, table_index, sink)
                scores = list(outcome.final_scores or ()) if outcome.final_scores else None
                tables.append({"table_index": table_index, "seed": seed,
                               "status": outcome.status, "scores": scores,
                               "place_points": None if scores is None else place_points(scores)})
            complete = [t for t in tables if t["status"] == "complete" and t["scores"]]
            stage_rows.append({
                "stage_seed": stage_seed,
                "tables": tables,
                "complete_tables": len(complete),
                "net_seat0": sum(t["scores"][0] for t in complete) if complete else None,
                "place_points_sum": (sum(t["place_points"] for t in complete
                                         if t["place_points"] is not None)
                                     if complete else None),
                "tie_tables": sum(1 for t in complete if t["place_points"] is None),
            })
            print(json.dumps({k: stage_rows[-1][k] for k in
                              ("stage_seed", "complete_tables", "net_seat0", "place_points_sum")},
                             ensure_ascii=False), flush=True)
    nets = [r["net_seat0"] for r in stage_rows if r["net_seat0"] is not None]
    summary = {"stage_seeds": list(args.stage_seeds), "tables_per_stage": args.tables,
               "rounds_per_table": 16, "arm": "rf1", "opponent_pool": "weighted_heuristic_v2 x3",
               "stages": stage_rows, "wall_seconds": round(time.perf_counter() - started, 1),
               "rf1_source_sha256": hashlib.sha256(RF1_SOURCE.encode()).hexdigest(),
               "scope": "装配验证与基线分布；单臂运行不构成强度结论；逻辑时钟"}
    if len(nets) >= 2:
        sd = statistics.stdev(nets)
        summary["net_sd_across_stages"] = round(sd, 2)
        summary["mde_two_arm_rough"] = round(1.96 * 2 * sd / (len(nets) ** 0.5), 2)
    (out / "STAGE-SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps({k: summary.get(k) for k in
                      ("net_sd_across_stages", "mde_two_arm_rough", "wall_seconds")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
