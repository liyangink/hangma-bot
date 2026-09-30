"""已开结局的动作后态模型开发诊断；不得当成独立确认。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Hu
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_competing_tail_audit import _label
from scripts.vip_p3_competing_value_probe import _load
from scripts.vip_p3_poststate_value_probe import expected_net, features


_LIMITS = ValueAnalysisLimits(max_expansions=8192)


def _mean_net(row: dict, key: str, seat: int) -> float:
    """同根相关隐藏世界的本人单局净积分均值。"""

    samples = row["outcomes_by_action"][key]
    if [sample["sample"] for sample in samples] != list(range(row["sample_count"])):
        raise ValueError("相关隐藏世界编号不守恒")
    return sum(sample["terminal"]["score_delta"][seat] for sample in samples) / len(samples)


def evaluate(scan: dict, model: dict, old_predictions: dict,
             shape: dict, r18: dict) -> dict:
    """原训练源不变，比较后态与旧模型在已开根的动作差；按根计数。"""

    if (scan.get("scope") != "pre_outcome_all_action_root_scan_not_strategy_value"
            or model.get("schema") != "vip-p3-poststate-terminal-probe/1"
            or old_predictions.get("scope") !=
            "pre_outcome_competing_terminal_predictions_not_C_alg"
            or shape.get("continuation_reference") != "shape"
            or r18.get("continuation_reference") != "r18_frozen"
            or any(report.get("start_seed") != scan.get("start_seed")
                   or report.get("requested_seeds") != scan.get("requested_seeds")
                   for report in (shape, r18, old_predictions))):
        raise ValueError("后态诊断来源身份不一致")
    for source in model["training_sources"]:
        path = Path(source["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("后态模型训练教师来源摘要漂移")
    if len(model.get("feature_sources", ())) != 2:
        raise ValueError("后态模型缺动作后态特征来源")
    for source in model["feature_sources"]:
        path = Path(source["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("后态模型特征来源摘要漂移")
    by_old = {row["root_id"]: row for row in old_predictions["rows"]}
    teachers = {name: {row["root_id"]: row for row in report["rows"]}
                for name, report in (("shape", shape), ("r18_frozen", r18))}
    ids = {row["root_id"] for row in scan["rows"]}
    if (len(ids) != scan["root_count"] or set(by_old) != ids
            or any(set(rows) != ids for rows in teachers.values())):
        raise ValueError("后态诊断观察根集合不守恒")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    rows_out = []
    calibration = {"poststate_brier": 0.0, "old_brier": 0.0,
                   "poststate_mass": [0.0] * 4, "old_mass": [0.0] * 4,
                   "observed_mass": [0.0] * 4}
    categories = ("draw", "self_low", "self_high", "other_win")
    for source in scan["rows"]:
        observation = observation_from_json(source["observation"])
        if hashlib.sha256(repr(observation).encode()).hexdigest() != source["root_id"]:
            raise ValueError("玩家观察摘要不一致")
        analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
        keys = [candidate.action_key for candidate in analysis.legal_candidates]
        if (analysis.completeness is not RuleCompleteness.COMPLETE
                or keys != source["legal_action_keys"]
                or [root.action_key for root in analysis.conditional_roots] != keys):
            raise ValueError("当前规则动作或条件根与扫描不同")
        scores = []
        probabilities = {}
        for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots):
            x, exact = features(candidate, root, observation)
            if isinstance(candidate.action, Hu):
                value = exact
            else:
                value, probabilities[candidate.action_key] = expected_net(x, model)
            scores.append((candidate.action_key, value))
        chosen = min(scores, key=lambda item: (-round(item[1], 8),
                                               item[0] != "hu", item[0]))[0]
        old = by_old[source["root_id"]]["chosen_action_key"]
        baseline = source["shape_first_action_key"]
        if any(key not in keys for key in (chosen, old, baseline)):
            raise ValueError("新旧首选不属于同根合法动作")
        old_scores = {item["action_key"]: item for item in by_old[source["root_id"]]["scores"]}
        if set(old_scores) != set(keys):
            raise ValueError("旧模型全动作分数与冻结扫描不一致")
        non_hu = list(probabilities)
        if non_hu:
            teacher = teachers["shape"][source["root_id"]]
            weight = 1.0 / (len(scan["rows"]) * len(non_hu))
            for key in non_hu:
                samples = teacher["outcomes_by_action"][key]
                counts = Counter(_label(sample["terminal"], observation.seat)
                                 for sample in samples)
                empirical = [counts[name] / len(samples) for name in categories]
                new_prob = probabilities[key]
                old_prob = old_scores[key]["terminal_category_probability"]
                if (old_prob is None or len(old_prob) != 4
                        or abs(sum(old_prob) - 1) > 1e-12):
                    raise ValueError("旧模型终局概率质量不守恒")
                for index in range(4):
                    calibration["poststate_mass"][index] += weight * new_prob[index]
                    calibration["old_mass"][index] += weight * old_prob[index]
                    calibration["observed_mass"][index] += weight * empirical[index]
                    calibration["poststate_brier"] += weight * (
                        new_prob[index] ** 2 - 2 * new_prob[index] * empirical[index]
                        + empirical[index])
                    calibration["old_brier"] += weight * (
                        old_prob[index] ** 2 - 2 * old_prob[index] * empirical[index]
                        + empirical[index])
        gains = {}
        old_gains = {}
        for name, report in teachers.items():
            teacher = report[source["root_id"]]
            if (teacher["observation"] != source["observation"]
                    or teacher["legal_action_keys"] != keys):
                raise ValueError("教师观察或合法动作与新模型输入不同")
            if "hu" in keys:
                exact = dict(scores)["hu"]
                if any(sample["terminal"]["score_delta"][observation.seat] != exact
                       for sample in teacher["outcomes_by_action"]["hu"]):
                    raise ValueError("教师当前胡积分与规则精确结算不同")
            gains[name] = _mean_net(teacher, chosen, observation.seat) - _mean_net(
                teacher, baseline, observation.seat)
            old_gains[name] = _mean_net(teacher, old, observation.seat) - _mean_net(
                teacher, baseline, observation.seat)
        rows_out.append({"seed": source["seed"], "root_id": source["root_id"],
                         "phase": source["phase"], "tags": source["tags"],
                         "shape_first_action": baseline, "old_action": old,
                         "poststate_action": chosen,
                         "poststate_minus_shape_net": gains,
                         "old_minus_shape_net": old_gains})
    result = {"scope": "opened_outcome_poststate_development_not_independent_validation",
              "root_count": len(rows_out), "rows": rows_out,
              "shape_teacher_category_calibration": calibration,
              "changed_vs_shape": sum(row["poststate_action"] != row["shape_first_action"]
                                      for row in rows_out),
              "changed_vs_old": sum(row["poststate_action"] != row["old_action"]
                                    for row in rows_out),
              "deferred_current_hu": sum(row["shape_first_action"] == "hu"
                                         and row["poststate_action"] != "hu"
                                         for row in rows_out)}
    for segment, selected in (("all", rows_out),
                              ("draw", [row for row in rows_out if row["phase"] == "draw"]),
                              ("response", [row for row in rows_out if row["phase"] != "draw"])):
        summary = {"root_count": len(selected)}
        for name in teachers:
            new_values = [row["poststate_minus_shape_net"][name] for row in selected]
            old_values = [row["old_minus_shape_net"][name] for row in selected]
            signs = Counter("positive" if value > 0 else "negative" if value < 0 else "zero"
                            for value in new_values)
            summary[name] = {
                "poststate_mean_net": sum(new_values) / len(new_values) if new_values else None,
                "old_mean_net": sum(old_values) / len(old_values) if old_values else None,
                "poststate_root_signs": {sign: signs[sign] for sign in
                                         ("positive", "negative", "zero")},
            }
        result[segment] = summary
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--old-predictions", type=Path, required=True)
    parser.add_argument("--shape", type=Path, required=True)
    parser.add_argument("--r18", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(_load(args.scan), _load(args.model),
                              _load(args.old_predictions), _load(args.shape),
                              _load(args.r18)), ensure_ascii=False,
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
