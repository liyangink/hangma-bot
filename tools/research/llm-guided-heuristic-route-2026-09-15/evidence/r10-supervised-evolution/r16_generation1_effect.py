"""R16 代际 1：在全新 H/M 来源上评价通过零桌门的目标优先候选。"""

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
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-generation1-effect-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R16-CONDITIONAL-SETTLEMENT-GOAL-FIRST-EVOLUTION-PLAN-2026-09-21.md')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921')
PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/behavior-preflight-02/result.json')
RULE_GOLD = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/rule-gold-verification.json')
MATH_CHECK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/math-check.json')
CONTRACT_CHECK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/contract-check.json')
BASELINE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026092819
MIXES = ("H", "M")
ROOTS = tuple(range(1, 9))
SEATS = (0, 1, 2, 3)
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sources() -> list[dict[str, Any]]:
    return [{"mix": mix, "root_index": root, "focal_seat": seat,
             "source_id": f"{mix}:r{root:02d}:s{seat}"}
            for mix in MIXES for root in ROOTS for seat in SEATS]


def passing_candidates() -> dict[str, Path]:
    """只读取已冻结零桌结果，不在效果运行中重新选择候选。"""

    result = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    passed = {
        str(row["candidate_id"]): _project_file(_PROJECT_ROOT, AUTHOR / str(row["candidate_id"]) / "candidate.py")
        for row in result.get("candidates", [])
        if row.get("status") == "PASS_R16_ZERO_TABLE_GATE"
        and all(row.get("gate_checks", {}).values())
    }
    if not passed:
        raise RuntimeError("R16代际1没有通过冻结零桌门的候选")
    if set(passed) - {"A", "B"}:
        raise RuntimeError("零桌结果含未预登记候选")
    return dict(sorted(passed.items()))


def source_paths(candidates: Mapping[str, Path]) -> list[Path]:
    return [Path(__file__), PLAN, PREFLIGHT, RULE_GOLD, MATH_CHECK, CONTRACT_CHECK,
            BASELINE, CONTRACT,
            Path(natural.__file__), *candidates.values()]


def prepare() -> None:
    """冻结新来源、通过零桌门的候选及完整两桌预算。"""

    if OUT.exists():
        raise SystemExit("R16代际1输出已存在；拒绝覆盖")
    candidates = passing_candidates()
    rule_gold = json.loads(RULE_GOLD.read_text(encoding="utf-8"))
    math_check = json.loads(MATH_CHECK.read_text(encoding="utf-8"))
    contract_check = json.loads(CONTRACT_CHECK.read_text(encoding="utf-8"))
    if (rule_gold.get("status") != "PASS" or math_check.get("status") != "PASS"
            or contract_check.get("status") != "PASS"
            or not all(contract_check.get("checks", {}).values())):
        raise RuntimeError("R16规则金例、目标数学或受限执行合同复核未通过")
    if set(candidates) != {"B"} or math_check.get("candidate_sha256") != digest(candidates["B"]):
        raise RuntimeError("R16代际1通过候选与独立数学复核身份不一致")
    for candidate_id, path in candidates.items():
        ActionValueScorer("r16-generation1-precheck-" + candidate_id,
                          path.read_text(encoding="utf-8"))
    arms = ["baseline", *["candidate:" + item for item in candidates]]
    planned_tables = SOURCE_UNITS * len(arms) * 2
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r16-generation1-effect-01",
        accounts={"tables_full": planned_tables}, issued_by="lead",
        issued_at_utc=search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "R16候选通过226个既有公开窗口的目标相关性、阶段账消融、合同与延迟门",
        "scope": "稳定V2及通过零桌门的R16代际1候选；H/M各8根×4座位×完整两桌；开发选择，不确认不发布",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r16-generation1-effect/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths(candidates)
                                 + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "plan": str(PLAN), "plan_sha256": digest(PLAN),
        "preflight": str(PREFLIGHT), "preflight_sha256": digest(PREFLIGHT),
        "rule_gold": str(RULE_GOLD), "rule_gold_sha256": digest(RULE_GOLD),
        "math_check": str(MATH_CHECK), "math_check_sha256": digest(MATH_CHECK),
        "contract_check": str(CONTRACT_CHECK),
        "contract_check_sha256": digest(CONTRACT_CHECK),
        "baseline_reference": str(BASELINE), "baseline_sha256": digest(BASELINE),
        "candidates": {item: {"path": str(path), "sha256": digest(path)}
                       for item, path in candidates.items()},
        "contract": str(CONTRACT), "contract_sha256": digest(CONTRACT),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": PANEL_SEED, "mixes": list(MIXES),
        "root_indices": list(ROOTS), "focal_seats": list(SEATS),
        "source_units": SOURCE_UNITS, "tables_per_stage": 2,
        "arms": arms, "planned_tables": planned_tables, "workers": 4,
        "gate": {
            "overall_u_delta_low_mean": ">0",
            "each_mix_u_delta_low_mean": ">=0",
            "at_least_one_mix_u_delta_low_mean": ">0",
            "positive_u_units_distinct_roots_min": 2,
            "positive_u_units_distinct_seats_min": 2,
            "execution_failures": 0,
        },
        "diagnostics_not_gates": [
            "first_table_delta_mean", "stage_score_delta_mean",
            "stage_score_delta_quantiles", "fourth_place_rate", "unresolved_rate",
        ],
        "first_table_policy": "记录但不淘汰；全部来源执行完整两桌",
        "strength_claim": False, "confirmation_reserved": 0,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED", "candidates": list(candidates),
                      "sources": SOURCE_UNITS, "planned_tables": planned_tables},
                     ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    for key, sha_key in (("plan", "plan_sha256"), ("preflight", "preflight_sha256"),
                         ("rule_gold", "rule_gold_sha256"),
                         ("math_check", "math_check_sha256"),
                         ("contract_check", "contract_check_sha256"),
                         ("baseline_reference", "baseline_sha256"),
                         ("contract", "contract_sha256")):
        if digest(Path(manifest[key])) != manifest[sha_key]:
            raise RuntimeError(f"冻结输入摘要漂移：{key}")
    for candidate_id, item in manifest["candidates"].items():
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("冻结候选摘要漂移：" + candidate_id)
    guard.verify(manifest["runtime"])
    return manifest


def execute_stage(arm: str, source: Mapping[str, Any],
                  candidates: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """每个进程独立装载候选并运行一个真实两桌阶段。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED)
    candidate_id = arm.split(":", 1)[1] if arm.startswith("candidate:") else next(iter(candidates))
    candidate_path = Path(candidates[candidate_id]["path"])
    scorer = ActionValueScorer("r16-goal-first-" + candidate_id,
                               candidate_path.read_text(encoding="utf-8"))
    result = natural.run_arm_stage(
        arm="candidate" if arm.startswith("candidate:") else "baseline",
        plans=plans, candidate_scorer=scorer,
        opponent_policies=contract["panel"]["opponent_scenarios"][str(source["mix"])]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=ValueAnalysisLimits())
    result["arm"] = arm
    return {"arm": arm, "source": dict(source), "stage": result}


def _stage_path(arm: str, source: Mapping[str, Any]) -> Path:
    safe_arm = arm.replace(":", "-")
    return _project_file(_PROJECT_ROOT, OUT / "stages" / f"{safe_arm}-{str(source['source_id']).replace(':', '-')}.json")


def run() -> None:
    """并行执行全部冻结阶段；已落盘完整任务可复核后跳过。"""

    manifest = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization))
    pending = []
    completed_tables = 0
    for source in sources():
        for arm in manifest["arms"]:
            path = _stage_path(arm, source)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if row.get("stage", {}).get("status") != "complete" \
                        or len(row["stage"].get("tables") or []) != 2:
                    raise RuntimeError("既有阶段文件不完整：" + str(path))
                completed_tables += 2
            else:
                pending.append((arm, source))
    reservation = ledger.reserve(
        step_id="r16-generation1:full-stages", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="R16代际1全新来源完整两桌；异常按未完成预留保守结算")
    failures = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {pool.submit(execute_stage, arm, source, manifest["candidates"]): (arm, source)
                       for arm, source in pending}
            for future in concurrent.futures.as_completed(futures):
                arm, source = futures[future]
                try:
                    row = future.result()
                    if row["stage"]["status"] != "complete" \
                            or len(row["stage"].get("tables") or []) != 2:
                        raise RuntimeError("阶段未完整")
                    write_json(_stage_path(arm, source), row)
                    completed_tables += 2
                    print(json.dumps({"arm": arm, "source": source["source_id"],
                                      "completed_tables": completed_tables},
                                     ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    failures.append({"arm": arm, "source": source,
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
                  note="按全部完整阶段文件结算；重跑跳过项仍纳入批次总额")
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r16-generation1-run/1", "stage_files": len(all_files),
        "actual_tables": actual_tables, "failures": failures,
        "spent": ledger.account_summary(),
    })
    expected_files = SOURCE_UNITS * len(manifest["arms"])
    if failures or len(all_files) != expected_files \
            or actual_tables != manifest["planned_tables"]:
        raise RuntimeError("R16代际1执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual_tables}, ensure_ascii=False))


def mean(rows: list[dict[str, Any]], key: str) -> float:
    return statistics.fmean(float(row[key]) for row in rows)


def quantiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    def pick(fraction: float) -> float:
        return ordered[round((len(ordered) - 1) * fraction)]
    return {"min": ordered[0], "p10": pick(0.10), "median": pick(0.50),
            "p90": pick(0.90), "max": ordered[-1]}


def focal_score(table: Mapping[str, Any]) -> int:
    participants = table["stage_situation"]["participant_ids_by_seat"]
    seat = participants.index(natural.FOCAL_PARTICIPANT)
    return int(table["scores_by_seat"][seat])


def fourth(stage: Mapping[str, Any]) -> bool:
    interval = stage.get("u_interval") or {}
    return interval.get("a") == 4 and interval.get("b") == 4


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sources": len(rows),
        "first_table_delta_mean": mean(rows, "first_table_delta"),
        "stage_score_delta_mean": mean(rows, "stage_score_delta"),
        "stage_score_delta_quantiles": quantiles([float(row["stage_score_delta"]) for row in rows]),
        "u_delta_low_mean": mean(rows, "u_delta_low"),
        "u_delta_high_mean": mean(rows, "u_delta_high"),
        "candidate_fourth_rate": mean(rows, "candidate_fourth"),
        "baseline_fourth_rate": mean(rows, "baseline_fourth"),
        "candidate_unresolved_rate": mean(rows, "candidate_unresolved"),
        "baseline_unresolved_rate": mean(rows, "baseline_unresolved"),
    }


def analyze() -> None:
    """逐候选按预登记 U 同向门裁定，积分仅作诊断。"""

    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary.get("failures") or run_summary.get("actual_tables") != manifest["planned_tables"]:
        raise RuntimeError("执行未完整，拒绝分析")
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    all_tables = []
    for source in sources():
        for arm in manifest["arms"]:
            stage = json.loads(_stage_path(arm, source).read_text(encoding="utf-8"))["stage"]
            by_key[(arm, str(source["source_id"]))] = stage
            all_tables.extend(stage["tables"])
    audit = natural.execution_audit.review_tables(all_tables)
    candidate_results = []
    all_paired = {}
    for candidate_id in manifest["candidates"]:
        arm = "candidate:" + candidate_id
        paired = []
        for source in sources():
            source_id = str(source["source_id"])
            baseline = by_key[("baseline", source_id)]
            candidate = by_key[(arm, source_id)]
            paired.append({
                **dict(source), "candidate_id": candidate_id,
                "baseline_first_table_score": focal_score(baseline["tables"][0]),
                "candidate_first_table_score": focal_score(candidate["tables"][0]),
                "first_table_delta": (focal_score(candidate["tables"][0])
                                      - focal_score(baseline["tables"][0])),
                "baseline_stage_score": baseline["focal_stage_score"],
                "candidate_stage_score": candidate["focal_stage_score"],
                "stage_score_delta": candidate["focal_stage_score"] - baseline["focal_stage_score"],
                "u_delta_low": candidate["u_low"] - baseline["u_high"],
                "u_delta_high": candidate["u_high"] - baseline["u_low"],
                "candidate_unresolved": candidate["unresolved"],
                "baseline_unresolved": baseline["unresolved"],
                "candidate_fourth": fourth(candidate),
                "baseline_fourth": fourth(baseline),
            })
        overall = summarize(paired)
        by_mix = {mix: summarize([row for row in paired if row["mix"] == mix])
                  for mix in MIXES}
        positive = [row for row in paired if row["u_delta_low"] > 0]
        gate_checks = {
            "execution_failures": bool(audit["zero_internal_failures_verified"]),
            "overall_u_delta_low_mean": overall["u_delta_low_mean"] > 0,
            "each_mix_u_delta_low_mean": all(by_mix[mix]["u_delta_low_mean"] >= 0
                                               for mix in MIXES),
            "at_least_one_mix_u_delta_low_mean": any(by_mix[mix]["u_delta_low_mean"] > 0
                                                       for mix in MIXES),
            "positive_u_units_distinct_roots": len({row["root_index"] for row in positive}) >= 2,
            "positive_u_units_distinct_seats": len({row["focal_seat"] for row in positive}) >= 2,
        }
        passed = all(gate_checks.values())
        candidate_results.append({
            "candidate_id": candidate_id,
            "candidate_sha256": manifest["candidates"][candidate_id]["sha256"],
            "status": ("PASS_R16_GENERATION1_DEVELOPMENT_GATE" if passed
                       else "FAIL_R16_GENERATION1_DEVELOPMENT_GATE"),
            "overall": overall, "by_mix": by_mix,
            "positive_u_units": len(positive),
            "positive_u_distinct_roots": sorted({row["root_index"] for row in positive}),
            "positive_u_distinct_seats": sorted({row["focal_seat"] for row in positive}),
            "gate_checks": gate_checks,
        })
        all_paired[candidate_id] = paired
    passed_ids = [row["candidate_id"] for row in candidate_results
                  if row["status"] == "PASS_R16_GENERATION1_DEVELOPMENT_GATE"]
    result = {
        "schema": "r16-generation1-effect-result/1",
        "status": ("PASS_SOME_R16_GENERATION1_DEVELOPMENT_GATE" if passed_ids
                   else "FAIL_ALL_R16_GENERATION1_DEVELOPMENT_GATE"),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidates": candidate_results, "passed_candidate_ids": passed_ids,
        "execution_audit": audit, "strength_claim": False,
        "confirmation_eligible": False,
        "next": ("按冻结选择键保留至多一个，并以同一源码进入第二套全新开发来源"
                 if passed_ids else "进入R16代际2；若仍失败则回到文献与杭麻规则复盘"),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "paired-units.json"), {
        "schema": "r16-generation1-paired/1", "by_candidate": all_paired})
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    globals()[args.operation]()
