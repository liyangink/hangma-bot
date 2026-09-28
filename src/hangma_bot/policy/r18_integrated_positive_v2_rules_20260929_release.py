"""R18 v2 同一评分源码在 2026-09-29 主线规则上的新绑定发布包。

旧发布包保持不可变；本包仅绑定新增吃碰后继分支事实的规则源码。
通过当前规则、时限及官方接线门之前，不应把本地装配成功视为上线验收。
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
from .r18_integrated_positive_v2_release import (
    R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
    _release_payload as _old_release_payload,
)


R18_V2_RULES_20260929_SOURCE_HASH = (
    "14e670edd631cb91a2c4c31d8131e360e9ebfb2d82d7c9ac9425f01d099e678d"
)
R18_V2_RULES_20260929_PARITY_SHA256 = (
    "6f7e1421fd95e08f261c1b8cd8ef925605c33bb7313fd5a3b41aca2eb0b947cd"
)


def _release_payload() -> dict[str, Any]:
    """继承已获准的算法和模式范围，显式追加本次规则绑定证据。"""
    payload = _old_release_payload()
    payload.update({
        "schema": "r18-integrated-positive-v2-release/2",
        "release_revision": "rules-20260929",
        "rules_source_hash": R18_V2_RULES_20260929_SOURCE_HASH,
        "evidence_sha256": {
            **payload["evidence_sha256"],
            "g194_same_source_rule_binding_parity": R18_V2_RULES_20260929_PARITY_SHA256,
        },
        "rule_binding_checked_date": "2026-09-29",
    })
    return payload


R18_V2_RULES_20260929_RELEASE_PACKAGE_ID = hashlib.sha256(
    json.dumps(_release_payload(), ensure_ascii=False, sort_keys=True,
               separators=(",", ":")).encode("utf-8")
).hexdigest()


class R18IntegratedPositiveV2Rules20260929ReleasePolicy(ActionValuePolicy):
    """R18 v2 算法与当前规则源的绑定；异常时拒绝真实环境装配。"""

    def __init__(self, *, rules_source_hash: str, value_analysis_sha256: str) -> None:
        if hashlib.sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest() != (
            R18_INTEGRATED_POSITIVE_V2_SHA256
        ):
            raise RuntimeError("R18 v2 发布候选源码摘要漂移；拒绝装配")
        if value_analysis_sha256 != R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256:
            raise RuntimeError("R18 v2 分值分析依赖摘要漂移；拒绝装配")
        if rules_source_hash != R18_V2_RULES_20260929_SOURCE_HASH:
            raise RuntimeError("R18 v2 当前规则发布包源码摘要漂移；拒绝装配")
        super().__init__(
            ActionValueScorer(
                R18_INTEGRATED_POSITIVE_V2_NAME,
                R18_INTEGRATED_POSITIVE_V2_SOURCE,
            ),
            value_limits=ValueAnalysisLimits(),
        )
        self.policy_id = (
            "release:r18-integrated-positive-v2-rules-20260929:"
            + R18_V2_RULES_20260929_RELEASE_PACKAGE_ID[:12]
        )

    @property
    def release_metadata(self) -> Mapping[str, Any]:
        """提供审计清单中的完整不可变身份。"""
        return {
            **_release_payload(),
            "release_package_id": R18_V2_RULES_20260929_RELEASE_PACKAGE_ID,
        }


__all__ = [
    "R18IntegratedPositiveV2Rules20260929ReleasePolicy",
    "R18_V2_RULES_20260929_SOURCE_HASH",
    "R18_V2_RULES_20260929_PARITY_SHA256",
    "R18_V2_RULES_20260929_RELEASE_PACKAGE_ID",
]
