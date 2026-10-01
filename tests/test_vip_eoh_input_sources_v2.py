"""新/2来源和证明合同；评分、规则、投影、装载均由隔离替身提供，无业务测量。"""
from copy import deepcopy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hangma_bot.offline import vip_eoh_input_sources as source
from hangma_bot.offline import vip_eoh_probe_v2 as probe
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.route_vip_heuristic import VipRouteProjectionLimits

ROOT = source.REPO_ROOT
INITIAL = Path(__file__).parent / "fixtures/vip_eoh_v2_action_before.json"


def record():
    """只读既有行动前字段，不重放、不计算或读取其结果用于选择。"""
    raw = json.loads(INITIAL.read_bytes())
    return {k: raw[k] for k in ("observation", "window_key", "legal_action_keys")}


def origin(root="r", hidden="original", source_id="s"):
    return {"source_id": source_id, "source_kind": source.CONDITIONED, "mother_root": root,
            "mother_single_hand": [root, 1], "permutation": [0, 1, 2, 3], "hidden_variant": hidden,
            "policy_role": "A", **source.CLAIMS}


def material(rows, source_id="s"):
    return {"source": {"source_id": source_id, "source_kind": source.CONDITIONED, "audit_dir": "/synthetic/" + source_id},
            "records": rows, "frame": {"fixture_kind": "synthetic_structure_only"}, "frozen_files": {}}


def test_result_fields_cannot_select():
    a = record(); b = deepcopy(a)
    b.update(selected_action_key="result-induced", status="winner", elapsed=999, candidate_score=1e90, settlement={"winner": 0})
    assert source.public_input(a, origin()) == source.public_input(b, origin())


def test_hidden_dedup_and_same_root_cap():
    a = source.public_input(record(), origin())
    b = source.public_input(record(), origin(hidden="public_consistent_hidden_1"))
    selected = source.select_public_inputs([material([a, b])], {"per_stratum": 3, "max_windows": 128, "max_windows_per_source_root": 1})
    assert selected["source_record_count"] == 2
    assert selected["unique_input_count"] == selected["window_count"] == 1
    assert len(selected["windows"][0]["origins"]) == 2
    assert selected["selected_source_roots"] == [{"source_id": "s", "mother_root": "r", "windows": 1}]
    with pytest.raises(ValueError, match="重复"):
        source.select_public_inputs([material([a, a])], {"per_stratum": 3, "max_windows": 128, "max_windows_per_source_root": 1})


def test_zero_white_mass_does_not_consume_rare_root_quota():
    rows = []
    for white, count in ((0, 100), (2, 3), (3, 3)):
        for i in range(count):
            item = source.public_input(record(), origin())
            # 纯选择器结构fixture：不冒称这些修改为真实来源公开输入。
            item["stratum"] = ["draw", white, i % 10, "41_plus", i % 4, False]
            item["input_sha256"] = source.sha(f"synthetic:{white}:{i}".encode())
            rows.append(item)
    selected = source.select_public_inputs([material(rows)], {"per_stratum": 3, "max_windows": 128, "max_windows_per_source_root": 12})
    assert selected["window_count"] == 12
    assert {w["stratum"][1] for w in selected["windows"]} == {0, 2, 3}
    assert selected["empty_rare_strata"] == "unknown_not_passed"


def test_source_cannot_be_aliased_to_escape_caps():
    one = material([source.public_input(record(), origin())])
    two = deepcopy(one); two["source"]["source_id"] = "alias"
    with pytest.raises(ValueError, match="改名重复"):
        source.select_public_inputs([one, two], {"per_stratum": 3, "max_windows": 128, "max_windows_per_source_root": 12})


def test_raw_candidate_not_remapped(tmp_path):
    ordinary = tmp_path / "candidate.py"; ordinary.write_bytes(b"ordinary RAW")
    original = tmp_path / "production.py"; original.write_bytes(b"current changed")
    snapshot = tmp_path / "snapshot.py"; snapshot.write_bytes(b"frozen producer")
    members = {str(ordinary): source.fingerprint(ordinary), str(original): source.fingerprint(snapshot)}
    files = {}
    source.verify_members(members, files, snapshot_map={str(original): str(snapshot)})
    assert str(ordinary) in files and str(snapshot) in files and str(original) not in files
    ordinary.write_bytes(b"RAW drift")
    with pytest.raises(ValueError, match="漂移"):
        source.verify_members(members, {}, snapshot_map={str(original): str(snapshot)})


def test_fake_schema_and_result_driven_spec_rejected(tmp_path):
    data = {"schema": source.SOURCE_SCHEMA, "source_id": "synthetic", "source_kind": "vip-heuristic-smoke-manifest/1",
            "audit_dir": str(tmp_path), "raw_seal": {}, "select_best_score": True}
    path = tmp_path / "source.json"; path.write_bytes(source.canonical(data))
    with pytest.raises(ValueError, match="严格source_kind"):
        source.read_public_input_source(path, source.sha(path.read_bytes()))
    data["source_kind"] = source.NATURAL; data["manifest"] = {}; path.write_bytes(source.canonical(data))
    with pytest.raises(ValueError, match="严格source_kind"):
        source.read_public_input_source(path, source.sha(path.read_bytes()))


def test_natural_filters_by_actual_manifest_A_before_fields(tmp_path, monkeypatch):
    baseline = {"policy_id": "r18-A", "registered_name": "r18_integrated_positive_v2",
                "provider": "registered_offline_research_not_live_release"}
    manifest = {"schema": "vip-route-development-manifest/1", "source_kind": "simulation", "development_only": True,
                "confirmation_claim": False, "published": False, "policy_metadata": {"A": baseline},
                "source_manifest": {}, "batch_id": "fixture", "pool_ids": {"H": "fixture"},
                "frame": [{"root_id": "r", "permutations": [[0, 1, 2, 3]]}]}
    path = tmp_path / "manifest.json"; path.write_bytes(source.canonical(manifest))
    pool = tmp_path / "H"; pool.mkdir()
    a = record(); a.update(policy_id="r18-A", root_id="r", permutation=[0, 1, 2, 3], pool="H", seat=0,
                           match_id="fixture:H:r:0123:r18-A")
    log = pool / "decisions.jsonl.gz"
    with gzip.open(log, "wb") as out:
        out.write(source.canonical({"policy_id": "C", "candidate_score": 99999, "winner": 0}) + b"\n")
        out.write(source.canonical(a) + b"\n")
    seal = tmp_path / "external-seal.json"
    seal.write_bytes(source.canonical({"files": {str(p): source.fingerprint(p) for p in (path, log)}}))
    spec = {"source_id": "synthetic", "audit_dir": str(tmp_path),
            "manifest": {"path": str(path), "sha256": source.sha(path.read_bytes())},
            "raw_seal": {"path": str(seal), "sha256": source.sha(seal.read_bytes())}}
    # 此fixture只测A过滤；真实producer验证另有实际73源码闭包只读检查。
    monkeypatch.setattr(source, "verify_natural_producer", lambda *args: None)
    monkeypatch.setattr(source, "verify_natural_integrity", lambda *args: None)
    monkeypatch.setattr(source, "verify_natural_baseline", lambda *args: None)
    rows, _ = source._natural(spec, {})
    assert len(rows) == 1 and rows[0]["origins"][0]["policy_role"] == "A"
    assert rows[0]["origins"][0]["source_line"] == 2


def test_fake_direct_parent_rejected(tmp_path):
    package = tmp_path / "package"; package.mkdir()
    (package / "generation.json").write_bytes(source.canonical({"parents": [{"identity": {"candidate_id": "real"}}]}))
    candidate = {"identity": {"candidate_id": "C"}, "path": str(package)}
    with pytest.raises(ValueError, match="真父"):
        probe.validate_reference_policy([{"candidate_id": "C", "basis": "generation_direct_parents", "reference_ids": ["fake"]}], [candidate])
    with pytest.raises(ValueError, match="本人"):
        probe.validate_reference_policy([{"candidate_id": "C", "basis": "explicit_batch_reference", "reference_ids": ["C"]}], [candidate])


@pytest.mark.parametrize("exploration,planned,limit,accepted", [
    (None, 16, 16, False), ({"purpose": "recording_and_coverage_exploration", "max_table_instances": 16}, 16, 16, True),
    ({"purpose": "recording_and_coverage_exploration", "max_table_instances": 16}, 32, 32, False),
    ({"purpose": "strength_admission", "max_table_instances": 16}, 16, 16, False),
    ({"purpose": "recording_and_coverage_exploration", "max_table_instances": 17}, 16, 16, False),
])
def test_unchanged_v2_only_explicit_small_exploration(exploration, planned, limit, accepted):
    proof = {"observed_behavior_difference": False}
    if accepted:
        probe.validate_development_scope(proof, exploration, planned, limit)
    else:
        with pytest.raises(ValueError):
            probe.validate_development_scope(proof, exploration, planned, limit)


def fixture_probe(tmp_path, monkeypatch, mode="ok", capture_bytes=1_000_000):
    rows = []
    for trigger in (0, 1):
        raw = record(); raw["window_key"]["trigger_seq"] = trigger
        rows.append(source.public_input(raw, origin()))
    panel = {"windows": rows, "window_count": 2}
    panel_file = tmp_path / "panel.json"; panel_file.write_bytes(source.canonical(panel))
    batch_file = tmp_path / "batch.json"; batch_file.write_bytes(b"synthetic generation batch")
    reference = [{"candidate_id": "C", "basis": "explicit_batch_reference", "reference_ids": ["A"]}]
    plan_file = tmp_path / "plan.json"
    plan_file.write_bytes(source.canonical({"schema": probe.PLAN_SCHEMA, "purpose": "development_behavior_diagnostic", "references": reference,
        "input_view_limits": {"max_single_view_bytes": capture_bytes, "max_total_view_bytes": 2_000_000, "max_views": 2}, "wall_clock_seconds": 60}))
    identity = {"view_schema_version": "vip-route-scoring-view/2", "graph_schema_version": "vip-route-action-graph/2",
                "normal_draw_hu_payment_semantics_version": "vip-normal-draw-hu-payment/1"}
    generation = SimpleNamespace(raw=batch_file.read_bytes(), max_operations=100,
                                 rule_config=RuleConfig("hangma-mvp-v10-public-counts", 1, False), route_limits=SimpleNamespace(), projection_limits=VipRouteProjectionLimits())
    materials = {}
    for name in ("A", "C"):
        path = tmp_path / name; path.mkdir()
        materials[str(path.resolve())] = {"identity": {**identity, "candidate_id": name}, "path": str(path), "source": "synthetic",
                                         "source_sha256": "a" * 64, "record_sha256": "b" * 64}
    monkeypatch.setattr(probe, "validate_public_input_panel", lambda p: {"panel": panel, "frozen_files": {str(panel_file): source.sha(panel_file.read_bytes())}})
    monkeypatch.setattr(probe.VipEohBatch, "read", lambda p: generation)
    def loader(path, batch, frozen, cost=None):
        if mode == "loadfail" and path.name == "C":
            raise OSError("synthetic public load failure")
        return deepcopy(materials[str(path)])
    monkeypatch.setattr(probe, "_load", loader)
    producer = {"src/hangma_bot/__init__.py": source.fingerprint(ROOT / "src/hangma_bot/__init__.py")}
    monkeypatch.setattr(probe, "source_manifest", lambda roots: deepcopy(producer))
    class Rules:
        def __init__(self, config): pass
        def analyze(self, observation, **kwargs):
            return SimpleNamespace(legal_candidates=[SimpleNamespace(action_key=k) for k in rows[0]["legal_action_keys"]])
    monkeypatch.setattr(probe, "HangmaRules", Rules)
    class View:
        def __init__(self, request): self.observation = request.observation
        def candidate_view(self):
            visible = self.observation
            public = {"seat": visible.seat, "dealer_seat": visible.dealer_seat, "phase": visible.phase,
                "my_hand": [t.code for t in visible.my_hand], "drawn_tile": visible.drawn_tile.code if visible.drawn_tile else None,
                "remaining_tile_count": visible.remaining_tile_count, "discards": [[t.code for t in row] for row in visible.discards],
                "melds": [[{"kind": m.kind, "tiles": [t.code for t in m.tiles], "from_seat": m.from_seat} for m in row] for row in visible.melds],
                "hand_counts": list(visible.hand_counts)}
            keys = rows[0]["legal_action_keys"]
            return {"schema_version": identity["view_schema_version"], "candidate_kind": probe.VIP_ROUTE_CANDIDATE_KIND,
                "graph_schema_version": identity["graph_schema_version"], "tile_order": list(probe.CANONICAL_TILE_ORDER), "visible_state": public,
                "binding": {**generation.rule_config.__dict__, "normal_draw_hu_payment_semantics_version": identity["normal_draw_hu_payment_semantics_version"],
                            "structure_semantics_version": probe.ROUTE_STRUCTURE_SCHEMA_VERSION, "executor_version": probe.EXECUTOR_VERSION},
                "limits": generation.projection_limits.__dict__,
                "workload": {"expanded_node_count": len(keys), "expanded_branch_count": 0, "waiting_draw_witness_count": 0, "target_distance_evaluation_count": 0},
                "actions": [{"action_key": k, "node_key": k} for k in keys],
                "nodes": [{"node_key": k, "children": [], "gap_kind": None, "expected_child_count": 0, "completed_child_count": 0} for k in keys]}
    monkeypatch.setattr(probe, "build_vip_route_scoring_view", lambda request, config, **kwargs: View(request))
    class Executor:
        def __init__(self, source, **kwargs): self.last_operation_count = 7
        def score_vip_route(self, view):
            if mode == "workload": raise probe.WorkloadExceeded("synthetic workload injection")
            trace = {"synthetic": True, "empty": None, "zero": 0}
            if mode == "sandbox_containers":
                # 模拟执行器公开输出中的计费容器，不访问其私有实现。
                class CountedDict(dict): pass
                class CountedList(list): pass
                trace["nested"] = CountedDict(values=CountedList([None, 0, False]), empty=CountedList())
            return SimpleNamespace(status="SCORED", entries=[SimpleNamespace(action_key=k, score=0.0, trace=trace) for k in rows[0]["legal_action_keys"]])
    monkeypatch.setattr(probe, "ActionValueExecutor", Executor)
    if mode in ("writefail", "closefail"):
        actual_open = probe.gzip.open
        class FailedWrite:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args):
                self.stream.close()
                if mode == "closefail": raise OSError("synthetic gzip footer failure")
            def write(self, raw):
                if mode == "writefail": raise OSError("synthetic full DTO write failure")
                return self.stream.write(raw)
            def flush(self): return self.stream.flush()
            def fileno(self): return self.stream.fileno()
        def opening(path, mode="rb", *args, **kwargs):
            stream = actual_open(path, mode, *args, **kwargs)
            return FailedWrite(stream) if str(path).endswith("views.jsonl.gz") and mode == "xb" else stream
        monkeypatch.setattr(probe.gzip, "open", opening)
    out = tmp_path / "run"
    result = probe.run_public_input_probe(panel_file, batch_file, plan_file, out, parent_paths=[tmp_path / "A"], candidate_paths=[tmp_path / "C"])
    return out, result, materials[str((tmp_path / "C").resolve())], generation, reference


def test_v2_full_denominator_capture_and_validator(tmp_path, monkeypatch):
    out, result, candidate, generation, refs = fixture_probe(tmp_path, monkeypatch)
    assert result["actual_score_calls"] == result["planned_package_windows"] == result["scored_package_windows"] == 4
    assert result["captured_input_windows"] == 2
    proof = probe.validate_public_input_probe(out / "summary.json", candidate, generation, reference_policy=refs)
    assert proof["preferred_changes"] == {"A": 0}
    assert proof["observed_behavior_difference"] is False


def test_workload_baseexception_retains_failed_cartesian(tmp_path, monkeypatch):
    out, result, *_ = fixture_probe(tmp_path, monkeypatch, mode="workload")
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert len(rows) == result["unfinished_package_windows"] == 4
    assert result["actual_score_calls"] == 4
    assert all(r["error"]["type"] == "WorkloadExceeded" and r["score_calls"] == 1 for r in rows)


def test_executor_container_trace_is_lossless_wire_json(tmp_path, monkeypatch):
    out, result, candidate, generation, refs = fixture_probe(tmp_path, monkeypatch, mode="sandbox_containers")
    assert result["scored_package_windows"] == 4
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert all(entry["trace"]["nested"] == {"values": [None, 0, False], "empty": []}
               for row in rows for entry in row["entries"])
    probe.validate_public_input_probe(out / "summary.json", candidate, generation, reference_policy=refs)


def test_full_dto_failure_prevents_scores_but_keeps_uncalled_denominator(tmp_path, monkeypatch):
    out, result, *_ = fixture_probe(tmp_path, monkeypatch, capture_bytes=1)
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert result["actual_score_calls"] == result["captured_input_windows"] == 0
    assert len(rows) == result["unfinished_package_windows"] == 4
    assert all(r["score_calls"] == 0 for r in rows)


def reseal(out, result):
    files = {p: source.fingerprint(Path(p)) for p in result["raw_files"]}
    seal = out / "RAW-FIRST-SEAL.json"; seal.write_bytes(source.canonical({"schema": "vip-eoh-probe-raw-first-seal/2", "files": files, "before_summary": True}) + b"\n")
    result.update(raw_files=files, raw_first_seal_sha256=source.sha(seal.read_bytes()))
    (out / "summary.json").write_bytes(source.canonical(result) + b"\n")


def test_missing_raw_row_rejected_even_if_summary_and_seal_rewritten(tmp_path, monkeypatch):
    out, result, candidate, generation, refs = fixture_probe(tmp_path, monkeypatch)
    path = out / "results.jsonl"; path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")
    reseal(out, result)
    with pytest.raises(ValueError, match="完整分母缺项"):
        probe.validate_public_input_probe(out / "summary.json", candidate, generation, reference_policy=refs)


def test_current_producer_drift_rejected(tmp_path, monkeypatch):
    out, result, candidate, generation, refs = fixture_probe(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, "source_manifest", lambda roots: {})
    with pytest.raises(ValueError, match="producer闭包漂移"):
        probe.validate_public_input_probe(out / "summary.json", candidate, generation, reference_policy=refs)


def test_trace_none_empty_zero_and_invalid_numbers():
    probe.validate_trace({"none": None, "empty": [], "zero": 0, "nested": {}})
    with pytest.raises(ValueError): probe.validate_trace({"score": float("nan")})


def test_load_failure_keeps_entire_uncalled_denominator(tmp_path, monkeypatch):
    out, result, *_ = fixture_probe(tmp_path, monkeypatch, mode="loadfail")
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert result["actual_score_calls"] == result["captured_input_windows"] == 0
    assert len(rows) == result["unfinished_package_windows"] == 4
    assert all(r["score_calls"] == 0 for r in rows)


def test_dto_io_failure_keeps_entire_uncalled_denominator(tmp_path, monkeypatch):
    out, result, *_ = fixture_probe(tmp_path, monkeypatch, mode="writefail")
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert result["actual_score_calls"] == result["captured_input_windows"] == 0
    assert result["cost"]["dto_write_attempts"] == 1
    assert len(rows) == result["unfinished_package_windows"] == 4


def test_full_legal_roots_missing_rejected(tmp_path, monkeypatch):
    out, result, candidate, generation, refs = fixture_probe(tmp_path, monkeypatch)
    path = out / "results.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["entries"].pop()
    path.write_bytes(b"".join(source.canonical(row) + b"\n" for row in rows))
    reseal(out, result)
    with pytest.raises(ValueError, match="全合法根"):
        probe.validate_public_input_probe(out / "summary.json", candidate, generation, reference_policy=refs)


def test_gzip_footer_failure_preserves_full_terminal_denominator(tmp_path, monkeypatch):
    out, result, candidate, generation, refs = fixture_probe(tmp_path, monkeypatch, mode="closefail")
    receipt = json.loads((out / "failed-full-denominator.json").read_bytes())
    assert receipt["planned_package_windows"] == len(receipt["rows"]) == 4
    assert result["actual_score_calls"] == 4
    assert result["status"] == "probe_unfinished_not_admitted"
    assert result["raw_output_errors"][0]["type"] == "OSError"
    with pytest.raises(ValueError, match="完整"):
        probe.validate_public_input_probe(out / "summary.json", candidate, generation, reference_policy=refs)
