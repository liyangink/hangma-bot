"""R18 v2 四种已授权入口的冻结身份与失配拒绝。"""

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
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.r18_integrated_positive_v2_release import (
    R18IntegratedPositiveV2ReleasePolicy,
    R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES,
    R18_INTEGRATED_POSITIVE_V2_CANDIDATE_ID,
    R18_INTEGRATED_POSITIVE_V2_KNOWN_GUIDE_VERSION,
    R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
    R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY,
    R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
    R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
)
from hangma_bot.policy.r18_integrated_positive_v2_rules_20260929_release import (
    R18IntegratedPositiveV2Rules20260929ReleasePolicy,
    R18_V2_RULES_20260929_RELEASE_PACKAGE_ID,
    R18_V2_RULES_20260929_SOURCE_HASH,
)


def _config_data(tmp_path: Path, mode: str) -> dict[str, object]:
    """用假凭证构造真实入口配置，不进行网络请求。"""

    return {
        "mode": mode,
        "token_kind": "official" if mode in ("auto_match", "official_tournament") else "test",
        "token": "fixture-not-a-real-token",
        "base_url": "https://platform.invalid",
        "expected_tournament_id": None if mode == "auto_match" else "t-r18-v2",
        "known_guide_version": R18_INTEGRATED_POSITIVE_V2_KNOWN_GUIDE_VERSION,
        "audit_root": str(tmp_path / mode),
        "strategy": R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY,
        "expected_policy_release_id": R18_V2_RULES_20260929_RELEASE_PACKAGE_ID,
    }


def test_v2_release_identity_is_frozen_and_not_default() -> None:
    policy = R18IntegratedPositiveV2ReleasePolicy(
        rules_source_hash=R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
        value_analysis_sha256=R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
    )
    metadata = policy.release_metadata
    assert R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY in AVAILABLE_STRATEGIES
    assert DEFAULT_STRATEGY != R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY
    assert metadata["release_package_id"] == R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID
    assert metadata["candidate_id"] == R18_INTEGRATED_POSITIVE_V2_CANDIDATE_ID
    assert tuple(metadata["allowed_modes"]) == R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES
    assert metadata["official_tournament_allowed"] is True
    assert metadata["production_default"] is False
    assert "p69_table_confirmation" in metadata["evidence_sha256"]


@pytest.mark.parametrize("mode", R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES)
def test_v2_release_assembles_only_with_matching_binding_and_rule_scope(
    tmp_path: Path, mode: str
) -> None:
    config = runtime_config_from_mapping(_config_data(tmp_path, mode))
    session = FakeTournamentSession(bootstrap=None)
    if mode == "auto_match":
        assembled = build_auto_match_runtime(
            config, AutoMatchSettings(), session_factory=lambda: session
        )
    else:
        assembled = build_runtime(config, session_factory=lambda: session)
    assert isinstance(assembled.policy, R18IntegratedPositiveV2Rules20260929ReleasePolicy)
    assert assembled.runtime._value_limits is not None
    assert assembled.runtime._manifest_extra["policy_release"]["release_package_id"] == (
        R18_V2_RULES_20260929_RELEASE_PACKAGE_ID
    )
    assert assembled.runtime._rules_factory(
        RuleConfig("hangma-mvp-v10-public-counts", 1, False)
    ).__class__.__name__ == "HangmaRules"
    for bad in (
        RuleConfig("hangma-mvp-v10-public-counts", 2, False),
        RuleConfig("hangma-mvp-v10-public-counts", 1, True),
        RuleConfig("other-rules", 1, False),
    ):
        with pytest.raises(ValueError, match="测试范围要求"):
            assembled.runtime._rules_factory(bad)


@pytest.mark.parametrize("release_id", (None, "0" * 64,
                                       R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID))
def test_v2_release_rejects_missing_or_stale_binding(
    tmp_path: Path, release_id: str | None
) -> None:
    data = _config_data(tmp_path, "auto_match")
    if release_id is None:
        del data["expected_policy_release_id"]
    else:
        data["expected_policy_release_id"] = release_id
    with pytest.raises(ValueError, match="发布包"):
        runtime_config_from_mapping(data)


def test_v2_release_rejects_old_guide_and_raw_research_name(tmp_path: Path) -> None:
    data = _config_data(tmp_path, "official_tournament")
    data["known_guide_version"] = R18_INTEGRATED_POSITIVE_V2_KNOWN_GUIDE_VERSION - 1
    with pytest.raises(ValueError, match="官方指南 v34"):
        runtime_config_from_mapping(data)
    data["known_guide_version"] = R18_INTEGRATED_POSITIVE_V2_KNOWN_GUIDE_VERSION
    data["strategy"] = "action_value:r18_integrated_positive_v2"
    with pytest.raises(ValueError, match="研究候选"):
        runtime_config_from_mapping(data)


def test_v2_release_rejects_dependency_drift() -> None:
    with pytest.raises(RuntimeError, match="分值分析依赖摘要漂移"):
        R18IntegratedPositiveV2ReleasePolicy(
            rules_source_hash=R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
            value_analysis_sha256="0" * 64,
        )
    with pytest.raises(RuntimeError, match="完整规则源摘要漂移"):
        R18IntegratedPositiveV2ReleasePolicy(
            rules_source_hash="0" * 64,
            value_analysis_sha256=R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
        )
    current = R18IntegratedPositiveV2Rules20260929ReleasePolicy(
        rules_source_hash=R18_V2_RULES_20260929_SOURCE_HASH,
        value_analysis_sha256=R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
    )
    assert current.release_metadata["release_package_id"] == (
        R18_V2_RULES_20260929_RELEASE_PACKAGE_ID
    )
    with pytest.raises(RuntimeError, match="当前规则发布包源码摘要漂移"):
        R18IntegratedPositiveV2Rules20260929ReleasePolicy(
            rules_source_hash=R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
            value_analysis_sha256=R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
        )
