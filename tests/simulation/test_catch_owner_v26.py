"""v26 圈主响应修复：真实守恒牌形，经公开模拟接口检验财飘、鸣牌和杠。

依据：官方 v27 全文 §1.1、§1.3、§2.4（2026-09-09 核验）。
保留弃前爆头才计飘的条件；不把普通打白转成财飘，也不修改线上状态。
"""

from collections import Counter

import pytest

from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Chi, Discard, Gang, GangKind, Pass, Peng, Tile
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine
from tests.simulation._helpers import total_tiles


def _game(owner_hand, front, *, other_hands=None, replacement="北"):
    """公开 full_world 导入：保留每种牌四张，指定前摸顺序与第一张杠补牌。"""
    rules = HangmaRules(RuleConfig("catch-owner-v26", 1, False))
    engine = SimulationEngine(rules)
    spec = MatchSpec(
        match_id="catch-owner-v26", scenario_id="catch-owner-v26", seed=0,
        config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
        initial_dealer=0, initial_scores=(0, 0, 0, 0),
    )
    row = engine.export_hand(engine.start(spec), 1)
    prepared = {0: owner_hand.split(), **(other_hands or {})}
    counts = Counter({code: 4 for code in CANONICAL_TILE_ORDER})
    counts.subtract(sum(prepared.values(), []) + ["白", replacement] + front)
    assert min(counts.values()) >= 0
    for seat in range(4):
        if seat not in prepared:
            prepared[seat] = list(counts.elements())[:13]
            counts.subtract(prepared[seat])
    hands = [prepared[seat] for seat in range(4)]
    assert all(len(hand) == 13 for hand in hands)
    rest = list(counts.elements())
    wall = front + rest[:-20] + [replacement] + rest[-20:]
    assert Counter(sum(hands, []) + ["白"] + wall) == Counter({code: 4 for code in CANONICAL_TILE_ORDER})
    row["initial"]["world_payload"].update(
        hands=hands, dealer_drawn_tile="白", wall=wall,
        wall_front=0, wall_back=len(wall) - 20,
    )
    row["initial"].update(hands=[hands[0] + ["白"]] + hands[1:], drawn_tile="白", wall=wall)
    return rules, engine, engine.from_replay(row)


def _one(engine, world):
    frame = engine.frame(world)
    assert frame.blocked_reason is None and len(frame.decisions) == 1
    return frame, frame.decisions[0]


def _play(engine, world, seat, action, phase):
    frame, decision = _one(engine, world)
    assert (decision.observation.seat, decision.observation.phase) == (seat, phase)
    advanced = engine.advance(world, frame.revision, (SimulationChoice(decision.window_key, action),))
    assert total_tiles(advanced) == 136
    return advanced


def _discard(engine, world, seat, code):
    for _ in range(3):
        frame = engine.frame(world)
        if len(frame.decisions) == 1 and frame.decisions[0].observation.phase == "draw":
            return _play(engine, world, seat, Discard(Tile(code)), "draw")
        assert all(decision.observation.phase in ("response_peng", "response_chi") for decision in frame.decisions)
        world = engine.advance(world, frame.revision, tuple(SimulationChoice(d.window_key, Pass()) for d in frame.decisions))
    raise AssertionError("碰、吃全过后必须摸牌")


def _after_piao_and_claim(claim):
    """三面子 + 自然对子/顺子搭子 + 两白：先飘，再鸣牌，仍有白可续飘。"""
    if claim == "peng":
        rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 白 白", ["东", "5b"])
    else:
        rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 7t 8t 白 白", ["1b", "2b", "9t", "5b"])
    _, initial = _one(engine, world)
    assert initial.observation.rule_state.baotou is True
    world = _discard(engine, world, 0, "白")
    if claim == "peng":
        world = _discard(engine, world, 1, "东")
        world = _play(engine, world, 0, Peng(Tile("东")), "response_peng")
    else:
        for seat, code in ((1, "1b"), (2, "2b"), (3, "9t")):
            world = _discard(engine, world, seat, code)
        world = _play(engine, world, 0, Pass(), "response_peng")
        world = _play(engine, world, 0, Chi((Tile("7t"), Tile("8t"), Tile("9t"))), "response_chi")
    return rules, engine, world


@pytest.mark.parametrize("claim", ["peng", "chi"])
def test_owner_claim_preserves_piao_chain_and_white_restarts_it(claim):
    rules, engine, world = _after_piao_and_claim(claim)
    _, decision = _one(engine, world)
    observation = decision.observation
    assert observation.drawn_tile is None
    assert observation.rule_state.catch_play_owner_seat == 0
    assert observation.rule_state.baotou is True
    assert (observation.rule_state.chain_count, observation.chain_piao) == (1, 1)
    assert rules.validate(observation, Discard(Tile("白"))).legal
    assert "hu" not in {candidate.action_key for candidate in rules.analyze(observation).legal_candidates}

    world = _discard(engine, world, 0, "白")
    # 次家摸打后再次开放圈主碰窗，直接读取圈主依法可见的链与听牌后态。
    world = _discard(engine, world, 1, "5b")
    _, owner = _one(engine, world)
    assert owner.observation.seat == 0
    assert owner.observation.rule_state.baotou is True
    assert (owner.observation.rule_state.chain_count, owner.observation.chain_piao) == (2, 2)
    whites = [event for event in owner.observation.public_history if event.kind == "tile_discarded" and event.tiles == (Tile("白"),)]
    assert len(whites) == 2 and all(event.seat == 0 and event.catch_play for event in whites)
    assert whites[1].seq > whites[0].seq


def test_owner_claim_then_nonwhite_clears_chain_and_restores_all_responses():
    _, engine, world = _after_piao_and_claim("peng")
    world = _discard(engine, world, 0, "1w")
    frame = engine.frame(world)
    assert {d.observation.seat for d in frame.decisions} == {1, 2, 3}
    assert all(d.observation.phase == "response_peng" for d in frame.decisions)
    assert all(not d.observation.rule_state.catch_play and d.observation.rule_state.catch_play_owner_seat is None for d in frame.decisions)
    # 以圈主下一次实际响应观察核验其旧链已清除。
    world = _discard(engine, world, 1, "5b")
    owner = next(d.observation for d in engine.frame(world).decisions if d.observation.seat == 0)
    assert (owner.rule_state.chain_count, owner.chain_piao) == (0, 0)


@pytest.mark.parametrize("kind", [GangKind.EXPOSED, GangKind.ADDED])
def test_owner_gang_replacement_preserves_circle_and_adds_to_piao_chain(kind):
    rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 东 白", ["东", "3b"], replacement="5b")
    world = _discard(engine, world, 0, "白")
    world = _discard(engine, world, 1, "东")
    if kind is GangKind.ADDED:
        world = _play(engine, world, 0, Peng(Tile("东")), "response_peng")
        world = _play(engine, world, 0, Gang(Tile("东"), kind), "draw")
    else:
        world = _play(engine, world, 0, Gang(Tile("东"), kind), "response_peng")
    _, owner = _one(engine, world)
    observation = owner.observation
    assert observation.seat == 0 and observation.drawn_tile == Tile("5b")
    assert observation.rule_state.catch_play_owner_seat == 0
    assert observation.rule_state.baotou is True
    assert (observation.rule_state.chain_count, observation.chain_piao) == (2, 1)
    assert rules.validate(observation, Discard(Tile("1w"))).legal
    world = _discard(engine, world, 0, "5b")
    assert all(not d.observation.rule_state.catch_play for d in engine.frame(world).decisions)


def test_nonowner_concealed_gang_preserves_owner_and_forced_replacement_discard():
    other = "1t 2t 3t 4t 5t 6t 7t 8t 9t 东 东 东 南".split()
    rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 白", ["东", "5b"], other_hands={1: other}, replacement="6b")
    world = _discard(engine, world, 0, "白")
    _, decision = _one(engine, world)
    assert rules.validate(decision.observation, Gang(Tile("东"), GangKind.CONCEALED)).legal
    world = _play(engine, world, 1, Gang(Tile("东"), GangKind.CONCEALED), "draw")
    _, decision = _one(engine, world)
    observation = decision.observation
    assert observation.drawn_tile == Tile("6b") and observation.rule_state.catch_play_owner_seat == 0
    assert (observation.rule_state.chain_count, observation.chain_piao) == (1, 0)
    keys = {c.action_key for c in rules.analyze(observation).legal_candidates if isinstance(c.action, Discard)}
    assert keys == {"discard:6b"}
    world = _discard(engine, world, 1, "6b")
    _, owner = _one(engine, world)
    assert owner.observation.seat == 0 and owner.observation.phase == "response_peng"
    assert (owner.observation.rule_state.chain_count, owner.observation.chain_piao) == (1, 1)
