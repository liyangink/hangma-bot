"""已开高番正控的模型首选动作后验续打；仅诊断动作区分。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import SimulationChoice, SimulationEngine

from scripts.vip_p3_anchored_value_probe import predict_observation
from scripts.vip_p3_first_event_preflight import _finish_hand
from scripts.vip_p3_highfan_probe_teacher import _selected_world


def audit(frozen: dict, model: dict, existing: dict) -> dict:
    """同一冻结观察和重采样键，只追加模型选出的首动作结局。"""

    if (frozen.get("scope") !=
            "pre_outcome_single_root_rule_payoff_probe_not_strategy_confirmation"
            or existing.get("scope") !=
            "opened_single_root_paired_teacher_not_VIP_policy_or_population_gain"
            or existing.get("freeze") != frozen
            or frozen.get("worlds_per_root") != 64):
        raise ValueError("后验正控与事前冻结样本不一致")
    selection_path = Path(frozen["selection_report"])
    if hashlib.sha256(selection_path.read_bytes()).hexdigest() != frozen[
        "selection_report_sha256"
    ]:
        raise ValueError("高番根结果盲选取来源摘要漂移")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selected, = [item for item in selection["selected_roots"]
                 if item["root_id"] == frozen["root_id"]]
    observation = observation_from_json(selected["observation"])
    scores = predict_observation(observation, model)
    chosen = scores[0]["action_key"]
    if chosen in frozen["forced_first_actions"]:
        raise ValueError("模型首选已在预冻结臂中，无须后验续打")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    world, frame, decision = _selected_world(engine, rules, frozen, observation)
    actions = {item.action_key: item.action for item in
               rules.analyze(observation).legal_candidates}
    if chosen not in actions:
        raise ValueError("模型首选不属于同次合法动作")
    by_existing = {(item["sample"], item["first_action_key"],
                    item["continuation_reference"]): item
                   for item in existing["rows"]}
    if len(by_existing) != existing["row_count"]:
        raise ValueError("预冻结正控结果重复")
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
            raise ValueError("后验相关隐藏世界改变本座观察")
        after = engine.advance(hidden, sampled_frame.revision, tuple(
            SimulationChoice(item.window_key,
                             actions[chosen] if item.window_key == decision.window_key else
                             choose_reference_action(rules, item,
                                                     mode=frozen["selection_reference"]))
            for item in sampled_frame.decisions
        ))
        for reference in frozen["continuation_references"]:
            terminal = _finish_hand(engine, rules, after, reference=reference)
            old = by_existing[(sample, "discard:6w", reference)]["terminal"]
            rows.append({
                "sample": sample, "continuation_reference": reference,
                "first_action_key": chosen, "terminal": terminal,
                "net_minus_frozen_discard_6w": terminal["score_delta"][
                    frozen["focal_seat"]] - old["score_delta"][frozen["focal_seat"]],
            })
    summary = {}
    for reference in frozen["continuation_references"]:
        subset = [item for item in rows if item["continuation_reference"] == reference]
        gains = [item["net_minus_frozen_discard_6w"] for item in subset]
        fans = Counter(item["terminal"]["fan"] for item in subset)
        summary[reference] = {
            "mean_own_net": sum(item["terminal"]["score_delta"][frozen["focal_seat"]]
                                for item in subset) / len(subset),
            "mean_minus_frozen_discard_6w": sum(gains) / len(gains),
            "fan_counts": dict(sorted(fans.items())),
            "paired_signs": {name: sum(("positive" if x > 0 else
                                        "negative" if x < 0 else "zero") == name
                                       for x in gains)
                             for name in ("positive", "negative", "zero")},
        }
    return {
        "scope": "posthoc_opened_root_action_diagnostic_not_independent_confirmation",
        "root_id": frozen["root_id"], "model_first_action_key": chosen,
        "model_first_score": scores[0], "row_count": len(rows),
        "summary": summary, "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--existing", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(*(json.loads(path.read_text(encoding="utf-8")) for path in
                             (args.freeze, args.model, args.existing))),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
