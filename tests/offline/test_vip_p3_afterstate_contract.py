"""P3 动作后态证据等级：吃碰尚未获裁决时不得伪造已生效后态。"""

import gzip
import json
from collections import Counter
from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json
from scripts.vip_p3_afterstate_contract import AfterstateStatus, project_afterstate


_SCAN = ("review/vip-route-2026-09-30/evidence/"
         "p3-competing-terminal-20260930/new-root-scan.json.gz")


def test_frozen_new_roots_keep_afterstate_evidence_separate():
    """结果盲选根全动作守恒；预列吃碰明杠不能成为已执行公开后态。"""

    with gzip.open(_SCAN, "rt", encoding="utf-8") as stream:
        scan = json.load(stream)
    assert scan["root_count"] == 128
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    counts = Counter()
    for row in scan["rows"]:
        observation = observation_from_json(row["observation"])
        analysis = rules.analyze(
            observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
        assert [candidate.action_key for candidate in analysis.legal_candidates] == row["legal_action_keys"]
        assert [root.action_key for root in analysis.conditional_roots] == row["legal_action_keys"]
        for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots):
            facts = project_afterstate(candidate, root, observation.seat)
            family = candidate.action_key.split(":")[0]
            counts[(family, facts.status)] += 1
            if facts.status is AfterstateStatus.EXACT_TERMINAL:
                assert facts.exact_current_hu_net == root.settlement.score_delta[observation.seat]
                assert facts.own_shape is None
            else:
                assert facts.exact_current_hu_net is None
            if facts.status is AfterstateStatus.EFFECTIVE_PENDING_EVENT:
                assert facts.public_after_effect_known and facts.own_shape is not None
            else:
                assert not facts.public_after_effect_known or facts.status is AfterstateStatus.EXACT_TERMINAL
            if facts.status is AfterstateStatus.CONDITIONAL_AWARD:
                assert facts.own_shape is not None
                assert root.proposal_state is not None
                assert all(branch.state.structural_only for branch in root.branches)
    assert counts == {
        ("chi", AfterstateStatus.CONDITIONAL_AWARD): 29,
        ("discard", AfterstateStatus.EFFECTIVE_PENDING_EVENT): 972,
        ("gang", AfterstateStatus.CONDITIONAL_AWARD): 1,
        ("gang", AfterstateStatus.EFFECTIVE_PENDING_EVENT): 3,
        ("hu", AfterstateStatus.EXACT_TERMINAL): 9,
        ("pass", AfterstateStatus.UNRESOLVED_RESPONSE): 44,
        ("peng", AfterstateStatus.CONDITIONAL_AWARD): 22,
    }


def test_claim_cannot_drop_structural_only_marker():
    """鸣牌预列分支即使含牌形，也不能在无裁决时晋升为事实。"""

    with gzip.open(_SCAN, "rt", encoding="utf-8") as stream:
        rows = json.load(stream)["rows"]
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    for row in rows:
        observation = observation_from_json(row["observation"])
        analysis = rules.analyze(
            observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
        for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots):
            if candidate.action_key.startswith(("chi:", "peng:", "gang:exposed")):
                branch = root.branches[0]
                forged = replace(root, branches=(replace(
                    branch, state=replace(branch.state, structural_only=False)),) + root.branches[1:])
                with pytest.raises(ValueError, match="获裁决条件分支"):
                    project_afterstate(candidate, forged, observation.seat)
                return
    pytest.fail("冻结扫描缺鸣牌响应根")
