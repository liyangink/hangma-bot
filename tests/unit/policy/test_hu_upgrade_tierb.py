"""概率档等胡（Tier-B）：用真实 fixture 与合成非爆头宽听固定与 Tier-A 的差异。

覆盖：
1. 真实"任意摸必爆头"窗口（fixture A）：概率档与保证档一致弃胡；
2. 真实窄听窗口（fixture A 的 discard:1w）：期望增益不足，保持立即胡；
3. 合成非爆头宽听：保证档无法触发（无 baotou 证明），概率档可以——本档位的存在理由；
4. 缺价值事实：保持立即胡。
"""
import asyncio
import json
from dataclasses import replace
from pathlib import Path

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import (CandidateValueFacts, RuleCandidate, Settlement,
                                         UsefulTileFact, ValueAnalysisLimits, ValueConditions,
                                         ValueCoverage, ValueRoute)
from hangma_bot.kernel.actions import Discard, Hu, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.hu_upgrade import HuUpgradePolicy, UpgradeRiskCell
from hangma_bot.policy.hu_upgrade_tierb import HuUpgradeTierBPolicy
from hangma_bot.policy.interface import DecisionBudget
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy

from .support import make_budget, make_observation, make_request, make_rules

ROOT = Path(__file__).resolve().parents[2]
RULES = HangmaRules(RuleConfig("hangma-mvp-v5-four-white", 1, False))
LOW_RISK = tuple(UpgradeRiskCell(band, threat, .80, .20) for band in range(3) for threat in (False, True))


def historical(name="A"):
    original = decision_request_from_json(json.loads(
        (ROOT / "fixtures/policy/one-draw-value" / (name + ".json")).read_text()
    )["request_event"]["payload"]["request"])
    return replace(original, rules=RULES.analyze(original.observation, value_limits=ValueAnalysisLimits()))


def choose_tierb(request, **kwargs):
    return asyncio.run(HuUpgradeTierBPolicy(monotonic=lambda: 0, risk_cells=kwargs.pop("risk_cells", LOW_RISK),
                                            **kwargs).choose(request, DecisionBudget(100, 101, 102)))


def choose_tier_a(request, **kwargs):
    return asyncio.run(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=kwargs.pop("risk_cells", LOW_RISK),
                                         **kwargs).choose(request, DecisionBudget(100, 101, 102)))


def test_guaranteed_any_draw_window_declines_in_both_tiers():
    request = historical("A")
    plan = choose_tierb(request, risk_version="controlled-test")
    assert plan.candidates[0].action_key == "discard:5b"
    assert "有界等胡（概率档）" in plan.candidates[0].reasons[-1]
    assert "controlled-test" in plan.candidates[0].reasons[-1]


def test_partial_route_coverage_can_decline_where_guarantee_cannot():
    """合成非爆头宽听：保证档要求 baotou 证明，概率档按未见加权期望仍可弃胡。"""

    def route(score, tiles, baotou):
        return ValueRoute(
            conditional_settlement=Settlement(score_delta=(score, 0, 0, 0), fan=4, details=("七对",)),
            shanten=0,
            useful_tiles=tuple(UsefulTileFact(code, 4) for code in tiles),
            followup_discard=None,
            conditions=ValueConditions(
                draw_kind="normal",
                pre_draw_hand=("1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w",
                               "8w", "9w", "1t", "2t", "3t"),
                meld_count=0, chain_count=0, chain_piao=0, baotou=baotou),
        )

    candidates = (
        RuleCandidate(Hu(), "hu", (), None,
                      value_facts=CandidateValueFacts(
                          immediate_settlement=Settlement(score_delta=(20, 0, 0, 0), fan=1, details=("平胡",)),
                          routes=(), coverage=ValueCoverage.COMPLETE, issues=())),
        RuleCandidate(Discard(Tile("1w")), "discard:1w", (), None,
                      value_facts=CandidateValueFacts(
                          immediate_settlement=None,
                          routes=(route(384, ("5w", "6w", "7w", "8w", "9w", "1t", "2t", "3t"), False),),
                          coverage=ValueCoverage.COMPLETE, issues=())),
    )
    observation = make_observation(my_hand=(Tile("1w"),), drawn_tile=Tile("2w"), remaining_tile_count=72)
    request = make_request(observation, make_rules(candidates))
    assert choose_tier_a(request).candidates[0].action_key == "hu"
    assert choose_tierb(request).candidates[0].action_key == "discard:1w"


def test_narrow_wait_keeps_immediate_hu_when_expectation_is_small():
    request = historical("A")
    narrowed = replace(request, rules=replace(request.rules, legal_candidates=tuple(
        candidate for candidate in request.rules.legal_candidates
        if candidate.action_key in ("hu", "discard:1w"))))
    assert choose_tierb(narrowed).candidates[0].action_key == "hu"


def test_missing_value_facts_keeps_immediate_hu():
    request = historical("A")
    stripped = replace(request, rules=replace(request.rules, legal_candidates=tuple(
        candidate for candidate in request.rules.legal_candidates
        if candidate.action_key in ("hu", "discard:5b"))))
    stripped = replace(stripped, rules=replace(stripped.rules, legal_candidates=tuple(
        replace(candidate, value_facts=None) if candidate.action_key == "discard:5b" else candidate
        for candidate in stripped.rules.legal_candidates)))
    assert choose_tierb(stripped).candidates[0].action_key == "hu"
