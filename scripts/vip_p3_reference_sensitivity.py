"""比较两名冻结续打者对同根、同隐藏世界合法动作差的影响。

只描述离线教师标签敏感性；不以动作对数冒充独立样本或策略成绩。
"""

from __future__ import annotations

import argparse
import gzip
import json
from itertools import combinations
from pathlib import Path


def compare(shape: dict, alternate: dict) -> dict:
    """逐根比较所有动作对的积分差方向，并保留根级分母。"""

    if (shape.get("scope") != "P3_offline_teacher_labels_only_not_candidate_policy_value"
            or alternate.get("scope") != shape["scope"]
            or shape.get("reference") != alternate.get("reference")
            or shape.get("continuation_reference", "shape") != "shape"
            or alternate.get("continuation_reference") != "r18_frozen"
            or shape.get("selection_tag") != alternate.get("selection_tag")
            or shape.get("worlds_per_root") != alternate.get("worlds_per_root")):
        raise ValueError("两份教师账的范围、选根或续打者不匹配")
    by_id = {row["root_id"]: row for row in alternate["rows"]}
    if len(by_id) != len(alternate["rows"]) or len(shape["rows"]) != len(by_id):
        raise ValueError("两份教师账根数或身份重复")
    rows = []
    for row in shape["rows"]:
        other = by_id.pop(row["root_id"], None)
        if (other is None or row["seed"] != other["seed"]
                or row["observation"] != other["observation"]
                or row["legal_action_keys"] != other["legal_action_keys"]
                or row["sample_count"] != other["sample_count"]):
            raise ValueError("同根玩家观察、合法动作或隐藏世界数不一致")
        seat = row["observation"]["seat"]
        if seat not in (0, 1, 2, 3):
            raise ValueError("玩家观察座位无效")
        values = {}
        high_fan = {}
        for label, data in (("shape", row), ("r18_frozen", other)):
            outcomes = data["outcomes_by_action"]
            if set(outcomes) != set(row["legal_action_keys"]):
                raise ValueError("全合法动作结果不完整")
            values[label] = {}
            high_fan[label] = 0
            for action_key in row["legal_action_keys"]:
                samples = outcomes[action_key]
                if ([item["sample"] for item in samples] !=
                        list(range(row["sample_count"]))):
                    raise ValueError("相关隐藏世界样本序号不守恒")
                values[label][action_key] = [
                    item["terminal"]["score_delta"][seat] for item in samples]
                high_fan[label] += sum(
                    item["terminal"]["winner_seat"] == seat
                    and item["terminal"]["fan"] >= 4 for item in samples)
        pair_counts = {"both_zero": 0, "both_nonzero_same_sign": 0,
                       "both_nonzero_opposite_sign": 0, "one_zero": 0}
        for first, second in combinations(row["legal_action_keys"], 2):
            differences = {
                label: sum(values[label][first]) - sum(values[label][second])
                for label in ("shape", "r18_frozen")
            }
            a, b = differences["shape"], differences["r18_frozen"]
            if a == 0 and b == 0:
                pair_counts["both_zero"] += 1
            elif a == 0 or b == 0:
                pair_counts["one_zero"] += 1
            elif (a > 0) == (b > 0):
                pair_counts["both_nonzero_same_sign"] += 1
            else:
                pair_counts["both_nonzero_opposite_sign"] += 1
        rows.append({"seed": row["seed"], "root_id": row["root_id"],
                     "action_count": len(row["legal_action_keys"]),
                     "sample_count": row["sample_count"],
                     "pair_counts": pair_counts,
                     "self_four_fan_action_worlds": high_fan})
    if by_id:
        raise ValueError("第二续打者有未配对根")
    return {
        "scope": "offline_continuation_sensitivity_not_candidate_policy_value",
        "root_count": len(rows),
        "worlds_per_root": shape["worlds_per_root"],
        "roots_with_opposite_pair": sum(
            row["pair_counts"]["both_nonzero_opposite_sign"] > 0 for row in rows),
        "roots_with_any_nonzero_pair": sum(
            row["pair_counts"]["both_nonzero_same_sign"]
            + row["pair_counts"]["both_nonzero_opposite_sign"]
            + row["pair_counts"]["one_zero"] > 0 for row in rows),
        "rows": sorted(rows, key=lambda row: row["seed"]),
    }


def _load(path: Path) -> dict:
    """只读取 JSON/gzip JSON 报告。"""

    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    """输出根级续打敏感性报告。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape-teacher", type=Path, required=True)
    parser.add_argument("--r18-teacher", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(_load(args.shape_teacher), _load(args.r18_teacher)),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
