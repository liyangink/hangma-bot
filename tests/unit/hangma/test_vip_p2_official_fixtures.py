"""v35 本座自然轨迹：只从已收到的官方快照与公开事件核动作机械。"""

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import observation, public_event
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits, ValueCoverage
from hangma_bot.hangma.observation_rules import reconcile_observation
from hangma_bot.kernel.actions import Gang, GangKind, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation


FIXTURES = Path(__file__).parents[2] / "fixtures/official/v35/vip-p2-natural"
CASES = (
    ("peng-followup-1114-1117.json", 2, 6, (1114, 1115, 1117),
     ((0, "peng:6b"), (1, "discard:9w"))),
    ("bugang-replenish-1510-1514.json", 3, 8, (1510, 1512, 1514),
     ((0, "gang:added:2t"), (1, "discard:6t"))),
    ("minggang-replenish-hu-1228-1231.json", 0, 6, (1228, 1230, 1231),
     ((0, "gang:exposed:4b"), (1, "hu"))),
)


def _read_case(name):
    """只读脱敏夹具；逐个官方响应走既有 DTO 与本座投影。"""

    data = json.loads((FIXTURES / name).read_text())
    raw_events = data["public_or_own_events"]
    assert all(event["type"] != "tile_drawn" or event["seat"] == data["seat"]
               for event in raw_events)
    events = tuple(public_event(event) for event in
                   parse_state_response({"events": raw_events}).events)
    views = []
    for record in data["state_responses"]:
        response = parse_state_response(record["response"])
        assert response.snapshot is not None and not response.gap
        snap = response.snapshot
        view = observation(snap, tuple(event for event in events if event.seq <= snap.seq),
                           data["game_id"])
        assert isinstance(view, PlayerObservation)
        views.append(replace(view, consumed_seq=snap.seq))
    config = data["provenance"]["rule_config"]
    assert (config["base_score"], config["you_cai_bi_kao"]) == (1, False)
    rules = HangmaRules(RuleConfig(config["ruleset_version"],
                                   config["base_score"], config["you_cai_bi_kao"]))
    return data, tuple(views), events, rules


@pytest.mark.parametrize("name,seat,round_no,seqs,actions", CASES,
                         ids=[case[0] for case in CASES])
def test_official_states_project_and_executed_actions_are_legal(
        name, seat, round_no, seqs, actions):
    """前后水位、信息权限与已执行动作必须同生产规则候选相容。"""

    data, views, events, rules = _read_case(name)
    assert data["provenance"]["guide_version"] == 35
    assert data["seat"] == seat
    assert tuple(view.snapshot_seq for view in views) == seqs
    assert all(view.game_id == data["game_id"] and view.round_no == round_no
               and view.seat == seat and view.consumed_seq == view.snapshot_seq
               for view in views)
    assert tuple(event.seq for event in events) == tuple(sorted(event.seq for event in events))
    assert all(view.chain_piao is None and view.gang_draw is None for view in views)
    assert all(record["response"].get("events") in (None, [])
               for record in data["state_responses"])
    for index, action_key in actions:
        legal = {candidate.action_key for candidate in rules.analyze(views[index]).legal_candidates}
        assert action_key in legal


def test_official_peng_keeps_claim_discard_as_a_separate_action():
    """碰成功先产生未摸弃牌窗；跟打再减少一张本人暗牌。"""

    data, (before, claimed, discarded), events, _ = _read_case(CASES[0][0])
    assert [event.kind for event in events] == ["tile_discarded", "peng", "tile_discarded"]
    assert all(row["response"] == {"ok": True} for row in data["successful_action_receipts"])
    seat = data["seat"]
    assert (before.phase, claimed.phase, discarded.phase) == (
        "response_peng", "draw", "response_peng")
    assert claimed.drawn_tile is None
    assert Counter(before.my_hand) - Counter((Tile("6b"), Tile("6b"))) == Counter(claimed.my_hand)
    assert claimed.melds[seat][:-1] == before.melds[seat]
    assert claimed.melds[seat][-1].kind == "peng"
    assert claimed.melds[seat][-1].tiles == (Tile("6b"),) * 3
    assert Counter(claimed.my_hand) - Counter((Tile("9w"),)) == Counter(discarded.my_hand)
    assert discarded.discards[seat] == claimed.discards[seat] + (Tile("9w"),)
    assert (before.remaining_tile_count, claimed.remaining_tile_count,
            discarded.remaining_tile_count) == (54, 54, 54)


@pytest.mark.parametrize("name,tile,kind,expected_meld", (
    ("bugang-replenish-1510-1514.json", "2t", GangKind.ADDED, "gang_bu"),
    ("minggang-replenish-hu-1228-1231.json", "4b", GangKind.EXPOSED, "gang_ming"),
))
def test_official_gang_replacement_requires_confirmed_action(
        name, tile, kind, expected_meld):
    """杠补来源与飘数只由成功回执、公开杠和权威快照共同核定。"""

    data, (before, landed, _), events, _ = _read_case(name)
    assert data["successful_action_receipts"][0]["response"] == {"ok": True}
    assert any(event.kind == "gang" and event.seat == data["seat"]
               and event.detail_kind == ("bu" if kind is GangKind.ADDED else "ming")
               for event in events)
    replacement = next(event for event in events if event.kind == "tile_drawn"
                       and event.gang_replenish)
    assert replacement.seq == landed.snapshot_seq and replacement.seat == data["seat"]
    assert landed.drawn_tile == replacement.tiles[0]
    assert landed.remaining_tile_count == before.remaining_tile_count - 1
    assert landed.rule_state.chain_count == before.rule_state.chain_count + 1 == 1
    assert any(meld.kind == expected_meld and meld.tiles == (Tile(tile),) * 4
               for meld in landed.melds[data["seat"]])
    assert landed.chain_piao is None and landed.gang_draw is None
    confirmed = reconcile_observation(
        before, landed, confirmed_action=Gang(Tile(tile), kind))
    assert confirmed.chain_piao == 0 and confirmed.gang_draw is True


def test_official_bugang_upgrades_original_peng_then_discards():
    """补杠升级原碰且补牌后跟打；不借赛后其他座位暗牌补齐状态。"""

    data, (before, landed, discarded), _, _ = _read_case(CASES[1][0])
    seat = data["seat"]
    assert len(before.melds[seat]) == len(landed.melds[seat]) == 2
    assert before.melds[seat][0].kind == "peng"
    assert landed.melds[seat][0].kind == "gang_bu"
    assert landed.melds[seat][0].from_seat == before.melds[seat][0].from_seat
    assert Counter(before.my_hand) - Counter((Tile("2t"),)) + Counter((Tile("7t"),)) == Counter(landed.my_hand)
    assert Counter(landed.my_hand) - Counter((Tile("6t"),)) == Counter(discarded.my_hand)
    assert discarded.discards[seat] == landed.discards[seat] + (Tile("6t"),)
    assert (before.rule_state.chain_count, landed.rule_state.chain_count,
            discarded.rule_state.chain_count) == (0, 1, 0)


def test_official_minggang_replacement_hu_settlement_only_after_reconciliation():
    """即时胡先承认原快照链证据缺项，再用已确认杠核番与四座净分。"""

    data, (before, landed, settled), events, rules = _read_case(CASES[2][0])
    assert before.phase == "response_peng" and landed.phase == "draw"
    assert settled.phase == "settled"
    seat = data["seat"]
    assert Counter(before.my_hand) - Counter((Tile("4b"),) * 3) + Counter((Tile("6b"),)) == Counter(landed.my_hand)
    assert len(landed.melds[seat]) == len(before.melds[seat]) + 1
    assert landed.melds[seat][-1].kind == "gang_ming"
    assert landed.melds[seat][-1].tiles == (Tile("4b"),) * 4
    assert landed.remaining_tile_count == before.remaining_tile_count - 1
    # 官方快照没有链内飘白/杠补字段。去掉同段可见事件后，不能只凭快照计分。
    without_chain_events = replace(landed, public_history=())
    unresolved_hu = next(candidate for candidate in rules.analyze(
        without_chain_events, value_limits=ValueAnalysisLimits()).legal_candidates
        if candidate.action_key == "hu")
    assert unresolved_hu.value_facts is not None
    assert unresolved_hu.value_facts.immediate_settlement is None
    assert unresolved_hu.value_facts.coverage is ValueCoverage.UNAVAILABLE
    assert data["successful_action_receipts"][1]["response"] == {"ok": True}
    confirmed = reconcile_observation(
        before, landed, confirmed_action=Gang(Tile("4b"), GangKind.EXPOSED))
    assert confirmed.chain_piao == 0 and confirmed.gang_draw is True
    hu = next(candidate for candidate in rules.analyze(
        confirmed, value_limits=ValueAnalysisLimits()).legal_candidates
        if candidate.action_key == "hu")
    result = hu.value_facts.immediate_settlement
    terminal = next(event for event in events if event.kind == "round_ended")
    assert result is not None and hu.value_facts.coverage is ValueCoverage.COMPLETE
    assert (result.fan, result.details, result.score_delta) == (
        terminal.result_fan, terminal.result_details, terminal.result_scores)
    assert settled.scores == tuple(before.scores[index] + result.score_delta[index]
                                   for index in range(4))
