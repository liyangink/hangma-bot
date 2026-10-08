"""验证修复隔离及真实三白接缝；不以桌赛得分增强作为通过条件。"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

from hangma_bot.offline.vip_scoring_repair import scoring_repair_phases
from hangma_bot.policy.action_value_executor import ActionValueExecutor, static_check

ROOT = Path(__file__).resolve().parents[3]
FAULT = ROOT / "tests/fixtures/vip_scoring_repair/fault_g37.py"


def definitions(source):
    tree = ast.parse(source)
    constants = {n.targets[0].id: ast.dump(n.value, include_attributes=False)
                 for n in tree.body if isinstance(n, ast.Assign)}
    functions = {n.name: ast.dump(n, include_attributes=False)
                 for n in tree.body if isinstance(n, ast.FunctionDef)}
    return constants, functions


def test_fix_does_not_change_parameters_payment_or_unrelated_functions():
    """阻止把无关进化夹进修复，包含支付聚合及当前Hu机会费。"""
    source = FAULT.read_text()
    constants, functions = definitions(source)
    for role, repaired in scoring_repair_phases(source).items():
        new_constants, new_functions = definitions(repaired)
        assert new_constants == constants
        assert {k: v for k, v in new_functions.items() if k in functions and k not in ("routewait", "score_actions")} == {
            k: v for k, v in functions.items() if k not in ("routewait", "score_actions")}
        static_check(repaired)


def test_repair_rejects_unknown_and_already_repaired_source():
    source = FAULT.read_text()
    with pytest.raises(ValueError, match="只适用于"):
        scoring_repair_phases(source + "\n")
    with pytest.raises(ValueError, match="只适用于"):
        scoring_repair_phases(scoring_repair_phases(source)["RF1"])


def test_real_qualified_hu_window_transmits_tie_quality_without_raising_continue():
    """真实原输入上，F2不涨主报价；RF1细分弃牌但保留Hu/继续门。"""
    path = ROOT / "review/vip-route-2026-09-30/evidence/t226-minimal-scoring-repair-1/regression_probe.py"
    spec = importlib.util.spec_from_file_location("repair_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    view, fixture = module.build_view()
    before = view.candidate_view()
    scored = {}
    for phase, source in scoring_repair_phases(FAULT.read_text()).items():
        executor = ActionValueExecutor(source, max_operations=4_800_000, max_local_collection_size=8192)
        batch = executor.score_vip_route(view)
        assert batch.status == "SCORED"
        scored[phase] = {e.action_key: e for e in batch.entries}
        assert sorted(scored[phase]) == fixture["legal_action_keys"]
        assert view.candidate_view() == before
    base, shadow, fixed = scored["F1"], scored["F2"], scored["RF1"]
    assert {k: e.score.hex() for k, e in base.items()} == {k: e.score.hex() for k, e in shadow.items()}
    assert base["discard:3b"].score.hex() == base["discard:7b"].score.hex()
    qa, qb = dict(shadow["discard:3b"].trace)["repair_shadow"], dict(shadow["discard:7b"].trace)["repair_shadow"]
    assert qa != qb
    assert (qa > qb) == (fixed["discard:3b"].score > fixed["discard:7b"].score)
    assert max(e.score for k, e in fixed.items() if k != "hu").hex() == max(e.score for k, e in shadow.items() if k != "hu").hex()
    assert fixed["hu"].score.hex() == base["hu"].score.hex()
    for key, entry in shadow.items():
        for other, peer in shadow.items():
            if entry.score < peer.score:
                assert fixed[key].score < fixed[other].score


def test_repair_package_is_honest_and_cannot_impersonate_model_proposal(tmp_path):
    """合成包只用于装载谱系测试；零模型、零评分，不授真实发布。"""
    from hangma_bot.offline.vip_eoh_generate import (
        VipEohBatch, VipEohError, load_vip_parents,
        VIP_EOH_BATCH_SCHEMA, VIP_EOH_GENERATION_SCHEMA, VIP_EOH_PROFILE,
    )
    from hangma_bot.offline.vip_scoring_repair import write_scoring_repair_package
    from hangma_bot.policy.route_heuristic_view import VIP_ROUTE_CANDIDATE_KIND
    fixture = json.loads((ROOT / "tests/fixtures/vip_scoring_repair/mature_three_white.json").read_text())
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps({
        "schema": VIP_EOH_BATCH_SCHEMA, "batch_id": "synthetic-scoring-repair",
        "budgets": {"model_calls": 0, "input_tokens": 0, "output_tokens": 0,
                    "table_instances": 0, "wall_clock_seconds": 100},
        "per_call": {"input_tokens": 400000, "max_tokens": 4096, "timeout_seconds": 20},
        "max_operations": 4800000, "projection_limits": fixture["projection_limits"],
        "route_limits": fixture["route_limits"], "rule_config": fixture["rule_config"],
        "sampling": {"temperature": None, "top_p": None, "seed": None},
        "input_bound": {"kind": "verified_model_input_limit", "model": "synthetic-no-call",
                        "max_input_tokens": 400000,
                        "evidence": {"sources": ["synthetic-unit-fixture"], "verified_on": "2026-10-08",
                                     "interpretation": "仅构造参数，不进行模型调用"}},
    }))
    batch = VipEohBatch.read(batch_file)
    parent = tmp_path / "synthetic-parent"
    parent.mkdir()
    source = FAULT.read_text()
    identity = batch.identity(source)
    (parent / "candidate.py").write_text(source)
    (parent / "generation.json").write_text(json.dumps({
        "schema": VIP_EOH_GENERATION_SCHEMA, "profile": VIP_EOH_PROFILE,
        "candidate_kind": VIP_ROUTE_CANDIDATE_KIND, "status": "loaded_not_admitted",
        "artifact_role": "candidate_proposal", "backend": "synthetic-unit-fixture",
        "is_model_output": False, "identity": identity, "source_sha256": identity["source_sha256"],
        "identity_stable": True, "load": {"ok": True}, "admission": {"admitted": False},
    }))
    output = tmp_path / "repair"
    record = write_scoring_repair_package(parent_path=parent, batch_file=batch_file, output=output)
    assert record["new_model_calls"] == 0 and record["is_model_output"] is False
    assert load_vip_parents([output], batch)[0]["artifact_role"] == "scoring_defect_repair"
    changed = dict(record, artifact_role="candidate_proposal")
    (output / "generation.json").write_text(json.dumps(changed))
    with pytest.raises(VipEohError, match="伪装"):
        load_vip_parents([output], batch)
    (output / "generation.json").write_text(json.dumps(record))
    (output / "candidate.py").write_text((output / "candidate.py").read_text() + "\n")
    with pytest.raises(VipEohError):
        load_vip_parents([output], batch)
