"""冻结双白机会教师账的根／自然种子聚类诊断，不作完整策略成绩。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from scripts.vip_p3_competing_tail_audit import _label


def _load(path: Path) -> dict:
    """读取确定性 gzip JSON 或普通 JSON，不修改证据原件。"""

    source = path.read_bytes()
    return json.loads(gzip.decompress(source) if path.suffix == ".gz" else source)


def _stats(values: list[float]) -> dict:
    """按观察根计符号；零差和极值仍留在结果中。"""

    signs = Counter("positive" if value > 0 else
                    "negative" if value < 0 else "zero" for value in values)
    return {"count": len(values),
            "mean_net": sum(values) / len(values) if values else None,
            "signs": {name: signs[name] for name in ("positive", "negative", "zero")},
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None}


def analyze(report: dict, frozen: dict, freeze_path: Path) -> dict:
    """全根留账；模型缺证据单独计，不从完整条件层分母偷删。"""

    if (report.get("scope") !=
            "opened_multi_root_forced_first_action_teacher_not_full_VIP_strength"
            or frozen.get("scope") !=
            "pre_outcome_multi_root_paired_actions_not_algorithm_confirmation"
            or report.get("freeze_sha256") != hashlib.sha256(freeze_path.read_bytes()).hexdigest()
            or report.get("pre_outcome_freeze_commit") != "c4615a378"
            or report.get("root_count") != len(frozen["roots"])
            or report.get("natural_seed_count") != len({row["seed"] for row in frozen["roots"]})):
        raise ValueError("机会教师账与预提交冻结包身份不符")
    by_frozen = {row["root_id"]: row for row in frozen["roots"]}
    summaries = report["root_summaries"]
    if (len(by_frozen) != len(frozen["roots"])
            or len(summaries) != len(by_frozen)
            or {row["root_id"] for row in summaries} != set(by_frozen)):
        raise ValueError("机会根摘要数量或身份不守恒")
    expected_rows = sum(row["worlds_per_root"] * len(row["forced_first_actions"])
                        * 2 for row in frozen["roots"])
    if report["row_count"] != expected_rows or len(report["rows"]) != expected_rows:
        raise ValueError("机会教师动作世界总数不守恒")
    actual = defaultdict(list)
    seen_worlds = set()
    for item in report["rows"]:
        root = by_frozen.get(item["root_id"])
        if (root is None or item["seed"] != root["seed"]
                or item["first_action_key"] not in root["forced_first_actions"]
                or item["continuation_reference"] not in
                frozen["continuation_references"]
                or type(item["sample"]) is not int
                or not 0 <= item["sample"] < root["worlds_per_root"]):
            raise ValueError("教师动作世界不属于冻结的根、臂或样本")
        identity = (item["root_id"], item["first_action_key"],
                    item["continuation_reference"], item["sample"])
        if identity in seen_worlds:
            raise ValueError("教师动作世界重复")
        seen_worlds.add(identity)
        if _label(item["terminal"], frozen["focal_seat"]) != item["terminal_category"]:
            raise ValueError("教师终局类别与四座结算不同")
        actual[identity[:3]].append(item)
    if len(seen_worlds) != expected_rows:
        raise ValueError("教师动作世界唯一身份不守恒")
    for row in summaries:
        root = by_frozen[row["root_id"]]
        for reference in frozen["continuation_references"]:
            for key in root["forced_first_actions"]:
                records = actual[(row["root_id"], key, reference)]
                if sorted(item["sample"] for item in records) != list(
                    range(root["worlds_per_root"])
                ):
                    raise ValueError("教师每根每动作相关隐藏世界不完整")
                own = [item["terminal"]["score_delta"][frozen["focal_seat"]]
                       for item in records]
                stats = row["references"][reference]["actions"][key]
                if (abs(stats["mean_own_net"] - sum(own) / len(own)) > 1e-9
                        or stats["self_high_count"] != sum(
                            item["terminal_category"] == "self_high" for item in records)
                        or stats["other_win_count"] != sum(
                            item["terminal_category"] == "other_win" for item in records)
                        or stats["draw_count"] != sum(
                            item["terminal_category"] == "draw" for item in records)):
                    raise ValueError("教师根级结算摘要与逐世界记录不符")
    output = []
    for row in summaries:
        root = by_frozen[row["root_id"]]
        if (row["seed"] != root["seed"] or row["tags"] != root["tags"]
                or row["roles"] != root["roles"]
                or row["worlds_per_root"] != root["worlds_per_root"]):
            raise ValueError("教师观察根角色或世界数与冻结包不同")
        comparisons = {}
        for reference in frozen["continuation_references"]:
            info = row["references"][reference]
            by_action = info["actions"]
            if set(by_action) != set(root["forced_first_actions"]):
                raise ValueError("教师根合法比较臂不完整")
            baseline = by_action[root["roles"]["r18"]]["mean_own_net"]
            effects = {}
            for role in ("anchored", "shape", "highfan_witness", "immediate_hu"):
                key = root["roles"][role]
                effects[role] = (by_action[key]["mean_own_net"] - baseline
                                 if key is not None else None)
            paired = info["anchored_minus_r18_paired"]
            if (paired is None) != (root["roles"]["anchored"] is None):
                raise ValueError("模型缺证据与成对结果不一致")
            if paired is not None and abs(paired["mean_own_net"] - effects["anchored"]) > 1e-9:
                raise ValueError("模型成对动作差与根均值差不一致")
            comparisons[reference] = {
                "r18_mean_own_net": baseline,
                "role_minus_r18_mean_own_net": effects,
                "anchored_paired_world_signs": (None if paired is None else {
                    key: paired[key] for key in ("positive", "negative", "zero")}),
                "r18_self_high_count": by_action[root["roles"]["r18"]]["self_high_count"],
                "r18_other_win_count": by_action[root["roles"]["r18"]]["other_win_count"],
                "r18_draw_count": by_action[root["roles"]["r18"]]["draw_count"],
            }
        output.append({
            "seed": root["seed"], "root_id": root["root_id"],
            "tags": root["tags"], "roles": root["roles"],
            "model_gap": root["roles"]["anchored"] is None,
            "worlds_per_root": root["worlds_per_root"],
            "references": comparisons,
        })
    result = {}
    for tag in ("all", "first_two_white", "first_highfan_witness"):
        chosen = [row for row in output if tag == "all" or tag in row["tags"]]
        seeds = defaultdict(list)
        for row in chosen:
            seeds[row["seed"]].append(row)
        tag_result = {
            "root_count": len(chosen), "natural_seed_count": len(seeds),
            "model_gap_roots": sum(row["model_gap"] for row in chosen),
            "model_gap_seeds": sum(any(row["model_gap"] for row in group)
                                   for group in seeds.values()),
        }
        for reference in frozen["continuation_references"]:
            for role in ("anchored", "shape", "highfan_witness", "immediate_hu"):
                def delta(row):
                    return row["references"][reference][
                        "role_minus_r18_mean_own_net"][role]
                eligible = [row for row in chosen if delta(row) is not None]
                per_root = [delta(row) for row in eligible]
                complete_seed = [
                    sum(delta(row) for row in group) / len(group)
                    for group in seeds.values() if all(delta(row) is not None for row in group)
                ]
                largest = max(complete_seed, key=abs) if complete_seed else None
                tag_result[reference + "." + role + "_minus_r18"] = {
                    "scored_roots": _stats(per_root),
                    "complete_seed_clusters": _stats(complete_seed),
                    "largest_abs_seed_mean_net": largest,
                    "mean_without_largest_abs_seed": (
                        (sum(complete_seed) - largest) / (len(complete_seed) - 1)
                        if len(complete_seed) > 1 else None),
                }
        result[tag] = tag_result
    reference_signs = Counter()
    for row in output:
        if (row["model_gap"] or row["roles"]["anchored"] == row["roles"]["r18"]):
            continue
        a, b = (row["references"][name]["role_minus_r18_mean_own_net"]["anchored"]
                for name in frozen["continuation_references"])
        category = ("both_zero" if a == b == 0 else
                    "one_zero" if a == 0 or b == 0 else
                    "same_sign" if (a > 0) == (b > 0) else "opposite")
        reference_signs[category] += 1
    return {
        "scope": "opened_multi_root_conditional_diagnostic_not_full_table_or_policy_strength",
        "freeze_commit": report["pre_outcome_freeze_commit"],
        "root_count": len(output),
        "natural_seed_count": len({row["seed"] for row in output}),
        "teacher_action_worlds": report["row_count"],
        "rule_payoff_checks": report["rule_payoff_checks"],
        "gate_status": "diagnostic_only_general_draw_value_failed_and_model_coverage_incomplete",
        "changed_action_reference_signs": {
            name: reference_signs[name] for name in
            ("same_sign", "opposite", "one_zero", "both_zero")},
        "segments": result,
        "roots": output,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(_load(args.teacher), _load(args.freeze), args.freeze),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
