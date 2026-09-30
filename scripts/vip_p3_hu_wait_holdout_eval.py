"""核对事前锁定的低番胡选择与留出教师结局；绝不重新拟合或挑动作。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from scripts.vip_p3_hu_wait_audit import _load, audit
from scripts.vip_p3_competing_tail_audit import _label


def _sign(value: float) -> str:
    """把相关世界的根均差按固定零容差分类。"""

    return "positive" if value > 1e-9 else "negative" if value < -1e-9 else "zero"


def evaluate(scan: dict, predictions: dict, first: dict, second: dict) -> dict:
    """只评价锁定动作在两名续打者下相对立即胡的配对积分。"""

    if (predictions.get("scope") != "pre_outcome_frozen_hu_wait_predictions_not_C_alg"
            or predictions.get("selection_method") != scan.get("selection_method")
            or predictions.get("start_seed") != scan.get("start_seed")
            or predictions.get("requested_seeds") != scan.get("requested_seeds")
            or first.get("continuation_reference") != "shape"
            or second.get("continuation_reference") != "r18_frozen"):
        raise ValueError("留出预测或两名续打者身份不符合事前冻结口径")
    paired = audit(scan, first, second)
    predicted = {row["root_id"]: row for row in predictions["rows"]}
    by_ref = {
        report["continuation_reference"]: {row["root_id"]: row
                                             for row in report["rows"]}
        for report in (first, second)
    }
    if (len(predicted) != predictions["root_count"]
            or set(predicted) != {row["root_id"] for row in paired["rows"]}
            or predictions["root_count"] != paired["root_count"]):
        raise ValueError("事前预测与留出教师的根身份不守恒")
    rows = []
    for paired_row in paired["rows"]:
        root_id = paired_row["root_id"]
        pred = predicted[root_id]
        key = pred["chosen_action_key"]
        scored_keys = [item["action_key"] for item in pred["scores"]]
        if (pred["seed"] != paired_row["seed"]
                or pred["current_hu_net"] != paired_row["current_hu_net"]
                or pred["current_hu_fan"] != paired_row["current_hu_fan"]
                or pred["white_count"] != paired_row["white_count"]
                or len(scored_keys) != len(set(scored_keys))
                or set(scored_keys) != set(by_ref["shape"][root_id]["legal_action_keys"])
                or key not in scored_keys):
            raise ValueError("预测动作或根事实与行动前账、合法候选不一致")
        # 复核锁定预测本身的排序；不能在看结局后改选动作。
        best = min(pred["scores"], key=lambda item: (
            -round(item["expected_net_probe"], 8),
            item["action_key"] != "hu", item["action_key"],
        ))
        if key != best["action_key"]:
            raise ValueError("锁定预测与冻结同分排序规则不一致")
        gains = {}
        categories = {}
        for ref in ("shape", "r18_frozen"):
            teacher = by_ref[ref][root_id]
            samples = teacher["outcomes_by_action"][key]
            seat = teacher["observation"]["seat"]
            gained = sum(item["terminal"]["score_delta"][seat]
                         for item in samples) / len(samples) - pred["current_hu_net"]
            if abs(gained - (paired_row["continue_mean_net_minus_hu"][ref].get(key, 0))) > 1e-9:
                raise ValueError("所选动作的配对净分与逐动作审计不一致")
            gains[ref] = gained
            categories[ref] = dict(sorted(Counter(
                _label(item["terminal"], seat) for item in samples
            ).items()))
        rows.append({
            "seed": pred["seed"], "root_id": root_id,
            "chosen_action_key": key, "wait_chosen": key != "hu",
            "current_hu_fan": pred["current_hu_fan"],
            "current_hu_net": pred["current_hu_net"],
            "white_count": pred["white_count"],
            "wall_remaining": pred["wall_remaining"],
            "paired_net_minus_immediate_hu": gains,
            "chosen_terminal_categories": categories,
        })
    wait_rows = [row for row in rows if row["wait_chosen"]]
    if len(wait_rows) != predictions["wait_chosen_roots"]:
        raise ValueError("冻结等待动作根数不守恒")

    def summarize(group: list[dict]) -> dict:
        """统计单位固定为观察根，绝不把隐藏世界当独立样本。"""

        out = {"root_count": len(group)}
        for ref in ("shape", "r18_frozen"):
            values = [row["paired_net_minus_immediate_hu"][ref] for row in group]
            signs = Counter(map(_sign, values))
            out[ref] = {
                "mean_paired_net_minus_immediate_hu_per_root":
                    sum(values) / len(values) if values else None,
                "sum_paired_net_minus_immediate_hu": sum(values),
                "root_signs": {key: signs[key] for key in
                               ("positive", "negative", "zero")},
                "worst_root": min(
                    ({"seed": row["seed"], "gain": value}
                     for row, value in zip(group, values)),
                    key=lambda item: item["gain"], default=None),
                "best_root": max(
                    ({"seed": row["seed"], "gain": value}
                     for row, value in zip(group, values)),
                    key=lambda item: item["gain"], default=None),
                "chosen_action_terminal_categories": dict(sorted(Counter({
                    label: sum(row["chosen_terminal_categories"][ref].get(label, 0)
                               for row in group)
                    for label in {label for row in group
                                  for label in row["chosen_terminal_categories"][ref]}
                }).items())),
            }
        return out

    return {
        "scope": "prelocked_holdout_action_once_teacher_continuation_not_C_alg",
        "references": ["shape", "r18_frozen"],
        "seed_frame": paired["seed_frame"],
        "worlds_per_root": paired["worlds_per_root"],
        "all_selected_roots": summarize(rows),
        "prelocked_wait_roots": summarize(wait_rows),
        "wait_roots_by_white_count": {
            label: summarize([row for row in wait_rows if
                              (row["white_count"] >= 2) == (label == "at_least_two")])
            for label in ("at_least_two", "under_two")
        },
        "wait_roots_by_current_fan": {
            str(fan): summarize([row for row in wait_rows
                                 if row["current_hu_fan"] == fan])
            for fan in sorted({row["current_hu_fan"] for row in wait_rows})
        },
        "wait_cross_reference_signs": dict(sorted(Counter(
            _sign(row["paired_net_minus_immediate_hu"]["shape"]) + "/" +
            _sign(row["paired_net_minus_immediate_hu"]["r18_frozen"])
            for row in wait_rows
        ).items())),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(_load(args.scan), _load(args.predictions),
                      _load(args.first), _load(args.second))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
