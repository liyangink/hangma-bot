"""契约验收向量的消费测试（评估线消费面）。

parallel-contracts §9：身份哈希、四进程重启合并、真实分块形态、缺牌墙分级
必须一致，每条线在自己的测试目录实现这些向量的消费测试。评估线消费的是
身份哈希（hand_id/split_group_id：决策行关联与结果聚类）与预算平移
（budget_translation：固定决策比较的时钟平移）。四进程合并与分块形态的
读写由审计/模拟线验收；这里额外验证归档房间向量的 hand_id 派生一致性。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hangma_bot.offline.evaluate import translate_budget
from hangma_bot.offline.evaluation_results import hand_id, split_group_id
from hangma_bot.policy.interface import DecisionBudget

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS_PATH = REPO_ROOT / "doc" / "implementation" / "contracts" / "contract-vectors.json"
VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

OFFICIAL_NAMESPACE = "hangma-official"


def test_identity_cases_match_vector_hand_id():
    for case in VECTORS["identity_cases"]:
        namespace, tournament_id, game_id, round_no = case["key"]
        assert hand_id(namespace, tournament_id, game_id, round_no) == case["hand_id"]


def test_identity_cases_match_vector_split_group_id():
    for case in VECTORS["identity_cases"]:
        namespace, tournament_id, game_id, round_no = case["key"]
        assert split_group_id([namespace, tournament_id]) == case["official_split_group_id"]


def test_invalid_identity_cases_raise_value_error():
    for case in VECTORS["invalid_identity_cases"]:
        with pytest.raises(ValueError):
            hand_id(*case["key"])


def test_archived_room_vectors_derive_consistent_hand_ids():
    for case in VECTORS["archived_room_cases"]:
        hand = case["hands"][0]
        assert (
            hand_id(OFFICIAL_NAMESPACE, case["room_id"], case["game_id"], hand["round_no"])
            == hand["hand_id"]
        )
        assert (
            split_group_id([OFFICIAL_NAMESPACE, case["room_id"]])
            == hand["split_group_id"]
        )


def test_budget_translation_matches_vector():
    budget = DecisionBudget(*VECTORS["budget_translation"]["old_deadlines"])
    translated = translate_budget(
        budget,
        VECTORS["budget_translation"]["old_origin"],
        VECTORS["budget_translation"]["new_origin"],
    )
    assert (
        translated.enhancement_deadline_monotonic,
        translated.fallback_deadline_monotonic,
        translated.latest_send_at_monotonic,
    ) == tuple(VECTORS["budget_translation"]["new_deadlines"])


def test_budget_translation_preserves_intervals_and_order():
    budget = DecisionBudget(10.0, 10.5, 10.9)
    translated = translate_budget(budget, old_origin_monotonic=10.0, new_origin_monotonic=500.0)
    assert translated.enhancement_deadline_monotonic == 500.0
    assert translated.fallback_deadline_monotonic == 500.5
    assert translated.latest_send_at_monotonic == 500.9


def test_budget_translation_rejects_reversed_deadlines():
    with pytest.raises(ValueError):
        DecisionBudget(10.9, 10.5, 10.0)
