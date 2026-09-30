"""VIP 条件机械与真实模拟推进对拍；完整世界只在测试侧作裁判。"""

from collections import Counter
from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.route_transition import (
    ConditionalPhase,
    advance_given_other_discard,
    advance_given_other_draw,
    advance_given_other_gang,
    advance_given_response,
    advance_response_state,
    apply_given_draw,
    apply_legal_draw_discard,
    apply_legal_draw_hu,
    analyze_given_claim_action,
    finish_given_exhaustive_draw,
    finish_given_official_other_win,
    analyze_given_self_draw,
    apply_legal_claim_discard,
    apply_legal_followup_gang,
    project_legal_roots,
)
from hangma_bot.kernel.actions import (
    CANONICAL_TILE_ORDER, Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile,
)
from hangma_bot.simulation import SimulationChoice, SimulationEngine
from hangma_bot.simulation.projection import (
    observation as project_observation, public_history_for,
)

from ._helpers import build_full_world_row, make_rules, make_spec, total_tiles


def _assert_public_equal(state, world):
    """只对拍本人可见事实；不把他家暗牌或未来墙序送入条件量具。"""

    observed = project_observation(world, 0)
    assert state.public_view.discards == observed.discards
    # 模拟器对外把三类杠统称 gang，内部 MeldRecord.gang_kind 才保留
    # an/ming/bu；官方条件视图按实见快照使用 gang_an/ming/bu。
    normalized_melds = tuple(tuple(
        replace(observed.melds[seat][index],
                kind=(f"gang_{meld.gang_kind}" if meld.kind == "gang"
                      else meld.kind))
        for index, meld in enumerate(world.progression.seats[seat].melds)
    ) for seat in range(4))
    assert state.public_view.melds == normalized_melds
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
    assert state.catch_circle.active == observed.rule_state.catch_play
    assert state.catch_circle.owner == observed.rule_state.catch_play_owner_seat


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


def test_full_no_claim_hands_reach_same_rule_terminal():
    """完整单局同一条件链：流局、本座胡与给定他座胡同源终止。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    own_wins = 0
    other_wins = 0
    for seed in (*range(11, 21), 34, 39):
        world = engine.start(make_spec(rules, rounds=1, seed=seed))
        frame = engine.frame(world)
        own = frame.decisions[0]
        analysis = rules.analyze(own.observation)
        first = next(item for item in analysis.legal_candidates
                     if isinstance(item.action, Discard)
                     and item.action.tile.code != "白")
        root = next(item for item in project_legal_roots(
            own.observation, _build_context(own.observation),
            analysis.legal_candidates, config=rules.config,
        ) if item.action_key == first.action_key)
        state = root.branches[0].state
        world = engine.advance(world, frame.revision, (
            SimulationChoice(own.window_key, first.action),
        ))
        _assert_public_equal(state, world)

        for _ in range(300):
            if world.progression.window in ("ended", "match_end"):
                if state.phase is not ConditionalPhase.TERMINAL:
                    state = finish_given_exhaustive_draw(state)
                assert state.terminal_result == world.progression.hand_result
                break
            frame = engine.frame(world)
            if world.progression.window.startswith("response_"):
                assert state.phase is ConditionalPhase.RESPONSE_RESOLUTION
                assert state.response_trigger is not None
                feeder, tile = state.response_trigger
                transition = advance_response_state(
                    state, window=world.progression.window,
                    discard_seat=feeder, discarded_tile=tile,
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
                if world.progression.window not in ("ended", "match_end", "draw"):
                    _assert_public_equal(state, world)
                continue

            assert world.progression.window == "draw"
            decision = frame.decisions[0]
            seat = decision.window_key.seat
            if seat == 0:
                assert state.phase is ConditionalPhase.NORMAL_DRAW
                assert decision.observation.drawn_tile is not None
                state = apply_given_draw(
                    state, decision.observation.drawn_tile,
                    replacement=False,
                )
                given = analyze_given_self_draw(
                    state, seat=0, dealer_seat=world.progression.dealer_seat,
                    config=rules.config,
                )
                production = rules.analyze(decision.observation)
                assert {item.action_key for item in given.legal_candidates} == {
                    item.action_key for item in production.legal_candidates
                }
                if seed == 39 and any(
                    isinstance(item.action, Hu) for item in given.legal_candidates
                ):
                    candidate = next(item for item in given.legal_candidates
                                     if isinstance(item.action, Hu))
                    state = apply_legal_draw_hu(given)
                    own_wins += 1
                else:
                    candidate = next(item for item in given.legal_candidates
                                     if isinstance(item.action, Discard)
                                     and item.action.tile.code != "白")
                    state = apply_legal_draw_discard(given, candidate.action_key)
            else:
                assert state.phase is ConditionalPhase.PUBLIC_WAIT
                state = advance_given_other_draw(state, seat=seat)
                production = rules.analyze(decision.observation)
                if seed == 34 and any(
                    isinstance(item.action, Hu)
                    for item in production.legal_candidates
                ):
                    world = engine.advance(world, frame.revision, (
                        SimulationChoice(decision.window_key, Hu()),
                    ))
                    event = next(item for item in public_history_for(
                        world.events, seat=0) if item.kind == "round_ended")
                    state = finish_given_official_other_win(
                        state, event, game_id=world.match_id,
                        round_no=world.round_no,
                    )
                    assert state.terminal_result == world.progression.hand_result
                    other_wins += 1
                    continue
                candidate = next(item for item in production.legal_candidates
                                 if isinstance(item.action, Discard)
                                 and item.action.tile.code != "白")
                state = advance_given_other_discard(
                    state, seat=seat, tile=candidate.action.tile,
                )
            world = engine.advance(world, frame.revision, (
                SimulationChoice(decision.window_key, candidate.action),
            ))
            if state.phase is ConditionalPhase.TERMINAL:
                assert state.terminal_result == world.progression.hand_result
            else:
                _assert_public_equal(state, world)
        else:
            raise AssertionError("固定单局未在 300 个窗口内结束")
    assert own_wins == 1
    assert other_wins == 1


def test_initial_white_discard_catch_circle_reaches_next_own_draw():
    """弃白跳过响应并开抓打圈后，给定三家真实公开动作到本人再摸。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    other_white_to_self = 0
    for seed in (16, 20, 22, 28, 33, 36, 39, 40):
        world = engine.start(make_spec(rules, rounds=1, seed=seed))
        frame = engine.frame(world)
        own = frame.decisions[0]
        analysis = rules.analyze(own.observation)
        discard = next(item for item in analysis.legal_candidates
                       if item.action_key == "discard:白")
        root = next(item for item in project_legal_roots(
            own.observation, _build_context(own.observation),
            analysis.legal_candidates, config=rules.config,
        ) if item.action_key == discard.action_key)
        state = root.branches[0].state
        assert state.phase is ConditionalPhase.PUBLIC_WAIT
        assert state.catch_circle.active and state.catch_circle.owner == 0
        world = engine.advance(world, frame.revision, (
            SimulationChoice(own.window_key, discard.action),
        ))

        for _ in range(30):
            frame = engine.frame(world)
            if world.progression.window == "draw":
                decision = frame.decisions[0]
                seat = decision.window_key.seat
                if seat == 0:
                    assert state.phase is ConditionalPhase.NORMAL_DRAW
                    state = apply_given_draw(
                        state, decision.observation.drawn_tile,
                        replacement=False,
                    )
                    _assert_public_equal(state, world)
                    given = analyze_given_self_draw(
                        state, seat=0,
                        dealer_seat=world.progression.dealer_seat,
                        config=rules.config,
                    )
                    assert {item.action_key for item in given.legal_candidates} == {
                        item.action_key for item in rules.analyze(
                            decision.observation).legal_candidates
                    }
                    next_discard = next(
                        item for item in given.legal_candidates
                        if isinstance(item.action, Discard)
                    )
                    state = apply_legal_draw_discard(
                        given, next_discard.action_key,
                    )
                    world = engine.advance(world, frame.revision, (
                        SimulationChoice(decision.window_key,
                                         next_discard.action),
                    ))
                    if next_discard.action.tile.code == "白":
                        state = advance_given_other_draw(state, seat=1)
                    _assert_public_equal(state, world)
                    break
                state = advance_given_other_draw(state, seat=seat)
                _assert_public_equal(state, world)
                candidates = rules.analyze(decision.observation).legal_candidates
                their_discard = next(item.action for item in candidates
                                     if isinstance(item.action, Discard))
                state = advance_given_other_discard(
                    state, seat=seat, tile=their_discard.tile,
                )
                if seat == 3 and their_discard.tile.code == "白":
                    assert state.phase is ConditionalPhase.NORMAL_DRAW
                    assert state.expected_draw_seat == 0
                    other_white_to_self += 1
                world = engine.advance(world, frame.revision, (
                    SimulationChoice(decision.window_key, their_discard),
                ))
                if world.progression.window.startswith("response_"):
                    _assert_public_equal(state, world)
                continue
            assert world.progression.window.startswith("response_")
            assert state.response_trigger is not None
            feeder, tile = state.response_trigger
            transition = advance_response_state(
                state, window=world.progression.window,
                discard_seat=feeder, discarded_tile=tile,
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
            if world.progression.window.startswith("response_"):
                _assert_public_equal(state, world)
        else:
            raise AssertionError("弃白后未在 30 个窗口内回到本人普通摸牌")
    assert other_white_to_self > 0


def test_concealed_gang_replacement_and_hu_match_simulator():
    """构造四张暗杠后补摸胡，核公开副露、资格和四座真实结算。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    focal = ["1w", "1w", "1w", "2w", "3w", "4w", "7w",
             "8w", "9w", "5w", "6w", "东", "东"]
    remaining = [code for code in CANONICAL_TILE_ORDER for _ in range(4)]
    for code in focal + ["1w"]:
        remaining.remove(code)
    other = remaining[-39:]
    wall = remaining[:-39]
    draw_index = wall.index("7w")
    wall[draw_index], wall[-21] = wall[-21], wall[draw_index]
    row = build_full_world_row(
        rules,
        hands13=[focal, other[:13], other[13:26], other[26:]],
        dealer_drawn="1w",
        wall=wall,
        dealer=0,
    )
    world = engine.from_replay(row)
    frame = engine.frame(world)
    own = frame.decisions[0]
    analysis = rules.analyze(own.observation)
    root = next(item for item in project_legal_roots(
        own.observation, _build_context(own.observation),
        analysis.legal_candidates, config=rules.config,
    ) if item.action_key == "gang:concealed:1w")
    state = root.branches[0].state
    assert state.phase is ConditionalPhase.REPLACEMENT_DRAW
    world = engine.advance(world, frame.revision, (
        SimulationChoice(own.window_key,
                         Gang(Tile("1w"), GangKind.CONCEALED)),
    ))
    observed = project_observation(world, 0)
    assert observed.drawn_tile is not None
    state = apply_given_draw(state, observed.drawn_tile, replacement=True)
    _assert_public_equal(state, world)
    given = analyze_given_self_draw(
        state, seat=0, dealer_seat=0, config=rules.config,
    )
    assert {item.action_key for item in given.legal_candidates} == {
        item.action_key for item in rules.analyze(observed).legal_candidates
    }
    state = apply_legal_draw_hu(given)
    frame = engine.frame(world)
    world = engine.advance(world, frame.revision, (
        SimulationChoice(frame.decisions[0].window_key, Hu()),
    ))
    assert state.terminal_result == world.progression.hand_result


def test_other_exposed_gang_award_replacement_and_discard_match_simulator():
    """物理有效四张明杠：公开裁决、他座补摸、跟打逐步对拍。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    pool = [code for code in CANONICAL_TILE_ORDER for _ in range(4)]
    for _ in range(4):
        pool.remove("5w")
    row = build_full_world_row(
        rules,
        hands13=[
            pool[:13], ["5w"] * 3 + pool[13:23],
            pool[23:36], pool[36:49],
        ],
        dealer_drawn="5w", wall=pool[49:], dealer=0,
    )
    world = engine.from_replay(row)
    frame = engine.frame(world)
    own = frame.decisions[0]
    analysis = rules.analyze(own.observation)
    root = next(item for item in project_legal_roots(
        own.observation, _build_context(own.observation),
        analysis.legal_candidates, config=rules.config,
    ) if item.action_key == "discard:5w")
    world = engine.advance(world, frame.revision, (
        SimulationChoice(own.window_key, Discard(Tile("5w"))),
    ))
    frame = engine.frame(world)
    gang = Gang(Tile("5w"), GangKind.EXPOSED)
    assert any(item.action_key == "gang:exposed:5w" for item in
               rules.analyze(next(item for item in frame.decisions
                                  if item.window_key.seat == 1).observation
                             ).legal_candidates)
    choices = tuple((item.window_key.seat,
                     gang if item.window_key.seat == 1 else Pass())
                    for item in frame.decisions)
    transition = advance_given_response(
        root, window="response_peng", discard_seat=0,
        discarded_tile=Tile("5w"),
        responding=world.progression.responding,
        choices=choices, retained_in_river=True,
    )
    assert transition.resolution.status == "resolved"
    assert transition.state.expected_replacement_draw
    world = engine.advance(world, frame.revision, tuple(
        SimulationChoice(item.window_key, action)
        for item, (_, action) in zip(frame.decisions, choices)
    ))
    state = advance_given_other_draw(
        transition.state, seat=1, replacement=True,
    )
    _assert_public_equal(state, world)
    frame = engine.frame(world)
    their_discard = next(item.action for item in
                         rules.analyze(frame.decisions[0].observation
                                       ).legal_candidates
                         if isinstance(item.action, Discard))
    state = advance_given_other_discard(
        state, seat=1, tile=their_discard.tile,
    )
    world = engine.advance(world, frame.revision, (
        SimulationChoice(frame.decisions[0].window_key, their_discard),
    ))
    _assert_public_equal(state, world)


def test_other_added_gang_after_peng_matches_continuous_public_path():
    """他座先碰再等真实第四张补杠；全程不给条件量具他座暗牌。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    pool = [code for code in CANONICAL_TILE_ORDER for _ in range(4)]
    for _ in range(4):
        pool.remove("5w")
    wall = pool[50:] + ["5w"]
    source = wall.index("5w")
    wall[source], wall[3] = wall[3], wall[source]
    row = build_full_world_row(
        rules,
        hands13=[
            pool[:13], ["5w", "5w"] + pool[13:24],
            pool[24:37], pool[37:50],
        ],
        dealer_drawn="5w", wall=wall, dealer=0,
    )
    world = engine.from_replay(row)
    frame = engine.frame(world)
    own = frame.decisions[0]
    analysis = rules.analyze(own.observation)
    root = next(item for item in project_legal_roots(
        own.observation, _build_context(own.observation),
        analysis.legal_candidates, config=rules.config,
    ) if item.action_key == "discard:5w")
    state = root.branches[0].state
    world = engine.advance(world, frame.revision, (
        SimulationChoice(own.window_key, Discard(Tile("5w"))),
    ))
    _assert_public_equal(state, world)

    for step in range(1, 30):
        frame = engine.frame(world)
        if world.progression.window.startswith("response_"):
            window = world.progression.window
            claim = step == 1
            choices = tuple((item.window_key.seat,
                             Peng(Tile("5w")) if claim and
                             item.window_key.seat == 1 else Pass())
                            for item in frame.decisions)
            assert state.response_trigger is not None
            feeder, tile = state.response_trigger
            common = dict(
                window=window, discard_seat=feeder, discarded_tile=tile,
                responding=world.progression.responding, choices=choices,
                retained_in_river=True if claim else None,
            )
            transition = (advance_given_response(root, **common) if claim
                          else advance_response_state(state, **common))
            assert transition.resolution.status == "resolved"
            state = transition.state
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key, action)
                for item, (_, action) in zip(frame.decisions, choices)
            ))
            if world.progression.window.startswith("response_") or claim:
                _assert_public_equal(state, world)
            continue

        assert world.progression.window == "draw"
        decision = frame.decisions[0]
        seat = decision.window_key.seat
        observed = decision.observation
        if observed.drawn_tile is None:
            assert seat == 1 and state.expected_discard_seat == 1
        elif seat == 0:
            assert state.phase is ConditionalPhase.NORMAL_DRAW
            state = apply_given_draw(
                state, observed.drawn_tile, replacement=False,
            )
            _assert_public_equal(state, world)
        else:
            state = advance_given_other_draw(state, seat=seat)
            _assert_public_equal(state, world)

        if seat == 1 and observed.drawn_tile == Tile("5w"):
            gang = Gang(Tile("5w"), GangKind.ADDED)
            assert any(item.action_key == "gang:added:5w" for item in
                       rules.analyze(observed).legal_candidates)
            state = advance_given_other_gang(state, seat=1, action=gang)
            world = engine.advance(world, frame.revision, (
                SimulationChoice(decision.window_key, gang),
            ))
            state = advance_given_other_draw(state, seat=1, replacement=True)
            _assert_public_equal(state, world)
            break

        production = rules.analyze(observed)
        discard = next(item for item in production.legal_candidates
                       if isinstance(item.action, Discard)
                       and item.action.tile.code != "白")
        if seat == 0:
            given = analyze_given_self_draw(
                state, seat=0, dealer_seat=world.progression.dealer_seat,
                config=rules.config,
            )
            assert {item.action_key for item in given.legal_candidates} == {
                item.action_key for item in production.legal_candidates
            }
            state = apply_legal_draw_discard(given, discard.action_key)
        else:
            state = advance_given_other_discard(
                state, seat=seat, tile=discard.action.tile,
            )
        world = engine.advance(world, frame.revision, (
            SimulationChoice(decision.window_key, discard.action),
        ))
        _assert_public_equal(state, world)
    else:
        raise AssertionError("物理指定的第四张 5w 未进入他座补杠窗口")


def _triple_gang_world(rules, engine, *, focal_seat):
    """完整136实体牌构造三杠链；预定摸牌仅属于模拟裁判的墙。"""

    focal = ["1w"] * 4 + ["2w"] * 4 + ["3w"] * 4 + ["东"]
    dealer_drawn = "东" if focal_seat == 0 else "白"
    required_wall = (["东"] if focal_seat == 1 else []) + ["4w", "5w", "6w"]
    pool = [code for code in CANONICAL_TILE_ORDER for _ in range(4)]
    for code in focal + [dealer_drawn] + required_wall:
        pool.remove(code)
    others, wall = pool[:39], pool[39:] + required_wall
    hands = [others[:13], others[13:26], others[26:]]
    hands.insert(focal_seat, focal)
    if focal_seat == 1:
        normal = wall.index("东")
        wall[normal], wall[0] = wall[0], wall[normal]
    for offset, code in enumerate(("4w", "5w", "6w"), 21):
        source = wall.index(code)
        wall[source], wall[-offset] = wall[-offset], wall[source]
    row = build_full_world_row(rules, hands13=hands, dealer_drawn=dealer_drawn,
                               wall=wall, dealer=0)
    world = engine.from_replay(row)
    assert total_tiles(world) == 136
    return world


@pytest.mark.parametrize("focal_seat", (0, 1))
@pytest.mark.parametrize("start_wall", (83, 23))
def test_three_gangs_and_terminal_match_independent_public_projection(focal_seat, start_wall):
    """本人/他座三次暗杠补摸至胡，逐步核136张守恒与公开投影。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    world = _triple_gang_world(rules, engine, focal_seat=focal_seat)
    if start_wall == 23:
        # 构造具有完整实体牌的末墙公开快照。移到河中的60张是已发生公开
        # 前缀，后续条件量具仍只消费投影，不读取余墙。这不冒充自然牌谱。
        consumed = world.wall[:60]
        if focal_seat == 1:
            # 第1张原定普通摸东留在未消费区，临界场景仍先正常摸后再杠。
            wall = list(world.wall)
            wall[0], wall[60] = wall[60], wall[0]
            world = replace(world, wall=tuple(wall))
            consumed = world.wall[:60]
        seats = list(world.progression.seats)
        for seat, prefix in zip((1, 2, 3), (consumed[:20], consumed[20:40], consumed[40:])):
            seats[seat] = replace(seats[seat], discards=tuple(prefix))
        world = replace(world, wall_front=60,
                        progression=replace(world.progression, seats=tuple(seats),
                                            wall_drawable=3, wall_total=23))
        assert total_tiles(world) == 136
    own = engine.frame(world).decisions[0]
    analysis = rules.analyze(own.observation)
    roots = project_legal_roots(
        own.observation, _build_context(own.observation),
        analysis.legal_candidates, config=rules.config)
    if focal_seat == 0:
        state = next(item for item in roots if item.action_key == "gang:concealed:1w").branches[0].state
        first = 0
    else:
        state = next(item for item in roots if item.action_key == "discard:白").branches[0].state
        world = engine.advance(world, engine.frame(world).revision, (
            SimulationChoice(own.window_key, Discard(Tile("白"))),))
        state = advance_given_other_draw(state, seat=1)
        _assert_public_equal(state, world)
        first = 1
    gang_count = min(3, start_wall - 20 - first)
    for index, code in enumerate(("1w", "2w", "3w")[:gang_count]):
        frame = engine.frame(world)
        decision = frame.decisions[0]
        production = rules.analyze(decision.observation)
        key = "gang:concealed:" + code
        assert key in {item.action_key for item in production.legal_candidates}
        if focal_seat == 1:
            state = advance_given_other_gang(
                state, seat=1, action=Gang(Tile(code), GangKind.CONCEALED))
        elif index > 0:
            given = analyze_given_self_draw(state, seat=0, dealer_seat=0, config=rules.config)
            assert {item.action_key for item in given.legal_candidates} == {
                item.action_key for item in production.legal_candidates}
            state = apply_legal_followup_gang(given, key)
        world = engine.advance(world, frame.revision, (
            SimulationChoice(decision.window_key, Gang(Tile(code), GangKind.CONCEALED)),))
        if focal_seat == 0:
            landed = project_observation(world, 0)
            state = apply_given_draw(state, landed.drawn_tile, replacement=True)
        else:
            # 条件量具只读公开的补摸来源，永远不获他座的补牌码。
            state = advance_given_other_draw(state, seat=1, replacement=True)
        _assert_public_equal(state, world)
        assert total_tiles(world) == 136
        assert state.wall_remaining == start_wall - 1 - first - index
    frame = engine.frame(world)
    final_candidates = rules.analyze(frame.decisions[0].observation).legal_candidates
    if start_wall == 23:
        assert not any(isinstance(item.action, Gang) for item in final_candidates)
    if gang_count < 3:
        # 他座先普通摸耗掉一张，所以23张仅容两次杠补；不能再假定第三杠。
        assert focal_seat == 1 and state.wall_remaining == 20
        discard = next(item.action for item in final_candidates
                       if isinstance(item.action, Discard))
        state = advance_given_other_discard(state, seat=1, tile=discard.tile)
        world = engine.advance(world, frame.revision, (
            SimulationChoice(frame.decisions[0].window_key, discard),))
        while world.progression.window.startswith("response_"):
            frame = engine.frame(world)
            window = world.progression.window
            responding = world.progression.responding
            transition = advance_response_state(
                state, window=window, discard_seat=1, discarded_tile=discard.tile,
                responding=responding, choices=tuple((seat, Pass()) for seat in responding))
            state = transition.state
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key, Pass()) for item in frame.decisions))
        state = finish_given_exhaustive_draw(state)
        assert state.terminal_result == world.progression.hand_result
        assert total_tiles(world) == 136
        return
    assert any(isinstance(item.action, Hu) for item in final_candidates)
    if focal_seat == 0:
        given = analyze_given_self_draw(state, seat=0, dealer_seat=0, config=rules.config)
        state = apply_legal_draw_hu(given)
    next_world = engine.advance(world, frame.revision, (
        SimulationChoice(frame.decisions[0].window_key, Hu()),))
    if focal_seat == 1:
        event = next(item for item in public_history_for(next_world.events, seat=0)
                     if item.kind == "round_ended")
        state = finish_given_official_other_win(
            state, event, game_id=world.match_id, round_no=world.round_no)
    assert state.terminal_result == next_world.progression.hand_result
    assert total_tiles(next_world) == 136
    assert state.public_view.snapshot_seq == own.observation.snapshot_seq


def test_mixed_claim_and_gang_public_paths_match_simulator():
    """多种自然牌山持续推进；他家暗牌仅供模拟器裁判，不进入条件转移。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    coverage = Counter()
    for seed in range(101, 131):
        world = engine.start(make_spec(rules, rounds=1, seed=seed))
        frame = engine.frame(world)
        own = frame.decisions[0]
        analysis = rules.analyze(own.observation)
        first = next(item for item in analysis.legal_candidates
                     if isinstance(item.action, Discard)
                     and item.action.tile.code != "白")
        root = next(item for item in project_legal_roots(
            own.observation, _build_context(own.observation),
            analysis.legal_candidates, config=rules.config,
        ) if item.action_key == first.action_key)
        state = root.branches[0].state
        world = engine.advance(world, frame.revision, (
            SimulationChoice(own.window_key, first.action),
        ))
        for step in range(400):
            if world.progression.window in ("ended", "match_end"):
                if state.phase is not ConditionalPhase.TERMINAL:
                    state = finish_given_exhaustive_draw(state)
                    coverage["draw"] += 1
                assert state.terminal_result == world.progression.hand_result
                break
            frame = engine.frame(world)
            coverage["windows"] += 1
            if world.progression.window.startswith("response_"):
                coverage["response_windows"] += 1
                assert state.phase is ConditionalPhase.RESPONSE_RESOLUTION
                choices = []
                claimed = False
                for decision in frame.decisions:
                    candidates = rules.analyze(decision.observation).legal_candidates
                    claims = [item.action for item in candidates
                              if isinstance(item.action, (Chi, Peng, Gang))]
                    if claims and not claimed and (seed + step) % 2 == 0:
                        action = claims[0]
                        claimed = True
                        coverage[type(action).__name__] += 1
                    else:
                        action = Pass()
                    choices.append((decision.window_key.seat, action))
                feeder, tile = state.response_trigger
                before = len(world.progression.seats[feeder].discards)
                next_world = engine.advance(world, frame.revision, tuple(
                    SimulationChoice(decision.window_key, action)
                    for decision, (_, action) in zip(frame.decisions, choices)
                ))
                retained = (len(next_world.progression.seats[feeder].discards)
                            == before) if claimed else None
                transition = advance_response_state(
                    state, window=world.progression.window,
                    discard_seat=feeder, discarded_tile=tile,
                    responding=world.progression.responding,
                    choices=tuple(choices), retained_in_river=retained,
                )
                assert transition.resolution.status == "resolved"
                state, world = transition.state, next_world
                continue

            assert world.progression.window == "draw"
            coverage["action_windows"] += 1
            decision = frame.decisions[0]
            seat = decision.window_key.seat
            observed = decision.observation
            if observed.drawn_tile is not None:
                replacement = state.phase is ConditionalPhase.REPLACEMENT_DRAW or (
                    state.phase is ConditionalPhase.PUBLIC_WAIT and
                    state.expected_replacement_draw)
                if seat == 0:
                    state = apply_given_draw(state, observed.drawn_tile,
                                             replacement=replacement)
                else:
                    state = advance_given_other_draw(
                        state, seat=seat, replacement=replacement)
                if replacement:
                    coverage["replacement_draws"] += 1
            else:
                coverage["claim_followup_windows"] += 1
            _assert_public_equal(state, world)
            production = rules.analyze(observed)
            candidates = production.legal_candidates
            if seat == 0:
                given = (analyze_given_self_draw(
                    state, seat=0, dealer_seat=observed.dealer_seat,
                    config=rules.config,
                ) if observed.drawn_tile is not None else
                    analyze_given_claim_action(state, seat=0,
                                               config=rules.config))
                assert {item.action_key for item in given.legal_candidates} == {
                    item.action_key for item in candidates
                }
            else:
                given = None
            wins = [item for item in candidates if isinstance(item.action, Hu)]
            gangs = [item for item in candidates if isinstance(item.action, Gang)]
            discards = [item for item in candidates
                        if isinstance(item.action, Discard)]
            if wins and (seed + step) % 3 != 0:
                candidate = wins[0]
                if seat == 0:
                    state = apply_legal_draw_hu(given)
                    coverage["self_hu"] += 1
            elif gangs and (seed + step) % 2 == 0:
                candidate = gangs[0]
                if seat == 0:
                    state = apply_legal_followup_gang(given,
                                                       candidate.action_key)
                else:
                    state = advance_given_other_gang(
                        state, seat=seat, action=candidate.action)
                coverage["gang_" + candidate.action.kind.value] += 1
            else:
                pool = [item for item in discards
                        if item.action.tile.code != "白"] or discards
                candidate = pool[(seed + step) % len(pool)]
                if seat == 0:
                    state = (apply_legal_draw_discard(given, candidate.action_key)
                             if observed.drawn_tile is not None else
                             apply_legal_claim_discard(given,
                                                       candidate.action_key))
                else:
                    state = advance_given_other_discard(
                        state, seat=seat, tile=candidate.action.tile)
            next_world = engine.advance(world, frame.revision, (
                SimulationChoice(decision.window_key, candidate.action),
            ))
            if isinstance(candidate.action, Hu) and seat != 0:
                event = next(item for item in public_history_for(
                    next_world.events, seat=0) if item.kind == "round_ended")
                state = finish_given_official_other_win(
                    state, event, game_id=world.match_id,
                    round_no=world.round_no)
                coverage["other_hu"] += 1
            world = next_world
        else:
            raise AssertionError("混合选择单局未在 400 帧内结束")
    assert coverage["Peng"] > 0
    assert coverage["Chi"] > 0
    assert coverage["gang_concealed"] + coverage["gang_added"] > 0
    assert coverage["self_hu"] + coverage["other_hu"] + coverage["draw"] == 30
    print("VIP mixed conditional differential:", dict(sorted(coverage.items())))
