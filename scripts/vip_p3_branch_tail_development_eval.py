"""在已打开的完整动作教师根诊断下一摸牌分支末端探针。

全部动作可评价，但结局已被上一轮研发打开；结果只可用于否证或
定位错误，不可当作新策略的独立留出成绩或自然完整桌成绩。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_anchored_value_probe import predict_observation as anchored_predict
from scripts.vip_p3_branch_tail_probe import predict_observation as branch_predict
from scripts.vip_p3_competing_value_probe import _load


def _mean(row: dict, action_key: str, seat: int) -> float:
    """同根相关隐藏世界的本座完整单局净分均值。"""

    samples = row["outcomes_by_action"][action_key]
    if [item["sample"] for item in samples] != list(range(row["sample_count"])):
        raise ValueError("教师世界样本编号不连续")
    return sum(item["terminal"]["score_delta"][seat] for item in samples) / len(samples)


def evaluate(scan: dict, branch: dict, anchored: dict,
             shape: dict, r18: dict) -> dict:
    """按观察根等权比较新旧支付探针，所有结果均注明已开。"""

    if (scan.get("scope") != "pre_outcome_all_action_root_scan_not_strategy_value"
            or branch.get("schema") != "vip-p3-branch-tail-probe/1"
            or anchored.get("schema") != "vip-p3-anchored-payoff-probe/1"
            or shape.get("continuation_reference") != "shape"
            or r18.get("continuation_reference") != "r18_frozen"
            or any(item.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}
                   for item in (scan, branch, anchored, shape, r18))):
        raise ValueError("分支末端诊断的来源合同不匹配")
    if hashlib.sha256(Path("scripts/vip_p3_branch_tail_probe.py").read_bytes()
                      ).hexdigest() != branch["feature_source_sha256"]:
        raise ValueError("分支末端特征源码已漂移")
    if branch["training_sources"] != anchored["training_sources"]:
        raise ValueError("新旧模型训练教师不同")
    training_ids = set()
    for item in branch["training_sources"]:
        path = Path(item["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("训练教师摘要漂移")
        training_ids.update(row["root_id"] for row in _load(path)["rows"])
    teachers = {name: {row["root_id"]: row for row in report["rows"]}
                for name, report in (("shape", shape), ("r18_frozen", r18))}
    scan_ids = {row["root_id"] for row in scan["rows"]}
    if (len(scan_ids) != scan["root_count"] or scan_ids & training_ids
            or any(set(rows) != scan_ids for rows in teachers.values())):
        raise ValueError("诊断观察根泄漏训练、重复或教师缺根")

    rows = []
    for source in scan["rows"]:
        observation = observation_from_json(source["observation"])
        root_id = hashlib.sha256(repr(observation).encode()).hexdigest()
        if root_id != source["root_id"]:
            raise ValueError("诊断玩家观察摘要不符")
        branch_key = branch_predict(observation, branch)[0]["action_key"]
        anchored_key = anchored_predict(observation, anchored)[0]["action_key"]
        shape_key = source["shape_first_action_key"]
        keys = source["legal_action_keys"]
        if any(key not in keys for key in (branch_key, anchored_key, shape_key)):
            raise ValueError("诊断预测首选不是合法动作")
        gains = {}
        for name, teacher in teachers.items():
            row = teacher[root_id]
            if (row["observation"] != source["observation"]
                    or row["legal_action_keys"] != keys):
                raise ValueError("诊断教师观察或合法动作不符")
            own = {key: _mean(row, key, observation.seat)
                   for key in (branch_key, anchored_key, shape_key)}
            gains[name] = {
                "branch_minus_shape": own[branch_key] - own[shape_key],
                "anchored_minus_shape": own[anchored_key] - own[shape_key],
                "branch_minus_anchored": own[branch_key] - own[anchored_key],
            }
        rows.append({"seed": source["seed"], "root_id": root_id,
                     "phase": source["phase"], "branch_action": branch_key,
                     "anchored_action": anchored_key, "shape_action": shape_key,
                     "gains": gains})

    summary = {}
    for segment, selected in (("all", rows),
                              ("draw", [row for row in rows if row["phase"] == "draw"]),
                              ("response", [row for row in rows if row["phase"] != "draw"])):
        stats = {"root_count": len(selected),
                 "branch_changed_vs_shape": sum(row["branch_action"] !=
                                                row["shape_action"] for row in selected),
                 "branch_changed_vs_anchored": sum(row["branch_action"] !=
                                                   row["anchored_action"] for row in selected)}
        for reference in teachers:
            for comparison in ("branch_minus_shape", "anchored_minus_shape",
                               "branch_minus_anchored"):
                values = [row["gains"][reference][comparison] for row in selected]
                signs = Counter("positive" if value > 0 else "negative" if value < 0
                                else "zero" for value in values)
                stats[f"{reference}.{comparison}"] = {
                    "mean_net_per_root": sum(values) / len(values) if values else None,
                    "root_signs": {name: signs[name] for name in
                                   ("positive", "negative", "zero")},
                }
        summary[segment] = stats
    return {"scope": "opened_branch_tail_development_not_independent_validation",
            "root_count": len(rows), "summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("scan", "branch", "anchored", "shape", "r18"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(*(_load(getattr(args, name)) for name in
                                ("scan", "branch", "anchored", "shape", "r18"))),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
