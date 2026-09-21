"""R18 一次自摸条件代理：全动作覆盖与生产规则事实复用。"""

from __future__ import annotations

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline.opportunity_oracle import build_one_draw_self_win_oracle
from tests.unit.hangma.test_value_analysis import _observation
from tests.unit.policy.support import make_request


def test_one_draw_oracle_values_every_legal_action_without_recomputing_rules():
    # 四副确定面子 + 一张白，摸任意牌可胡；没有四同张，所以题面只有胡和弃牌。
    observation = _observation(
        ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
         "1b", "1b", "1b", "白"),
        draw="东",
        baotou=True,
    )
    rules = HangmaRules(RuleConfig("r18-oracle-test", 1, False))
    analysis = rules.analyze(
        observation,
        value_limits=ValueAnalysisLimits(
            max_expansions=10000,
            max_routes_per_candidate=256,
        ),
    )
    request = make_request(observation, analysis)

    result = build_one_draw_self_win_oracle(request)

    assert result.issues == ()
    assert {item.action_key for item in result.values} == {
        item.action_key for item in analysis.legal_candidates
    }
    assert result.unseen_tile_count == 122
    hu = next(item for item in result.values if item.action_key == "hu")
    assert hu.value > 0
    assert hu.error_bound == 0.0


def test_one_draw_oracle_exits_when_value_analysis_is_not_complete():
    observation = _observation(
        ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
         "1b", "1b", "1b", "白"),
        draw="东",
        baotou=True,
    )
    rules = HangmaRules(RuleConfig("r18-oracle-test", 1, False))
    analysis = rules.analyze(
        observation,
        value_limits=ValueAnalysisLimits(
            max_expansions=1,
            max_routes_per_candidate=1,
        ),
    )

    result = build_one_draw_self_win_oracle(make_request(observation, analysis))

    assert len(result.values) < len(analysis.legal_candidates)
    assert result.issues
