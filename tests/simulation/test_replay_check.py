"""历史核对 check_hand：结构、重放一致性、官方结果对拍、按能力核对。

覆盖：模拟导出单局行（胡/流局）passed；冲突构造 failed；缺墙 full_history
流局 not_checked；三份真实归档资料按能力核对（赢家场次 passed、两张流局
场次 not_checked 且零冲突）。行为向量 full-history-without-wall 的对应侧
（from_replay 拒绝）在 test_export_import.py。
"""

from __future__ import annotations

import copy
import json

import pytest

from hangma_bot.offline.replay_check import check_hand
from hangma_bot.simulation import SimulationEngine

from ._helpers import (
    ARCHIVED_ROOMS,
    archived_fixture,
    archived_hand_row,
    make_rules,
    make_spec,
    simple_chooser,
    drive,
)


_JUNK = ["1b", "4b", "7b", "2t", "5t", "8t", "3w", "6w", "9w", "东", "南", "西", "北"]


def _completed_row(win=False):
    """用小牌墙快速完成一局并导出单局行（win=True 为胡牌行）。"""
    from ._helpers import build_full_world_row

    rules = make_rules()
    engine = SimulationEngine(rules, rules_hash="hash-1")
    if win:
        hand13 = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "北"]
        row = build_full_world_row(
            rules,
            hands13=[hand13, _JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"]],
            dealer_drawn="北",
            wall=["2b", "3b"] + ["发"] * 20,
            dealer=0,
        )
        world = engine.from_replay(row)

        def chooser(decision):
            from hangma_bot.kernel.actions import Hu

            return Hu()

        world = drive(engine, world, chooser)
    else:
        row = build_full_world_row(
            rules,
            hands13=[_JUNK[:], _JUNK[1:] + ["5b"], _JUNK[2:] + ["6t", "7t"], ["5w"] + _JUNK[:12]],
            dealer_drawn="9t",
            wall=["2b", "3b"] + ["发"] * 20,
            dealer=0,
        )
        world = drive(engine, engine.from_replay(row), simple_chooser(rules))
    return rules, engine.export_hand(world, 1)


def test_simulated_rows_pass_check():
    """模拟导出的胡牌/流局单局行都能通过规则核对（status=passed）。"""
    rules = make_rules()
    for win in (False, True):
        _rules, row = _completed_row(win=win)
        outcome = check_hand(row, rules)
        assert outcome["status"] == "passed", "win={0}: {1}".format(win, outcome)
        assert outcome["hand_id"] == row["hand_id"]
        assert outcome["checked_events"] == len(row["events"])


def test_check_conflicts_are_failed():
    """规则冲突构造 → failed 并带 seq；不读文件、不改输入。"""
    rules = make_rules()
    _rules, row = _completed_row(win=False)
    snapshot = json.dumps(row, ensure_ascii=False, sort_keys=True)
    # 篡改弃牌：把第一个 tile_discarded 换成不在手牌的牌码。
    for event in row["events"]:
        if event["type"] == "tile_discarded":
            event["tile"] = "9b" if event["tile"] != "9b" else "8b"
            break
    outcome = check_hand(row, rules)
    assert outcome["status"] == "failed"
    conflict_codes = [issue["code"] for issue in outcome["issues"] if issue["code"].startswith("conflict")]
    assert conflict_codes, outcome["issues"]
    assert json.dumps(row, ensure_ascii=False, sort_keys=True) != snapshot  # 修改发生在输入上（预期）


def test_unknown_replay_version_not_checked():
    rules = make_rules()
    _rules, row = _completed_row(win=False)
    row["replay_schema_version"] = 99
    outcome = check_hand(row, rules)
    assert outcome["status"] == "not_checked"
    assert outcome["checked_events"] == 0


def test_missing_round_ended_not_checked():
    rules = make_rules()
    _rules, row = _completed_row(win=False)
    row["events"] = [e for e in row["events"] if e["type"] != "round_ended"]
    outcome = check_hand(row, rules)
    assert outcome["status"] == "not_checked"
    assert any(i["code"] == "not_checked.round_ended_missing" for i in outcome["issues"])


def test_full_history_without_wall_draw_is_not_checked():
    """缺墙 full_history：流局成因不可核对 → not_checked（不冒充完整世界）。"""
    rules = make_rules()
    _rules, row = _completed_row(win=False)  # 模拟流局行，改造成缺墙 full_history
    history_row = copy.deepcopy(row)
    history_row["coverage"] = "full_history"
    history_row["origin"] = "official"
    history_row["initial"]["wall"] = None
    history_row["initial"]["world_payload"] = None
    history_row["initial"]["world_schema"] = None
    history_row["initial"]["draw_identity_known"] = False
    outcome = check_hand(history_row, rules)
    assert outcome["status"] == "not_checked"
    codes = [issue["code"] for issue in outcome["issues"]]
    assert "not_checked.wall_unknown_draw_cause" in codes
    assert not any(code.startswith("conflict") for code in codes)


@pytest.mark.parametrize("filename,event_count,has_win,winner", ARCHIVED_ROOMS)
def test_archived_rooms_checked_by_capability(filename, event_count, has_win, winner):
    """三份真实分块资料按能力核对：赢家场次 passed、流局场次 not_checked。"""
    path = archived_fixture(filename)
    if not path.exists():
        pytest.skip("归档夹具缺失：{0}".format(filename))
    rules = make_rules(ruleset="official-v14", base=1, youcai=False)
    row = archived_hand_row(path, rules)
    outcome = check_hand(row, rules)
    assert outcome["checked_events"] == event_count, outcome
    conflict_codes = [
        issue["code"] for issue in outcome["issues"] if issue["code"].startswith("conflict")
    ]
    assert not conflict_codes, "真实资料出现规则冲突：{0}".format(conflict_codes)
    if has_win:
        assert outcome["status"] == "passed", outcome
        # 官方赢家对拍细节：fan=1、明细 [平胡]、积分增量。
        assert row["winner_seat"] == winner
    else:
        assert outcome["status"] == "not_checked", outcome
        codes = [issue["code"] for issue in outcome["issues"]]
        assert "not_checked.wall_unknown_draw_cause" in codes


def test_archived_win_recomputes_official_fan():
    """t_714a 官方自摸：本地重算 fan=1/平胡与官方 round_ended 一致（passed 即证明）。"""
    path = archived_fixture("t_714a42392cba_b0.json")
    if not path.exists():
        pytest.skip("归档夹具缺失")
    rules = make_rules(ruleset="official-v14", base=1, youcai=False)
    row = archived_hand_row(path, rules)
    outcome = check_hand(row, rules)
    assert outcome["status"] == "passed"
    round_ended = next(e for e in row["events"] if e["type"] == "round_ended")
    assert round_ended["data"]["fan"] == 1
    assert round_ended["data"]["detail"] == ["平胡"]