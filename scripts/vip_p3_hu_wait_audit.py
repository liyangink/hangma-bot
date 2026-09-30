"""当前低番胡与继续动作在同观察、同隐藏世界下的积分配对账。

逐动作结果只诊断教师续打标签；事后选最佳继续动作会有赢家偏差，
不能当作可执行策略、自然桌收益或概率校准。
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from scripts.vip_p3_competing_tail_audit import _label


def audit(scan: dict, first: dict, second: dict) -> dict:
    """对齐已冻结根与两名续打者，核立即胡结算和全部继续动作。"""

    if (scan.get("scope") !=
            "result_blind_opportunity_root_selection_not_outcome_or_probability"
            or scan.get("selection_method") != "first_low_fan_hu_under_shape_per_seed"
            or first.get("scope") !=
            "P3_offline_teacher_labels_only_not_candidate_policy_value"
            or second.get("scope") != first["scope"]
            or first.get("selection_tag") != "first_low_fan_hu"
            or second.get("selection_tag") != "first_low_fan_hu"
            or first.get("start_seed") != scan["start_seed"]
            or second.get("start_seed") != scan["start_seed"]
            or first.get("requested_seeds") != scan["requested_seeds"]
            or second.get("requested_seeds") != scan["requested_seeds"]
            or first.get("worlds_per_root") != second.get("worlds_per_root")):
        raise ValueError("低番胡扫描与教师来源或抽样口径不一致")
    names = (first["continuation_reference"], second["continuation_reference"])
    if names[0] == names[1]:
        raise ValueError("低番胡配对需要两名不同续打者")
    selected = {row["observation_sha256"]: row for row in scan["selected_roots"]
                if "first_low_fan_hu" in row["tags"]}
    if len(selected) != scan["counts"]["selected_first_low_fan_hu"]:
        raise ValueError("扫描根身份重复或数量不守恒")
    by_ref = {}
    for name, report in zip(names, (first, second)):
        rows = {row["root_id"]: row for row in report["rows"]}
        if len(rows) != len(report["rows"]) or set(rows) != set(selected):
            raise ValueError("教师根与行动前冻结扫描不一致")
        by_ref[name] = rows
    sign_counts: Counter[str] = Counter()
    any_positive = Counter()
    shared_positive = 0
    rows_out = []
    for root_id, selected_row in sorted(selected.items(),
                                        key=lambda pair: pair[1]["seed"]):
        root_rows = [by_ref[name][root_id] for name in names]
        row = root_rows[0]
        if (row["seed"] != selected_row["seed"]
                or row["observation"] != root_rows[1]["observation"]
                or row["legal_action_keys"] != root_rows[1]["legal_action_keys"]
                or row["sample_count"] != root_rows[1]["sample_count"]
                or row["sample_count"] != first["worlds_per_root"]
                or "hu" not in row["legal_action_keys"]):
            raise ValueError("低番胡根观察、合法动作或相关世界不一致")
        keys = row["legal_action_keys"]
        if len(set(keys)) != len(keys) or len(keys) < 2:
            raise ValueError("低番胡根缺唯一 Hu 与继续动作")
        seat = row["observation"]["seat"]
        if type(seat) is not int or seat not in range(4):
            raise ValueError("低番胡根座位无效")
        net = selected_row["current_hu_net"]
        fan = selected_row["current_hu_fan"]
        values = {}
        categories = {}
        for name, data in zip(names, root_rows):
            arms = data["outcomes_by_action"]
            if set(arms) != set(keys):
                raise ValueError("低番胡教师缺全合法动作")
            values[name] = {}
            categories[name] = {}
            for key in keys:
                samples = arms[key]
                if [item["sample"] for item in samples] != list(
                    range(row["sample_count"])):
                    raise ValueError("同根继续动作隐藏世界编号不守恒")
                labels = [_label(item["terminal"], seat) for item in samples]
                points = [item["terminal"]["score_delta"][seat]
                          for item in samples]
                if key == "hu" and any(
                    label not in ("self_low", "self_high")
                    or point != net or item["terminal"]["fan"] != fan
                    for label, point, item in zip(labels, points, samples)
                ):
                    raise ValueError("当前 Hu 教师结局与行动前规则结算不一致")
                values[name][key] = sum(points) / len(points)
                categories[name][key] = dict(sorted(Counter(labels).items()))
        gains = {name: {key: values[name][key] - net
                        for key in keys if key != "hu"} for name in names}
        for name in names:
            any_positive[name] += any(delta > 0 for delta in gains[name].values())
        shared_positive += any(all(gains[name][key] > 0 for name in names)
                               for key in gains[names[0]])
        for key in gains[names[0]]:
            a, b = (gains[name][key] for name in names)
            tag = ("both_zero" if a == b == 0 else "one_zero" if a == 0 or b == 0
                   else "same_sign" if (a > 0) == (b > 0) else "opposite")
            sign_counts[tag] += 1
        rows_out.append({
            "seed": selected_row["seed"], "root_id": root_id,
            "current_hu_fan": fan, "current_hu_net": net,
            "white_count": selected_row["white_count"],
            "wall_remaining": selected_row["wall_remaining"],
            "continue_mean_net_minus_hu": gains,
            "continue_terminal_categories": {
                name: {key: categories[name][key] for key in gains[name]}
                for name in names},
        })
    return {
        "scope": "offline_hu_wait_teacher_diagnostic_not_strategy_gain",
        "references": names,
        "seed_frame": [scan["start_seed"],
                       scan["start_seed"] + scan["requested_seeds"] - 1],
        "root_count": len(rows_out),
        "worlds_per_root": first["worlds_per_root"],
        "roots_with_any_positive_continue": dict(any_positive),
        "roots_with_same_positive_continue_both_references": shared_positive,
        "all_continue_action_signs": {
            key: sign_counts[key]
            for key in ("both_zero", "one_zero", "same_sign", "opposite")},
        "rows": rows_out,
    }


def _load(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(_load(args.scan), _load(args.first),
                           _load(args.second)),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
