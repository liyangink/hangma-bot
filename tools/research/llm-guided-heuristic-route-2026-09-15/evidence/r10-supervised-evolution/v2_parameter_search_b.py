"""可信V2联合参数搜索阶段B：8配置补H/M各8根，累计每层16根后留3。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import concurrent.futures
import json
import multiprocessing
from pathlib import Path

import confirmation_execution_identity as guard
import sitin_archive as archive
import sitin_natural_panel as natural
import strong_seed_batch as batch
import v2_parameter_policy as parameter
import v2_parameter_search as phase_a
import v2_parameter_wiring as wiring
from confirmation_execution_probe import execute_arm
from hangma_bot.hangma.interface import ValueAnalysisLimits


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-b-20260920')
A_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-a-20260920')
A_FREEZE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-a-20260920/phase-b-freeze.json')
A_SAMPLES = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-a-20260920/phase-a-samples.json')
DESIGN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/parameter-search-design-20260920.json')
CONTRACT = batch.ROUTE / "contracts/group-dev-v1.json"
ROOTS = tuple(range(9, 17))
MIXES = ("H", "M")
SEATS = tuple(range(4))


def _selected_rows():
    """只接受阶段A机器冻结的8个配置，保持其选留顺序。"""
    freeze = batch.read(A_FREEZE)
    ids = freeze["selected_configuration_ids"]
    if len(ids) != 8 or freeze["new_root_indices"] != list(ROOTS):
        raise ValueError("阶段B冻结清单不符")
    rows = {row["config_id"]: row for row in phase_a._configurations()}
    if any(config_id not in rows for config_id in ids):
        raise ValueError("阶段B含未知配置")
    return [rows[config_id] for config_id in ids]


def _source_paths():
    return [Path(__file__), Path(phase_a.__file__), Path(parameter.__file__),
            Path(wiring.__file__), Path(archive.__file__), DESIGN, CONTRACT,
            A_FREEZE, A_SAMPLES]


def prepare():
    """冻结阶段B的8配置、16个新根和1,152桌预算。"""
    if OUT.exists():
        raise ValueError("阶段B目录已存在，拒绝覆盖")
    if batch.read(_project_file(_PROJECT_ROOT, A_OUT / "summary.json"))["status"] != "COMPLETE_PHASE_A_DEVELOPMENT_RANKING":
        raise ValueError("阶段A尚未完整结案")
    rows = _selected_rows()
    OUT.mkdir()
    auth = batch.unified_document(
        batch_label=OUT.name, authorization_id="r10-v2-parameter-search-b",
        accounts={"tables_full": 1152}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    auth.update({
        "issuance_basis": "阶段A机器选留完成，按预登记24→8→3继续追加共同新根",
        "scope": "阶段B开发筛选；8配置、H/M各新增8根、4座位、2桌；累计每层16根后留3；不确认不发布",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    natural.require_authorization(auth)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    runtime = guard.capture(source_paths=_source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "v2-joint-parameter-search-b/1",
        "created_at_utc": batch.search.utc_now(), "runtime": runtime,
        "phase_a_freeze": str(A_FREEZE),
        "phase_a_freeze_sha256": batch.digest(A_FREEZE.read_bytes()),
        "phase_a_samples": str(A_SAMPLES),
        "phase_a_samples_sha256": batch.digest(A_SAMPLES.read_bytes()),
        "design": str(DESIGN), "design_sha256": batch.digest(DESIGN.read_bytes()),
        "contract": str(CONTRACT), "contract_sha256": batch.digest(CONTRACT.read_bytes()),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": batch.read(_project_file(_PROJECT_ROOT, A_OUT / "manifest.json"))["panel_seed"],
        "opponents": list(MIXES), "new_root_indices": list(ROOTS),
        "focal_seats": list(SEATS), "tables_per_arm": 2,
        "configuration_ids": [row["config_id"] for row in rows],
        "configuration_policy_sha256": {
            row["config_id"]: row["policy_weights_sha256"] for row in rows},
        "baseline_policy_id": "ComparableHeuristicPolicyV2",
        "candidate_tables": 1024, "baseline_tables": 128,
        "max_full_tables": 1152, "workers": 4,
        "selection": {
            "fitness": "阶段A+B累计H/M等权根级保守差d_low均值",
            "keep": 3,
            "tie_break": "相对默认权重六维归一化L1距离升序，再config_id升序",
            "meaning": "预算分配，不是显著性检验",
        },
        "model_calls": 0, "confirmation_roots": 0,
        "selection_eligible": True, "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 1152}).save()
    print("prepared phase B: 8 configs, 16 new roots total, 1152 tables", flush=True)


def _verify_inputs(plan):
    guard.verify(plan["runtime"])
    for key, sha_key in (("phase_a_freeze", "phase_a_freeze_sha256"),
                         ("phase_a_samples", "phase_a_samples_sha256"),
                         ("design", "design_sha256"),
                         ("contract", "contract_sha256")):
        if batch.digest(Path(plan[key]).read_bytes()) != plan[sha_key]:
            raise ValueError(key + " 漂移")
    rows = _selected_rows()
    if [row["config_id"] for row in rows] != plan["configuration_ids"]:
        raise ValueError("阶段B配置顺序漂移")
    if {row["config_id"]: row["policy_weights_sha256"] for row in rows} != plan[
            "configuration_policy_sha256"]:
        raise ValueError("阶段B运行身份漂移")


def _plans(contract, mix, root, seat, plan):
    return natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=plan["panel_seed"])


def _run_baseline_all():
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    contract = batch.read(CONTRACT)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 1152})
    versions = natural.stage.contract_versions_block(contract)
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = _plans(contract, mix, root, seat, plan)
                label = f"b-baseline-{mix}-r{root:02d}-s{seat}"
                expected = {"step_id": label, "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "baseline", "candidate_id": plan["baseline_policy_id"]}
                checked = execute_arm(
                    _project_file(_PROJECT_ROOT, OUT / "baseline" / label), expected=expected, ledger=ledger,
                    runner=lambda plans=plans, mix=mix: natural.run_arm_stage(
                        arm="baseline", plans=plans, candidate_scorer=None,
                        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
                        versions_block=versions, step_limit=contract["stop"]["step_limit"],
                        value_limits=ValueAnalysisLimits()),
                    verifier=lambda raw, plans=plans: wiring._verify_stage(
                        raw, plans, contract, plan["baseline_policy_id"], None))
                count += checked["tables"]
    _verify_inputs(plan)
    return {"kind": "baseline", "tables": count}


def _run_configuration(config_id):
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    row = next(item for item in _selected_rows() if item["config_id"] == config_id)
    weights = parameter.weights_from_record(row["weights"])
    policy_id = parameter.PREFIX + row["policy_weights_sha256"]
    contract = batch.read(CONTRACT)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 1152})
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = _plans(contract, mix, root, seat, plan)
                label = f"b-{config_id}-{mix}-r{root:02d}-s{seat}"
                expected = {"step_id": label, "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "candidate", "candidate_id": policy_id}
                checked = execute_arm(
                    _project_file(_PROJECT_ROOT, OUT / "candidates" / config_id / label),
                    expected=expected, ledger=ledger,
                    runner=lambda plans=plans, mix=mix: wiring._run_configured_stage(
                        plans, mix, contract, weights),
                    verifier=lambda raw, plans=plans: wiring._verify_stage(
                        raw, plans, contract, policy_id, row["policy_weights_sha256"]))
                count += checked["tables"]
    _verify_inputs(plan)
    return {"kind": "candidate", "config_id": config_id, "tables": count}


def run_b():
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    context = multiprocessing.get_context("spawn")
    completed = []
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=plan["workers"], mp_context=context) as pool:
        futures = [pool.submit(_run_baseline_all)]
        futures.extend(pool.submit(_run_configuration, config_id)
                       for config_id in plan["configuration_ids"])
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            completed.append(result)
            print(result.get("config_id", "baseline"), "complete", result["tables"], flush=True)
    if len(completed) != 9:
        raise ValueError("阶段B工作单元未全部完成")
    summarize_b()


def _root_digest(plan, mix, root, contract):
    seats = {}
    for seat in SEATS:
        plans = _plans(contract, mix, root, seat, plan)
        seats[str(seat)] = {"table_ids": [item.table_id for item in plans],
                            "table_seeds": [item.seed for item in plans]}
    return wiring._digest({"generator": "v2-joint-parameter-search/1",
        "panel_seed": plan["panel_seed"], "opponent_mix": mix,
        "root_index": root, "seats": seats})


def summarize_b():
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 1152})
    if ledger.spent("tables_full") != 1152:
        raise ValueError("阶段B费用未完整结算")
    contract = batch.read(CONTRACT)
    design = batch.read(DESIGN)
    old_by_candidate = {}
    for sample in batch.read(A_SAMPLES):
        old_by_candidate.setdefault(sample["candidate_id"], []).append(sample)
    new_samples, rankings = [], []
    for row in _selected_rows():
        config_id = row["config_id"]
        candidate_id = parameter.PREFIX + row["policy_weights_sha256"]
        current = []
        for mix in MIXES:
            for root in ROOTS:
                root_id = f"v2pb-{mix}-{plan['panel_seed']}-root{root:02d}"
                digest = _root_digest(plan, mix, root, contract)
                for seat in SEATS:
                    base_label = f"b-baseline-{mix}-r{root:02d}-s{seat}"
                    cand_label = f"b-{config_id}-{mix}-r{root:02d}-s{seat}"
                    baseline = batch.read(_project_file(_PROJECT_ROOT, OUT / "baseline" / base_label / "result.json"))["raw"]
                    candidate = batch.read(_project_file(_PROJECT_ROOT, OUT / "candidates" / config_id /
                                           cand_label / "result.json"))["raw"]
                    sample = {"schema": natural.NATURAL_SAMPLE_SCHEMA,
                        "source_root_id": root_id, "root_content_digest": digest,
                        "root_index": root, "root_usage": "development_core",
                        "candidate_id": candidate_id, "opponent_mix": mix,
                        "scenario": "normal", "focal_anchor_seat": seat,
                        "root_expected": {"seats": 4,
                            "arms": ["baseline", "candidate"], "tables_per_arm": 2},
                        "arms": {"baseline": phase_a._arm_view(
                                    baseline, plan["baseline_policy_id"]),
                                 "candidate": phase_a._arm_view(candidate, candidate_id)},
                        "completeness": "complete", "invalid_reasons": [],
                        "cost": {"budget_units": 4,
                            "elapsed_ms": baseline["elapsed_ms"] + candidate["elapsed_ms"]}}
                    current.append(sample); new_samples.append(sample)
        cumulative = old_by_candidate[candidate_id] + current
        stats = archive.paired_stage_statistics(cumulative, min_roots=16)
        if stats["invalid_count"] or stats["uncomputable_count"]:
            raise ValueError("阶段B累计样本无效：" + config_id)
        normal = stats["by_candidate"][candidate_id]["panels"]["normal"]
        panels = normal["panels"]
        if any(panel["status"] != "ok" or panel["n_roots"] != 16
               or not panel["manifest_complete"] for panel in panels.values()):
            raise ValueError("阶段B累计根清单不完整：" + config_id)
        rankings.append({"config_id": config_id, "candidate_id": candidate_id,
            "policy_weights_sha256": row["policy_weights_sha256"],
            "fitness_mean_delta_low": normal["declared_mix"]["mean_delta_low"],
            "mean_delta": normal["declared_mix"]["mean_delta"],
            "mean_delta_high": normal["declared_mix"]["mean_delta_high"],
            "H": {key: panels["H"][key] for key in
                  ("n_roots", "mean_delta", "standard_error", "interval_95")},
            "M": {key: panels["M"][key] for key in
                  ("n_roots", "mean_delta", "standard_error", "interval_95")},
            "normalized_l1_from_default": phase_a._distance_from_default(row, design)})
    ranked = phase_a.rank_rows(rankings)
    selected = [row["config_id"] for row in ranked[:3]]
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-b-new-samples.json"), new_samples)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-b-ranking.json"), {"schema": "v2-joint-parameter-phase-b-ranking/1",
        "ranking": [{**row, "rank": index + 1,
                     "disposition": ("ADVANCE_TO_C" if index < 3
                                     else "NOT_SELECTED_WITHIN_BUDGET")}
                    for index, row in enumerate(ranked)],
        "selected_for_c": selected, "selection_rule": plan["selection"],
        "strength_claim": False, "confirmation_eligible": False,
        "release_eligible": False})
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-c-freeze.json"), {"schema": "v2-joint-parameter-phase-c-freeze/1",
        "created_after_complete_phase_b": True,
        "phase_b_manifest_sha256": batch.digest((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_bytes()),
        "phase_b_ranking_sha256": batch.digest((_project_file(_PROJECT_ROOT, OUT / "phase-b-ranking.json")).read_bytes()),
        "selected_configuration_ids": selected,
        "new_root_indices": list(range(17, 33)),
        "cumulative_roots_per_mix": 32,
        "planned_candidate_tables": 768, "baseline_new_tables": 256,
        "selection_keep": 1, "fitness": plan["selection"]["fitness"],
        "model_calls": 0, "confirmation_roots": 0, "release_eligible": False})
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {"status": "COMPLETE_PHASE_B_DEVELOPMENT_RANKING",
        "configurations": 8, "new_roots_per_configuration": 16,
        "cumulative_roots_per_configuration": 32,
        "candidate_tables": 1024, "baseline_tables": 128, "full_tables": 1152,
        "selected_for_c": selected, "leader": ranked[0],
        "spent": ledger.account_summary(), "model_calls": 0,
        "confirmation_roots": 0, "strength_claim": False,
        "confirmation_eligible": False, "release_eligible": False,
        "next": "按phase-c-freeze补H/M各16根并冻结单一冠军"})
    print(json.dumps({"status": "COMPLETE_PHASE_B_DEVELOPMENT_RANKING",
        "leader": ranked[0]["config_id"], "fitness": ranked[0]["fitness_mean_delta_low"],
        "selected_for_c": selected}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-b", "summarize-b"))
    args = parser.parse_args()
    {"prepare": prepare, "run-b": run_b, "summarize-b": summarize_b}[args.operation]()
