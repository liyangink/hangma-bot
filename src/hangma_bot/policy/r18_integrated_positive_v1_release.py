"""R18 累计能力候选的人工批准真实环境冻结包。

该包把候选源码、候选身份、规则范围和 P45—P48 证据摘要绑定为一个
不可变发布候选身份。它只由组合根在人工批准的测试房、测试赛事和自由赛
模式显式装配；正式赛事仍由 ``RuntimeConfig`` 拒绝。
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Mapping

from hangma_bot.hangma import value_analysis
from hangma_bot.hangma.interface import ValueAnalysisLimits

from .action_value_policy import ActionValuePolicy
from .action_value_seeds import ActionValueScorer
from .r18_integrated_positive_v1 import (
    R18_INTEGRATED_POSITIVE_V1_NAME,
    R18_INTEGRATED_POSITIVE_V1_SHA256,
    R18_INTEGRATED_POSITIVE_V1_SOURCE,
)


R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY = "r18_integrated_positive_v1"
R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID = (
    "1c44c5a56ebd88f5a2d5a9cbf3ae37ad66e105d678b6478dc85ac76ef2855416"
)
R18_INTEGRATED_POSITIVE_V1_RULESET_VERSION = "hangma-mvp-v10-public-counts"
R18_INTEGRATED_POSITIVE_V1_KNOWN_GUIDE_VERSION = 34
R18_INTEGRATED_POSITIVE_V1_ALLOWED_MODES = (
    "test_room",
    "test_tournament",
    "auto_match",
)
R18_INTEGRATED_POSITIVE_V1_EVIDENCE = {
    "p45_capability_merge": "5c5c3fee66b19c5b092671fd52eed8f50e77e7a92d97d1955f7bc5f153874c9b",
    "p46_fresh_table_safety": "62063b2c0506f3e9904692882bcd543cb163f9fb5889e1bdf0d950a268286ad9",
    "p47_package_registration": "1e277e8567e6994ba0e0d60b769df175e435393bde8c5e2c8a9c2952306157ba",
    "p48_full_chain_preflight": "fd8962c07921cefea9ddabbad2002777a17fd8a171f2ef6bd544fe1a57e55825",
    "p55_white_value_route_repair": "a020a4c340953a9cb5de634d4a1605b23482b9ac0186397c47f2e85ac4a5940c",
}
R18_INTEGRATED_POSITIVE_V1_VALUE_ANALYSIS_SHA256 = (
    "ec2a2416d654b4cec1dd4aa79b455d1cd5f12a2d6d46f6f11da91f722c50f0f8"
)
R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH = (
    "d8a6346c8303a891523952bff618989931beb62fa041a511805b807ee471a6ef"
)


def _source_digest() -> str:
    return hashlib.sha256(
        R18_INTEGRATED_POSITIVE_V1_SOURCE.encode("utf-8")
    ).hexdigest()


def _value_analysis_digest() -> str:
    """返回当前规则分值分析源码摘要；源码不可读时拒绝网络装配。"""

    source_path = inspect.getsourcefile(value_analysis)
    if source_path is None:
        raise RuntimeError("无法定位分值分析源码；拒绝装配 R18 发布候选")
    return hashlib.sha256(Path(source_path).read_bytes()).hexdigest()


def _release_payload() -> dict[str, Any]:
    return {
        "schema": "r18-integrated-positive-v1-release/2",
        "strategy": R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
        "candidate_name": R18_INTEGRATED_POSITIVE_V1_NAME,
        "candidate_id": R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID,
        "candidate_source_sha256": R18_INTEGRATED_POSITIVE_V1_SHA256,
        "value_analysis_sha256": R18_INTEGRATED_POSITIVE_V1_VALUE_ANALYSIS_SHA256,
        "rules_source_hash": R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH,
        "ruleset_version": R18_INTEGRATED_POSITIVE_V1_RULESET_VERSION,
        "known_guide_version_min": R18_INTEGRATED_POSITIVE_V1_KNOWN_GUIDE_VERSION,
        "base_score": 1,
        "you_cai_bi_kao": False,
        "value_analysis_limits": {
            "max_expansions": ValueAnalysisLimits().max_expansions,
            "max_routes_per_candidate": ValueAnalysisLimits().max_routes_per_candidate,
        },
        "allowed_modes": R18_INTEGRATED_POSITIVE_V1_ALLOWED_MODES,
        "evidence_sha256": dict(R18_INTEGRATED_POSITIVE_V1_EVIDENCE),
        "human_approval_date": "2026-09-23",
        "official_tournament_allowed": False,
        "production_default": False,
    }


R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID = hashlib.sha256(
    json.dumps(
        _release_payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


class R18IntegratedPositiveV1ReleasePolicy(ActionValuePolicy):
    """绑定 P49 人工审核结果的 R18 真实环境候选策略。"""

    def __init__(self, *, rules_source_hash: str) -> None:
        if _source_digest() != R18_INTEGRATED_POSITIVE_V1_SHA256:
            raise RuntimeError("R18 发布候选源码摘要漂移；拒绝装配")
        if _value_analysis_digest() != R18_INTEGRATED_POSITIVE_V1_VALUE_ANALYSIS_SHA256:
            raise RuntimeError("R18 分值分析依赖摘要漂移；拒绝装配")
        if rules_source_hash != R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH:
            raise RuntimeError("R18 完整规则源摘要漂移；拒绝装配")
        super().__init__(
            ActionValueScorer(
                R18_INTEGRATED_POSITIVE_V1_NAME,
                R18_INTEGRATED_POSITIVE_V1_SOURCE,
            ),
            value_limits=ValueAnalysisLimits(),
        )
        self.policy_id = (
            "release:r18-integrated-positive-v1:"
            + R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID[:12]
        )

    @property
    def release_metadata(self) -> Mapping[str, Any]:
        """返回写入运行清单的完整冻结身份，不包含凭证或运行期状态。"""

        return {
            **_release_payload(),
            "release_package_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        }


__all__ = [
    "R18IntegratedPositiveV1ReleasePolicy",
    "R18_INTEGRATED_POSITIVE_V1_ALLOWED_MODES",
    "R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID",
    "R18_INTEGRATED_POSITIVE_V1_KNOWN_GUIDE_VERSION",
    "R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID",
    "R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH",
    "R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY",
    "R18_INTEGRATED_POSITIVE_V1_VALUE_ANALYSIS_SHA256",
]
