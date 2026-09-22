"""R18 v2 四种真实环境模式共用的冻结发布包。

用户批准将已通过 P69 完整桌确认与 P71 全链预检的候选用于自由赛、
测试房、测试赛事和正式赛事。本包绑定候选、规则、条件分值分析和评测
证据的摘要；运行配置还须显式绑定本包身份。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from hangma_bot.hangma.interface import ValueAnalysisLimits

from .action_value_policy import ActionValuePolicy
from .action_value_seeds import ActionValueScorer
from .r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_NAME,
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY = "r18_integrated_positive_v2"
R18_INTEGRATED_POSITIVE_V2_CANDIDATE_ID = R18_INTEGRATED_POSITIVE_V2_SHA256
R18_INTEGRATED_POSITIVE_V2_RULESET_VERSION = "hangma-mvp-v10-public-counts"
R18_INTEGRATED_POSITIVE_V2_KNOWN_GUIDE_VERSION = 34
R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES = (
    "test_room",
    "test_tournament",
    "auto_match",
    "official_tournament",
)
R18_INTEGRATED_POSITIVE_V2_EVIDENCE = {
    "p45_capability_merge": "5c5c3fee66b19c5b092671fd52eed8f50e77e7a92d97d1955f7bc5f153874c9b",
    "p46_fresh_table_safety": "62063b2c0506f3e9904692882bcd543cb163f9fb5889e1bdf0d950a268286ad9",
    "p55_white_value_route_repair": "a020a4c340953a9cb5de634d4a1605b23482b9ac0186397c47f2e85ac4a5940c",
    "p66b_candidate_preflight": "0d1a5994416fb9bd1e85e556bfa8cc5efcc45d4cd2959ed2dedb66ac23dae8ab",
    "p67_blind_replication": "0aea48f8858fec51b7fef3aa11fbf97764bb314dba1b41bd15b6cdedec53c396",
    "p69_table_confirmation": "7805e56817abbdaaeb44d214c652b606be90ed8f63b59d65dafb7e8b880caf08",
    "p70_registration": "aa59d77123004acc9f14dda2be8d4cbef4b0a1083c28c5bd51c0b5ff319f1d60",
    "p71_full_chain_preflight": "ba4c76611fe59fa1f14f380369b3e963379f9ff6910aea87ab1b5e81b1edfa13",
}
R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256 = (
    "ec2a2416d654b4cec1dd4aa79b455d1cd5f12a2d6d46f6f11da91f722c50f0f8"
)
R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH = (
    "d8a6346c8303a891523952bff618989931beb62fa041a511805b807ee471a6ef"
)


def _release_payload() -> dict[str, Any]:
    """返回构成自由赛测试包身份的不可变公开字段。"""

    return {
        "schema": "r18-integrated-positive-v2-release/1",
        "strategy": R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY,
        "candidate_name": R18_INTEGRATED_POSITIVE_V2_NAME,
        "candidate_id": R18_INTEGRATED_POSITIVE_V2_CANDIDATE_ID,
        "candidate_source_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "value_analysis_sha256": R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
        "rules_source_hash": R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
        "ruleset_version": R18_INTEGRATED_POSITIVE_V2_RULESET_VERSION,
        "known_guide_version_min": R18_INTEGRATED_POSITIVE_V2_KNOWN_GUIDE_VERSION,
        "base_score": 1,
        "you_cai_bi_kao": False,
        "value_analysis_limits": {
            "max_expansions": ValueAnalysisLimits().max_expansions,
            "max_routes_per_candidate": ValueAnalysisLimits().max_routes_per_candidate,
        },
        "allowed_modes": R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES,
        "evidence_sha256": dict(R18_INTEGRATED_POSITIVE_V2_EVIDENCE),
        "human_approval_date": "2026-09-23",
        "official_tournament_allowed": True,
        "production_default": False,
    }


R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID = hashlib.sha256(
    json.dumps(
        _release_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
).hexdigest()


class R18IntegratedPositiveV2ReleasePolicy(ActionValuePolicy):
    """供四种已授权真实环境模式使用的 R18 v2 冻结策略。"""

    def __init__(self, *, rules_source_hash: str, value_analysis_sha256: str) -> None:
        if hashlib.sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest() != (
            R18_INTEGRATED_POSITIVE_V2_SHA256
        ):
            raise RuntimeError("R18 v2 发布候选源码摘要漂移；拒绝装配")
        if value_analysis_sha256 != R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256:
            raise RuntimeError("R18 v2 分值分析依赖摘要漂移；拒绝装配")
        if rules_source_hash != R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH:
            raise RuntimeError("R18 v2 完整规则源摘要漂移；拒绝装配")
        super().__init__(
            ActionValueScorer(
                R18_INTEGRATED_POSITIVE_V2_NAME, R18_INTEGRATED_POSITIVE_V2_SOURCE
            ),
            value_limits=ValueAnalysisLimits(),
        )
        self.policy_id = (
            "release:r18-integrated-positive-v2:"
            + R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID[:12]
        )

    @property
    def release_metadata(self) -> Mapping[str, Any]:
        """返回审计清单使用的完整冻结身份。"""

        return {
            **_release_payload(),
            "release_package_id": R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
        }


__all__ = [
    "R18IntegratedPositiveV2ReleasePolicy",
    "R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES",
    "R18_INTEGRATED_POSITIVE_V2_CANDIDATE_ID",
    "R18_INTEGRATED_POSITIVE_V2_EVIDENCE",
    "R18_INTEGRATED_POSITIVE_V2_KNOWN_GUIDE_VERSION",
    "R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID",
    "R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY",
    "R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH",
    "R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256",
]
