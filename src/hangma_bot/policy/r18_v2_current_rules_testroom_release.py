"""R18原公式在当前规则上的测试房对照包；不授正式发布资格。

组合根先校验完整运行源码、数学后端和实验清单，再传入公开元数据。
策略本身不读取文件或网络，也不修改既有正式R18包的摘要。
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from hangma_bot.hangma.interface import ValueAnalysisLimits
from .action_value_policy import ActionValuePolicy
from .action_value_seeds import ActionValueScorer
from .r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_NAME,
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)
from .r18_integrated_positive_v2_release import R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256

R18_CURRENT_TESTROOM_STRATEGY = "r18_v2_current_rules_testroom_20261004"
R18_CURRENT_TESTROOM_RULES_SHA256 = "8976d7a95faf72985aa1564e53b10a90988160d286c915177cfde4ea9734be40"


class R18CurrentRulesTestroomPolicy(ActionValuePolicy):
    """同一R18评分与默认分析限额；仅接收已验签的测试房身份。"""

    def __init__(self, *, rules_source_hash: str, value_analysis_sha256: str,
                 package: Mapping[str, Any]) -> None:
        if hashlib.sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode()).hexdigest() != R18_INTEGRATED_POSITIVE_V2_SHA256:
            raise RuntimeError("R18测试对照原评分源码摘要漂移")
        if rules_source_hash != R18_CURRENT_TESTROOM_RULES_SHA256:
            raise RuntimeError("R18测试对照规则源码摘要漂移")
        if value_analysis_sha256 != R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256:
            raise RuntimeError("R18测试对照分值分析源码摘要漂移")
        if (package.get("strategy") != R18_CURRENT_TESTROOM_STRATEGY
                or package.get("allowed_modes") != ["test_room"]
                or package.get("strength_admission") is not False
                or package.get("production_default") is not False):
            raise RuntimeError("R18测试对照包未限制实验范围")
        super().__init__(ActionValueScorer(R18_INTEGRATED_POSITIVE_V2_NAME,
                                         R18_INTEGRATED_POSITIVE_V2_SOURCE),
                         value_limits=ValueAnalysisLimits())
        self._testroom_package = dict(package)
        self.policy_id = "experimental-r18-testroom:" + package["release_package_id"][:12]

    @property
    def release_metadata(self) -> Mapping[str, Any]:
        """公开冻结身份；包含规则、依赖和公式摘要，不含凭据。"""
        return dict(self._testroom_package)
