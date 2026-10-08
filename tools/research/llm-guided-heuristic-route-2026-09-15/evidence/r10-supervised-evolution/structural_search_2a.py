"""R10 第二结构批次 A：T2 六配置在 H/M 各 8 个共同新来源根上的完整阶段筛选。"""
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
import structural_search_a as first  # noqa: E402
import v2_parameter_policy as parameter  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
import verify_full_natural_results as full  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/effect-a')
PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/repair-preflight/behavior-preflight-v2/summary.json')
CONFIG_ROOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/repair-preflight/behavior-preflight-v2/configurations')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026092169
ROOTS = tuple(range(1, 9))
MIXES = ("H", "M")
SEATS = tuple(range(4))
PARENT_CONTROL = "t2-cfg-01"
TABLE_BUDGET = 896


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def configurations() -> list[dict]:
    """重建冻结的T2六配置；零效应配置是上一批S3父代对照。"""
    preflight = batch.read(PREFLIGHT)
    if preflight["passed_tasks"] != ["T2"] or preflight["failed_tasks"] != ["T4"]:
        raise ValueError("修复行为预检结论漂移")
    task = next(row for row in preflight["tasks"] if row["task"] == "T2")
    rows = []
    for item in task["configurations"]:
        source_id = item["config_id"]
        config_id = source_id.replace("s2-", "t2-", 1)
        path = _project_file(_PROJECT_ROOT, CONFIG_ROOT / source_id / "candidate.py")
        digest = sha256_bytes(path.read_bytes())
        if digest != item["source_sha256"]:
            raise ValueError("T2结构配置源码摘要漂移：" + source_id)
        rows.append({
            "config_id": config_id,
            "source_config_id": source_id,
            "kind": "action_value_source",
            "family": "T2_SELECTIVE_FOLLOWUP",
            "source": str(path),
            "source_sha256": digest,
            "scorer_name": "offline-structural-t2:" + digest,
            "candidate_id": "action_value_v1:offline-structural-t2:" + digest,
            "values": item["values"],
            "is_zero_effect": item["is_zero_effect"],
            "is_author_default": item["is_author_default"],
            "preference_signature": item["preference_signature"],
            "score_signature": item["score_signature"],
            "changed_preferred_vs_parent": item["changed_preferred_vs_base"],
            "changed_scores_vs_parent": item["changed_scores_vs_base"],
        })
    if len(rows) != 6 or len({row["config_id"] for row in rows}) != 6:
        raise ValueError("第二结构批次A必须恰有六个唯一T2配置")
    zero = [row["config_id"] for row in rows if row["is_zero_effect"]]
    if zero != [PARENT_CONTROL]:
        raise ValueError("父代零效应身份漂移")
    return rows


def bind_first_module() -> None:
    """让首批经过验证的执行函数读取本批冻结常量。"""
    first.BATCH = BATCH
    first.OUT = OUT
    first.PREFLIGHT = PREFLIGHT
    first.CONFIG_ROOT = CONFIG_ROOT
    first.CONTRACT = CONTRACT
    first.PANEL_SEED = PANEL_SEED
    first.ROOTS = ROOTS
    first.MIXES = MIXES
    first.SEATS = SEATS
    first.configurations = configurations


bind_first_module()


def source_paths() -> list[Path]:
    result = [Path(__file__), Path(first.__file__), Path(parameter.__file__),
              Path(wiring.__file__), Path(archive.__file__), Path(full.__file__),
              PREFLIGHT, CONTRACT]
    result.extend(Path(row["source"]) for row in configurations())
    return result


def prepare() -> None:
    """冻结六配置、共同新来源和896桌上限；尚不运行模拟。"""
    if OUT.exists():
        raise SystemExit("第二结构批次A目录已存在；拒绝覆盖")
    if any(str(PANEL_SEED) in path.read_text(errors="ignore")
           for path in HERE.glob("**/*.json")):
        raise ValueError("第二结构批次A panel_seed 已出现在证据 JSON")
    configs = configurations()
    contract = batch.read(CONTRACT)
    if contract["group"]["tables_per_group"] != 2:
        raise ValueError("预算只适用于每阶段2桌")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-structural-search-02-a",
        authorization_id="r10-structural-search-02-a-20260921",
        accounts={"tables_full": TABLE_BUDGET}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "第二结构批次T2已通过静态、参数空间、父代零效应和真实行为预检",
        "scope": "T2六配置开发筛选；H/M各8根、4座位、2桌；不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-structural-search-2a/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "behavior_preflight": str(PREFLIGHT),
        "behavior_preflight_sha256": sha256_bytes(PREFLIGHT.read_bytes()),
        "contract": str(CONTRACT),
        "contract_sha256": sha256_bytes(CONTRACT.read_bytes()),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": PANEL_SEED,
        "opponents": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "tables_per_arm": 2,
        "configurations": configs,
        "configuration_ids": [row["config_id"] for row in configs],
        "baseline_policy_id": "ComparableHeuristicPolicyV2",
        "candidate_tables": 768,
        "baseline_tables": 128,
        "max_full_tables": TABLE_BUDGET,
        "workers": 4,
        "selection": {
            "fitness": "H/M等权的根级保守差d_low均值",
            "keep": 3,
            "forced_parent_control": PARENT_CONTROL,
            "rule": "按适应度降序、config_id升序取前2；S3父代零效应对照强制占第3席（已在前2则顺延一席）",
            "meaning": "预算分配，不是显著性检验；未续评记NOT_SELECTED_WITHIN_BUDGET",
        },
        "model_calls": 0,
        "confirmation_roots": 0,
        "selection_eligible": True,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": TABLE_BUDGET}).save()
    print("prepared structural phase 2A: 6 configs, 16 roots/config, 896 max tables")


def verify_inputs(plan: dict) -> list[dict]:
    guard.verify(plan["runtime"])
    for path_key, sha_key in (("behavior_preflight", "behavior_preflight_sha256"),
                              ("contract", "contract_sha256")):
        if sha256_bytes(Path(plan[path_key]).read_bytes()) != plan[sha_key]:
            raise ValueError(path_key + " 漂移")
    current = configurations()
    if current != plan["configurations"]:
        raise ValueError("T2结构配置清单漂移")
    return current


def run_baseline_all() -> dict:
    bind_first_module()
    first.verify_inputs = verify_inputs
    return first.run_baseline_all()


def run_configuration(config_id: str) -> dict:
    bind_first_module()
    first.verify_inputs = verify_inputs
    return first.run_configuration(config_id)


def arm_view(raw: dict, identity: str) -> dict:
    return {key: raw.get(key) for key in (
        "status", "usable", "error", "focal_stage_score",
        "stage_totals_by_participant", "u", "u_low", "u_high",
        "unresolved", "elapsed_ms")} | {"candidate_id": identity, "policy_id": identity}


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    seats = {}
    for seat in SEATS:
        plans = first.plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {"table_ids": [item.table_id for item in plans],
                            "table_seeds": [item.seed for item in plans]}
    return wiring._digest({"generator": "r10-structural-search-2a/1",
                           "panel_seed": plan["panel_seed"], "opponent_mix": mix,
                           "root_index": root, "seats": seats})


def select_for_b(ranking: list[dict]) -> list[str]:
    chosen = [row["config_id"] for row in ranking
              if row["config_id"] != PARENT_CONTROL][:2]
    if PARENT_CONTROL not in chosen:
        chosen.append(PARENT_CONTROL)
    if len(chosen) < 3:
        chosen.extend(row["config_id"] for row in ranking
                      if row["config_id"] not in chosen and len(chosen) < 3)
    return chosen


def summarize_a() -> None:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    configs = verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": TABLE_BUDGET})
    if ledger.spent("tables_full") != TABLE_BUDGET:
        raise ValueError("第二结构批次A费用未完整结算")
    contract = batch.read(CONTRACT)
    samples, ranking_rows = [], []
    for row in configs:
        candidate_samples = []
        for mix in MIXES:
            for root in ROOTS:
                root_id = f"r10s2a-{mix}-{plan['panel_seed']}-root{root:02d}"
                content = root_digest(plan, mix, root, contract)
                for seat in SEATS:
                    baseline_label = f"a-baseline-{mix}-r{root:02d}-s{seat}"
                    candidate_label = f"a-{row['config_id']}-{mix}-r{root:02d}-s{seat}"
                    baseline = batch.read(_project_file(_PROJECT_ROOT, OUT / "baseline" / baseline_label / "result.json"))["raw"]
                    candidate = batch.read(_project_file(_PROJECT_ROOT, OUT / "candidates" / row["config_id"] /
                                           candidate_label / "result.json"))["raw"]
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
                        "arms": {"baseline": arm_view(baseline, plan["baseline_policy_id"]),
                                 "candidate": arm_view(candidate, row["candidate_id"])},
                        "completeness": "complete",
                        "invalid_reasons": [],
                        "cost": {"budget_units": 4,
                                 "elapsed_ms": baseline["elapsed_ms"] + candidate["elapsed_ms"]},
                    }
                    candidate_samples.append(sample)
                    samples.append(sample)
        stats = archive.paired_stage_statistics(candidate_samples, min_roots=8)
        if stats["invalid_count"] or stats["uncomputable_count"]:
            raise ValueError("配置存在无效样本：" + row["config_id"])
        normal = stats["by_candidate"][row["candidate_id"]]["panels"]["normal"]
        panels = normal["panels"]
        if set(panels) != set(MIXES) or any(
                panel["status"] != "ok" or not panel["manifest_complete"]
                for panel in panels.values()):
            raise ValueError("配置根清单不完整：" + row["config_id"])
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
                     key=lambda row: (-row["fitness_mean_delta_low"], row["config_id"]))
    selected = select_for_b(ordered)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-samples.json"), samples)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json"), {
        "schema": "r10-structural-phase-2a-ranking/1",
        "ranking": [{**row, "rank": index + 1,
                     "disposition": ("ADVANCE_TO_2B" if row["config_id"] in selected
                                     else "NOT_SELECTED_WITHIN_BUDGET")}
                    for index, row in enumerate(ordered)],
        "selected_for_b": selected,
        "selection_rule": plan["selection"],
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-b-freeze.json"), {
        "schema": "r10-structural-phase-2b-freeze/1",
        "created_after_complete_phase_a": True,
        "phase_a_manifest_sha256": sha256_bytes((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_bytes()),
        "phase_a_ranking_sha256": sha256_bytes((_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json")).read_bytes()),
        "selected_configuration_ids": selected,
        "forced_parent_control": PARENT_CONTROL,
        "new_root_indices": list(range(9, 17)),
        "cumulative_roots_per_mix": 16,
        "planned_candidate_tables": 384,
        "baseline_new_tables": 128,
        "selection_keep": 2,
        "fitness": plan["selection"]["fitness"],
        "model_calls": 0,
        "confirmation_roots": 0,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {
        "status": "COMPLETE_STRUCTURAL_PHASE_2A_DEVELOPMENT_RANKING",
        "configurations": 6,
        "families": 1,
        "roots_per_configuration": 16,
        "candidate_tables": 768,
        "baseline_tables": 128,
        "full_tables": TABLE_BUDGET,
        "selected_for_b": selected,
        "leader": ordered[0],
        "parent_control": next(row for row in ordered
                               if row["config_id"] == PARENT_CONTROL),
        "spent": ledger.account_summary(),
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
        "next": "按phase-b-freeze补H/M各8根；阶段2A仅分配预算",
    })
    print(json.dumps({
        "status": "COMPLETE_STRUCTURAL_PHASE_2A_DEVELOPMENT_RANKING",
        "leader": ordered[0]["config_id"],
        "fitness": ordered[0]["fitness_mean_delta_low"],
        "parent_fitness": next(row["fitness_mean_delta_low"] for row in ordered
                               if row["config_id"] == PARENT_CONTROL),
        "selected_for_b": selected,
    }, ensure_ascii=False))


def run_a() -> None:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
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
    verify_inputs(plan)
    if len(completed) != 7:
        raise ValueError("第二结构批次A工作单元未全部完成")
    summarize_a()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-a", "summarize-a"))
    args = parser.parse_args()
    {"prepare": prepare, "run-a": run_a, "summarize-a": summarize_a}[args.operation]()
