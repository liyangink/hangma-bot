"""G261 离线父代接缝：仅轻量装配和身份守卫，不运行完整桌。"""

from __future__ import annotations

from argparse import Namespace
from hashlib import sha256
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "review/freematch-deep-dive-20260925"
if str(REVIEW) not in sys.path:
    sys.path.insert(0, str(REVIEW))

import g261_current_rules_panel as subject  # noqa: E402
import g193_early_shape_policy as research_parent  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v2_release import (  # noqa: E402
    R18IntegratedPositiveV2ReleasePolicy,
    R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
)


CANDIDATE = "candidate@review/wiring-queue-rootcause-2026-09-25/candidates/OPTY-R18-C03-RIVER0.py"


def test_research_arm_is_explicit_and_single_candidate() -> None:
    """旧发布臂名保留，新研究臂只在显式入口出现。"""

    assert subject.arms_for(CANDIDATE) == (subject.RESEARCH_PARENT_ARM, CANDIDATE)
    with pytest.raises(ValueError, match="candidate@"):
        subject.arms_for("r18_v2")
    with pytest.raises(ValueError, match="一个候选"):
        subject.arms_for(CANDIDATE + ",r18_v1")
    with pytest.raises(ValueError, match="旧发布包"):
        subject.policy_factory("r18_v2")


def test_both_arms_build_under_same_analysis_limits(monkeypatch) -> None:
    """通过工厂入参核双臂源码和分析限额，不读取策略私有状态。"""

    monkeypatch.setattr(
        subject.panel.paired, "R18IntegratedPositiveV2ReleasePolicy",
        lambda **_kwargs: pytest.fail("G261 双臂不得装配旧发布包"))
    parent = subject.policy_factory(subject.RESEARCH_PARENT_ARM)(lambda: 800.0)
    candidate = subject.policy_factory(CANDIDATE)(lambda: 800.0)
    assert isinstance(parent, ActionValuePolicy)
    assert isinstance(candidate, ActionValuePolicy)
    assert parent.scorer_name == research_parent.R18_INTEGRATED_POSITIVE_V2_NAME
    assert candidate.scorer_name == "research:" + Path(CANDIDATE).stem
    assert not parent.policy_id.startswith("release:")

    assembled = []

    def record_policy(scorer, *, value_limits):
        assembled.append((scorer.name, scorer.source, value_limits))
        return object()

    monkeypatch.setattr(research_parent, "ActionValuePolicy", record_policy)
    monkeypatch.setattr(subject.panel.paired, "ActionValuePolicy", record_policy)
    subject.policy_factory(subject.RESEARCH_PARENT_ARM)(lambda: 800.0)
    subject.policy_factory(CANDIDATE)(lambda: 800.0)
    assert assembled == [
        (research_parent.R18_INTEGRATED_POSITIVE_V2_NAME,
         subject.R18_INTEGRATED_POSITIVE_V2_SOURCE, subject.panel.paired.LIMITS),
        ("research:" + Path(CANDIDATE).stem,
         (ROOT / CANDIDATE.removeprefix("candidate@")).read_text(encoding="utf-8"),
         subject.panel.paired.LIMITS),
    ]


def test_manifest_separates_research_identity_from_release() -> None:
    """当前规则、父代源码和候选摘要入账，旧发布包身份显式为空。"""

    args = Namespace(panel_seed=2026122961, root_start=1, roots_per_mix=1)
    row = subject.manifest(args, subject.arms_for(CANDIDATE))
    assert row["arms"] == [subject.RESEARCH_PARENT_ARM, CANDIDATE]
    assert row["r18_v2_release_id"] is None
    assert row["parent_binding"] == "research_current_rules_not_release_package"
    assert row["rules_source_hash"] == row["research_rules_source_hash"]
    assert list(row["candidate_sources"]) == [CANDIDATE]
    assert row["candidate_sources"][CANDIDATE] == sha256(
        (ROOT / CANDIDATE.removeprefix("candidate@")).read_bytes()).hexdigest()
    assert row["input_identity"]["review/freematch-deep-dive-20260925/g261_current_rules_panel.py"] == (
        subject.digest(REVIEW / "g261_current_rules_panel.py"))


def test_run_unit_passes_same_rules_to_both_arms(monkeypatch) -> None:
    """只拦截面板入口核装配，不执行任何牌山或完整桌。"""

    seen = []
    monkeypatch.setattr(subject.panel.natural, "build_seat_stage_plans",
                        lambda **_kwargs: ("same-plan",))
    monkeypatch.setattr(subject.panel.natural.stage, "contract_versions_block",
                        lambda _contract: {"ruleset_version": "same-current-rules"})

    def fake_stage(**kwargs):
        policy = kwargs["candidate_policy_factory"](lambda: 800.0)
        seen.append((kwargs["plans"], kwargs["versions_block"], policy.policy_id))
        return {"status": "not-executed"}

    monkeypatch.setattr(subject.panel.accounted, "run_accounted_stage", fake_stage)
    for arm in subject.arms_for(CANDIDATE):
        row = subject.run_unit(("H", 1, 0, arm, 2026122961))
        assert row["stage"]["status"] == "not-executed"
    assert len(seen) == 2
    assert seen[0][:2] == seen[1][:2] == (("same-plan",),
                                          {"ruleset_version": "same-current-rules"})
    assert seen[0][2] != seen[1][2]


def test_original_release_guard_still_rejects_bad_rules_hash() -> None:
    """新研究入口不改变线上发布包对规则源摘要的拒装。"""

    with pytest.raises(RuntimeError, match="完整规则源摘要漂移"):
        R18IntegratedPositiveV2ReleasePolicy(
            rules_source_hash="not-the-published-rules",
            value_analysis_sha256=R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
        )
