"""按已提交冻结点打开单根双动作、双续打的相关隐藏世界结局。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine

from scripts.vip_p3_competing_tail_audit import _label
from scripts.vip_p3_first_event_preflight import _event_key, _finish_hand, _first_event


def _selected_world(engine, rules, frozen: dict, observation):
    """按冻结路径重建行动前世界，但只用本人观察核选根身份。"""

    seed = frozen["seed"]
    prefix = frozen["scenario_prefix"]
    spec = MatchSpec(
        match_id=f"{prefix}-{seed}", scenario_id=f"{prefix}-{seed}",
        config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
        seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0),
    )
    world = engine.start(spec)
    own_draw_index = 0
    for _ in range(500):
        frame = engine.frame(world)
        if frame.blocked_reason is not None or frame.final_scores is not None:
            raise ValueError("冻结高番根之前单局结束或模拟器阻塞")
        for decision in frame.decisions:
            if (decision.window_key.seat == frozen["focal_seat"]
                    and decision.observation.phase == "draw"
                    and decision.observation.drawn_tile is not None):
                own_draw_index += 1
                if own_draw_index == frozen["own_draw_index"]:
                    if decision.observation != observation:
                        raise ValueError("冻结高番根观察与复建参考路径不同")
                    return world, frame, decision
        world = engine.advance(world, frame.revision, tuple(
            SimulationChoice(item.window_key, choose_reference_action(
                rules, item, mode=frozen["selection_reference"]))
            for item in frame.decisions
        ))
    raise ValueError("冻结高番根 500 帧内未到达")


def audit(frozen: dict) -> dict:
    """完整验证冻结来源后才打开结局；未来只进教师标签。"""

    if (frozen.get("scope") !=
            "pre_outcome_single_root_rule_payoff_probe_not_strategy_confirmation"
            or frozen.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}
            or frozen.get("forced_first_actions") != ["hu", "discard:6w"]
            or frozen.get("continuation_references") != ["shape", "r18_frozen"]
            or frozen.get("worlds_per_root") != 64):
        raise ValueError("高番探针冻结合同不符")
    selection_path = Path(frozen["selection_report"])
    if hashlib.sha256(selection_path.read_bytes()).hexdigest() != frozen[
        "selection_report_sha256"
    ]:
        raise ValueError("结果盲选根来源摘要漂移")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if (selection.get("scope") !=
            "pre_outcome_highfan_payoff_selection_not_outcome_or_probability"
            or selection.get("reference") != frozen["selection_reference"]
            or selection.get("scenario_prefix") != frozen["scenario_prefix"]):
        raise ValueError("冻结根选择来源不符")
    selected = [row for row in selection["selected_roots"]
                if row["seed"] == frozen["seed"]]
    if (len(selected) != 1 or selected[0]["root_id"] != frozen["root_id"]
            or selected[0]["own_draw_index"] != frozen["own_draw_index"]):
        raise ValueError("冻结观察根身份与扫描不一致")
    observation = observation_from_json(selected[0]["observation"])
    if hashlib.sha256(repr(observation).encode()).hexdigest() != frozen["root_id"]:
        raise ValueError("冻结玩家观察摘要不一致")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    world, frame, decision = _selected_world(engine, rules, frozen, observation)
    analysis = rules.analyze(observation)
    actions = {candidate.action_key: candidate.action for candidate in analysis.legal_candidates}
    if (analysis.completeness is not RuleCompleteness.COMPLETE
            or list(actions) != selected[0]["legal_action_keys"]
            or any(key not in actions for key in frozen["forced_first_actions"])):
        raise ValueError("冻结强制首动作不属于同根规则合法动作")
    rows = []
    for sample in range(frozen["worlds_per_root"]):
        hidden = engine.resample_public_consistent_hidden_world(
            world, focal_seat=frozen["focal_seat"],
            sample_key=f"{frozen['resample_key_prefix']}-{sample}",
        )
        sampled_frame = engine.frame(hidden)
        focal = [item for item in sampled_frame.decisions
                 if item.window_key == decision.window_key]
        if len(focal) != 1 or focal[0].observation != observation:
            raise ValueError("相关隐藏世界改变冻结本座玩家观察或窗口")
        for key in frozen["forced_first_actions"]:
            choices = tuple(SimulationChoice(
                item.window_key,
                actions[key] if item.window_key == decision.window_key else
                choose_reference_action(rules, item, mode=frozen["selection_reference"]),
            ) for item in sampled_frame.decisions)
            after = engine.advance(hidden, sampled_frame.revision, choices)
            for reference in frozen["continuation_references"]:
                event = _first_event(
                    engine, rules, after, seat=frozen["focal_seat"],
                    reference=reference)
                terminal = _finish_hand(engine, rules, after, reference=reference)
                if event["kind"] in ("self_win", "other_win", "draw") and (
                    event["score_delta"] != terminal["score_delta"]
                ):
                    raise ValueError("首次终局事件与完整单局结算不同")
                category = _label(terminal, frozen["focal_seat"])
                rows.append({
                    "sample": sample, "first_action_key": key,
                    "continuation_reference": reference,
                    "first_event_key": _event_key(event),
                    "terminal_category": category,
                    "terminal": terminal,
                })
    summaries = {}
    for reference in frozen["continuation_references"]:
        by_action = {}
        for key in frozen["forced_first_actions"]:
            subset = [row for row in rows if row["continuation_reference"] == reference
                      and row["first_action_key"] == key]
            if [row["sample"] for row in subset] != list(range(frozen["worlds_per_root"])):
                raise ValueError("高番探针相关世界编号不守恒")
            categories = Counter(row["terminal_category"] for row in subset)
            events = Counter(row["first_event_key"].split(":")[0] for row in subset)
            net = [row["terminal"]["score_delta"][frozen["focal_seat"]]
                   for row in subset]
            by_action[key] = {
                "mean_own_net": sum(net) / len(net),
                "category_counts": dict(sorted(categories.items())),
                "first_event_kind_counts": dict(sorted(events.items())),
                "maximum_realized_fan": max(row["terminal"]["fan"] or 0
                                            for row in subset),
            }
        by_action["paired_discard_minus_hu_mean_net"] = (
            by_action["discard:6w"]["mean_own_net"] - by_action["hu"]["mean_own_net"])
        summaries[reference] = by_action
    return {
        "scope": "opened_single_root_paired_teacher_not_VIP_policy_or_population_gain",
        "freeze": frozen, "root_id": frozen["root_id"],
        "row_count": len(rows), "summary": summaries, "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(json.loads(args.freeze.read_text(encoding="utf-8"))),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
