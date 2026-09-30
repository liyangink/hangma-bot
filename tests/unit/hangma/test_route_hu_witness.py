"""局部仅胡入口与完整动作入口逐码对照，不使用完整世界或未来牌墙。"""

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma import action_families, hand_analysis, route_transition
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.route_hu_witness import analyze_waiting_hu_witness
from hangma_bot.hangma.route_transition import (
    advance_given_response, analyze_given_claim_action,
    analyze_given_replacement_draw, analyze_waiting_draw_witness, apply_given_draw,
    apply_legal_claim_discard, apply_legal_draw_discard, apply_legal_followup_gang,
)
from hangma_bot.kernel.actions import (
    CANONICAL_TILE_ORDER, Chi, Discard, Gang, Hu, Pass, Peng, Tile,
)
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicMeld, RulePublicState
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy import route_vip_heuristic


CONFIG = RuleConfig("hu-only-witness-test", 1, False)
LIMITS = ValueAnalysisLimits(max_expansions=8192)
INPUTS = Path("review/vip-route-2026-09-30/evidence/t2-performance-profile/inputs.json")


def _waiting(codes, *, meld_count=0, discarded="南", seat=0, dealer=0):
    """由生产规则的合法弃牌根取得等待态，副露用互不重叠的字牌刻子。"""

    melds = tuple(PublicMeld(seat, "peng", (Tile(code),) * 3, (seat + 1) % 4)
                  for code in ("东", "西", "北", "中")[:meld_count])
    rows = tuple(melds if index == seat else () for index in range(4))
    counts = tuple(len(codes) + 1 if index == seat else 13 for index in range(4))
    observation = PlayerObservation(
        game_id="hu-only-test", seat=seat, round_no=1, snapshot_seq=10,
        phase="draw", dealer_seat=dealer, turn_seat=seat, responding_seats=(),
        my_hand=tuple(Tile(code) for code in codes), drawn_tile=Tile(discarded),
        discards=((), (), (), ()), melds=rows, hand_counts=counts, last_discard=None,
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(), chain_piao=0, gang_draw=False,
    )
    analysis = HangmaRules(CONFIG).analyze(observation, route_limits=LIMITS)
    root = next(root for root in analysis.conditional_roots
                if root.action_key == "discard:" + discarded)
    assert root.gap_kind is None
    return root.branches[0].state


def _compare(state, code, *, restricted=False, wall=60, config=CONFIG):
    """完整入口是独立组合参照，比较合法胡、实际结算、问题与局部范围。"""

    arguments = dict(wall_remaining_before_draw=wall,
                     catch_restricted=restricted, config=config)
    full = analyze_waiting_draw_witness(state, Tile(code), **arguments)
    only = analyze_waiting_hu_witness(state, Tile(code), **arguments)
    assert only.legal_hu == any(isinstance(item.action, Hu) for item in full.legal_candidates)
    assert only.immediate_settlement == full.immediate_settlement
    assert only.issues == full.issues
    assert only.baotou_after_draw == full.source_state.baotou
    assert only.local_witness_only is full.local_witness_only is True
    assert only.scope == "local_given_normal_draw_hu_only"
    assert only.tile == Tile(code) and only.catch_restricted is restricted
    assert only.wall_remaining_before_draw == wall
    assert only.wall_remaining_after_draw == full.source_state.wall_remaining == wall - 1
    index = CANONICAL_TILE_ORDER.index(code)
    assert only.draw_capacity_before == state.unseen_capacities[index]
    assert only.draw_capacity_after == full.source_state.unseen_capacities[index]
    return only


@pytest.mark.parametrize("codes,winning", (
    (("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
      "7w", "8w", "9w", "9t"), "9t"),
    (("1w", "1w", "2w", "2w", "4w", "4w", "5t", "5t", "6t", "6t",
      "8b", "8b", "东"), "东"),
    (("1w",) * 4 + ("2w",) * 2 + ("4w",) * 2 + ("6t",) * 2 + ("8b",) * 2 + ("东",), "东"),
    (("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
      "7w", "8w", "白", "白"), "6w"),
    (("1w", "1w", "2w", "2w", "3t", "3t", "4t", "4t", "5b") + ("白",) * 4, "5b"),
    (("1w", "1w", "2w", "2w", "3w", "3w", "4w", "4w", "5w", "5w",
      "6w", "6w", "7w"), "7w"),
))
@pytest.mark.parametrize("restricted", (False, True))
def test_patterns_scopes_and_immediate_four_seat_settlement(codes, winning, restricted):
    state = _waiting(codes, seat=2, dealer=1)
    before = state
    only = _compare(state, winning, restricted=restricted, wall=21)
    assert only.legal_hu and only.immediate_settlement is not None
    assert len(only.immediate_settlement.score_delta) == 4
    assert sum(only.immediate_settlement.score_delta) == 0
    assert state is before and state.drawn_tile is None
    with pytest.raises(FrozenInstanceError):
        only.legal_hu = False


@pytest.mark.parametrize("meld_count", range(5))
def test_all_meld_counts_use_existing_normal_hand_rule(meld_count):
    groups = (("1w", "2w", "3w"), ("1t", "2t", "3t"),
              ("1b", "2b", "3b"), ("7w", "8w", "9w"))
    codes = tuple(code for group in groups[meld_count:] for code in group) + ("9t",)
    state = _waiting(codes, meld_count=meld_count)
    assert _compare(state, "9t").legal_hu


def test_non_winning_draw_and_unknown_chain_preserve_truthful_result():
    plain = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))
    assert not _compare(plain, "8t").legal_hu
    unknown = replace(plain, chain_count=1, chain_piao=None)
    witness = _compare(unknown, "9t")
    assert witness.legal_hu and witness.immediate_settlement is None and witness.issues
    chained = replace(plain, chain_count=3, chain_piao=1)
    assert _compare(chained, "9t").immediate_settlement is not None


@pytest.mark.parametrize("whites", range(5))
def test_every_white_inventory_uses_same_win_math(whites):
    base = ("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b")
    tails = (("7w", "8w", "东", "东"), ("7w", "8w", "东", "白"),
             ("7w", "8w", "白", "白"), ("7w", "白", "白", "白"), ("白",) * 4)
    assert _compare(_waiting(base + tails[whites]), "6w").legal_hu


def test_normal_draw_clears_stale_baotou_and_can_establish_new_baotou():
    base = ("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b")
    ordinary = replace(_waiting(base + ("7w", "8w", "东", "东")), baotou=True)
    assert _compare(ordinary, "9w").baotou_after_draw is False
    predecessor = replace(_waiting(base + ("7w", "8w", "白", "白")), baotou=False)
    assert _compare(predecessor, "东").baotou_after_draw is True


@pytest.mark.parametrize("winner", range(4))
@pytest.mark.parametrize("dealer", range(4))
def test_winner_and_dealer_four_seat_order(winner, dealer):
    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"), seat=winner, dealer=dealer)
    result = _compare(state, "9t").immediate_settlement
    assert result.score_delta[winner] == result.fan * (24 if winner == dealer else 10)


def test_win_split_failure_keeps_legal_hu_and_explicit_mechanical_issue(monkeypatch):
    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))
    monkeypatch.setattr(hand_analysis, "win_split", lambda *args: None)
    witness = _compare(state, "9t")
    assert witness.legal_hu and witness.immediate_settlement is None
    assert witness.issues[0].area == "route_transition.mechanical"


def test_hu_family_fault_keeps_explicit_issue_instead_of_precise_non_hu(monkeypatch):
    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))

    def fail(*args):
        raise RuntimeError("胡族故障注入")

    monkeypatch.setattr(action_families, "hu_candidates", fail)
    witness = _compare(state, "9t")
    assert not witness.legal_hu and witness.issues[0].area == "action_families.hu"


def test_win_math_fault_propagates_instead_of_becoming_non_hu(monkeypatch):
    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))

    def failed_math(*args):
        raise RuntimeError("数学入口故障注入")

    monkeypatch.setattr(hand_analysis, "analyse_hand", failed_math)
    monkeypatch.setattr(hand_analysis, "analyse_hand_win", failed_math)
    for helper in (analyze_waiting_draw_witness, analyze_waiting_hu_witness):
        with pytest.raises(RuntimeError, match="数学入口故障"):
            helper(state, Tile("9t"), wall_remaining_before_draw=60,
                   catch_restricted=False, config=CONFIG)


def test_hu_only_does_not_analyse_other_actions_or_rescan_public_history(monkeypatch):
    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))

    def unnecessary(*args, **kwargs):
        raise AssertionError("仅胡入口不应执行完整分析或公开库存重扫")

    monkeypatch.setattr(hand_analysis, "analyse_hand", unnecessary)
    monkeypatch.setattr(action_families, "generate_candidates", unnecessary)
    monkeypatch.setattr(route_transition, "count_unseen_tiles_from_view", unnecessary)
    witness = analyze_waiting_hu_witness(state, Tile("9t"), wall_remaining_before_draw=60,
                                       catch_restricted=False, config=CONFIG)
    assert witness.legal_hu and witness.immediate_settlement is not None


@pytest.mark.parametrize("kind", ("conservative", "unknown"))
def test_non_exact_capacity_rejected_by_both_public_entrances(kind):
    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))
    index = CANONICAL_TILE_ORDER.index("9t")
    evidence = list(state.unseen_evidence)
    evidence[index] = kind
    altered = replace(state, unseen_evidence=tuple(evidence))
    for helper in (analyze_waiting_draw_witness, analyze_waiting_hu_witness):
        with pytest.raises(ValueError, match="不精确"):
            helper(altered, Tile("9t"), wall_remaining_before_draw=60,
                   catch_restricted=False, config=CONFIG)


@pytest.mark.parametrize("wall", (0, 19, 20))
def test_reserved_wall_rejected_before_assuming_any_draw(wall):
    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))
    for helper in (analyze_waiting_draw_witness, analyze_waiting_hu_witness):
        with pytest.raises(ValueError, match="保留区"):
            helper(state, Tile("9t"), wall_remaining_before_draw=wall,
                   catch_restricted=False, config=CONFIG)


def test_physical_fifth_white_and_unawarded_structure_rejected():
    state = _waiting(("1w", "1w", "2w", "2w", "3t", "3t", "4t", "4t", "5b") + ("白",) * 4)
    for helper in (analyze_waiting_draw_witness, analyze_waiting_hu_witness):
        with pytest.raises(ValueError, match="为零"):
            helper(state, Tile("白"), wall_remaining_before_draw=60,
                   catch_restricted=False, config=CONFIG)
        with pytest.raises(ValueError, match="未裁决"):
            helper(replace(state, structural_only=True), Tile("5b"),
                   wall_remaining_before_draw=60, catch_restricted=False, config=CONFIG)


@pytest.mark.parametrize("alteration", (
    "identity", "public_view", "hand_count", "drawn", "pending_discard", "rules",
    "wall_bool", "catch_not_bool", "phase",
    "seat_negative",
))
def test_same_required_waiting_preconditions(alteration):
    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))
    kwargs = dict(wall_remaining_before_draw=60, catch_restricted=False, config=CONFIG)
    if alteration == "identity":
        state = replace(state, identity=None)
    elif alteration == "public_view":
        state = replace(state, public_view=None)
    elif alteration == "hand_count":
        state = replace(state, public_view=replace(state.public_view, hand_counts=(12, 13, 13, 13)))
    elif alteration == "drawn":
        state = replace(state, drawn_tile=Tile("9t"))
    elif alteration == "pending_discard":
        state = replace(state, expected_discard_seat=1)
    elif alteration == "rules":
        kwargs["config"] = RuleConfig("wrong-binding", 1, False)
    elif alteration == "wall_bool":
        kwargs["wall_remaining_before_draw"] = True
    elif alteration == "catch_not_bool":
        kwargs["catch_restricted"] = 1
    elif alteration == "phase":
        state = replace(state, phase=route_transition.ConditionalPhase.CLAIM_DISCARD)
    elif alteration == "seat_negative":
        state = replace(state, seat=-1)
    for helper in (analyze_waiting_draw_witness, analyze_waiting_hu_witness):
        with pytest.raises(ValueError):
            helper(state, Tile("9t"), **kwargs)


@pytest.mark.parametrize("binding", ("seat", "dealer_seat"))
@pytest.mark.parametrize("code", ("8t", "9t"))
@pytest.mark.parametrize("invalid", (True, 1.0))
def test_invalid_seat_type_is_rejected_even_without_win(binding, code, invalid):
    """合法观察禁止布尔座位；非胡分支也不能绕过结算处的严格座位门禁。"""

    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))
    altered = replace(state, **{binding: invalid})
    for helper in (analyze_waiting_draw_witness, analyze_waiting_hu_witness):
        with pytest.raises(ValueError, match="座位"):
            helper(altered, Tile(code), wall_remaining_before_draw=60,
                   catch_restricted=False, config=CONFIG)


@pytest.mark.parametrize("code", ("8t", "9t"))
def test_negative_seat_cannot_use_python_negative_index_to_pass_public_binding(code):
    """原性能改写遗漏的非法负座位，成胡与非胡都须拒绝。"""

    state = _waiting(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                      "7w", "8w", "9w", "9t"))
    for helper in (analyze_waiting_draw_witness, analyze_waiting_hu_witness):
        with pytest.raises(ValueError, match="座位"):
            helper(replace(state, seat=-1), Tile(code), wall_remaining_before_draw=60,
                   catch_restricted=False, config=CONFIG)


def _all_waiting_states(observation, config):
    """逐根组合公开合法转移，包含所有弃牌和相容杠补，绝不选最佳后继。"""

    rules = HangmaRules(config).analyze(observation, route_limits=LIMITS)
    waits = {}

    def remember(state):
        key = (state.concealed, state.meld_count, state.phase, state.baotou,
               state.chain_count, state.chain_piao, state.wall_remaining,
               state.my_chi_count, state.my_peng_codes, state.unseen_capacities,
               state.unseen_evidence, state.seat, state.dealer_seat,
               state.public_view.hand_counts, state.identity.ruleset_version)
        waits.setdefault(key, state)

    def actions(analysis):
        assert not analysis.issues
        for candidate in analysis.legal_candidates:
            if isinstance(candidate.action, Discard):
                apply = apply_legal_claim_discard if analysis.source_state.drawn_tile is None else apply_legal_draw_discard
                remember(apply(analysis, candidate.action_key))
            elif isinstance(candidate.action, Gang):
                replacement(apply_legal_followup_gang(analysis, candidate.action_key))
            else:
                assert isinstance(candidate.action, Hu)

    def replacement(state):
        for index, code in enumerate(CANONICAL_TILE_ORDER):
            if state.unseen_evidence[index] == "exact" and state.unseen_capacities[index] > 0:
                landed = apply_given_draw(state, Tile(code), replacement=True)
                actions(analyze_given_replacement_draw(landed, seat=state.seat,
                                                       dealer_seat=state.dealer_seat, config=config))

    for candidate, root in zip(rules.legal_candidates, rules.conditional_roots):
        assert not root.gap_kinds
        if isinstance(candidate.action, Hu):
            continue
        if isinstance(candidate.action, (Discard, Pass)):
            remember(root.branches[0].state)
            continue
        if isinstance(candidate.action, (Chi, Peng)) or root.proposal_state is not None:
            trigger = observation.last_discard
            choices = tuple((seat, candidate.action if seat == observation.seat else Pass())
                            for seat in observation.responding_seats)
            awarded = advance_given_response(root, window=observation.phase,
                discard_seat=trigger.seat, discarded_tile=trigger.tile,
                responding=observation.responding_seats, choices=choices, retained_in_river=False)
            assert not awarded.issues and awarded.state.claim_awarded
            state = awarded.state
        else:
            state = root.branches[0].state
        if isinstance(candidate.action, Gang):
            replacement(state)
        else:
            actions(analyze_given_claim_action(state, seat=state.seat, config=config))
    return tuple(waits.values())


@pytest.mark.parametrize("index", (0, 1))
def test_every_waiting_structure_and_compatible_code_in_two_real_slow_requests(index):
    """固定两条慢公开观察；每个不同等待事实枚举全部精确相容码和两种限制。"""

    selected = json.loads(INPUTS.read_text())["observations"][index]
    observation = observation_from_json(selected["observation"])
    config = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
    states = _all_waiting_states(observation, config)
    assert len(states) > 20
    compared = 0
    for state in states:
        for position, code in enumerate(CANONICAL_TILE_ORDER):
            if state.unseen_evidence[position] != "exact" or state.unseen_capacities[position] <= 0:
                continue
            for restricted in (False, True):
                _compare(state, code, restricted=restricted, wall=state.wall_remaining, config=config)
                compared += 1
    assert compared > 1000


@pytest.mark.parametrize("index", (0, 1))
def test_integrated_graph_scores_and_traces_equal_full_witness_oracle(monkeypatch, index):
    """只替换公开胡查询，整图、全部根排序分与解释同旧完整规则入口。"""

    selected = json.loads(INPUTS.read_text())["observations"][index]
    observation = observation_from_json(selected["observation"])
    config = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
    rules = HangmaRules(config).analyze(observation, route_limits=LIMITS)
    window = window_key_from_json(selected["window_key"])
    request = DecisionRequest(observation, CompetitionContext("witness-oracle", None, None,
        None, None, (), 0), rules, selected["decision_id"], window.trigger_seq, window, ())

    def full_hu_projection(*args, **kwargs):
        full = analyze_waiting_draw_witness(*args, **kwargs)
        return SimpleNamespace(legal_hu=any(isinstance(item.action, Hu) for item in full.legal_candidates),
                               issues=full.issues, immediate_settlement=full.immediate_settlement)

    monkeypatch.setattr(route_vip_heuristic, "analyze_waiting_hu_witness", full_hu_projection)
    full_view = route_vip_heuristic.build_vip_route_scoring_view(request, config)
    executor = ActionValueExecutor(route_vip_heuristic.VIP_ROUTE_HEURISTIC_SEED_SOURCE)
    full_scores = executor.score_vip_route(full_view)
    old_operations = executor.last_operation_count
    monkeypatch.setattr(route_vip_heuristic, "analyze_waiting_hu_witness", analyze_waiting_hu_witness)
    hu_view = route_vip_heuristic.build_vip_route_scoring_view(request, config)
    hu_scores = executor.score_vip_route(hu_view)
    assert hu_view == full_view
    assert hu_view.candidate_view() == full_view.candidate_view()
    assert hu_scores == full_scores  # ActionScore含完整trace，绝对排序分也须逐项相等
    assert executor.last_operation_count == old_operations
