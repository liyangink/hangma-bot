"""开发抽卡权限、真实同分排序、失败分母与冻结漂移回归。"""

import asyncio
import gzip
import hashlib
import json
from collections import Counter
from dataclasses import asdict

import pytest

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import (
    observation_from_json, observation_to_json, window_key_from_json, window_key_to_json,
)
from hangma_bot.offline import vip_eoh_probe as probe
from hangma_bot.offline.vip_eoh_generate import (
    VIP_EOH_BATCH_SCHEMA, VIP_EOH_GENERATION_SCHEMA, VIP_EOH_PROFILE, VipEohBatch,
    write_vip_seed_parent,
)
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.action_value import ScoreBatch
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_heuristic_view import VIP_ROUTE_CANDIDATE_KIND
from hangma_bot.policy.route_vip_heuristic import (
    RouteVipHeuristicPolicy, VIP_ROUTE_HEURISTIC_SEED_SOURCE, VipRouteProjectionLimits,
)
from hangma_bot.simulation import MatchSpec, SimulationEngine, SimulationChoice


TIE_SOURCE = '''
def score_actions(view):
    entries = []
    for action in view["actions"]:
        entries.append({"action_key": action["action_key"], "score": 0.0, "trace": {"case": "tie"}})
    return {"status": "SCORED", "entries": entries}
'''
CHANGED_SOURCE = '''
def score_actions(view):
    best = max([action["action_key"] for action in view["actions"]])
    entries = []
    for action in view["actions"]:
        entries.append({"action_key": action["action_key"], "score": 1.0 if action["action_key"] == best else 0.0, "trace": {}})
    return {"status": "SCORED", "entries": entries}
'''


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(path, batch_file, source):
    """人工装载夹具走真实身份和executor；不冒充模型或准入证据。"""

    batch = VipEohBatch.read(batch_file)
    ActionValueExecutor(source, max_operations=batch.max_operations)
    identity = batch.identity(source)
    path.mkdir()
    (path / "candidate.py").write_text(source)
    write_json(path / "generation.json", {
        "schema": VIP_EOH_GENERATION_SCHEMA, "profile": VIP_EOH_PROFILE,
        "candidate_kind": VIP_ROUTE_CANDIDATE_KIND, "artifact_role": "candidate_proposal",
        "status": "loaded_not_admitted", "load": {"ok": True}, "identity_stable": True,
        "identity": identity, "source_sha256": identity["source_sha256"],
        "thought": "人工探针夹具，不是实际模型输出", "mechanism": None,
        "admission": {"eligible": False},
    })
    return path


@pytest.fixture
def batch_file(tmp_path):
    path = tmp_path / "batch.json"
    write_json(path, {
        "schema": VIP_EOH_BATCH_SCHEMA, "batch_id": "probe-test",
        "budgets": {"model_calls": 0, "input_tokens": 0, "output_tokens": 0,
                    "table_instances": 0, "wall_clock_seconds": 1000},
        "per_call": {"input_tokens": 1, "max_tokens": 1, "timeout_seconds": 1},
        "max_operations": 100_000, "projection_limits": asdict(VipRouteProjectionLimits()),
        "rule_config": asdict(RuleConfig("hangma-mvp-v10-public-counts", 1, False)),
        "route_limits": asdict(ValueAnalysisLimits(max_expansions=8192)),
        "input_bound": None, "sampling": {"temperature": None, "top_p": None, "seed": None},
    })
    return path


@pytest.fixture(scope="module")
def real_records():
    """只取公开模拟器初始合法帧，不运行完整桌或读WorldState内部。"""

    config = TournamentConfig(1, 1, RuleConfig("hangma-mvp-v10-public-counts", 1, False), TimingConfig(1, 1, 3))
    rules, records = HangmaRules(config.rules), []
    engine = SimulationEngine(rules)
    for seed in (*range(12), 219):
        decision = engine.frame(engine.start(MatchSpec(
            "probe-test", f"probe-{seed}", config, seed, 0, (0, 0, 0, 0)))).decisions[0]
        observation = decision.observation
        analysis = rules.analyze(observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
        records.append({"schema": "vip-heuristic-smoke-decision/1",
                        "observation": observation_to_json(observation),
                        "window_key": window_key_to_json(decision.window_key),
                        "legal_action_keys": [c.action_key for c in analysis.legal_candidates],
                        "status": "scored", "selected_action_key": analysis.emergency_candidate.action_key,
                        "policy_compute_ms_observed": 1, "outcome": "arbitrary-test-marker"})
    return records


def audit(path, batch_file, records):
    path.mkdir()
    batch = VipEohBatch.read(batch_file)
    identity = batch.identity(VIP_ROUTE_HEURISTIC_SEED_SOURCE)
    (path / "candidate.py").write_text(VIP_ROUTE_HEURISTIC_SEED_SOURCE)
    write_json(path / "manifest.json", {
        "schema": "vip-heuristic-smoke-manifest/1", "kind": "mechanical_smoke_not_strength_or_runtime_gate",
        "strict_policy": True, "normal_fallback_allowed": False,
        "identity": identity, "config": {"rules": asdict(batch.rule_config)},
    })
    with gzip.open(path / "decisions.jsonl.gz", "wt") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def panel(tmp_path, batch_file, records, *, max_windows=2, per_stratum=1):
    source = audit(tmp_path / "audit", batch_file, records)
    out = tmp_path / "panel"
    probe.build_vip_eoh_panel(source, out, manifest_sha256=sha(source / "manifest.json"),
        decisions_sha256=sha(source / "decisions.jsonl.gz"), max_windows=max_windows, per_stratum=per_stratum)
    return out / "panel.json"


def test_selection_ignores_outcomes_status_choices_scores_and_timing(tmp_path, batch_file, real_records):
    source_a = audit(tmp_path / "a", batch_file, real_records)
    changed = [{**r, "status": "failed", "selected_action_key": "never-use-this",
                "candidates": [{"score": 1e99}], "outcome": "opposite", "policy_compute_ms_observed": 9999}
               for r in real_records]
    source_b = audit(tmp_path / "b", batch_file, changed)
    results = []
    for source in (source_a, source_b):
        results.append(probe.build_vip_eoh_panel(source, tmp_path / (source.name + "-panel"),
            manifest_sha256=sha(source / "manifest.json"), decisions_sha256=sha(source / "decisions.jsonl.gz")))
    assert results[0]["windows"] == results[1]["windows"]
    assert results[0]["source"]["decisions_sha256"] != results[1]["source"]["decisions_sha256"]
    assert all(r["development_only"] and not r["confirmation"] for r in results)


def test_visible_pair_count_four_tiles_are_two_pairs_and_selection_is_capped(tmp_path, batch_file, real_records):
    selected = json.loads(panel(tmp_path, batch_file, [real_records[-1]], max_windows=1).read_bytes())
    item = selected["windows"][0]
    visible = observation_from_json(item["observation"])
    held = Counter(t.code for t in visible.my_hand + (visible.drawn_tile,))
    assert held["发"] == 4
    assert item["stratum"][3] == sum(n // 2 for c, n in held.items() if c != "白") == 3
    assert item["stratum"][1] == held["白"]
    assert item["stratum"][2] == sorted({k.split(":", 1)[0] for k in item["legal_action_keys"]})
    with pytest.raises(ValueError):
        probe.build_vip_eoh_panel(tmp_path / "audit", tmp_path / "bad", manifest_sha256="a"*64,
            decisions_sha256="b"*64, max_windows=129)


@pytest.mark.parametrize("name", ("manifest.json", "decisions.jsonl.gz"))
def test_source_hash_drift_rejects_before_panel_output(tmp_path, batch_file, real_records, name):
    source = audit(tmp_path / "audit", batch_file, real_records)
    hashes = (sha(source / "manifest.json"), sha(source / "decisions.jsonl.gz"))
    with (source / name).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="SHA256"):
        probe.build_vip_eoh_panel(source, tmp_path / "out", manifest_sha256=hashes[0], decisions_sha256=hashes[1])
    assert not (tmp_path / "out").exists()


def test_shared_frozen_view_and_real_policy_tie_order(tmp_path, batch_file, real_records, monkeypatch):
    panel_file = panel(tmp_path, batch_file, real_records, max_windows=1)
    parent = package(tmp_path / "parent", batch_file, TIE_SOURCE)
    candidate = package(tmp_path / "candidate", batch_file, TIE_SOURCE.replace('"score": 0.0', '"score": 1.0'))
    counts, received = Counter(), []
    actual_analyze, actual_build = HangmaRules.analyze, probe.build_vip_route_scoring_view
    actual_score = ActionValueExecutor.score_vip_route

    def counted_analyze(*args, **kwargs):
        counts["analyze"] += 1
        return actual_analyze(*args, **kwargs)

    def counted_build(*args, **kwargs):
        counts["build"] += 1
        return actual_build(*args, **kwargs)

    def counted_score(self, view):
        received.append(view)
        return actual_score(self, view)

    monkeypatch.setattr(HangmaRules, "analyze", counted_analyze)
    monkeypatch.setattr(probe, "build_vip_route_scoring_view", counted_build)
    monkeypatch.setattr(ActionValueExecutor, "score_vip_route", counted_score)
    out = tmp_path / "probe"
    result = probe.run_vip_eoh_probe(panel_file, batch_file, out, parent_paths=[parent], candidate_paths=[candidate])
    assert counts == {"analyze": 1, "build": 1}
    assert len(received) == 2 and received[0] is received[1]
    assert received[0].__dataclass_params__.frozen
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert result["status"] == "probe_complete_not_admitted"
    comparison = result["comparisons"][0]
    assert comparison["score_changed_windows"] == 1
    assert comparison["preferred_action_changed_windows"] == 0
    assert comparison["observed_behavior_difference"] is False
    item = json.loads(panel_file.read_bytes())["windows"][0]
    observation, window = observation_from_json(item["observation"]), window_key_from_json(item["window_key"])
    batch = VipEohBatch.read(batch_file)
    analysis = actual_analyze(HangmaRules(batch.rule_config), observation, route_limits=batch.route_limits)
    request = DecisionRequest(observation, CompetitionContext("test", None, None, None, None, (), 0),
        analysis, "test", window.trigger_seq, window, ())
    plan = asyncio.run(RouteVipHeuristicPolicy(batch.rule_config, source=TIE_SOURCE).choose(request, BudgetPolicy().build(800, 3)))
    assert rows[0]["ordered_action_keys"] == [c.action_key for c in plan.candidates]
    assert rows[0]["preferred_action_key"] == min(item["legal_action_keys"])
    assert rows[0]["candidate_counted_operations"] > 0 and all("trace" in e for e in rows[0]["entries"])
    with pytest.raises(FileExistsError):
        probe.run_vip_eoh_probe(panel_file, batch_file, out, parent_paths=[parent], candidate_paths=[candidate])


def test_probe_uses_frozen_capacity_instead_of_legacy_default(tmp_path, batch_file, real_records):
    """真实探针能执行4097项局部集合，容量与生成档声明的8192保持一致。"""
    data = json.loads(batch_file.read_bytes())
    data["projection_limits"]["max_nodes"] = 8192
    write_json(batch_file, data)
    source = '''
def score_actions(view):
    values = list(range(4097))
    return {"status":"SCORED", "entries":[{"action_key":a["action_key"], "score":len(values), "trace":{}} for a in view["actions"]]}
'''
    panel_file = panel(tmp_path, batch_file, real_records, max_windows=1)
    candidate = package(tmp_path / "candidate", batch_file, source)
    result = probe.run_vip_eoh_probe(panel_file, batch_file, tmp_path / "probe",
        parent_paths=[candidate], candidate_paths=[candidate])
    assert result["status"] == "probe_complete_not_admitted"


@pytest.mark.parametrize("source", (
    'def score_actions(view):\n return {"status":"ABSTAIN","entries":[],"reason":"test"}',
    'def score_actions(view):\n return {"status":"SCORED","entries":[]}',
    TIE_SOURCE.replace('{"case": "tie"}', '{"large": "x" * 100000}'),
    'def score_actions(view):\n total = 0\n for number in range(100000):\n  total += number\n return {"status":"SCORED","entries":[]}',
))
def test_failed_candidate_keeps_all_windows_and_parent_comparison_denominator(tmp_path, batch_file, real_records, source):
    panel_file = panel(tmp_path, batch_file, real_records)
    parent = package(tmp_path / "parent", batch_file, TIE_SOURCE)
    candidate = package(tmp_path / "candidate", batch_file, source)
    out = tmp_path / "probe"
    result = probe.run_vip_eoh_probe(panel_file, batch_file, out, parent_paths=[parent], candidate_paths=[candidate])
    assert result["planned_package_windows"] == 4
    assert result["scored_package_windows"] == 2 and result["unfinished_package_windows"] == 2
    assert result["comparisons"][0]["planned_windows"] == 2
    assert result["comparisons"][0]["unfinished_windows"] == 2
    assert result["comparisons"][0]["observed_behavior_difference"] is False
    assert len((out / "results.jsonl").read_text().splitlines()) == 4


def test_failed_load_and_failed_projection_keep_cartesian_denominator(tmp_path, batch_file, real_records, monkeypatch):
    panel_file = panel(tmp_path, batch_file, real_records)
    parent = package(tmp_path / "parent", batch_file, TIE_SOURCE)

    def failed_build(*args, **kwargs):
        raise ValueError("injected projection failure")

    monkeypatch.setattr(probe, "build_vip_route_scoring_view", failed_build)
    result = probe.run_vip_eoh_probe(panel_file, batch_file, tmp_path / "probe",
        parent_paths=[parent], candidate_paths=[tmp_path / "missing"])
    assert result["planned_package_windows"] == result["unfinished_package_windows"] == 4
    assert result["packages"][1]["loaded"] is False and result["comparisons"][0]["unfinished_windows"] == 2


def test_only_preferred_changes_get_behavior_difference_per_ordered_parent(tmp_path, batch_file, real_records):
    panel_file = panel(tmp_path, batch_file, real_records, max_windows=1)
    first = package(tmp_path / "first", batch_file, TIE_SOURCE)
    second = package(tmp_path / "second", batch_file, CHANGED_SOURCE)
    candidate = package(tmp_path / "candidate", batch_file, CHANGED_SOURCE)
    result = probe.run_vip_eoh_probe(panel_file, batch_file, tmp_path / "probe",
        parent_paths=[first, second], candidate_paths=[candidate])
    assert [p["path"] for p in result["packages"]] == [str(p.resolve()) for p in (first, second, candidate)]
    assert [c["preferred_action_changed_windows"] for c in result["comparisons"]] == [1, 0]
    assert [c["observed_behavior_difference"] for c in result["comparisons"]] == [True, False]
    assert all(not result[k] for k in ("admitted", "confirmation", "strength_claim", "release_claim"))


def test_package_changes_during_probe_invalidate_behavior_credit(tmp_path, batch_file, real_records, monkeypatch):
    panel_file = panel(tmp_path, batch_file, real_records, max_windows=1)
    parent = package(tmp_path / "parent", batch_file, TIE_SOURCE)
    candidate = package(tmp_path / "candidate", batch_file, CHANGED_SOURCE)
    original = ActionValueExecutor.score_vip_route

    def drift_after_score(self, view):
        result = original(self, view)
        with (candidate / "candidate.py").open("a") as stream:
            stream.write("\n# drift\n")
        return result

    monkeypatch.setattr(ActionValueExecutor, "score_vip_route", drift_after_score)
    result = probe.run_vip_eoh_probe(panel_file, batch_file, tmp_path / "probe",
        parent_paths=[parent], candidate_paths=[candidate])
    assert result["status"] == "invalidated" and result["identity_stable"] is False
    assert result["scored_package_windows"] == 2 and result["comparisons"][0]["preferred_action_changed_windows"] == 1
    assert result["comparisons"][0]["observed_behavior_difference"] is False


def test_panel_observation_hash_cannot_be_rewritten(tmp_path, batch_file, real_records):
    panel_file = panel(tmp_path, batch_file, real_records, max_windows=1)
    record = json.loads(panel_file.read_bytes())
    record["windows"][0]["observation"]["scores"] = [1, 0, 0, 0]
    write_json(panel_file, record)
    with pytest.raises(ValueError, match="SHA256"):
        probe.run_vip_eoh_probe(panel_file, batch_file, tmp_path / "probe",
            parent_paths=[], candidate_paths=[tmp_path / "missing"])


def test_manual_seed_package_uses_existing_public_loader(tmp_path, batch_file, real_records):
    panel_file = panel(tmp_path, batch_file, real_records, max_windows=1)
    parent = tmp_path / "seed"
    write_vip_seed_parent(parent, batch_file)
    result = probe.run_vip_eoh_probe(panel_file, batch_file, tmp_path / "probe",
        parent_paths=[parent], candidate_paths=[parent])
    assert result["status"] == "probe_complete_not_admitted"
    assert result["comparisons"][0]["preferred_action_changed_windows"] == 0


def test_nonpreferred_order_change_has_no_behavior_credit(tmp_path, batch_file, real_records):
    """首选固定为最小键，另把其他键倒序；次选换序仍不算行为改变。"""

    source = '''
def score_actions(view):
    keys = sorted([a["action_key"] for a in view["actions"]])
    entries = []
    for index, key in enumerate(keys):
        entries.append({"action_key": key, "score": 1000.0 if index == 0 else index, "trace": {}})
    return {"status": "SCORED", "entries": entries}
'''
    panel_file = panel(tmp_path, batch_file, real_records, max_windows=1)
    first = package(tmp_path / "parent", batch_file, TIE_SOURCE)
    candidate = package(tmp_path / "candidate", batch_file, source)
    result = probe.run_vip_eoh_probe(panel_file, batch_file, tmp_path / "probe",
        parent_paths=[first], candidate_paths=[candidate])
    compared = result["comparisons"][0]
    assert compared["nonpreferred_order_only_changed_windows"] == 1
    assert compared["preferred_action_changed_windows"] == 0
    assert compared["observed_behavior_difference"] is False


@pytest.mark.parametrize("field", ("panel", "batch", "audit"))
def test_input_changes_during_probe_invalidate_report(tmp_path, batch_file, real_records, monkeypatch, field):
    panel_file = panel(tmp_path, batch_file, real_records, max_windows=1)
    candidate = package(tmp_path / "candidate", batch_file, TIE_SOURCE)
    original = ActionValueExecutor.score_vip_route
    path = {"panel": panel_file, "batch": batch_file, "audit": tmp_path / "audit/decisions.jsonl.gz"}[field]

    def change_after_score(self, view):
        result = original(self, view)
        with path.open("ab") as stream:
            stream.write(b" ")
        return result

    monkeypatch.setattr(ActionValueExecutor, "score_vip_route", change_after_score)
    result = probe.run_vip_eoh_probe(panel_file, batch_file, tmp_path / "probe",
        parent_paths=[], candidate_paths=[candidate])
    assert result["status"] == "invalidated" and result["identity_stable"] is False


def test_stratum_cap_keeps_each_public_phase_round_robin(tmp_path, batch_file, real_records):
    """通过一次公开弃牌生成真实响应帧；两张上限也须兼顾摸牌和响应。"""

    config = TournamentConfig(1, 1, RuleConfig("hangma-mvp-v10-public-counts", 1, False), TimingConfig(1, 1, 3))
    rules = HangmaRules(config.rules)
    engine = SimulationEngine(rules)
    world = engine.start(MatchSpec("probe-response", "probe-response", config, 13, 0, (0, 0, 0, 0)))
    frame = engine.frame(world)
    decision = frame.decisions[0]
    action = next(c.action for c in rules.analyze(decision.observation).legal_candidates if isinstance(c.action, Discard))
    responses = engine.frame(engine.advance(world, frame.revision, (SimulationChoice(decision.window_key, action),)))
    response_records = []
    for decision in responses.decisions:
        analysis = rules.analyze(decision.observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
        response_records.append({"observation": observation_to_json(decision.observation),
            "window_key": window_key_to_json(decision.window_key),
            "legal_action_keys": [c.action_key for c in analysis.legal_candidates]})
    assert all(r["observation"]["phase"] != "draw" for r in response_records)
    panel_file = panel(tmp_path, batch_file, [*real_records, *response_records], max_windows=2)
    selected = json.loads(panel_file.read_bytes())
    assert len({i["stratum"][0] for i in selected["windows"]}) == 2


def test_partial_comparison_preserves_observed_change_without_full_panel_credit(tmp_path, batch_file, real_records, monkeypatch):
    """不能靠弃评一个窗口，再将剩余窗口的首选改变冒称完整面板差异。"""

    panel_file = panel(tmp_path, batch_file, real_records)
    parent = package(tmp_path / "parent", batch_file, TIE_SOURCE)
    candidate = package(tmp_path / "candidate", batch_file, CHANGED_SOURCE)
    original = ActionValueExecutor.score_vip_route
    calls = 0

    def abstain_last(self, view):
        nonlocal calls
        calls += 1
        if calls == 4:
            return ScoreBatch("ABSTAIN", (), "injected last-window abstention")
        return original(self, view)

    monkeypatch.setattr(ActionValueExecutor, "score_vip_route", abstain_last)
    result = probe.run_vip_eoh_probe(panel_file, batch_file, tmp_path / "probe",
        parent_paths=[parent], candidate_paths=[candidate])
    compared = result["comparisons"][0]
    assert compared["planned_windows"] == 2 and compared["paired_scored_windows"] == 1
    assert compared["preferred_action_changed_windows"] == 1
    assert compared["comparison_complete"] is False and compared["observed_behavior_difference"] is False


def test_expanded_panel_retains_all_observed_strata(tmp_path, batch_file, real_records):
    """显式128界可纳入全部观察层及最高白板量层，不按结果决定收录。"""
    file = panel(tmp_path, batch_file, real_records, max_windows=128)
    result = json.loads(file.read_bytes())
    assert result["max_windows"] == 128
    assert result["window_count"] == result["stratum_count"]
    assert {json.dumps(item["stratum"]) for item in result["windows"]} == {
        json.dumps(item["stratum"]) for item in result["stratum_sizes"]}
    expected_max = max(sum(t == "白" for t in row["observation"]["my_hand"])
                       + int(row["observation"]["drawn_tile"] == "白") for row in real_records)
    assert max(item["stratum"][1] for item in result["windows"]) == expected_max


@pytest.mark.parametrize("limit", (False, True, 0, 129))
def test_panel_rejects_invalid_expanded_bound(tmp_path, limit):
    with pytest.raises(ValueError):
        probe.build_vip_eoh_panel(tmp_path / "absent", tmp_path / "new",
            manifest_sha256="a" * 64, decisions_sha256="b" * 64, max_windows=limit)


def test_public_panel_validation_binds_source_files(tmp_path, batch_file, real_records):
    """后续开发驱动获得公开可重核材料，不依赖另一模块的私有入口。"""
    file = panel(tmp_path, batch_file, real_records, max_windows=2)
    verified = probe.validate_vip_eoh_panel(file)
    assert verified["panel"] == json.loads(file.read_bytes())
    assert len(verified["frozen_files"]) == 4
    for path, expected in verified["frozen_files"].items():
        from pathlib import Path
        assert sha(Path(path)) == expected
    source = tmp_path / "audit/candidate.py"
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError):
        probe.validate_vip_eoh_panel(file)
