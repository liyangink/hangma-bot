"""脚本化金例：吃碰杠、杠上补牌、抓打圈、禁杠边界、流局、胡牌结算。

通过 from_replay 导入手工构造的 full_world 起点（牌墙可指定），用
QueuedChooser 按窗口脚本化选择，逐项对拍推进语义与官方证据（v15/
2026-09-05 快照；细节口径见 handoffs/simulation.md 支持矩阵）。
"""

from __future__ import annotations

import pytest

from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile
from hangma_bot.simulation import SimulationChoice, SimulationEngine

from ._helpers import QueuedChooser, build_full_world_row, make_rules, simple_chooser


def _engine(world_row, rules=None):
    rules = rules or make_rules()
    engine = SimulationEngine(rules)
    return rules, engine, engine.from_replay(world_row)


def _drive_frames(engine, world, chooser, count):
    """推进恰好 count 帧（终局/阻塞提前返回）。"""
    for _ in range(count):
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            return world
        choices = tuple(
            SimulationChoice(d.window_key, chooser(d)) for d in frame.decisions
        )
        world = engine.advance(world, frame.revision, choices)
    return world


def _drive_to_end(engine, world, chooser, max_steps=400):
    steps = 0
    while True:
        frame = engine.frame(world)
        if frame.blocked_reason is not None or frame.final_scores is not None:
            return world
        choices = tuple(
            SimulationChoice(d.window_key, chooser(d)) for d in frame.decisions
        )
        world = engine.advance(world, frame.revision, choices)
        steps += 1
        if steps > max_steps:
            raise AssertionError("驱动超步数")


_JUNK = ["1b", "4b", "7b", "2t", "5t", "8t", "3w", "6w", "9w", "东", "南", "西", "北"]


def _reserve() -> list:
    return ["发"] * 20


def test_peng_flow_and_post_meld_hu_gate():
    """碰 → 碰后出牌窗口（无摸牌）；碰后禁止胡牌门禁（指南变更日志 v1）。"""
    rules = make_rules()
    row = build_full_world_row(
        rules,
        hands13=[
            ["5w"] + _JUNK[:12],
            ["5w", "5w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "北", "北"],
            _JUNK[:],
            _JUNK[1:] + ["5b"],
        ],
        dealer_drawn="5w",
        wall=["2b", "3b", "4b"] + _reserve()[:17] + ["6b", "7b", "8b"],
        dealer=0,
    )
    rules, engine, world = _engine(row, rules)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Discard(Tile("5w")))
    chooser.enqueue("response_peng", 1, Peng(Tile("5w")))
    world = _drive_frames(engine, world, chooser, 2)
    frame = engine.frame(world)
    decision = frame.decisions[0]
    assert decision.window_key.phase.value == "draw"
    assert decision.window_key.seat == 1
    assert decision.observation.drawn_tile is None
    # 碰后窗口手牌已成胡形（123w456w789w+碰5w+北北），门禁无 hu。
    analysis = rules.analyze(decision.observation)
    assert not any(c.action_key == "hu" for c in analysis.legal_candidates)
    with pytest.raises(ValueError):
        engine.advance(
            world, frame.revision, (SimulationChoice(decision.window_key, Hu()),),
        )
    world = engine.advance(
        world, frame.revision, (SimulationChoice(decision.window_key, Discard(Tile("1w"))),),
    )
    state = world.progression
    assert state.seats[1].melds[0].kind == "peng"
    assert [t.code for t in state.seats[1].melds[0].tiles] == ["5w", "5w", "5w"]
    assert len(state.seats[1].hand) == 10  # 13-2(碰)-1(弃)
    kinds = [e.kind for e in world.events]
    assert "peng" in kinds
    assert "pass" in kinds


def test_chi_flow_window_order():
    """碰窗口全过 → 吃窗口仅下家；吃事件携带三张组合。"""
    rules = make_rules()
    row = build_full_world_row(
        rules,
        hands13=[
            ["5w"] + _JUNK[:12],
            ["4w", "6w"] + _JUNK[:11],
            _JUNK[:],
            _JUNK[1:] + ["5b"],
        ],
        dealer_drawn="5w",
        wall=["2b", "3b", "4b"] + _reserve()[:17] + ["6b", "7b", "8b"],
        dealer=0,
    )
    rules, engine, world = _engine(row, rules)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Discard(Tile("5w")))
    chooser.enqueue("response_chi", 1, Chi((Tile("4w"), Tile("5w"), Tile("6w"))))
    world = _drive_frames(engine, world, chooser, 3)
    state = world.progression
    assert state.seats[1].melds[0].kind == "chi"
    chi_event = next(e for e in world.events if e.kind == "chi")
    assert dict(chi_event.data)["tiles"] == ("4w", "5w", "6w")
    public_chi = next(
        event for event in engine.frame(world).decisions[0].observation.public_history
        if event.kind == "chi"
    )
    assert public_chi.claimed_tile == Tile("5w")
    kinds = [e.kind for e in world.events]
    assert kinds.count("pass") == 3  # 碰窗口三家过；吃窗口直接吃
    assert "peng" not in kinds
    assert "chi" in kinds


def test_ming_gang_replacement_from_wall_back():
    """明杠：暗牌 3 张 + 被弃牌；杠上补牌从可摸区尾端取（world_schema 口径）。"""
    rules = make_rules()
    wall = ["2b", "3b", "4b", "5b"] + ["6b"] * 2 + _reserve()[:18]
    row = build_full_world_row(
        rules,
        hands13=[
            ["5w"] + _JUNK[:12],
            ["5w", "5w", "5w"] + _JUNK[:10],
            _JUNK[:],
            _JUNK[1:] + ["5b"],
        ],
        dealer_drawn="5w",
        wall=wall,
        dealer=0,
    )
    rules, engine, world = _engine(row, rules)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Discard(Tile("5w")))
    chooser.enqueue("response_peng", 1, Gang(Tile("5w"), GangKind.EXPOSED))
    world = _drive_frames(engine, world, chooser, 2)
    state = world.progression
    gang_event = next(e for e in world.events if e.kind == "gang")
    assert dict(gang_event.data)["kind"] == "ming"
    assert state.seats[1].melds[0].kind == "gang"
    assert state.seats[1].chain_count == 1  # 杠链 +1（指南 1.3）
    assert state.seats[1].drawn is not None
    assert state.seats[1].drawn.code == wall[len(wall) - 21]  # 可摸区尾端
    frame = engine.frame(world)
    assert frame.decisions[0].observation.rule_state.chain_count == 1


def test_concealed_gang_then_gang_win():
    """暗杠 → 杠上补牌 → 杠开自摸：fan=2、明细 [平胡, 杠开]。"""
    rules = make_rules()
    hand13 = ["1w", "1w", "1w", "2w", "3w", "4w", "7w", "8w", "9w", "5w", "6w", "东", "东"]
    wall = ["2b", "3b", "4b", "6b", "7w"] + _reserve()
    row = build_full_world_row(
        rules,
        hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="1w",
        wall=wall,
        dealer=0,
    )
    rules, engine, world = _engine(row, rules)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Gang(Tile("1w"), GangKind.CONCEALED))
    chooser.enqueue("draw", 0, Hu())
    world = _drive_to_end(engine, world, chooser)
    frame = engine.frame(world)
    assert frame.final_scores is not None
    record = world.round_records[0]
    assert record.is_draw is False
    assert record.winner_seat == 0
    assert record.fan == 2
    assert list(record.details) == ["平胡", "杠开"]
    assert record.score_delta == (48, -16, -16, -16)  # 庄家胡 底1×番2×8×3
    round_ended = next(e for e in world.events if e.kind == "round_ended")
    assert dict(round_ended.data)["fan"] == 2
    assert list(dict(round_ended.data)["detail"]) == ["平胡", "杠开"]


def test_added_gang_after_peng():
    """补杠：碰副露 + 暗牌第 4 张；副露转为 gang(bu)，链 +1，杠上补牌。"""
    rules = make_rules()
    wall = ["2b", "3b", "4b", "5w", "6b", "7b"] + _reserve()
    row = build_full_world_row(
        rules,
        hands13=[
            ["5w"] + _JUNK[:12],
            ["5w", "5w"] + _JUNK[:11],
            _JUNK[:],
            _JUNK[1:] + ["5b"],
        ],
        dealer_drawn="5w",
        wall=wall,
        dealer=0,
    )
    rules, engine, world = _engine(row, rules)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Discard(Tile("5w")))
    chooser.enqueue("response_peng", 1, Peng(Tile("5w")))
    chooser.enqueue("draw", 1, Discard(Tile("1b")))  # 碰后弃牌
    chooser.enqueue("draw", 1, Gang(Tile("5w"), GangKind.ADDED))  # 摸到 5w 补杠
    # 帧序：弃5w → 碰窗口 → 碰后弃牌 → 碰窗口×3过 → 吃过 → 2/3/0 依次摸打 → 座位1摸5w补杠。
    world = _drive_frames(engine, world, chooser, 15)
    state = world.progression
    assert state.seats[1].melds[0].kind == "gang"
    assert state.seats[1].melds[0].gang_kind == "bu"
    assert state.seats[1].chain_count == 1
    assert state.seats[1].drawn is not None
    assert state.seats[1].drawn.code == "7b"  # 杠上补牌 = 可摸区尾端
    gang_event = next(e for e in world.events if e.kind == "gang")
    assert dict(gang_event.data)["kind"] == "bu"


def test_wealth_discard_skips_response_windows():
    """v26：白板不可响应；随后非白仅给圈主开窗，即使其他家也有对子。"""
    rules = make_rules()
    wall = ["2b", "3b", "4b", "5b", "6b"] + _reserve()
    row = build_full_world_row(
        rules,
        hands13=[
            ["白"] + _JUNK[:12],
            _JUNK[:],
            ["2b", "2b"] + _JUNK[2:],
            _JUNK[2:] + ["6t", "7t"],
        ],
        dealer_drawn="白",
        wall=wall,
        dealer=0,
    )
    rules, engine, world = _engine(row, rules)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Discard(Tile("白")))
    world = _drive_frames(engine, world, chooser, 1)
    discard_event = world.events[0]
    assert discard_event.kind == "tile_discarded"
    assert dict(discard_event.data)["catch_play"] is True
    # 下一帧直接是座位 1 摸牌（弃白无响应窗口）。
    frame = engine.frame(world)
    assert frame.decisions[0].window_key.phase.value == "draw"
    assert frame.decisions[0].window_key.seat == 1
    # 座位 1 摸切 2b；座位 2 虽有对子，响应成员仍只有圈主 0。
    world = _drive_frames(engine, world, chooser, 1)
    frame = engine.frame(world)
    assert len(frame.decisions) == 1
    assert frame.decisions[0].window_key.phase.value == "response_peng"
    assert frame.decisions[0].window_key.seat == 0
    assert frame.decisions[0].observation.rule_state.catch_play is True
    world = _drive_frames(engine, world, chooser, 1)
    frame = engine.frame(world)
    assert frame.decisions[0].window_key.phase.value == "draw"
    assert frame.decisions[0].window_key.seat == 2


def test_catch_play_owner_can_hand_discard_and_end_circle():
    """全局抓打标记仍为真时，已证明圈主可手切；弃非白后该圈结束。"""
    rules = make_rules()
    wall = ["2b", "3b", "4b", "5b", "6b"] + _reserve()
    row = build_full_world_row(
        rules,
        hands13=[
            ["白"] + _JUNK[:12],
            _JUNK[:],
            _JUNK[1:] + ["5b"],
            _JUNK[2:] + ["6t", "7t"],
        ],
        dealer_drawn="白",
        wall=wall,
        dealer=0,
    )
    rules, engine, world = _engine(row, rules)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Discard(Tile("白")))
    # v26：圈内三个碰窗口，以及上家弃牌后的吃窗口，圈主均过牌后再摸。
    world = _drive_frames(engine, world, chooser, 8)
    frame = engine.frame(world)
    assert frame.decisions[0].window_key.seat == 0
    assert frame.decisions[0].window_key.phase.value == "draw"
    obs = frame.decisions[0].observation
    assert obs.rule_state.catch_play is True
    analysis = rules.analyze(obs)
    discard_keys = [
        c.action_key for c in analysis.legal_candidates if c.action_key.startswith("discard")
    ]
    assert "discard:1b" in discard_keys
    assert "discard:{0}".format(obs.drawn_tile.code) in discard_keys
    assert obs.drawn_tile != Tile("1b")
    world = engine.advance(
        world, frame.revision,
        (SimulationChoice(frame.decisions[0].window_key, Discard(Tile("1b"))),),
    )
    assert all(not d.observation.rule_state.catch_play for d in engine.frame(world).decisions)


def test_gang_wall_boundary():
    """最后 10 墩禁杠：剩余 ≤20 无杠候选；>20 允许（v15 1.1）。"""
    rules = make_rules()
    hand13 = ["1w", "1w", "1w"] + _JUNK[:10]
    row_empty = build_full_world_row(
        rules, hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="1w", wall=_reserve(), dealer=0,
    )
    rules, engine, world = _engine(row_empty, rules)
    frame = engine.frame(world)
    analysis = rules.analyze(frame.decisions[0].observation)
    assert not any(
        c.action_key == "gang:concealed:1w" for c in analysis.legal_candidates
    )
    with pytest.raises(ValueError):
        engine.advance(
            world, frame.revision,
            (SimulationChoice(frame.decisions[0].window_key, Gang(Tile("1w"), GangKind.CONCEALED)),),
        )
    row_one = build_full_world_row(
        rules, hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="1w", wall=["6b"] + _reserve(), dealer=0,
    )
    world = engine.from_replay(row_one)
    frame = engine.frame(world)
    analysis = rules.analyze(frame.decisions[0].observation)
    assert any(
        c.action_key == "gang:concealed:1w" for c in analysis.legal_candidates
    )
    world = engine.advance(
        world, frame.revision,
        (SimulationChoice(frame.decisions[0].window_key, Gang(Tile("1w"), GangKind.CONCEALED)),),
    )
    assert world.progression.seats[0].drawn is not None
    assert world.progression.seats[0].drawn.code == "6b"


def test_wall_exhaustion_draw():
    """摸完无人胡则流局：增量全零、round_ended(draw)（v15 1.1）。"""
    rules = make_rules()
    wall = ["2b", "3b"] + _reserve()
    row = build_full_world_row(
        rules,
        hands13=[_JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"], ["5w"] + _JUNK[:12]],
        dealer_drawn="9t",
        wall=wall,
        dealer=0,
    )
    rules, engine, world = _engine(row, rules)
    world = _drive_to_end(engine, world, simple_chooser(rules))
    frame = engine.frame(world)
    assert frame.final_scores == (0, 0, 0, 0)
    record = world.round_records[0]
    assert record.is_draw is True
    assert record.winner_seat is None
    assert record.score_delta == (0, 0, 0, 0)
    round_ended = next(e for e in world.events if e.kind == "round_ended")
    assert dict(round_ended.data)["draw"] is True


def test_plain_self_draw_settlement():
    """平胡自摸：fan=1、明细 [平胡]、庄家胡 +24/-8×3。"""
    rules = make_rules()
    hand13 = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "北"]
    row = build_full_world_row(
        rules,
        hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="北",
        wall=["2b", "3b"] + _reserve()[:18] + ["6b", "7b"],
        dealer=0,
    )
    rules, engine, world = _engine(row, rules)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Hu())
    world = _drive_to_end(engine, world, chooser)
    record = world.round_records[0]
    assert record.winner_seat == 0
    assert record.fan == 1
    assert list(record.details) == ["平胡"]
    assert record.score_delta == (24, -8, -8, -8)


def test_piao_chain_and_baotou_win():
    """爆头摸白弃胡打出（财飘）→ 圈内他人摸打 → 再摸任意牌胡：财飘+爆头。"""
    rules = make_rules()
    hand13 = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "白"]
    wall = ["2b", "3b", "4b", "北"] + _reserve()
    row = build_full_world_row(
        rules,
        hands13=[_JUNK[:], hand13, _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="白",
        wall=wall,
        dealer=1,
    )
    rules, engine, world = _engine(row, rules)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 1, Discard(Tile("白")))
    chooser.enqueue("draw", 1, Hu())
    world = _drive_to_end(engine, world, chooser)
    frame = engine.frame(world)
    assert frame.final_scores is not None
    record = world.round_records[0]
    assert record.winner_seat == 1
    assert record.fan == 4  # 平胡 1 × 财飘 2 × 爆头 2
    assert list(record.details) == ["平胡", "财飘", "爆头"]
    assert record.score_delta == (-32, 96, -32, -32)  # 庄家(座位1)胡：三家各付 底1×番4×8
    # 弃白本身不开响应窗口：弃白事件后第一个事件是座位 2 的摸牌。
    events = world.events
    wealth_index = next(
        i for i, e in enumerate(events)
        if e.kind == "tile_discarded" and e.tile.code == "白"
    )
    assert events[wealth_index + 1].kind == "tile_drawn"
    assert events[wealth_index + 1].seat == 2


def test_youcai_bi_kao_gate():
    """有财必拷响：手留财神非爆头非杠开 → 无胡候选（宁漏胡不 409）。"""
    hand13 = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "东", "东", "东", "白", "北"]
    base = dict(
        hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="9w",
        wall=["2b", "3b"] + _reserve()[:18] + ["6b", "7b"],
        dealer=0,
    )
    row_youcai = build_full_world_row(make_rules(youcai=True), **base)
    row_plain = build_full_world_row(make_rules(youcai=False), **base)
    engine_youcai = SimulationEngine(make_rules(youcai=True))
    engine_plain = SimulationEngine(make_rules(youcai=False))
    world_youcai = engine_youcai.from_replay(row_youcai)
    world_plain = engine_plain.from_replay(row_plain)
    frame = engine_youcai.frame(world_youcai)
    analysis = engine_youcai.rules.analyze(frame.decisions[0].observation)
    assert not any(c.action_key == "hu" for c in analysis.legal_candidates)
    with pytest.raises(ValueError):
        engine_youcai.advance(
            world_youcai, frame.revision,
            (SimulationChoice(frame.decisions[0].window_key, Hu()),),
        )
    frame_plain = engine_plain.frame(world_plain)
    analysis_plain = engine_plain.rules.analyze(frame_plain.decisions[0].observation)
    assert any(c.action_key == "hu" for c in analysis_plain.legal_candidates)
