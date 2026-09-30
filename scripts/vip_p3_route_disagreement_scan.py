"""结果盲发现“高番条件前沿优于 R18 首选”的新模拟根。

仅用行动前 PlayerObservation、同源规则条件胡和冻结 R18 评分选根；
不打开任何隐藏世界的动作结果。每个牌山种子至多留一根，按高番
公开容量差排序。公开未见容量不是实际牌墙概率，此脚本不选新策略。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine


def _route_capacity(root) -> tuple[int, int]:
    """返回下一普通摸可≥4番胡的公开容量与牌码数，非兑现概率。"""

    wins = [edge for edge in root.draw_edges
            if edge.immediate_win is not None
            and edge.immediate_win.settlement.fan >= 4]
    return sum(edge.support_capacity for edge in wins), len(wins)


def _one_observation(rules, scorer, limits, decision, *, seed: int, own_draw_index: int):
    """只读当前合法动作与规则前沿；有缺口则记录而不填零。"""

    observation = decision.observation
    analysis = rules.analyze(observation, route_limits=limits)
    frontier = analysis.route_frontier
    if frontier is None or frontier.top_level_gap is not None:
        return None, "frontier_top_gap"
    roots = {root.action_key: root for root in frontier.roots}
    discards = [item for item in analysis.legal_candidates
                if isinstance(item.action, Discard)]
    if not discards or any(roots[item.action_key].gap_kind is not None for item in discards):
        return None, "discard_root_gap"
    request = DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="vip-p3-disagreement-sim", stage_no=None,
            stage_role=None, stage_total=None, participant_rank=None,
            ranking=(), observed_at_unix_ms=0,
        ),
        rules=analysis, decision_id=f"vip-p3:{seed}:{own_draw_index}",
        trigger_seq=decision.window_key.trigger_seq,
        window_key=decision.window_key,
        rejected_attempts=(),
    )
    scored = scorer.score(build_scoring_view(request, value_limits=limits))
    if scored.status != "SCORED" or not scored.entries:
        return None, "r18_not_scored"
    parent = min(scored.entries, key=lambda item: (-item.score, item.action_key))
    capacity_by_key = {
        item.action_key: _route_capacity(roots[item.action_key])
        for item in discards
    }
    parent_capacity = capacity_by_key.get(parent.action_key, (0, 0))[0]
    best_key = min(capacity_by_key,
                   key=lambda key: (-capacity_by_key[key][0],
                                    -capacity_by_key[key][1], key))
    best_capacity, best_codes = capacity_by_key[best_key]
    if best_key == parent.action_key or best_capacity <= parent_capacity:
        return None, "no_high_fan_capacity_advantage"
    parent_score = parent.score
    best_score = next(item.score for item in scored.entries
                      if item.action_key == best_key)
    return {
        "seed": seed,
        "own_draw_index": own_draw_index,
        "observation_sha256": hashlib.sha256(repr(observation).encode("utf-8")).hexdigest(),
        "wall_remaining": observation.remaining_tile_count,
        "white_count": sum(tile.code == "白" for tile in
                           observation.my_hand + ((observation.drawn_tile,)
                           if observation.drawn_tile is not None else ())),
        "r18_top_action": parent.action_key,
        "r18_top_score": parent_score,
        "r18_top_high_fan_capacity": parent_capacity,
        "route_alternative": best_key,
        "route_alternative_r18_score": best_score,
        "route_alternative_high_fan_capacity": best_capacity,
        "route_alternative_high_fan_codes": best_codes,
        "capacity_gap": best_capacity - parent_capacity,
    }, None


def scan(*, start_seed: int, seeds: int, max_own_draw_index: int = 15) -> dict:
    """先冻结选择再看结果；每种子留容量差最大的一个行动前根。"""

    if start_seed < 0 or seeds < 1 or max_own_draw_index < 1:
        raise ValueError("扫描种子或本人摸牌窗口上限无效")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    limits = ValueAnalysisLimits(max_expansions=8192)
    scorer = ActionValueScorer("vip-p3-r18-disagreement-reference",
                               R18_INTEGRATED_POSITIVE_V2_SOURCE)
    counts: Counter[str] = Counter()
    selected = []
    for seed in range(start_seed, start_seed + seeds):
        spec = MatchSpec(
            match_id=f"vip-p3-scan-{seed}", scenario_id=f"vip-p3-scan-{seed}",
            config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
            seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0),
        )
        world = engine.start(spec)
        candidates = []
        own_draw_index = 0
        for _ in range(500):
            frame = engine.frame(world)
            if frame.blocked_reason is not None:
                raise ValueError(f"种子 {seed} 模拟器阻塞: {frame.blocked_reason}")
            if frame.final_scores is not None:
                break
            for decision in frame.decisions:
                if (decision.window_key.seat != 0
                        or decision.observation.phase != "draw"):
                    continue
                own_draw_index += 1
                if own_draw_index > max_own_draw_index:
                    break
                counts["scanned_own_draw_windows"] += 1
                candidate, reason = _one_observation(
                    rules, scorer, limits, decision,
                    seed=seed, own_draw_index=own_draw_index)
                if candidate is not None:
                    candidates.append(candidate)
                    counts["eligible_windows"] += 1
                else:
                    counts[reason] += 1
            if own_draw_index >= max_own_draw_index:
                break
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key,
                                 choose_reference_action(rules, item, mode="shape"))
                for item in frame.decisions
            ))
        else:
            raise ValueError(f"种子 {seed} 超过 500 帧")
        if candidates:
            selected.append(min(candidates,
                                key=lambda item: (-item["capacity_gap"],
                                                 -item["route_alternative_high_fan_capacity"],
                                                 item["own_draw_index"],
                                                 item["route_alternative"])))
    return {
        "scope": "result_blind_P1_next_draw_high_fan_capacity_disagreement_only",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "reference": "shape",
        "r18_source_sha256": hashlib.sha256(
            R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest(),
        "start_seed": start_seed, "requested_seeds": seeds,
        "max_own_draw_index": max_own_draw_index,
        "counts": dict(sorted(counts.items())),
        "selected_roots": sorted(selected, key=lambda item: item["seed"]),
    }


def main() -> None:
    """仅输出行动前选根结果；不访问分支终局。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=601)
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--max-own-draw-index", type=int, default=15)
    args = parser.parse_args()
    print(json.dumps(scan(start_seed=args.start_seed, seeds=args.seeds,
                          max_own_draw_index=args.max_own_draw_index),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
