#!/usr/bin/env python3
"""只读审计 G186 同世界动作的目标单局互斥终局；不拟合候选。"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


DEFAULT_ROWS = (
    Path(__file__).resolve().parents[1]
    / "review/freematch-deep-dive-20260925/evidence"
    / "g186-multi-action-full-table-teacher-20260928/rows.jsonl"
)
OUTCOMES = ("self_high", "self_low", "other_win", "draw")


def _target_hand(outcome: dict, round_no: int) -> dict:
    """取唯一目标单局已证结算；四座增量固定按座位 0—3。"""

    hands = [hand for hand in outcome["hands"] if hand["round_no"] == round_no]
    if len(hands) != 1:
        raise ValueError("分支缺唯一目标单局结算")
    hand = hands[0]
    delta = hand["score_delta"]
    if (hand.get("result_confirmed") is not True or len(delta) != 4
            or any(type(value) is not int for value in delta)
            or sum(delta) != 0):
        raise ValueError("目标单局四座结算未确认或不守恒")
    return hand


def _label(hand: dict, seat: int) -> str:
    """终局互斥标签；本人≥4番仅为这次稀疏度审计的显式分层。"""

    if type(hand["is_draw"]) is not bool:
        raise ValueError("目标单局流局标志不是布尔值")
    if hand["is_draw"]:
        if hand["winner_seat"] is not None:
            raise ValueError("流局不得同时有赢家")
        return "draw"
    winner = hand["winner_seat"]
    fan = hand["fan"]
    if type(winner) is not int or winner not in range(4) or type(fan) is not int or fan < 1:
        raise ValueError("胡牌终局缺合法赢家或番数")
    if winner != seat:
        return "other_win"
    return "self_high" if fan >= 4 else "self_low"


def audit(rows_path: Path) -> dict:
    """按行动前根成组读取，统计动作结果与同世界父子结局变化。"""

    if not rows_path.is_file():
        raise ValueError("教师行文件不存在")
    all_labels: Counter[str] = Counter()
    parent_labels: Counter[str] = Counter()
    alternate_labels: Counter[str] = Counter()
    paired: Counter[str] = Counter()
    roots = worlds = action_worlds = paired_worlds = 0
    seen_roots: set[tuple] = set()
    with rows_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            identity = row["window_identity"]
            seat = identity["focal_seat"]
            round_no = identity["round_no"]
            parent = identity["parent_action"]
            key = (identity["mix"], identity["root_index"], seat,
                   round_no, identity["observation_sha256"])
            if key in seen_roots or type(seat) is not int or seat not in range(4):
                raise ValueError("重复或无效的行动前根身份")
            seen_roots.add(key)
            roots += 1
            sample_keys = set()
            for world in row["paired_worlds"]:
                sample_key = world["sample_key"]
                if sample_key in sample_keys:
                    raise ValueError("同根重复隐藏世界")
                sample_keys.add(sample_key)
                worlds += 1
                actions = world["outcomes"]
                if parent not in actions or set(actions) != {
                    parent, *row["alternate_actions"]
                }:
                    raise ValueError("同世界动作集合与冻结候选不一致")
                labels = {
                    action: _label(_target_hand(outcome, round_no), seat)
                    for action, outcome in actions.items()
                }
                for action, label in labels.items():
                    all_labels[label] += 1
                    (parent_labels if action == parent else alternate_labels)[label] += 1
                    action_worlds += 1
                for action, label in labels.items():
                    if action == parent:
                        continue
                    paired[labels[parent] + "->" + label] += 1
                    paired_worlds += 1
            if len(sample_keys) != 8:
                raise ValueError("G186 每根必须有八个相关隐藏世界")
    if not roots:
        raise ValueError("教师行为空")
    if sum(all_labels.values()) != action_worlds or sum(paired.values()) != paired_worlds:
        raise ValueError("互斥标签计数不守恒")
    return {
        "source_sha256": sha256(rows_path.read_bytes()).hexdigest(),
        "roots": roots,
        "worlds": worlds,
        "action_worlds": action_worlds,
        "paired_alternative_worlds": paired_worlds,
        "target_hand_labels": {key: all_labels[key] for key in OUTCOMES},
        "parent_labels": {key: parent_labels[key] for key in OUTCOMES},
        "alternative_labels": {key: alternate_labels[key] for key in OUTCOMES},
        "pair_changed_category": sum(
            count for key, count in paired.items()
            if key.split("->")[0] != key.split("->")[1]
        ),
        "pair_categories": dict(sorted(paired.items())),
        "scope": "frozen_G186_selected_width_actions_diagnostic_only",
    }


def main() -> None:
    """打印可复算 JSON；只读输入，不写训练产物或修改冻结证据。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=Path, default=DEFAULT_ROWS)
    args = parser.parse_args()
    print(json.dumps(audit(args.rows), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
