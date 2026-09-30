"""VIP 条件机械与真实模拟推进对拍；完整世界只在测试侧作裁判。"""

from collections import Counter

import pytest

from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.route_transition import (
    ConditionalPhase,
    advance_given_other_discard,
    advance_given_other_draw,
    advance_given_response,
    advance_response_state,
    apply_given_draw,
    project_legal_roots,
)
from hangma_bot.kernel.actions import Discard, Pass
from hangma_bot.simulation import SimulationChoice, SimulationEngine
from hangma_bot.simulation.projection import observation as project_observation

from ._helpers import make_rules, make_spec


def _assert_public_equal(state, world):
    """只对拍本人可见事实；不把他家暗牌或未来墙序送入条件量具。"""

    observed = project_observation(world, 0)
    assert state.public_view.discards == observed.discards
    assert state.public_view.melds == observed.melds
    assert state.public_view.hand_counts == observed.hand_counts
    assert state.public_view.remaining_tile_count == observed.remaining_tile_count
    assert state.wall_remaining == observed.remaining_tile_count
    assert state.dealer_seat == observed.dealer_seat
    assert Counter(tile.code for tile in state.concealed) == Counter(
        tile.code for tile in observed.my_hand + (
            (observed.drawn_tile,) if observed.drawn_tile is not None else ())
    )
    assert state.baotou == observed.rule_state.baotou
    assert state.chain_count == observed.rule_state.chain_count
    assert state.chain_piao == observed.chain_piao


def test_every_initial_discard_root_matches_simulator_public_state():
    """30 种固定起手的全部弃牌根逐个与实际推进对拍，含弃白直摸。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    compared = 0
    white_discards = 0
    for seed in range(11, 41):
        world = engine.start(make_spec(rules, rounds=1, seed=seed))
        frame = engine.frame(world)
        own = frame.decisions[0]
        analysis = rules.analyze(own.observation)
        roots = project_legal_roots(
            own.observation, _build_context(own.observation),
            analysis.legal_candidates, config=rules.config,
        )
        by_key = {root.action_key: root for root in roots}
        for candidate in analysis.legal_candidates:
            if not isinstance(candidate.action, Discard):
                continue
            root = by_key[candidate.action_key]
            assert root.gap_kind is None
            state = root.branches[0].state
            next_world = engine.advance(world, frame.revision, (
                SimulationChoice(own.window_key, candidate.action),
            ))
            if candidate.action.tile.code == "白":
                # 模拟器自动完成下家摸牌；条件量具只消费公开可见的“摸”。
                assert state.phase is ConditionalPhase.PUBLIC_WAIT
                state = advance_given_other_draw(state, seat=1)
                white_discards += 1
            else:
                assert state.phase is ConditionalPhase.RESPONSE_RESOLUTION
            _assert_public_equal(state, next_world)
            compared += 1
    assert compared >= 300
    assert white_discards > 0


def test_same_seed_full_public_circle_matches_simulation_without_hidden_inputs():
    """本人弃牌、全过、三家摸弃、再摸：逐事件核公开机械和本人暗牌。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    for seed in range(11, 41):
        world = engine.start(make_spec(rules, rounds=1, seed=seed))
        frame = engine.frame(world)
        own = frame.decisions[0]
        analysis = rules.analyze(own.observation)
        discard = next(candidate for candidate in analysis.legal_candidates
                       if isinstance(candidate.action, Discard)
                       and candidate.action.tile.code != "白")
        roots = project_legal_roots(
            own.observation, _build_context(own.observation),
            analysis.legal_candidates, config=rules.config,
        )
        root = next(item for item in roots if item.action_key == discard.action_key)
        state = root.branches[0].state
        world = engine.advance(world, frame.revision, (
            SimulationChoice(own.window_key, discard.action),
        ))
        _assert_public_equal(state, world)


        for other_seat in (1, 2, 3):
            for window in ("response_peng", "response_chi"):
                frame = engine.frame(world)
                assert world.progression.window == window
                responding = world.progression.responding
                choices = tuple((item.window_key.seat, Pass())
                                for item in frame.decisions)
                if other_seat == 1 and window == "response_peng":
                    transition = advance_given_response(
                        root, window=window, discard_seat=0,
                        discarded_tile=discard.action.tile,
                        responding=responding, choices=choices,
                    )
                else:
                    assert state.response_trigger is not None
                    feeder, tile = state.response_trigger
                    transition = advance_response_state(
                        state, window=window, discard_seat=feeder,
                        discarded_tile=tile, responding=responding,
                        choices=choices,
                    )
                assert transition.resolution.status == "resolved"
                state = transition.state
                world = engine.advance(world, frame.revision, tuple(
                    SimulationChoice(item.window_key, Pass())
                    for item in frame.decisions
                ))
                if window == "response_peng":
                    _assert_public_equal(state, world)
            assert state.phase is ConditionalPhase.PUBLIC_WAIT
            assert state.expected_draw_seat == other_seat
            state = advance_given_other_draw(state, seat=other_seat)
            _assert_public_equal(state, world)
            frame = engine.frame(world)
            assert frame.decisions[0].window_key.seat == other_seat
            their_analysis = rules.analyze(frame.decisions[0].observation)
            their_discard = next(
                item.action for item in their_analysis.legal_candidates
                if isinstance(item.action, Discard)
                and item.action.tile.code != "白"
            )
            state = advance_given_other_discard(
                state, seat=other_seat, tile=their_discard.tile,
            )
            world = engine.advance(world, frame.revision, (
                SimulationChoice(frame.decisions[0].window_key, their_discard),
            ))
            _assert_public_equal(state, world)

        for window in ("response_peng", "response_chi"):
            frame = engine.frame(world)
            assert world.progression.window == window
            assert state.response_trigger is not None
            feeder, tile = state.response_trigger
            transition = advance_response_state(
                state, window=window, discard_seat=feeder,
                discarded_tile=tile,
                responding=world.progression.responding,
                choices=tuple((item.window_key.seat, Pass())
                              for item in frame.decisions),
            )
            assert transition.resolution.status == "resolved"
            state = transition.state
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key, Pass())
                for item in frame.decisions
            ))
            if window == "response_peng":
                _assert_public_equal(state, world)
        assert state.phase is ConditionalPhase.NORMAL_DRAW
        assert state.expected_draw_seat == 0
        observed = project_observation(world, 0)
        assert observed.drawn_tile is not None
        state = apply_given_draw(state, observed.drawn_tile, replacement=False)
        assert state.phase is ConditionalPhase.DRAW_ACTION
        _assert_public_equal(state, world)


@pytest.mark.parametrize("seed,discard_key,claim_window,claim_key", (
    (13, "discard:1w", "response_peng", "peng:1w"),
    (21, "discard:2w", "response_chi", "chi:1w,2w,3w"),
))
def test_given_other_claim_matches_simulator_public_award(
    seed, discard_key, claim_window, claim_key,
):
    """他家实际碰/吃由公开裁决给定，条件量具只核本座可见后态。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=seed))
    frame = engine.frame(world)
    own = frame.decisions[0]
    analysis = rules.analyze(own.observation)
    discard = next(item for item in analysis.legal_candidates
                   if item.action_key == discard_key)
    root = next(item for item in project_legal_roots(
        own.observation, _build_context(own.observation),
        analysis.legal_candidates, config=rules.config,
    ) if item.action_key == discard_key)
    state = root.branches[0].state
    world = engine.advance(world, frame.revision, (
        SimulationChoice(own.window_key, discard.action),
    ))
    if claim_window == "response_chi":
        frame = engine.frame(world)
        transition = advance_given_response(
            root, window="response_peng", discard_seat=0,
            discarded_tile=discard.action.tile,
            responding=world.progression.responding,
            choices=tuple((item.window_key.seat, Pass())
                          for item in frame.decisions),
        )
        assert transition.resolution.status == "resolved"
        state = transition.state
        world = engine.advance(world, frame.revision, tuple(
            SimulationChoice(item.window_key, Pass())
            for item in frame.decisions
        ))
    frame = engine.frame(world)
    assert world.progression.window == claim_window
    claimant = next(item for item in frame.decisions
                    if item.window_key.seat == 1)
    claim = next(item.action for item in rules.analyze(
        claimant.observation).legal_candidates if item.action_key == claim_key)
    choices = tuple((item.window_key.seat,
                     claim if item.window_key.seat == 1 else Pass())
                    for item in frame.decisions)
    common = dict(
        window=claim_window, discard_seat=0,
        discarded_tile=discard.action.tile,
        responding=world.progression.responding,
        choices=choices, retained_in_river=True,
    )
    transition = (advance_given_response(root, **common)
                  if claim_window == "response_peng"
                  else advance_response_state(state, **common))
    assert transition.resolution.status == "resolved"
    world = engine.advance(world, frame.revision, tuple(
        SimulationChoice(item.window_key, action)
        for item, (_, action) in zip(frame.decisions, choices)
    ))
    assert transition.state.phase is ConditionalPhase.PUBLIC_WAIT
    assert transition.state.expected_discard_seat == 1
    _assert_public_equal(transition.state, world)

