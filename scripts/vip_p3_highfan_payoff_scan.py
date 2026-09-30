"""自然牌山结果盲扫描：寻找下一摸可达 ≥8 番的规则支付锚点。

选择只用当前 PlayerObservation 和 HangmaRules 事实；完整 WorldState
仅驱动冻结参考者到达窗口，不读取未来牌墙决定留根。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.serialization import observation_to_json
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine

from scripts.vip_p3_payoff_frontier import extract_payoff_frontier


_SCENARIO_PREFIX = "vip-p3-highfan-payoff"


def scan(*, start_seed: int, seeds: int, reference: str = "shape",
         minimum_fan: int = 8, max_own_draw_index: int = 20) -> dict:
    """每自然种子留首次高番支付根；只扫描至少两张实持白板的本人摸牌窗。"""

    if (start_seed < 0 or seeds < 1 or reference not in (
            "shape", "shape_white_hold", "r18_frozen")
            or minimum_fan < 4 or max_own_draw_index < 1):
        raise ValueError("高番支付扫描参数无效")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    limits = ValueAnalysisLimits(max_expansions=8192)
    counts: Counter[str] = Counter()
    selected = []
    for seed in range(start_seed, start_seed + seeds):
        spec = MatchSpec(
            match_id=f"{_SCENARIO_PREFIX}-{seed}",
            scenario_id=f"{_SCENARIO_PREFIX}-{seed}",
            config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
            seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0),
        )
        world = engine.start(spec)
        own_draw_index = 0
        found = False
        for _ in range(500):
            frame = engine.frame(world)
            if frame.blocked_reason is not None:
                raise ValueError("高番支付扫描模拟器阻塞: " + frame.blocked_reason)
            if frame.final_scores is not None:
                break
            for decision in frame.decisions:
                obs = decision.observation
                if (decision.window_key.seat != 0 or obs.phase != "draw"
                        or obs.drawn_tile is None):
                    continue
                own_draw_index += 1
                if own_draw_index > max_own_draw_index:
                    break
                counts["own_draw_windows"] += 1
                whites = sum(tile.code == "白" for tile in
                             obs.my_hand + (obs.drawn_tile,))
                if whites < 2:
                    continue
                counts["at_least_two_white_windows"] += 1
                analysis = rules.analyze(obs, value_limits=limits, route_limits=limits)
                if (analysis.completeness is not RuleCompleteness.COMPLETE
                        or analysis.conditional_roots is None
                        or len(analysis.conditional_roots) != len(analysis.legal_candidates)):
                    counts["analysis_gap"] += 1
                    continue
                opportunities = []
                try:
                    for candidate, root in zip(analysis.legal_candidates,
                                               analysis.conditional_roots):
                        if not isinstance(candidate.action, Discard):
                            continue
                        frontier = extract_payoff_frontier(candidate, root, obs.seat)
                        cells = [cell for path in frontier.paths for cell in path.cells
                                 if cell.fan >= minimum_fan]
                        if cells:
                            opportunities.append({
                                "action_key": candidate.action_key,
                                "highest_fan": max(cell.fan for cell in cells),
                                "highest_own_net": max(cell.own_net for cell in cells),
                                "high_fan_codes": len(cells),
                                "high_fan_public_capacity": sum(
                                    cell.public_unseen_count for cell in cells),
                            })
                except ValueError:
                    counts["payoff_evidence_gap"] += 1
                    continue
                counts["analyzed_white_windows"] += 1
                if not opportunities:
                    continue
                root_id = hashlib.sha256(repr(obs).encode("utf-8")).hexdigest()
                selected.append({
                    "seed": seed, "root_id": root_id,
                    "own_draw_index": own_draw_index,
                    "white_count": whites,
                    "wall_remaining": obs.remaining_tile_count,
                    "observation": observation_to_json(obs),
                    "legal_action_keys": [candidate.action_key
                                          for candidate in analysis.legal_candidates],
                    "opportunities": sorted(opportunities, key=lambda row: row["action_key"]),
                })
                counts["selected_roots"] += 1
                found = True
                break
            if found or own_draw_index >= max_own_draw_index:
                break
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key,
                                 choose_reference_action(rules, item, mode=reference))
                for item in frame.decisions
            ))
        else:
            raise ValueError("高番支付扫描超过 500 帧")
    return {
        "scope": "pre_outcome_highfan_payoff_selection_not_outcome_or_probability",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "reference": reference,
        "scenario_prefix": _SCENARIO_PREFIX,
        "minimum_fan": minimum_fan,
        "max_own_draw_index": max_own_draw_index,
        "start_seed": start_seed, "requested_seeds": seeds,
        "counts": dict(sorted(counts.items())),
        "selected_roots": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, required=True)
    parser.add_argument("--reference", choices=("shape", "shape_white_hold", "r18_frozen"),
                        default="shape")
    parser.add_argument("--minimum-fan", type=int, default=8)
    parser.add_argument("--max-own-draw-index", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(scan(
        start_seed=args.start_seed, seeds=args.seeds, reference=args.reference,
        minimum_fan=args.minimum_fan, max_own_draw_index=args.max_own_draw_index,
    ), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
