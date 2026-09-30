"""P3 当前低番胡／继续的结果盲根扫描。

沿冻结 shape 自然路径，每自然牌山种子至多留首次本人普通摸牌
可低于四番胡且仍有合法弃牌的窗口。只读行动前玩家可见状态和
同源即时结算，不根据后续赢家、牌墙或反事实收益选根。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard, Hu
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine


def scan(*, start_seed: int, seeds: int,
         max_own_draw_index: int = 20) -> dict:
    """按行动前低番胡资格取根；首次未命中种子仍计入抽样框。"""

    if start_seed < 0 or seeds < 1 or max_own_draw_index < 1:
        raise ValueError("低番胡扫描种子或窗口上限无效")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    limits = ValueAnalysisLimits(max_expansions=8192)
    counts: Counter[str] = Counter()
    selected = []
    for seed in range(start_seed, start_seed + seeds):
        spec = MatchSpec(
            match_id=f"vip-p3-opportunity-{seed}",
            scenario_id=f"vip-p3-opportunity-{seed}",
            config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
            seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0),
        )
        world = engine.start(spec)
        own_draw_index = 0
        found = False
        for _ in range(500):
            frame = engine.frame(world)
            if frame.blocked_reason is not None:
                raise ValueError("低番胡选根前模拟器阻塞: " + frame.blocked_reason)
            if frame.final_scores is not None:
                break
            for decision in frame.decisions:
                observation = decision.observation
                if (decision.window_key.seat != 0 or observation.phase != "draw"
                        or observation.drawn_tile is None):
                    continue
                own_draw_index += 1
                if own_draw_index > max_own_draw_index:
                    break
                counts["scanned_own_draw_windows"] += 1
                analysis = rules.analyze(observation, value_limits=limits)
                if analysis.completeness is not RuleCompleteness.COMPLETE:
                    raise ValueError("行动前规则分析退化，不能静默丢根")
                win = next((item for item in analysis.legal_candidates
                            if isinstance(item.action, Hu)), None)
                if win is None:
                    continue
                counts["current_hu_windows"] += 1
                settlement = (win.value_facts.immediate_settlement
                              if win.value_facts is not None else None)
                if settlement is None:
                    raise ValueError("行动前合法胡缺精确规则结算")
                if settlement.fan >= 4 or not any(
                    isinstance(item.action, Discard)
                    for item in analysis.legal_candidates
                ):
                    counts["excluded_high_fan_or_no_continue"] += 1
                    continue
                whites = sum(tile.code == "白" for tile in
                             observation.my_hand + (observation.drawn_tile,))
                tags = ["first_low_fan_hu"]
                if whites >= 2:
                    tags.append("two_white_low_fan_hu")
                selected.append({
                    "seed": seed, "own_draw_index": own_draw_index,
                    "observation_sha256": hashlib.sha256(
                        repr(observation).encode("utf-8")).hexdigest(),
                    "wall_remaining": observation.remaining_tile_count,
                    "white_count": whites, "current_hu_fan": settlement.fan,
                    "current_hu_net": settlement.score_delta[observation.seat],
                    "legal_action_count": len(analysis.legal_candidates),
                    "tags": tags,
                })
                counts["selected_first_low_fan_hu"] += 1
                if whites >= 2:
                    counts["selected_two_white_low_fan_hu"] += 1
                found = True
                break
            if found or own_draw_index >= max_own_draw_index:
                break
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key,
                                 choose_reference_action(rules, item, mode="shape"))
                for item in frame.decisions
            ))
        else:
            raise ValueError("低番胡选根续打超过 500 帧")
        counts["seed_selected" if found else "seed_no_eligible_window"] += 1
    return {
        "scope": "result_blind_opportunity_root_selection_not_outcome_or_probability",
        "selection_method": "first_low_fan_hu_under_shape_per_seed",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "reference": "shape", "start_seed": start_seed,
        "requested_seeds": seeds,
        "max_own_draw_index": max_own_draw_index,
        "counts": dict(sorted(counts.items())),
        "selected_roots": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=2201)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--max-own-draw-index", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(scan(
        start_seed=args.start_seed, seeds=args.seeds,
        max_own_draw_index=args.max_own_draw_index,
    ), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
