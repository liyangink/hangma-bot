"""C_proto 只验证 P1 条件排序、缺口停止及审计，不评估完整桌赛效果。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, RuleIssue, Settlement, ValueAnalysisLimits
from hangma_bot.hangma.route_frontier import RouteGapKind
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState
from hangma_bot.policy.route_vip_proto import RoutePrototypeError, RouteVipPrototypePolicy

from .support import make_budget, make_request, rejected, run_choose


@pytest.fixture(scope="module")
def complete_case():
    """规则源生成可立即胡、且全部弃牌根有条件边的公开普通自摸。"""

    observation = PlayerObservation(
        game_id="c-proto-test", seat=0, round_no=1, snapshot_seq=10,
        phase="draw", dealer_seat=0, turn_seat=0, responding_seats=(),
        my_hand=tuple(Tile(code) for code in (
            "1w", "2w", "3w", "4w", "5w", "6w", "7w",
            "8w", "9w", "1b", "2b", "3b", "4t",
        )),
        drawn_tile=Tile("4t"),
        discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(14, 13, 13, 13), last_discard=None,
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(), chain_piao=0, gang_draw=False,
    )
    rules = HangmaRules(RuleConfig("c-proto-test", 1, False)).analyze(
        observation, route_limits=ValueAnalysisLimits(max_expansions=8192),
    )
    assert rules.route_frontier is not None and rules.route_frontier.complete
    return observation, rules


def _choose(observation, rules, *, attempts=()):
    return run_choose(
        RouteVipPrototypePolicy(), make_request(observation, rules, rejected=attempts),
        make_budget(),
    )


def test_all_legal_roots_and_emergency_are_ranked_with_auditable_parts(complete_case):
    observation, rules = complete_case
    plan = _choose(observation, rules)
    assert {item.action_key for item in plan.candidates} == {
        candidate.action_key for candidate in rules.legal_candidates
    }
    assert [item.rank for item in plan.candidates] == list(range(1, len(plan.candidates) + 1))
    assert [item.action_key for item in plan.candidates] == [
        item.action_key for item in sorted(
            plan.candidates, key=lambda item: (-item.total_score, item.action_key),
        )
    ]
    assert next(item for item in plan.candidates if item.is_emergency).action_key == (
        rules.emergency_candidate.action_key
    )
    for candidate in plan.candidates:
        assert candidate.total_score == pytest.approx(sum(part.value for part in candidate.score_parts))
        assert candidate.reasons
    discard = next(item for item in plan.candidates if item.action_key.startswith("discard:"))
    assert "非真实牌墙概率" in discard.reasons[0]
    assert {part.name for part in discard.score_parts} >= {
        "C_proto.one_draw_hu_net_proxy",
        "C_proto.tail_shape_proxy_uncalibrated",
        "C_proto.tail_width_proxy_uncalibrated",
        "C_proto.tail_white_useful_width_proxy_uncalibrated",
    }


def test_current_hu_and_continuation_use_same_score_axis_without_fixed_hu_priority(complete_case):
    observation, rules = complete_case
    frontier = rules.route_frontier
    assert frontier is not None
    hu = next(root for root in frontier.roots if root.action_key == "hu")
    assert hu.immediate_settlement is not None
    strong = _choose(observation, rules)
    assert strong.candidates[0].action_key == "hu"
    assert strong.candidates[0].total_score == hu.immediate_settlement.score_delta[observation.seat]

    # 只改变规则结算输入，保留条件前沿；验证胡/继续并非固定优先层。
    low_hu = replace(hu, immediate_settlement=Settlement(
        score_delta=(1, 0, 0, -1), fan=1, details=("研究对照",),
    ))
    low_frontier = replace(frontier, roots=tuple(
        low_hu if root.action_key == "hu" else root for root in frontier.roots
    ))
    low = _choose(observation, replace(rules, route_frontier=low_frontier))
    assert low.candidates[0].action_key != "hu"
    assert next(item for item in low.candidates if item.action_key == "hu").total_score == 1.0


def test_two_shape_routes_on_one_draw_code_are_not_added_as_two_events(complete_case):
    observation, rules = complete_case
    frontier = rules.route_frontier
    assert frontier is not None
    root = next(root for root in frontier.roots if root.action_key == "discard:1w")
    edge = next(edge for edge in root.draw_edges if edge.immediate_win is None)
    # 仅把同一后继叶的七对距离改到与普通型同样可达；权重仍属于这一摸牌码。
    def dual_route(envelope):
        leaves = tuple(replace(
            leaf, seven_pairs_shanten_after=leaf.standard_shanten_after,
        ) for leaf in envelope.discard_frontier)
        return replace(envelope, discard_frontier=leaves)

    changed_edge = replace(edge, successor=replace(
        edge.successor,
        restricted=dual_route(edge.successor.restricted),
        unrestricted=dual_route(edge.successor.unrestricted),
    ))
    changed_root = replace(root, draw_edges=tuple(
        changed_edge if item.draw_code == edge.draw_code else item for item in root.draw_edges
    ))
    changed_frontier = replace(frontier, roots=tuple(
        changed_root if item.action_key == root.action_key else item for item in frontier.roots
    ))
    before = next(item for item in _choose(observation, rules).candidates if item.action_key == root.action_key)
    after = next(item for item in _choose(
        observation, replace(rules, route_frontier=changed_frontier),
    ).candidates if item.action_key == root.action_key)
    assert after.total_score == pytest.approx(before.total_score)


@pytest.mark.parametrize("kind", tuple(RouteGapKind))
def test_any_root_gap_fails_visible_even_if_that_action_was_rejected(complete_case, kind):
    observation, rules = complete_case
    frontier = rules.route_frontier
    assert frontier is not None
    first = frontier.roots[0]
    broken = replace(first, structure_complete=False, qualification_complete=False,
                     gap_kind=kind, issues=(RuleIssue("research", "缺口样本"),))
    changed = replace(rules, route_frontier=replace(
        frontier, roots=(broken,) + frontier.roots[1:],
    ))
    with pytest.raises(RoutePrototypeError) as error:
        _choose(observation, changed, attempts=(rejected(first.action_key),))
    assert error.value.category == kind.name
    assert error.value.action_key == first.action_key


def test_missing_frontier_and_degraded_rules_stop_with_stable_categories(complete_case):
    observation, rules = complete_case
    with pytest.raises(RoutePrototypeError) as missing:
        _choose(observation, replace(rules, route_frontier=None))
    assert missing.value.category == "INPUT_EVIDENCE_GAP"
    with pytest.raises(RoutePrototypeError) as degraded:
        _choose(observation, replace(
            rules, completeness=RuleCompleteness.DEGRADED,
            issues=(RuleIssue("test", "规则降级"),),
        ))
    assert degraded.value.category == "RULES_DEGRADED"


def test_rejected_filtering_preserves_other_roots_and_emergency(complete_case):
    observation, rules = complete_case
    key = next(candidate.action_key for candidate in rules.legal_candidates
               if candidate.action_key not in ("hu", rules.emergency_candidate.action_key))
    plan = _choose(observation, rules, attempts=(rejected(key),))
    assert key not in {item.action_key for item in plan.candidates}
    assert len(plan.candidates) == len(rules.legal_candidates) - 1
    assert any(item.is_emergency for item in plan.candidates)
    assert plan.revision == 2


def test_illicit_hidden_payload_cannot_change_public_observation_score(complete_case):
    observation, rules = complete_case
    baseline = _choose(observation, rules)
    # 即使测试错误地给公开值对象附加了赛后世界信息，也不得影响策略。
    contaminated = replace(observation)
    object.__setattr__(contaminated, "_hidden_future_wall", ("白",) * 40)
    object.__setattr__(contaminated, "_hidden_other_hands", (("白",) * 13,) * 3)
    other = _choose(contaminated, rules)
    assert [(item.action_key, item.total_score) for item in baseline.candidates] == [
        (item.action_key, item.total_score) for item in other.candidates
    ]


def test_white_draw_hand_encodings_have_identical_scores(complete_case):
    base, _ = complete_case
    drawn = Tile("白")
    separate = replace(base, drawn_tile=drawn)
    included = replace(base, my_hand=base.my_hand + (drawn,), drawn_tile=drawn)
    engine = HangmaRules(RuleConfig("c-proto-test", 1, False))
    limits = ValueAnalysisLimits(max_expansions=8192)
    separate_rules = engine.analyze(separate, route_limits=limits)
    included_rules = engine.analyze(included, route_limits=limits)
    assert separate_rules.route_frontier is not None and separate_rules.route_frontier.complete
    assert included_rules.route_frontier is not None and included_rules.route_frontier.complete
    separate_plan = _choose(separate, separate_rules)
    included_plan = _choose(included, included_rules)
    assert [(item.action_key, item.total_score) for item in separate_plan.candidates] == [
        (item.action_key, item.total_score) for item in included_plan.candidates
    ]
