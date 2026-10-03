"""完整路线事实审计与恶意 JSON 门禁；不运行选择、桌赛或官方房。"""
import copy
from dataclasses import fields, is_dataclass, replace
import json

import pytest

from hangma_bot.application.audit_codec import (
    decision_request_from_json, decision_request_to_json,
    rule_analysis_from_json, rule_analysis_to_json,
)
from hangma_bot.application import route_fact_codec as codec
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.progression import CatchPlayState, HandResult
from hangma_bot.hangma.public_tile_counts import (
    ConditionalTileCounts, PublicClaimEvidence, PublicTileCounts,
)
from hangma_bot.hangma.route_transition import ConditionalPhase
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicDiscard, PublicEvent, PublicMeld
from tests.unit.policy.support import make_observation, make_request


CONFIG = RuleConfig("route-fact-codec-test", 1, False)
ORDINARY = ("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "东", "东")


def observation(hand=ORDINARY, drawn="南", *, phase="draw", trigger=None):
    response = phase != "draw"
    return make_observation(
        my_hand=tuple(Tile(code) for code in hand),
        drawn_tile=None if response else Tile(drawn), phase=phase,
        responding_seats=(0,) if response else (), turn_seat=3 if response else 0,
        last_discard=PublicDiscard(3, Tile(trigger), 10) if response else None,
        discards=((), (), (), (Tile(trigger),)) if response else ((), (), (), ()),
        hand_counts=(13 if response else 14, 13, 13, 13), chain_piao=0, gang_draw=False,
    )


def analyze(obs, *, extended=True):
    return HangmaRules(CONFIG).analyze(
        obs, route_limits=ValueAnalysisLimits(max_expansions=8192) if extended else None)


def assert_all_fields_equal(before, after):
    """递归比较每个字段，不依赖数据类 __eq__ 或 field.compare 的选择。"""
    assert type(before) is type(after)
    if is_dataclass(before):
        for field in fields(before):
            assert_all_fields_equal(getattr(before, field.name), getattr(after, field.name))
    elif type(before) is tuple:
        assert len(before) == len(after)
        for first, second in zip(before, after):
            assert_all_fields_equal(first, second)
    else:
        assert before == after


@pytest.fixture(scope="module")
def analysis():
    return analyze(observation())


@pytest.mark.parametrize("obs,required", (
    (observation(), "discard:"),
    (observation(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                  "7w", "8w", "白", "白"), "9w"), "hu"),
    (observation(("1w", "2w", "1b", "1b", "1b", "1b", "5w", "6w", "7w",
                  "8w", "9w", "东", "南"), phase="response_chi", trigger="3w"), "chi:"),
    (observation(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                  "东", "东", "东", "南"), phase="response_peng", trigger="东"), "peng:"),
    (observation(("1w",) * 4 + ("2w",) * 4 + ("3w", "4w", "5w", "东", "南"), "白"), "gang:"),
    (observation(("白",) * 3 + ORDINARY[:10]), "discard:"),
    (observation(("白",) * 4 + ORDINARY[:9]), "discard:"),
))
def test_actual_rules_all_action_families_and_multi_white_round_trip(obs, required):
    original = analyze(obs)
    assert any(item.action_key.startswith(required) for item in original.legal_candidates)
    assert original.route_frontier is not None and original.conditional_roots is not None
    encoded = rule_analysis_to_json(original)
    wire = json.loads(json.dumps(encoded, ensure_ascii=False, allow_nan=False))
    restored = rule_analysis_from_json(wire)
    assert_all_fields_equal(original, restored)
    assert rule_analysis_to_json(restored) == wire


def test_legacy_keys_and_missing_optional_extensions_restore_none():
    original = analyze(observation(), extended=False)
    wire = rule_analysis_to_json(original)
    assert set(wire) == {"codec_version", "legal_candidates", "emergency_candidate",
                         "completeness", "ruleset_version", "issues"}
    restored = rule_analysis_from_json(json.loads(json.dumps(wire)))
    assert restored.route_frontier is restored.conditional_roots is None
    assert_all_fields_equal(original, restored)
    assert json.dumps(rule_analysis_to_json(restored), separators=(",", ":")) == json.dumps(
        wire, separators=(",", ":"))


def test_optional_fields_can_be_saved_independently_and_empty_is_not_none(analysis):
    for original in (replace(analysis, route_frontier=None),
                     replace(analysis, conditional_roots=None),
                     replace(analysis, conditional_roots=())):
        restored = rule_analysis_from_json(rule_analysis_to_json(original))
        assert_all_fields_equal(original, restored)
    old = rule_analysis_to_json(analysis)
    old.pop("route_frontier")
    old.pop("conditional_roots")
    assert rule_analysis_from_json(old).conditional_roots is None


def test_complete_conditional_state_events_claim_evidence_terminal_and_unknown(analysis):
    root = analysis.conditional_roots[0]
    original = root.branches[0].state
    events = (
        PublicEvent(10, "chi", 0, (Tile("1w"), Tile("2w"), Tile("3w")),
                    occurred_at_unix_sec=12345, detail_kind="公開", catch_play=True,
                    gang_replenish=False, response_window="response_chi", claimed_tile=Tile("3w")),
        PublicEvent(11, "game_end", 0, result_draw=False, result_fan=2,
                    result_details=("爆头",), result_scores=(6, -2, -2, -2), final_scores=(10, -2, -3, -5)),
    )
    meld = PublicMeld(0, "chi", events[0].tiles, 3)
    claim = PublicClaimEvidence(0, 0, 3, Tile("3w"), "assumed", False)
    public = replace(original.public_view, melds=((meld,), (), (), ()),
                     public_history=events, consumed_seq=11, claim_evidence=(claim,))
    terminal = replace(original,
        phase=ConditionalPhase.TERMINAL, terminal_result=HandResult(0, False, 2, ("爆头",), (6, -2, -2, -2)),
        identity=replace(original.identity, path=("本家合法杠", "给定补牌")),
        unseen_capacities=(None,) + original.unseen_capacities[1:],
        unseen_evidence=("unknown",) + original.unseen_evidence[1:],
        catch_circle=CatchPlayState(True, 3), root_public_view=public, public_view=public,
        response_public_discard=PublicDiscard(3, Tile("3w"), 10),
        response_trigger=(3, Tile("3w")), response_window="response_chi",
        expected_draw_seat=None, expected_discard_seat=None, other_draw_replacement=None,
    )
    changed = replace(root, branches=(replace(root.branches[0], state=terminal),))
    full = replace(analysis, conditional_roots=(changed,) + analysis.conditional_roots[1:])
    decoded = rule_analysis_from_json(json.loads(json.dumps(rule_analysis_to_json(full))))
    assert_all_fields_equal(full, decoded)
    restored = decoded.conditional_roots[0].branches[0].state
    assert restored.public_view.public_history[-1].result_scores == (6, -2, -2, -2)
    assert restored.public_view.claim_evidence[0].retained_in_river is False
    assert restored.unseen_capacities[0] is None and restored.unseen_evidence[0] == "unknown"
    assert restored.root_public_view is not None and restored.public_view is not None


@pytest.mark.parametrize("value", (
    PublicTileCounts((None, 0, 4) + (2,) * 31, ("unknown", "conservative", "exact") + ("exact",) * 31),
    ConditionalTileCounts((None,) + (2,) * 33, (None,) + (1,) * 33, ("unknown",) + ("exact",) * 33),
    CatchPlayState(True, None), HandResult(None, True, 0, (), (0, 0, 0, 0)),
))
def test_public_counts_and_terminal_values_exact_round_trip(value):
    restored = codec.route_fact_from_json(json.loads(json.dumps(codec.route_fact_to_json(value))))
    assert_all_fields_equal(value, restored)


@pytest.mark.parametrize("change", ("tag", "root_tag", "missing", "extra", "bool", "enum", "vector", "version"))
def test_malicious_or_incomplete_tags_fields_and_types_are_rejected(analysis, change):
    wire = rule_analysis_to_json(analysis)["conditional_roots"]
    state = wire["value"][0]["fields"]["branches"][0]["fields"]["state"]
    if change == "tag":
        state["type"] = "os.system"
    elif change == "root_tag":
        wire["root_type"] = "PlayerObservation"
    elif change == "missing":
        state["fields"].pop("concealed")
    elif change == "extra":
        state["fields"]["secret"] = "不允许的字段"
    elif change == "bool":
        state["fields"]["meld_count"] = True
    elif change == "enum":
        state["fields"]["phase"]["value"] = "invented"
    elif change == "vector":
        state["fields"]["unseen_capacities"].pop()
    else:
        wire["codec_version"] = "route-fact-codec/2"
    with pytest.raises(ValueError):
        codec.conditional_roots_from_json(wire)


@pytest.mark.parametrize("number", (float("nan"), float("inf"), float("-inf")))
def test_non_finite_values_are_rejected_before_type_construction(analysis, number):
    wire = rule_analysis_to_json(analysis)["conditional_roots"]
    wire["value"][0]["fields"]["branches"][0]["fields"]["state"]["fields"]["wall_remaining"] = number
    with pytest.raises(ValueError, match="非有限"):
        codec.conditional_roots_from_json(wire)


def test_wire_depth_and_lengths_are_checked_before_recursive_decode():
    nested = 0
    for _ in range(codec.MAX_ROUTE_FACT_DEPTH + 1):
        nested = [nested]
    with pytest.raises(ValueError, match="深度"):
        codec.route_fact_from_json(nested)
    with pytest.raises(ValueError, match="数组长度"):
        codec.route_fact_from_json([0] * (codec.MAX_ROUTE_FACT_SEQUENCE_ITEMS + 1))
    with pytest.raises(ValueError, match="字符串长度"):
        codec.route_fact_from_json("白" * codec.MAX_ROUTE_FACT_STRING_BYTES)


def test_encoder_checks_types_and_capacity_before_large_materialization(analysis, monkeypatch):
    root = analysis.conditional_roots[0]
    state = root.branches[0].state
    with pytest.raises(ValueError, match="标量类型"):
        codec.route_fact_to_json(replace(state, meld_count=True))
    with pytest.raises(ValueError, match="数组长度"):
        codec.route_fact_to_json(replace(state.identity, path=("x",) * (codec.MAX_ROUTE_FACT_SEQUENCE_ITEMS + 1)))
    with pytest.raises(ValueError, match="整数位数"):
        codec.route_fact_to_json(replace(state.identity, round_no=1 << codec.MAX_ROUTE_FACT_INTEGER_BITS))
    monkeypatch.setattr(codec, "MAX_ROUTE_FACT_VALUES", 5)
    with pytest.raises(ValueError, match="总值数量"):
        codec.route_fact_to_json(state)


def test_payload_container_mutation_is_private_and_mismatched_root_types_rejected(analysis):
    encoded = rule_analysis_to_json(analysis)
    original = copy.deepcopy(encoded)
    decoded = rule_analysis_from_json(encoded)
    encoded["conditional_roots"]["value"].clear()
    assert codec.conditional_roots_to_json(decoded.conditional_roots) == original["conditional_roots"]
    with pytest.raises(ValueError, match="前沿根标签"):
        codec.route_frontier_from_json(original["conditional_roots"])
    with pytest.raises(ValueError, match="条件根标签"):
        codec.conditional_roots_from_json(original["route_frontier"])


def test_unknown_objects_and_raw_mapping_extensions_cannot_be_deserialized():
    with pytest.raises(ValueError, match="白名单"):
        codec.route_fact_to_json(object())
    with pytest.raises(ValueError):
        codec.route_fact_from_json({"type": "ConditionalRouteState", "fields": {}})


def test_complete_decision_request_restores_the_actual_extended_rule_facts(analysis):
    request = make_request(observation(), analysis)
    wire = json.loads(json.dumps(decision_request_to_json(request), ensure_ascii=False, allow_nan=False))
    restored = decision_request_from_json(wire)
    assert_all_fields_equal(request, restored)
    assert decision_request_to_json(restored) == wire


@pytest.mark.parametrize("count,evidence", ((5, "exact"), (-1, "exact"), (0, "invented")))
def test_public_counts_reject_invalid_capacity_and_evidence(count, evidence):
    value = PublicTileCounts((count,) + (0,) * 33, (evidence,) + ("exact",) * 33)
    with pytest.raises(ValueError, match="公开计数"):
        codec.route_fact_to_json(value)
    wire = codec.route_fact_to_json(PublicTileCounts((0,) * 34, ("exact",) * 34))
    wire["value"]["fields"]["counts"][0] = count
    wire["value"]["fields"]["evidence"][0] = evidence
    with pytest.raises(ValueError, match="公开计数"):
        codec.route_fact_from_json(wire)
