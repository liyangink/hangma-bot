"""通过公开 check_hand 核对持续爆头与链；固定规则例，不调用在线服务。"""

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Tile
from hangma_bot.offline.replay_check import check_hand

from ._helpers import make_rules


def _row(hand, events):
    other = "1b 2b 3b 4b 5b 6b 7b 8b 9b 南 南 西 西".split()
    return {
        "hand_id": "lifecycle-fixed", "replay_schema_version": 1, "round_no": 1,
        "rule_config": {"ruleset_version": "test-v1", "base_score": 1, "you_cai_bi_kao": False},
        "initial": {"dealer_seat": 0, "hands": [hand.split(), other, other, other], "wall": None},
        "events": events,
    }


def test_dealer_initial_draw_initializes_baotou_for_settlement():
    """庄家14张直抽没有tile_drawn事件，也必须初始化爆头计番。"""
    row = _row("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 东 白 北", [
        {"seq": 1, "type": "round_ended", "seat": 0,
         "data": {"draw": False, "fan": 2, "detail": ["平胡", "爆头"], "scores": [48, -16, -16, -16]}},
    ])
    rules = make_rules(ruleset="test-v1", base=1, youcai=False)
    assert check_hand(row, rules)["status"] == "passed"


class _ObservedRules(HangmaRules):
    """记录 check_hand 交给公开规则接口的玩家观察，实际计算仍用原规则。"""

    def __init__(self):
        super().__init__(make_rules(ruleset="test-v1", base=1, youcai=False).config)
        self.observations = []

    def analyze(self, observation):
        self.observations.append(observation)
        return super().analyze(observation)


def _event(events, kind, seat, tile=None, data=None):
    events.append({"seq": len(events) + 1, "type": kind, "seat": seat, "tile": tile, "data": data or {}})


def _discard_and_pass(events, seat, tile, *, chi=True):
    _event(events, "tile_discarded", seat, tile)
    for responder in ((seat + 1) % 4, (seat + 2) % 4, (seat + 3) % 4):
        _event(events, "pass", responder)
    if chi:
        _event(events, "pass", (seat + 1) % 4)


def _chi_gang_win_row(marker):
    """固定听任意牌前态吃后暗杠；补牌时静态非任意听但继承爆头。"""
    events = []
    _discard_and_pass(events, 0, "北")
    for seat, draw in ((1, "5t"), (2, "6t"), (3, "2w")):
        _event(events, "tile_drawn", seat, draw)
        _discard_and_pass(events, seat, draw, chi=seat != 3)
    _event(events, "chi", 0, "2w", {"tiles": ["2w", "3w", "4w"]})
    _event(events, "gang", 0, "1w", {"kind": "an"})
    _event(events, "tile_drawn", 0, "2w", {} if marker is None else {"gang_replenish": marker})
    _event(events, "round_ended", 0, data={
        "draw": False, "fan": 4, "detail": ["平胡", "杠开", "爆头"], "scores": [96, -32, -32, -32],
    })
    return _row("1w 1w 1w 1w 白 白 2w 3w 4w 2w 3w 4w 6w 北", events)


@pytest.mark.parametrize("marker", [None, True])
def test_chi_gang_replacement_keeps_baotou_and_replays_exact_settlement(marker):
    rules = _ObservedRules()
    outcome = check_hand(_chi_gang_win_row(marker), rules)
    assert not [issue for issue in outcome["issues"] if issue["code"].startswith("conflict")], outcome
    # 未给牌墙只限制杠边界核验，不能声称完整passed。
    assert outcome["status"] == "not_checked"
    assert {issue["code"] for issue in outcome["issues"]} == {"not_checked.gang_wall_boundary"}
    final = rules.observations[-1]
    assert final.rule_state.baotou is True
    assert final.rule_state.chain_count == 1
    assert final.chain_piao == 0
    assert final.gang_draw is True


def test_check_hand_preserves_seat_zero_and_masks_other_draw_without_dropping_event():
    rules = _ObservedRules()
    check_hand(_chi_gang_win_row(True), rules)
    final = rules.observations[-1]
    assert final.public_history[0].seat == 0
    other_draws = [event for event in final.public_history if event.kind == "tile_drawn" and event.seat in (1, 2, 3)]
    assert len(other_draws) == 3
    assert all(event.tiles == () for event in other_draws)
    assert final.consumed_seq == final.public_history[-1].seq
    assert final.public_history[-1].gang_replenish is True


@pytest.mark.parametrize("tile_fields,expected", [
    ({"tile": "2w"}, Tile("2w")), ({}, None), ({"tile": None}, None), ({"tile": ""}, None),
])
def test_check_hand_preserves_only_explicit_chi_supply(tile_fields, expected):
    """历史核对只透传当时公开供牌；缺字段时不从组合或影子暗牌回填。"""
    row = _chi_gang_win_row(True)
    source_chi = next(event for event in row["events"] if event["type"] == "chi")
    source_chi.pop("tile")
    source_chi.update(tile_fields)
    rules = _ObservedRules()
    check_hand(row, rules)
    final = rules.observations[-1]
    public_chi = next(event for event in final.public_history if event.kind == "chi")
    assert public_chi.claimed_tile == expected
    assert public_chi.tiles == (Tile("2w"), Tile("3w"), Tile("4w"))
    assert all(event.claimed_tile is None for event in final.public_history if event.kind != "chi")


@pytest.mark.parametrize("claimed_tile", ["3w", "9t", "10t", 9, False, ["2w"]])
def test_check_hand_reports_conflicting_chi_supply_without_raising(claimed_tile):
    """坏供牌必须在影子状态推进前返回冲突，不能留到 PublicEvent 构造时抛错。"""
    row = _chi_gang_win_row(True)
    source_chi = next(event for event in row["events"] if event["type"] == "chi")
    source_chi["tile"] = claimed_tile
    outcome = check_hand(row, _ObservedRules())
    assert outcome["status"] == "failed"
    assert any(issue["code"] == "conflict.meld_tile_mismatch" and issue["seq"] == source_chi["seq"]
               for issue in outcome["issues"])


def test_discard_updates_baotou_before_next_claim_without_waiting_for_own_draw():
    """打北后进入听任意牌；下一次本人动作是吃，途中没有本人摸牌。"""
    row = _chi_gang_win_row(True)
    row["initial"]["hands"][0] = "1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 白 北 东".split()
    row["events"] = row["events"][:-3]  # 吃后停在记录末尾，未提供终局。
    rules = _ObservedRules()
    outcome = check_hand(row, rules)
    assert {issue["code"] for issue in outcome["issues"]} == {"not_checked.round_ended_missing"}
    assert rules.observations[-1].phase == "response_chi"
    assert rules.observations[-1].rule_state.baotou is True
    assert rules.observations[-1].rule_state.chain_count == 0


def test_gap_before_replacement_without_marker_is_not_guessed_as_ordinary_draw():
    row = _chi_gang_win_row(None)
    for event in row["events"][-2:]:
        event["seq"] += 1
    outcome = check_hand(row, _ObservedRules())
    assert outcome["status"] == "not_checked"
    assert any(issue["code"] == "not_checked.baotou_draw_source" for issue in outcome["issues"])
    assert not any(issue["code"].startswith("conflict") for issue in outcome["issues"])


def test_non_dealer_initial_baotou_is_inherited_before_first_draw_and_settles():
    """闲家起手任意听，直接吃→暗杠→补牌胡，须保留起手爆头计4番。"""
    events = []
    _discard_and_pass(events, 0, "2w", chi=False)
    _event(events, "chi", 1, "2w", {"tiles": ["2w", "3w", "4w"]})
    _event(events, "gang", 1, "1w", {"kind": "an"})
    _event(events, "tile_drawn", 1, "2w", {"gang_replenish": True})
    _event(events, "round_ended", 1, data={
        "draw": False, "fan": 4, "detail": ["平胡", "杠开", "爆头"],
        "scores": [-32, 40, -4, -4],
    })
    row = _row("1t 2t 3t 4t 5t 6t 7t 8t 9t 东 东 北 北 2w", events)
    row["initial"]["hands"][1] = "1w 1w 1w 1w 白 白 2w 3w 4w 2w 3w 4w 6w".split()
    rules = _ObservedRules()
    outcome = check_hand(row, rules)
    assert {issue["code"] for issue in outcome["issues"]} == {"not_checked.gang_wall_boundary"}
    assert outcome["status"] == "not_checked"
    first = rules.observations[0]
    assert first.seat == 1
    assert first.phase == "response_chi"
    assert first.drawn_tile is None
    assert first.rule_state.baotou is True
    final = rules.observations[-1]
    assert final.rule_state.baotou is True
    assert final.gang_draw is True
    assert (final.rule_state.chain_count, final.chain_piao) == (1, 0)
