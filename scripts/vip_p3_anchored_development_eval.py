"""已开根上否证规则支付锚定探针；结果仅作开发诊断。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_anchored_value_probe import predict_observation
from scripts.vip_p3_competing_value_probe import _load
from scripts.vip_p3_poststate_value_probe import expected_net, features


_LIMITS = ValueAnalysisLimits(max_expansions=8192)


def _mean(row: dict, key: str, seat: int) -> float:
    """一个观察根中相关隐藏世界的本人完整单局净分均值。"""

    samples = row["outcomes_by_action"][key]
    if [item["sample"] for item in samples] != list(range(row["sample_count"])):
        raise ValueError("教师相关隐藏世界编号不守恒")
    return sum(item["terminal"]["score_delta"][seat] for item in samples) / len(samples)


def evaluate(scan: dict, anchored: dict, poststate: dict,
             shape: dict, r18: dict) -> dict:
    """同根比较已冻结的 shape 续打、旧模型与新支付锚定探针。"""

    if (scan.get("scope") != "pre_outcome_all_action_root_scan_not_strategy_value"
            or shape.get("continuation_reference") != "shape"
            or r18.get("continuation_reference") != "r18_frozen"
            or anchored.get("schema") != "vip-p3-anchored-payoff-probe/1"
            or poststate.get("schema") != "vip-p3-poststate-terminal-probe/1"
            or any(item.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}
                   for item in (scan, anchored, poststate, shape, r18))):
        raise ValueError("支付探针评测来源配置或版本不匹配")
    sources = anchored["training_sources"]
    if (not sources or any(hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()
                           != item["sha256"] for item in sources)):
        raise ValueError("支付模型训练来源摘要漂移")
    training_ids = set()
    for item in sources:
        training_ids.update(row["root_id"] for row in _load(Path(item["path"]))["rows"])
    teachers = {name: {row["root_id"]: row for row in report["rows"]}
                for name, report in (("shape", shape), ("r18_frozen", r18))}
    scan_ids = {row["root_id"] for row in scan["rows"]}
    if (len(scan_ids) != scan["root_count"] or scan_ids & training_ids
            or any(set(rows) != scan_ids for rows in teachers.values())):
        raise ValueError("评测观察根重复、泄漏训练或教师根身份不符")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    rows_out = []
    first_normal = 0
    discard_worlds = 0
    for source in scan["rows"]:
        observation = observation_from_json(source["observation"])
        root_id = hashlib.sha256(repr(observation).encode()).hexdigest()
        if root_id != source["root_id"]:
            raise ValueError("扫描玩家观察摘要不符")
        analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
        keys = [candidate.action_key for candidate in analysis.legal_candidates]
        if keys != source["legal_action_keys"]:
            raise ValueError("扫描合法动作与规则重算不同")
        new_scores = predict_observation(observation, anchored)
        new = new_scores[0]["action_key"]
        old_scores = {}
        for candidate, route in zip(analysis.legal_candidates, analysis.conditional_roots):
            x, exact = features(candidate, route, observation)
            old_scores[candidate.action_key] = (
                exact if exact is not None else expected_net(x, poststate)[0]
            )
        old = min(keys, key=lambda key: (-round(old_scores[key], 8),
                                        key != "hu", key))
        baseline = source["shape_first_action_key"]
        if any(key not in keys for key in (new, old, baseline)):
            raise ValueError("评测首选不属于同根合法动作")
        gains = {}
        for name, teacher in teachers.items():
            row = teacher[root_id]
            if row["observation"] != source["observation"] or row[
                "legal_action_keys"
            ] != keys:
                raise ValueError("教师观察或动作与扫描不一致")
            seat = observation.seat
            gains[name] = {
                "anchored_minus_shape": _mean(row, new, seat) - _mean(row, baseline, seat),
                "poststate_minus_shape": _mean(row, old, seat) - _mean(row, baseline, seat),
                "anchored_minus_poststate": _mean(row, new, seat) - _mean(row, old, seat),
            }
        for key in keys:
            if not key.startswith("discard:"):
                continue
            arm = teachers["shape"][root_id]["outcomes_by_action"][key]
            discard_worlds += len(arm)
            first_normal += sum(item["first_event"]["kind"] == "self_normal_draw"
                                for item in arm)
        rows_out.append({
            "seed": source["seed"], "root_id": root_id,
            "phase": source["phase"], "tags": source["tags"],
            "shape_action": baseline, "poststate_action": old,
            "anchored_action": new,
            "anchored_first_score": new_scores[0],
            "gains": gains,
        })
    summary = {}
    for segment, selected in (("all", rows_out),
                              ("draw", [row for row in rows_out if row["phase"] == "draw"]),
                              ("response", [row for row in rows_out if row["phase"] != "draw"])):
        stats = {"root_count": len(selected),
                 "changed_vs_shape": sum(row["anchored_action"] != row["shape_action"]
                                         for row in selected),
                 "changed_vs_poststate": sum(row["anchored_action"] !=
                                             row["poststate_action"] for row in selected)}
        for teacher in teachers:
            for key in ("anchored_minus_shape", "poststate_minus_shape",
                        "anchored_minus_poststate"):
                values = [row["gains"][teacher][key] for row in selected]
                signs = Counter("positive" if value > 0 else
                                "negative" if value < 0 else "zero" for value in values)
                stats[teacher + "." + key] = {
                    "mean_net_per_root": sum(values) / len(values) if values else None,
                    "root_signs": {name: signs[name] for name in
                                   ("positive", "negative", "zero")},
                }
        summary[segment] = stats
    return {
        "scope": "opened_outcome_anchored_development_not_independent_validation",
        "root_count": len(rows_out),
        "first_normal_draw_action_worlds": first_normal,
        "discard_action_worlds": discard_worlds,
        "empirical_first_normal_draw_action_world_fraction": (
            first_normal / discard_worlds if discard_worlds else None),
        "model_first_normal_draw_root_mean": anchored["first_event_normal_draw_root_mean"],
        "summary": summary, "rows": rows_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--anchored", type=Path, required=True)
    parser.add_argument("--poststate", type=Path, required=True)
    parser.add_argument("--shape", type=Path, required=True)
    parser.add_argument("--r18", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(*(_load(path) for path in (
        args.scan, args.anchored, args.poststate, args.shape, args.r18,
    ))), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
