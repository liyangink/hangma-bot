"""R10 第二代路线置信结构阶段 C：三方追加 H/M 各十六根并冻结结论。"""
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
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import sitin_archive as archive  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
import structural_search_2c as base  # noqa: E402
import route_confidence_search_a as phase_a  # noqa: E402
import route_confidence_search_b as phase_b  # noqa: E402
import v2_parameter_policy as parameter  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402


BATCH = phase_a.BATCH
OUT = BATCH / "effect-c"
A_OUT = phase_a.OUT
B_OUT = phase_b.OUT
B_FREEZE = B_OUT / "phase-c-freeze.json"
A_SAMPLES = A_OUT / "phase-a-samples.json"
B_SAMPLES = B_OUT / "phase-b-new-samples.json"
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
ROOTS = tuple(range(17, 33))
MIXES = ("H", "M")
SEATS = tuple(range(4))
V2_CONTROL = phase_a.V2_CONTROL
OLD_PARENT_CONTROL = phase_a.OLD_PARENT_CONTROL
TABLE_BUDGET = 1024


def digest(path: Path) -> str:
    return batch.digest(path.read_bytes())


def selected_rows() -> list[dict]:
    freeze = batch.read(B_FREEZE)
    ids = freeze["selected_configuration_ids"]
    if (len(ids) != 3 or freeze["new_root_indices"] != list(ROOTS)
            or freeze["forced_controls"] != [OLD_PARENT_CONTROL, V2_CONTROL]
            or freeze["planned_candidate_tables"] != 768
            or freeze["baseline_new_tables"] != 256):
        raise ValueError("路线置信阶段 C 冻结清单不符")
    rows = {row["config_id"]: row for row in phase_a.configurations()}
    if any(config_id not in rows for config_id in ids):
        raise ValueError("路线置信阶段 C 含未知配置")
    return [rows[config_id] for config_id in ids]


def bind_base() -> None:
    base.BATCH = BATCH
    base.OUT = OUT
    base.A_OUT = A_OUT
    base.B_OUT = B_OUT
    base.B_FREEZE = B_FREEZE
    base.A_SAMPLES = A_SAMPLES
    base.B_SAMPLES = B_SAMPLES
    base.CONTRACT = CONTRACT
    base.ROOTS = ROOTS
    base.MIXES = MIXES
    base.SEATS = SEATS
    base.PARENT_CONTROL = V2_CONTROL
    base.TABLE_BUDGET = TABLE_BUDGET
    base.phase_a = phase_a
    base.phase_b = phase_b
    base.selected_rows = selected_rows


bind_base()


def source_paths() -> list[Path]:
    paths = [Path(__file__), Path(base.__file__), Path(base.first.__file__),
             Path(phase_a.__file__), Path(phase_b.__file__), Path(parameter.__file__),
             Path(wiring.__file__), Path(archive.__file__), CONTRACT,
             B_OUT / "manifest.json", B_FREEZE, A_SAMPLES, B_SAMPLES]
    paths.extend(Path(row["source"]) for row in selected_rows())
    return paths


def prepare() -> None:
    if OUT.exists():
        raise SystemExit("路线置信阶段 C 目录已存在；拒绝覆盖")
    if batch.read(B_OUT / "summary.json")["status"] != (
            "COMPLETE_ROUTE_CONFIDENCE_PHASE_B_DEVELOPMENT_RANKING"):
        raise ValueError("路线置信阶段 B 尚未完整结案")
    rows = selected_rows()
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-route-confidence-c",
        authorization_id="r10-route-confidence-c-20260921",
        accounts={"tables_full": TABLE_BUDGET}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "阶段B固定预算完成；按预冻结三方对照完成累计32根裁决",
        "scope": (
            "第二代C1、上一代固定+8冠军和稳定V2；H/M各新增16根、"
            "4座位、2桌；累计每类32根后关闭或保留结构；不确认不发布"
        ),
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(OUT / "authorization.json", authorization)
    runtime = guard.capture(source_paths=source_paths() + [OUT / "authorization.json"])
    plan_b = batch.read(B_OUT / "manifest.json")
    manifest = {
        "schema": "r10-route-confidence-search-c/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "phase_b_manifest": str(B_OUT / "manifest.json"),
        "phase_b_manifest_sha256": digest(B_OUT / "manifest.json"),
        "phase_b_freeze": str(B_FREEZE),
        "phase_b_freeze_sha256": digest(B_FREEZE),
        "phase_a_samples": str(A_SAMPLES),
        "phase_a_samples_sha256": digest(A_SAMPLES),
        "phase_b_samples": str(B_SAMPLES),
        "phase_b_samples_sha256": digest(B_SAMPLES),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": plan_b["panel_seed"],
        "opponents": list(MIXES),
        "new_root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "tables_per_arm": 2,
        "configurations": rows,
        "configuration_ids": [row["config_id"] for row in rows],
        "baseline_policy_id": "ComparableHeuristicPolicyV2",
        "candidate_tables": 768,
        "baseline_tables": 256,
        "max_full_tables": TABLE_BUDGET,
        "workers": 4,
        "selection": {
            "fitness": "阶段A+B+C累计 H/M 等权的根级保守差 d_low 均值",
            "keep": 1,
            "rule": "按适应度冻结总冠军，并单独裁决第二代结构是否严格优于0与上一代父代",
            "meaning": (
                "开发冻结，不是显著性检验；第二代只有保守差严格为正且超过上一代父代，"
                "才保留为新来源复核候选，否则关闭本参数邻域"
            ),
        },
        "model_calls": 0,
        "confirmation_roots": 0,
        "selection_eligible": True,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(OUT / "manifest.json", manifest)
    batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": TABLE_BUDGET}).save()
    print(json.dumps({"status": "PREPARED_ROUTE_CONFIDENCE_C",
                      "configurations": 3, "tables": TABLE_BUDGET}, ensure_ascii=False))


def verify_inputs(plan: dict) -> list[dict]:
    guard.verify(plan["runtime"])
    for path_key, sha_key in (
            ("phase_b_manifest", "phase_b_manifest_sha256"),
            ("phase_b_freeze", "phase_b_freeze_sha256"),
            ("phase_a_samples", "phase_a_samples_sha256"),
            ("phase_b_samples", "phase_b_samples_sha256"),
            ("contract", "contract_sha256")):
        if digest(Path(plan[path_key])) != plan[sha_key]:
            raise ValueError(path_key + " 漂移")
    rows = selected_rows()
    if rows != plan["configurations"]:
        raise ValueError("路线置信阶段 C 配置身份漂移")
    return rows


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    seats = {}
    for seat in SEATS:
        plans = base.first.plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {"table_ids": [item.table_id for item in plans],
                            "table_seeds": [item.seed for item in plans]}
    return wiring._digest({"generator": "r10-route-confidence-search-c/1",
                           "panel_seed": plan["panel_seed"], "opponent_mix": mix,
                           "root_index": root, "seats": seats})


def bind_execution() -> None:
    bind_base()
    base.bind_first_module()
    base.verify_inputs = verify_inputs


def run_baseline_all() -> dict:
    bind_execution()
    return base.run_baseline_all()


def run_configuration(config_id: str) -> dict:
    bind_execution()
    return base.run_configuration(config_id)


def summarize_c() -> None:
    plan = batch.read(OUT / "manifest.json")
    rows = verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": TABLE_BUDGET})
    if ledger.spent("tables_full") != TABLE_BUDGET:
        raise ValueError("路线置信阶段 C 费用未完整结算")
    contract = batch.read(CONTRACT)
    old_by_candidate: dict[str, list[dict]] = {}
    for path in (A_SAMPLES, B_SAMPLES):
        for sample in batch.read(path):
            old_by_candidate.setdefault(sample["candidate_id"], []).append(sample)
    new_samples: list[dict] = []
    ranking_rows: list[dict] = []
    for row in rows:
        current = []
        for mix in MIXES:
            for root in ROOTS:
                root_id = f"r10rcc-{mix}-{plan['panel_seed']}-root{root:02d}"
                content = root_digest(plan, mix, root, contract)
                for seat in SEATS:
                    baseline_label = f"c-baseline-{mix}-r{root:02d}-s{seat}"
                    candidate_label = f"c-{row['config_id']}-{mix}-r{root:02d}-s{seat}"
                    baseline = batch.read(OUT / "baseline" / baseline_label / "result.json")["raw"]
                    candidate = batch.read(OUT / "candidates" / row["config_id"] /
                                           candidate_label / "result.json")["raw"]
                    sample = {
                        "schema": natural.NATURAL_SAMPLE_SCHEMA,
                        "source_root_id": root_id,
                        "root_content_digest": content,
                        "root_index": root,
                        "root_usage": "development_core",
                        "candidate_id": row["candidate_id"],
                        "opponent_mix": mix,
                        "scenario": "normal",
                        "focal_anchor_seat": seat,
                        "root_expected": {"seats": 4, "arms": ["baseline", "candidate"],
                                          "tables_per_arm": 2},
                        "arms": {"baseline": phase_a.engine.arm_view(
                                     baseline, plan["baseline_policy_id"]),
                                 "candidate": phase_a.engine.arm_view(candidate, row["candidate_id"])},
                        "completeness": "complete",
                        "invalid_reasons": [],
                        "cost": {"budget_units": 4,
                                 "elapsed_ms": baseline["elapsed_ms"] + candidate["elapsed_ms"]},
                    }
                    current.append(sample)
                    new_samples.append(sample)
        cumulative = old_by_candidate.get(row["candidate_id"], []) + current
        if len(cumulative) != 256:
            raise ValueError("路线置信阶段 C 累计样本数异常：" + row["config_id"])
        stats = archive.paired_stage_statistics(cumulative, min_roots=32)
        if stats["invalid_count"] or stats["uncomputable_count"]:
            raise ValueError("路线置信阶段 C 累计样本无效：" + row["config_id"])
        normal = stats["by_candidate"][row["candidate_id"]]["panels"]["normal"]
        panels = normal["panels"]
        if (set(panels) != set(MIXES) or any(
                panel["status"] != "ok" or panel["n_roots"] != 32
                or not panel["manifest_complete"] for panel in panels.values())):
            raise ValueError("路线置信阶段 C 累计根清单不完整：" + row["config_id"])
        ranking_rows.append({
            "config_id": row["config_id"],
            "candidate_id": row["candidate_id"],
            "family": row["family"],
            "is_zero_effect": row["is_zero_effect"],
            "is_author_default": row["is_author_default"],
            "values": row["values"],
            "fitness_mean_delta_low": normal["declared_mix"]["mean_delta_low"],
            "mean_delta": normal["declared_mix"]["mean_delta"],
            "mean_delta_high": normal["declared_mix"]["mean_delta_high"],
            "H": {key: panels["H"][key] for key in
                  ("n_roots", "mean_delta", "standard_error", "interval_95")},
            "M": {key: panels["M"][key] for key in
                  ("n_roots", "mean_delta", "standard_error", "interval_95")},
        })
    ordered = sorted(ranking_rows,
                     key=lambda item: (-item["fitness_mean_delta_low"], item["config_id"]))
    champion = ordered[0]
    new_row = next(row for row in ordered if row["config_id"] not in
                   {V2_CONTROL, OLD_PARENT_CONTROL})
    old_row = next(row for row in ordered if row["config_id"] == OLD_PARENT_CONTROL)
    v2_row = next(row for row in ordered if row["config_id"] == V2_CONTROL)
    new_positive = (
        new_row["fitness_mean_delta_low"] > 0.0
        and new_row["fitness_mean_delta_low"] > old_row["fitness_mean_delta_low"]
    )
    batch.write(OUT / "phase-c-new-samples.json", new_samples)
    batch.write(OUT / "phase-c-ranking.json", {
        "schema": "r10-route-confidence-phase-c-ranking/1",
        "ranking": [{**row, "rank": index + 1,
                     "disposition": ("DEVELOPMENT_CHAMPION" if index == 0
                                     else "NOT_SELECTED_WITHIN_BUDGET")}
                    for index, row in enumerate(ordered)],
        "development_champion": champion["config_id"],
        "new_structure_positive_and_beats_parent": new_positive,
        "selection_rule": plan["selection"],
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    disposition = (
        "RETAIN_NEW_STRUCTURE_FOR_NEW_SOURCE_REVIEW" if new_positive
        else "CLOSE_ROUTE_CONFIDENCE_PARAMETER_NEIGHBORHOOD"
    )
    batch.write(OUT / "development-conclusion.json", {
        "schema": "r10-route-confidence-development-conclusion/1",
        "created_after_complete_phase_c": True,
        "phase_c_manifest_sha256": digest(OUT / "manifest.json"),
        "phase_c_ranking_sha256": digest(OUT / "phase-c-ranking.json"),
        "overall_champion": champion,
        "new_structure": new_row,
        "old_parent": old_row,
        "v2_control": v2_row,
        "new_structure_positive_and_beats_parent": new_positive,
        "disposition": disposition,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
        "next": (
            "使用全新panel_seed做新来源复核" if new_positive else
            "按ReEvo比较反馈和EoH多父代变异，加入副露后续质量与手牌自由度；禁止继续调本批阈值"
        ),
    })
    batch.write(OUT / "summary.json", {
        "status": "COMPLETE_ROUTE_CONFIDENCE_PHASE_C_DEVELOPMENT_CONCLUSION",
        "configurations": 3,
        "new_roots_per_mix": 16,
        "cumulative_roots_per_mix": 32,
        "candidate_tables": 768,
        "baseline_tables": 256,
        "full_tables": TABLE_BUDGET,
        "development_champion": champion,
        "new_structure": new_row,
        "old_parent_control": old_row,
        "v2_control": v2_row,
        "new_structure_positive_and_beats_parent": new_positive,
        "disposition": disposition,
        "spent": ledger.account_summary(),
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "COMPLETE_ROUTE_CONFIDENCE_PHASE_C_DEVELOPMENT_CONCLUSION",
        "champion": champion["config_id"],
        "champion_fitness": champion["fitness_mean_delta_low"],
        "new_structure_fitness": new_row["fitness_mean_delta_low"],
        "old_parent_fitness": old_row["fitness_mean_delta_low"],
        "disposition": disposition,
    }, ensure_ascii=False), flush=True)


def run_c() -> None:
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    context = multiprocessing.get_context("spawn")
    completed = []
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=plan["workers"], mp_context=context) as pool:
        futures = [pool.submit(run_baseline_all)]
        futures.extend(pool.submit(run_configuration, config_id)
                       for config_id in plan["configuration_ids"])
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            completed.append(result)
            print((result.get("config_id") or "baseline"), "complete",
                  result["tables"], "tables", flush=True)
    if len(completed) != 4:
        raise ValueError("路线置信阶段 C 工作单元未全部完成")
    summarize_c()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-c"))
    args = parser.parse_args()
    {"prepare": prepare, "run-c": run_c}[args.operation]()
