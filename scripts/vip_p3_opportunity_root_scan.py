"""P3 结果盲机会根扫描：高番条件见证、双白与较晚本人摸牌窗。

只读取 `shape` 自然续打到达的 PlayerObservation 和同次规则前沿。
公开未见容量是物理上限，不是牌墙概率；扫描不打开隐藏世界分支结果。
每个自然牌山种子按预注册标签最多留三根，稀有层不代表自然频率。
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
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine


def _opportunity(rules: HangmaRules, observation, limits: ValueAnalysisLimits):
    """同次弃牌前沿的下一普通摸 ≥4 番公开容量，不按牌型重复计码。"""

    analysis = rules.analyze(observation, route_limits=limits)
    frontier = analysis.route_frontier
    if (analysis.completeness is not RuleCompleteness.COMPLETE or frontier is None
            or frontier.top_level_gap is not None):
        return None, "analysis_gap"
    by_key = {root.action_key: root for root in frontier.roots}
    best = None
    for candidate in analysis.legal_candidates:
        if not isinstance(candidate.action, Discard):
            continue
        root = by_key.get(candidate.action_key)
        if root is None or root.gap_kind is not None:
            return None, "discard_root_gap"
        high_edges = tuple(edge for edge in root.draw_edges
                           if edge.immediate_win is not None
                           and edge.immediate_win.settlement.fan >= 4)
        capacity = sum(edge.support_capacity for edge in high_edges)
        row = {
            "action_key": candidate.action_key,
            "high_fan_capacity": capacity,
            "high_fan_codes": len(high_edges),
            "highest_witnessed_fan": max(
                (edge.immediate_win.settlement.fan for edge in high_edges),
                default=0),
        }
        if best is None or (
            -capacity, -row["highest_witnessed_fan"], -row["high_fan_codes"],
            candidate.action_key,
        ) < (
            -best["high_fan_capacity"], -best["highest_witnessed_fan"],
            -best["high_fan_codes"], best["action_key"],
        ):
            best = row
    return best, None if best is not None else "no_discard"


def scan(*, start_seed: int, seeds: int, max_own_draw_index: int = 20,
         late_draw_index: int = 14) -> dict:
    """按自然路径行动前事实取每种子最多一个最高高番根及两个固定层。"""

    if (start_seed < 0 or seeds < 1 or max_own_draw_index < 1
            or not 1 <= late_draw_index <= max_own_draw_index):
        raise ValueError("扫描种子或本人摸牌窗口范围无效")
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
        candidates = []
        draw_index = 0
        for _ in range(500):
            frame = engine.frame(world)
            if frame.blocked_reason is not None:
                raise ValueError("机会扫描模拟器阻塞: " + frame.blocked_reason)
            if frame.final_scores is not None:
                break
            for decision in frame.decisions:
                obs = decision.observation
                if decision.window_key.seat != 0 or obs.phase != "draw":
                    continue
                if obs.drawn_tile is None:
                    continue  # 吃碰后跟打不是本人普通摸牌序号
                draw_index += 1
                if draw_index > max_own_draw_index:
                    break
                counts["scanned_own_draw_windows"] += 1
                best, reason = _opportunity(rules, obs, limits)
                if best is None:
                    counts[reason] += 1
                    continue
                white_count = sum(tile.code == "白" for tile in
                                  obs.my_hand + (obs.drawn_tile,))
                row = {
                    "seed": seed,
                    "own_draw_index": draw_index,
                    "observation_sha256": hashlib.sha256(
                        repr(obs).encode("utf-8")).hexdigest(),
                    "wall_remaining": obs.remaining_tile_count,
                    "white_count": white_count,
                    **best,
                }
                candidates.append(row)
                counts["analyzed_own_draw_windows"] += 1
            if draw_index >= max_own_draw_index:
                break
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key,
                                 choose_reference_action(rules, item, mode="shape"))
                for item in frame.decisions
            ))
        else:
            raise ValueError("机会扫描超过 500 帧")
        tagged = []
        high = [row for row in candidates if row["high_fan_capacity"] > 0]
        if high:
            chosen = min(high, key=lambda row: (
                -row["high_fan_capacity"], -row["highest_witnessed_fan"],
                row["own_draw_index"], row["action_key"]))
            tagged.append(("high_fan_witness", chosen))
        white = [row for row in candidates if row["white_count"] >= 2]
        if white:
            tagged.append(("first_two_white", white[0]))
        late = next((row for row in candidates
                     if row["own_draw_index"] == late_draw_index), None)
        if late is not None:
            tagged.append(("late_draw", late))
        by_id = {}
        for tag, row in tagged:
            key = row["observation_sha256"]
            if key not in by_id:
                by_id[key] = {**row, "tags": []}
            by_id[key]["tags"].append(tag)
            counts["selected_" + tag] += 1
        selected.extend(by_id.values())
    return {
        "scope": "result_blind_opportunity_root_selection_not_outcome_or_probability",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "reference": "shape",
        "start_seed": start_seed, "requested_seeds": seeds,
        "max_own_draw_index": max_own_draw_index,
        "late_draw_index": late_draw_index,
        "counts": dict(sorted(counts.items())),
        "selected_roots": sorted(selected,
                                 key=lambda row: (row["seed"], row["own_draw_index"])),
    }


def main() -> None:
    """打印行动前选择依据；不运行反事实分支。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=1201)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--max-own-draw-index", type=int, default=20)
    parser.add_argument("--late-draw-index", type=int, default=14)
    args = parser.parse_args()
    print(json.dumps(scan(
        start_seed=args.start_seed, seeds=args.seeds,
        max_own_draw_index=args.max_own_draw_index,
        late_draw_index=args.late_draw_index,
    ), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
