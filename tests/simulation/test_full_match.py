"""完整桌赛：Rounds 来自配置、终局积分、庄家轮转一致性、阻塞不计完成局。"""

from __future__ import annotations

from hangma_bot.hangma.progression import next_dealer
from hangma_bot.simulation import SimulationEngine

from ._helpers import make_rules, make_spec, simple_chooser, drive


def test_complete_match_produces_final_scores():
    """rounds_per_game=2：完整桌赛才有 final_scores，completed_hands=2。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    spec = make_spec(rules, rounds=2, seed=33, scores=(0, 0, 0, 0))
    world = drive(engine, engine.start(spec), simple_chooser(rules))
    frame = engine.frame(world)
    assert frame.final_scores is not None
    assert frame.blocked_reason is None
    assert frame.decisions == ()
    assert frame.completed_hands == 2
    assert len(world.round_records) == 2
    assert sum(world.scores) == 0  # 四家积分总和守恒


def test_round_records_consistency_and_dealer_rotation():
    """每局记录与庄家轮转一致：闲家胡换庄，流局/庄家胡连庄（v15 连庄口径）。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    spec = make_spec(rules, rounds=2, seed=55)
    world = drive(engine, engine.start(spec), simple_chooser(rules))
    assert frame_of(engine, world).final_scores is not None
    records = world.round_records
    expected_dealer = spec.initial_dealer
    for record in records:
        assert record.dealer_seat == expected_dealer
        assert record.scores_before is not None and record.scores_after is not None
        assert tuple(record.scores_after[i] - record.scores_before[i] for i in range(4)) == record.score_delta
        assert sum(record.score_delta) == 0
        expected_dealer = next_dealer(record.dealer_seat, record.winner_seat, record.is_draw)
    # 终局积分 = 起点积分 + 全部局增量。
    assert tuple(
        spec.initial_scores[i] + sum(record.score_delta[i] for record in records)
        for i in range(4)
    ) == world.scores


def test_single_round_import_world_completes_one_hand():
    """from_replay 单局世界 rounds=1：完成该局即终局（不伪造原桌赛其余局）。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    from ._helpers import build_full_world_row

    row = build_full_world_row(
        rules,
        hands13=[["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b"]] * 4,
        dealer_drawn="5w",
        wall=_small_wall(),
    )
    world = drive(engine, engine.from_replay(row), simple_chooser(rules))
    frame = engine.frame(world)
    assert frame.final_scores is not None
    assert frame.completed_hands == 1
    assert len(world.round_records) == 1


def _small_wall():
    """7 张可摸 + 20 保留的最小牌墙（供快速单局）。"""
    drawable = ["1t", "2t", "3t", "4t", "5t", "6t", "7t"]
    reserve = ["白"] * 4 + ["东"] * 4 + ["南"] * 4 + ["西"] * 4 + ["北"] * 4
    return drawable + reserve


def frame_of(engine, world):
    return engine.frame(world)