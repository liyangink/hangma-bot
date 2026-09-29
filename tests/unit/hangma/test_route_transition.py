"""条件转移对照生产规则候选与生命周期；不把未来条件写成已发生事实。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.hangma import progression
from hangma_bot.hangma.engine import HangmaRules, _build_context
from hangma_bot.hangma.interface import RuleCandidate, ValueAnalysisLimits
from hangma_bot.hangma.route_frontier import RouteGapKind
from hangma_bot.hangma.public_tile_counts import (
    count_unseen_tiles_from_view, public_view_from_observation,
)
from hangma_bot.hangma.route_transition import (
    ConditionalPhase, ConditionalRouteState, analyze_given_claim_action,
    analyze_given_replacement_draw,
    analyze_given_self_draw, apply_given_draw, apply_legal_followup_gang,
    apply_legal_claim_discard, advance_given_response, advance_response_state,
    advance_given_other_draw, advance_given_other_discard,
    advance_given_other_gang,
    finish_given_exhaustive_draw,
    given_next_normal_draw,
    project_legal_roots,
)
from hangma_bot.kernel.actions import (
    CANONICAL_TILE_INDEX, Chi, Gang, GangKind, Pass, Peng, Tile, action_key,
)
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation, PublicDiscard, PublicMeld, RulePublicState,
)
from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import observation as project_observation, public_event


def _observation(*, phase="draw", last=None, hand=None, drawn=None, baotou=False,
                 chain=0, piao=0, my_melds=()):
    if hand is None:
        hand = ("1w", "1w", "1w", "2w", "3w", "4w", "5w",
                "6w", "7w", "8w", "9w", "东", "南")
    return PlayerObservation(
        game_id="conditional-test", seat=0, round_no=1, snapshot_seq=10,
        phase=phase, dealer_seat=0, turn_seat=0 if phase == "draw" else 1,
        responding_seats=() if phase == "draw" else (0,),
        my_hand=tuple(Tile(code) for code in hand), drawn_tile=drawn,
        discards=((), (), (), ()), melds=(my_melds, (), (), ()),
        hand_counts=(len(hand) + int(drawn is not None), 13, 13, 13),
        last_discard=last, remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), baotou, chain, False),
        public_history=(), chain_piao=piao, gang_draw=False,
    )


def _roots(observation):
    config = RuleConfig("conditional-test", 1, False)
    rules = HangmaRules(config)
    analysis = rules.analyze(observation)
    projected = project_legal_roots(observation, _build_context(observation),
                                    analysis.legal_candidates, config=config)
    assert tuple(root.action_key for root in projected) == tuple(
        candidate.action_key for candidate in analysis.legal_candidates)
    return analysis, {root.action_key: root for root in projected}


def test_draw_roots_preserve_all_legal_candidates_and_same_source_lifecycle():
    observation = _observation(drawn=Tile("白"), baotou=True, chain=1, piao=1)
    _, roots = _roots(observation)
    assert roots["discard:白"].branches[0].state.chain_count == 2
    assert roots["discard:白"].branches[0].state.chain_piao == 2
    assert roots["discard:东"].branches[0].state.chain_count == 0
    assert roots["discard:东"].branches[0].state.chain_piao == 0
    for key in ("discard:白", "discard:东"):
        assert roots[key].gap_kind is None
        assert roots[key].gap_kinds == ()
        assert roots[key].pending_condition is roots[key].branches[0].state.phase
        assert roots[key].branches[0].state.baotou == progression.baotou_after_action(
            True, next(candidate.action for candidate in
                       HangmaRules(RuleConfig("conditional-test", 1, False)).analyze(observation).legal_candidates
                       if candidate.action_key == key),
            _build_context(observation).full_hand(), 0)


def test_new_own_discard_replaces_prior_official_trigger_without_fake_seq():
    observation = replace(
        _observation(drawn=Tile("3b"), last=PublicDiscard(3, Tile("2b"), 9)),
        discards=((), (), (), (Tile("2b"),)),
    )
    _, roots = _roots(observation)
    state = roots["discard:3b"].branches[0].state
    assert state.response_trigger == (0, Tile("3b"))
    assert state.response_public_discard is None
    assert state.response_window == "response_peng"
    assert state.public_view.snapshot_seq == observation.snapshot_seq


def test_peng_keeps_every_followup_discard_and_pass_keeps_waiting_hand():
    observation = _observation(
        phase="response_peng", last=PublicDiscard(1, Tile("1w"), 10))
    analysis, roots = _roots(observation)
    peng = next(item for item in analysis.legal_candidates if item.action_key == "peng:1w")
    expected = tuple(branch.followup_key for branch in peng.facts.followup_branches)
    actual = tuple(branch.followup_key for branch in roots["peng:1w"].branches)
    assert actual == expected
    claim_state = roots["peng:1w"].claim_state
    assert claim_state is not None
    assert claim_state.phase is ConditionalPhase.CLAIM_DISCARD
    assert claim_state.drawn_tile is None
    assert len(claim_state.concealed) == 11
    assert claim_state.my_peng_codes == ("1w",)
    assert all(branch.state.meld_count == 1 for branch in roots["peng:1w"].branches)
    assert all(len(branch.state.concealed) == 10 for branch in roots["peng:1w"].branches)
    assert roots["pass"].branches[0].state.concealed == observation.my_hand
    assert roots["pass"].branches[0].state.phase is ConditionalPhase.RESPONSE_RESOLUTION
    for key in ("pass", "peng:1w"):
        assert roots[key].gap_kinds == ()
        assert roots[key].issues == ()
        assert roots[key].pending_condition is ConditionalPhase.RESPONSE_RESOLUTION


def test_chi_keeps_every_followup_and_exposed_gang_waits_for_replacement():
    chi_observation = _observation(
        phase="response_chi", last=PublicDiscard(3, Tile("3w"), 10),
        hand=("1w", "2w", "4w", "5w", "6w", "7w", "8w",
              "9w", "1b", "2b", "3b", "东", "南"))
    analysis, roots = _roots(chi_observation)
    chi_candidates = [item for item in analysis.legal_candidates if item.action_key.startswith("chi:")]
    assert chi_candidates
    for candidate in chi_candidates:
        expected = tuple(branch.followup_key for branch in candidate.facts.followup_branches)
        assert tuple(branch.followup_key for branch in roots[candidate.action_key].branches) == expected
        assert roots[candidate.action_key].claim_state.phase is ConditionalPhase.CLAIM_DISCARD
        assert roots[candidate.action_key].claim_state.my_chi_count == 1
        assert roots[candidate.action_key].pending_condition is ConditionalPhase.RESPONSE_RESOLUTION
        assert roots[candidate.action_key].gap_kinds == ()

    gang_observation = _observation(
        phase="response_peng", last=PublicDiscard(1, Tile("1w"), 10))
    _, gang_roots = _roots(gang_observation)
    exposed = gang_roots["gang:exposed:1w"].branches[0].state
    assert exposed.phase is ConditionalPhase.REPLACEMENT_DRAW
    assert gang_roots["gang:exposed:1w"].pending_condition is ConditionalPhase.RESPONSE_RESOLUTION
    assert gang_roots["gang:exposed:1w"].gap_kinds == ()
    assert exposed.meld_count == 1
    assert len(exposed.concealed) == 10


def test_exposed_gang_proposal_keeps_hand_until_public_award():
    observation = replace(
        _observation(phase="response_peng", last=PublicDiscard(1, Tile("1w"), 10)),
        discards=((), (Tile("1w"),), (), ()),
    )
    _, roots = _roots(observation)
    root = roots["gang:exposed:1w"]
    assert root.proposal_state.concealed == observation.my_hand
    assert root.branches[0].state.structural_only
    assert len(root.branches[0].state.concealed) == len(observation.my_hand) - 3
    incomplete = advance_given_response(
        root, window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=((0, Gang(Tile("1w"), GangKind.EXPOSED)),))
    assert incomplete.resolution.status == "unready"
    assert incomplete.state.concealed == observation.my_hand
    awarded = advance_given_response(
        root, window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=((2, Pass()), (3, Pass()),
                 (0, Gang(Tile("1w"), GangKind.EXPOSED))),
        retained_in_river=False)
    assert awarded.state.phase is ConditionalPhase.REPLACEMENT_DRAW
    assert awarded.state.claim_awarded
    assert not awarded.state.structural_only
    assert len(awarded.state.concealed) == len(observation.my_hand) - 3


def test_added_gang_preserves_meld_count_and_rejects_other_rules_config():
    peng = PublicMeld(0, "peng", (Tile("1w"),) * 3, 1)
    observation = _observation(
        hand=("1w", "2w", "3w", "4w", "5w", "6w", "7w",
              "8w", "9w", "东"),
        drawn=Tile("南"), my_melds=(peng,))
    analysis, roots = _roots(observation)
    added = roots["gang:added:1w"].branches[0].state
    assert added.phase is ConditionalPhase.REPLACEMENT_DRAW
    assert roots["gang:added:1w"].pending_condition is ConditionalPhase.REPLACEMENT_DRAW
    assert roots["gang:added:1w"].gap_kinds == ()
    assert added.meld_count == 1
    assert len(added.concealed) == 10
    with pytest.raises(ValueError, match="BaseScore"):
        project_legal_roots(observation, _build_context(observation),
                            analysis.legal_candidates,
                            config=RuleConfig("conditional-test", 2, False))


def test_concealed_gang_then_given_replacement_draw_uses_production_baotou():
    observation = _observation(
        hand=("1w", "1w", "1w", "1w", "2w", "3w", "4w", "5w",
              "6w", "7w", "8w", "东", "南"), drawn=Tile("白"))
    _, roots = _roots(observation)
    state = roots["gang:concealed:1w"].branches[0].state
    assert state.phase is ConditionalPhase.REPLACEMENT_DRAW
    assert state.chain_count == 1
    assert state.meld_count == 1
    landed = apply_given_draw(state, Tile("9w"), replacement=True)
    assert landed.phase is ConditionalPhase.DRAW_ACTION
    assert landed.drawn_tile == Tile("9w")
    assert landed.baotou == progression.baotou_after_draw(
        state.baotou, state.concealed, state.meld_count, Tile("9w"), replacement=True)
    assert landed.wall_remaining == 59
    with pytest.raises(ValueError, match="来源"):
        apply_given_draw(state, Tile("9w"), replacement=False)
    with pytest.raises(ValueError, match="保留区"):
        apply_given_draw(replace(state, wall_remaining=20), Tile("9w"), replacement=True)


def test_given_normal_draw_can_enter_or_leave_baotou_without_future_tile_guess():
    observation = _observation()
    concealed = tuple(Tile(code) for code in (
        "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
        "1b", "2b", "3b", "东"))
    view = public_view_from_observation(observation)
    counts = count_unseen_tiles_from_view(
        view, seat=0, concealed=concealed, drawn_tile=None, chain_piao=0)
    state = ConditionalRouteState(
        concealed,
        0, ConditionalPhase.NORMAL_DRAW, False, 0, 0, 60,
        unseen_capacities=counts.unseen,
        unseen_evidence=counts.evidence,
        root_public_view=view)
    result = apply_given_draw(state, Tile("南"), replacement=False)
    assert result.baotou == progression.baotou_after_draw(
        False, state.concealed, 0, Tile("南"), replacement=False)
    assert state.drawn_tile is None
    assert result.drawn_tile == Tile("南")


def test_restricted_white_discard_opens_own_circle_in_conditional_state():
    observation = replace(
        _observation(
            drawn=Tile("白"),
            hand=("1w", "1w", "1w", "2w", "3w", "4w", "5w",
                  "6w", "7w", "8w", "9w", "东", "南"),
        ),
        rule_state=RulePublicState(Tile("白"), False, 0, True, 1),
    )
    _, roots = _roots(observation)
    assert tuple(roots) == ("discard:白",)
    after = roots["discard:白"].branches[0].state
    assert after.catch_restricted is False
    assert after.catch_circle == progression.CatchPlayState(True, 0)
    assert after.phase is ConditionalPhase.PUBLIC_WAIT
    assert after.expected_draw_seat == 1


def test_owner_nonwhite_discard_closes_circle_in_conditional_state():
    observation = replace(
        _observation(drawn=Tile("南")),
        rule_state=RulePublicState(Tile("白"), False, 0, True, 0),
    )
    _, roots = _roots(observation)
    after = roots["discard:东"].branches[0].state
    assert after.catch_circle == progression.CatchPlayState(False, None)
    assert after.catch_restricted is False


def test_added_gang_public_four_prevents_impossible_fifth_replacement():
    peng = PublicMeld(0, "peng", (Tile("1w"),) * 3, 1)
    observation = _observation(
        hand=("1w", "2w", "3w", "4w", "5w", "6w", "7w",
              "8w", "9w", "东"),
        drawn=Tile("南"), my_melds=(peng,))
    _, roots = _roots(observation)
    pending = roots["gang:added:1w"].branches[0].state
    with pytest.raises(ValueError, match="容量为零|证据不精确"):
        apply_given_draw(pending, Tile("1w"), replacement=True)


def test_other_seat_public_four_prevents_impossible_conditional_draw():
    other_gang = PublicMeld(2, "gang_an", (Tile("9b"),) * 4, None)
    observation = replace(
        _observation(drawn=Tile("南")),
        melds=((), (), (other_gang,), ()),
    )
    _, roots = _roots(observation)
    after_discard = roots["discard:东"].branches[0].state
    with pytest.raises(ValueError, match="容量为零"):
        given_next_normal_draw(
            after_discard, Tile("9b"),
            wall_remaining_before_draw=55, catch_restricted=False,
            allow_local_witness=True,
        )


def test_missing_chain_piao_is_input_evidence_gap_not_zero():
    observation = _observation(drawn=Tile("白"), baotou=True, chain=1, piao=None)
    _, roots = _roots(observation)
    root = roots["discard:白"]
    assert root.gap_kind is RouteGapKind.INPUT_EVIDENCE_GAP
    assert root.gap_kinds == (RouteGapKind.INPUT_EVIDENCE_GAP,)
    assert root.branches[0].state.chain_piao is None
    assert any("链内飘白次数" in issue.reason for issue in root.issues)


def test_independent_observation_issue_does_not_turn_future_into_mechanical_gap():
    observation = replace(
        _observation(drawn=Tile("南")),
        observation_issues=("独立的公开事实缺项",),
    )
    _, roots = _roots(observation)
    root = roots["discard:东"]
    assert root.gap_kinds == (RouteGapKind.INPUT_EVIDENCE_GAP,)
    assert root.pending_condition is ConditionalPhase.RESPONSE_RESOLUTION
    assert all(issue.area == "route_transition.input_evidence" for issue in root.issues)


def test_injected_candidate_hand_conflict_is_mechanical_gap_not_missing_input():
    observation = _observation(drawn=Tile("白"))
    impossible = Gang(Tile("9w"), GangKind.CONCEALED)
    root = project_legal_roots(
        observation, _build_context(observation),
        (RuleCandidate(impossible, action_key(impossible), ("故障注入",)),),
        config=RuleConfig("conditional-test", 1, False),
    )[0]
    assert root.gap_kind is RouteGapKind.MECHANICAL_GAP
    assert root.branches == ()
    assert "同次合法事实冲突" in root.issues[0].reason


def test_real_root_failure_and_independent_missing_input_keep_both_axes():
    observation = replace(
        _observation(drawn=Tile("白")),
        observation_issues=("独立的公开事实缺项",),
    )
    impossible = Gang(Tile("9w"), GangKind.CONCEALED)
    root = project_legal_roots(
        observation, _build_context(observation),
        (RuleCandidate(impossible, action_key(impossible), ("故障注入",)),),
        config=RuleConfig("conditional-test", 1, False),
    )[0]
    assert root.gap_kind is RouteGapKind.MECHANICAL_GAP
    assert root.gap_kinds == (
        RouteGapKind.MECHANICAL_GAP, RouteGapKind.INPUT_EVIDENCE_GAP)
    assert root.pending_condition is None


def test_concealed_gang_given_replacement_can_hu_or_continue_by_same_rule_sources():
    config = RuleConfig("conditional-test", 1, False)
    observation = _observation(
        hand=("1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w",
              "8w", "8w", "8w", "东"), drawn=Tile("1w"))
    _, roots = _roots(observation)
    pending = roots["gang:concealed:1w"].branches[0].state
    landed = apply_given_draw(pending, Tile("东"), replacement=True)
    actual = analyze_given_replacement_draw(
        landed, seat=0, dealer_seat=0, config=config)
    keys = {candidate.action_key for candidate in actual.legal_candidates}
    assert "hu" in keys
    assert "discard:东" in keys
    assert actual.immediate_settlement is not None
    assert actual.immediate_settlement.fan >= 2  # 杠链由同源结算计入
    assert actual.issues == ()
    rules = HangmaRules(config)
    production = rules.analyze(
        observation, value_limits=ValueAnalysisLimits(max_expansions=8192))
    gang = next(item for item in production.legal_candidates
                if item.action_key == "gang:concealed:1w")
    route = next(route for route in gang.value_facts.routes
                 if route.conditions.draw_kind == "replacement"
                 and any(tile.code == "东" for tile in route.useful_tiles))
    assert actual.immediate_settlement == route.conditional_settlement
    with pytest.raises(ValueError, match="杠补牌"):
        analyze_given_replacement_draw(
            replace(landed, last_draw_replacement=False),
            seat=0, dealer_seat=0, config=config)


def test_given_replacement_can_open_second_concealed_gang():
    config = RuleConfig("conditional-test", 1, False)
    observation = _observation(
        hand=("1w", "1w", "1w", "2w", "2w", "2w", "3w", "4w", "5w",
              "6w", "7w", "8w", "9w"), drawn=Tile("1w"))
    _, roots = _roots(observation)
    first = roots["gang:concealed:1w"].branches[0].state
    landed = apply_given_draw(first, Tile("2w"), replacement=True)
    actual = analyze_given_replacement_draw(
        landed, seat=0, dealer_seat=0, config=config)
    assert "gang:concealed:2w" in {item.action_key for item in actual.legal_candidates}
    assert landed.chain_count == 1
    second = apply_legal_followup_gang(actual, "gang:concealed:2w")
    assert second.phase is ConditionalPhase.REPLACEMENT_DRAW
    assert second.chain_count == 2
    assert second.meld_count == 2


@pytest.mark.parametrize("phase,hand,claim_prefix", [
    ("response_peng", ("1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w",
                       "8w", "8w", "8w", "东", "南"), "peng:"),
    ("response_chi", ("1w", "2w", "4w", "5w", "6w", "7w", "8w", "9w",
                      "1b", "1b", "1b", "东", "南"), "chi:"),
])
def test_claim_discard_given_normal_draw_matches_production_value_witness(
    phase, hand, claim_prefix,
):
    config = RuleConfig("conditional-test", 1, False)
    claimed_tile = Tile("1w" if phase == "response_peng" else "3w")
    observation = _observation(
        phase=phase, last=PublicDiscard(3 if phase == "response_chi" else 1,
                                      claimed_tile, 10), hand=hand)
    rules = HangmaRules(config)
    analysis = rules.analyze(observation, value_limits=ValueAnalysisLimits(max_expansions=8192))
    roots = project_legal_roots(
        observation, _build_context(observation), analysis.legal_candidates, config=config)
    root_by_key = {item.action_key: item for item in roots}
    matched = False
    for candidate in analysis.legal_candidates:
        if not candidate.action_key.startswith(claim_prefix):
            continue
        root = root_by_key[candidate.action_key]
        assert root.claim_state.phase is ConditionalPhase.CLAIM_DISCARD
        for branch in root.branches:
            if branch.followup_discard != "南":
                continue
            landed = given_next_normal_draw(
                branch.state, Tile("东"), wall_remaining_before_draw=55,
                catch_restricted=False, allow_local_witness=True)
            actual = analyze_given_self_draw(
                landed, seat=0, dealer_seat=0, config=config)
            assert actual.local_witness_only
            route = next((route for route in candidate.value_facts.routes
                          if route.followup_discard == "南"
                          and route.conditions.draw_kind == "normal"
                          and any(tile.code == "东" for tile in route.useful_tiles)), None)
            if route is None:
                continue
            matched = True
            assert "hu" in {item.action_key for item in actual.legal_candidates}
            assert actual.immediate_settlement == route.conditional_settlement
            assert actual.issues == ()
    assert matched


def test_official_chi_then_gang_then_replacement_keeps_all_legal_claim_actions():
    """v18 实见吃→暗杠→补牌；只列吃后弃牌会漏掉合法路线。"""

    fixture = Path(__file__).parents[2] / "fixtures/official/v18/action-chain/chi-gang-draw.json"
    data = json.loads(fixture.read_text())
    events = tuple(public_event(item) for item in
                   parse_state_response({"events": data["events"]}).events)
    views = {}
    for seq_text, payload in data["snapshots"].items():
        seq = int(seq_text)
        snapshot = parse_state_response(payload).snapshot
        views[seq] = replace(
            project_observation(
                snapshot, tuple(item for item in events if item.seq <= seq),
                "vip-official-chain"),
            consumed_seq=seq,
        )
    config = RuleConfig("vip-official-chain", 1, False)
    rules = HangmaRules(config)
    before = views[2266]
    analysis = rules.analyze(before)
    roots = project_legal_roots(
        before, _build_context(before), analysis.legal_candidates, config=config)
    chi = next(item for item in roots if item.action_key == "chi:7t,8t,9t")
    claim_result = advance_given_response(
        chi, window="response_chi", discard_seat=2,
        discarded_tile=Tile("9t"), responding=(3,),
        choices=((3, next(item.action for item in analysis.legal_candidates
                          if item.action_key == chi.action_key)),),
        retained_in_river=True,
    )
    assert claim_result.resolution.status == "resolved"
    claim = analyze_given_claim_action(
        claim_result.state, seat=before.seat, config=config)
    assert {item.action_key for item in claim.legal_candidates} == {
        item.action_key for item in rules.analyze(views[2267]).legal_candidates}
    assert "gang:concealed:2w" in {item.action_key for item in claim.legal_candidates}
    assert "hu" not in {item.action_key for item in claim.legal_candidates}
    pending = apply_legal_followup_gang(claim, "gang:concealed:2w")
    assert pending.public_view.melds[before.seat][-1].kind == "gang_an"
    assert pending.public_view.hand_counts[before.seat] == (
        claim_result.state.public_view.hand_counts[before.seat] - 4)
    landed = apply_given_draw(pending, Tile("4w"), replacement=True)
    assert landed.baotou == views[2269].rule_state.baotou
    assert landed.chain_count == views[2269].rule_state.chain_count
    assert landed.concealed == _build_context(views[2269]).full_hand()
    assert landed.public_view.hand_counts == views[2269].hand_counts
    assert landed.public_view.remaining_tile_count == views[2269].remaining_tile_count
    assert tuple(tuple(m.tiles for m in row) for row in landed.public_view.melds) == (
        tuple(tuple(m.tiles for m in row) for row in views[2269].melds))
    actual = analyze_given_replacement_draw(
        landed, seat=before.seat, dealer_seat=before.dealer_seat,
        config=config)
    assert {item.action_key for item in actual.legal_candidates} == {
        item.action_key for item in rules.analyze(views[2269]).legal_candidates}


def _peng_response_root():
    observation = replace(
        _observation(phase="response_peng", last=PublicDiscard(1, Tile("1w"), 10)),
        discards=((), (Tile("1w"),), (), ()),
    )
    _, roots = _roots(observation)
    return observation, roots["peng:1w"]


@pytest.mark.parametrize("retained", [True, False])
def test_given_peng_resolution_updates_current_view_and_every_tile_capacity(retained):
    observation, root = _peng_response_root()
    assert len(root.proposal_state.concealed) == 13
    assert len(root.claim_state.concealed) == 11  # 仅成功条件，尚非裁决事实
    choices = ((2, Pass()), (3, Pass()), (0, Peng(Tile("1w"))))
    result = advance_given_response(
        root, window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=choices, retained_in_river=retained)
    assert result.resolution.status == "resolved"
    state = result.state
    assert state.phase is ConditionalPhase.CLAIM_DISCARD
    assert len(state.concealed) == 11
    assert state.public_view.hand_counts[0] == observation.hand_counts[0] - 2
    assert len(state.public_view.melds[0]) == 1
    assert len(state.public_view.discards[1]) == int(retained)
    assert state.unseen_capacities[CANONICAL_TILE_INDEX["1w"]] == 0
    assert state.public_view.snapshot_seq == observation.snapshot_seq
    assert state.public_view.consumed_seq == observation.consumed_seq
    assert state.identity.path[-1] == "response:response_peng:resolved"
    claim_analysis = analyze_given_claim_action(
        state, seat=0, config=RuleConfig("conditional-test", 1, False))
    assert "hu" not in {item.action_key for item in claim_analysis.legal_candidates}
    after_discard = apply_legal_claim_discard(claim_analysis, "discard:东")
    assert len(after_discard.concealed) == 10
    assert after_discard.public_view.discards[0][-1] == Tile("东")
    assert after_discard.public_view.hand_counts[0] == observation.hand_counts[0] - 3
    assert after_discard.public_view.snapshot_seq == observation.snapshot_seq


def test_other_exposed_gang_requires_replacement_draw_before_discard():
    """他座明杠公开获裁决后，必须接补摸，不能误走普通摸或直接跟打。"""

    before = replace(
        _observation(
            phase="response_peng", last=PublicDiscard(1, Tile("1w"), 10),
            hand=("2w", "2w", "3w", "4w", "5w", "6w", "7w",
                  "8w", "9w", "东", "南", "西", "北")),
        discards=((), (Tile("1w"),), (), ()),
    )
    _, roots = _roots(before)
    result = advance_given_response(
        roots["pass"], window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=((2, Gang(Tile("1w"), GangKind.EXPOSED)),
                 (3, Pass()), (0, Pass())), retained_in_river=False)
    assert result.resolution.status == "resolved"
    assert result.gap_kinds == ()
    waiting = result.state
    assert waiting.phase is ConditionalPhase.PUBLIC_WAIT
    assert waiting.expected_draw_seat == 2 and waiting.expected_replacement_draw
    assert waiting.public_view.melds[2][-1].kind == "gang_ming"
    assert waiting.public_view.hand_counts[2] == 10
    with pytest.raises(ValueError, match="摸牌来源"):
        advance_given_other_draw(waiting, seat=2)
    with pytest.raises(ValueError, match="当前行动座位"):
        advance_given_other_discard(waiting, seat=2, tile=Tile("9b"))
    drawn = advance_given_other_draw(waiting, seat=2, replacement=True)
    assert drawn.public_view.hand_counts[2] == 11
    assert drawn.wall_remaining == before.remaining_tile_count - 1
    assert drawn.expected_discard_seat == 2
    discarded = advance_given_other_discard(drawn, seat=2, tile=Tile("9b"))
    assert discarded.phase is ConditionalPhase.RESPONSE_RESOLUTION
    assert discarded.response_trigger == (2, Tile("9b"))
    assert discarded.public_view.snapshot_seq == before.snapshot_seq


def test_other_concealed_gang_after_normal_draw_preserves_unknown_hand():
    """他座已给定暗杠只改变公开副露和手牌数，不借牌码推断其余暗牌。"""

    before = _observation(drawn=Tile("白"))
    _, roots = _roots(before)
    waiting = roots["discard:白"].branches[0].state
    drawn = advance_given_other_draw(waiting, seat=1)
    with pytest.raises(ValueError, match="当前行动座位"):
        advance_given_other_gang(waiting, seat=1,
                                 action=Gang(Tile("9b"), GangKind.CONCEALED))
    pending = advance_given_other_gang(
        drawn, seat=1, action=Gang(Tile("9b"), GangKind.CONCEALED))
    assert pending.public_view.melds[1][-1].kind == "gang_an"
    assert pending.public_view.hand_counts[1] == drawn.public_view.hand_counts[1] - 4
    assert pending.expected_draw_seat == 1 and pending.expected_replacement_draw
    assert pending.wall_remaining == drawn.wall_remaining
    assert pending.concealed == waiting.concealed
    with pytest.raises(ValueError, match="摸牌来源"):
        advance_given_other_draw(pending, seat=1)
    replenished = advance_given_other_draw(pending, seat=1, replacement=True)
    assert replenished.public_view.hand_counts[1] == drawn.public_view.hand_counts[1] - 3
    assert replenished.wall_remaining == drawn.wall_remaining - 1
    with pytest.raises(ValueError, match="公开容量冲突"):
        advance_given_other_gang(
            replenished, seat=1,
            action=Gang(Tile("9b"), GangKind.CONCEALED))


def test_other_added_gang_upgrades_awarded_peng_without_new_hidden_fact():
    """给定他座已领我方弃牌，再给定补杠，沿用原碰的供牌证据。"""

    before = _observation(drawn=Tile("2b"))
    _, roots = _roots(before)
    awarded = advance_given_response(
        roots["discard:2b"], window="response_peng", discard_seat=0,
        discarded_tile=Tile("2b"), responding=(1, 2, 3),
        choices=((1, Peng(Tile("2b"))), (2, Pass()), (3, Pass())),
        retained_in_river=False)
    assert awarded.resolution.status == "resolved"
    claim = awarded.state
    assert claim.expected_discard_seat == 1
    assert claim.unseen_capacities[CANONICAL_TILE_INDEX["2b"]] == 1
    assert claim.unseen_evidence[CANONICAL_TILE_INDEX["2b"]] == "exact"
    added = advance_given_other_gang(
        claim, seat=1, action=Gang(Tile("2b"), GangKind.ADDED))
    assert len(added.public_view.melds[1]) == 1
    assert added.public_view.melds[1][0].kind == "gang_bu"
    assert added.public_view.melds[1][0].from_seat == 0
    assert added.public_view.claim_evidence == claim.public_view.claim_evidence
    assert added.public_view.hand_counts[1] == claim.public_view.hand_counts[1] - 1
    assert added.expected_replacement_draw and added.expected_draw_seat == 1
    assert added.unseen_capacities[CANONICAL_TILE_INDEX["2b"]] == 0
    with pytest.raises(ValueError, match="受限他座不能补杠"):
        advance_given_other_gang(
            replace(claim, catch_circle=progression.CatchPlayState(True, 0)),
            seat=1, action=Gang(Tile("2b"), GangKind.ADDED))


def test_exhaustive_draw_waits_for_responses_then_uses_shared_zero_settlement():
    """最后可摸区结束仍须先裁决碰吃；流局按同源规则零支付。"""

    before = replace(_observation(drawn=Tile("2b")), remaining_tile_count=20)
    _, roots = _roots(before)
    discarded = roots["discard:2b"].branches[0].state
    with pytest.raises(ValueError, match="已裁决"):
        finish_given_exhaustive_draw(discarded)
    peng_pass = advance_response_state(
        discarded, window="response_peng", discard_seat=0,
        discarded_tile=Tile("2b"), responding=(1, 2, 3),
        choices=((1, Pass()), (2, Pass()), (3, Pass())))
    assert peng_pass.state.phase is ConditionalPhase.RESPONSE_RESOLUTION
    with pytest.raises(ValueError, match="已裁决"):
        finish_given_exhaustive_draw(peng_pass.state)
    chi_pass = advance_response_state(
        peng_pass.state, window="response_chi", discard_seat=0,
        discarded_tile=Tile("2b"), responding=(1,), choices=((1, Pass()),))
    pending = chi_pass.state
    assert pending.phase is ConditionalPhase.PUBLIC_WAIT
    assert pending.expected_draw_seat == 1
    ended = finish_given_exhaustive_draw(pending)
    assert ended.phase is ConditionalPhase.TERMINAL
    assert ended.terminal_result == progression.exhaustive_draw_result()
    assert ended.terminal_result.score_delta == (0, 0, 0, 0)
    assert ended.public_view == pending.public_view
    assert ended.identity.path[-1] == "exhaustive-draw"


def test_given_response_missing_member_wrong_trigger_and_multi_claim_stay_visible():
    _, root = _peng_response_root()
    incomplete = advance_given_response(
        root, window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=((2, Pass()), (0, Peng(Tile("1w")))),
        retained_in_river=True)
    assert incomplete.resolution.status == "unready"
    assert incomplete.resolution.missing_seats == (3,)
    assert incomplete.state.concealed == root.proposal_state.concealed
    assert incomplete.gap_kinds == (RouteGapKind.INPUT_EVIDENCE_GAP,)
    with pytest.raises(ValueError, match="触发弃牌"):
        advance_given_response(
            root, window="response_peng", discard_seat=1,
            discarded_tile=Tile("2w"), responding=(2, 3, 0),
            choices=((2, Pass()), (3, Pass()), (0, Peng(Tile("1w")))),
            retained_in_river=True)
    blocked = advance_given_response(
        root, window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=((2, Peng(Tile("1w"))), (3, Pass()), (0, Peng(Tile("1w")))),
        retained_in_river=True)
    assert blocked.resolution.status == "blocked"
    assert blocked.state.concealed == root.proposal_state.concealed


def test_peng_all_pass_continues_from_returned_state_into_chi_window():
    observation = replace(
        _observation(phase="response_peng", last=PublicDiscard(3, Tile("3w"), 10)),
        discards=((), (), (), (Tile("3w"),)),
    )
    _, roots = _roots(observation)
    first = advance_given_response(
        roots["pass"], window="response_peng", discard_seat=3,
        discarded_tile=Tile("3w"), responding=(0, 1, 2),
        choices=((0, Pass()), (1, Pass()), (2, Pass())))
    assert first.resolution.next_window == "response_chi"
    assert first.state.response_window == "response_chi"
    assert first.state.public_view == roots["pass"].proposal_state.public_view
    with pytest.raises(ValueError, match="同源动作族合法候选"):
        advance_response_state(
            first.state, window="response_chi", discard_seat=3,
            discarded_tile=Tile("3w"), responding=(0,),
            choices=((0, Chi((Tile("1w"), Tile("3w"), Tile("4w")))),),
            retained_in_river=False)
    chi = Chi((Tile("1w"), Tile("2w"), Tile("3w")))
    second = advance_response_state(
        first.state, window="response_chi", discard_seat=3,
        discarded_tile=Tile("3w"), responding=(0,),
        choices=((0, chi),), retained_in_river=False)
    assert second.resolution.status == "resolved"
    assert second.state.phase is ConditionalPhase.CLAIM_DISCARD
    assert len(second.state.concealed) == len(observation.my_hand) - 2
    assert second.state.public_view.discards[3] == ()
    assert second.state.public_view.snapshot_seq == observation.snapshot_seq
    assert second.state.identity.path[-2:] == (
        "claim-success", "response:response_chi:resolved")


def test_public_wait_enforces_next_actor_and_white_discard_changes_circle():
    """全过后按同源裁决定下一摸；他座摸牌不读牌码，弃白直接换圈。"""

    observation = _observation(drawn=Tile("3b"))
    _, roots = _roots(observation)
    first = advance_given_response(
        roots["discard:3b"], window="response_peng", discard_seat=0,
        discarded_tile=Tile("3b"), responding=(1, 2, 3),
        choices=((1, Pass()), (2, Pass()), (3, Pass())))
    assert first.resolution.next_window == "response_chi"
    second = advance_response_state(
        first.state, window="response_chi", discard_seat=0,
        discarded_tile=Tile("3b"), responding=(1,), choices=((1, Pass()),))
    waiting = second.state
    assert waiting.phase is ConditionalPhase.PUBLIC_WAIT
    assert waiting.expected_draw_seat == 1
    with pytest.raises(ValueError, match="下一摸座位"):
        advance_given_other_draw(waiting, seat=2)
    with pytest.raises(ValueError, match="当前行动座位"):
        advance_given_other_discard(waiting, seat=1, tile=Tile("白"))
    drawn = advance_given_other_draw(waiting, seat=1)
    assert drawn.public_view.hand_counts[1] == waiting.public_view.hand_counts[1] + 1
    assert drawn.wall_remaining == waiting.wall_remaining - 1
    assert drawn.public_view.snapshot_seq == observation.snapshot_seq
    new_trigger = advance_given_other_discard(drawn, seat=1, tile=Tile("1w"))
    assert new_trigger.response_public_discard is None
    assert new_trigger.unseen_capacities[CANONICAL_TILE_INDEX["1w"]] == 0
    with pytest.raises(ValueError, match="同源动作族合法候选"):
        advance_response_state(
            new_trigger, window="response_peng", discard_seat=1,
            discarded_tile=Tile("1w"), responding=(2, 3, 0),
            choices=((2, Pass()), (3, Pass()), (0, Peng(Tile("2w")))),
            retained_in_river=False)
    claimed = advance_response_state(
        new_trigger, window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=((2, Pass()), (3, Pass()), (0, Peng(Tile("1w")))),
        retained_in_river=False)
    assert claimed.resolution.status == "resolved"
    assert claimed.state.phase is ConditionalPhase.CLAIM_DISCARD
    assert claimed.state.public_view.discards[1] == ()
    assert claimed.state.response_public_discard is None
    assert claimed.state.public_view.snapshot_seq == observation.snapshot_seq
    gang = advance_response_state(
        new_trigger, window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=((2, Pass()), (3, Pass()),
                 (0, Gang(Tile("1w"), GangKind.EXPOSED))),
        retained_in_river=False)
    assert gang.state.phase is ConditionalPhase.REPLACEMENT_DRAW
    assert gang.state.public_view.melds[0][-1].kind == "gang_ming"
    assert gang.state.public_view.hand_counts[0] == new_trigger.public_view.hand_counts[0] - 3
    assert gang.state.public_view.snapshot_seq == observation.snapshot_seq
    before_white = drawn.unseen_capacities[CANONICAL_TILE_INDEX["白"]]
    discarded = advance_given_other_discard(drawn, seat=1, tile=Tile("白"))
    assert discarded.catch_circle == progression.CatchPlayState(True, 1)
    assert discarded.catch_restricted
    assert discarded.phase is ConditionalPhase.PUBLIC_WAIT
    assert discarded.expected_draw_seat == 2
    assert discarded.response_trigger is None
    assert discarded.public_view.discards[1][-1] == Tile("白")
    assert discarded.public_view.hand_counts[1] == waiting.public_view.hand_counts[1]
    assert discarded.unseen_capacities[CANONICAL_TILE_INDEX["白"]] == before_white - 1
    assert discarded.public_view.snapshot_seq == observation.snapshot_seq


def test_given_other_discard_can_open_same_source_chi_without_official_seq():
    """给定他座摸弃后，碰窗全过、吃窗合法性仍由生产动作族判断。"""

    observation = replace(
        _observation(phase="response_peng", last=PublicDiscard(2, Tile("6b"), 10)),
        discards=((), (), (Tile("6b"),), ()),
    )
    _, roots = _roots(observation)
    first = advance_given_response(
        roots["pass"], window="response_peng", discard_seat=2,
        discarded_tile=Tile("6b"), responding=(3, 0, 1),
        choices=((3, Pass()), (0, Pass()), (1, Pass())))
    second = advance_response_state(
        first.state, window="response_chi", discard_seat=2,
        discarded_tile=Tile("6b"), responding=(3,), choices=((3, Pass()),))
    assert second.state.expected_draw_seat == 3
    drawn = advance_given_other_draw(second.state, seat=3)
    discarded = advance_given_other_discard(drawn, seat=3, tile=Tile("3w"))
    peng_pass = advance_response_state(
        discarded, window="response_peng", discard_seat=3,
        discarded_tile=Tile("3w"), responding=(0, 1, 2),
        choices=((0, Pass()), (1, Pass()), (2, Pass())))
    with pytest.raises(ValueError, match="同源动作族合法候选"):
        advance_response_state(
            peng_pass.state, window="response_chi", discard_seat=3,
            discarded_tile=Tile("3w"), responding=(0,),
            choices=((0, Chi((Tile("1w"), Tile("3w"), Tile("4w")))),),
            retained_in_river=True)
    chi = advance_response_state(
        peng_pass.state, window="response_chi", discard_seat=3,
        discarded_tile=Tile("3w"), responding=(0,),
        choices=((0, Chi((Tile("1w"), Tile("2w"), Tile("3w")))),),
        retained_in_river=True)
    assert chi.state.phase is ConditionalPhase.CLAIM_DISCARD
    assert chi.state.public_view.melds[0][-1].kind == "chi"
    assert chi.state.public_view.discards[3] == (Tile("3w"),)
    assert chi.state.public_view.snapshot_seq == observation.snapshot_seq


def test_given_other_discard_rejects_fifth_copy_known_in_own_hand():
    observation = _observation(
        hand=("1w", "1w", "1w", "1w", "2w", "3w", "4w",
              "5w", "6w", "7w", "8w", "9w", "东"),
        drawn=Tile("3b"))
    _, roots = _roots(observation)
    peng_pass = advance_given_response(
        roots["discard:3b"], window="response_peng", discard_seat=0,
        discarded_tile=Tile("3b"), responding=(1, 2, 3),
        choices=((1, Pass()), (2, Pass()), (3, Pass())))
    chi_pass = advance_response_state(
        peng_pass.state, window="response_chi", discard_seat=0,
        discarded_tile=Tile("3b"), responding=(1,), choices=((1, Pass()),))
    drawn = advance_given_other_draw(chi_pass.state, seat=1)
    with pytest.raises(ValueError, match="物理上限冲突"):
        advance_given_other_discard(drawn, seat=1, tile=Tile("1w"))


def test_official_v35_peng_then_followup_discard_matches_own_seat_snapshots():
    """v35 本座 1114→1115→1117：先裁决碰，再在未摸态打 9w。"""

    fixture = (Path(__file__).parents[2] / "fixtures/official/v35/vip-p2-natural"
               / "peng-followup-1114-1117.json")
    data = json.loads(fixture.read_text())
    parsed_events = parse_state_response({"events": data["public_or_own_events"]}).events
    events = tuple(public_event(item) for item in parsed_events)
    observations = {}
    for record in data["state_responses"]:
        response = parse_state_response(record["response"])
        seq = record["response"]["seq"]
        observations[seq] = replace(
            project_observation(
                response.snapshot, tuple(item for item in events if item.seq <= seq),
                "vip-v35-natural"),
            consumed_seq=seq,
        )
    before, after_claim, after_discard = (
        observations[1114], observations[1115], observations[1117])
    config = RuleConfig("vip-v35-natural", 1, False)
    rules = HangmaRules(config)
    analysis = rules.analyze(before)
    roots = project_legal_roots(
        before, _build_context(before), analysis.legal_candidates, config=config)
    root = next(item for item in roots if item.action_key == "peng:6b")
    assert root.proposal_state.concealed == _build_context(before).full_hand()
    assert root.claim_state.concealed != _build_context(before).full_hand()
    claim = advance_given_response(
        root, window="response_peng", discard_seat=0,
        discarded_tile=Tile("6b"), responding=(1, 2, 3),
        choices=((1, Pass()), (2, Peng(Tile("6b"))), (3, Pass())),
        retained_in_river=False,
    )
    assert claim.resolution.status == "resolved"
    state = claim.state
    assert state.concealed == _build_context(after_claim).full_hand()
    assert state.phase is ConditionalPhase.CLAIM_DISCARD
    assert state.drawn_tile is None
    assert state.public_view.discards == after_claim.discards
    assert state.public_view.hand_counts == after_claim.hand_counts
    assert tuple(tuple(m.tiles for m in row) for row in state.public_view.melds) == (
        tuple(tuple(m.tiles for m in row) for row in after_claim.melds))
    assert state.public_view.snapshot_seq == before.snapshot_seq
    assert state.public_view.consumed_seq == before.consumed_seq
    claim_actions = analyze_given_claim_action(state, seat=2, config=config)
    assert {item.action_key for item in claim_actions.legal_candidates} == {
        item.action_key for item in rules.analyze(after_claim).legal_candidates}
    played = apply_legal_claim_discard(claim_actions, "discard:9w")
    assert played.concealed == _build_context(after_discard).full_hand()
    assert played.public_view.discards[2] == after_discard.discards[2]
    assert played.public_view.hand_counts[2] == after_discard.hand_counts[2]
    assert played.public_view.snapshot_seq == before.snapshot_seq
