"""抓打圈换主、退出与开窗：通过公开模拟接口核验外部可观察行为。

依据为 2026-09-08 用户确认的被迫弃白换主，以及已核验的圈主可手切
官方轨迹，以及 v26 修复后的圈主响应规则（v27 全文 §1.1/§2.4）。
正常响应窗口显式过牌；活跃圈仅圈主响应，不沿用 v24 跳过全部窗口的缺陷。
"""

from collections import Counter

import pytest

from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Discard, Pass, Tile
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine


@pytest.fixture
def game():
    """构造 136 张守恒牌山；A 先弃白，B 随即摸白，其后各家摸自然牌。"""

    rules = HangmaRules(RuleConfig("catch-play-lifetime", 1, True))
    engine = SimulationEngine(rules)
    spec = MatchSpec(
        match_id="catch-play-lifetime",
        scenario_id="catch-play-lifetime",
        config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
        seed=0,
        initial_dealer=0,
        initial_scores=(0, 0, 0, 0),
    )
    row = engine.export_hand(engine.start(spec), 1)
    hand_a = "1w 2w 3w 4w 5w 6w 7w 8w 9w 东 南 西 北".split()
    wall_prefix = ["白", "东", "9b", "5b", "6b", "7b"]
    available = Counter({code: 4 for code in CANONICAL_TILE_ORDER})
    available.subtract(hand_a + ["白"] + wall_prefix)
    assert min(available.values()) >= 0
    rest = list(available.elements())
    hands = [hand_a, rest[:13], rest[13:26], rest[26:39]]
    wall = wall_prefix + rest[39:]
    assert Counter(sum(hands, []) + ["白"] + wall) == Counter(
        {code: 4 for code in CANONICAL_TILE_ORDER}
    )
    row["initial"]["world_payload"].update(
        hands=hands, dealer_drawn_tile="白", wall=wall,
        wall_front=0, wall_back=len(wall) - 20,
    )
    row["initial"].update(hands=[hand_a + ["白"]] + hands[1:], drawn_tile="白", wall=wall)
    return rules, engine, engine.from_replay(row)


def _next_draw(engine, world):
    """仅跳过可能存在的响应窗口；不对官方是否开放响应窗口作额外假设。"""

    for _ in range(3):
        frame = engine.frame(world)
        assert frame.blocked_reason is None and frame.final_scores is None
        if len(frame.decisions) == 1 and frame.decisions[0].observation.phase == "draw":
            return world, frame.decisions[0]
        assert frame.decisions
        assert all(d.observation.phase in ("response_peng", "response_chi") for d in frame.decisions)
        world = engine.advance(
            world, frame.revision,
            tuple(SimulationChoice(d.window_key, Pass()) for d in frame.decisions),
        )
    raise AssertionError("过完碰、吃窗口后应到下一家摸牌")


def _discard(engine, world, seat, code):
    world, decision = _next_draw(engine, world)
    assert decision.observation.seat == seat
    return engine.advance(
        world, engine.frame(world).revision,
        (SimulationChoice(decision.window_key, Discard(Tile(code))),),
    )


def _discard_keys(rules, observation):
    return {
        candidate.action_key
        for candidate in rules.analyze(observation).legal_candidates
        if isinstance(candidate.action, Discard)
    }


def _after_owner_transfer(engine, world):
    world = _discard(engine, world, 0, "白")
    # B 的白来自刚摸牌；不依赖此时是否爆头或是否有财飘收益。
    return _discard(engine, world, 1, "白")


def _before_old_owner_discards(engine, world):
    world = _after_owner_transfer(engine, world)
    world = _discard(engine, world, 2, "东")
    world = _discard(engine, world, 3, "9b")
    return _next_draw(engine, world)


def test_white_draw_by_non_owner_is_forced_before_it_transfers_ownership(game):
    rules, engine, world = game
    world = _discard(engine, world, 0, "白")
    _, decision = _next_draw(engine, world)
    observation = decision.observation

    assert observation.seat == 1 and observation.drawn_tile == Tile("白")
    assert _discard_keys(rules, observation) == {"discard:白"}


def test_other_players_stay_in_the_new_owners_circle(game):
    rules, engine, world = game
    world = _after_owner_transfer(engine, world)
    _, decision = _next_draw(engine, world)

    assert decision.observation.seat == 2
    assert _discard_keys(rules, decision.observation) == {"discard:东"}


def test_old_owner_becomes_restricted_and_cannot_close_the_new_circle(game):
    rules, engine, world = game
    world, old_owner = _before_old_owner_discards(engine, world)

    assert old_owner.observation.seat == 0
    assert _discard_keys(rules, old_owner.observation) == {"discard:5b"}
    world = _discard(engine, world, 0, "5b")
    _, new_owner = _next_draw(engine, world)
    # god.catch_play 表示全局圈仍存在；不能在 A 的非白弃牌处把 B 的圈结束。
    assert new_owner.observation.seat == 1
    assert new_owner.observation.rule_state.catch_play is True


def test_new_owner_can_hand_discard_then_end_its_own_circle(game):
    rules, engine, world = game
    world, _ = _before_old_owner_discards(engine, world)
    world = _discard(engine, world, 0, "5b")
    world, new_owner = _next_draw(engine, world)
    observation = new_owner.observation
    assert observation.seat == 1 and observation.drawn_tile == Tile("6b")
    hand_discard = observation.my_hand[0]
    assert hand_discard != observation.drawn_tile
    assert rules.validate(observation, Discard(hand_discard)).legal

    world = _discard(engine, world, 1, hand_discard.code)
    _, next_player = _next_draw(engine, world)
    assert next_player.observation.seat == 2
    assert next_player.observation.rule_state.catch_play is False
    assert len(_discard_keys(rules, next_player.observation)) > 1


def test_exported_discard_flag_reports_circle_after_the_action(game):
    """官方 a85 b8r6 等四轨迹：旧圈主非白仍 true，新圈主非白才 false。"""

    _, engine, world = game
    world, _ = _before_old_owner_discards(engine, world)
    world = _discard(engine, world, 0, "5b")
    # 本例让新圈主也选择摸切，独立检查圈退出，不与“圈主可手切”红灯重叠。
    world = _discard(engine, world, 1, "6b")
    discards = [
        event for event in engine.export_hand(world, 1)["events"]
        if event["type"] == "tile_discarded"
    ]

    assert [(event["seat"], event["tile"]) for event in discards] == [
        (0, "白"), (1, "白"), (2, "东"), (3, "9b"), (0, "5b"), (1, "6b"),
    ]
    assert [event["data"]["catch_play"] for event in discards] == [
        True, True, True, True, True, False,
    ]


def test_public_discard_history_preserves_circle_flag_after_owner_transfer(game):
    """规则收到的公开弃牌保留事件标记，不能在投影时把已知 true 丢成未知。"""

    _, engine, world = game
    world, _ = _before_old_owner_discards(engine, world)
    world = _discard(engine, world, 0, "5b")
    _, new_owner = _next_draw(engine, world)
    last_discard = next(
        event for event in reversed(new_owner.observation.public_history)
        if event.kind == "tile_discarded"
    )

    assert last_discard.seat == 0 and last_discard.tiles == (Tile("5b"),)
    assert last_discard.catch_play is True


def test_public_history_keeps_other_draw_sequences_without_revealing_tiles(game):
    """他家摸牌事件保持序号连续，牌值仍只对摸牌者可见。"""

    _, engine, world = game
    world, _ = _before_old_owner_discards(engine, world)
    world = _discard(engine, world, 0, "5b")
    _, new_owner = _next_draw(engine, world)
    observation = new_owner.observation
    history = observation.public_history
    other_draws = [
        event for event in history
        if event.kind == "tile_drawn" and event.seat != observation.seat
    ]

    assert other_draws
    assert all(event.tiles == () for event in other_draws)
    assert tuple(event.seq for event in history) == tuple(range(1, observation.consumed_seq + 1))
    assert history[-1].kind == "tile_drawn"
    assert history[-1].seat == observation.seat and history[-1].tiles == (Tile("6b"),)


def test_active_circle_opens_peng_only_for_current_owner(game):
    """v26：他家普通弃牌保留圈，仅圈主收到碰窗口；非下家圈主没有吃窗。"""
    _, engine, world = game
    world = _after_owner_transfer(engine, world)
    world = _discard(engine, world, 2, "东")
    frame = engine.frame(world)
    assert len(frame.decisions) == 1
    observation = frame.decisions[0].observation
    assert observation.phase == "response_peng" and observation.seat == 1
    assert observation.responding_seats == (1,)
    assert observation.rule_state.catch_play is True
    world = engine.advance(world, frame.revision, (SimulationChoice(frame.decisions[0].window_key, Pass()),))
    following = engine.frame(world).decisions[0].observation
    assert following.phase == "draw" and following.seat == 3


def test_old_owner_discard_only_opens_responses_for_new_owner(game):
    _, engine, world = game
    world, _ = _before_old_owner_discards(engine, world)
    world = _discard(engine, world, 0, "5b")
    frame = engine.frame(world)
    assert len(frame.decisions) == 1
    assert frame.decisions[0].observation.phase == "response_peng"
    assert frame.decisions[0].observation.seat == 1
    assert frame.decisions[0].observation.rule_state.catch_play is True
    world = engine.advance(world, frame.revision, (SimulationChoice(frame.decisions[0].window_key, Pass()),))
    frame = engine.frame(world)
    assert len(frame.decisions) == 1
    assert frame.decisions[0].observation.phase == "response_chi"
    assert frame.decisions[0].observation.seat == 1


def test_owner_nonwhite_end_restores_normal_response_windows(game):
    _, engine, world = game
    world, _ = _before_old_owner_discards(engine, world)
    world = _discard(engine, world, 0, "5b")
    world = _discard(engine, world, 1, "6b")
    frame = engine.frame(world)
    assert len(frame.decisions) == 3
    assert all(d.observation.phase == "response_peng" for d in frame.decisions)
    assert all(not d.observation.rule_state.catch_play for d in frame.decisions)
