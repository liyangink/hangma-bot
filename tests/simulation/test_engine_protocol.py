"""advance 协议：原子拒绝、置换不变、分叉隔离、阻塞语义。"""

from __future__ import annotations

import json

import pytest

from hangma_bot.kernel.actions import Discard, Gang, GangKind, Hu, Pass, Peng, Tile
from hangma_bot.simulation import SimulationChoice, SimulationEngine

from ._helpers import make_rules, make_spec, simple_chooser, drive


def _first_draw_world():
    rules = make_rules()
    engine = SimulationEngine(rules)
    return rules, engine, engine.start(make_spec(rules, rounds=1, seed=5))


def test_old_revision_rejected_atomically():
    rules, engine, world = _first_draw_world()
    frame = engine.frame(world)
    chooser = simple_chooser(rules)
    choices = tuple(
        SimulationChoice(d.window_key, chooser(d)) for d in frame.decisions
    )
    next_world = engine.advance(world, frame.revision, choices)
    with pytest.raises(ValueError):
        engine.advance(next_world, frame.revision, choices)  # 旧 revision
    # 世界未被修改（不可变对象，失败前后一致）。
    assert engine.frame(next_world).revision == next_world.revision


def test_missing_duplicate_extra_choices_rejected():
    rules, engine, world = _first_draw_world()
    frame = engine.frame(world)
    decision = frame.decisions[0]
    chooser = simple_chooser(rules)
    action = chooser(decision)
    with pytest.raises(ValueError):
        engine.advance(world, frame.revision, ())  # 缺少
    duplicate = SimulationChoice(decision.window_key, action)
    with pytest.raises(ValueError):
        engine.advance(world, frame.revision, (duplicate, duplicate))  # 重复
    # 多余窗口：伪造一个不存在的窗口键（不同 phase）。
    from hangma_bot.kernel.actions import WindowKey, WindowPhase

    fake = SimulationChoice(
        WindowKey(
            game_id=decision.window_key.game_id,
            round_no=decision.window_key.round_no,
            trigger_seq=decision.window_key.trigger_seq,
            phase=WindowPhase.RESPONSE_PENG,
            seat=1,
        ),
        Pass(),
    )
    with pytest.raises(ValueError):
        engine.advance(world, frame.revision, (duplicate, fake))
    assert engine.frame(world).revision == 0  # 原世界未被推进


def test_illegal_action_rejected():
    rules, engine, world = _first_draw_world()
    frame = engine.frame(world)
    decision = frame.decisions[0]
    with pytest.raises(ValueError):
        engine.advance(
            world,
            frame.revision,
            (SimulationChoice(decision.window_key, Hu()),),  # 起手未成胡
        )
    with pytest.raises(ValueError):
        engine.advance(
            world,
            frame.revision,
            (SimulationChoice(decision.window_key, Gang(Tile("东"), GangKind.CONCEALED)),),
        )
    assert engine.frame(world).revision == 0


def test_choices_permutation_invariance():
    """同帧选择数组顺序不改变规则裁决（peng 窗口三响应者置换）。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    from ._helpers import build_full_world_row

    junk = ["1b", "4b", "7b", "2t", "5t", "8t", "3w", "6w", "9w", "东", "南", "西", "北"]
    row = build_full_world_row(
        rules,
        hands13=[
            ["5w"] + junk[:12],
            ["5w", "5w"] + junk[:11],
            junk[:],
            junk[1:] + ["5b"],
        ],
        dealer_drawn="5w",
        wall=["2b", "3b", "4b"] + ["发"] * 20,
        dealer=0,
    )
    world = engine.from_replay(row)
    frame = engine.frame(world)
    world = engine.advance(
        world, frame.revision,
        (SimulationChoice(frame.decisions[0].window_key, Discard(Tile("5w"))),),
    )
    assert world.progression.window == "response_peng"
    frame = engine.frame(world)
    assert len(frame.decisions) == 3
    by_seat = {d.window_key.seat: d for d in frame.decisions}
    claim = SimulationChoice(by_seat[1].window_key, Peng(Tile("5w")))
    pass_2 = SimulationChoice(by_seat[2].window_key, Pass())
    pass_3 = SimulationChoice(by_seat[3].window_key, Pass())
    world_a = engine.advance(world, frame.revision, (claim, pass_2, pass_3))
    world_b = engine.advance(world, frame.revision, (pass_3, claim, pass_2))
    assert [e.kind for e in world_a.events] == [e.kind for e in world_b.events]
    assert [e.seq for e in world_a.events] == [e.seq for e in world_b.events]
    assert world_a.progression.scores == world_b.progression.scores
    assert json.dumps(_seats(world_a)) == json.dumps(_seats(world_b))


def test_fork_does_not_pollute_parent():
    rules, engine, world = _first_draw_world()
    frame = engine.frame(world)
    decision = frame.decisions[0]
    analysis = rules.analyze(decision.observation)
    discards = [c.action for c in analysis.legal_candidates if type(c.action).__name__ == "Discard"]
    assert len(discards) >= 2
    branch_a = engine.advance(world, frame.revision, (SimulationChoice(decision.window_key, discards[0]),))
    branch_b = engine.advance(world, frame.revision, (SimulationChoice(decision.window_key, discards[1]),))
    assert branch_a != branch_b
    assert engine.frame(world).revision == 0  # 父世界未变
    assert world.progression.seats[0].discards == ()


def test_blocked_on_multi_claim():
    """两家同时碰同一弃牌 → blocked（无官方优先级依据，不默认先到先得）。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    # 座位 0 弃 X，座位 1/3 各持 X×2：构造 full_world 起点。
    from ._helpers import build_full_world_row

    row = build_full_world_row(
        rules,
        hands13=[
            ["5w", "5w", "5w", "6w", "7w", "1b", "2b", "3b", "4b", "5b", "6b", "7b", "8b"],
            ["5w", "5w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t", "东", "南"],
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b"],
            ["5w", "5w", "9b", "9b", "9b", "1t", "1t", "1t", "中", "中", "中", "发", "发"],
        ],
        dealer_drawn="5w",
        wall=["白", "白", "白", "白"] + ["1w"] * 4 + ["2w"] * 4 + ["3w"] * 4 + ["4w"] * 3 + ["5w"] * 0 + ["6w"] * 4 + ["7w"] * 3 + ["8w"] * 4 + ["9w"] * 3 + ["1b"] * 1 + ["2b"] * 1 + ["3b"] * 1 + ["4b"] * 0 + ["5b"] * 3 + ["6b"] * 3 + ["7b"] * 3 + ["8b"] * 3 + ["9b"] * 1 + ["东"] * 3 + ["南"] * 3 + ["西"] * 4 + ["北"] * 4 + ["中"] * 1 + ["发"] * 2,
        dealer=0,
    )
    world = engine.from_replay(row)
    # 庄家弃 5w（drawn 是 5w）→ 座位 1 与 3 都持 5w×2。
    frame = engine.frame(world)
    chooser = simple_chooser(rules)
    world = engine.advance(
        world, frame.revision,
        (SimulationChoice(frame.decisions[0].window_key, chooser(frame.decisions[0])),),
    )
    assert world.progression.window == "response_peng"
    frame = engine.frame(world)
    by_seat = {d.window_key.seat: d for d in frame.decisions}
    world = engine.advance(
        world,
        frame.revision,
        (
            SimulationChoice(by_seat[1].window_key, Peng(Tile("5w"))),
            SimulationChoice(by_seat[3].window_key, Peng(Tile("5w"))),
            SimulationChoice(by_seat[2].window_key, Pass()),
        ),
    )
    assert world.blocked_reason is not None
    assert "优先级" in world.blocked_reason or "先到先得" in world.blocked_reason
    frame = engine.frame(world)
    assert frame.decisions == ()
    assert frame.blocked_reason is not None
    assert frame.final_scores is None
    with pytest.raises(ValueError):
        engine.advance(world, world.revision, ())


def _seats(world):
    state = world.progression
    return [
        [
            [t.code for t in seat.hand],
            [t.code for t in seat.discards],
            [[t.code for t in meld.tiles] for meld in seat.melds],
        ]
        for seat in state.seats
    ]