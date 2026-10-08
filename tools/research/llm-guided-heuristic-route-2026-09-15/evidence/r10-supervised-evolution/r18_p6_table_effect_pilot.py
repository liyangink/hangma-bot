"""R18 P6 正式 BotPolicy 相对 P5 的完整桌同墙换座效果首尺。"""

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
import asyncio
from collections import Counter
import concurrent.futures
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p6-table-effect-pilot-01-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p6-seven-pairs-01-20260922/generation/candidate.py')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/generation/candidate.py')
HIDDEN_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p6-hidden-admission-01-20260922/result.json')
PANEL_SEED = 2026101009
MIXES = ("H", "M")
ROOTS = (1, 2, 3, 4)
SEATS = (0, 1, 2, 3)
ARMS = ("parent", "candidate")
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)
PLANNED_TABLES = SOURCE_UNITS * len(ARMS) * 2
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sources() -> list[dict[str, Any]]:
    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": f"{mix}:r{root:02d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_paths() -> list[Path]:
    return [
        Path(__file__), CONTRACT, CANDIDATE, PARENT, HIDDEN_RESULT,
        Path(natural.__file__),
    ]


def prepare() -> None:
    """冻结 128 张完整桌、父子身份、配对计划与首尺分流判据。"""

    if OUT.exists():
        raise SystemExit("P6 桌赛效果首尺目录已存在；拒绝覆盖")
    hidden = json.loads(HIDDEN_RESULT.read_text(encoding="utf-8"))
    if (
        hidden.get("status") != "PASS_P6_HIDDEN"
        or hidden.get("candidate_sha256") != digest(CANDIDATE)
    ):
        raise ValueError("P6 候选未以当前身份通过隐藏机会门")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p6-table-effect-pilot-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P6通过开发预检及60根一次性新来源隐藏机会门",
        "scope": "冻结P5父代与P6；全新H/M各4根、4座位、每阶段2张完整桌；同墙换座效果首尺",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p6-table-effect-pilot-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "candidate_path": str(CANDIDATE),
        "candidate_sha256": digest(CANDIDATE),
        "parent_path": str(PARENT),
        "parent_sha256": digest(PARENT),
        "hidden_result_path": str(HIDDEN_RESULT),
        "hidden_result_sha256": digest(HIDDEN_RESULT),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "source_units": SOURCE_UNITS,
        "arms": list(ARMS),
        "tables_per_stage": 2,
        "planned_tables": PLANNED_TABLES,
        "workers": 8,
        "value_analysis_limits": {
            "max_expansions": LIMITS.max_expansions,
            "max_routes_per_candidate": LIMITS.max_routes_per_candidate,
        },
        "source_relation": "候选冻结后的新panel_seed；不复用发现、确认、开发或隐藏机会世界",
        "gate": {
            "all_tables_complete": True,
            "zero_internal_failures": True,
            "all_candidate_requests_action_value_scored": True,
            "candidate_request_errors": 0,
            "seven_pairs_triggered_requests": ">=1",
            "paired_stage_score_delta_mean_candidate_minus_parent": ">=0 opens expanded confirmation; <0 stops candidate",
            "negative_paired_stage_units": "reported but not gated in this 32-unit pilot",
        },
        "interpretation": "首尺只决定停止或扩样，不授予完整桌赛非劣、强度或发布资格",
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "source_units": SOURCE_UNITS,
        "planned_tables": PLANNED_TABLES,
    }, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if digest(CANDIDATE) != manifest["candidate_sha256"]:
        raise ValueError("P6 候选摘要漂移")
    if digest(PARENT) != manifest["parent_sha256"]:
        raise ValueError("P5 父代摘要漂移")
    if digest(HIDDEN_RESULT) != manifest["hidden_result_sha256"]:
        raise ValueError("P6 隐藏结果漂移")
    if digest(CONTRACT) != manifest["contract_sha256"]:
        raise ValueError("桌赛合同漂移")
    guard.verify(manifest["runtime"])
    return manifest


async def audit_requests(requests: list[Any], candidate_source: str, parent_source: str) -> dict[str, Any]:
    candidate = ActionValuePolicy(ActionValueScorer("r18-P6-table-audit", candidate_source))
    parent = ActionValuePolicy(ActionValueScorer("r18-P6-parent-table-audit", parent_source))
    counts = Counter()
    problems = []
    for request in requests:
        counts["requests"] += 1
        budget = DecisionBudget(810.0, 820.0, 830.0)
        try:
            candidate_plan = await candidate.choose(request, budget)
            parent_plan = await parent.choose(request, budget)
        except Exception as exc:  # noqa: BLE001 - 记录候选异常面
            counts["policy_errors"] += 1
            problems.append(type(exc).__name__ + ": " + str(exc)[:240])
            continue
        if candidate_plan.candidates[0].action_key != parent_plan.candidates[0].action_key:
            counts["changed_top_actions"] += 1
        overlays = []
        for item in candidate_plan.candidates:
            detail = ((item.score_trace or {}).get("detail") or {})
            overlay = detail.get("r18_opportunity_overlay")
            if isinstance(overlay, Mapping):
                overlays.append(overlay)
        if overlays:
            counts["opportunity_overlay_present"] += 1
        if any(row.get("triggered") is True for row in overlays):
            counts["opportunity_triggered"] += 1
        if any(
            row.get("structure") == "three_wealth_piao_cf_supported/v1"
            and row.get("triggered") is True
            for row in overlays
        ):
            counts["p3_triggered"] += 1
        dominance = []
        for item in candidate_plan.candidates:
            detail = ((item.score_trace or {}).get("detail") or {})
            overlay = detail.get("r18_gang_dominance_overlay")
            if isinstance(overlay, Mapping):
                dominance.append(overlay)
        if dominance:
            counts["gang_dominance_overlay_present"] += 1
        if any(row.get("triggered") is True for row in dominance):
            counts["gang_dominance_triggered"] += 1
        seven_pairs = []
        for item in candidate_plan.candidates:
            detail = ((item.score_trace or {}).get("detail") or {})
            overlay = detail.get("r18_seven_pairs_overlay")
            if isinstance(overlay, Mapping):
                seven_pairs.append(overlay)
        if seven_pairs:
            counts["seven_pairs_overlay_present"] += 1
        if any(row.get("triggered") is True for row in seven_pairs):
            counts["seven_pairs_triggered"] += 1
    return {"counts": dict(counts), "problems": problems}


def execute_stage(arm: str, source_row: Mapping[str, Any]) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source_row["mix"]),
        root_index=int(source_row["root_index"]),
        focal_seat=int(source_row["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    candidate_source = CANDIDATE.read_text(encoding="utf-8")
    parent_source = PARENT.read_text(encoding="utf-8")
    source = candidate_source if arm == "candidate" else parent_source
    scorer = ActionValueScorer("r18-P6-table-" + arm, source)
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="candidate",
        plans=plans,
        candidate_scorer=scorer,
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source_row["mix"])
        ]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
        decision_observer=requests.append if arm == "candidate" else None,
    )
    request_audit = None
    if arm == "candidate" and stage.get("status") == "complete":
        request_audit = asyncio.run(audit_requests(requests, candidate_source, parent_source))
        if request_audit["counts"].get("policy_errors", 0):
            stage["status"] = "error"
            stage["usable"] = False
            stage["error"] = "P6/P5 请求复算存在策略异常"
    return {
        "arm": arm,
        "source": dict(source_row),
        "stage": stage,
        "request_audit": request_audit,
    }


def stage_path(arm: str, source_row: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "stages" / (
        arm + "-" + str(source_row["source_id"]).replace(":", "-") + ".json"
    ))


def run() -> None:
    manifest = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for source_row in sources():
        for arm in ARMS:
            path = stage_path(arm, source_row)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if row.get("stage", {}).get("status") != "complete":
                    raise ValueError("既有阶段不完整：" + str(path))
                completed_tables += len(row["stage"].get("tables") or [])
            else:
                pending.append((arm, source_row))
    reservation = ledger.reserve(
        step_id="r18-p6:table-effect-pilot",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="P6相对P5全新来源同墙换座双桌效果首尺",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {
                pool.submit(execute_stage, arm, source_row): (arm, source_row)
                for arm, source_row in pending
            }
            for future in concurrent.futures.as_completed(futures):
                arm, source_row = futures[future]
                row = None
                try:
                    row = future.result()
                    count = len(row.get("stage", {}).get("tables") or [])
                    executed += count
                    if row["stage"]["status"] != "complete" or count != 2:
                        raise RuntimeError(row["stage"].get("error") or "阶段不完整")
                    write_json(stage_path(arm, source_row), row)
                    completed_tables += count
                    if completed_tables % 16 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001 - 批次保留完整失败证据
                    if row is None:
                        usage_unknown = True
                    failures.append({
                        "arm": arm,
                        "source_id": source_row["source_id"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按本次返回完整桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "stages")).glob("*.json")) if (_project_file(_PROJECT_ROOT, OUT / "stages")).exists() else []
    actual = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["stage"].get("tables") or [])
        for path in files
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p6-table-effect-pilot-run/1",
        "stage_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != SOURCE_UNITS * len(ARMS):
        raise RuntimeError("P6 桌赛效果首尺执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary.get("failures") or run_summary.get("actual_tables") != PLANNED_TABLES:
        raise ValueError("P6 桌赛效果首尺执行不完整，拒绝分析")
    all_tables = []
    candidate_tables = []
    paired = []
    audit_counts = Counter()
    audit_problems = []
    for source_row in sources():
        parent = json.loads(
            stage_path("parent", source_row).read_text(encoding="utf-8")
        )["stage"]
        candidate_doc = json.loads(
            stage_path("candidate", source_row).read_text(encoding="utf-8")
        )
        candidate = candidate_doc["stage"]
        all_tables.extend(parent["tables"])
        all_tables.extend(candidate["tables"])
        candidate_tables.extend(candidate["tables"])
        request_audit = candidate_doc.get("request_audit") or {}
        audit_counts.update(request_audit.get("counts") or {})
        audit_problems.extend(request_audit.get("problems") or [])
        paired.append({
            **source_row,
            "parent_stage_score": parent["focal_stage_score"],
            "candidate_stage_score": candidate["focal_stage_score"],
            "stage_score_delta": candidate["focal_stage_score"] - parent["focal_stage_score"],
            "u_delta_low": candidate["u_low"] - parent["u_high"],
            "u_delta_high": candidate["u_high"] - parent["u_low"],
            "score_trajectory_equal": [
                table["scores_by_seat"] for table in candidate["tables"]
            ] == [table["scores_by_seat"] for table in parent["tables"]],
        })
    execution = natural.execution_audit.review_tables(all_tables)
    candidate_execution = natural.execution_audit.review_tables(candidate_tables)
    recorded = execution["recorded_counts"]
    candidate_recorded = candidate_execution["recorded_counts"]
    failure_windows = sum(int(recorded[key]) for key in (
        "action_value_failed", "ambiguous_diagnostics", "unclassified_action_value",
    ))
    deltas = [int(row["stage_score_delta"]) for row in paired]
    checks = {
        "all_tables_complete": run_summary["actual_tables"] == PLANNED_TABLES,
        "zero_internal_failures": execution["zero_internal_failures_verified"] is True,
        "candidate_request_errors": audit_counts["policy_errors"] == 0,
        "all_candidate_requests_action_value_scored": (
            candidate_recorded["action_value_scored"] == audit_counts["requests"]
        ),
        "zero_action_value_failure_windows": failure_windows == 0,
        "paired_stage_score_delta_mean_nonnegative": statistics.fmean(deltas) >= 0,
        "seven_pairs_triggered_requests_positive": audit_counts["seven_pairs_triggered"] >= 1,
    }
    passed = all(checks.values())
    by_mix = {
        mix: {
            "units": sum(row["mix"] == mix for row in paired),
            "stage_score_delta_mean": statistics.fmean(
                row["stage_score_delta"] for row in paired if row["mix"] == mix
            ),
            "negative_units": sum(
                row["stage_score_delta"] < 0 for row in paired if row["mix"] == mix
            ),
        }
        for mix in MIXES
    }
    result = {
        "schema": "r18-p6-table-effect-pilot-result/1",
        "status": "PASS_R18_P6_TABLE_EFFECT_PILOT" if passed else "STOP_R18_P6_TABLE_EFFECT_PILOT",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidate_sha256": manifest["candidate_sha256"],
        "parent_sha256": manifest["parent_sha256"],
        "tables": PLANNED_TABLES,
        "source_units": SOURCE_UNITS,
        "overall": {
            "stage_score_delta_mean": statistics.fmean(deltas),
            "negative_units": sum(value < 0 for value in deltas),
            "positive_units": sum(value > 0 for value in deltas),
            "zero_units": sum(value == 0 for value in deltas),
            "score_trajectory_equal_units": sum(row["score_trajectory_equal"] for row in paired),
            "u_delta_low_mean": statistics.fmean(row["u_delta_low"] for row in paired),
            "u_delta_high_mean": statistics.fmean(row["u_delta_high"] for row in paired),
        },
        "by_mix": by_mix,
        "request_audit_counts": dict(audit_counts),
        "request_audit_problems": audit_problems,
        "execution_review": execution,
        "candidate_execution_review": candidate_execution,
        "action_value_failure_windows": failure_windows,
        "gate_checks": checks,
        "natural_trigger_interpretation": "本批必须出现P6七对触发；配对均值只作停止或扩样分流，不是确认结论",
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
        "next": (
            "冻结本批后转入更大独立同墙换座确认，并预登记非劣区间"
            if passed else
            "停止P6晋级；分析七对触发的负向来源，保留P5父代"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "paired-units.json"), {
        "schema": "r18-p6-table-effect-pilot-paired/1", "rows": paired,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    globals()[args.operation]()
