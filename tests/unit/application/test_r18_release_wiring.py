"""R18 P49 人工批准冻结包的真实入口范围与身份审计。"""

from __future__ import annotations

from pathlib import Path

import pytest

from fakes import FakeTournamentSession
from hangma_bot.application.auto_match_runtime import AutoMatchSettings
from hangma_bot.bootstrap import (
    AVAILABLE_STRATEGIES,
    DEFAULT_STRATEGY,
    build_auto_match_runtime,
    build_runtime,
    runtime_config_from_mapping,
)
from hangma_bot.policy.r18_integrated_positive_v1_release import (
    R18IntegratedPositiveV1ReleasePolicy,
    R18_INTEGRATED_POSITIVE_V1_ALLOWED_MODES,
    R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID,
    R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
    R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH,
    R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
    R18_INTEGRATED_POSITIVE_V1_VALUE_ANALYSIS_SHA256,
)


def _config(tmp_path: Path, mode: str, token_kind: str):
    return runtime_config_from_mapping(
        {
            "mode": mode,
            "token_kind": token_kind,
            "token": "fixture-not-a-real-token",
            "base_url": "https://platform.invalid",
            "expected_tournament_id": "" if mode == "auto_match" else "t-r18",
            "known_guide_version": 34,
            "audit_root": str(tmp_path),
            "strategy": R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
            "expected_policy_release_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        }
    )


def test_release_package_identity_and_default_are_frozen() -> None:
    policy = R18IntegratedPositiveV1ReleasePolicy(
        rules_source_hash=R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH,
        value_analysis_sha256=R18_INTEGRATED_POSITIVE_V1_VALUE_ANALYSIS_SHA256,
    )
    metadata = policy.release_metadata

    assert R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY in AVAILABLE_STRATEGIES
    assert DEFAULT_STRATEGY != R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY
    assert metadata["release_package_id"] == R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID
    assert metadata["candidate_id"] == R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID
    assert metadata["value_analysis_sha256"] == (
        R18_INTEGRATED_POSITIVE_V1_VALUE_ANALYSIS_SHA256
    )
    assert metadata["rules_source_hash"] == R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH
    assert "p55_white_value_route_repair" in metadata["evidence_sha256"]
    assert tuple(metadata["allowed_modes"]) == R18_INTEGRATED_POSITIVE_V1_ALLOWED_MODES
    assert metadata["official_tournament_allowed"] is False
    assert metadata["production_default"] is False
    assert policy.policy_id.startswith("release:r18-integrated-positive-v1:")


def test_release_candidate_rejects_rule_source_drift() -> None:
    with pytest.raises(RuntimeError, match="完整规则源摘要漂移"):
        R18IntegratedPositiveV1ReleasePolicy(
            rules_source_hash="0" * 64,
            value_analysis_sha256=R18_INTEGRATED_POSITIVE_V1_VALUE_ANALYSIS_SHA256,
        )


def test_release_candidate_rejects_value_analysis_drift() -> None:
    with pytest.raises(RuntimeError, match="分值分析依赖摘要漂移"):
        R18IntegratedPositiveV1ReleasePolicy(
            rules_source_hash=R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH,
            value_analysis_sha256="0" * 64,
        )


@pytest.mark.parametrize(
    "mode,token_kind",
    (("test_room", "test"), ("test_tournament", "test"), ("auto_match", "official")),
)
def test_historical_v1_release_fails_closed_on_current_rule_source(
    tmp_path: Path, mode: str, token_kind: str
) -> None:
    config = _config(tmp_path, mode, token_kind)
    session = FakeTournamentSession(bootstrap=None)
    with pytest.raises(RuntimeError, match="完整规则源摘要漂移"):
        if mode == "auto_match":
            build_auto_match_runtime(
                config,
                AutoMatchSettings(),
                session_factory=lambda: session,
            )
        else:
            build_runtime(config, session_factory=lambda: session)


def test_release_candidate_rejects_official_tournament(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="只获批测试房、测试赛事和自由赛"):
        _config(tmp_path, "official_tournament", "official")


def test_release_candidate_rejects_stale_known_guide(tmp_path: Path) -> None:
    data = {
        "mode": "test_tournament",
        "token_kind": "test",
        "token": "fixture-not-a-real-token",
        "base_url": "https://platform.invalid",
        "expected_tournament_id": "t-r18",
        "known_guide_version": 33,
        "audit_root": str(tmp_path),
        "strategy": R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
        "expected_policy_release_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
    }
    with pytest.raises(ValueError, match="官方指南 v34"):
        runtime_config_from_mapping(data)


@pytest.mark.parametrize("release_id", (None, "0" * 64))
def test_release_candidate_rejects_missing_or_stale_package_binding(
    tmp_path: Path, release_id: str | None
) -> None:
    data = {
        "mode": "test_tournament",
        "token_kind": "test",
        "token": "fixture-not-a-real-token",
        "base_url": "https://platform.invalid",
        "expected_tournament_id": "t-r18",
        "known_guide_version": 34,
        "audit_root": str(tmp_path),
        "strategy": R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
    }
    if release_id is not None:
        data["expected_policy_release_id"] = release_id
    with pytest.raises(ValueError, match="发布包"):
        runtime_config_from_mapping(data)


def test_non_release_strategy_rejects_release_binding(tmp_path: Path) -> None:
    data = {
        "mode": "test_tournament",
        "token_kind": "test",
        "token": "fixture-not-a-real-token",
        "base_url": "https://platform.invalid",
        "expected_tournament_id": "t-r18",
        "known_guide_version": 34,
        "audit_root": str(tmp_path),
        "strategy": "weighted_heuristic_v2",
        "expected_policy_release_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
    }
    with pytest.raises(ValueError, match="冻结发布策略"):
        runtime_config_from_mapping(data)


def test_raw_research_name_remains_rejected_in_every_network_mode(tmp_path: Path) -> None:
    for mode, token_kind in (
        ("test_room", "test"),
        ("test_tournament", "test"),
        ("auto_match", "official"),
        ("official_tournament", "official"),
    ):
        data = {
            "mode": mode,
            "token_kind": token_kind,
            "token": "fixture-not-a-real-token",
            "base_url": "https://platform.invalid",
            "expected_tournament_id": "" if mode == "auto_match" else "t-r18",
            "known_guide_version": 23,
            "audit_root": str(tmp_path),
            "strategy": "action_value:r18_integrated_positive_v1",
        }
        with pytest.raises(ValueError, match="研究候选"):
            runtime_config_from_mapping(data)
