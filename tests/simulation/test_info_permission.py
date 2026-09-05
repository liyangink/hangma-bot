"""信息权限：替换他家手牌/未来牌墙不改变玩家观察；公开事实变化才改变。"""

from __future__ import annotations

import json
from dataclasses import replace

from hangma_bot.kernel.serialization import observation_to_json
from hangma_bot.simulation import SimulationEngine

from ._helpers import make_rules, make_spec, simple_chooser


def _advance_once(engine, world, chooser):
    from hangma_bot.simulation import SimulationChoice

    frame = engine.frame(world)
    choices = tuple(
        SimulationChoice(d.window_key, chooser(d)) for d in frame.decisions
    )
    return engine.advance(world, frame.revision, choices)


def test_hidden_info_swap_does_not_change_observation():
    """同可见局面：替换他家暗牌与未来牌墙，玩家观察逐字节一致。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=13))
    chooser = simple_chooser(rules)
    world = _advance_once(engine, world, chooser)  # 庄家弃牌 → 碰窗口（三家同期观察）
    assert world.progression.window == "response_peng"
    decisions = engine.frame(world).decisions
    by_seat = {d.window_key.seat: d for d in decisions}
    baseline_2 = json.dumps(observation_to_json(by_seat[2].observation), sort_keys=True)
    baseline_3 = json.dumps(observation_to_json(by_seat[3].observation), sort_keys=True)
    baseline_1 = json.dumps(observation_to_json(by_seat[1].observation), sort_keys=True)
    # 替换座位 1 的暗牌（张数不变）与牌墙未来两枚（游标之后）——对 2/3 座都是隐藏信息。
    seats = list(world.progression.seats)
    seat1 = seats[1]
    swapped_hand = (seat1.hand[1],) + (seat1.hand[0],) + seat1.hand[2:] if len(seat1.hand) >= 2 else seat1.hand
    seats[1] = replace(seat1, hand=swapped_hand)
    progression = replace(world.progression, seats=tuple(seats))
    wall = list(world.wall)
    front = world.wall_front
    wall[front + 1], wall[front + 2] = wall[front + 2], wall[front + 1]
    modified = replace(world, progression=progression, wall=tuple(wall))
    modified_decisions = engine.frame(modified).decisions
    after_by_seat = {d.window_key.seat: d for d in modified_decisions}
    # 他座观察不因隐藏信息替换而改变。
    assert json.dumps(observation_to_json(after_by_seat[2].observation), sort_keys=True) == baseline_2
    assert json.dumps(observation_to_json(after_by_seat[3].observation), sort_keys=True) == baseline_3
    # 本人暗牌是可见信息：替换座位 1 自己的暗牌顺序会反映到座位 1 的观察。
    assert json.dumps(observation_to_json(after_by_seat[1].observation), sort_keys=True) != baseline_1


def test_public_change_does_change_observation():
    """对照：公开事实（他家牌河）变化必须反映到观察。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=13))
    chooser = simple_chooser(rules)
    world = _advance_once(engine, world, chooser)
    assert world.progression.window == "response_peng"
    baseline = [
        json.dumps(observation_to_json(d.observation), sort_keys=True)
        for d in engine.frame(world).decisions
    ]
    seats = list(world.progression.seats)
    seats[0] = replace(seats[0], discards=seats[0].discards + (seats[0].discards[0],))
    modified = replace(world, progression=replace(world.progression, seats=tuple(seats)))
    after = [
        json.dumps(observation_to_json(d.observation), sort_keys=True)
        for d in engine.frame(modified).decisions
    ]
    assert after != baseline