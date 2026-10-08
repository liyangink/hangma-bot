"""R10 第三结构批次 B：三配置追加 H/M 各8根，累计每类16根后留二。"""
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
import structural_search_2b as base  # noqa: E402
import structural_search_3a as phase_a  # noqa: E402
import v2_parameter_policy as parameter  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402


BATCH = phase_a.BATCH
OUT = BATCH / "effect-b"
A_OUT = phase_a.OUT
A_FREEZE = A_OUT / "phase-b-freeze.json"
A_SAMPLES = A_OUT / "phase-a-samples.json"
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
ROOTS = tuple(range(9, 17))
MIXES = ("H", "M")
SEATS = tuple(range(4))
PARENT_CONTROL = phase_a.PARENT_CONTROL
TABLE_BUDGET = 512
BASE_SUMMARIZE = base.summarize_b


def digest(path: Path) -> str:
    return batch.digest(path.read_bytes())


def selected_rows() -> list[dict]:
    freeze = batch.read(A_FREEZE)
    ids = freeze["selected_configuration_ids"]
    if (len(ids) != 3 or freeze["new_root_indices"] != list(ROOTS)
            or freeze["forced_parent_control"] != PARENT_CONTROL
            or freeze["planned_candidate_tables"] != 384
            or freeze["baseline_new_tables"] != 128):
        raise ValueError("第三结构批次B冻结清单不符")
    rows = {row["config_id"]: row for row in phase_a.configurations()}
    if any(config_id not in rows for config_id in ids):
        raise ValueError("第三结构批次B含未知配置")
    return [rows[config_id] for config_id in ids]


def bind_base() -> None:
    base.BATCH = BATCH
    base.OUT = OUT
    base.A_OUT = A_OUT
    base.A_FREEZE = A_FREEZE
    base.A_SAMPLES = A_SAMPLES
    base.CONTRACT = CONTRACT
    base.ROOTS = ROOTS
    base.MIXES = MIXES
    base.SEATS = SEATS
    base.PARENT_CONTROL = PARENT_CONTROL
    base.TABLE_BUDGET = TABLE_BUDGET
    base.phase_a = phase_a
    base.selected_rows = selected_rows


bind_base()


def source_paths() -> list[Path]:
    paths = [Path(__file__), Path(base.__file__), Path(base.first.__file__),
             Path(phase_a.__file__), Path(parameter.__file__), Path(wiring.__file__),
             Path(archive.__file__), CONTRACT, A_OUT / "manifest.json", A_FREEZE, A_SAMPLES]
    paths.extend(Path(row["source"]) for row in selected_rows())
    return paths


def prepare() -> None:
    if OUT.exists():
        raise SystemExit("第三结构批次B目录已存在；拒绝覆盖")
    if batch.read(A_OUT / "summary.json")["status"] != (
            "COMPLETE_STRUCTURAL_PHASE_3A_DEVELOPMENT_RANKING"):
        raise ValueError("第三结构批次A尚未完整结案")
    rows = selected_rows()
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-structural-search-03-b",
        authorization_id="r10-structural-search-03-b-20260921",
        accounts={"tables_full": TABLE_BUDGET}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "阶段3A机器选留完成，按冻结清单追加共同新根",
        "scope": (
            "第三结构批次B开发筛选；3配置、H/M各新增8根、4座位、2桌；"
            "累计每类16根后留1个新结构加稳定V2对照；不确认不发布"
        ),
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(OUT / "authorization.json", authorization)
    runtime = guard.capture(source_paths=source_paths() + [OUT / "authorization.json"])
    plan_a = batch.read(A_OUT / "manifest.json")
    manifest = {
        "schema": "r10-structural-search-3b/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "phase_a_manifest": str(A_OUT / "manifest.json"),
        "phase_a_manifest_sha256": digest(A_OUT / "manifest.json"),
        "phase_a_freeze": str(A_FREEZE),
        "phase_a_freeze_sha256": digest(A_FREEZE),
        "phase_a_samples": str(A_SAMPLES),
        "phase_a_samples_sha256": digest(A_SAMPLES),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": plan_a["panel_seed"],
        "opponents": list(MIXES),
        "new_root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "tables_per_arm": 2,
        "configurations": rows,
        "configuration_ids": [row["config_id"] for row in rows],
        "baseline_policy_id": "ComparableHeuristicPolicyV2",
        "candidate_tables": 384,
        "baseline_tables": 128,
        "max_full_tables": TABLE_BUDGET,
        "workers": 4,
        "selection": {
            "fitness": "阶段3A+3B累计H/M等权的根级保守差d_low均值",
            "keep": 2,
            "forced_parent_control": PARENT_CONTROL,
            "rule": "按适应度降序、config_id升序取最高非父代配置；稳定V2对照强制占第2席",
            "meaning": "预算分配，不是显著性检验；未续评记NOT_SELECTED_WITHIN_BUDGET",
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
    print("prepared structural phase 3B: 3 configs, 16 new roots, 512 tables")


def verify_inputs(plan: dict) -> list[dict]:
    guard.verify(plan["runtime"])
    for path_key, sha_key in (
            ("phase_a_manifest", "phase_a_manifest_sha256"),
            ("phase_a_freeze", "phase_a_freeze_sha256"),
            ("phase_a_samples", "phase_a_samples_sha256"),
            ("contract", "contract_sha256")):
        if digest(Path(plan[path_key])) != plan[sha_key]:
            raise ValueError(path_key + " 漂移")
    rows = selected_rows()
    if rows != plan["configurations"]:
        raise ValueError("第三结构批次B配置身份漂移")
    return rows


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    seats = {}
    for seat in SEATS:
        plans = base.first.plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {"table_ids": [item.table_id for item in plans],
                            "table_seeds": [item.seed for item in plans]}
    return wiring._digest({"generator": "r10-structural-search-3b/1",
                           "panel_seed": plan["panel_seed"], "opponent_mix": mix,
                           "root_index": root, "seats": seats})


def bind_execution() -> None:
    bind_base()
    base.bind_first_module()
    base.verify_inputs = verify_inputs
    base.root_digest = root_digest


def run_baseline_all() -> dict:
    bind_execution()
    return base.run_baseline_all()


def run_configuration(config_id: str) -> dict:
    bind_execution()
    return base.run_configuration(config_id)


def summarize_b() -> None:
    bind_execution()
    BASE_SUMMARIZE()
    samples_path = OUT / "phase-b-new-samples.json"
    samples = batch.read(samples_path)
    for sample in samples:
        sample["source_root_id"] = sample["source_root_id"].replace("r10s2b-", "r10s3b-", 1)
    batch.write(samples_path, samples)
    ranking_path = OUT / "phase-b-ranking.json"
    ranking = batch.read(ranking_path)
    ranking["schema"] = "r10-structural-phase-3b-ranking/1"
    for row in ranking["ranking"]:
        if row["disposition"] == "ADVANCE_TO_2C":
            row["disposition"] = "ADVANCE_TO_3C"
    batch.write(ranking_path, ranking)
    freeze_path = OUT / "phase-c-freeze.json"
    freeze = batch.read(freeze_path)
    freeze["schema"] = "r10-structural-phase-3c-freeze/1"
    freeze["forced_parent_control"] = PARENT_CONTROL
    batch.write(freeze_path, freeze)
    summary_path = OUT / "summary.json"
    summary = batch.read(summary_path)
    summary["status"] = "COMPLETE_STRUCTURAL_PHASE_3B_DEVELOPMENT_RANKING"
    summary["next"] = "按phase-c-freeze补H/M各16根并冻结第三结构批次开发冠军"
    batch.write(summary_path, summary)
    print(json.dumps({
        "status": summary["status"],
        "leader": summary["leader"]["config_id"],
        "fitness": summary["leader"]["fitness_mean_delta_low"],
        "parent_fitness": summary["parent_control"]["fitness_mean_delta_low"],
        "selected_for_c": summary["selected_for_c"],
    }, ensure_ascii=False), flush=True)


def run_b() -> None:
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
    verify_inputs(plan)
    if len(completed) != 4:
        raise ValueError("第三结构批次B工作单元未全部完成")
    summarize_b()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-b", "summarize-b"))
    args = parser.parse_args()
    {"prepare": prepare, "run-b": run_b, "summarize-b": summarize_b}[args.operation]()
