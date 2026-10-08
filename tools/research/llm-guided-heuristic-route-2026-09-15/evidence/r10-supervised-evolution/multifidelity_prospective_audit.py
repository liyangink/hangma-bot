"""R13-MF1：在全新来源上前瞻执行第一桌漏斗并补跑淘汰审计。"""

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
import math
import multiprocessing
import statistics
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import multifidelity_first_table_retro as retro  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
import v2_parameter_policy as parameter  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
from hangma_bot.application.deadline import ManualClock  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/multifidelity-prospective-audit-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R13-MULTI-FIDELITY-EVOLUTION-FUNNEL-PLAN-2026-09-21.md')
MF0 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/multifidelity-first-table-retro-01-20260921')
MF0_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/multifidelity-first-table-retro-01-20260921/result.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026092460
MIXES = ("H", "M")
ROOTS = (1, 2, 3, 4)
SEATS = (0, 1, 2, 3)
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)
PARAMETER_IDS = ("v2_joint_02", "v2_joint_07", "v2_joint_14", "v2_joint_24")
STRUCTURAL_SOURCES = {
    "hard-sol-high": _project_file(_PROJECT_ROOT, HERE / "strong-seeds-20260920/hard-sol-high/run/iterations/iter-01/generation/candidate.py"),
    "hard-terra-max": _project_file(_PROJECT_ROOT, HERE / "strong-seeds-20260920/hard-terra-max/run/iterations/iter-01/generation/candidate.py"),
    "hard-sol-max": _project_file(_PROJECT_ROOT, HERE / "strong-seeds-20260920/hard-sol-max/run/iterations/iter-02/generation/candidate.py"),
    "hard-astra-high": _project_file(_PROJECT_ROOT, HERE / "strong-seeds-20260920/hard-astra-high/run/iterations/iter-01/generation/candidate.py"),
    "river-sol-high": _project_file(_PROJECT_ROOT, HERE / "strong-seeds-20260920/river-sol-high/run/iterations/iter-01/generation/candidate.py"),
    "route-terra-max": _project_file(_PROJECT_ROOT, HERE / "strong-seeds-20260920/route-terra-max/run/iterations/iter-01/generation/candidate.py"),
}
BASELINE_ID = "stable-v2"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_specs() -> list[dict[str, Any]]:
    specs = [{"candidate_id": name, "family": "structure", "kind": "action_value",
              "source": str(path), "source_sha256": digest(path)}
             for name, path in STRUCTURAL_SOURCES.items()]
    for config_id in PARAMETER_IDS:
        weights, weights_sha = wiring._configuration(config_id)
        specs.append({"candidate_id": config_id, "family": "parameter", "kind": "parameter",
                      "weights": asdict(weights),
                      "weights_sha256": weights_sha})
    return specs


def _source_specs() -> list[dict[str, Any]]:
    return [{"mix": mix, "root_index": root, "focal_seat": seat,
             "source_id": f"{mix}:r{root:02d}:s{seat}"}
            for mix in MIXES for root in ROOTS for seat in SEATS]


def _find_candidate(candidate_id: str) -> dict[str, Any]:
    matches = [row for row in _candidate_specs() if row["candidate_id"] == candidate_id]
    if len(matches) != 1:
        raise ValueError("候选身份不存在或重复：" + candidate_id)
    return matches[0]


def _plans(source: Mapping[str, Any]) -> list[Any]:
    contract = json.loads(CONTRACT.read_text())
    return natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED)


def _logical_policies(candidate_id: str, candidate: Mapping[str, Any] | None,
                      plan: Any, mix: str, contract: Mapping[str, Any],
                      clock: ManualClock) -> dict[str, Any]:
    if candidate_id == BASELINE_ID:
        return natural.arm_logical_policies(
            arm="baseline", candidate_scorer=None,
            logical_participants=plan.logical_participants,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
            monotonic=clock.now)
    assert candidate is not None
    if candidate["kind"] == "action_value":
        source = Path(str(candidate["source"])).read_text()
        scorer = ActionValueScorer(str(candidate_id), source)
        return natural.arm_logical_policies(
            arm="candidate", candidate_scorer=scorer,
            logical_participants=plan.logical_participants,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
            monotonic=clock.now)
    logical = natural.arm_logical_policies(
        arm="baseline", candidate_scorer=None,
        logical_participants=plan.logical_participants,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        monotonic=clock.now)
    weights = parameter.weights_from_record(candidate["weights"])
    logical[natural.FOCAL_PARTICIPANT] = parameter.ResearchWeightedV2(weights, monotonic=clock.now)
    return logical


def _execute_table(candidate_id: str, source: Mapping[str, Any], table_no: int,
                   prior: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """执行一张真实桌；第二桌阶段账只由已完成第一桌结果构造。"""

    candidate = None if candidate_id == BASELINE_ID else _find_candidate(candidate_id)
    contract = json.loads(CONTRACT.read_text())
    plans = _plans(source)
    plan = plans[table_no - 1]
    totals: dict[str, int] = {}
    places: dict[str, int] = {}
    if table_no == 2:
        if prior is None or prior.get("match_status") != "complete":
            raise ValueError("第二桌缺少完整第一桌")
        placement = natural.stage.place_points_for_table(prior["scores_by_seat"])
        for seat, participant_id in enumerate(plans[0].seats()):
            totals[participant_id] = int(prior["scores_by_seat"][seat])
            places[participant_id] = int(placement[seat])
    situation = natural.build_stage_situation(
        plan=plan, table_no=table_no, tables_completed=table_no - 1,
        totals=totals, place_totals=places,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]))
    clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
    logical = _logical_policies(candidate_id, candidate, plan, str(source["mix"]),
                                contract, clock)
    row = natural.execute_natural_table(
        plan=plan,
        policies_by_seat=natural.seat_policies_from(
            logical, plan.permutation, plan.logical_participants),
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=ValueAnalysisLimits(), stage_situation=situation)
    row["stage_situation"] = situation.to_json()
    if row.get("match_status") != "complete" or row.get("scores_by_seat") is None:
        raise RuntimeError(f"{candidate_id}/{source['source_id']}/t{table_no} 未完成")
    review = natural.execution_audit.review_tables([row])
    if not review["zero_internal_failures_verified"]:
        raise RuntimeError(f"{candidate_id}/{source['source_id']}/t{table_no} 执行审计失败")
    return row


def _task(candidate_id: str, source: Mapping[str, Any], table_no: int,
          prior_path: str | None = None) -> dict[str, Any]:
    prior = None if prior_path is None else json.loads(Path(prior_path).read_text())["table"]
    return {"candidate_id": candidate_id, "source": dict(source), "table_no": table_no,
            "table": _execute_table(candidate_id, source, table_no, prior)}


def _safe(candidate_id: str, source_id: str, table_no: int) -> str:
    return f"{candidate_id}-{source_id.replace(':', '-')}-t{table_no}.json"


def _focal_score(table: Mapping[str, Any]) -> int:
    participants = table["stage_situation"]["participant_ids_by_seat"]
    return int(table["scores_by_seat"][participants.index(natural.FOCAL_PARTICIPANT)])


def _assemble(candidate_id: str, source: Mapping[str, Any], first: Mapping[str, Any],
              second: Mapping[str, Any]) -> dict[str, Any]:
    totals: dict[str, int] = {}
    places: dict[str, int] = {}
    plans = _plans(source)
    for plan, table in zip(plans, (first, second), strict=True):
        placement = natural.stage.place_points_for_table(table["scores_by_seat"])
        for seat, participant_id in enumerate(plan.seats()):
            totals[participant_id] = totals.get(participant_id, 0) + int(table["scores_by_seat"][seat])
            places[participant_id] = places.get(participant_id, 0) + int(placement[seat])
    utility = natural.stage.group_advance_utility([
        natural.stage.LedgerRow(participant_id=participant_id, total_score=totals[participant_id],
                                place_points=places[participant_id])
        for participant_id in sorted(totals)
    ], focal_id=natural.FOCAL_PARTICIPANT)
    return {"candidate_id": candidate_id, "source": dict(source),
            "first_table_focal_score": _focal_score(first),
            "focal_stage_score": totals[natural.FOCAL_PARTICIPANT],
            "u_low": float(utility["u_low"]), "u_high": float(utility["u_high"]),
            "unresolved": bool(utility["unresolved"])}


def _historical_thresholds() -> dict[str, float]:
    result = json.loads(MF0_RESULT.read_text())
    summaries = result["candidate_summaries"]
    return {
        "retain_first_delta_mean": retro._percentile(
            [row["first_table_delta_mean"] for row in summaries], 0.5),
        "competitive_u_delta_low_mean": retro._percentile(
            [row["u_delta_low_mean"] for row in summaries], 0.75),
    }


def source_paths() -> list[Path]:
    return [Path(__file__), PLAN, MF0_RESULT, CONTRACT, Path(natural.__file__),
            Path(parameter.__file__), Path(wiring.__file__), *STRUCTURAL_SOURCES.values()]


def prepare() -> None:
    """冻结 10 候选、32 个新来源、历史阈值和补跑审计规则。"""

    if OUT.exists():
        raise SystemExit("MF1 输出已存在，拒绝覆盖")
    mf0 = json.loads(MF0_RESULT.read_text())
    if mf0.get("status") != "PASS_R13_MF0_FOR_PROSPECTIVE_AUDIT":
        raise ValueError("MF0 未通过前瞻审计入口")
    specs = _candidate_specs()
    if len(specs) != 10 or sum(row["family"] == "structure" for row in specs) != 6:
        raise ValueError("MF1 候选家族数量漂移")
    for row in specs:
        if row["kind"] == "action_value":
            ActionValueScorer(row["candidate_id"], Path(row["source"]).read_text())
    OUT.mkdir(parents=True)
    max_tables = SOURCE_UNITS * (2 + 2 * len(specs))
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r13-mf1-prospective-audit-01",
        accounts={"tables_full": max_tables}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "MF0历史四折达到误淘汰与节省门，进入全新来源跨结构前瞻审计",
        "scope": "6结构+4参数候选；H/M各4根×4座位；先第一桌，保留者及按摘要排序的一半淘汰者补第二桌；不确认不发布",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r13-multifidelity-prospective-audit/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "plan": str(PLAN), "plan_sha256": digest(PLAN),
        "mf0_result": str(MF0_RESULT), "mf0_result_sha256": digest(MF0_RESULT),
        "contract": str(CONTRACT), "contract_sha256": digest(CONTRACT),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": PANEL_SEED, "mixes": list(MIXES), "root_indices": list(ROOTS),
        "focal_seats": list(SEATS), "source_units": SOURCE_UNITS,
        "candidates": specs, "historical_thresholds": _historical_thresholds(),
        "stage1_tables": SOURCE_UNITS * (1 + len(specs)),
        "baseline_stage2_tables": SOURCE_UNITS,
        "max_tables": max_tables, "workers": 4,
        "audit_culled": "按sha256('r13-mf1-audit|candidate_id')升序补跑ceil(淘汰候选/2)",
        "continue_gate": {"audited_false_negative_rate_max": 0.05,
                          "projected_candidate_table_savings_min": 0.25,
                          "completed_candidate_overall_spearman_min": 0.50,
                          "mix_spearman_min": 0.0,
                          "execution_failures": 0},
        "savings_note": "projected按准入后无资格补跑的稳态成本；本次为估计误淘汰而补跑的审计成本另报",
        "model_calls": 0, "strength_claim": False,
        "confirmation_eligible": False, "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": max_tables}).save()
    print(json.dumps({"status": "PREPARED_R13_MF1", "candidates": len(specs),
                      "sources": SOURCE_UNITS, "max_tables": max_tables}, ensure_ascii=False))


def verify(manifest: Mapping[str, Any]) -> None:
    guard.verify(manifest["runtime"])
    for path_key, sha_key in (("plan", "plan_sha256"), ("mf0_result", "mf0_result_sha256"),
                              ("contract", "contract_sha256")):
        if digest(Path(str(manifest[path_key]))) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")
    if manifest["candidates"] != _candidate_specs():
        raise ValueError("MF1 候选身份漂移")


def _parallel(tasks: Sequence[tuple[str, Mapping[str, Any], int, str | None]],
              out_dir: Path, workers: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    context = multiprocessing.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        futures = {pool.submit(_task, *task): task for task in tasks}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            candidate_id, source, table_no, _ = futures[future]
            batch.write(out_dir / _safe(candidate_id, source["source_id"], table_no), record)
            completed += 1
            if completed % 20 == 0 or completed == len(tasks):
                print(json.dumps({"completed": completed, "total": len(tasks),
                                  "phase_table_no": table_no}, ensure_ascii=False), flush=True)


def stage1() -> None:
    """执行共享基线两桌与全部候选第一桌，然后冻结保留/补跑清单。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text())
    verify(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "stage1-decisions.json")).exists():
        raise SystemExit("MF1 stage1 已完成，拒绝覆盖")
    candidates = [row["candidate_id"] for row in manifest["candidates"]]
    sources = _source_specs()
    tasks1 = [(BASELINE_ID, source, 1, None) for source in sources]
    tasks1.extend((candidate, source, 1, None) for candidate in candidates for source in sources)
    tasks2 = [(BASELINE_ID, source, 2,
               str(_project_file(_PROJECT_ROOT, OUT / "table1" / _safe(BASELINE_ID, source["source_id"], 1))))
              for source in sources]
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": manifest["max_tables"]})
    reservation = ledger.reserve(step_id="mf1-stage1-and-baseline-stage2",
                                 account="tables_full", amount=len(tasks1) + len(tasks2),
                                 note="全部候选第一桌及共享基线完整两桌")
    try:
        _parallel(tasks1, _project_file(_PROJECT_ROOT, OUT / "table1"), int(manifest["workers"]))
        _parallel(tasks2, _project_file(_PROJECT_ROOT, OUT / "table2"), int(manifest["workers"]))
    except Exception:
        ledger.settle(reservation, usage_unknown=True, note="MF1 stage1中断，按预留保守计费")
        raise
    ledger.settle(reservation, actual=len(tasks1) + len(tasks2))
    summaries = []
    for candidate in candidates:
        deltas = []
        by_mix: dict[str, list[float]] = {mix: [] for mix in MIXES}
        for source in sources:
            candidate_row = json.loads((_project_file(_PROJECT_ROOT, OUT / "table1" / _safe(
                candidate, source["source_id"], 1))).read_text())["table"]
            baseline_row = json.loads((_project_file(_PROJECT_ROOT, OUT / "table1" / _safe(
                BASELINE_ID, source["source_id"], 1))).read_text())["table"]
            delta = _focal_score(candidate_row) - _focal_score(baseline_row)
            deltas.append(delta)
            by_mix[source["mix"]].append(delta)
        summaries.append({"candidate_id": candidate,
                          "family": _find_candidate(candidate)["family"],
                          "first_table_delta_mean": statistics.fmean(deltas),
                          "by_mix": {mix: statistics.fmean(values)
                                     for mix, values in by_mix.items()}})
    threshold = float(manifest["historical_thresholds"]["retain_first_delta_mean"])
    retained = sorted(row["candidate_id"] for row in summaries
                      if row["first_table_delta_mean"] >= threshold)
    culled = sorted(set(candidates) - set(retained))
    audit_order = sorted(culled, key=lambda name: hashlib.sha256(
        ("r13-mf1-audit|" + name).encode()).hexdigest())
    audited = audit_order[:math.ceil(len(culled) / 2)]
    decisions = {"schema": "r13-mf1-stage1-decisions/1",
                 "retain_threshold": threshold, "summaries": summaries,
                 "retained": retained, "culled": culled, "audited_culled": audited,
                 "second_table_candidates": sorted(retained + audited),
                 "projected_candidate_table_savings": len(culled) / (2.0 * len(candidates)),
                 "qualification_actual_savings": (len(culled) - len(audited))
                                                  / (2.0 * len(candidates))}
    batch.write(_project_file(_PROJECT_ROOT, OUT / "stage1-decisions.json"), decisions)
    print(json.dumps({"status": "COMPLETE_R13_MF1_STAGE1", "retained": retained,
                      "culled": culled, "audited_culled": audited,
                      "projected_savings": decisions["projected_candidate_table_savings"]},
                     ensure_ascii=False))


def stage2() -> None:
    """只为保留候选和冻结淘汰审计样本执行第二桌。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text())
    verify(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("MF1 已结算，拒绝覆盖")
    decisions = json.loads((_project_file(_PROJECT_ROOT, OUT / "stage1-decisions.json")).read_text())
    sources = _source_specs()
    candidates = decisions["second_table_candidates"]
    tasks = [(candidate, source, 2,
              str(_project_file(_PROJECT_ROOT, OUT / "table1" / _safe(candidate, source["source_id"], 1))))
             for candidate in candidates for source in sources]
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": manifest["max_tables"]})
    reservation = ledger.reserve(step_id="mf1-selected-and-audit-stage2",
                                 account="tables_full", amount=len(tasks),
                                 note="保留候选与冻结淘汰审计候选第二桌")
    try:
        _parallel(tasks, _project_file(_PROJECT_ROOT, OUT / "table2"), int(manifest["workers"]))
    except Exception:
        ledger.settle(reservation, usage_unknown=True, note="MF1 stage2中断，按预留保守计费")
        raise
    ledger.settle(reservation, actual=len(tasks))
    baseline = {}
    for source in sources:
        first = json.loads((_project_file(_PROJECT_ROOT, OUT / "table1" / _safe(
            BASELINE_ID, source["source_id"], 1))).read_text())["table"]
        second = json.loads((_project_file(_PROJECT_ROOT, OUT / "table2" / _safe(
            BASELINE_ID, source["source_id"], 2))).read_text())["table"]
        baseline[source["source_id"]] = _assemble(BASELINE_ID, source, first, second)
    summaries = []
    unit_rows = []
    for candidate in candidates:
        units = []
        for source in sources:
            first = json.loads((_project_file(_PROJECT_ROOT, OUT / "table1" / _safe(
                candidate, source["source_id"], 1))).read_text())["table"]
            second = json.loads((_project_file(_PROJECT_ROOT, OUT / "table2" / _safe(
                candidate, source["source_id"], 2))).read_text())["table"]
            arm = _assemble(candidate, source, first, second)
            base = baseline[source["source_id"]]
            row = {"candidate_id": candidate, "family": _find_candidate(candidate)["family"],
                   "mix": source["mix"], "root_index": source["root_index"],
                   "focal_seat": source["focal_seat"],
                   "first_table_delta": arm["first_table_focal_score"]
                                        - base["first_table_focal_score"],
                   "full_stage_score_delta": arm["focal_stage_score"]
                                             - base["focal_stage_score"],
                   "u_delta_low": arm["u_low"] - base["u_high"],
                   "u_delta_high": arm["u_high"] - base["u_low"]}
            units.append(row)
            unit_rows.append(row)
        by_mix = {}
        for mix in MIXES:
            layer = [row for row in units if row["mix"] == mix]
            by_mix[mix] = {"first_table_delta_mean": statistics.fmean(
                                row["first_table_delta"] for row in layer),
                           "u_delta_low_mean": statistics.fmean(
                                row["u_delta_low"] for row in layer)}
        summaries.append({"candidate_id": candidate,
                          "family": _find_candidate(candidate)["family"],
                          "retained": candidate in decisions["retained"],
                          "audited_culled": candidate in decisions["audited_culled"],
                          "first_table_delta_mean": statistics.fmean(
                              row["first_table_delta"] for row in units),
                          "full_stage_score_delta_mean": statistics.fmean(
                              row["full_stage_score_delta"] for row in units),
                          "u_delta_low_mean": statistics.fmean(
                              row["u_delta_low"] for row in units),
                          "by_mix": by_mix})
    competitive_threshold = float(
        manifest["historical_thresholds"]["competitive_u_delta_low_mean"])
    audited = [row for row in summaries if row["audited_culled"]]
    false_negatives = [row for row in audited
                       if row["u_delta_low_mean"] >= competitive_threshold]
    audited_false_negative_rate = len(false_negatives) / len(audited) if audited else 0.0
    first_values = [row["first_table_delta_mean"] for row in summaries]
    u_values = [row["u_delta_low_mean"] for row in summaries]
    correlations = {"overall": retro._spearman(first_values, u_values)}
    for mix in MIXES:
        correlations[mix] = retro._spearman(
            [row["by_mix"][mix]["first_table_delta_mean"] for row in summaries],
            [row["by_mix"][mix]["u_delta_low_mean"] for row in summaries])
    gate = manifest["continue_gate"]
    checks = {
        "audited_false_negative_rate": audited_false_negative_rate
                                       <= gate["audited_false_negative_rate_max"],
        "projected_candidate_table_savings": decisions["projected_candidate_table_savings"]
                                              >= gate["projected_candidate_table_savings_min"],
        "completed_candidate_overall_spearman": correlations["overall"]
                                                >= gate["completed_candidate_overall_spearman_min"],
        "mix_spearman": all(correlations[mix] >= gate["mix_spearman_min"] for mix in MIXES),
        "execution_failures": True,
    }
    passed = all(checks.values())
    result = {"schema": "r13-multifidelity-prospective-audit-result/1",
              "status": ("PASS_R13_MF1_FIRST_TABLE_FUNNEL" if passed
                         else "CLOSE_R13_MF1_FIRST_TABLE_FUNNEL_FAILED"),
              "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
              "decisions_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "stage1-decisions.json")),
              "counts": {"candidates": len(manifest["candidates"]),
                         "retained": len(decisions["retained"]),
                         "culled": len(decisions["culled"]),
                         "audited_culled": len(audited),
                         "completed_full_candidates": len(summaries),
                         "tables_spent": ledger.spent("tables_full")},
              "historical_thresholds": manifest["historical_thresholds"],
              "projected_candidate_table_savings": decisions["projected_candidate_table_savings"],
              "qualification_actual_savings": decisions["qualification_actual_savings"],
              "audited_false_negatives": [row["candidate_id"] for row in false_negatives],
              "audited_false_negative_rate": audited_false_negative_rate,
              "correlations": correlations, "candidate_summaries": summaries,
              "gate_checks": checks, "strength_claim": False,
              "confirmation_eligible": False, "release_eligible": False,
              "next": ("把漏斗接入下一批有界种群，并持续随机补全淘汰审计" if passed
                       else "关闭第一桌漏斗，下一批全部执行完整两桌")}
    batch.write(_project_file(_PROJECT_ROOT, OUT / "full-units.json"), {"schema": "r13-mf1-full-units/1", "rows": unit_rows})
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"status": result["status"], "counts": result["counts"],
                      "projected_savings": result["projected_candidate_table_savings"],
                      "audited_false_negative_rate": audited_false_negative_rate,
                      "correlations": correlations, "gate_checks": checks}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "stage1", "stage2"))
    args = parser.parse_args()
    {"prepare": prepare, "stage1": stage1, "stage2": stage2}[args.command]()


if __name__ == "__main__":
    main()
