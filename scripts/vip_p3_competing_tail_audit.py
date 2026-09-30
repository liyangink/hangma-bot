"""同根两名离线续打者的互斥终局与后继价值敏感性审计。

动作世界共享观察根和隐藏世界，计数只作标签诊断，不是独立桌赛成绩。
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path


_SCOPE = "P3_offline_teacher_labels_only_not_candidate_policy_value"
_OUTCOMES = ("self_low", "self_high", "other_win", "draw")


def _label(terminal: dict, seat: int) -> str:
    """按四座终局只记一个类别；四番只是本人胡的互斥分层。"""

    delta = terminal.get("score_delta")
    if (not isinstance(delta, list) or len(delta) != 4
            or any(type(value) is not int for value in delta)
            or sum(delta) != 0):
        raise ValueError("教师终局缺守恒的四座整数积分")
    if type(terminal.get("is_draw")) is not bool:
        raise ValueError("教师终局缺流局布尔事实")
    winner = terminal.get("winner_seat")
    if terminal["is_draw"]:
        if winner is not None:
            raise ValueError("流局不得有赢家")
        if any(delta):
            raise ValueError("目标规则流局必须是四座零支付")
        return "draw"
    if type(winner) is not int or winner not in range(4):
        raise ValueError("胡牌终局缺有效赢家")
    if type(terminal.get("fan")) is not int or terminal["fan"] < 1:
        raise ValueError("胡牌终局缺有效番数")
    return ("other_win" if winner != seat else
            "self_high" if terminal["fan"] >= 4 else "self_low")


def audit(first: dict, second: dict) -> dict:
    """配对同一观察、动作及隐藏世界，核类别质量与积分差方向。"""

    if (first.get("scope") != _SCOPE or second.get("scope") != _SCOPE
            or first.get("reference") != second.get("reference")
            or first.get("continuation_reference") ==
            second.get("continuation_reference")
            or first.get("start_seed") != second.get("start_seed")
            or first.get("requested_seeds") != second.get("requested_seeds")
            or first.get("worlds_per_root") != second.get("worlds_per_root")
            or first.get("selection_tag") != second.get("selection_tag")):
        raise ValueError("两份教师账的来源、抽样或续打者不匹配")
    labels = (first["continuation_reference"], second["continuation_reference"])
    if not all(isinstance(name, str) and name for name in labels):
        raise ValueError("教师续打者缺稳定名称")
    by_id = {row["root_id"]: row for row in second["rows"]}
    if (len(by_id) != len(second["rows"])
            or len(first["rows"]) != len(by_id)
            or len({row["root_id"] for row in first["rows"]}) != len(by_id)):
        raise ValueError("观察根身份重复或两份教师账根数不一致")
    outcomes = {name: Counter() for name in labels}
    high_roots = {name: Counter() for name in labels}
    pair_signs: Counter[str] = Counter()
    opposite_roots = set()
    first_event_changed = 0
    root_rows = []
    for row in first["rows"]:
        other = by_id.pop(row["root_id"], None)
        if (other is None or any(row.get(key) != other.get(key) for key in
                                 ("seed", "observation", "legal_action_keys", "sample_count"))):
            raise ValueError("同根玩家观察、合法动作或隐藏世界数不一致")
        keys = row["legal_action_keys"]
        samples = row["sample_count"]
        seat = row["observation"]["seat"]
        if (not keys or len(set(keys)) != len(keys) or type(seat) is not int
                or seat not in range(4) or samples != first["worlds_per_root"]):
            raise ValueError("根的合法动作、座位或样本数无效")
        root_points = {}
        root_outcomes = {}
        for name, data in zip(labels, (row, other)):
            arms = data["outcomes_by_action"]
            if set(arms) != set(keys):
                raise ValueError("教师账缺全合法动作")
            root_points[name] = {}
            root_outcomes[name] = Counter()
            for key in keys:
                arm = arms[key]
                if [item.get("sample") for item in arm] != list(range(samples)):
                    raise ValueError("同根动作的隐藏世界编号不守恒")
                points = []
                for item in arm:
                    category = _label(item["terminal"], seat)
                    outcomes[name][category] += 1
                    root_outcomes[name][category] += 1
                    if category == "self_high":
                        high_roots[name][row["seed"]] += 1
                    points.append(item["terminal"]["score_delta"][seat])
                root_points[name][key] = sum(points)
        for key in keys:
            for left, right in zip(row["outcomes_by_action"][key],
                                   other["outcomes_by_action"][key]):
                if left.get("first_event_key") != right.get("first_event_key"):
                    first_event_changed += 1
        baseline = keys[0]  # 仅规范首项，不代表 R18 或强策略。
        for key in keys[1:]:
            a, b = (root_points[name][key] - root_points[name][baseline]
                    for name in labels)
            if a == b == 0:
                category = "both_zero"
            elif a == 0 or b == 0:
                category = "one_zero"
            elif (a > 0) == (b > 0):
                category = "same_sign"
            else:
                category = "opposite"
                opposite_roots.add(row["root_id"])
            pair_signs[category] += 1
        root_rows.append({
            "seed": row["seed"], "root_id": row["root_id"],
            "action_count": len(keys),
            "outcomes": {name: {category: root_outcomes[name][category]
                                for category in _OUTCOMES} for name in labels},
        })
    if by_id:
        raise ValueError("第二份教师账有未配对观察根")
    action_worlds = sum(len(row["legal_action_keys"]) * row["sample_count"]
                        for row in first["rows"])
    if any(sum(outcomes[name].values()) != action_worlds for name in labels):
        raise ValueError("互斥终局类别质量不守恒")
    return {
        "scope": "paired_offline_reference_tail_diagnostic_not_candidate_strength",
        "references": labels, "root_count": len(root_rows),
        "worlds_per_root": first["worlds_per_root"],
        "action_worlds_per_reference": action_worlds,
        "first_event_key_changed_action_worlds": first_event_changed,
        "outcomes": {name: {category: outcomes[name][category]
                            for category in _OUTCOMES} for name in labels},
        "self_high_by_root": {name: dict(sorted(high_roots[name].items()))
                              for name in labels},
        "paired_action_directions_vs_first_legal": {
            category: pair_signs[category]
            for category in ("both_zero", "one_zero", "same_sign", "opposite")
        },
        "roots_with_opposite_action_pair": len(opposite_roots),
        "rows": sorted(root_rows, key=lambda item: (item["seed"], item["root_id"])),
    }


def _load(path: Path) -> dict:
    """读取 UTF-8 JSON 或 gzip JSON；不修改原始教师账。"""

    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    """将配对守恒及根级方向账输出为严格 JSON。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(_load(args.first), _load(args.second)),
                     ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
