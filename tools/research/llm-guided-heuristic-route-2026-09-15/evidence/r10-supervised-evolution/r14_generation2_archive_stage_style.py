"""R14 代际 2：在代际 1 冻结来源上评价归档的阶段处境候选。"""

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


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r14-generation2-archive-stage-style-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R14-HM-ROBUST-POPULATION-EVOLUTION-PLAN-2026-09-21.md')
G1_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r14-generation1-effect-01-20260921')
G1_MANIFEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r14-generation1-effect-01-20260921/manifest.json')
G1_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r14-generation1-effect-01-20260921/result.json')
ARCHIVE_CLOSURE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/stage-style-20260920/stage-style-terra-max/batch-closure.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/stage-style-20260920/stage-style-terra-max/run/iterations/iter-01/generation/candidate.py')
BASELINE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026092470
MIXES = ("H", "M")
ROOTS = tuple(range(1, 9))
SEATS = (0, 1, 2, 3)
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)
PLANNED_TABLES = SOURCE_UNITS * 2


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sources() -> list[dict[str, Any]]:
    return [{"mix": mix, "root_index": root, "focal_seat": seat,
             "source_id": f"{mix}:r{root:02d}:s{seat}"}
            for mix in MIXES for root in ROOTS for seat in SEATS]


def source_paths() -> list[Path]:
    return [Path(__file__), PLAN, G1_MANIFEST, G1_RESULT, ARCHIVE_CLOSURE,
            CANDIDATE, BASELINE, CONTRACT, Path(natural.__file__)]


def g1_stage_path(source: Mapping[str, Any]) -> Path:
    """返回代际 1 已冻结的稳定 V2 阶段文件。"""

    suffix = str(source["source_id"]).replace(":", "-")
    return _project_file(_PROJECT_ROOT, G1_OUT / "stages" / f"baseline-{suffix}.json")


def prepare() -> None:
    """冻结归档候选、代际 1 基线证据和完整两桌预算。"""

    if OUT.exists():
        raise SystemExit("代际2输出已存在；拒绝覆盖")
    g1_result = json.loads(G1_RESULT.read_text(encoding="utf-8"))
    if g1_result.get("status") != "FAIL_R14_G1_DEVELOPMENT_GATE":
        raise RuntimeError("代际1失败结论漂移")
    archive = json.loads(ARCHIVE_CLOSURE.read_text(encoding="utf-8"))
    if archive.get("candidate_source_sha256") != digest(CANDIDATE):
        raise RuntimeError("归档候选摘要与既有开发证据不一致")
    if archive.get("versus_v2", {}).get("H", {}).get("mean_delta", 0) <= 0 \
            or archive.get("versus_v2", {}).get("M", {}).get("mean_delta") != 0:
        raise RuntimeError("归档候选不再满足 H 正向、M 不退化的选择依据")
    ActionValueScorer("r14-generation2-precheck", CANDIDATE.read_text(encoding="utf-8"))
    baseline_stages = {}
    for source in sources():
        path = g1_stage_path(source)
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("stage", {}).get("status") != "complete" \
                or len(row["stage"].get("tables") or []) != 2:
            raise RuntimeError("代际1稳定 V2 阶段不完整：" + str(path))
        baseline_stages[str(path)] = digest(path)
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r14-generation2-stage-style-01",
        accounts={"tables_full": PLANNED_TABLES}, issued_by="lead",
        issued_at_utc=search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "R14代际1失败后按档案复用原则，检验与完整阶段目标直接相连的冻结候选",
        "scope": "stage-style归档候选；H/M各8根×4座位×两桌；复用同源稳定V2基线；开发选择，不确认不发布",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r14-generation2-archive-stage-style/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "plan": str(PLAN), "plan_sha256": digest(PLAN),
        "generation1_manifest": str(G1_MANIFEST),
        "generation1_manifest_sha256": digest(G1_MANIFEST),
        "generation1_result": str(G1_RESULT),
        "generation1_result_sha256": digest(G1_RESULT),
        "archive_closure": str(ARCHIVE_CLOSURE),
        "archive_closure_sha256": digest(ARCHIVE_CLOSURE),
        "candidate": str(CANDIDATE), "candidate_sha256": digest(CANDIDATE),
        "baseline_reference": str(BASELINE), "baseline_sha256": digest(BASELINE),
        "contract": str(CONTRACT), "contract_sha256": digest(CONTRACT),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": PANEL_SEED, "mixes": list(MIXES),
        "root_indices": list(ROOTS), "focal_seats": list(SEATS),
        "source_units": SOURCE_UNITS, "tables_per_stage": 2,
        "candidate_arm": "candidate", "planned_tables": PLANNED_TABLES, "workers": 4,
        "baseline_reuse": {
            "source_batch": str(G1_OUT),
            "stage_files": baseline_stages,
            "reason": "同一冻结来源与稳定V2源码；避免重复消耗128张确定性基线桌",
        },
        "gate": {
            "overall_u_delta_low_mean": ">0",
            "each_mix_u_delta_low_mean": ">=0",
            "overall_stage_score_delta_mean": ">0",
            "at_least_one_mix_u_delta_low_mean": ">0",
            "positive_u_units_distinct_roots_min": 2,
            "positive_u_units_distinct_seats_min": 2,
            "execution_failures": 0,
        },
        "first_table_policy": "记录但不淘汰；候选全部来源执行完整两桌",
        "selection_status": "归档开发证据用于选择，因此本批属于第二开发来源，不是独立确认",
        "strength_claim": False, "confirmation_reserved": 0,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED", "sources": SOURCE_UNITS,
                      "planned_tables": PLANNED_TABLES}, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    for key, sha_key in (("plan", "plan_sha256"),
                         ("generation1_manifest", "generation1_manifest_sha256"),
                         ("generation1_result", "generation1_result_sha256"),
                         ("archive_closure", "archive_closure_sha256"),
                         ("candidate", "candidate_sha256"),
                         ("baseline_reference", "baseline_sha256"),
                         ("contract", "contract_sha256")):
        if digest(Path(manifest[key])) != manifest[sha_key]:
            raise RuntimeError(f"冻结输入摘要漂移：{key}")
    for path, expected in manifest["baseline_reuse"]["stage_files"].items():
        if digest(Path(path)) != expected:
            raise RuntimeError("冻结稳定 V2 阶段漂移：" + path)
    guard.verify(manifest["runtime"])
    return manifest


def execute_stage(source: Mapping[str, Any]) -> dict[str, Any]:
    """每个进程独立装载候选并运行一个真实两桌阶段。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED)
    scorer = ActionValueScorer("r14-stage-style", CANDIDATE.read_text(encoding="utf-8"))
    result = natural.run_arm_stage(
        arm="candidate", plans=plans, candidate_scorer=scorer,
        opponent_policies=contract["panel"]["opponent_scenarios"][str(source["mix"])]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=ValueAnalysisLimits())
    return {"arm": "candidate", "source": dict(source), "stage": result}


def _stage_path(source: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "stages" / f"candidate-{str(source['source_id']).replace(':', '-')}.json")


def run() -> None:
    """并行执行全部 128 张候选桌；稳定 V2 复用冻结结果。"""

    manifest = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization))
    pending = []
    completed_tables = 0
    for source in sources():
        path = _stage_path(source)
        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("stage", {}).get("status") != "complete" \
                    or len(row["stage"].get("tables") or []) != 2:
                raise RuntimeError("既有阶段文件不完整：" + str(path))
            completed_tables += 2
        else:
            pending.append(source)
    reservation = ledger.reserve(
        step_id="generation2:archive-stage-style", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="R14代际2归档候选完整两桌；异常按未完成预留保守结算")
    failures = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {pool.submit(execute_stage, source): source for source in pending}
            for future in concurrent.futures.as_completed(futures):
                source = futures[future]
                try:
                    row = future.result()
                    if row["stage"]["status"] != "complete" \
                            or len(row["stage"].get("tables") or []) != 2:
                        raise RuntimeError("阶段未完整")
                    write_json(_stage_path(source), row)
                    completed_tables += 2
                    print(json.dumps({"arm": "candidate", "source": source["source_id"],
                                      "completed_tables": completed_tables},
                                     ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    failures.append({"arm": "candidate", "source": source,
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
        "schema": "r14-generation2-run/1", "stage_files": len(all_files),
        "actual_tables": actual_tables, "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(all_files) != SOURCE_UNITS \
            or actual_tables != PLANNED_TABLES:
        raise RuntimeError("代际2执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual_tables}, ensure_ascii=False))


def mean(rows: list[dict[str, Any]], key: str) -> float:
    return statistics.fmean(float(row[key]) for row in rows)


def focal_score(table: Mapping[str, Any]) -> int:
    """按桌前阶段账中的参赛者座位顺序读取焦点积分。"""

    participants = table["stage_situation"]["participant_ids_by_seat"]
    seat = participants.index(natural.FOCAL_PARTICIPANT)
    return int(table["scores_by_seat"][seat])


def analyze() -> None:
    """按预登记 H/M 同向门裁定，第一桌不参与淘汰。"""

    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary.get("failures") or run_summary.get("actual_tables") != PLANNED_TABLES:
        raise RuntimeError("执行未完整，拒绝分析")
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    all_tables = []
    for source in sources():
        baseline_row = json.loads(g1_stage_path(source).read_text(encoding="utf-8"))
        candidate_row = json.loads(_stage_path(source).read_text(encoding="utf-8"))
        by_key[("baseline", str(source["source_id"]))] = baseline_row["stage"]
        by_key[("candidate", str(source["source_id"]))] = candidate_row["stage"]
        all_tables.extend(baseline_row["stage"]["tables"])
        all_tables.extend(candidate_row["stage"]["tables"])
    audit = natural.execution_audit.review_tables(all_tables)
    paired = []
    for source in sources():
        source_id = str(source["source_id"])
        baseline = by_key[("baseline", source_id)]
        candidate = by_key[("candidate", source_id)]
        paired.append({
            **dict(source),
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
        })
    overall = {
        "sources": len(paired),
        "first_table_delta_mean": mean(paired, "first_table_delta"),
        "stage_score_delta_mean": mean(paired, "stage_score_delta"),
        "u_delta_low_mean": mean(paired, "u_delta_low"),
        "u_delta_high_mean": mean(paired, "u_delta_high"),
    }
    by_mix = {}
    for mix in MIXES:
        rows = [row for row in paired if row["mix"] == mix]
        by_mix[mix] = {
            "sources": len(rows),
            "first_table_delta_mean": mean(rows, "first_table_delta"),
            "stage_score_delta_mean": mean(rows, "stage_score_delta"),
            "u_delta_low_mean": mean(rows, "u_delta_low"),
            "u_delta_high_mean": mean(rows, "u_delta_high"),
        }
    positive = [row for row in paired if row["u_delta_low"] > 0]
    gate_checks = {
        "execution_failures": bool(audit["zero_internal_failures_verified"]),
        "overall_u_delta_low_mean": overall["u_delta_low_mean"] > 0,
        "each_mix_u_delta_low_mean": all(by_mix[mix]["u_delta_low_mean"] >= 0 for mix in MIXES),
        "overall_stage_score_delta_mean": overall["stage_score_delta_mean"] > 0,
        "at_least_one_mix_u_delta_low_mean": any(by_mix[mix]["u_delta_low_mean"] > 0 for mix in MIXES),
        "positive_u_units_distinct_roots": len({row["root_index"] for row in positive}) >= 2,
        "positive_u_units_distinct_seats": len({row["focal_seat"] for row in positive}) >= 2,
    }
    passed = all(gate_checks.values())
    result = {
        "schema": "r14-generation2-archive-stage-style-result/1",
        "status": ("PASS_R14_G2_DEVELOPMENT_GATE" if passed
                   else "FAIL_R14_G2_DEVELOPMENT_GATE"),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidate_id": "archive-stage-style-terra-max",
        "candidate_sha256": manifest["candidate_sha256"],
        "overall": overall, "by_mix": by_mix,
        "positive_u_units": len(positive),
        "positive_u_distinct_roots": sorted({row["root_index"] for row in positive}),
        "positive_u_distinct_seats": sorted({row["focal_seat"] for row in positive}),
        "gate_checks": gate_checks, "execution_audit": audit,
        "prior_development": {
            "source": str(ARCHIVE_CLOSURE),
            "H_u_delta_mean": 0.03125,
            "M_u_delta_mean": 0.0,
            "selection_affected_by_result": True,
        },
        "strength_claim": False, "confirmation_eligible": passed,
        "next": ("冻结候选并进入不参与选择的全新来源独立确认" if passed
                 else "两个冻结代际均失败；依据文献与杭麻规则关闭当前结构邻域并选下一条可证伪路线"),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "paired-units.json"), {"schema": "r14-generation2-paired/1",
                                            "rows": paired})
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    globals()[args.operation]()
