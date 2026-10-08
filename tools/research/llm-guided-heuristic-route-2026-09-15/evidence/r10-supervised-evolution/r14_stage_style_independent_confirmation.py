"""R14：冻结阶段处境候选在全新 H/M 来源上的固定样本独立确认。"""

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
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_draft as analysis  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import confirmation_pairing as pairing  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r14-stage-style-independent-confirmation-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R14-HM-ROBUST-POPULATION-EVOLUTION-PLAN-2026-09-21.md')
G2_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r14-generation2-archive-stage-style-01-20260921/result.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/stage-style-20260920/stage-style-terra-max/run/iterations/iter-01/generation/candidate.py')
BASELINE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
REGISTRATION_SEED = 2026092609
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
ARMS = ("baseline", "candidate")
ROOT_COUNT = len(MIXES) * len(ROOTS)
SOURCE_UNITS = ROOT_COUNT * len(SEATS)
PLANNED_TABLES = SOURCE_UNITS * len(ARMS) * 2
MINIMUM_MEAN_EFFECT = 0.03125
ONE_SIDED_ALPHA = 0.05


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_root_plans() -> list[dict[str, Any]]:
    """用未参与生成、选择或诊断的登记种子构造固定确认根。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return [pairing.build_root_plan(
        contract=contract, registration_seed=REGISTRATION_SEED,
        opponent=mix, root_index=root)
        for mix in MIXES for root in ROOTS]


def source_paths() -> list[Path]:
    return [Path(__file__), PLAN, G2_RESULT, CANDIDATE, BASELINE, CONTRACT,
            Path(pairing.__file__), Path(natural.__file__)]


def prepare() -> None:
    """在执行前冻结候选、全新来源、固定样本量和一次性确认判据。"""

    if OUT.exists():
        raise SystemExit("独立确认输出已存在；拒绝覆盖")
    g2 = json.loads(G2_RESULT.read_text(encoding="utf-8"))
    if g2.get("status") != "PASS_R14_G2_DEVELOPMENT_GATE" \
            or g2.get("candidate_sha256") != digest(CANDIDATE):
        raise RuntimeError("代际2通过结论或候选摘要漂移")
    ActionValueScorer("r14-confirmation-precheck", CANDIDATE.read_text(encoding="utf-8"))
    roots = build_root_plans()
    if len({row["independence_id"] for row in roots}) != ROOT_COUNT \
            or len({row["root_content_digest"] for row in roots}) != ROOT_COUNT:
        raise RuntimeError("确认根随机身份或内容摘要重复")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r14-stage-style-confirmation-01",
        accounts={"tables_full": PLANNED_TABLES}, issued_by="lead",
        issued_at_utc=search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "冻结stage-style候选已跨两个开发来源H/M同向；执行一次固定样本全新来源独立确认",
        "scope": "H/M各32个独立根×4焦点座位×双臂×两桌；不按中间结果停止、扩样或调参",
        "max_model_calls": 0, "confirmation_roots": ROOT_COUNT,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r14-stage-style-independent-confirmation/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "plan": str(PLAN), "plan_sha256": digest(PLAN),
        "generation2_result": str(G2_RESULT),
        "generation2_result_sha256": digest(G2_RESULT),
        "candidate": str(CANDIDATE), "candidate_sha256": digest(CANDIDATE),
        "baseline_reference": str(BASELINE), "baseline_sha256": digest(BASELINE),
        "contract": str(CONTRACT), "contract_sha256": digest(CONTRACT),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "registration_seed": REGISTRATION_SEED,
        "root_plans": roots,
        "mixes": list(MIXES), "root_indices": list(ROOTS),
        "focal_seats": list(SEATS), "arms": list(ARMS),
        "independent_roots": ROOT_COUNT, "source_units": SOURCE_UNITS,
        "tables_per_stage": 2, "planned_tables": PLANNED_TABLES, "workers": 4,
        "fixed_sample": True,
        "optional_stopping": False,
        "primary_gate": {
            "metric": "每个独立根四座位平均的 candidate.u_low-baseline.u_high",
            "overall_mean_min": MINIMUM_MEAN_EFFECT,
            "each_mix_mean_min": 0.0,
            "one_sided_exact_sign_flip_p_max": ONE_SIDED_ALPHA,
            "one_sided_stratified_normal_lower_bound_min": 0.0,
            "unresolved_intervals": 0,
        },
        "secondary_gate": {
            "overall_stage_score_delta_mean": ">0",
            "positive_root_each_mix": True,
            "execution_failures": 0,
        },
        "analysis_note": (
            "精确符号翻转检验对非零根绝对差做完整动态规划；"
            "正态下界按H/M逐根样本方差和等权分层标准误计算，仅作并列保守门"),
        "selection_note": "本来源及结果未参与候选生成、归一化、门控或参数选择",
        "strength_claim": False, "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED", "roots": ROOT_COUNT,
                      "planned_tables": PLANNED_TABLES}, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    for key, sha_key in (("plan", "plan_sha256"),
                         ("generation2_result", "generation2_result_sha256"),
                         ("candidate", "candidate_sha256"),
                         ("baseline_reference", "baseline_sha256"),
                         ("contract", "contract_sha256")):
        if digest(Path(manifest[key])) != manifest[sha_key]:
            raise RuntimeError(f"冻结输入摘要漂移：{key}")
    if manifest["root_plans"] != build_root_plans():
        raise RuntimeError("冻结确认根计划漂移")
    guard.verify(manifest["runtime"])
    return manifest


def tasks(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """展开根、四座位与双臂，不读取任何结果。"""

    values = []
    for root in manifest["root_plans"]:
        for config in root["configurations"]:
            for arm in ARMS:
                values.append({"root": root, "config": config, "arm": arm})
    return values


def task_id(task: Mapping[str, Any]) -> str:
    root = task["root"]
    return f"{root['opponent_mix']}-root{root['source_root_id'].split('root')[-1]}-seat{task['config']['focal_anchor_seat']}-{task['arm']}"


def stage_path(task: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "stages" / (task_id(task) + ".json"))


def execute_stage(task: Mapping[str, Any]) -> dict[str, Any]:
    """进程内独立装载候选，执行一条冻结双桌臂。"""

    root = task["root"]
    config = task["config"]
    arm = str(task["arm"])
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = [natural.stage.TablePlan.from_json(row) for row in config["tables"]]
    scorer = ActionValueScorer("r14-stage-style-confirmation",
                               CANDIDATE.read_text(encoding="utf-8"))
    result = natural.run_arm_stage(
        arm=arm, plans=plans, candidate_scorer=scorer,
        opponent_policies=contract["panel"]["opponent_scenarios"][root["opponent_mix"]]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=ValueAnalysisLimits())
    return {
        "task_id": task_id(task),
        "root_identity": {key: root[key] for key in (
            "source_root_id", "root_content_digest", "independence_id", "opponent_mix")},
        "config_digest": analysis.digest(config),
        "focal_anchor_seat": config["focal_anchor_seat"],
        "arm": arm,
        "stage": result,
    }


def run() -> None:
    """执行固定 1,024 张桌；只允许恢复已完整落盘的任务。"""

    manifest = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization))
    pending = []
    completed_tables = 0
    for task in tasks(manifest):
        path = stage_path(task)
        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("stage", {}).get("status") != "complete" \
                    or len(row["stage"].get("tables") or []) != 2:
                raise RuntimeError("既有确认阶段不完整：" + str(path))
            completed_tables += 2
        else:
            pending.append(task)
    reservation = ledger.reserve(
        step_id="independent-confirmation:fixed-sample", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="固定样本独立确认；异常按未完成预留保守结算")
    failures = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {pool.submit(execute_stage, task): task for task in pending}
            for future in concurrent.futures.as_completed(futures):
                task = futures[future]
                try:
                    row = future.result()
                    if row["stage"]["status"] != "complete" \
                            or len(row["stage"].get("tables") or []) != 2:
                        raise RuntimeError("确认阶段未完整")
                    write_json(stage_path(task), row)
                    completed_tables += 2
                    if completed_tables % 64 == 0 or completed_tables == manifest["planned_tables"]:
                        print(json.dumps({"completed_tables": completed_tables,
                                          "planned_tables": manifest["planned_tables"]},
                                         ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    failures.append({"task_id": task_id(task),
                                     "error": type(exc).__name__ + ": " + str(exc)})
    finally:
        ledger.settle(reservation, usage_unknown=True,
                      note="中断保守结算；成功后按完整阶段文件复核实际桌数")
    all_files = list((_project_file(_PROJECT_ROOT, OUT / "stages")).glob("*.json")) if (_project_file(_PROJECT_ROOT, OUT / "stages")).exists() else []
    actual_tables = 0
    for path in all_files:
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("stage", {}).get("status") == "complete":
            actual_tables += len(row["stage"].get("tables") or [])
    ledger.settle(reservation, actual=actual_tables,
                  note="按全部完整确认阶段文件结算；恢复项纳入批次总额")
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r14-stage-style-confirmation-run/1",
        "stage_files": len(all_files), "actual_tables": actual_tables,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or len(all_files) != SOURCE_UNITS * len(ARMS) \
            or actual_tables != PLANNED_TABLES:
        raise RuntimeError("独立确认执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual_tables}, ensure_ascii=False))


def focal_score(table: Mapping[str, Any]) -> int:
    participants = table["stage_situation"]["participant_ids_by_seat"]
    seat = participants.index(natural.FOCAL_PARTICIPANT)
    return int(table["scores_by_seat"][seat])


def exact_sign_flip_p(values: list[float]) -> dict[str, Any]:
    """对根级配对差做完整符号翻转分布，零差不虚增证据。"""

    fractions = [Fraction(str(value)) for value in values if value != 0]
    observed = sum(fractions, Fraction(0))
    distribution: dict[Fraction, int] = {Fraction(0): 1}
    for value in fractions:
        magnitude = abs(value)
        updated: dict[Fraction, int] = {}
        for subtotal, count in distribution.items():
            updated[subtotal + magnitude] = updated.get(subtotal + magnitude, 0) + count
            updated[subtotal - magnitude] = updated.get(subtotal - magnitude, 0) + count
        distribution = updated
    total = 2 ** len(fractions)
    extreme = sum(count for value, count in distribution.items() if value >= observed)
    return {
        "nonzero_roots": len(fractions),
        "observed_sum": float(observed),
        "distribution_states": len(distribution),
        "extreme_assignments": extreme,
        "total_assignments": total,
        "one_sided_p": extreme / total if total else 1.0,
    }


def stratified_summary(root_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """按 H/M 根等权计算均值、标准误与单侧 95% 正态下界。"""

    by_mix = {mix: [float(row["u_delta_low"]) for row in root_rows
                    if row["mix"] == mix] for mix in MIXES}
    means = {mix: statistics.fmean(values) for mix, values in by_mix.items()}
    variances = {mix: statistics.variance(values) for mix, values in by_mix.items()}
    standard_error = math.sqrt(sum(variances[mix] / len(by_mix[mix]) for mix in MIXES)) / 2
    overall = sum(means.values()) / 2
    lower = overall - 1.6448536269514722 * standard_error
    return {
        "overall_mean": overall,
        "by_mix_mean": means,
        "by_mix_variance": variances,
        "stratified_standard_error": standard_error,
        "one_sided_95_normal_lower": lower,
    }


def analyze() -> None:
    """固定样本全部完成后一次分析；不追加根、不修改候选或阈值。"""

    manifest = verify_manifest()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary.get("failures") or summary.get("actual_tables") != PLANNED_TABLES:
        raise RuntimeError("确认执行未完整，拒绝分析")
    seat_rows = []
    all_tables = []
    for root in manifest["root_plans"]:
        for config in root["configurations"]:
            pair = {}
            for arm in ARMS:
                task = {"root": root, "config": config, "arm": arm}
                row = json.loads(stage_path(task).read_text(encoding="utf-8"))
                if row["root_identity"]["root_content_digest"] != root["root_content_digest"] \
                        or row["config_digest"] != analysis.digest(config):
                    raise RuntimeError("确认阶段身份漂移")
                pair[arm] = row["stage"]
                all_tables.extend(row["stage"]["tables"])
            baseline = pair["baseline"]
            candidate = pair["candidate"]
            seat_rows.append({
                "mix": root["opponent_mix"],
                "source_root_id": root["source_root_id"],
                "root_content_digest": root["root_content_digest"],
                "focal_anchor_seat": config["focal_anchor_seat"],
                "baseline_stage_score": baseline["focal_stage_score"],
                "candidate_stage_score": candidate["focal_stage_score"],
                "stage_score_delta": candidate["focal_stage_score"] - baseline["focal_stage_score"],
                "baseline_u_low": baseline["u_low"], "baseline_u_high": baseline["u_high"],
                "candidate_u_low": candidate["u_low"], "candidate_u_high": candidate["u_high"],
                "u_delta_low": candidate["u_low"] - baseline["u_high"],
                "u_delta_high": candidate["u_high"] - baseline["u_low"],
                "first_table_delta": (focal_score(candidate["tables"][0])
                                      - focal_score(baseline["tables"][0])),
            })
    audit = natural.execution_audit.review_tables(all_tables)
    root_rows = []
    for root in manifest["root_plans"]:
        rows = [row for row in seat_rows if row["source_root_id"] == root["source_root_id"]]
        if len(rows) != 4:
            raise RuntimeError("确认根缺少四座位")
        root_rows.append({
            "mix": root["opponent_mix"],
            "source_root_id": root["source_root_id"],
            "u_delta_low": statistics.fmean(row["u_delta_low"] for row in rows),
            "u_delta_high": statistics.fmean(row["u_delta_high"] for row in rows),
            "stage_score_delta": statistics.fmean(row["stage_score_delta"] for row in rows),
            "first_table_delta": statistics.fmean(row["first_table_delta"] for row in rows),
        })
    unresolved = [row for row in seat_rows
                  if row["baseline_u_low"] != row["baseline_u_high"]
                  or row["candidate_u_low"] != row["candidate_u_high"]]
    effect = stratified_summary(root_rows)
    randomization = exact_sign_flip_p([row["u_delta_low"] for row in root_rows])
    stage_score_mean = statistics.fmean(row["stage_score_delta"] for row in root_rows)
    positive_by_mix = {mix: sum(row["u_delta_low"] > 0 for row in root_rows if row["mix"] == mix)
                       for mix in MIXES}
    negative_by_mix = {mix: sum(row["u_delta_low"] < 0 for row in root_rows if row["mix"] == mix)
                       for mix in MIXES}
    gate_checks = {
        "execution_failures": bool(audit["zero_internal_failures_verified"]),
        "unresolved_intervals": len(unresolved) == 0,
        "overall_mean_effect": effect["overall_mean"] >= MINIMUM_MEAN_EFFECT,
        "each_mix_nonnegative": all(effect["by_mix_mean"][mix] >= 0 for mix in MIXES),
        "exact_sign_flip": randomization["one_sided_p"] <= ONE_SIDED_ALPHA,
        "normal_lower_bound": effect["one_sided_95_normal_lower"] > 0,
        "stage_score_delta": stage_score_mean > 0,
        "positive_root_each_mix": all(positive_by_mix[mix] > 0 for mix in MIXES),
    }
    passed = all(gate_checks.values())
    result = {
        "schema": "r14-stage-style-independent-confirmation-result/1",
        "status": ("PASS_R14_INDEPENDENT_CONFIRMATION" if passed
                   else "INCONCLUSIVE_R14_INDEPENDENT_CONFIRMATION"),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidate_sha256": manifest["candidate_sha256"],
        "independent_roots": ROOT_COUNT,
        "roots_per_mix": {mix: len(ROOTS) for mix in MIXES},
        "effect": effect,
        "exact_sign_flip": randomization,
        "stage_score_delta_mean": stage_score_mean,
        "positive_roots_by_mix": positive_by_mix,
        "negative_roots_by_mix": negative_by_mix,
        "unresolved_seat_units": len(unresolved),
        "gate_checks": gate_checks,
        "execution_audit": audit,
        "strength_claim": passed,
        "release_eligible": False,
        "next": ("进入性能优化空间审查、扩展对手池与官方赛事发布门禁" if passed
                 else "不得扩样追认；回到公开规则态父代路由器作为下一条可证伪结构路线"),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "seat-units.json"), {"schema": "r14-confirmation-seat-units/1",
                                          "rows": seat_rows})
    write_json(_project_file(_PROJECT_ROOT, OUT / "root-units.json"), {"schema": "r14-confirmation-root-units/1",
                                          "rows": root_rows})
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    globals()[args.operation]()
