"""公开分析入口的一次摸牌条件结算、有限范围和故障隔离验收。

官方算分请求仅投影成合成摸前观察，用于核验条件分值，不冒充原始动作轨迹。
所有未来条件见证来自规则模块；测试不把未来暗牌或牌墙传入策略观察。
"""

from dataclasses import replace
import json
from pathlib import Path
from unittest import mock

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits, ValueCoverage, WinDescription
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, PublicMeld, RulePublicState


_ROOT = Path(__file__).resolve().parents[2] / "fixtures/official/v23/fan-calc"
_OFFICIAL = [
    row for row in (json.loads(line) for line in (_ROOT / "cases.jsonl").read_text().splitlines())
    if row["http_status"] == 200
]


def _tiles(codes):
    if isinstance(codes, str):
        codes = codes.split()
    return tuple(Tile(code) for code in codes)


def _observation(hand, draw=None, *, seat=0, dealer=0, chain=0, piao=0,
                 baotou=False, melds=(), response=None, discards=None):
    """本人为指定座位；手牌不含单列摸牌，链事实显式给定以隔离历史缺失。"""
    holding = _tiles(hand)
    own_melds = [(), (), (), ()]
    own_melds[seat] = tuple(melds)
    turn = seat if response is None else (seat + 3) % 4
    rivers = [(), (), (), ()]
    if response is not None:
        rivers[turn] = (Tile(response),)
    if discards is not None:
        rivers = discards
    return PlayerObservation(
        game_id="value-analysis", seat=seat, round_no=1, snapshot_seq=10,
        consumed_seq=10, phase="draw" if response is None else "response_peng",
        dealer_seat=dealer, turn_seat=turn,
        responding_seats=() if response is None else (seat,),
        my_hand=holding, drawn_tile=Tile(draw) if draw else None,
        discards=tuple(rivers), melds=tuple(own_melds),
        hand_counts=tuple(len(holding) + bool(draw) if player == seat else 13 for player in range(4)),
        last_discard=None if response is None else PublicDiscard(turn, Tile(response), 10),
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), baotou, chain, False),
        public_history=(), chain_piao=piao,
    )


def _rules(enabled=False, base=1):
    return HangmaRules(RuleConfig("value-test-v23", base, enabled))


def _by_key(analysis):
    return {candidate.action_key: candidate for candidate in analysis.legal_candidates}


def _value(observation, action, *, rules=None, limits=None):
    analyzed = (rules or _rules()).analyze(
        observation, value_limits=limits or ValueAnalysisLimits()
    )
    return _by_key(analyzed)[action].value_facts


def _by_draw(facts, followup=None):
    return {
        tile.code: (route.conditional_settlement, tile.remaining_estimate, route.conditions)
        for route in facts.routes if route.followup_discard == followup
        for tile in route.useful_tiles
    }


@pytest.mark.parametrize("row", _OFFICIAL, ids=lambda row: row["tags"][0])
def test_conditional_pass_matches_every_current_official_fan_input(row):
    """652 个 v23 200 响应覆盖一次摸牌分值及房间开关；无网络、无旧版本回退。"""
    request, expected = row["request"], row["response"]
    hand, draw = request["hand"], request["draw"]
    claim = next(code for code in CANONICAL_TILE_ORDER if code not in hand and code != draw and code != "白")
    chain = request.get("chain", {"count": 0, "piao": 0})
    for enabled in (False, True):
        for dealer in (0, 1):
            obs = _observation(
                hand, response=claim, dealer=dealer,
                chain=chain["count"], piao=chain["piao"],
            )
            rivers = list(obs.discards)
            rivers[obs.seat] = (Tile("白"),) * chain["piao"]
            obs = replace(obs, discards=tuple(rivers))
            facts = _value(obs, "pass", rules=_rules(enabled, request.get("base", 1)))
            assert facts.coverage is ValueCoverage.COMPLETE
            assert facts.immediate_settlement is None
            options = _by_draw(facts)
            has_whites = "白" in hand or draw == "白"
            allowed = expected["hu"] and (not enabled or not has_whites or expected["baotou"])
            assert (draw in options) is allowed
            if allowed:
                result, remaining, conditions = options[draw]
                assert result.fan == expected["fan"]
                assert result.details == tuple(expected["detail"])
                assert conditions.baotou == expected["baotou"]
                assert remaining == 4 - hand.count(draw) - (chain["piao"] if draw == "白" else 0)
                section = expected["scores"]["dealer_hu" if dealer == 0 else "nondealer_hu"]
                assert result.score_delta[0] == section["win"]
                assert sorted(-delta for delta in result.score_delta if delta < 0) == sorted(section["lose"])
                assert sum(result.score_delta) == 0


def test_default_behavior_and_emergency_do_not_request_value_analysis():
    obs = _observation("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", "4t")
    rules = _rules()
    baseline = rules.analyze(obs)
    enriched = rules.analyze(obs, value_limits=ValueAnalysisLimits())
    assert all(candidate.value_facts is None for candidate in baseline.legal_candidates)
    assert enriched.emergency_candidate == baseline.emergency_candidate
    assert enriched.emergency_candidate.value_facts is None
    assert enriched.completeness == baseline.completeness
    assert enriched.issues == baseline.issues
    assert tuple(replace(candidate, value_facts=None) for candidate in enriched.legal_candidates) == baseline.legal_candidates
    assert _by_key(enriched)["hu"].value_facts.immediate_settlement == rules.score(WinDescription(obs, obs.seat))


def test_full_hand_and_separate_draw_observations_have_identical_value_facts():
    obs = _observation("1w 1w 6w 6w 5t 5t 7t 7t 8t 8t 9t 9t 7w", "5w")
    with_draw = replace(obs, my_hand=obs.my_hand + (obs.drawn_tile,))
    rules = _rules()
    first = rules.analyze(obs, value_limits=ValueAnalysisLimits())
    second = rules.analyze(with_draw, value_limits=ValueAnalysisLimits())
    assert {key: candidate.value_facts for key, candidate in _by_key(first).items()} == {
        key: candidate.value_facts for key, candidate in _by_key(second).items()
    }
    pairs = _by_draw(_by_key(first)["discard:5w"].value_facts)
    assert {code: data[0].fan for code, data in pairs.items()} == {"7w": 2, "白": 2}
    assert pairs["7w"][1] == 3


def test_unseen_tiles_deduct_discard_and_every_public_tile():
    obs = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", "4t",
        discards=((), _tiles("1w 1w"), (), ()),
    )
    result = _by_draw(_value(obs, "discard:1w"))
    assert result["1w"][1] == 1  # 手牌里的 1w 出河后也必须扣除。
    depleted = replace(obs, discards=((), _tiles("1w 1w 1w"), (), ()))
    assert "1w" not in _by_draw(_value(depleted, "discard:1w"))


@pytest.mark.parametrize("action_key,hand,draw,melds,response", [
    ("gang:concealed:9w", "9w 9w 9w 9w 1t 2t 3t 4t 5t 6t 7t 8t 9t", "白", (), None),
    ("gang:exposed:9w", "9w 9w 9w 1t 2t 3t 4t 5t 6t 7t 8t 9t 白", None, (), "9w"),
    ("gang:added:9w", "1t 2t 3t 4t 5t 6t 7t 8t 9t 白", "9w",
     (PublicMeld(0, "peng", _tiles("9w 9w 9w"), 3),), None),
])
def test_three_gangs_use_replacement_draw_and_hide_no_fifth_tile(action_key, hand, draw, melds, response):
    obs = _observation(hand, draw, melds=melds, response=response)
    facts = _value(obs, action_key, rules=_rules(True))
    assert facts.coverage is ValueCoverage.COMPLETE
    options = _by_draw(facts)
    assert "9w" not in options
    assert options
    for result, remaining, conditions in options.values():
        assert conditions.draw_kind == "replacement"
        assert conditions.chain_count == 1
        assert conditions.chain_piao == 0
        assert conditions.meld_count == 1
        assert conditions.baotou is True
        assert result.details == ("平胡", "杠开", "爆头")
        assert result.fan == 4
        assert remaining > 0


def test_gang_keeps_inherited_baotou_but_no_generic_youcai_exemption():
    meld = PublicMeld(0, "peng", _tiles("1w 1w 1w"), 3)
    base = _observation("2w 3w 4w 5w 6w 7w 东 东 白 北", "1w", melds=(meld,))
    ordinary = _value(base, "gang:added:1w", rules=_rules(True))
    assert ordinary.coverage is ValueCoverage.COMPLETE
    assert ordinary.routes == ()  # 补牌前不是任意听，手留白；杠本身不能绕过必爆头。
    inherited = _value(replace(base, rule_state=replace(base.rule_state, baotou=True)),
                       "gang:added:1w", rules=_rules(True))
    assert inherited.routes
    assert all(route.conditions.baotou for route in inherited.routes)
    assert all("爆头" in route.conditional_settlement.details for route in inherited.routes)


def test_claim_keeps_distinct_followup_choices_and_counts_claimed_tile_once():
    obs = _observation("5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b", response="5w")
    facts = _value(obs, "peng:5w")
    assert facts.coverage is ValueCoverage.COMPLETE
    assert {route.followup_discard for route in facts.routes} >= {"2b", "3b"}
    for followup in {route.followup_discard for route in facts.routes}:
        draws = [tile.code for route in facts.routes if route.followup_discard == followup for tile in route.useful_tiles]
        assert len(draws) == len(set(draws))
    # 后续打 2b 或 3b 都听其余同码与白；二者不是可以相加的互斥进张集合。
    assert _by_draw(facts, "2b")["3b"][1] == 3
    assert _by_draw(facts, "3b")["2b"][1] == 3
    assert all(route.conditions.meld_count == 1 for route in facts.routes)


def test_chi_preserves_all_legal_followup_one_draw_witnesses():
    obs = _observation("1w 2w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 2b", response="3w")
    obs = replace(obs, phase="response_chi")
    facts = _value(obs, "chi:1w,2w,3w")
    assert facts.coverage is ValueCoverage.COMPLETE
    assert {route.followup_discard for route in facts.routes} >= {"1t", "9t", "2b"}
    assert all(route.conditions.draw_kind == "normal" for route in facts.routes)


def test_unknown_chain_is_unavailable_but_normal_discard_resets_it():
    obs = _observation(
        "1w 1w 1w 2w 2w 2w 3b 3b 3b 4t 4t 4t 白", "9b",
        baotou=True, chain=1, piao=None,
    )
    analyzed = _rules().analyze(obs, value_limits=ValueAnalysisLimits())
    by_key = _by_key(analyzed)
    assert by_key["hu"].value_facts.coverage is ValueCoverage.UNAVAILABLE
    assert by_key["discard:白"].value_facts.coverage is ValueCoverage.UNAVAILABLE
    reset = by_key["discard:9b"].value_facts
    assert reset.coverage is ValueCoverage.COMPLETE
    assert reset.routes
    assert all(route.conditions.chain_count == route.conditions.chain_piao == 0 for route in reset.routes)
    assert analyzed.emergency_candidate is not None


def test_known_piao_prohibits_impossible_fifth_total_white_without_complete_river():
    obs = _observation("1w 2w 3w 4w 5w 6w 7b 8b 9b 东 白 白 白", response="1b", chain=1, piao=1)
    facts = _value(obs, "pass")
    assert facts.coverage is ValueCoverage.COMPLETE
    assert "白" not in _by_draw(facts)
    assert facts.routes
    assert all("4个白板" in route.conditional_settlement.details for route in facts.routes)


def test_work_limit_includes_any_tile_internal_expansion_and_is_explicit():
    obs = _observation("1w 1w 2w 2w 3w 3w 4b 4b 5b 5b 6t 6t 白", response="9w")
    from hangma_bot.hangma import progression
    with mock.patch.object(progression, "baotou_after_draw", wraps=progression.baotou_after_draw) as checked:
        facts = _value(obs, "pass", limits=ValueAnalysisLimits(max_expansions=34))
        assert facts.coverage is ValueCoverage.PARTIAL
        assert checked.call_count == 0  # basis 的 1 节点后不足 34，不偷偷执行内部循环。
    partial = _value(obs, "pass", limits=ValueAnalysisLimits(max_expansions=36))
    assert partial.coverage is ValueCoverage.PARTIAL
    assert set(_by_draw(partial)) == {"1w"}
    full = _value(obs, "pass", limits=ValueAnalysisLimits(max_expansions=69))
    assert full.coverage is ValueCoverage.COMPLETE
    assert len(_by_draw(full)) == 34  # 他家公开的 9w 尚有 3 张，因此仍在；白也在。


def test_route_limit_retains_checked_groups_and_marks_partial():
    obs = _observation("2w 2w 4w 4w 4w 1b 1b 4t 4t 6t 8t 白 白", response="9w")
    full = _value(obs, "pass")
    assert len(full.routes) >= 2
    partial = _value(obs, "pass", limits=ValueAnalysisLimits(max_routes_per_candidate=1))
    assert partial.coverage is ValueCoverage.PARTIAL
    assert len(partial.routes) == 1
    assert partial.issues[0].area == "value_analysis.limit"


def test_candidate_exception_does_not_change_legality_or_other_candidates():
    obs = _observation("1w 1w 6w 6w 5t 5t 7t 7t 8t 8t 9t 9t 7w", "5w")
    rules = _rules()
    baseline = rules.analyze(obs)
    from hangma_bot.hangma import hand_analysis
    original = hand_analysis.win_split

    def broken_for_one_discard(hand, melds):
        if sum(tile.code == "6w" for tile in hand) == 1:
            raise RuntimeError("injected-one-candidate")
        return original(hand, melds)

    with mock.patch.object(hand_analysis, "win_split", side_effect=broken_for_one_discard):
        result = rules.analyze(obs, value_limits=ValueAnalysisLimits())
    assert result.emergency_candidate == baseline.emergency_candidate
    assert result.completeness == baseline.completeness
    assert result.issues == baseline.issues
    by_key = _by_key(result)
    assert by_key["discard:6w"].value_facts.coverage is ValueCoverage.UNAVAILABLE
    assert by_key["discard:5w"].value_facts.coverage is ValueCoverage.COMPLETE
    assert by_key["discard:5w"].value_facts.routes
    assert tuple(replace(candidate, value_facts=None) for candidate in result.legal_candidates) == baseline.legal_candidates


@pytest.mark.parametrize("wall", [0, 19, 20])
def test_exhausted_drawable_wall_has_no_future_routes_but_keeps_current_hu(wall):
    obs = _observation("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", "4t")
    obs = replace(obs, remaining_tile_count=wall)
    analysis = _rules().analyze(obs, value_limits=ValueAnalysisLimits())
    for candidate in analysis.legal_candidates:
        facts = candidate.value_facts
        assert facts.coverage is ValueCoverage.COMPLETE
        assert facts.routes == ()
        assert (facts.immediate_settlement is not None) is (candidate.action_key == "hu")
    waiting = _observation("1w 1w 2w 2w 3w 3w 4b 4b 5b 5b 6t 6t 白", response="9w")
    facts = _value(replace(waiting, remaining_tile_count=wall), "pass")
    assert facts.coverage is ValueCoverage.COMPLETE
    assert facts.routes == ()


@pytest.mark.parametrize("wall", [None, 21])
def test_unknown_or_nonempty_wall_preserves_explicit_future_conditions(wall):
    waiting = _observation("1w 1w 2w 2w 3w 3w 4b 4b 5b 5b 6t 6t 白", response="9w")
    facts = _value(replace(waiting, remaining_tile_count=wall), "pass")
    assert facts.coverage is ValueCoverage.COMPLETE
    assert facts.routes


@pytest.mark.parametrize("recorded_piao", [0, 1])
def test_piao_caps_remaining_white_without_double_deducting_complete_river(recorded_piao):
    obs = _observation("1w 2w 3w 4w 5w 6w 7b 8b 9b 东 东 白 白", response="1b", chain=1, piao=1)
    rivers = list(obs.discards)
    rivers[obs.seat] = (Tile("白"),) * recorded_piao
    facts = _value(replace(obs, discards=tuple(rivers)), "pass")
    assert facts.coverage is ValueCoverage.COMPLETE
    assert _by_draw(facts)["白"][1] == 1


def test_expansion_budget_is_shared_across_candidates():
    obs = _observation("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", "4t")
    from hangma_bot.hangma import progression
    with mock.patch.object(progression, "baotou_after_draw", wraps=progression.baotou_after_draw) as checked:
        result = _rules().analyze(obs, value_limits=ValueAnalysisLimits(max_expansions=69))
    assert checked.call_count == 1
    facts = [candidate.value_facts for candidate in result.legal_candidates]
    assert facts[0].coverage is ValueCoverage.COMPLETE
    assert all(value.coverage is ValueCoverage.PARTIAL for value in facts[1:])
    assert result.emergency_candidate is not None


@pytest.mark.parametrize("recorded_piao", [0, 1])
@pytest.mark.parametrize("baotou", [False, True])
def test_new_white_discard_cannot_replace_missing_old_piao_evidence(recorded_piao, baotou):
    """普通打白和飘白都新增一张公开白，不能拿它填补旧牌河缺失的另一张。

    baotou 为权威状态控制量；本例验证可见牌计数，不作为官方连续轨迹。
    """
    meld = PublicMeld(0, "peng", _tiles("东 东 东"), 3)
    obs = _observation(
        "1w 2w 3w 4w 5w 6w 7b 8b 9b 白", "北",
        melds=(meld,), chain=1, piao=1, baotou=baotou,
        discards=((Tile("白"),) * recorded_piao, _tiles("白 白"), (), ()),
    )
    facts = _value(obs, "discard:白")
    assert facts.coverage is ValueCoverage.COMPLETE
    assert "白" not in _by_draw(facts)
    assert facts.routes
    expected_piao = 2 if baotou else 0
    assert all(route.conditions.chain_piao == expected_piao for route in facts.routes)
