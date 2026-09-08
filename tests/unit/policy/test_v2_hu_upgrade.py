"""通过 choose 验证只变更等胡增量，普通取舍和关闭模式严格回到 V2。"""

import asyncio
from dataclasses import replace

import pytest

from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_VERSION
from .test_hu_upgrade import BUDGET, historical
from .support import rejected


def choose(request, **kwargs):
    return asyncio.run(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                        risk_version=RISK_VERSION, **kwargs).choose(request, BUDGET))


def v2(request):
    return asyncio.run(ComparableHeuristicPolicyV2(monotonic=lambda: 0).choose(request, BUDGET))


@pytest.mark.parametrize("name", list("ABCDEFGH"))
def test_disabled_is_exactly_frozen_v2_for_every_historical_action_family(name):
    request = historical(name)
    assert choose(request, upgrade_weight=0) == v2(request)


@pytest.mark.parametrize("name", list("BCDEGH"))
def test_enabled_preserves_v2_normal_discard_claim_and_gang_choices(name):
    request = historical(name)
    assert choose(request) == v2(request)


@pytest.mark.parametrize("name,key", [("A", "discard:5b"), ("F", "discard:白")])
def test_known_hu_upgrades_still_work_on_the_v2_base(name, key):
    request = historical(name)
    plan = choose(request)
    assert plan.candidates[0].action_key == key
    assert plan.candidates[1].action_key == "hu"
    assert {c.action_key for c in plan.candidates} == {c.action_key for c in v2(request).candidates}


def test_uncovered_cell_and_rejected_upgrade_keep_complete_v2():
    request = historical()
    request = replace(request, observation=replace(request.observation, remaining_tile_count=32))
    assert choose(request) == v2(request)
    request = historical()
    request = replace(request, rejected_attempts=(rejected("discard:5b"), rejected("discard:8t")))
    assert choose(request) == v2(request)


def test_timeout_after_v2_is_audited_with_the_actual_fallback_base(monkeypatch):
    request = historical()
    baseline = v2(request)
    policy = V2HuUpgradePolicy(monotonic=lambda: 101, risk_cells=RISK_CELLS)
    async def already_completed(*args):
        return baseline
    monkeypatch.setattr(policy._baseline, "choose", already_completed)
    plan = asyncio.run(policy.choose(request, BUDGET))
    assert plan.candidates == baseline.candidates
    assert "沿用完整V2计划" in plan.degraded_reasons[-1]
    assert "一次摸牌" not in plan.degraded_reasons[-1]
