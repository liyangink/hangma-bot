"""庄家直抽牌按实际座位导出；仅通过模拟器及规则模块公开接口回归。"""

from collections import Counter

import pytest

from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Discard, Hu, Pass
from hangma_bot.simulation import SimulationChoice, SimulationEngine

from ._helpers import drive, make_rules, make_spec


def _assert_initial_tiles(row):
    """检查四座位起手、直抽归属和整副牌守恒，不读取模拟内部字段。"""
    initial = row["initial"]
    dealer = initial["dealer_seat"]
    assert [len(hand) for hand in initial["hands"]] == [
        14 if seat == dealer else 13 for seat in range(4)
    ]
    assert initial["hands"][dealer][-1] == initial["drawn_tile"]
    assert Counter(tile for hand in initial["hands"] for tile in hand) + Counter(
        initial["wall"]
    ) == Counter({code: 4 for code in CANONICAL_TILE_ORDER})


def _chooser(rules):
    """合法胡优先，否则走紧急动作；合法性沿用公开规则验证接口。"""
    def choose(decision):
        if rules.validate(decision.observation, Hu()).legal:
            return Hu()
        candidate = rules.emergency_action(decision.observation)
        assert candidate is not None
        return candidate.action
    return choose


@pytest.mark.parametrize("dealer", range(4))
def test_incomplete_export_preserves_actual_dealer_and_observation(dealer):
    """四种首庄的未完成导出均能再导入，恢复相同玩家观察与起手牌。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=202609071003, dealer=dealer))
    before = engine.frame(world)
    row = engine.export_hand(world, 1)
    _assert_initial_tiles(row)
    restored = engine.from_replay(row)
    assert engine.frame(restored).decisions == before.decisions
    assert engine.export_hand(restored, 1) == row
    assert engine.frame(world) == before


@pytest.mark.parametrize("dealer", range(4))
def test_completed_export_preserves_dealer_and_reproduces_events(dealer):
    """已完成记录也必须按实际庄家保存；再导入后事件及结算逐项一致。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=202609071003, dealer=dealer))
    initial = engine.frame(world).decisions
    world = drive(engine, world, _chooser(rules))
    row = engine.export_hand(world, 1)
    _assert_initial_tiles(row)
    restored = engine.from_replay(row)
    assert engine.frame(restored).decisions == initial
    restored = drive(engine, restored, _chooser(rules))
    assert engine.export_hand(restored, 1) == row


def test_cross_hand_exports_after_dealer_retention_and_rotation():
    """完整桌赛含连庄与换庄；结束后导出每个旧单局并独立重演结算。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=3, seed=66, dealer=1))
    def chooser(decision):
        """消费规则牌效选择弃牌，使固定桌赛覆盖胡牌换庄；不重写牌型算法。"""
        if decision.observation.round_no == 1:
            # 首单局固定只用紧急动作打到流局，确保覆盖连庄路径。
            return rules.emergency_action(decision.observation).action
        candidates = rules.analyze(decision.observation).legal_candidates
        for candidate in candidates:
            if isinstance(candidate.action, (Hu, Pass)):
                return candidate.action
        discards = [c for c in candidates if isinstance(c.action, Discard)]
        return min(discards, key=lambda c: (
            c.facts.shanten_after,
            -sum(tile.remaining_estimate for tile in c.facts.useful_tiles),
            c.action_key,
        )).action
    starts = {}
    for _ in range(8000):
        frame = engine.frame(world)
        assert frame.blocked_reason is None
        if frame.final_scores is not None:
            break
        round_no = frame.decisions[0].observation.round_no
        starts.setdefault(round_no, frame.decisions[0].observation.dealer_seat)
        world = engine.advance(world, frame.revision, tuple(
            SimulationChoice(d.window_key, chooser(d)) for d in frame.decisions
        ))
    else:
        pytest.fail("完整桌赛未结束")
    dealers = list(starts.values())
    assert len(dealers) == 3
    assert any(a == b for a, b in zip(dealers, dealers[1:]))
    assert any(a != b for a, b in zip(dealers, dealers[1:]))
    for round_no, dealer in starts.items():
        row = engine.export_hand(world, round_no)
        assert row["initial"]["dealer_seat"] == dealer
        _assert_initial_tiles(row)
        restored = drive(engine, engine.from_replay(row), chooser)
        replayed = engine.export_hand(restored, round_no)
        assert replayed["scores_after"] == row["scores_after"]
        assert replayed["score_delta"] == row["score_delta"]
        # 导入的单局独立结束时额外产生 game_ended，不改变单局已发生事件。
        assert [e for e in replayed["events"] if e["type"] != "game_ended"] == [
            e for e in row["events"] if e["type"] != "game_ended"
        ]
