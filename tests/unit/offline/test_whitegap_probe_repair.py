"""复验变体真实执行、多白完整回退与160单局统计，不授策略收益。"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view, VipRouteProjectionLimits
from hangma_bot.policy.vip_g37_rf1_identity import VIP_G37_RF1_IDENTITY

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools/research/white-count-audit-2026-10-09"


def load_tool(name):
    spec = importlib.util.spec_from_file_location("whitegap_" + name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROBE = load_tool("probe_quote_variants")
STAGE = load_tool("stage160_driver")
BASE = PROBE.RF1_SOURCE.read_text()
FIXTURE = json.loads((ROOT / "tests/fixtures/research/whitegap-probe-repair/input-witnesses.json").read_text())
WITNESSES = FIXTURE["witnesses"]
SOURCES = {**PROBE.variant_sources(BASE, "discard"), **PROBE.variant_sources(BASE, "response")}


@lru_cache
def source_module(name):
    return PROBE.load_module(SOURCES[name])


def score(name, witness):
    return source_module(name)["score_actions"](WITNESSES[witness]["view"])


def parent(witness):
    return PROBE.load_module(BASE)["score_actions"](WITNESSES[witness]["view"])


@pytest.mark.parametrize("name", list(SOURCES))
def test_all_declared_probes_compile_in_production_restricted_executor(name):
    ActionValueExecutor(SOURCES[name], name=name, max_operations=4_800_000,
                        max_local_collection_size=8192)


@pytest.mark.parametrize("name,witness", [
    ("kappa_1.1", "discard_support_flip"),
    ("varref_3", "singlewhite_width_flip"),
    ("claimcost_0.10", "singlewhite_claim_flip"),
    ("flexcost_1", "singlewhite_flex_flip"),
])
def test_true_public_input_changes_quote_and_first_choice(name, witness):
    """此正控会拒绝原同命名空间覆盖；恒等控制通过不能替代它。"""
    before, after = parent(witness), score(name, witness)
    assert PROBE.chosen(before)[0] != PROBE.chosen(after)[0]
    assert {e["action_key"] for e in before["entries"]} == {e["action_key"] for e in after["entries"]}
    assert {e["action_key"]: e["score"] for e in before["entries"]} != {
        e["action_key"]: e["score"] for e in after["entries"]}


@pytest.mark.parametrize("name", list(SOURCES))
def test_actual_multiwhite_response_preserves_entire_parent_output(name):
    assert PROBE.window_whites(WITNESSES["multiwhite_response"]["view"]) == 2
    assert score(name, "multiwhite_response") == parent("multiwhite_response")


def test_parameter_receipts_and_full_identity_controls_are_independent():
    rows = list(WITNESSES.values())
    d = PROBE.audit_views(BASE, rows, mode="discard")
    r = PROBE.audit_views(BASE, rows, mode="response")
    assert d["identity_control_full_outputs_equal"] and r["identity_control_full_outputs_equal"]
    assert d["all_outside_gate_full_outputs_equal"] and r["all_outside_gate_full_outputs_equal"]
    knobs = d["variants"]["kappa_1.1"]["effective_knobs"]
    assert knobs["SPEEDCAP"] == 5.28
    assert d["variants"]["varref_3"]["effective_knobs"]["VARREF"] == 3.0
    assert d["variants"]["purposes1_5.0"]["effective_knobs"]["PURPOSES"][1] == 5.0
    assert r["variants"]["claimcost_0.10"]["effective_knobs"]["CLAIMCOST"] == 0.1


def test_white_count_does_not_double_count_a_joined_draw_and_rejects_bad_size():
    view = copy.deepcopy(WITNESSES["urgency_low"]["view"])
    state = view["visible_state"]
    state["my_hand"] = ["1w"] * 13
    state["drawn_tile"] = "白"
    assert PROBE.window_whites(view) == 1
    state["my_hand"].append("白")
    assert PROBE.window_whites(view) == 1
    state["my_hand"][0] = "白"
    assert PROBE.window_whites(view) == 2
    assert not PROBE.eligible(view)
    state["my_hand"].append("1w")
    assert PROBE.window_whites(view) is None
    assert not PROBE.eligible(view)


def test_tight_or_unknown_wall_and_hu_root_keep_the_parent():
    view = copy.deepcopy(WITNESSES["discard_support_flip"]["view"])
    enhanced = source_module("kappa_1.1")["score_actions"]
    baseline = PROBE.load_module(BASE)["score_actions"]
    for wall in (20, None):
        view["visible_state"]["remaining_tile_count"] = wall
        assert enhanced(view) == baseline(view)
    view["visible_state"]["remaining_tile_count"] = 70
    # 合成的根类型只检验范围门，不声称该修改是合法牌局。
    view["actions"][0]["action_type"] = "hu"
    assert not PROBE.eligible(view)
    assert enhanced(view) == baseline(view)


def test_urgency_uses_current_context_and_has_no_previous_window_residue():
    name = "m2_u1.5_melds2"
    first = score(name, "urgency_high")
    assert first != parent("urgency_high")
    assert score(name, "urgency_low") == parent("urgency_low")
    assert score(name, "urgency_high") == first


@lru_cache
def rebuilt_view(witness):
    """以生产唯一规则由原公开观察重建，不手写VIP图或规则结果。"""
    row = WITNESSES[witness]
    params = VIP_G37_RF1_IDENTITY["params"]
    config = RuleConfig(**params["rule_config"])
    rules = HangmaRules(config)
    observation = observation_from_json(row["observation"])
    window = window_key_from_json(row["window_key"])
    request = DecisionRequest(observation,
        CompetitionContext("offline-whitegap-regression", None, None, None, None, (), 0),
        rules.analyze(observation, route_limits=ValueAnalysisLimits(**params["route_limits"])),
        row["decision_id"], window.trigger_seq, window, ())
    view = build_vip_route_scoring_view(request, config,
        limits=VipRouteProjectionLimits(**params["projection_limits"]))
    raw = json.dumps(view.candidate_view(), ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode()
    assert hashlib.sha256(raw).hexdigest() == row["view_sha256"]
    return view


@pytest.mark.parametrize("name,witness", [
    ("kappa_1.1", "discard_support_flip"),
    ("claimcost_0.10", "singlewhite_claim_flip"),
    ("flexcost_1", "multiwhite_response"),
    ("m2_u1.5_melds2", "urgency_high"),
])
def test_rebuilt_public_view_scores_match_restricted_executor(name, witness):
    expected = score(name, witness)
    executor = ActionValueExecutor(SOURCES[name], name=name, max_operations=4_800_000,
                                   max_local_collection_size=8192)
    batch = executor.score_vip_route(rebuilt_view(witness))
    assert batch.status == "SCORED"
    assert {e.action_key: e.score.hex() for e in batch.entries} == {
        e["action_key"]: e["score"].hex() for e in expected["entries"]}


@pytest.mark.parametrize("scores,expected", [
    ([10, 5, 0, -5], 3), ([-5, 0, 5, 10], -3),
    ([10, 10, 5, 0], 2), ([0, 0, 0, 0], 0), ([0, 10, 10, 0], -2),
])
def test_official_place_points_direction_and_ties(scores, expected):
    assert STAGE.place_points(scores) == expected


def complete_tables():
    return [{"table_index": i, "status": "complete", "scores": [30, -10, -10, -10],
             "completed_hands": 16, "exported_hands": 16, "export_errors": 0,
             "place_points": 3} for i in range(10)]


def test_complete_stage_aggregates_all_160_hands():
    row = STAGE.summarize_stage(7, complete_tables())
    assert row["stage_valid_160"]
    assert row["net_seat0"] == 300 and row["place_points_sum"] == 30


@pytest.mark.parametrize("change", ["missing", "failed", "short_rounds", "export_error",
                                      "missing_export", "duplicate", "wrong_points", "nonconserving"])
def test_incomplete_or_inconsistent_stage_is_unknown_not_partial_total(change):
    tables = complete_tables()
    if change == "missing": tables.pop()
    elif change == "failed": tables[0]["status"] = "failed"
    elif change == "short_rounds": tables[0]["completed_hands"] = 15
    elif change == "export_error": tables[0]["export_errors"] = 1
    elif change == "missing_export": tables[0]["exported_hands"] = 15
    elif change == "duplicate": tables[0]["table_index"] = 1
    elif change == "wrong_points": tables[0]["place_points"] = -3
    elif change == "nonconserving": tables[0]["scores"][1] = -9
    row = STAGE.summarize_stage(7, tables)
    assert not row["stage_valid_160"]
    assert row["net_seat0"] is None and row["place_points_sum"] is None


def test_export_failure_is_retained_and_repeated_frame_does_not_duplicate_hands():
    class Engine:
        def start(self, spec): return "world"
        def frame(self, world): return SimpleNamespace(completed_hands=16)
        def export_hand_settlement(self, world, number): return {"round_no": number}
        def export_hand(self, world, number):
            if number == 5: raise ValueError("explicit export gap")
            return {"round_no": number}

    rows = []
    engine = STAGE.StageAuditEngine(Engine(), rows.append)
    world = engine.start(SimpleNamespace(match_id="synthetic-export-gate"))
    engine.frame(world)
    engine.frame(world)
    assert len(rows) == 16 and engine.exported_hands == 16 and engine.export_errors == 1
    assert rows[4]["hand_export_error"] == "ValueError"
