"""通过公开生成、修复及装载入口保护原作者费用和唯一确定性补丁。"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline.vip_eoh_generate import (
    VIP_EOH_BATCH_SCHEMA, VipEohBatch, VipEohError, legacy_generation_tools,
    load_vip_parents, run_vip_eoh_generate, write_vip_seed_parent,
)
from hangma_bot.offline.vip_eoh_trace_repair import repair_structure_trace_source, repair_vip_trace_codec
from hangma_bot.policy.action_value import ActionScore
from hangma_bot.policy.route_vip_heuristic import VIP_ROUTE_HEURISTIC_SEED_SOURCE, VipRouteProjectionLimits


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def rewrite_record(path, edit):
    value = json.loads(path.read_bytes())
    edit(value)
    write_json(path, value)


@pytest.fixture
def materials(tmp_path):
    """假传输生成当前已加载提案；没有外部 API、真实作者或桌赛调用。"""

    batch_file = tmp_path / "batch.json"
    write_json(batch_file, {
        "schema": VIP_EOH_BATCH_SCHEMA, "batch_id": "synthetic-trace-author",
        "budgets": {"model_calls": 30, "input_tokens": 20_000_000,
                    "output_tokens": 200_000, "table_instances": 0, "wall_clock_seconds": 1000},
        "per_call": {"input_tokens": 400_000, "max_tokens": 4096, "timeout_seconds": 20},
        "max_operations": 100_000, "projection_limits": asdict(VipRouteProjectionLimits()),
        "rule_config": asdict(RuleConfig("hangma-mvp-v10-public-counts", 1, False)),
        "route_limits": asdict(ValueAnalysisLimits(max_expansions=8192)),
        "input_bound": {"kind": "verified_model_input_limit", "model": "synthetic-trace-model",
                        "max_input_tokens": 400_000, "evidence": {
                            "sources": ["synthetic-test-evidence"], "verified_on": "2026-10-01",
                            "interpretation": "仅假传输上限，不是实际调用"}},
        "sampling": {"temperature": None, "top_p": None, "seed": None},
    })
    source = VIP_ROUTE_HEURISTIC_SEED_SOURCE + '''

def make_support_credits(family, codes, active, weightedinventory, extra, credit):
    """代理向量：家族、原码集、是否加权、加权库存代理、加权额外代理、评分。"""
    proxyrows = []
    proxyrows.append((family, codes, active, weightedinventory, extra, credit))
    return proxyrows
'''
    mechanism = {"operator": "i1", "trigger": "人工格式测试", "changed_branches": "固定解释记录",
                 "expected_direction": "未测预期", "counterexample": "解释深度受限",
                 "parent_differences": [], "parameter_changes": []}
    text = "{人工格式测试}\n```json\n" + json.dumps(mechanism, ensure_ascii=False) + "\n```\n```python\n" + source + "\n```\n"
    tools = legacy_generation_tools()

    class Transport:
        model = "synthetic-trace-model"

        def complete(self, prompt):
            return tools.ModelReply(text=text, backend="api", origin=tools.ORIGIN_CAPTURED,
                provider="synthetic-test", model=self.model, model_requested=self.model,
                captured_at_utc="2026-10-01T00:00:00Z", finish_reason="stop", http_status=200,
                usage={"prompt_tokens": 1200, "completion_tokens": 900}, usage_source="response_body")

    package = tmp_path / "source-proposal"
    record = run_vip_eoh_generate(batch_file=batch_file, out_dir=package, operator="i1",
                                  backend="api", backend_factory=lambda *args, **kwargs: Transport())
    assert record["status"] == "loaded_not_admitted"
    failure = tmp_path / "original-failure.json"
    write_json(failure, {"status": "unfinished", "error": "ActionScore.trace 嵌套深度超过 3"})
    return batch_file, package, failure


def repair(materials, out):
    batch, package, failure = materials
    return repair_vip_trace_codec(batch_file=batch, source_package=package, out_dir=out,
                                 execution_evidence_files=[failure])


def test_real_trace_contract_rejects_nested_codes_and_accepts_lossless_flat_codes():
    """实际消费接缝复现深度错误；不能靠放宽全局限制通过。"""

    codes = ("5w", "8w", "5w")
    with pytest.raises(ValueError, match="嵌套深度"):
        ActionScore("discard:西", 1.0, {"structure_support": [("standard", codes, True, 7.5, 0.5, 1.0)]})
    entry = ActionScore("discard:西", 1.0, {"structure_support": [("standard", True, 7.5, 0.5, 1.0) + codes]})
    assert entry.trace["structure_support"][0][5:] == codes


def test_public_repair_preserves_origin_failure_and_author_ledger(materials, tmp_path):
    batch_file, original, failure = materials
    paths = [original / "candidate.py", original / "generation.json", failure,
             batch_file, batch_file.with_suffix(".vip-eoh-ledger.json")]
    before = {p: p.read_bytes() for p in paths}
    out = tmp_path / "repaired"
    record = repair(materials, out)
    author = json.loads(before[original / "generation.json"])
    assert record["artifact_role"] == record["backend"] == "trace_codec_repair"
    assert record["is_model_output"] is False and record["operator_actual"] is None
    assert record["parents"] == [] and record["behavior_change_credit"] is False
    assert record["admission"]["eligible"] is False and record["load"]["full_return_or_behavior_verified"] is False
    assert all(type(v) is int and v == 0 for v in record["billing"]["charged"].values())
    assert record["provenance"]["original_author_evidence"]["billing"] == author["billing"]
    assert author["billing"]["charged"]["model_calls"] == 1
    assert (out / "original-generation.json").read_bytes() == before[original / "generation.json"]
    assert (out / "original-candidate.py").read_bytes() == before[original / "candidate.py"]
    assert (out / "candidate.py").read_text() == repair_structure_trace_source(before[original / "candidate.py"].decode())
    assert (out / "execution-evidence/000-original-failure.json").read_bytes() == before[failure]
    assert all(p.read_bytes() == raw for p, raw in before.items())
    loaded = load_vip_parents([out], VipEohBatch.read(batch_file))[0]
    assert loaded["identity"]["candidate_id"] != author["identity"]["candidate_id"]
    emitted = run_vip_eoh_generate(batch_file=batch_file, out_dir=tmp_path / "followup",
                                  operator="m1", backend="emit", parent_paths=[out])
    assert emitted["status"] == "prompt_emitted" and emitted["billing"]["charged"]["model_calls"] == 0
    assert emitted["parents"][0]["artifact_role"] == "trace_codec_repair"


@pytest.mark.parametrize("edit", [
    lambda r: r.update(artifact_role="candidate_proposal"),
    lambda r: r.update(artifact_role="research_budget_rebind"),
    lambda r: r.update(is_model_output=True),
    lambda r: r.update(operator_actual="m1"),
    lambda r: r.update(parents=[{}]),
    lambda r: r["billing"]["charged"].update(model_calls=1),
    lambda r: r["billing"]["charged"].update(input_tokens=False),
    lambda r: r["admission"].update(eligible=True),
    lambda r: r["load"].update(full_return_or_behavior_verified=True),
    lambda r: r["provenance"].update(repair_id="arbitrary-source-change"),
    lambda r: r["provenance"].update(universal_score_equivalence_claim=True),
    lambda r: r["provenance"].update(trace_layout=["family", "codes"]),
    lambda r: r["provenance"]["original_author_evidence"]["billing"]["charged"].update(model_calls=0),
    lambda r: r["provenance"]["original_author_evidence"]["billing"]["charged"].update(model_calls=True),
    lambda r: r["provenance"]["source_identity"]["params"]["rule_config"].update(base_score=True),
    lambda r: r["provenance"]["target_identity"]["params"]["rule_config"].update(base_score=True),
])
def test_forged_model_credit_role_and_cost_are_rejected(materials, tmp_path, edit):
    out = tmp_path / "repaired"
    repair(materials, out)
    rewrite_record(out / "generation.json", edit)
    with pytest.raises(VipEohError):
        load_vip_parents([out], VipEohBatch.read(materials[0]))


@pytest.mark.parametrize("which", ["source_code", "source_record", "copied_code", "copied_record", "batch", "copied_batch", "failure", "copied_failure"])
def test_original_and_copied_bytes_cannot_drift(materials, tmp_path, which):
    batch, original, failure = materials
    out = tmp_path / "repaired"
    repair(materials, out)
    paths = {"source_code": original / "candidate.py", "source_record": original / "generation.json",
             "copied_code": out / "original-candidate.py", "copied_record": out / "original-generation.json",
             "batch": batch, "copied_batch": out / "batch.json", "failure": failure,
             "copied_failure": out / "execution-evidence/000-original-failure.json"}
    path = paths[which]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(VipEohError):
        load_vip_parents([out], VipEohBatch.read(batch))


def test_extra_scoring_edit_cannot_be_hidden_by_recomputing_identity(materials, tmp_path):
    out = tmp_path / "repaired"
    repair(materials, out)
    source = (out / "candidate.py").read_text().replace("20.0", "20.2", 1)
    (out / "candidate.py").write_text(source)
    identity = VipEohBatch.read(materials[0]).identity(source)
    def edit(record):
        record.update(identity=identity, source_sha256=identity["source_sha256"])
        record["provenance"]["target_identity"] = identity
    rewrite_record(out / "generation.json", edit)
    with pytest.raises(VipEohError):
        load_vip_parents([out], VipEohBatch.read(materials[0]))


def test_model_proposal_identity_does_not_allow_bool_as_integer(materials):
    rewrite_record(materials[1] / "generation.json",
                   lambda r: r["identity"]["params"]["rule_config"].update(base_score=True))
    with pytest.raises(VipEohError):
        load_vip_parents([materials[1]], VipEohBatch.read(materials[0]))


def test_double_repair_wrong_location_and_duplicate_site_rejected(materials, tmp_path):
    source = (materials[1] / "candidate.py").read_text()
    with pytest.raises(VipEohError):
        repair_structure_trace_source(repair_structure_trace_source(source))
    with pytest.raises(VipEohError):
        repair_structure_trace_source(source.replace("def make_support_credits", "def other_helper"))
    with pytest.raises(VipEohError):
        repair_structure_trace_source(source + source[source.index("def make_support_credits"):])
    repaired = tmp_path / "first"
    repair(materials, repaired)
    with pytest.raises(VipEohError):
        repair_vip_trace_codec(batch_file=materials[0], source_package=repaired, out_dir=tmp_path / "second")


def test_existing_directory_and_manual_seed_rejected(materials, tmp_path):
    out = tmp_path / "user-directory"
    out.mkdir()
    (out / "keep").write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        repair(materials, out)
    assert (out / "keep").read_bytes() == b"keep"
    manual = tmp_path / "manual"
    write_vip_seed_parent(manual, materials[0])
    with pytest.raises(VipEohError):
        repair_vip_trace_codec(batch_file=materials[0], source_package=manual, out_dir=tmp_path / "bad-manual")
