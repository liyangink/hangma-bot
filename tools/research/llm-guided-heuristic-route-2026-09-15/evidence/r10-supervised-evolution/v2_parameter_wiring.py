"""V2 联合参数研究接线：48个开发工程桌，零效果选留、零模型、零确认。"""

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
import json
from collections import Counter
from pathlib import Path
from time import monotonic

import confirmation_execution_identity as guard
import sitin_natural_panel as natural
import strong_seed_batch as batch
import v2_parameter_policy as parameter
import verify_full_natural_results as full
from confirmation_execution_probe import execute_arm
from hangma_bot.application.deadline import ManualClock
from hangma_bot.hangma.interface import ValueAnalysisLimits


HERE = Path(__file__).resolve().parent
FAILED_V1 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-wiring-20260920')
FAILED_V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-wiring-v2-20260920')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-wiring-v3-20260920')
DESIGN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/parameter-search-design-20260920.json')
CONTRACT = batch.ROUTE / "contracts/group-dev-v1.json"
PANEL_SEED = 2026092051
PROBE_CONFIG = "v2_joint_18"


def _digest(value):
    """统一严格JSON摘要，用于臂身份和恢复检查。"""
    return batch.digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False).encode())


def _configuration(config_id):
    """从冻结设计中严格读取一个配置，不接受运行时覆盖。"""
    design = batch.read(DESIGN)
    if config_id == "default":
        record = design["baseline_weights"]
    else:
        matches = [row for row in design["selected"] if row["config_id"] == config_id]
        if len(matches) != 1:
            raise ValueError("配置身份不存在或重复：" + config_id)
        record = matches[0]["weights"]
    weights = parameter.weights_from_record(record)
    return weights, parameter.weights_digest(weights)


def _sources():
    """冻结研究入口、配置、合同和独立核验器；生产闭包由guard补齐。"""
    return [Path(__file__), Path(parameter.__file__), DESIGN, CONTRACT,
            Path(natural.__file__), Path(full.__file__)]


def prepare():
    """冻结H/M同根三臂48桌及账本；不产生任何效果选择资格。"""
    if OUT.exists():
        raise ValueError("接线目录已存在，拒绝覆盖")
    default, default_sha = _configuration("default")
    probe, probe_sha = _configuration(PROBE_CONFIG)
    if default_sha == probe_sha:
        raise ValueError("探针配置与默认配置身份相同")
    contract = batch.read(CONTRACT)
    if contract["group"]["tables_per_group"] != 2:
        raise ValueError("接线预算只适用于每阶段2桌的冻结合同")
    OUT.mkdir()
    prior_result = _project_file(_PROJECT_ROOT, FAILED_V1 / "arms/H-root1-seat0-stable_v2/result.json")
    prior_ledger = _project_file(_PROJECT_ROOT, FAILED_V1 / "ledger.json")
    if not prior_result.exists() or batch.read(prior_ledger)["spent"]["tables_full"] != 2.0:
        raise ValueError("v1失败现场不完整，不能重用或继续")
    failed_v2_begin = _project_file(_PROJECT_ROOT, FAILED_V2 / "arms/H-root1-seat0-research_default/begin.json")
    failed_v2_ledger_path = _project_file(_PROJECT_ROOT, FAILED_V2 / "ledger.json")
    if not failed_v2_begin.exists() or (failed_v2_begin.parent / "result.json").exists():
        raise ValueError("v2失败现场不符合结果落盘前序列化失败的预期")
    failed_v2_ledger = batch.search.ActionValueLedger.load(
        failed_v2_ledger_path, authorized_budgets={"tables_full": 46})
    failed_v2_ledger.settle(
        batch.read(failed_v2_begin)["reservation"], usage_unknown=True,
        note="两桌已执行但含WindowKey对象的诊断轨迹无法JSON落盘；保守计费、不重用")
    failed_v2_ledger.save()
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r10-v2-parameter-wiring",
        accounts={"tables_full": 46}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "用户取消旧目标并授权按R10调研路线设立新目标继续推进",
        "scope": "可信V2联合参数独立研究接线；H/M各1根、4座位、稳定/默认研究/非默认研究三臂；工程等价与真实生效检查",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=_sources() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "v2-joint-parameter-wiring/1",
        "created_at_utc": batch.search.utc_now(),
        "scope": "development_engineering_only",
        "runtime": runtime,
        "contract": str(CONTRACT), "contract_sha256": batch.digest(CONTRACT.read_bytes()),
        "design": str(DESIGN), "design_sha256": batch.digest(DESIGN.read_bytes()),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": PANEL_SEED, "root_indices": [1], "opponents": ["H", "M"],
        "focal_seats": [0, 1, 2, 3], "tables_per_arm": 2,
        "arms": ["stable_v2", "research_default", "research_probe"],
        "planned_full_tables": 48, "planned_new_full_tables": 46,
        "reused_failed_v1_tables": 2,
        "additional_failed_v2_tables_charged_not_reused": 2,
        "reused_failed_v1_result": {"path": str(prior_result),
                                    "sha256": batch.digest(prior_result.read_bytes())},
        "default_weights_sha256": default_sha,
        "probe_config_id": PROBE_CONFIG, "probe_weights_sha256": probe_sha,
        "acceptance": [
            "48桌完整结果和阶段账通过独立复算",
            "稳定V2与默认权重研究臂16桌终端、完成手数及运行计数一致",
            "默认与探针配置在同一可见decision_id上至少一处完整动作排序不同",
            "三臂焦点策略身份与完整权重摘要一致且零驱动内部失败",
        ],
        "model_calls": 0, "confirmation_roots": 0,
        "selection_eligible": False, "strength_evidence": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 46}).save()
    batch.write(_project_file(_PROJECT_ROOT, FAILED_V1 / "closure.json"), {
        "status": "CLOSED_WIRING_IDENTITY_EXPECTATION_ERROR",
        "reason": "逻辑配置名 weighted_heuristic_v2 被误当作运行时policy_id；实际对象未声明policy_id，执行器记录类名 ComparableHeuristicPolicyV2",
        "tables_charged": 2, "result_sha256": batch.digest(prior_result.read_bytes()),
        "retry": False, "reuse_in": str(OUT), "strength_evidence": False,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, FAILED_V2 / "closure.json"), {
        "status": "CLOSED_TRACE_SERIALIZATION_ERROR",
        "reason": "研究轨迹包含不可JSON序列化的WindowKey，桌赛完成但结果文件未落盘",
        "tables_charged_usage_unknown": 2, "rerun": False,
        "replacement": str(OUT), "strength_evidence": False,
        "release_eligible": False,
    })
    print("prepared 46 new + 2 verified-reuse; two extra failed tables conservatively charged", flush=True)


def _verify_inputs(plan):
    """每臂前复核执行闭包、合同、设计与权重摘要。"""
    guard.verify(plan["runtime"])
    if batch.digest(CONTRACT.read_bytes()) != plan["contract_sha256"]:
        raise ValueError("合同漂移")
    if batch.digest(DESIGN.read_bytes()) != plan["design_sha256"]:
        raise ValueError("参数设计漂移")
    if _configuration("default")[1] != plan["default_weights_sha256"]:
        raise ValueError("默认权重漂移")
    if _configuration(plan["probe_config_id"])[1] != plan["probe_weights_sha256"]:
        raise ValueError("探针权重漂移")
    reused = Path(plan["reused_failed_v1_result"]["path"])
    if batch.digest(reused.read_bytes()) != plan["reused_failed_v1_result"]["sha256"]:
        raise ValueError("v1可复用完整结果漂移")


def _run_configured_stage(plans, mix, contract, weights):
    """只替换焦点位为带身份的V2权重实例；对手、规则、驱动和目标保持单一来源。"""
    versions = natural.stage.contract_versions_block(contract)
    totals, points, tables = {}, {}, []
    started = monotonic()
    for index, plan in enumerate(plans):
        situation = natural.build_stage_situation(
            plan=plan, table_no=index + 1, tables_completed=index,
            totals=totals, place_totals=points,
            rounds_per_game=versions["rounds_per_game"])
        clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
        logical = natural.arm_logical_policies(
            arm="baseline", candidate_scorer=None,
            logical_participants=plan.logical_participants,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
            monotonic=clock.now)
        focal = parameter.ResearchWeightedV2(weights, monotonic=clock.now)
        logical[natural.FOCAL_PARTICIPANT] = focal
        row = natural.execute_natural_table(
            plan=plan,
            policies_by_seat=natural.seat_policies_from(
                logical, plan.permutation, plan.logical_participants),
            versions_block=versions, step_limit=contract["stop"]["step_limit"],
            value_limits=ValueAnalysisLimits(), stage_situation=situation)
        row["stage_situation"] = situation.to_json()
        row["research_trace"] = focal.decision_trace
        row["weights_sha256"] = focal.weights_sha256
        tables.append(row)
        if row["match_status"] != "complete" or row["scores_by_seat"] is None:
            raise RuntimeError("联合参数工程桌未完成：" + plan.table_id)
        placement = natural.stage.place_points_for_table(row["scores_by_seat"])
        for seat, participant in enumerate(plan.seats()):
            totals[participant] = totals.get(participant, 0) + row["scores_by_seat"][seat]
            points[participant] = points.get(participant, 0) + placement[seat]
    utility = natural.stage.group_advance_utility([
        natural.stage.LedgerRow(participant_id=p, total_score=totals[p],
                                place_points=points[p]) for p in sorted(totals)
    ], focal_id=natural.FOCAL_PARTICIPANT)
    return {
        "arm": "configured", "status": "complete", "usable": True, "error": None,
        "tables": tables, "stage_totals_by_participant": totals,
        "stage_place_points_by_participant": points,
        "focal_stage_score": totals[natural.FOCAL_PARTICIPANT],
        "u_low": float(utility["u_low"]), "u_high": float(utility["u_high"]),
        "u": float(utility["u_low"]) if utility["u_low"] == utility["u_high"] else None,
        "unresolved": utility["unresolved"],
        "u_interval": {key: utility[key] for key in ("a", "b", "tie_block")},
        "elapsed_ms": (monotonic() - started) * 1000,
        "execution_review": natural.execution_audit.review_tables(tables),
    }


def _verify_stage(raw, plans, contract, expected_policy_id, weights_sha=None):
    """从完整桌重算阶段账，并核对焦点位真实策略身份和可见决策轨迹。"""
    if raw["status"] != "complete" or raw["usable"] is not True or raw["error"] is not None:
        raise ValueError("工程臂不完整")
    if len(raw["tables"]) != len(plans) or len(plans) != 2:
        raise ValueError("工程臂桌数不符")
    totals, points, trace = {}, {}, []
    for index, (row, plan) in enumerate(zip(raw["tables"], plans, strict=True)):
        full.verify_full_table(row, plan, contract, natural.compute_rules_hash(natural.REPO),
                               require_execution_audit=True)
        situation = natural.build_stage_situation(
            plan=plan, table_no=index + 1, tables_completed=index,
            totals=totals, place_totals=points,
            rounds_per_game=contract["versions"]["rounds_per_game"])
        if row["stage_situation"] != situation.to_json():
            raise ValueError("阶段账投影不符")
        focal_seat = list(plan.seats()).index(natural.FOCAL_PARTICIPANT)
        if row["policy_execution"]["policy_ids_by_seat"][focal_seat] != expected_policy_id:
            raise ValueError("焦点策略身份不符")
        if row["result"]["versions"]["natural_seat_policy:" + str(focal_seat)] != expected_policy_id:
            raise ValueError("结果版本未绑定焦点策略身份")
        if weights_sha is not None:
            if row.get("weights_sha256") != weights_sha:
                raise ValueError("实际权重摘要不符")
            rows = row.get("research_trace")
            if not isinstance(rows, list) or len(rows) != row["policy_execution"]["by_seat"][focal_seat]["decision_count"]:
                raise ValueError("研究决策轨迹缺失或行数不符")
            if len({item["decision_id"] for item in rows}) != len(rows):
                raise ValueError("研究决策轨迹身份重复")
            trace.extend(rows)
        placement = natural.stage.place_points_for_table(row["scores_by_seat"])
        for seat, participant in enumerate(plan.seats()):
            totals[participant] = totals.get(participant, 0) + row["scores_by_seat"][seat]
            points[participant] = points.get(participant, 0) + placement[seat]
    utility = natural.stage.group_advance_utility([
        natural.stage.LedgerRow(participant_id=p, total_score=totals[p],
                                place_points=points[p]) for p in sorted(totals)
    ], focal_id=natural.FOCAL_PARTICIPANT)
    if raw["stage_totals_by_participant"] != totals or raw["stage_place_points_by_participant"] != points:
        raise ValueError("阶段账汇总不符")
    if (raw["u_low"], raw["u_high"]) != (utility["u_low"], utility["u_high"]):
        raise ValueError("阶段效用复算不符")
    review = natural.execution_audit.review_tables(raw["tables"])
    if raw["execution_review"] != review or not review["zero_internal_failures_verified"]:
        raise ValueError("执行审计失败")
    return {"tables": len(plans), "trace": trace,
            "terminal_digest": _digest({
                "totals": totals, "points": points,
                "u_low": utility["u_low"], "u_high": utility["u_high"],
                "completed_hands": [row["result"]["completed_hands"] for row in raw["tables"]],
                "runtime_counts": [row["result"]["runtime_counts"] for row in raw["tables"]],
            }), "release_eligible": False}


def run():
    """可恢复地执行三臂；默认等价和探针生效不满足即失败并保留现场。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    authorization = batch.read(_project_file(_PROJECT_ROOT, OUT / "authorization.json"))
    natural.require_authorization(authorization)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 46})
    contract = batch.read(CONTRACT)
    weights = {
        "research_default": _configuration("default")[0],
        "research_probe": _configuration(plan["probe_config_id"])[0],
    }
    identities = {
        "stable_v2": "ComparableHeuristicPolicyV2",
        **{name: parameter.PREFIX + parameter.weights_digest(value)
           for name, value in weights.items()},
    }
    table_count = 0
    equal_cells = 0
    common_decisions = changed_first = changed_order = 0
    readings = []
    versions = natural.stage.contract_versions_block(contract)
    for mix in plan["opponents"]:
        for seat in plan["focal_seats"]:
            plans = natural.build_seat_stage_plans(
                contract=contract, opponent=mix, root_index=1,
                focal_seat=seat, panel_seed=plan["panel_seed"])
            outputs = {}
            for arm in plan["arms"]:
                _verify_inputs(plan)
                label = f"{mix}-root1-seat{seat}-{arm}"
                expected = {
                    "step_id": label, "planned_tables": 2,
                    "manifest_digest": _digest(plan),
                    "plans_digest": _digest([item.to_json() for item in plans]),
                    "arm": arm, "candidate_id": identities[arm],
                }
                if arm == "stable_v2":
                    runner = lambda: natural.run_arm_stage(
                        arm="baseline", plans=plans, candidate_scorer=None,
                        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
                        versions_block=versions, step_limit=contract["stop"]["step_limit"],
                        value_limits=ValueAnalysisLimits())
                    weight_sha = None
                else:
                    runner = lambda w=weights[arm]: _run_configured_stage(
                        plans, mix, contract, w)
                    weight_sha = parameter.weights_digest(weights[arm])
                if arm == "stable_v2" and mix == "H" and seat == 0:
                    prior = Path(plan["reused_failed_v1_result"]["path"])
                    bundle = batch.read(prior)
                    raw = bundle["raw"]
                    checked = _verify_stage(raw, plans, contract, identities[arm], None)
                    batch.write(_project_file(_PROJECT_ROOT, OUT / "reused-failed-v1-stable.json"), {
                        "source": str(prior), "source_sha256": batch.digest(prior.read_bytes()),
                        "checked": checked, "charged_in_prior_ledger": 2,
                        "rerun": False, "release_eligible": False,
                    })
                else:
                    checked = execute_arm(
                        _project_file(_PROJECT_ROOT, OUT / "arms" / label), expected=expected, ledger=ledger,
                        runner=runner,
                        verifier=lambda raw, pid=identities[arm], sha=weight_sha:
                            _verify_stage(raw, plans, contract, pid, sha))
                    raw = batch.read(_project_file(_PROJECT_ROOT, OUT / "arms" / label / "result.json"))["raw"]
                outputs[arm] = {"checked": checked, "raw": raw}
                table_count += checked["tables"]
                readings.append({"label": label,
                                 "terminal_digest": checked["terminal_digest"]})
            if outputs["stable_v2"]["checked"]["terminal_digest"] != outputs["research_default"]["checked"]["terminal_digest"]:
                raise ValueError("稳定V2与默认研究权重的完整阶段终端不等价")
            equal_cells += 1
            default_trace = {row["decision_id"]: row["ordered_action_keys"]
                             for row in outputs["research_default"]["checked"]["trace"]}
            probe_trace = {row["decision_id"]: row["ordered_action_keys"]
                           for row in outputs["research_probe"]["checked"]["trace"]}
            for decision_id in sorted(set(default_trace).intersection(probe_trace)):
                common_decisions += 1
                changed_order += default_trace[decision_id] != probe_trace[decision_id]
                changed_first += default_trace[decision_id][:1] != probe_trace[decision_id][:1]
            print(mix, "seat", seat, "three arms verified", flush=True)
    _verify_inputs(plan)
    if table_count != 48 or ledger.spent("tables_full") != 46:
        raise ValueError("工程桌数或费用不符")
    if equal_cells != 8:
        raise ValueError("默认权重等价单元不完整")
    if common_decisions == 0 or changed_order == 0:
        raise ValueError("非默认权重未在真实决策路径产生可核变化")
    summary = {
        "status": "PASS_V2_JOINT_PARAMETER_WIRING",
        "full_tables_verified": table_count,
        "stable_default_equivalent_cells": equal_cells,
        "common_visible_decisions_default_vs_probe": common_decisions,
        "full_order_changes": changed_order, "first_action_changes": changed_first,
        "identities": identities, "readings": readings,
        "spent": ledger.account_summary(),
        "prior_failed_v1_tables_reused": 2,
        "model_calls": 0, "confirmation_roots": 0,
        "selection_eligible": False, "strength_evidence": False,
        "release_eligible": False,
        "next": "冻结24配置的64根开发顺序和分段执行清单；本结果不得用于配置选优",
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), summary)
    print(json.dumps({key: summary[key] for key in (
        "status", "full_tables_verified", "stable_default_equivalent_cells",
        "common_visible_decisions_default_vs_probe", "full_order_changes",
        "first_action_changes")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    arguments = parser.parse_args()
    prepare() if arguments.operation == "prepare" else run()
