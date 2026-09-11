"""一摸价值层 + 有界等胡：固定"底座是价值层"与"等胡仍生效"两条不变量。"""
import asyncio
import json
from dataclasses import replace
from pathlib import Path

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.hu_upgrade import HuUpgradePolicy, UpgradeRiskCell
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.policy.v2_value_upgrade import V2ValueUpgradePolicy
from hangma_bot.policy.value_one_draw import OneDrawValuePolicy

from .support import make_budget

ROOT = Path(__file__).resolve().parents[2]
RULES = HangmaRules(RuleConfig("hangma-mvp-v5-four-white", 1, False))
LOW_RISK = tuple(UpgradeRiskCell(band, threat, .80, .20) for band in range(3) for threat in (False, True))


def historical(name):
    original = decision_request_from_json(json.loads(
        (ROOT / "fixtures/policy/one-draw-value" / (name + ".json")).read_text()
    )["request_event"]["payload"]["request"])
    return replace(original, rules=RULES.analyze(original.observation, value_limits=ValueAnalysisLimits()))


def plan_of(policy, request):
    return asyncio.run(policy.choose(request, make_budget()))


def test_baseline_is_the_one_draw_value_layer():
    policy = V2ValueUpgradePolicy(monotonic=lambda: 0, risk_cells=LOW_RISK, risk_version="test")
    assert isinstance(policy._baseline, OneDrawValuePolicy), "底座必须是一次摸牌价值层"


def test_matches_hu_upgrade_policy_on_real_windows():
    """与 HuUpgradePolicy 同底座：同一窗口上的计划必须逐字一致。"""

    for name in ("A", "B", "C", "D"):
        request = historical(name)
        variant = plan_of(V2ValueUpgradePolicy(monotonic=lambda: 0, risk_cells=LOW_RISK,
                                               risk_version="test"), request)
        reference = plan_of(HuUpgradePolicy(monotonic=lambda: 0, risk_cells=LOW_RISK,
                                            risk_version="test"), request)
        assert [c.action_key for c in variant.candidates] == [c.action_key for c in reference.candidates], name


def test_upgrade_mechanism_still_declines_on_fixture_a():
    request = historical("A")
    plan = plan_of(V2ValueUpgradePolicy(monotonic=lambda: 0, risk_cells=LOW_RISK,
                                        risk_version="test"), request)
    assert plan.candidates[0].action_key == "discard:5b"


def test_value_layer_changes_choice_versus_pure_v2_baseline():
    """至少在一个真实窗口上，价值层底座与纯 V2 底座给出不同首选（否则本候选无差异）。"""

    differing = False
    for name in ("B", "C", "D", "G"):
        request = historical(name)
        value_layer = plan_of(V2ValueUpgradePolicy(monotonic=lambda: 0, risk_cells=LOW_RISK,
                                                   risk_version="test"), request)
        pure_v2 = plan_of(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=LOW_RISK,
                                            risk_version="test"), request)
        if value_layer.candidates[0].action_key != pure_v2.candidates[0].action_key:
            differing = True
    assert differing, "价值层候选在 B/C/D/G 上应与纯 V2 至少有一处不同"
