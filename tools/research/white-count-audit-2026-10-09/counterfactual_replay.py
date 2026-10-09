#!/usr/bin/env python3
"""反事实重放驱动：同种子同牌墙重放，在指定决策窗强制替代弃牌，对比最终得分。

臂 A=面板原始对局（PANEL-SUMMARY 的 final_scores）；臂 B=ForcerPolicy 在目标
出现序号处强制替代动作、其余窗口沿用 RF1。发生序号=我方座位 choose() 调用的
全局序号（与面板 decisions 行序一致）；分叉后轨迹自然分岔（他家对我弃牌的
响应不同属反事实的一部分）。每个分叉记录：命中校验（decision_id 对齐）、
四座终分、本座位分差。只读面板与冻结 RF1 源码；不改线上包。
"""
from __future__ import annotations

import argparse
import asyncio
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
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.interface import DecisionPlan, RankedCandidate, ScorePart
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine
from hangma_bot.simulation.artifacts import compute_rules_hash

RF1_SOURCE = (_ROOT / "prebuilt/vip-g37-rf1-compiled-v1/source.py").read_text(encoding="utf-8")
RULESET = "hangma-mvp-v10-public-counts"


class ForcerPolicy:
    """到目标出现序号前透传内层策略；命中时以合法候选构造强制计划。"""

    name = RouteVipHeuristicPolicy.name

    def __init__(self, inner, targets: dict[int, dict]) -> None:
        self.inner = inner
        self.targets = targets
        self.count = 0
        self.hits: list[dict] = []

    async def choose(self, request, budget):
        index = self.count
        self.count += 1
        plan = await self.inner.choose(request, budget)
        target = self.targets.get(index)
        if target is None:
            return plan
        forced_key = target["forced"]
        candidate = next((c for c in request.rules.legal_candidates
                          if c.action_key == forced_key), None)
        if candidate is None:
            self.hits.append({"occurrence": index, "decision_id": request.decision_id,
                              "status": "forced_key_not_legal"})
            return plan
        emergency_key = request.rules.emergency_candidate.action_key
        ranked = RankedCandidate(
            action=candidate.action, action_key=forced_key, rank=1, total_score=0.0,
            score_parts=(ScorePart(self.name, 0.0),),
            reasons=("counterfactual forced discard",),
            is_emergency=forced_key == emergency_key)
        self.hits.append({"occurrence": index, "decision_id": request.decision_id,
                          "status": "forced", "expected_decision_id": target["decision_id"],
                          "forced": forced_key, "natural": plan.candidates[0].action_key})
        return DecisionPlan(request.decision_id, request.window_key,
                            request.observation.snapshot_seq, 1, (ranked,), ())


def build(seeds_rounds=16):
    rules_config = RuleConfig(RULESET, 1, False)
    config = TournamentConfig(1, seeds_rounds, rules_config, TimingConfig(1, 1, 3))
    rules = HangmaRules(rules_config)
    engine = SimulationEngine(rules, rules_hash=compute_rules_hash(_ROOT))
    return rules_config, config, rules, engine


def run_match(seed, targets, rules_config, config, rules, engine):
    rf1 = RouteVipHeuristicPolicy(rules_config, source=RF1_SOURCE, max_operations=2_000_000)
    forcer = ForcerPolicy(rf1, targets)
    clock = lambda: 800.0  # noqa: E731
    opponents = tuple(ComparableHeuristicPolicyV2(weights=DEFAULT_WEIGHTS_V1, monotonic=clock)
                      for _ in range(3))
    spec = MatchSpec(match_id=f"panel-rf1-{seed}", scenario_id=f"seed-{seed}",
                     config=config, seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0))
    driver_config = MatchDriverConfig(clock_mode="logical", step_limit=200_000,
                                      budget_policy=BudgetPolicy(),
                                      competition_tournament_id="offline-counterfactual",
                                      strict_policy=True, route_limits=ValueAnalysisLimits())
    outcome = asyncio.run(drive_match(
        engine=engine, spec=spec, policies_by_seat=(forcer, *opponents),
        rules=rules, choice_factory=lambda key, action: SimulationChoice(key, action),
        config=driver_config, now_monotonic=clock, wall_clock=None,
        value_limits=ValueAnalysisLimits()))
    return outcome, forcer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default="artifacts/white-gap-step0/panel-rf1-001")
    parser.add_argument("--targets", required=True)
    parser.add_argument("--out", required=True, help="输出目录（须不存在）")
    parser.add_argument("--kind", choices=("core_selling", "control", "verify"), required=True)
    parser.add_argument("--limit", type=int, default=0, help="最多重放多少分叉，0=全部")
    args = parser.parse_args()

    summary = json.loads((Path(args.panel) / "PANEL-SUMMARY.json").read_text())
    baseline = {m["seed"]: m["final_scores"] for m in summary["matches"] if m["status"] == "complete"}
    targets_doc = json.loads(Path(args.targets).read_text())

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    rules_config, config, rules, engine = build()

    if args.kind == "verify":
        seed = 1101
        outcome, forcer = run_match(seed, {}, rules_config, config, rules, engine)
        match = {"seed": seed, "status": outcome.status,
                 "final_scores": list(outcome.final_scores or ()),
                 "baseline": baseline.get(seed),
                 "deterministic": list(outcome.final_scores or ()) == baseline.get(seed),
                 "choose_calls": forcer.count}
        (out / "VERIFY.json").write_text(json.dumps(match, ensure_ascii=False, indent=1))
        print(json.dumps(match, ensure_ascii=False))
        return

    forks = targets_doc["targets"][args.kind]
    if args.limit:
        forks = forks[:args.limit]
    by_seed = {}
    for fork in forks:
        by_seed.setdefault(fork["seed"], []).append(fork)

    results = []
    started = time.perf_counter()
    for seed, seed_forks in sorted(by_seed.items()):
        for fork in seed_forks:
            outcome, forcer = run_match(seed, {fork["occurrence"]: fork},
                                        rules_config, config, rules, engine)
            hit = forcer.hits[0] if forcer.hits else {"status": "no_hit"}
            aligned = (hit.get("status") == "forced"
                       and hit.get("expected_decision_id") == hit.get("decision_id"))
            base = baseline.get(seed)
            final = list(outcome.final_scores or ()) if outcome.final_scores else None
            delta = None if (final is None or base is None) else final[0] - base[0]
            results.append({**fork, "kind": args.kind, "status": outcome.status,
                            "hit_status": hit.get("status"), "decision_aligned": aligned,
                            "final_scores": final, "baseline": base, "delta_seat0": delta})
            print(json.dumps({"occ": fork["occurrence"], "seed": seed, "status": outcome.status,
                              "aligned": aligned, "delta": delta}, ensure_ascii=False), flush=True)
        (out / "forks.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in results))
    summary_out = {"kind": args.kind, "forks": len(results),
                   "completed": sum(1 for r in results if r["status"] == "complete"),
                   "aligned": sum(1 for r in results if r.get("decision_aligned")),
                   "wall_seconds": round(time.perf_counter() - started, 1)}
    deltas = [r["delta_seat0"] for r in results
              if r.get("decision_aligned") and r["delta_seat0"] is not None]
    if deltas:
        ordered = sorted(deltas)
        summary_out.update({"delta_mean": round(sum(deltas) / len(deltas), 3),
                            "delta_median": round(ordered[len(ordered) // 2], 3),
                            "delta_pos": sum(1 for d in deltas if d > 0),
                            "delta_neg": sum(1 for d in deltas if d < 0),
                            "delta_zero": sum(1 for d in deltas if d == 0),
                            "delta_min": ordered[0], "delta_max": ordered[-1]})
    (out / "SUMMARY.json").write_text(json.dumps(summary_out, ensure_ascii=False, indent=1))
    print(json.dumps(summary_out, ensure_ascii=False))


if __name__ == "__main__":
    main()
