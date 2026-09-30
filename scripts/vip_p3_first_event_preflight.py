"""P3 首次竞争事件的同观察、同隐藏世界多动作预检。

只在离线模拟器持有 WorldState；选窗和弃牌臂在结果揭晓前固定。
第一次本人再获有选择的动作窗口或他座先胡/流局恰落一个互斥类别。
只有 Pass 的响应窗口是中间公开转移，不占首次决策事件质量。
此脚本不估计线上概率，不拟合价值模型，也不宣称算法改进。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard, Hu, Pass
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine


def _first_event(engine: SimulationEngine, rules: HangmaRules, world, *,
                 seat: int, reference: str) -> dict:
    """按冻结参考者续打，仅返回首次本人行动机会或公开终局。"""

    for _ in range(500):
        frame = engine.frame(world)
        if frame.blocked_reason is not None:
            raise ValueError("参考续打被模拟器阻塞: " + frame.blocked_reason)
        if frame.final_scores is not None:
            result = world.progression.hand_result
            if result is None or sum(result.score_delta) != 0:
                raise ValueError("首次事件终局缺守恒的四座结算")
            return {
                "kind": "draw" if result.is_draw else "other_win",
                "winner_seat": result.winner_seat,
                "score_delta": list(result.score_delta),
            }
        mine = [item for item in frame.decisions if item.window_key.seat == seat]
        if mine:
            if len(mine) != 1:
                raise ValueError("同一帧本人行动窗口重复")
            observation = mine[0].observation
            if observation.phase == "draw":
                if observation.drawn_tile is None:
                    raise ValueError("本人自摸机会缺已摸牌")
                analysis = rules.analyze(
                    observation, value_limits=ValueAnalysisLimits(max_expansions=8192))
                win = next((item for item in analysis.legal_candidates
                            if isinstance(item.action, Hu)), None)
                settlement = (win.value_facts.immediate_settlement
                              if win is not None and win.value_facts is not None else None)
                if win is not None and settlement is None:
                    raise ValueError("给定本人摸牌合法胡缺同次四座结算")
                if settlement is not None and (
                    len(settlement.score_delta) != 4
                    or sum(settlement.score_delta) != 0
                    or settlement.fan < 1
                ):
                    raise ValueError("给定本人摸牌结算的四座积分或番数无效")
                return {
                    "kind": ("self_replacement_draw" if observation.gang_draw
                             else "self_normal_draw"),
                    "tile": observation.drawn_tile.code,
                    "immediate_hu": (
                        None if settlement is None else {
                            "fan": settlement.fan,
                            "score_delta": list(settlement.score_delta),
                        }),
                }
            if observation.phase not in ("response_peng", "response_chi"):
                raise ValueError("未知本人窗口")
            if any(not isinstance(item.action, Pass) for item in
                   rules.analyze(observation).legal_candidates):
                if observation.last_discard is None:
                    raise ValueError("可行动响应缺触发弃牌")
                return {"kind": "self_actionable_response", "window": observation.phase,
                        "tile": observation.last_discard.tile.code}
        world = engine.advance(world, frame.revision, tuple(
            SimulationChoice(item.window_key,
                             choose_reference_action(rules, item, mode=reference))
            for item in frame.decisions
        ))
    raise ValueError("首次事件续打超过 500 帧")


def _finish_hand(engine: SimulationEngine, rules: HangmaRules, world, *,
                 reference: str) -> dict:
    """同一冻结续打者走完当前单局，返回真实规则结算。"""

    for _ in range(500):
        frame = engine.frame(world)
        if frame.blocked_reason is not None:
            raise ValueError("完整单局参考续打阻塞: " + frame.blocked_reason)
        if frame.final_scores is not None:
            result = world.progression.hand_result
            if result is None or len(result.score_delta) != 4 or sum(result.score_delta) != 0:
                raise ValueError("完整单局终局缺守恒的四座结算")
            return {"winner_seat": result.winner_seat,
                    "is_draw": result.is_draw, "fan": result.fan,
                    "score_delta": list(result.score_delta)}
        world = engine.advance(world, frame.revision, tuple(
            SimulationChoice(item.window_key,
                             choose_reference_action(rules, item, mode=reference))
            for item in frame.decisions
        ))
    raise ValueError("完整单局续打超过 500 帧")


def _arms(rules: HangmaRules, observation) -> tuple:
    """结果盲地取规范排序首、中、尾三种非白合法弃牌。"""

    discards = sorted(
        (item for item in rules.analyze(observation).legal_candidates
         if isinstance(item.action, Discard) and item.action.tile.code != "白"),
        key=lambda item: item.action_key,
    )
    if len(discards) < 2:
        raise ValueError("预检根缺至少两种非白弃牌")
    indexes = (0, len(discards) // 2, len(discards) - 1)
    return tuple(discards[index] for index in dict.fromkeys(indexes))


def _event_key(event: dict) -> str:
    """互斥事件包含摸入/响应牌码；资格标签不另加概率质量。"""

    kind = event["kind"]
    if kind in ("self_normal_draw", "self_replacement_draw"):
        return kind + ":" + event["tile"]
    if kind == "self_actionable_response":
        return kind + ":" + event["window"] + ":" + event["tile"]
    if kind == "other_win":
        return kind + ":" + str(event["winner_seat"])
    if kind == "draw":
        return kind
    raise ValueError("未知竞争事件类别")


def _target_root(engine: SimulationEngine, rules: HangmaRules, world, *,
                 own_draw_index: int, reference: str):
    """只依靠冻结参考者走到第 N 个本座摸牌窗口，不按结果筛窗。"""

    seen = 0
    for _ in range(500):
        frame = engine.frame(world)
        if frame.blocked_reason is not None:
            raise ValueError("目标本人摸牌窗口前模拟单局阻塞")
        if frame.final_scores is not None:
            return None
        for decision in frame.decisions:
            if decision.window_key.seat == 0 and decision.observation.phase == "draw":
                seen += 1
                if seen == own_draw_index:
                    return world, frame, decision
        world = engine.advance(world, frame.revision, tuple(
            SimulationChoice(item.window_key,
                             choose_reference_action(rules, item, mode=reference))
            for item in frame.decisions
        ))
    raise ValueError("目标本人摸牌窗口未在 500 帧内出现")


def audit(*, start_seed: int, seeds: int, worlds_per_root: int,
          own_draw_index: int = 6, full_tail: bool = False,
          reference: str = "first_discard") -> dict:
    """按牌山种子分组，保持同根多动作共享每个隐藏世界。"""

    if start_seed < 0 or seeds < 1 or worlds_per_root < 1 or own_draw_index < 1:
        raise ValueError("预检样本范围无效")
    if reference not in ("first_discard", "shape"):
        raise ValueError("未知参考续打者")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    histogram: Counter[str] = Counter()
    event_keys: Counter[str] = Counter()
    paired: Counter[str] = Counter()
    paired_hu: Counter[str] = Counter()
    paired_tail: Counter[str] = Counter()
    immediate_hu = 0
    roots = []
    skipped: list[dict] = []
    for seed in range(start_seed, start_seed + seeds):
        spec = MatchSpec(
            match_id=f"vip-p3-event-{seed}",
            scenario_id=f"vip-p3-event-{seed}",
            config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
            seed=seed,
            initial_dealer=0,
            initial_scores=(0, 0, 0, 0),
        )
        target = _target_root(
            engine, rules, engine.start(spec), own_draw_index=own_draw_index,
            reference=reference)
        if target is None:
            skipped.append({"seed": seed, "reason": "ended_before_target_draw"})
            continue
        root, frame, decision = target
        observation = decision.observation
        try:
            arms = _arms(rules, observation)
        except ValueError as exc:
            skipped.append({"seed": seed, "reason": str(exc)})
            continue
        root_id = hashlib.sha256(repr(observation).encode("utf-8")).hexdigest()
        group = {item.action_key: Counter() for item in arms}
        group_hu = {item.action_key: Counter() for item in arms}
        group_hu_points = {item.action_key: 0 for item in arms}
        group_tail_points = {item.action_key: 0 for item in arms}
        group_tail_high = {item.action_key: 0 for item in arms}
        for sample in range(worlds_per_root):
            hidden = engine.resample_public_consistent_hidden_world(
                root, focal_seat=0, sample_key=f"vip-p3-first-event-{sample}",
            )
            if engine.frame(hidden).decisions[0].observation != observation:
                raise ValueError("重采样改变本人依法可见观察")
            outcomes = {}
            tail_points = {}
            for arm in arms:
                after = engine.advance(hidden, frame.revision, (
                    SimulationChoice(decision.window_key, arm.action),
                ))
                event = _first_event(engine, rules, after, seat=0,
                                     reference=reference)
                kind = event["kind"]
                key = _event_key(event)
                histogram[kind] += 1
                event_keys[key] += 1
                group[arm.action_key][key] += 1
                if event.get("immediate_hu") is not None:
                    immediate_hu += 1
                    group_hu[arm.action_key][str(event["immediate_hu"]["fan"])] += 1
                    group_hu_points[arm.action_key] += event["immediate_hu"]["score_delta"][0]
                outcomes[arm.action_key] = event
                if full_tail:
                    terminal = _finish_hand(engine, rules, after,
                                            reference=reference)
                    points = terminal["score_delta"][0]
                    group_tail_points[arm.action_key] += points
                    group_tail_high[arm.action_key] += (
                        terminal["winner_seat"] == 0 and terminal["fan"] >= 4)
                    tail_points[arm.action_key] = points
            baseline_event = outcomes[arms[0].action_key]
            baseline = _event_key(baseline_event)
            for arm in arms[1:]:
                other = outcomes[arm.action_key]
                paired[baseline + "->" + _event_key(other)] += 1
                paired_hu[("hu" if baseline_event.get("immediate_hu") else "no_hu")
                          + "->" + ("hu" if other.get("immediate_hu") else "no_hu")] += 1
                if full_tail:
                    delta = tail_points[arm.action_key] - tail_points[arms[0].action_key]
                    paired_tail["positive" if delta > 0 else
                                "negative" if delta < 0 else "zero"] += 1
        if any(sum(counts.values()) != worlds_per_root for counts in group.values()):
            raise ValueError("同根动作的首次事件质量不守恒")
        roots.append({
            "seed": seed, "observation_sha256": root_id,
            "arms": [item.action_key for item in arms],
            "event_counts_by_arm": {key: dict(sorted(value.items()))
                                    for key, value in group.items()},
            "immediate_hu_fan_counts_by_arm": {
                key: dict(sorted(value.items())) for key, value in group_hu.items()},
            "immediate_hu_net_points_by_arm": group_hu_points,
            **({"full_hand_net_points_by_arm": group_tail_points,
                "full_hand_self_high_counts_by_arm": group_tail_high}
               if full_tail else {}),
        })
    expected = sum(len(item["arms"]) for item in roots) * worlds_per_root
    if sum(histogram.values()) != expected or sum(paired.values()) != sum(
        len(item["arms"]) - 1 for item in roots) * worlds_per_root:
        raise ValueError("互斥事件或相关世界配对计数不守恒")
    return {
        "scope": "P3_first_event_preflight_only_no_probability_model_or_strength",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "start_seed": start_seed, "requested_seeds": seeds,
        "reached_roots": len(roots), "skipped_roots": skipped,
        "worlds_per_root": worlds_per_root,
        "own_draw_index": own_draw_index,
        "full_tail": full_tail,
        "reference": reference,
        "action_worlds": expected,
        "event_counts": dict(sorted(histogram.items())),
        "event_key_counts": dict(sorted(event_keys.items())),
        "immediate_hu_action_worlds": immediate_hu,
        "paired_immediate_hu": dict(sorted(paired_hu.items())),
        "paired_full_hand_delta_sign": dict(sorted(paired_tail.items())),
        "paired_event_changes": dict(sorted(paired.items())),
        "root_groups": roots,
    }


def main() -> None:
    """打印完整分母与每根事件质量，供新根预检复算。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=301)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--worlds-per-root", type=int, default=4)
    parser.add_argument("--own-draw-index", type=int, default=6)
    parser.add_argument("--full-tail", action="store_true")
    parser.add_argument("--reference", choices=("first_discard", "shape"),
                        default="first_discard")
    args = parser.parse_args()
    print(json.dumps(audit(
        start_seed=args.start_seed, seeds=args.seeds,
        worlds_per_root=args.worlds_per_root,
        own_draw_index=args.own_draw_index,
        full_tail=args.full_tail,
        reference=args.reference,
    ), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
