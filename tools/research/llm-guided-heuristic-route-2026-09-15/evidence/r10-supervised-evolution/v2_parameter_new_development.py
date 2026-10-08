"""冻结V2参数冠军后的新来源开发复核：H/M各128根、4,096桌。"""

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
import math
import multiprocessing
import subprocess
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
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-new-development-20260921')
C_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-c-20260920')
CHAMPION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-c-20260920/development-champion-freeze.json')
C_SUMMARY = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-c-20260920/summary.json')
CONTRACT = batch.ROUTE / "contracts/group-dev-v1.json"
PANEL_SEEDS = (2026092053, 2026092054)
ROOTS = tuple(range(1, 65))
MIXES = ("H", "M")
SEATS = tuple(range(4))
ARMS = ("baseline", "candidate")
Z_95 = 1.959963984540054


def _champion():
    """读取机器冻结冠军并严格装配完整权重身份。"""
    row = batch.read(CHAMPION)
    if (row.get("config_id") != "v2_joint_07"
            or row.get("positive_development_signal") is not True):
        raise ValueError("阶段C未冻结预期的正向开发冠军")
    weights = parameter.weights_from_record(row["weights"])
    digest = parameter.weights_digest(weights)
    if digest != row["policy_weights_sha256"]:
        raise ValueError("冠军权重摘要漂移")
    if parameter.PREFIX + digest != row["candidate_id"]:
        raise ValueError("冠军策略身份漂移")
    return row, weights


def _source_paths():
    return [Path(__file__), Path(parameter.__file__), Path(wiring.__file__),
            Path(phase_a.__file__), Path(archive.__file__), Path(natural.__file__),
            CHAMPION, C_SUMMARY, CONTRACT]


def _ensure_new_seeds():
    """确认两个预定面板种子未出现在既有JSON证据中。"""
    for seed in PANEL_SEEDS:
        scan = subprocess.run(
            ["rg", "-l", "-F", str(seed), str(HERE), "-g", "*.json"],
            capture_output=True, text=True, check=False)
        if scan.returncode not in (0, 1):
            raise RuntimeError("面板种子清单检索失败：" + scan.stderr)
        if scan.stdout.strip():
            raise ValueError("新开发面板种子已有JSON记录：" + scan.stdout.strip())


def prepare():
    """在读取任何新效果前冻结双种子、完整样本量、分析和停止规则。"""
    if OUT.exists():
        raise ValueError("新开发复核目录已存在，拒绝覆盖")
    c_summary = batch.read(C_SUMMARY)
    if (c_summary.get("status") != "COMPLETE_PHASE_C_DEVELOPMENT_CHAMPION"
            or c_summary.get("positive_development_signal") is not True):
        raise ValueError("阶段C不满足新来源开发复核前提")
    champion, _weights = _champion()
    _ensure_new_seeds()
    OUT.mkdir()
    auth = batch.unified_document(
        batch_label=OUT.name, authorization_id="r10-v2-parameter-new-development",
        accounts={"tables_full": 4096}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    auth.update({
        "issuance_basis": "R10预登记§5.4：阶段C冠军保守开发适应度大于0，进入全新H/M各128根开发复核",
        "scope": "冻结单一参数冠军对稳定V2；两个新panel_seed各H/M各64根、4座位、2桌、2臂；全量完成前不读结果改设计；不是正式确认",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    natural.require_authorization(auth)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    runtime = guard.capture(source_paths=_source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "v2-joint-parameter-new-development/1",
        "created_at_utc": batch.search.utc_now(), "runtime": runtime,
        "champion_freeze": str(CHAMPION),
        "champion_freeze_sha256": batch.digest(CHAMPION.read_bytes()),
        "phase_c_summary": str(C_SUMMARY),
        "phase_c_summary_sha256": batch.digest(C_SUMMARY.read_bytes()),
        "contract": str(CONTRACT), "contract_sha256": batch.digest(CONTRACT.read_bytes()),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "config_id": champion["config_id"],
        "candidate_id": champion["candidate_id"],
        "policy_weights_sha256": champion["policy_weights_sha256"],
        "weights": champion["weights"],
        "baseline_policy_id": "ComparableHeuristicPolicyV2",
        "panel_seeds": list(PANEL_SEEDS), "root_indices_per_seed": list(ROOTS),
        "roots_per_mix": 128, "opponents": list(MIXES),
        "focal_seats": list(SEATS), "tables_per_arm": 2,
        "arms": list(ARMS), "max_full_tables": 4096, "workers": 4,
        "analysis": {
            "primary": "根级保守差L_r在H/M内各自均值后等权；SE=sqrt(s_H^2/n_H+s_M^2/n_M)/2；95%开发正态近似区间",
            "positive_but_interval_crosses_zero": "INCONCLUSIVE_DEVELOPMENT；不自动扩评，保留为结构搜索父代",
            "nonpositive_mean": "NO_POSITIVE_DEVELOPMENT；停止该参数候选提名",
            "positive_interval_lower": "WORTH_INDEPENDENT_CONFIRMATION；仍须处理分家族显著退步并另冻正式确认",
            "family_regression": "任一H/M点差或保守差95%开发区间上端小于0时阻止直接进入确认准备",
            "interval_status": "开发正态近似，不是正式显著性或发布证明",
        },
        "seed_selection": "阶段C冠军冻结后选取的两个未见固定panel_seed；prepare前对同层全部JSON做精确文本查重",
        "model_calls": 0, "confirmation_roots": 0,
        "selection_eligible": False, "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 4096}).save()
    print("prepared new development: H/M each 128 roots, 4096 tables", flush=True)


def _verify_inputs(plan):
    guard.verify(plan["runtime"])
    for key, sha_key in (("champion_freeze", "champion_freeze_sha256"),
                         ("phase_c_summary", "phase_c_summary_sha256"),
                         ("contract", "contract_sha256")):
        if batch.digest(Path(plan[key]).read_bytes()) != plan[sha_key]:
            raise ValueError(key + " 漂移")
    champion, weights = _champion()
    if (champion["candidate_id"] != plan["candidate_id"]
            or champion["weights"] != plan["weights"]
            or parameter.weights_digest(weights) != plan["policy_weights_sha256"]):
        raise ValueError("新开发冠军运行身份漂移")


def _plans(contract, mix, panel_seed, root, seat):
    return natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=panel_seed)


def _run_work_unit(panel_seed, mix, arm):
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    _champion_row, weights = _champion()
    contract = batch.read(CONTRACT)
    versions = natural.stage.contract_versions_block(contract)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 4096})
    count = 0
    seed_slot = plan["panel_seeds"].index(panel_seed) + 1
    for root in ROOTS:
        for seat in SEATS:
            plans = _plans(contract, mix, panel_seed, root, seat)
            label = f"nd-p{seed_slot}-{arm}-{mix}-r{root:02d}-s{seat}"
            candidate_id = (plan["baseline_policy_id"] if arm == "baseline"
                            else plan["candidate_id"])
            expected = {"step_id": label, "planned_tables": 2,
                "manifest_digest": wiring._digest(plan),
                "plans_digest": wiring._digest([item.to_json() for item in plans]),
                "arm": arm, "candidate_id": candidate_id}
            if arm == "baseline":
                runner = lambda plans=plans, mix=mix: natural.run_arm_stage(
                    arm="baseline", plans=plans, candidate_scorer=None,
                    opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
                    versions_block=versions, step_limit=contract["stop"]["step_limit"],
                    value_limits=ValueAnalysisLimits())
                verifier = lambda raw, plans=plans: wiring._verify_stage(
                    raw, plans, contract, plan["baseline_policy_id"], None)
            else:
                runner = lambda plans=plans, mix=mix: wiring._run_configured_stage(
                    plans, mix, contract, weights)
                verifier = lambda raw, plans=plans: wiring._verify_stage(
                    raw, plans, contract, plan["candidate_id"],
                    plan["policy_weights_sha256"])
            checked = execute_arm(
                _project_file(_PROJECT_ROOT, OUT / "arms" / f"p{seed_slot}-{arm}-{mix}" / label),
                expected=expected, ledger=ledger, runner=runner, verifier=verifier)
            count += checked["tables"]
    _verify_inputs(plan)
    return {"panel_seed": panel_seed, "mix": mix, "arm": arm, "tables": count}


def run():
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    context = multiprocessing.get_context("spawn")
    completed = []
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=plan["workers"], mp_context=context) as pool:
        futures = [pool.submit(_run_work_unit, seed, mix, arm)
                   for seed in PANEL_SEEDS for mix in MIXES for arm in ARMS]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            completed.append(result)
            print("complete", result["panel_seed"], result["mix"],
                  result["arm"], result["tables"], flush=True)
    if len(completed) != 8 or sum(row["tables"] for row in completed) != 4096:
        raise ValueError("新开发复核工作单元未完整完成")
    summarize()


def _root_digest(contract, mix, panel_seed, root):
    seats = {}
    for seat in SEATS:
        plans = _plans(contract, mix, panel_seed, root, seat)
        seats[str(seat)] = {"table_ids": [item.table_id for item in plans],
                            "table_seeds": [item.seed for item in plans]}
    return wiring._digest({"generator": "v2-joint-parameter-new-development/1",
        "panel_seed": panel_seed, "opponent_mix": mix,
        "root_index": root, "seats": seats})


def _root_level_interval(panels):
    """按预登记公式合并H/M保守根差的抽样不确定性。"""
    means = [panels[mix]["delta_bounds"]["mean_delta_low"] for mix in MIXES]
    ses = [panels[mix]["delta_bounds"]["standard_error_low"] for mix in MIXES]
    if any(value is None for value in means + ses):
        raise ValueError("保守根差缺少均值或标准误")
    mean_low = sum(means) / 2.0
    standard_error = math.sqrt(sum(value * value for value in ses)) / 2.0
    return {"mean": mean_low, "standard_error": standard_error,
            "interval_95": [mean_low - Z_95 * standard_error,
                            mean_low + Z_95 * standard_error],
            "formula": "sqrt(SE_H_low^2 + SE_M_low^2) / 2",
            "kind": "sampling_uncertainty_normal_approx_on_conservative_root_delta"}


def summarize():
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    _verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 4096})
    if ledger.spent("tables_full") != 4096:
        raise ValueError("新开发复核费用未完整结算")
    contract = batch.read(CONTRACT)
    samples = []
    for panel_seed in PANEL_SEEDS:
        seed_slot = plan["panel_seeds"].index(panel_seed) + 1
        for mix in MIXES:
            for root in ROOTS:
                root_id = f"v2pnd-{mix}-{panel_seed}-root{root:02d}"
                digest = _root_digest(contract, mix, panel_seed, root)
                for seat in SEATS:
                    base_label = f"nd-p{seed_slot}-baseline-{mix}-r{root:02d}-s{seat}"
                    cand_label = f"nd-p{seed_slot}-candidate-{mix}-r{root:02d}-s{seat}"
                    baseline = batch.read(_project_file(_PROJECT_ROOT, OUT / "arms" / f"p{seed_slot}-baseline-{mix}" /
                                          base_label / "result.json"))["raw"]
                    candidate = batch.read(_project_file(_PROJECT_ROOT, OUT / "arms" / f"p{seed_slot}-candidate-{mix}" /
                                           cand_label / "result.json"))["raw"]
                    samples.append({"schema": natural.NATURAL_SAMPLE_SCHEMA,
                        "source_root_id": root_id, "root_content_digest": digest,
                        "root_index": root, "root_usage": "new_development",
                        "candidate_id": plan["candidate_id"], "opponent_mix": mix,
                        "scenario": "normal", "focal_anchor_seat": seat,
                        "root_expected": {"seats": 4,
                            "arms": ["baseline", "candidate"], "tables_per_arm": 2},
                        "arms": {"baseline": phase_a._arm_view(
                                    baseline, plan["baseline_policy_id"]),
                                 "candidate": phase_a._arm_view(
                                    candidate, plan["candidate_id"])},
                        "completeness": "complete", "invalid_reasons": [],
                        "cost": {"budget_units": 4,
                            "elapsed_ms": baseline["elapsed_ms"] + candidate["elapsed_ms"]}})
    stats = archive.paired_stage_statistics(samples, min_roots=128)
    if stats["invalid_count"] or stats["uncomputable_count"]:
        raise ValueError("新开发复核存在无效或不可计算样本")
    normal = stats["by_candidate"][plan["candidate_id"]]["panels"]["normal"]
    panels = normal["panels"]
    if any(panel["status"] != "ok" or panel["n_roots"] != 128
           or not panel["manifest_complete"] for panel in panels.values()):
        raise ValueError("新开发复核根清单不完整")
    conservative = _root_level_interval(panels)
    family_regressions = []
    for mix in MIXES:
        panel = panels[mix]
        if panel["interval_95"][1] < 0:
            family_regressions.append({"mix": mix, "measure": "point_delta",
                                       "interval_95": panel["interval_95"]})
        low_interval = panel["delta_bounds"]["interval_95_low"]
        if low_interval[1] < 0:
            family_regressions.append({"mix": mix, "measure": "conservative_delta",
                                       "interval_95": low_interval})
    if conservative["mean"] <= 0:
        disposition = "NO_POSITIVE_DEVELOPMENT"
    elif conservative["interval_95"][0] <= 0:
        disposition = "INCONCLUSIVE_DEVELOPMENT"
    elif family_regressions:
        disposition = "FAMILY_REGRESSION_REVIEW_REQUIRED"
    else:
        disposition = "WORTH_INDEPENDENT_CONFIRMATION"
    compact_panels = {}
    for mix in MIXES:
        panel = panels[mix]
        compact_panels[mix] = {
            "n_roots": panel["n_roots"], "mean_delta": panel["mean_delta"],
            "standard_error": panel["standard_error"],
            "interval_95": panel["interval_95"],
            "mean_delta_low": panel["delta_bounds"]["mean_delta_low"],
            "standard_error_low": panel["delta_bounds"]["standard_error_low"],
            "interval_95_low": panel["delta_bounds"]["interval_95_low"],
            "mean_delta_high": panel["delta_bounds"]["mean_delta_high"],
            "unresolved_roots": panel["delta_bounds"]["unresolved_roots"],
        }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "new-development-samples.json"), samples)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "statistics.json"), stats)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {
        "status": "COMPLETE_V2_PARAMETER_NEW_DEVELOPMENT",
        "disposition": disposition, "config_id": plan["config_id"],
        "candidate_id": plan["candidate_id"], "policy_weights_sha256": plan["policy_weights_sha256"],
        "full_tables_verified": 4096, "roots_per_mix": 128,
        "panels": compact_panels,
        "declared_equal_mix": normal["declared_mix"],
        "conservative_equal_mix_sampling": conservative,
        "family_regressions": family_regressions,
        "spent": ledger.account_summary(), "model_calls": 0,
        "confirmation_roots": 0, "strength_claim": False,
        "continue_confirmation_preparation": disposition == "WORTH_INDEPENDENT_CONFIRMATION",
        "retain_as_structural_parent": disposition in (
            "INCONCLUSIVE_DEVELOPMENT", "WORTH_INDEPENDENT_CONFIRMATION"),
        "confirmation_eligible": False, "release_eligible": False,
        "next": ("冻结正式确认设计并复核统计入口" if disposition == "WORTH_INDEPENDENT_CONFIRMATION"
                 else "按R10文献复盘转入小型多父代结构搜索，不追加本批根"),
    })
    print(json.dumps({"status": "COMPLETE_V2_PARAMETER_NEW_DEVELOPMENT",
        "disposition": disposition,
        "conservative_mean": conservative["mean"],
        "interval_95": conservative["interval_95"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "summarize"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "summarize": summarize}[args.operation]()
