"""合成 v26 事件经公开导出/核验入口，旧平台跳窗按原版本兼容。"""

from copy import deepcopy

import pytest

from hangma_bot.kernel.actions import Pass
from hangma_bot.offline.replay_check import check_hand
from tests.simulation.test_catch_owner_v26 import _after_piao_and_claim, _discard, _game, _play


def assert_prefix_checked(row, rules):
    result = check_hand(row, rules)
    assert result["checked_events"] == len(row["events"]), result
    assert result["status"] == "not_checked", result  # 有限前缀刻意没有终局。
    assert {item["code"] for item in result["issues"]} == {"not_checked.round_ended_missing"}, result


@pytest.mark.parametrize("claim", ["peng", "chi"])
def test_exported_owner_claim_and_repeat_piao_are_checkable(claim):
    rules, engine, world = _after_piao_and_claim(claim)
    world = _discard(engine, world, 0, "白")
    world = _discard(engine, world, 1, "5b")
    assert_prefix_checked(engine.export_hand(world, 1), rules)


def test_forced_white_relay_transfers_replay_owner():
    rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 白 白", ["白", "5b"])
    world = _discard(engine, world, 0, "白")
    world = _discard(engine, world, 1, "白")
    world = _discard(engine, world, 2, "5b")
    assert_prefix_checked(engine.export_hand(world, 1), rules)


def test_nonowner_hand_discard_is_rejected_by_shared_rules():
    rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 白 白", ["东", "5b"])
    world = _discard(engine, world, 0, "白")
    world = _discard(engine, world, 1, "东")
    row = engine.export_hand(world, 1)
    discarded = next(e for e in row["events"] if e["type"] == "tile_discarded" and e["seat"] == 1)
    discarded["tile"] = next(code for code in row["initial"]["hands"][1] if code != "东")
    result = check_hand(row, rules)
    assert result["status"] == "failed"
    assert any(i["code"] == "conflict.action_illegal" for i in result["issues"])


def test_old_direct_draw_is_not_mistaken_for_v26_window_behavior():
    rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 白 白", ["东", "5b"])
    world = _discard(engine, world, 0, "白")
    world = _discard(engine, world, 1, "东")
    world = _play(engine, world, 0, Pass(), "response_peng")
    row = engine.export_hand(world, 1)
    row["events"] = [e for e in row["events"] if e["type"] != "pass"]
    assert check_hand(row, rules)["status"] == "failed"
    for version in (24, None):
        old = deepcopy(row)
        old["guide_version"] = version
        result = check_hand(old, rules)
        assert result["status"] == "not_checked", result
        assert not any(i["code"].startswith("conflict.") for i in result["issues"])
        assert any(i["code"] == "info.legacy_catch_play_window" for i in result["issues"])
