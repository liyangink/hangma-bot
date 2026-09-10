"""庄位节奏变体：守"庄位换底座、闲位逐字一致、等胡机制不受影响"三条不变量。"""
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.hu_upgrade import UpgradeRiskCell
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.policy.v2_hu_upgrade_dealer import DEALER_WEIGHTS_V1, V2HuUpgradeDealerPolicy
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1

from .support import make_budget

ROOT = Path(__file__).resolve().parents[2]
RULES = HangmaRules(RuleConfig("hangma-mvp-v5-four-white", 1, False))
LOW_RISK = tuple(UpgradeRiskCell(band, threat, .80, .20) for band in range(3) for threat in (False, True))


def historical(name="A"):
    original = decision_request_from_json(json.loads(
        (ROOT / "fixtures/policy/one-draw-value" / (name + ".json")).read_text()
    )["request_event"]["payload"]["request"])
    return replace(original, rules=RULES.analyze(original.observation, value_limits=ValueAnalysisLimits()))


class Recorder:
    """记录是否被调用的底座替身；返回固定计划以观察调度。"""

    def __init__(self, plan):
        self.plan = plan
        self.calls = 0

    async def choose(self, request, budget):
        self.calls += 1
        return self.plan


def plan_of(policy, request):
    return asyncio.run(policy.choose(request, make_budget()))


def test_dealer_window_uses_tempo_baseline_and_nondealer_uses_default():
    request = historical("A")
    assert request.observation.dealer_seat == request.observation.seat, "夹具 A 应为庄位窗口"
    variant = V2HuUpgradeDealerPolicy(monotonic=lambda: 0, risk_cells=LOW_RISK, risk_version="test")
    reference = plan_of(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=LOW_RISK, risk_version="test"), request)
    variant._dealer_baseline = Recorder(reference)
    variant._baseline = Recorder(reference)
    plan_of(variant, request)
    assert variant._dealer_baseline.calls == 1 and variant._baseline.calls == 0

    nondealer_observation = replace(request.observation, dealer_seat=(request.observation.seat + 1) % 4)
    nondealer = replace(request, observation=nondealer_observation)
    variant._dealer_baseline = Recorder(reference)
    variant._baseline = Recorder(reference)
    plan_of(variant, nondealer)
    assert variant._baseline.calls == 1 and variant._dealer_baseline.calls == 0


def test_dealer_tempo_does_not_change_the_decline_mechanism():
    """等胡路径不受节奏权重影响：夹具 A 仍是"弃 5b 等任意摸"。"""

    request = historical("A")
    variant = plan_of(V2HuUpgradeDealerPolicy(monotonic=lambda: 0, risk_cells=LOW_RISK,
                                              risk_version="test"), request)
    reference = plan_of(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=LOW_RISK,
                                          risk_version="test"), request)
    assert variant.candidates[0].action_key == reference.candidates[0].action_key == "discard:5b"


def test_tempo_weights_only_relax_claims_and_raise_progress():
    """庄位权重只改三处：吃碰固定风险归零、向听推进抬高；其余逐项不变。"""

    assert DEALER_WEIGHTS_V1.claim_risk_peng == 0.0
    assert DEALER_WEIGHTS_V1.claim_risk_chi == 0.0
    assert DEALER_WEIGHTS_V1.shanten_step > DEFAULT_WEIGHTS_V1.shanten_step
    for field in ("win_now", "gang_bonus", "wealth_god_keep", "effective_tile", "win_potential",
                  "feed_risk", "safe_tile_bonus"):
        assert getattr(DEALER_WEIGHTS_V1, field) == getattr(DEFAULT_WEIGHTS_V1, field), field
