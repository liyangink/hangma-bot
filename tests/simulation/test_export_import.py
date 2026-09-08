"""导出导入：单局行/world_payload 往返、反事实身份、缺墙拒绝。"""

from __future__ import annotations

import copy
import json

import pytest

from hangma_bot.simulation import SimulationEngine, hand_id, split_group_id

from ._helpers import build_full_world_row, make_rules, make_spec, simple_chooser, drive


def test_export_roundtrip_drives_identically():
    """full_world 导出 → 导入 → 同策略驱动：终局一致，事件流逐字节一致。"""
    rules = make_rules()
    engine = SimulationEngine(rules, rules_hash="hash-1")
    spec = make_spec(rules, rounds=1, seed=66)
    world = drive(engine, engine.start(spec), simple_chooser(rules))
    row = engine.export_hand(world, 1)
    assert row["coverage"] == "full_world"
    assert row["winner_seat"] is not None or row["is_draw"] is True
    imported = engine.from_replay(row)
    imported = drive(engine, imported, simple_chooser(rules))
    assert imported.scores == world.scores
    assert [json.dumps(_ev(e), sort_keys=True) for e in imported.round_records[0].events] == [
        json.dumps(_ev(e), sort_keys=True) for e in world.round_records[0].events
    ]


def test_export_incomplete_round_has_null_results():
    """未完成局导出：结果字段明确为空，world_payload 仍可导入。"""
    rules = make_rules()
    engine = SimulationEngine(rules, rules_hash="hash-1")
    spec = make_spec(rules, rounds=1, seed=66)
    world = engine.start(spec)
    row = engine.export_hand(world, 1)
    assert row["winner_seat"] is None
    assert row["is_draw"] is None
    assert row["scores_after"] is None
    assert row["score_delta"] is None
    assert row["result_confirmed"] is False
    assert row["events"] == []
    imported = engine.from_replay(row)
    assert imported.progression.window == "draw"


def test_export_is_deterministic_and_does_not_mutate():
    rules = make_rules()
    engine = SimulationEngine(rules, rules_hash="hash-1")
    spec = make_spec(rules, rounds=1, seed=66)
    world = drive(engine, engine.start(spec), simple_chooser(rules))
    before = world
    row_a = engine.export_hand(world, 1)
    row_b = engine.export_hand(world, 1)
    assert row_a == row_b
    assert world == before


def test_counterfactual_export_identity():
    """另存反事实轨迹：新 match_id、parent_hand_id 保留、scenario 不变、世界不改。"""
    rules = make_rules()
    engine = SimulationEngine(rules, rules_hash="hash-1")
    spec = make_spec(rules, rounds=1, seed=66, match_id="m-orig", scenario_id="s-orig")
    world = drive(engine, engine.start(spec), simple_chooser(rules))
    row = engine.export_hand(world, 1, match_id="m-fork")
    original_hand_id = hand_id("hangma-simulation", "s-orig", "m-orig", 1)
    assert row["hand_id"] == hand_id("hangma-simulation", "s-orig", "m-fork", 1)
    assert row["parent_hand_id"] == original_hand_id
    assert row["game_key"]["game_id"] == "m-fork"
    assert row["game_key"]["tournament_id"] == "s-orig"
    assert row["split_group_id"] == split_group_id(["hangma-simulation", "s-orig"])
    # 反事实导出可独立导入完成。
    imported = drive(engine, engine.from_replay(row), simple_chooser(rules))
    assert engine.frame(imported).final_scores is not None
    # 原世界不受影响。
    assert world.scores == drive(engine, engine.from_replay(engine.export_hand(world, 1)), simple_chooser(rules)).scores


def test_from_replay_rejects_full_history_without_wall():
    """行为向量 full-history-without-wall：历史可核对，世界导入必须拒绝。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    row = build_full_world_row(
        rules, hands13=[["1w"] * 13] * 4, dealer_drawn="2w", wall=["3w"] * 4 + ["4w"] * 16,
    )
    history_row = copy.deepcopy(row)
    history_row["coverage"] = "full_history"
    history_row["initial"]["wall"] = None
    history_row["initial"]["world_payload"] = None
    history_row["initial"]["world_schema"] = None
    with pytest.raises(ValueError):
        engine.from_replay(history_row)


def test_from_replay_rejections():
    """版本/配置/牌墙/冗余字段不一致一律 ValueError，未知版本保留拒绝。"""
    rules = make_rules()
    engine = SimulationEngine(rules)
    base = build_full_world_row(
        rules, hands13=[["1w"] * 13] * 4, dealer_drawn="2w", wall=["3w"] * 4 + ["4w"] * 16,
    )
    # 未知 replay_schema_version。
    bad = copy.deepcopy(base)
    bad["replay_schema_version"] = 99
    with pytest.raises(ValueError):
        engine.from_replay(bad)
    # 未知 world_schema。
    bad = copy.deepcopy(base)
    bad["initial"]["world_schema"] = "simulation-world/2"
    with pytest.raises(ValueError):
        engine.from_replay(bad)
    # 未知发牌算法。
    bad = copy.deepcopy(base)
    bad["initial"]["world_payload"]["deal_algorithm"] = "other-deal"
    with pytest.raises(ValueError):
        engine.from_replay(bad)
    # 规则配置不一致（另一底分）。
    bad = copy.deepcopy(base)
    bad["initial"]["world_payload"]["rule_config"]["base_score"] = 2
    with pytest.raises(ValueError):
        engine.from_replay(bad)
    # 保留区张数不合法。
    bad = copy.deepcopy(base)
    bad["initial"]["world_payload"]["wall_back"] = len(base["initial"]["wall"])
    with pytest.raises(ValueError):
        engine.from_replay(bad)
    # 冗余 initial.hands 与 payload 不一致。
    bad = copy.deepcopy(base)
    bad["initial"]["hands"][0][0] = "9b"
    with pytest.raises(ValueError):
        engine.from_replay(bad)
    # 缺 payload。
    bad = copy.deepcopy(base)
    bad["initial"]["world_payload"] = None
    with pytest.raises(ValueError):
        engine.from_replay(bad)


def test_export_includes_manifest_fields():
    """单局行携带规则配置/哈希/指南版本与源身份（契约 §5.2 字段）。"""
    rules = make_rules()
    engine = SimulationEngine(rules, rules_hash="rules-hash-abc")
    spec = make_spec(rules, rounds=1, seed=66, scenario_id="sc-x", match_id="m-x")
    world = drive(engine, engine.start(spec), simple_chooser(rules))
    row = engine.export_hand(world, 1)
    assert row["replay_schema_version"] == 1
    assert row["rules_hash"] == "rules-hash-abc"
    assert row["guide_version"] == 23
    assert row["guide_captured_at"] == "2026-09-08"
    assert row["rule_config"] == {
        "ruleset_version": "test",
        "base_score": 1,
        "you_cai_bi_kao": False,
    }
    assert row["origin"] == "simulated"
    assert row["initial"]["draw_identity_known"] is True
    assert len(row["initial"]["hands"][0]) == 14
    assert all(len(hand) == 13 for hand in row["initial"]["hands"][1:])
    payload = row["initial"]["world_payload"]
    assert payload["world_schema"] == "simulation-world/1"
    assert payload["deal_algorithm"] == "simulation-v1:deal-v1"


def _ev(event) -> dict:
    return {
        "seq": event.seq,
        "type": event.kind,
        "seat": event.seat,
        "tile": event.tile.code if event.tile is not None else "",
        "data": dict(event.data) if event.data else None,
    }
