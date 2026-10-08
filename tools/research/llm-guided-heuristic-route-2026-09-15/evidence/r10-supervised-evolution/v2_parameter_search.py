"""可信V2联合参数分段搜索；当前实现阶段A（24配置、H/M各8根）。"""

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
import v2_parameter_wiring as wiring
import verify_full_natural_results as full
from confirmation_execution_probe import execute_arm
from hangma_bot.hangma.interface import ValueAnalysisLimits


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-a-20260920')
DESIGN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/parameter-search-design-20260920.json')
CONTRACT = batch.ROUTE / "contracts/group-dev-v1.json"
WIRING = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-wiring-v3-20260920/summary.json')
PANEL_SEED = 2026092052
ROOTS = tuple(range(1, 9))
MIXES = ("H", "M")
SEATS = tuple(range(4))


def _configurations():
    """按冻结设计顺序返回24个配置；阶段A不得增删或重排。"""
    design = batch.read(DESIGN)
    rows = list(design["selected"])
    if len(rows) != 24 or [row["config_id"] for row in rows] != [
            "v2_joint_%02d" % index for index in range(1, 25)]:
        raise ValueError("冻结24配置清单漂移")
    for row in rows:
        weights = parameter.weights_from_record(row["weights"])
        # 设计文件先前用json.dumps默认空格编码；运行身份改用严格紧凑JSON。
        # 两种摘要都保留各自口径，不能拿编码差异冒充权重值漂移。
        design_sha = batch.digest(json.dumps(
            row["weights"], sort_keys=True).encode())
        if design_sha != row["weights_sha256"]:
            raise ValueError("配置权重摘要不符：" + row["config_id"])
        row["policy_weights_sha256"] = parameter.weights_digest(weights)
    return rows


def _source_paths():
    """绑定阶段A入口、接线结果、统计器和完整结果核验器。"""
    return [Path(__file__), Path(parameter.__file__), Path(wiring.__file__),
            Path(archive.__file__), Path(full.__file__), DESIGN, CONTRACT, WIRING]


def prepare():
    """冻结新开发来源、24配置和3,200桌阶段A预算。"""
    if OUT.exists():
        raise ValueError("阶段A目录已存在，拒绝覆盖")
    if batch.read(WIRING)["status"] != "PASS_V2_JOINT_PARAMETER_WIRING":
        raise ValueError("联合参数接线尚未通过")
    if any(str(PANEL_SEED) in path.read_text(errors="ignore")
           for path in HERE.glob("*.json") if path not in (WIRING,)):
        raise ValueError("阶段A panel_seed 已出现在同层JSON，拒绝冒充新来源")
    configs = _configurations()
    contract = batch.read(CONTRACT)
    if contract["group"]["tables_per_group"] != 2:
        raise ValueError("阶段A预算仅适用于每阶段2桌")
    OUT.mkdir()
    auth = batch.unified_document(
        batch_label=OUT.name, authorization_id="r10-v2-parameter-search-a",
        accounts={"tables_full": 3200}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    auth.update({
        "issuance_basis": "新目标：按R10文献复盘路线执行可信V2联合参数优化",
        "scope": "阶段A开发筛选；24配置、H/M各8根、4座位、2桌；基线每单元只执行一次；不确认不发布",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    natural.require_authorization(auth)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    runtime = guard.capture(source_paths=_source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "v2-joint-parameter-search-a/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "design": str(DESIGN), "design_sha256": batch.digest(DESIGN.read_bytes()),
        "wiring_summary": str(WIRING), "wiring_sha256": batch.digest(WIRING.read_bytes()),
        "contract": str(CONTRACT), "contract_sha256": batch.digest(CONTRACT.read_bytes()),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": PANEL_SEED, "opponents": list(MIXES),
        "root_indices": list(ROOTS), "focal_seats": list(SEATS),
        "tables_per_arm": 2,
        "configuration_ids": [row["config_id"] for row in configs],
        "configuration_design_sha256": {
            row["config_id"]: row["weights_sha256"] for row in configs},
        "configuration_policy_sha256": {
            row["config_id"]: row["policy_weights_sha256"] for row in configs},
        "baseline_policy_id": "ComparableHeuristicPolicyV2",
        "candidate_tables": 3072, "baseline_tables": 128,
        "max_full_tables": 3200, "workers": 4,
        "selection": {
            "fitness": "H/M等权的根级保守差d_low均值",
            "keep": 8,
            "tie_break": "相对默认权重的六维归一化L1距离升序，再config_id升序",
            "meaning": "预算分配，不是显著性检验；未续评记NOT_SELECTED_WITHIN_BUDGET",
        },
        "model_calls": 0, "confirmation_roots": 0,
        "selection_eligible": True, "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 3200}).save()
    print("prepared phase A: 24 configs, 16 roots/config, 3200 max tables", flush=True)


def _verify_inputs(plan):
    """执行与汇总前核对全部冻结输入。"""
    guard.verify(plan["runtime"])
    for path_key, sha_key in (("design", "design_sha256"),
                              ("wiring_summary", "wiring_sha256"),
                              ("contract", "contract_sha256")):
        path = Path(plan[path_key])
        if batch.digest(path.read_bytes()) != plan[sha_key]:
            raise ValueError(path_key + " 漂移")
    rows = _configurations()
    if [row["config_id"] for row in rows] != plan["configuration_ids"]:
        raise ValueError("配置顺序漂移")
    if {row["config_id"]: row["weights_sha256"] for row in rows} != plan[
            "configuration_design_sha256"]:
        raise ValueError("配置设计摘要清单漂移")
    if {row["config_id"]: row["policy_weights_sha256"] for row in rows} != plan[
            "configuration_policy_sha256"]:
        raise ValueError("配置运行身份摘要清单漂移")


def _plans(contract, mix, root, seat, plan):
    """构造与臂无关的冻结两桌计划。"""
    return natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=plan["panel_seed"])


def _run_baseline_all():
    """执行阶段A所有64个基线单元；由所有配置复用同一原件。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    contract = batch.read(CONTRACT)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 3200})
    versions = natural.stage.contract_versions_block(contract)
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = _plans(contract, mix, root, seat, plan)
                label = f"a-baseline-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label, "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "baseline", "candidate_id": plan["baseline_policy_id"],
                }
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
    """执行一个配置的64个候选阶段单元；不同进程共享受锁账本。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    row = next(item for item in _configurations() if item["config_id"] == config_id)
    weights = parameter.weights_from_record(row["weights"])
    policy_id = parameter.PREFIX + row["policy_weights_sha256"]
    contract = batch.read(CONTRACT)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 3200})
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = _plans(contract, mix, root, seat, plan)
                label = f"a-{config_id}-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label, "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "candidate", "candidate_id": policy_id,
                }
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


def run_a():
    """四进程执行基线与24配置；单任务失败保留现场并使整批不汇总。"""
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
            if result["kind"] == "candidate":
                print(result["config_id"], "complete", result["tables"], "tables", flush=True)
            else:
                print("baseline complete", result["tables"], "tables", flush=True)
    _verify_inputs(plan)
    if len(completed) != 25:
        raise ValueError("阶段A工作单元未全部完成")
    summarize_a()


def _arm_view(raw, identity):
    """把完整阶段结果压成统计器需要的臂记录。"""
    return {key: raw.get(key) for key in (
        "status", "usable", "error", "focal_stage_score",
        "stage_totals_by_participant", "u", "u_low", "u_high",
        "unresolved", "elapsed_ms")} | {
            "candidate_id": identity, "policy_id": identity,
        }


def _root_digest(plan, mix, root, contract):
    """绑定本阶段根的生成器、随机来源和四座位赛程。"""
    seats = {}
    for seat in SEATS:
        plans = _plans(contract, mix, root, seat, plan)
        seats[str(seat)] = {
            "table_ids": [item.table_id for item in plans],
            "table_seeds": [item.seed for item in plans],
        }
    return wiring._digest({
        "generator": "v2-joint-parameter-search-a/1",
        "panel_seed": plan["panel_seed"], "opponent_mix": mix,
        "root_index": root, "seats": seats,
    })


def _distance_from_default(row, design):
    """冻结六维范围归一化L1距离；只作完全同适应度的确定性平分。"""
    total = 0.0
    for field, bounds in design["space"].items():
        low, high = float(bounds[0]), float(bounds[1])
        total += abs(float(row["weights"][field]) -
                     float(design["baseline_weights"][field])) / (high - low)
    return total


def rank_rows(rows):
    """按预登记保守适应度降序、默认距离升序、身份升序确定排名。"""
    return sorted(rows, key=lambda row: (-row["fitness_mean_delta_low"],
                                         row["normalized_l1_from_default"],
                                         row["config_id"]))


def summarize_a():
    """独立重读全部完整臂，构造根级统计并冻结阶段B的8个席位。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 3200})
    if ledger.spent("tables_full") != 3200:
        raise ValueError("阶段A费用未完整结算")
    contract = batch.read(CONTRACT)
    design = batch.read(DESIGN)
    samples, rankings = [], []
    for row in _configurations():
        config_id = row["config_id"]
        candidate_id = parameter.PREFIX + row["policy_weights_sha256"]
        candidate_samples = []
        for mix in MIXES:
            for root in ROOTS:
                root_id = f"v2pa-{mix}-{plan['panel_seed']}-root{root:02d}"
                digest = _root_digest(plan, mix, root, contract)
                for seat in SEATS:
                    baseline_label = f"a-baseline-{mix}-r{root:02d}-s{seat}"
                    candidate_label = f"a-{config_id}-{mix}-r{root:02d}-s{seat}"
                    baseline = batch.read(_project_file(_PROJECT_ROOT, OUT / "baseline" / baseline_label / "result.json"))["raw"]
                    candidate = batch.read(_project_file(_PROJECT_ROOT, OUT / "candidates" / config_id /
                                           candidate_label / "result.json"))["raw"]
                    sample = {
                        "schema": natural.NATURAL_SAMPLE_SCHEMA,
                        "source_root_id": root_id,
                        "root_content_digest": digest,
                        "root_index": root, "root_usage": "development_core",
                        "candidate_id": candidate_id,
                        "opponent_mix": mix, "scenario": "normal",
                        "focal_anchor_seat": seat,
                        "root_expected": {"seats": 4,
                                          "arms": ["baseline", "candidate"],
                                          "tables_per_arm": 2},
                        "arms": {
                            "baseline": _arm_view(baseline, plan["baseline_policy_id"]),
                            "candidate": _arm_view(candidate, candidate_id),
                        },
                        "completeness": "complete", "invalid_reasons": [],
                        "cost": {"budget_units": 4,
                                 "elapsed_ms": baseline["elapsed_ms"] + candidate["elapsed_ms"]},
                    }
                    candidate_samples.append(sample)
                    samples.append(sample)
        stats = archive.paired_stage_statistics(candidate_samples, min_roots=8)
        if stats["invalid_count"] or stats["uncomputable_count"]:
            raise ValueError("候选存在无效或不可计算样本：" + config_id)
        normal = stats["by_candidate"][candidate_id]["panels"]["normal"]
        panels = normal["panels"]
        if set(panels) != set(MIXES) or any(
                panel["status"] != "ok" or not panel["manifest_complete"]
                for panel in panels.values()):
            raise ValueError("候选根清单或统计状态不完整：" + config_id)
        rankings.append({
            "config_id": config_id, "candidate_id": candidate_id,
            "design_weights_sha256": row["weights_sha256"],
            "policy_weights_sha256": row["policy_weights_sha256"],
            "fitness_mean_delta_low": normal["declared_mix"]["mean_delta_low"],
            "mean_delta": normal["declared_mix"]["mean_delta"],
            "mean_delta_high": normal["declared_mix"]["mean_delta_high"],
            "H": {key: panels["H"][key] for key in
                  ("n_roots", "mean_delta", "standard_error", "interval_95")},
            "M": {key: panels["M"][key] for key in
                  ("n_roots", "mean_delta", "standard_error", "interval_95")},
            "normalized_l1_from_default": _distance_from_default(row, design),
        })
    ranked = rank_rows(rankings)
    selected = [row["config_id"] for row in ranked[:plan["selection"]["keep"]]]
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-samples.json"), samples)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json"), {
        "schema": "v2-joint-parameter-phase-a-ranking/1",
        "ranking": [{**row, "rank": index + 1,
                     "disposition": ("ADVANCE_TO_B" if index < 8
                                     else "NOT_SELECTED_WITHIN_BUDGET")}
                    for index, row in enumerate(ranked)],
        "selected_for_b": selected,
        "selection_rule": plan["selection"],
        "strength_claim": False, "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-b-freeze.json"), {
        "schema": "v2-joint-parameter-phase-b-freeze/1",
        "created_after_complete_phase_a": True,
        "phase_a_manifest_sha256": batch.digest((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_bytes()),
        "phase_a_ranking_sha256": batch.digest((_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json")).read_bytes()),
        "selected_configuration_ids": selected,
        "new_root_indices": list(range(9, 17)),
        "cumulative_roots_per_mix": 16,
        "planned_candidate_tables": 1024,
        "baseline_new_tables": 128,
        "selection_keep": 3,
        "fitness": plan["selection"]["fitness"],
        "model_calls": 0, "confirmation_roots": 0,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {
        "status": "COMPLETE_PHASE_A_DEVELOPMENT_RANKING",
        "configurations": 24, "roots_per_configuration": 16,
        "candidate_tables": 3072, "baseline_tables": 128,
        "full_tables": 3200, "selected_for_b": selected,
        "leader": ranked[0], "spent": ledger.account_summary(),
        "model_calls": 0, "confirmation_roots": 0,
        "strength_claim": False, "confirmation_eligible": False,
        "release_eligible": False,
        "next": "按phase-b-freeze补H/M各8根；阶段A排名仅分配预算",
    })
    print(json.dumps({"status": "COMPLETE_PHASE_A_DEVELOPMENT_RANKING",
                      "leader": ranked[0]["config_id"],
                      "fitness": ranked[0]["fitness_mean_delta_low"],
                      "selected_for_b": selected}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-a", "summarize-a"))
    args = parser.parse_args()
    {"prepare": prepare, "run-a": run_a, "summarize-a": summarize_a}[args.operation]()
