"""冻结研究候选的包内身份与离线接缝回归。"""

from __future__ import annotations

import hashlib

import pytest

from hangma_bot.bootstrap import AVAILABLE_STRATEGIES, build_research_policy
from hangma_bot.policy.action_value_policy import ActionValuePolicy
from hangma_bot.policy.action_value_seeds import build_sample_view
from hangma_bot.policy.research_candidates import (
    RESEARCH_CANDIDATE_NAMES,
    R18_INTEGRATED_POSITIVE_V1_NAME,
    R18_INTEGRATED_POSITIVE_V1_SHA256,
    R18_INTEGRATED_POSITIVE_V1_SOURCE,
    R18_INTEGRATED_POSITIVE_V2_NAME,
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
    R18_TWO_WEALTH_BAOTOU_V1_NAME,
    R18_TWO_WEALTH_BAOTOU_V1_SHA256,
    R18_TWO_WEALTH_BAOTOU_V1_SOURCE,
    build_research_candidate_scorer,
)


def test_r18_two_wealth_source_matches_frozen_normalized_digest() -> None:
    """包内源码必须与 P37 规范化父代的冻结摘要一致。"""
    assert hashlib.sha256(
        R18_TWO_WEALTH_BAOTOU_V1_SOURCE.encode("utf-8")
    ).hexdigest() == R18_TWO_WEALTH_BAOTOU_V1_SHA256
    assert RESEARCH_CANDIDATE_NAMES == (
        R18_TWO_WEALTH_BAOTOU_V1_NAME,
        R18_INTEGRATED_POSITIVE_V1_NAME,
        R18_INTEGRATED_POSITIVE_V2_NAME,
    )


def test_r18_integrated_source_matches_frozen_digest() -> None:
    """累计候选源码必须绑定 P45 合并父代的冻结摘要。"""
    assert hashlib.sha256(
        R18_INTEGRATED_POSITIVE_V1_SOURCE.encode("utf-8")
    ).hexdigest() == R18_INTEGRATED_POSITIVE_V1_SHA256


def test_r18_integrated_v2_source_matches_frozen_digest() -> None:
    """第二版累计候选必须绑定 P65 冻结源码摘要。"""
    assert hashlib.sha256(
        R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")
    ).hexdigest() == R18_INTEGRATED_POSITIVE_V2_SHA256


def test_r18_two_wealth_scorer_is_bounded_and_scores_complete_sample() -> None:
    """正式工厂仍经过受限执行器，并对样例动作表完整返回。"""
    scorer = build_research_candidate_scorer(R18_TWO_WEALTH_BAOTOU_V1_NAME)
    batch = scorer.score(build_sample_view())

    assert batch.status == "SCORED"
    assert {entry.action_key for entry in batch.entries} == {
        "discard:1w",
        "hu",
        "pass",
    }
    assert 0 < scorer.last_operation_count <= scorer.max_operations == 100_000


def test_r18_two_wealth_policy_is_offline_only() -> None:
    """活动父代可经离线组合根构造，但不进入真实网络策略清单。"""
    strategy = "action_value:r18_two_wealth_baotou_v1"
    policy = build_research_policy(strategy)

    assert isinstance(policy, ActionValuePolicy)
    assert policy.scorer_name == R18_TWO_WEALTH_BAOTOU_V1_NAME
    assert strategy not in AVAILABLE_STRATEGIES


def test_r18_integrated_policy_is_offline_only() -> None:
    """累计父代可离线构造，但仍不得进入真实网络策略清单。"""
    strategy = "action_value:r18_integrated_positive_v1"
    policy = build_research_policy(strategy)

    assert isinstance(policy, ActionValuePolicy)
    assert policy.scorer_name == R18_INTEGRATED_POSITIVE_V1_NAME
    assert strategy not in AVAILABLE_STRATEGIES


def test_r18_integrated_v2_policy_is_offline_only() -> None:
    """第二版累计父代可离线构造，但仍不得进入真实网络策略清单。"""
    strategy = "action_value:r18_integrated_positive_v2"
    policy = build_research_policy(strategy)

    assert isinstance(policy, ActionValuePolicy)
    assert policy.scorer_name == R18_INTEGRATED_POSITIVE_V2_NAME
    assert strategy not in AVAILABLE_STRATEGIES


def test_unknown_research_candidate_fails_closed() -> None:
    """注册表未知项不得静默替换为稳定种子。"""
    with pytest.raises(ValueError, match="未知 action_value 研究候选"):
        build_research_candidate_scorer("unknown")
