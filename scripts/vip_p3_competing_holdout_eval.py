"""事前全动作预测在新根上的相关世界积分与互斥终局校准审计。"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from collections import Counter
from pathlib import Path

from scripts.vip_p3_competing_tail_audit import _label, audit as paired_audit


_CATEGORIES = ("draw", "self_low", "self_high", "other_win")


def _load(path: Path) -> dict:
    """从只读 JSON 或 gzip JSON 装载已冻结证据。"""

    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def _sign(value: float) -> str:
    return "positive" if value > 1e-9 else "negative" if value < -1e-9 else "zero"


def _summarize(rows: list[dict]) -> dict:
    """每行动前观察根等权，相关隐藏世界只用于根内均值。"""

    result = {"root_count": len(rows)}
    for ref in ("shape", "r18_frozen"):
        values = [row["paired_net_minus_shape_first"][ref] for row in rows]
        counts = Counter(_sign(value) for value in values)
        ranked = sorted(zip(values, (row["seed"] for row in rows)), reverse=True)
        result[ref] = {
            "mean_paired_net_delta_per_root": sum(values) / len(values) if values else None,
            "sum_paired_net_delta": sum(values),
            "root_signs": {name: counts[name] for name in
                           ("positive", "negative", "zero")},
            "worst_root": (min(({"seed": row["seed"], "gain": value}
                                for row, value in zip(rows, values)),
                               key=lambda item: item["gain"], default=None)),
            "best_root": (max(({"seed": row["seed"], "gain": value}
                               for row, value in zip(rows, values)),
                              key=lambda item: item["gain"], default=None)),
            "mean_after_removing_best_one": (
                (sum(values) - ranked[0][0]) / (len(values) - 1)
                if len(values) > 1 else None),
            "mean_after_removing_best_two": (
                (sum(values) - ranked[0][0] - ranked[1][0]) / (len(values) - 2)
                if len(values) > 2 else None),
        }
    return result


def evaluate(scan: dict, predictions: dict, shape: dict, r18: dict) -> dict:
    """先核来源和质量守恒，再只结算事前首选的根级差。"""

    if (scan.get("scope") != "pre_outcome_all_action_root_scan_not_strategy_value"
            or predictions.get("scope") !=
            "pre_outcome_competing_terminal_predictions_not_C_alg"
            or scan.get("start_seed") != predictions.get("start_seed")
            or scan.get("requested_seeds") != predictions.get("requested_seeds")
            or predictions.get("root_count") != scan.get("root_count")
            or shape.get("start_seed") != scan.get("start_seed")
            or r18.get("start_seed") != scan.get("start_seed")
            or shape.get("requested_seeds") != scan.get("requested_seeds")
            or r18.get("requested_seeds") != scan.get("requested_seeds")
            or shape.get("continuation_reference") != "shape"
            or r18.get("continuation_reference") != "r18_frozen"):
        raise ValueError("事前预测、选根和两套教师的来源不一致")
    sensitivity = paired_audit(shape, r18)
    roots = {row["root_id"]: row for row in scan["rows"]}
    predicted = {row["root_id"]: row for row in predictions["rows"]}
    teachers = {name: {row["root_id"]: row for row in report["rows"]}
                for name, report in (("shape", shape), ("r18_frozen", r18))}
    if (len(roots) != scan["root_count"] or len(predicted) != len(roots)
            or set(predicted) != set(roots)
            or any(len(rows) != len(roots) or set(rows) != set(roots)
                   for rows in teachers.values())):
        raise ValueError("事前扫描、预测和教师观察根集合不守恒")
    calibration_predicted = [0.0] * 4
    calibration_observed = [0.0] * 4
    calibration_brier = 0.0
    calibrated_roots = 0
    rows_out = []
    for root_id, original in sorted(roots.items(),
                                    key=lambda pair: (pair[1]["seed"], pair[0])):
        pred = predicted[root_id]
        by_ref = {name: teachers[name][root_id]
                  for name in ("shape", "r18_frozen")}
        keys = original["legal_action_keys"]
        scored = {item["action_key"]: item for item in pred["scores"]}
        if (pred["seed"] != original["seed"]
                or pred["tags"] != original["tags"]
                or pred["phase"] != original["phase"]
                or pred["shape_first_action_key"] != original["shape_first_action_key"]
                or len(scored) != len(pred["scores"]) or set(scored) != set(keys)
                or pred["chosen_action_key"] not in scored
                or any((row["seed"], row["tags"], row["phase"],
                        row["observation"], row["legal_action_keys"])
                       != (original["seed"], original["tags"], original["phase"],
                           original["observation"], keys)
                       for row in by_ref.values())):
            raise ValueError("教师观察、合法动作或事前预测身份不一致")
        chosen = min(pred["scores"], key=lambda item: (
            -round(item["expected_net_probe"], 8),
            item["action_key"] != "hu", item["action_key"],
        ))["action_key"]
        if chosen != pred["chosen_action_key"]:
            raise ValueError("事前首选不符合冻结评分排序")
        seat = original["observation"]["seat"]
        non_hu = [key for key in keys if key != "hu"]
        if non_hu:
            calibrated_roots += 1
        for key in keys:
            score = scored[key]
            for name, row in by_ref.items():
                samples = row["outcomes_by_action"][key]
                if [sample["sample"] for sample in samples] != list(
                        range(row["sample_count"])):
                    raise ValueError("相关隐藏世界编号不守恒")
                if key == "hu" and any(
                    sample["terminal"]["score_delta"][seat] !=
                    score["exact_current_hu_net"] for sample in samples
                ):
                    raise ValueError("立即胡的教师积分与规则真值不一致")
            if key == "hu":
                if score["terminal_category_probability"] is not None:
                    raise ValueError("立即胡不得用终局概率代理")
                continue
            probability = score["terminal_category_probability"]
            if (not isinstance(probability, list) or len(probability) != 4
                    or any(not isinstance(value, (float, int)) or
                           not math.isfinite(value) or value < 0
                           for value in probability)
                    or abs(sum(probability) - 1) > 1e-12):
                raise ValueError("非胡的互斥概率质量不守恒")
            samples = by_ref["shape"]["outcomes_by_action"][key]
            counts = Counter(_label(sample["terminal"], seat)
                             for sample in samples)
            weight = 1.0 / len(non_hu)
            for index, label in enumerate(_CATEGORIES):
                empirical = counts[label] / len(samples)
                calibration_predicted[index] += weight * probability[index]
                calibration_observed[index] += weight * empirical
                calibration_brier += weight * (
                    probability[index] ** 2 -
                    2 * probability[index] * empirical + empirical)
        gains = {}
        chosen_categories = {}
        for name, row in by_ref.items():
            arms = row["outcomes_by_action"]
            sample_count = row["sample_count"]
            if sample_count != shape["worlds_per_root"]:
                raise ValueError("新根相关隐藏世界数与冻结口径不一致")
            def net(key: str) -> float:
                return sum(sample["terminal"]["score_delta"][seat]
                           for sample in arms[key]) / sample_count
            gains[name] = net(chosen) - net(original["shape_first_action_key"])
            chosen_categories[name] = dict(sorted(Counter(
                _label(sample["terminal"], seat)
                for sample in arms[chosen]
            ).items()))
        rows_out.append({
            "seed": original["seed"], "root_id": root_id,
            "tags": original["tags"], "phase": original["phase"],
            "shape_first_action_key": original["shape_first_action_key"],
            "chosen_action_key": chosen,
            "changed": chosen != original["shape_first_action_key"],
            "paired_net_minus_shape_first": gains,
            "chosen_terminal_categories": chosen_categories,
        })
    if calibrated_roots == 0:
        raise ValueError("新根没有可校准的非胡动作")
    if sum(row["changed"] for row in rows_out) != predictions["changed_vs_shape_roots"]:
        raise ValueError("事前改选根数不守恒")
    changed = [row for row in rows_out if row["changed"]]
    return {
        "scope": "prelocked_competing_terminal_action_once_not_C_alg",
        "seed_frame": [scan["start_seed"],
                       scan["start_seed"] + scan["requested_seeds"] - 1],
        "worlds_per_root": shape["worlds_per_root"],
        "all_roots": _summarize(rows_out),
        "changed_roots": _summarize(changed),
        "by_tag": {tag: _summarize([row for row in rows_out
                                     if tag in row["tags"]])
                   for tag in sorted({tag for row in rows_out
                                      for tag in row["tags"]})},
        "changed_action_family": dict(sorted(Counter(
            row["chosen_action_key"].split(":", 1)[0]
            for row in changed).items())),
        "changed_cross_reference_signs": dict(sorted(Counter(
            _sign(row["paired_net_minus_shape_first"]["shape"]) + "/" +
            _sign(row["paired_net_minus_shape_first"]["r18_frozen"])
            for row in changed).items())),
        "shape_terminal_category_calibration_all_non_hu_arms": {
            "category_order": list(_CATEGORIES),
            "root_count": calibrated_roots,
            "predicted_mass": [value / calibrated_roots
                               for value in calibration_predicted],
            "observed_mass": [value / calibrated_roots
                              for value in calibration_observed],
            "brier_multiclass": calibration_brier / calibrated_roots,
        },
        "teacher_sensitivity": {key: value for key, value in sensitivity.items()
                                if key != "rows"},
        "rows": rows_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--shape", type=Path, required=True)
    parser.add_argument("--r18", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(_load(args.scan), _load(args.predictions),
                      _load(args.shape), _load(args.r18))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
