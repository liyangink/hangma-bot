"""SimulationEngine 基础：发牌、窗口、确定性、随机流隔离、牌张守恒。"""

from __future__ import annotations

import json

import pytest

from hangma_bot.kernel.serialization import observation_to_json
from hangma_bot.simulation import SimulationEngine, WorldState

from ._helpers import (
    make_rules,
    make_spec,
    simple_chooser,
    drive,
    total_tiles,
)


def test_start_opens_dealer_draw_window():
    """起点 = 庄家摸牌窗口：14/13/13/13、drawn=直抽、其余座位无窗口。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=11))
    state = world.progression
    assert state.window == "draw"
    assert state.turn_seat == 0
    assert world.progression.seats[0].drawn is not None
    assert len(world.progression.seats[0].hand) == 13
    for seat in (1, 2, 3):
        assert len(world.progression.seats[seat].hand) == 13
        assert world.progression.seats[seat].drawn is None
    frame = engine.frame(world)
    assert len(frame.decisions) == 1
    assert frame.decisions[0].window_key.phase.value == "draw"
    assert frame.decisions[0].window_key.trigger_seq == 0  # 首窗口无触发事件（直抽无事件）
    assert total_tiles(world) == 136


def test_wall_is_deterministic_per_scenario_seed_round():
    """同一 spec 逐字节一致；不同 seed 换牌；scenario/round 参与派生。"""
    rules = make_rules()
    engine_a = SimulationEngine(rules)
    engine_b = SimulationEngine(rules)
    spec_a = make_spec(rules, rounds=1, seed=11, scenario_id="s-a")
    spec_b = make_spec(rules, rounds=1, seed=11, scenario_id="s-b")
    spec_c = make_spec(rules, rounds=1, seed=12, scenario_id="s-a")
    world_a1 = engine_a.start(spec_a)
    world_a2 = engine_b.start(spec_a)
    assert json.dumps([t.code for t in world_a1.round_start_wall]) == json.dumps(
        [t.code for t in world_a2.round_start_wall]
    )
    assert json.dumps([t.code for t in world_a1.round_start_wall]) != json.dumps(
        [t.code for t in engine_a.start(spec_b).round_start_wall]
    )
    assert json.dumps([t.code for t in world_a1.round_start_wall]) != json.dumps(
        [t.code for t in engine_a.start(spec_c).round_start_wall]
    )


def test_full_run_determinism():
    """固定 spec/规则/发牌版本：完整桌赛结果与事件流逐字节一致。"""
    rules = make_rules()
    spec = make_spec(rules, rounds=2, seed=42)
    engine_a = SimulationEngine(rules)
    engine_b = SimulationEngine(rules)
    world_a = drive(engine_a, engine_a.start(spec), simple_chooser(rules))
    world_b = drive(engine_b, engine_b.start(spec), simple_chooser(rules))
    assert world_a.scores == world_b.scores
    assert [json.dumps(_event_dict(e), sort_keys=True) for r in world_a.round_records for e in r.events] == [
        json.dumps(_event_dict(e), sort_keys=True) for r in world_b.round_records for e in r.events
    ]
    assert json.dumps(_world_events(world_a), sort_keys=True) == json.dumps(_world_events(world_b), sort_keys=True)


def test_round_walls_independent_of_prior_choices():
    """后续单局发牌只依赖 (scenario, seed, round_no)：第 2 局牌墙不受第 1 局选择影响。"""
    rules = make_rules()
    spec = make_spec(rules, rounds=2, seed=77)
    engine_a = SimulationEngine(rules)
    engine_b = SimulationEngine(rules)

    def never_hu_chooser(decision):
        from hangma_bot.kernel.actions import Hu

        analysis = rules.analyze(decision.observation)
        candidates = analysis.legal_candidates
        if decision.window_key.phase.value in ("response_peng", "response_chi"):
            from hangma_bot.kernel.actions import Pass

            return Pass()
        for candidate in candidates:
            if not isinstance(candidate.action, Hu):
                return candidate.action
        raise AssertionError("无候选")

    # A 可胡、B 永不胡：第 1 局选择完全不同（结果可能不同），第 2 局牌墙必须一致。
    world_a = drive(engine_a, engine_a.start(spec), simple_chooser(rules))
    world_b = drive(engine_b, engine_b.start(spec), never_hu_chooser)
    assert world_a.completed_hands == 2 and world_b.completed_hands == 2
    assert json.dumps([t.code for t in world_a.round_records[1].wall]) == json.dumps(
        [t.code for t in world_b.round_records[1].wall]
    )
    # 第 2 局起手是否相同只取决于庄家轮转是否相同（牌墙本身已证一致）。
    from hangma_bot.hangma.progression import next_dealer

    hands_a = [[t.code for t in hand] for hand in world_a.round_records[1].initial_hands]
    hands_b = [[t.code for t in hand] for hand in world_b.round_records[1].initial_hands]
    dealer_a = next_dealer(0, world_a.round_records[0].winner_seat, world_a.round_records[0].is_draw)
    dealer_b = next_dealer(0, world_b.round_records[0].winner_seat, world_b.round_records[0].is_draw)
    assert (hands_a == hands_b) == (dealer_a == dealer_b)


def test_future_drawable_resampling_is_deterministic_and_observation_preserving():
    """离线未来顺序重排不改变当前观察、牌张、过去前缀或固定保留区。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=117, scenario_id="resample"))
    before = json.dumps(
        [observation_to_json(item.observation) for item in engine.frame(world).decisions],
        sort_keys=True,
        ensure_ascii=False,
    )
    first = engine.resample_future_drawable_wall(world, sample_key="sample-1")
    again = engine.resample_future_drawable_wall(world, sample_key="sample-1")
    second = engine.resample_future_drawable_wall(world, sample_key="sample-2")

    assert first.wall == again.wall
    assert first.wall != second.wall
    assert world.wall != first.wall
    assert world.wall[: world.wall_front] == first.wall[: first.wall_front]
    assert world.wall[world.wall_back :] == first.wall[first.wall_back :]
    assert sorted(tile.code for tile in world.wall) == sorted(tile.code for tile in first.wall)
    assert first.round_start_wall == first.wall
    assert world.round_start_wall == world.wall
    after = json.dumps(
        [observation_to_json(item.observation) for item in engine.frame(first).decisions],
        sort_keys=True,
        ensure_ascii=False,
    )
    assert before == after


def test_future_drawable_resampling_rejects_empty_sample_key():
    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=118))
    with pytest.raises(ValueError, match="sample_key"):
        engine.resample_future_drawable_wall(world, sample_key="")


def test_public_consistent_hidden_world_is_deterministic_and_preserves_observation():
    """隐藏教师样本固定焦点观察、区域张数与物理牌池。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=2, seed=791))
    focal = world.progression.turn_seat
    assert focal is not None
    before_observation = engine.frame(world).decisions[0].observation
    before_pool = sorted(
        [
            tile.code
            for index, seat in enumerate(world.progression.seats)
            if index != focal
            for tile in seat.hand
        ]
        + [tile.code for tile in world.wall[world.wall_front:]]
    )

    first = engine.resample_public_consistent_hidden_world(
        world, focal_seat=focal, sample_key="hidden-1"
    )
    again = engine.resample_public_consistent_hidden_world(
        world, focal_seat=focal, sample_key="hidden-1"
    )
    second = engine.resample_public_consistent_hidden_world(
        world, focal_seat=focal, sample_key="hidden-2"
    )

    assert first == again
    assert first != second
    assert world.history_consistent is True
    assert first.history_consistent is False
    assert engine.frame(first).decisions[0].observation == before_observation
    assert first.progression.seats[focal] == world.progression.seats[focal]
    assert first.wall_front == world.wall_front
    assert first.wall_back == world.wall_back
    assert first.wall[:first.wall_front] == world.wall[:world.wall_front]
    after_pool = sorted(
        [
            tile.code
            for index, seat in enumerate(first.progression.seats)
            if index != focal
            for tile in seat.hand
        ]
        + [tile.code for tile in first.wall[first.wall_front:]]
    )
    assert before_pool == after_pool
    with pytest.raises(ValueError, match="不是历史一致世界"):
        engine.export_hand(first, first.round_no)

    terminal = drive(engine, first, simple_chooser(rules))
    assert terminal.round_no == 2
    assert terminal.history_consistent is False
    with pytest.raises(ValueError, match="不是历史一致世界"):
        engine.export_hand(terminal, terminal.round_no)


def test_public_consistent_hidden_world_rejects_nonacting_focal_seat():
    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=792))
    focal = world.progression.turn_seat
    assert focal is not None
    with pytest.raises(ValueError, match="当前摸牌窗口行动座位"):
        engine.resample_public_consistent_hidden_world(
            world, focal_seat=(focal + 1) % 4, sample_key="hidden"
        )


def test_conservation_during_full_match():
    """推进全程每局牌张守恒（暗牌+副露+牌河+剩余墙=136）。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    spec = make_spec(rules, rounds=2, seed=99)
    world = engine.start(spec)
    steps = 0
    while True:
        assert total_tiles(world) == 136, "第 {0} 步牌张不守恒".format(steps)
        frame = engine.frame(world)
        if frame.blocked_reason is not None or frame.final_scores is not None:
            break
        chooser = simple_chooser(rules)
        from hangma_bot.simulation import SimulationChoice

        choices = tuple(
            SimulationChoice(decision.window_key, chooser(decision))
            for decision in frame.decisions
        )
        world = engine.advance(world, frame.revision, choices)
        steps += 1
        if steps > 600:
            raise AssertionError("超步数")


def _event_dict(event) -> dict:
    return {
        "seq": event.seq,
        "type": event.kind,
        "seat": event.seat,
        "tile": event.tile.code if event.tile is not None else "",
        "data": dict(event.data) if event.data else None,
    }


def _world_events(world: WorldState):
    return [_event_dict(event) for event in world.events]
