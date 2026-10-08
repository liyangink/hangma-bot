"""R18 P4 正式 BotPolicy 完整桌赛非劣预检（全新同牌墙换座来源）。"""

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
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-table-preflight-01-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
CANDIDATE = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/P4/normalized-v2/candidate.py')
)
HIDDEN_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-hidden-admission-01-20260922/result.json')
PANEL_SEED = 2026100118
MIXES = ("H", "M")
ROOTS = (1, 2)
SEATS = (0, 1, 2, 3)
ARMS = ("baseline", "candidate")
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
        for mix in MIXES
        for root in ROOTS
        for seat in SEATS
    ]


def source_paths() -> list[Path]:
    return [
        Path(__file__),
        CONTRACT,
        CANDIDATE,
        HIDDEN_RESULT,
        Path(natural.__file__),
    ]


def prepare() -> None:
    """冻结 64 张完整桌、候选身份、同牌墙换座计划与非劣判据。"""

    if OUT.exists():
        raise SystemExit("P4 桌赛预检目录已存在；拒绝覆盖")
    hidden = json.loads(HIDDEN_RESULT.read_text(encoding="utf-8"))
    if (
        hidden.get("status") != "PASS_HIDDEN_OPPORTUNITY"
        or hidden.get("candidate_sha256") != digest(CANDIDATE)
    ):
        raise ValueError("P4 候选未以当前身份通过隐藏机会门")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p4-table-preflight-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P4通过开发题、2048世界尾部压力及一次性隐藏机会门",
        "scope": "稳定V2与冻结P4；全新H/M各2根、4座位、每阶段2张完整桌；安全预检，不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r18-p4-table-preflight-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "candidate_path": str(CANDIDATE),
        "candidate_sha256": digest(CANDIDATE),
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
        "workers": 4,
        "value_analysis_limits": {
            "max_expansions": LIMITS.max_expansions,
            "max_routes_per_candidate": LIMITS.max_routes_per_candidate,
        },
        "source_relation": "全新panel_seed；不复用机会题、反事实世界或R17桌赛根",
        "gate": {
            "all_tables_complete": True,
            "zero_runtime_failures": True,
            "candidate_request_errors": 0,
            "candidate_degraded_plans": 0,
            "paired_stage_score_delta_mean": ">=0",
            "negative_paired_stage_units": 0,
        },
        "interpretation": "若自然桌零触发，只证明正式接缝和非机会窗口安全；机会效果由独立题库/反事实证明",
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({
        "status": "PREPARED",
        "source_units": SOURCE_UNITS,
        "planned_tables": PLANNED_TABLES,
    }, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if digest(CANDIDATE) != manifest["candidate_sha256"]:
        raise ValueError("P4 候选摘要漂移")
    if digest(HIDDEN_RESULT) != manifest["hidden_result_sha256"]:
        raise ValueError("P4 隐藏门结果漂移")
    if digest(CONTRACT) != manifest["contract_sha256"]:
        raise ValueError("桌赛合同漂移")
    guard.verify(manifest["runtime"])
    return manifest


async def audit_requests(requests: list[Any], source: str) -> dict[str, Any]:
    """经正式 BotPolicy 接口复算焦点请求，记录触发、行为变化和降级。"""

    candidate = ActionValuePolicy(ActionValueScorer("r18-P4-table-audit", source))
    baseline = ComparableHeuristicPolicyV2(monotonic=lambda: 800.0)
    counts = {
        "requests": 0,
        "policy_errors": 0,
        "degraded_plans": 0,
        "changed_top_actions": 0,
        "opportunity_overlay_present": 0,
        "opportunity_triggered": 0,
    }
    problems = []
    for request in requests:
        counts["requests"] += 1
        budget = DecisionBudget(810.0, 820.0, 830.0)
        try:
            candidate_plan = await candidate.choose(request, budget)
            baseline_plan = await baseline.choose(request, budget)
        except Exception as exc:  # noqa: BLE001 - 预检记录候选全异常面
            counts["policy_errors"] += 1
            problems.append(type(exc).__name__ + ": " + str(exc)[:240])
            continue
        if candidate_plan.degraded_reasons:
            counts["degraded_plans"] += 1
        if (
            candidate_plan.candidates[0].action_key
            != baseline_plan.candidates[0].action_key
        ):
            counts["changed_top_actions"] += 1
        overlays = []
        for item in candidate_plan.candidates:
            trace = item.score_trace or {}
            detail = trace.get("detail") or {}
            overlay = detail.get("r18_opportunity_overlay")
            if isinstance(overlay, Mapping):
                overlays.append(overlay)
        if overlays:
            counts["opportunity_overlay_present"] += 1
        if any(overlay.get("triggered") is True for overlay in overlays):
            counts["opportunity_triggered"] += 1
    return {"counts": counts, "problems": problems}


def execute_stage(arm: str, source_row: Mapping[str, Any]) -> dict[str, Any]:
    """子进程独立装配一条双桌臂；候选臂额外复算收到的公开请求。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source_row["mix"]),
        root_index=int(source_row["root_index"]),
        focal_seat=int(source_row["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    source = CANDIDATE.read_text(encoding="utf-8")
    scorer = ActionValueScorer("r18-P4-table", source)
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm=arm,
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
        request_audit = asyncio.run(audit_requests(requests, source))
        if request_audit["counts"]["policy_errors"]:
            stage["status"] = "error"
            stage["usable"] = False
            stage["error"] = "P4 请求复算存在策略异常"
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
    """并行执行冻结的 32 条双桌臂，并支持完整文件级恢复。"""

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
        step_id="r18-p4:table-preflight",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="P4正式BotPolicy全新来源双桌安全预检",
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
                except Exception as exc:  # noqa: BLE001
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
        "schema": "r18-p4-table-preflight-run/1",
        "stage_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != SOURCE_UNITS * len(ARMS):
        raise RuntimeError("P4桌赛预检执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    """按来源成对核对非劣、运行可靠性和自然触发数。"""

    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary.get("failures") or run_summary.get("actual_tables") != PLANNED_TABLES:
        raise ValueError("P4桌赛执行不完整，拒绝分析")
    all_tables = []
    paired = []
    audit_counts = {
        "requests": 0,
        "policy_errors": 0,
        "degraded_plans": 0,
        "changed_top_actions": 0,
        "opportunity_overlay_present": 0,
        "opportunity_triggered": 0,
    }
    audit_problems = []
    for source_row in sources():
        baseline = json.loads(
            stage_path("baseline", source_row).read_text(encoding="utf-8")
        )["stage"]
        candidate_doc = json.loads(
            stage_path("candidate", source_row).read_text(encoding="utf-8")
        )
        candidate = candidate_doc["stage"]
        all_tables.extend(baseline["tables"])
        all_tables.extend(candidate["tables"])
        request_audit = candidate_doc.get("request_audit") or {}
        for key in audit_counts:
            audit_counts[key] += int((request_audit.get("counts") or {}).get(key, 0))
        audit_problems.extend(request_audit.get("problems") or [])
        paired.append({
            **source_row,
            "baseline_stage_score": baseline["focal_stage_score"],
            "candidate_stage_score": candidate["focal_stage_score"],
            "stage_score_delta": (
                candidate["focal_stage_score"] - baseline["focal_stage_score"]
            ),
            "u_delta_low": candidate["u_low"] - baseline["u_high"],
            "u_delta_high": candidate["u_high"] - baseline["u_low"],
            "score_trajectory_equal": [
                table["scores_by_seat"] for table in candidate["tables"]
            ] == [table["scores_by_seat"] for table in baseline["tables"]],
        })
    execution = natural.execution_audit.review_tables(all_tables)
    deltas = [int(row["stage_score_delta"]) for row in paired]
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
    checks = {
        "all_tables_complete": run_summary["actual_tables"] == PLANNED_TABLES,
        "zero_runtime_failures": execution["zero_internal_failures_verified"] is True,
        "candidate_request_errors": audit_counts["policy_errors"] == 0,
        "candidate_degraded_plans": audit_counts["degraded_plans"] == 0,
        "paired_stage_score_delta_mean": statistics.fmean(deltas) >= 0,
        "negative_paired_stage_units": sum(value < 0 for value in deltas) == 0,
    }
    passed = all(checks.values())
    result = {
        "schema": "r18-p4-table-preflight-result/1",
        "status": "PASS_R18_P4_TABLE_PREFLIGHT" if passed else "FAIL_R18_P4_TABLE_PREFLIGHT",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidate_sha256": manifest["candidate_sha256"],
        "tables": PLANNED_TABLES,
        "source_units": SOURCE_UNITS,
        "overall": {
            "stage_score_delta_mean": statistics.fmean(deltas),
            "negative_units": sum(value < 0 for value in deltas),
            "positive_units": sum(value > 0 for value in deltas),
            "zero_units": sum(value == 0 for value in deltas),
            "score_trajectory_equal_units": sum(
                row["score_trajectory_equal"] for row in paired
            ),
            "u_delta_low_mean": statistics.fmean(row["u_delta_low"] for row in paired),
            "u_delta_high_mean": statistics.fmean(row["u_delta_high"] for row in paired),
        },
        "by_mix": by_mix,
        "request_audit_counts": audit_counts,
        "request_audit_problems": audit_problems,
        "execution_review": execution,
        "gate_checks": checks,
        "natural_trigger_interpretation": (
            "本批自然桌出现P4触发；效果须结合配对桌差和机会证据复核"
            if audit_counts["opportunity_triggered"]
            else "本批自然桌未出现四财神飘触发；本结果只证明接缝/回退安全与桌赛非劣，不估计机会收益频率"
        ),
        "strength_claim": False,
        "confirmation_eligible": passed,
        "release_eligible": False,
        "next": (
            "扩展多手牌P4开发/隐藏题，并把P4作为Pareto机会精英进入下一代"
            if passed else
            "停止晋级；按失败来源修复正式接缝或收紧触发"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "paired-units.json"), {
        "schema": "r18-p4-table-preflight-paired/1",
        "rows": paired,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    globals()[args.operation]()
