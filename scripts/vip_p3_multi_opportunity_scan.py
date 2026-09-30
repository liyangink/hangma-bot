"""R18 自然路径的结果盲双白机会抽样，兼顾前驱和近端高番出口。

每自然单局最多留首次双白根与首次下一普通摸可四番根；二者重合
时只保留一个观察。选根不读取未来牌墙或他家暗牌，冻结首动作也只
消费当前 PlayerObservation、同源规则及已保存的离线研究模型。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.serialization import observation_to_json
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine

from scripts.vip_p3_anchored_value_probe import predict_observation
from scripts.vip_p3_payoff_frontier import extract_payoff_frontier


_SCENARIO_PREFIX = "vip-p3-multi-opportunity"
_LIMITS = ValueAnalysisLimits(max_expansions=8192)
_KNOWN_MODEL_GAP = "下一摸交换性近似缺完整精确公开未见容量"


def _opportunity(analysis, seat: int) -> dict | None:
    """以互斥摸牌码的四番以上准确支付量选一条近端规则见证。"""

    result = []
    for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots):
        if not isinstance(candidate.action, Discard):
            continue
        frontier = extract_payoff_frontier(candidate, root, seat)
        paths = [path for path in frontier.paths
                 if path.followup_discard is None and path.conditions.draw_kind == "normal"]
        if len(paths) > 1:
            raise ValueError("普通弃牌的一次本人摸牌存在重复路径")
        # 容量用于结果盲选根排序，必须逐码精确；未知不充作零或正概率。
        cells = [cell for path in paths for cell in path.cells
                 if cell.fan >= 4 and cell.capacity_exact_after_effect]
        if cells:
            result.append({
                "action_key": candidate.action_key,
                "high_fan_public_capacity": sum(cell.public_unseen_count for cell in cells),
                "high_fan_capacity_weighted_net": sum(
                    cell.public_unseen_count * cell.own_net for cell in cells),
                "highest_fan": max(cell.fan for cell in cells),
                "high_fan_code_count": len(cells),
            })
    return min(result, key=lambda row: (
        -row["high_fan_capacity_weighted_net"],
        -row["high_fan_public_capacity"], -row["highest_fan"], row["action_key"],
    )) if result else None


def scan(*, start_seed: int, seeds: int, model_path: Path,
         max_own_draw_index: int = 20) -> dict:
    """仅用行动前事实选择自然 R18 路径根并锁定比较首动作。"""

    if start_seed < 0 or seeds < 1 or max_own_draw_index < 1:
        raise ValueError("双白机会抽样范围无效")
    model_bytes = model_path.read_bytes()
    model = json.loads(model_bytes)
    if model.get("schema") != "vip-p3-anchored-payoff-probe/1":
        raise ValueError("机会抽样模型身份不符")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
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
        draw_index = 0
        first_two_white = None
        first_highfan = None
        for _ in range(500):
            frame = engine.frame(world)
            if frame.blocked_reason is not None:
                raise ValueError("R18 自然路径在双白扫描中阻塞")
            if frame.final_scores is not None:
                break
            for decision in frame.decisions:
                obs = decision.observation
                if (decision.window_key.seat != 0 or obs.phase != "draw"
                        or obs.drawn_tile is None):
                    continue
                draw_index += 1
                if draw_index > max_own_draw_index:
                    break
                counts["own_draw_windows"] += 1
                whites = sum(tile.code == "白" for tile in obs.my_hand + (obs.drawn_tile,))
                if whites < 2:
                    continue
                counts["two_white_windows"] += 1
                if first_two_white is not None and first_highfan is not None:
                    continue
                analysis = rules.analyze(obs, value_limits=_LIMITS, route_limits=_LIMITS)
                if (analysis.completeness is not RuleCompleteness.COMPLETE
                        or analysis.conditional_roots is None
                        or len(analysis.legal_candidates) != len(analysis.conditional_roots)
                        or any(root.gap_kind is not None for root in analysis.conditional_roots)):
                    raise ValueError("双白扫描遇到未闭合的正常机械或规则价值根")
                opportunity = _opportunity(analysis, obs.seat)
                if first_two_white is None or (opportunity is not None
                                               and first_highfan is None):
                    r18_action = choose_reference_action(rules, decision, mode="r18_frozen")
                    shape_action = choose_reference_action(rules, decision, mode="shape")
                    keys = {candidate.action: candidate.action_key
                            for candidate in analysis.legal_candidates}
                    try:
                        scores = predict_observation(obs, model)
                        anchored_gap = None
                    except ValueError as exc:
                        if str(exc) != _KNOWN_MODEL_GAP:
                            raise
                        scores = None
                        anchored_gap = str(exc)
                        counts["anchored_value_gap_windows"] += 1
                    if r18_action not in keys or shape_action not in keys:
                        raise ValueError("冻结参考者首选不属于本根合法动作")
                    row = {
                        "seed": seed, "root_id": hashlib.sha256(repr(obs).encode()).hexdigest(),
                        "own_draw_index": draw_index,
                        "white_count": whites, "wall_remaining": obs.remaining_tile_count,
                        "observation": observation_to_json(obs),
                        "legal_action_keys": [item.action_key for item in
                                              analysis.legal_candidates],
                        "r18_first_action_key": keys[r18_action],
                        "shape_first_action_key": keys[shape_action],
                        "anchored_first_action_key": (
                            scores[0]["action_key"] if scores is not None else None),
                        "anchored_first_score": scores[0] if scores is not None else None,
                        "anchored_value_gap": anchored_gap,
                        "highfan_witness": opportunity,
                    }
                    if first_two_white is None:
                        first_two_white = row
                    if opportunity is not None and first_highfan is None:
                        first_highfan = row
            if draw_index >= max_own_draw_index or (
                first_two_white is not None and first_highfan is not None
            ):
                break
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key,
                                 choose_reference_action(rules, item, mode="r18_frozen"))
                for item in frame.decisions
            ))
        else:
            raise ValueError("R18 双白机会扫描超过 500 帧")
        by_id = {}
        for tag, row in (("first_two_white", first_two_white),
                         ("first_highfan_witness", first_highfan)):
            if row is None:
                continue
            key = row["root_id"]
            by_id.setdefault(key, {**row, "tags": []})["tags"].append(tag)
            counts["selected_" + tag] += 1
        selected.extend(by_id.values())
    return {
        "scope": "pre_outcome_r18_natural_two_white_and_highfan_roots_not_strategy_result",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "reference": "r18_frozen", "scenario_prefix": _SCENARIO_PREFIX,
        "model_path": str(model_path),
        "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
        "start_seed": start_seed, "requested_seeds": seeds,
        "max_own_draw_index": max_own_draw_index,
        "counts": dict(sorted(counts.items())),
        "selected_roots": sorted(selected, key=lambda row: (
            row["seed"], row["own_draw_index"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--max-own-draw-index", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(scan(start_seed=args.start_seed, seeds=args.seeds,
                          model_path=args.model,
                          max_own_draw_index=args.max_own_draw_index),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
