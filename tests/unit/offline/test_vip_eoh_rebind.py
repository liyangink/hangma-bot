"""研究额度重绑定只用公开生成/装载入口及假传输，不评分或运行桌赛。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import pytest

from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline.vip_eoh_generate import (
    VIP_EOH_BATCH_SCHEMA, VipEohBatch, VipEohError, legacy_generation_tools,
    load_vip_parents, run_vip_eoh_generate, write_vip_seed_parent,
)
from hangma_bot.offline.vip_eoh_rebind import rebind_vip_research_budget
from hangma_bot.policy.route_vip_heuristic import VIP_ROUTE_HEURISTIC_SEED_SOURCE, VipRouteProjectionLimits


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def rewrite_record(package, edit):
    path = package / "generation.json"
    record = json.loads(path.read_bytes())
    edit(record)
    write_json(path, record)


@pytest.fixture
def materials(tmp_path):
    """公开生成入口产假模型提案，其作者费用用于保留与不重计的检验。"""

    source_batch = tmp_path / "source-batch.json"
    data = {
        "schema": VIP_EOH_BATCH_SCHEMA, "batch_id": "synthetic-author-batch",
        "budgets": {"model_calls": 30, "input_tokens": 20_000_000,
                    "output_tokens": 200_000, "table_instances": 0, "wall_clock_seconds": 1000},
        "per_call": {"input_tokens": 400_000, "max_tokens": 4096, "timeout_seconds": 20},
        "max_operations": 100_000, "projection_limits": asdict(VipRouteProjectionLimits()),
        "rule_config": asdict(RuleConfig("hangma-mvp-v10-public-counts", 1, False)),
        "route_limits": asdict(ValueAnalysisLimits(max_expansions=8192)),
        "input_bound": {"kind": "verified_model_input_limit", "model": "synthetic-rebind-model",
                        "max_input_tokens": 400_000, "evidence": {
                            "sources": ["synthetic-test-evidence"], "verified_on": "2026-09-30",
                            "interpretation": "仅假传输人工上限，不是实际模型调用"}},
        "sampling": {"temperature": None, "top_p": None, "seed": None},
    }
    write_json(source_batch, data)
    source = VIP_ROUTE_HEURISTIC_SEED_SOURCE.replace("20.0", "20.1", 1)
    mechanism = {"operator": "i1", "trigger": "人工故障测试", "changed_branches": "全合法根统一评分",
                 "expected_direction": "未测预期", "counterexample": "可能牺牲普通出口",
                 "parent_differences": [], "parameter_changes": []}
    text = "{人工格式测试机制}\n```json\n" + json.dumps(mechanism, ensure_ascii=False) + "\n```\n```python\n" + source + "\n```\n"
    tools = legacy_generation_tools()

    class Transport:
        model = "synthetic-rebind-model"

        def complete(self, prompt):
            return tools.ModelReply(
                text=text, backend="api", origin=tools.ORIGIN_CAPTURED, provider="synthetic-test",
                model="synthetic-rebind-model", model_requested="synthetic-rebind-model",
                captured_at_utc="2026-09-30T00:00:00Z", finish_reason="stop", http_status=200,
                usage={"prompt_tokens": 1200, "completion_tokens": 900}, usage_source="response_body",
            )

    source_package = tmp_path / "source-proposal"
    record = run_vip_eoh_generate(batch_file=source_batch, out_dir=source_package, operator="i1",
                                  backend="api", backend_factory=lambda *args, **kwargs: Transport())
    assert record["status"] == "loaded_not_admitted"
    target_batch = tmp_path / "target-batch.json"
    target_data = dict(data, batch_id="synthetic-research-300k", max_operations=300_000)
    write_json(target_batch, target_data)
    evidence = tmp_path / "original-execution-failure.json"
    evidence.write_bytes(b'{"status":"unfinished","error":{"type":"WorkloadExceeded"},"max_operations":100000}\n')
    return source_batch, source_package, target_batch, evidence


def bind(materials, out):
    source_batch, source_package, target_batch, evidence = materials
    return rebind_vip_research_budget(source_batch_file=source_batch, source_package=source_package,
        target_batch_file=target_batch, out_dir=out, execution_evidence_files=[evidence])


def test_public_rebind_preserves_original_bytes_cost_failure_and_load_gate(materials, tmp_path):
    source_batch, source_package, target_batch, evidence = materials
    original_bytes = (source_package / "generation.json").read_bytes()
    original_source = (source_package / "candidate.py").read_bytes()
    author = json.loads(original_bytes)
    ledger_path = source_batch.with_suffix(".vip-eoh-ledger.json")
    ledger_bytes = ledger_path.read_bytes()
    out = tmp_path / "rebound"
    record = bind(materials, out)
    assert record["artifact_role"] == record["backend"] == "research_budget_rebind"
    assert record["status"] == "loaded_not_admitted" and record["identity_stable"] is True
    assert record["identity"]["params"]["max_operations"] == 300_000
    assert record["identity"]["candidate_id"] != author["identity"]["candidate_id"]
    assert record["billing"]["charged"] == dict.fromkeys(record["billing"]["charged"], 0)
    assert record["provenance"]["original_author_evidence"]["billing"] == author["billing"]
    assert author["billing"]["charged"]["model_calls"] == 1
    assert author["billing"]["charged"]["input_tokens"] == 1200
    assert record["provenance"]["original_author_evidence"]["model_identity"] == author["model_identity"]
    assert record["operator_actual"] is None and record["is_model_output"] is False
    assert record["admission"]["eligible"] is False and record["behavior_change_credit"] is False
    assert record["provenance"]["source_batch_sha256"] == hashlib.sha256(source_batch.read_bytes()).hexdigest()
    assert (out / "original-generation.json").read_bytes() == original_bytes
    assert (out / "candidate.py").read_bytes() == (out / "original-candidate.py").read_bytes() == original_source
    assert (out / "original-source-raw.py").read_bytes() == (source_package / "source-raw.py").read_bytes()
    assert (out / "source-batch.json").read_bytes() == source_batch.read_bytes()
    assert (out / "execution-evidence/000-original-execution-failure.json").read_bytes() == evidence.read_bytes()
    assert (source_package / "generation.json").read_bytes() == original_bytes
    assert ledger_path.read_bytes() == ledger_bytes
    assert not target_batch.with_suffix(".vip-eoh-ledger.json").exists()
    assert load_vip_parents([out], VipEohBatch.read(target_batch))[0]["artifact_role"] == "research_budget_rebind"
    with pytest.raises(VipEohError):
        load_vip_parents([out], VipEohBatch.read(source_batch))


def test_source_execution_batch_can_differ_from_original_author_batch(materials, tmp_path):
    source_batch, source_package, _, evidence = materials
    execution_data = json.loads(source_batch.read_bytes())
    execution_data.update(batch_id="different-execution-label")
    execution_data["budgets"]["model_calls"] = 1
    execution = tmp_path / "source-execution.json"
    write_json(execution, execution_data)
    target = tmp_path / "target-execution.json"
    write_json(target, dict(execution_data, batch_id="new-research-label", max_operations=300_000))
    out = tmp_path / "different-author-and-execution"
    record = rebind_vip_research_budget(source_batch_file=execution, source_package=source_package,
                                      target_batch_file=target, out_dir=out, execution_evidence_files=[evidence])
    author = json.loads((source_package / "generation.json").read_bytes())
    assert record["provenance"]["source_batch_sha256"] != author["batch_sha256"]
    assert record["provenance"]["original_author_evidence"]["batch_sha256"] == author["batch_sha256"]
    assert (out / "original-author-batch.json").read_bytes() == source_batch.read_bytes()
    assert load_vip_parents([out], VipEohBatch.read(target))


@pytest.mark.parametrize("operations", [True, False, 100_000, 99_999, 0, -1, 300_000.0])
def test_bool_noninteger_and_nonincreasing_operations_rejected(materials, tmp_path, operations):
    target = materials[2]
    data = json.loads(target.read_bytes())
    data["max_operations"] = operations
    write_json(target, data)
    with pytest.raises(VipEohError):
        bind(materials, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("field,key,value", [
    ("rule_config", "base_score", 2), ("rule_config", "you_cai_bi_kao", True),
    ("route_limits", "max_expansions", 8193), ("projection_limits", "max_nodes", 4095),
    ("sampling", "temperature", 0.1), ("budgets", "model_calls", 31),
    ("per_call", "max_tokens", 4097), ("input_bound", "max_input_tokens", 400001),
])
def test_only_operation_increase_and_batch_label_can_change(materials, tmp_path, field, key, value):
    target = materials[2]
    data = json.loads(target.read_bytes())
    data[field][key] = value
    write_json(target, data)
    with pytest.raises(VipEohError, match="配置必须完全相同"):
        bind(materials, tmp_path / "rejected")


@pytest.mark.parametrize("target", ["source_code", "source_record", "copied_record", "source_batch", "failure_evidence", "author_batch"])
def test_live_and_copied_provenance_drift_rejected(materials, tmp_path, target):
    source_batch, source_package, target_batch, evidence = materials
    out = tmp_path / "rebound"
    bind(materials, out)
    paths = {"source_code": source_package / "candidate.py", "source_record": source_package / "generation.json",
             "copied_record": out / "original-generation.json", "source_batch": source_batch,
             "failure_evidence": evidence, "author_batch": source_package / "batch.json"}
    path = paths[target]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(VipEohError):
        load_vip_parents([out], VipEohBatch.read(target_batch))


@pytest.mark.parametrize("edit", [
    lambda record: record.update(artifact_role="candidate_proposal"),
    lambda record: record.update(backend="api"),
    lambda record: record.update(operator_actual="m1"),
    lambda record: record.update(is_model_output=True),
    lambda record: record["provenance"]["original_author_evidence"]["billing"]["charged"].update(model_calls=0),
    lambda record: record["billing"]["charged"].update(model_calls=1),
    lambda record: record["provenance"].update(source_identity={}),
])
def test_forged_role_author_cost_and_identity_cannot_bypass_origin_gate(materials, tmp_path, edit):
    out = tmp_path / "rebound"
    bind(materials, out)
    rewrite_record(out, edit)
    with pytest.raises(VipEohError):
        load_vip_parents([out], VipEohBatch.read(materials[2]))


def test_directory_cover_and_nonproposal_sources_rejected(materials, tmp_path):
    out = tmp_path / "existing"
    out.mkdir()
    (out / "user-file").write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        bind(materials, out)
    assert (out / "user-file").read_bytes() == b"keep"
    manual = tmp_path / "manual"
    write_vip_seed_parent(manual, materials[0])
    with pytest.raises(VipEohError, match="人工种子"):
        rebind_vip_research_budget(source_batch_file=materials[0], source_package=manual,
                                  target_batch_file=materials[2], out_dir=tmp_path / "manual-rebind")
    rewrite_record(materials[1], lambda record: record.update(status="failed"))
    with pytest.raises(VipEohError):
        bind(materials, tmp_path / "failed-source")


def test_recursive_origin_chain_and_cycle_are_checked(materials, tmp_path):
    first = tmp_path / "first"
    bind(materials, first)
    final_batch = tmp_path / "500k.json"
    data = json.loads(materials[2].read_bytes())
    data.update(max_operations=500_000, batch_id="synthetic-research-500k")
    write_json(final_batch, data)
    second = tmp_path / "second"
    rebind_vip_research_budget(source_batch_file=materials[2], source_package=first,
                              target_batch_file=final_batch, out_dir=second)
    assert load_vip_parents([second], VipEohBatch.read(final_batch))
    rewrite_record(first, lambda record: record["provenance"].update(original_package_path=str(first)))
    with pytest.raises(VipEohError, match="循环"):
        load_vip_parents([first], VipEohBatch.read(materials[2]))
    with pytest.raises(VipEohError):
        load_vip_parents([second], VipEohBatch.read(final_batch))


def test_followup_author_batch_accepts_same_execution_identity_without_rewriting_origin(materials, tmp_path):
    """后代作者预算不是父代评分身份；公开emit也可使用已重绑定的父包。"""

    source_batch, source_package, target_batch, _ = materials
    out = tmp_path / "rebound"
    bind(materials, out)
    originals = {path: path.read_bytes() for path in (
        target_batch, out / "generation.json", out / "batch.json", source_package / "generation.json",
        source_batch.with_suffix(".vip-eoh-ledger.json"))}
    followup = tmp_path / "followup-author-batch.json"
    data = json.loads(target_batch.read_bytes())
    data["batch_id"] = "different-followup-author-label"
    data["budgets"].update(model_calls=1, input_tokens=30_000_000, output_tokens=300_000, wall_clock_seconds=2000)
    data["per_call"].update(input_tokens=800_000, max_tokens=8192, timeout_seconds=30)
    data["input_bound"].update(model="different-followup-model", max_input_tokens=800_000)
    data["sampling"]["temperature"] = 0.2
    write_json(followup, data)
    batch = VipEohBatch.read(followup)
    material = load_vip_parents([out], batch)[0]
    assert material["identity"] == json.loads((out / "generation.json").read_bytes())["identity"]
    emitted = run_vip_eoh_generate(batch_file=followup, out_dir=tmp_path / "followup-prompt",
                                   operator="m1", backend="emit", parent_paths=[out])
    assert emitted["status"] == "prompt_emitted"
    assert emitted["parents"][0]["identity"] == material["identity"]
    assert emitted["billing"]["charged"]["model_calls"] == 0
    assert all(path.read_bytes() == original for path, original in originals.items())


@pytest.mark.parametrize("edit", [
    lambda record: record["load"].update(method="full_table_completion"),
    lambda record: record["load"].update(gates_run=["complete_table"]),
    lambda record: record["load"].update(full_return_or_behavior_verified=True),
    lambda record: record["admission"].update(gates_run=["complete_table"]),
])
def test_fake_completion_claims_rejected(materials, tmp_path, edit):
    out = tmp_path / "rebound"
    bind(materials, out)
    rewrite_record(out, edit)
    with pytest.raises(VipEohError):
        load_vip_parents([out], VipEohBatch.read(materials[2]))


def test_original_target_identity_cannot_diverge_from_record(materials, tmp_path):
    """原target400k与record/caller300k不得各自比source提高后就混为同身份。"""

    out = tmp_path / "rebound"
    bind(materials, out)
    caller = tmp_path / "caller300k.json"
    caller.write_bytes(materials[2].read_bytes())
    data = json.loads(materials[2].read_bytes())
    data.update(max_operations=400_000, batch_id="forged-original-target-400k")
    write_json(materials[2], data)
    target_bytes = materials[2].read_bytes()
    (out / "batch.json").write_bytes(target_bytes)

    def edit(record):
        record["batch_id"] = data["batch_id"]
        record["batch_sha256"] = hashlib.sha256(target_bytes).hexdigest()
        record["provenance"]["target_batch_sha256"] = record["batch_sha256"]

    rewrite_record(out, edit)
    caller_batch = VipEohBatch.read(caller)
    record = json.loads((out / "generation.json").read_bytes())
    assert caller_batch.identity((out / "candidate.py").read_text()) == record["identity"]
    with pytest.raises(VipEohError, match="执行批次"):
        load_vip_parents([out], caller_batch)


@pytest.mark.parametrize("field,key,value", [
    ("max_operations", None, 100_000), ("max_operations", None, 400_000),
    ("rule_config", "base_score", 2), ("route_limits", "max_expansions", 8193),
    ("projection_limits", "max_nodes", 4095),
])
def test_followup_caller_different_scoring_parameters_still_rejected(materials, tmp_path, field, key, value):
    out = tmp_path / "rebound"
    bind(materials, out)
    data = json.loads(materials[2].read_bytes())
    if key is None:
        data[field] = value
    else:
        data[field][key] = value
    caller = tmp_path / "different-scoring.json"
    write_json(caller, data)
    with pytest.raises(VipEohError, match="逐字节身份"):
        load_vip_parents([out], VipEohBatch.read(caller))
