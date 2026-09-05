"""修订轮回归：round_ended 增量语义、事件 data 列表化、导入局导出上限、
杠+流局牌墙游标、核对器真实局号/庄家（挑战者复现缺陷 1/2/3/8/9）。"""

from __future__ import annotations

import copy

import pytest

from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Hu, Tile
from hangma_bot.offline.replay_check import check_hand
from hangma_bot.simulation import SimulationChoice, SimulationEngine

from ._helpers import QueuedChooser, build_full_world_row, make_rules, simple_chooser, drive

_JUNK = ["1b", "4b", "7b", "2t", "5t", "8t", "3w", "6w", "9w", "东", "南", "西", "北"]


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


def test_round_ended_event_carries_delta_not_cumulative():
    """缺陷 1：round_ended.data.scores 是四家增量；累计积分只在 game_ended。"""
    rules = make_rules()
    hand13 = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "北"]
    row = build_full_world_row(
        rules,
        hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="北",
        wall=["2b", "3b"] + ["发"] * 20,
        dealer=0,
        scores_before=(10, 20, 30, 40),
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Hu())
    world = _drive_to_end(engine, world, chooser)
    round_ended = next(e for e in world.events if e.kind == "round_ended")
    game_ended = next(e for e in world.events if e.kind == "game_ended")
    assert dict(round_ended.data)["scores"] == (24, -8, -8, -8)  # 增量
    assert dict(game_ended.data)["final_scores"] == (34, 12, 22, 32)  # 累计
    # 非零起点积分下导出 → 进程内核对（含 JSON 落盘口径一致的回归）。
    exported = engine.export_hand(world, 1)
    exported_event = next(e for e in exported["events"] if e["type"] == "round_ended")
    assert exported_event["data"]["scores"] == [24, -8, -8, -8]
    assert exported["scores_before"] == [10, 20, 30, 40]
    assert exported["scores_after"] == [34, 12, 22, 32]
    outcome = check_hand(exported, rules)
    assert outcome["status"] == "passed", outcome


def test_check_hand_in_memory_chi_row_passes():
    """缺陷 2：事件 data 值内存即 list；吃行进程内核对（不经 JSON 往返）passed。"""
    rules = make_rules()
    wall = ["2b", "3b", "4b"] + ["发"] * 17 + ["6b", "7b", "8b"]
    row = build_full_world_row(
        rules,
        hands13=[
            ["5w"] + _JUNK[:12],
            ["4w", "6w"] + _JUNK[:11],
            _JUNK[:],
            _JUNK[1:] + ["5b"],
        ],
        dealer_drawn="5w",
        wall=wall,
        dealer=0,
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Discard(Tile("5w")))
    chooser.enqueue("response_chi", 1, Chi((Tile("4w"), Tile("5w"), Tile("6w"))))
    world = _drive_to_end(engine, world, chooser)
    exported = engine.export_hand(world, 1)
    chi_event = next(e for e in exported["events"] if e["type"] == "chi")
    assert isinstance(chi_event["data"]["tiles"], list)
    outcome = check_hand(exported, rules)  # 内存直查，无 JSON 序列化历史
    assert outcome["status"] == "passed", outcome


def test_check_hand_in_memory_gang_draw_row_passes():
    """缺陷 9：暗杠 + 流局的手经导出后进程内核对 passed（补牌不占用 front 游标）。"""
    rules = make_rules()
    hand13 = ["1w", "1w", "1w"] + _JUNK[:10]
    wall = ["2b", "3b", "4b"] + ["发"] * 20
    row = build_full_world_row(
        rules, hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="1w", wall=wall, dealer=0,
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Gang(Tile("1w"), GangKind.CONCEALED))
    world = _drive_to_end(engine, world, chooser)
    record = world.round_records[0]
    assert record.is_draw is True
    # 补牌只移动补牌端游标：可摸区无滞留、无保留区被摸。
    assert world.wall_front == world.wall_back
    drawn = [
        e.tile.code for e in world.events if e.kind == "tile_drawn"
    ]
    assert sorted(drawn) == ["2b", "3b", "4b"]  # 可摸区 3 张全部消耗
    exported = engine.export_hand(world, 1)
    outcome = check_hand(exported, rules)
    assert outcome["status"] == "passed", outcome


def test_check_hand_win_after_gang_row_passes():
    """杠开胡的行进程内核对 passed（事件 data 列表化覆盖 gang/detail/scores）。"""
    rules = make_rules()
    hand13 = ["1w", "1w", "1w", "2w", "3w", "4w", "7w", "8w", "9w", "5w", "6w", "东", "东"]
    wall = ["2b", "3b", "4b", "6b", "7w"] + ["发"] * 20
    row = build_full_world_row(
        rules,
        hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="1w", wall=wall, dealer=0,
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Gang(Tile("1w"), GangKind.CONCEALED))
    chooser.enqueue("draw", 0, Hu())
    world = _drive_to_end(engine, world, chooser)
    exported = engine.export_hand(world, 1)
    gang_event = next(e for e in exported["events"] if e["type"] == "gang")
    assert gang_event["data"]["kind"] == "an"
    outcome = check_hand(exported, rules)
    assert outcome["status"] == "passed", outcome


def test_export_imported_round_gt_rounds_per_game():
    """缺陷 3：from_replay 单局世界 round_no>1 可导出并可反事实另存。"""
    rules = make_rules()
    wall = ["2b", "3b"] + ["发"] * 20
    row = build_full_world_row(
        rules,
        hands13=[_JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"], ["5w"] + _JUNK[:12]],
        dealer_drawn="9t",
        wall=wall,
        dealer=0,
        round_no=5,
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    assert world.round_no == 5
    exported = engine.export_hand(world, 5)  # 修复前：round_no 5 超出 1..1
    assert exported["round_no"] == 5
    assert exported["winner_seat"] is None  # 进行中结果为空
    imported = engine.from_replay(exported)
    assert imported.round_no == 5
    # 反事实另存（契约 §6 parent_hand_id 流程）对导入单局同样可用。
    forked = engine.export_hand(world, 5, match_id="m-fork")
    assert forked["parent_hand_id"] == exported["hand_id"]
    assert engine.from_replay(forked).round_no == 5
    # 无记录的旧局号必须拒绝。
    with pytest.raises(ValueError):
        engine.export_hand(world, 1)
    with pytest.raises(ValueError):
        engine.export_hand(world, 9)


def test_check_hand_round_no_missing_is_not_checked():
    """缺陷 8 口径：缺 round_no 的行按 not_checked 处理（观察投影回退 1 并记录）。"""
    rules = make_rules()
    hand13 = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "北"]
    row = build_full_world_row(
        rules,
        hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="北",
        wall=["2b", "3b"] + ["发"] * 20,
        dealer=0,
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Hu())
    world = _drive_to_end(engine, world, chooser)
    exported = engine.export_hand(world, 1)
    del exported["round_no"]
    outcome = check_hand(exported, rules)
    assert outcome["status"] == "not_checked"
    codes = [issue["code"] for issue in outcome["issues"]]
    assert "not_checked.round_no_missing" in codes
    assert not any(code.startswith("conflict") for code in codes)


def test_export_completed_imported_world_rejects_old_round_no():
    """缺陷 A：已完成 from_replay 世界导出旧局号必须拒绝（防身份错标）。"""
    rules = make_rules()
    hand13 = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "北"]
    row = build_full_world_row(
        rules,
        hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="北",
        wall=["2b", "3b"] + ["发"] * 20,
        dealer=0,
        round_no=5,
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Hu())
    world = _drive_to_end(engine, world, chooser)
    assert engine.frame(world).final_scores is not None
    assert len(world.round_records) == 1
    # 旧局号（记录下标取到第 5 局记录但局号不匹配）必须拒绝。修复前会静默
    # 导出第 5 局数据却标成 round_no=1、hand_id 也按 1 生成。
    with pytest.raises(ValueError):
        engine.export_hand(world, 1)
    exported = engine.export_hand(world, 5)
    assert exported["round_no"] == 5
    assert exported["winner_seat"] == 0
    outcome = check_hand(exported, rules)
    assert outcome["status"] == "passed", outcome


def test_final_round_export_includes_game_ended():
    """缺陷 B：末局导出行必须含 game_ended（累计积分唯一载体）。"""
    rules = make_rules()
    hand13 = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "北"]
    row = build_full_world_row(
        rules,
        hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="北",
        wall=["2b", "3b"] + ["发"] * 20,
        dealer=0,
        scores_before=(10, 20, 30, 40),
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Hu())
    world = _drive_to_end(engine, world, chooser)
    record = world.round_records[0]
    kinds = [e.kind for e in record.events]
    assert kinds[-1] == "game_ended"  # 记录内也含 game_ended（修复前仅 world.events 有）
    exported = engine.export_hand(world, 1)
    exported_kinds = [e["type"] for e in exported["events"]]
    assert exported_kinds[-1] == "game_ended"
    game_ended = exported["events"][-1]
    assert game_ended["data"]["final_scores"] == [34, 12, 22, 32]
    assert game_ended["seat"] == -1  # 官方语义：-1 表示无获胜者（缺陷 F 对齐）
    round_ended = next(e for e in exported["events"] if e["type"] == "round_ended")
    assert round_ended["seat"] == 0  # 胡牌局 round_ended 座位=赢家
    outcome = check_hand(exported, rules)
    assert outcome["status"] == "passed", outcome


def test_draw_round_ended_seat_aligned_to_minus_one():
    """缺陷 F：流局 round_ended 导出 seat=-1（官方无获胜者语义）。"""
    rules = make_rules()
    wall = ["2b", "3b"] + ["发"] * 20
    row = build_full_world_row(
        rules,
        hands13=[_JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"], ["5w"] + _JUNK[:12]],
        dealer_drawn="9t",
        wall=wall,
        dealer=0,
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    world = _drive_to_end(engine, world, simple_chooser(rules))
    exported = engine.export_hand(world, 1)
    round_ended = next(e for e in exported["events"] if e["type"] == "round_ended")
    game_ended = next(e for e in exported["events"] if e["type"] == "game_ended")
    assert round_ended["seat"] == -1
    assert game_ended["seat"] == -1
    outcome = check_hand(exported, rules)
    assert outcome["status"] == "passed", outcome


def test_total_tiles_after_gang_replacement():
    """缺陷 E：杠上补牌后守恒计数不虚高（可摸区+保留区口径）。"""
    from ._helpers import total_tiles

    rules = make_rules()
    hand13 = ["1w", "1w", "1w"] + _JUNK[:10]
    wall = ["2b", "3b", "4b"] + ["发"] * 20
    row = build_full_world_row(
        rules, hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
        dealer_drawn="1w", wall=wall, dealer=0,
    )
    engine = SimulationEngine(rules)
    world = engine.from_replay(row)
    chooser = QueuedChooser(rules)
    chooser.enqueue("draw", 0, Gang(Tile("1w"), GangKind.CONCEALED))
    world = _drive_frames(engine, world, chooser, 1)
    assert world.progression.seats[0].chain_count == 1
    # 起点：53（14/13/13/13）+ 23 墙 = 76；补牌后 76 不变（修复前高估为 77）。
    assert total_tiles(world) == 76


def _drive_frames(engine, world, chooser, count):
    for _ in range(count):
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            return world
        choices = tuple(
            SimulationChoice(d.window_key, chooser(d)) for d in frame.decisions
        )
        world = engine.advance(world, frame.revision, choices)
    return world
