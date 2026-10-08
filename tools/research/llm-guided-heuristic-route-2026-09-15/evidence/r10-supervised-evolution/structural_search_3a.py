"""R10 第三结构批次 A：C1 六配置在 H/M 各8个共同新根上的完整阶段筛选。"""
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
import structural_search_2a as second  # noqa: E402
import v2_parameter_policy as parameter  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
import verify_full_natural_results as full  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-03-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-03-20260921/effect-a')
PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-03-20260921/behavior-preflight-v2/summary.json')
CONFIG_ROOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-03-20260921/behavior-preflight-v2/configurations')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026092183
ROOTS = tuple(range(1, 9))
MIXES = ("H", "M")
SEATS = tuple(range(4))
PARENT_CONTROL = "c1-cfg-00"
TABLE_BUDGET = 896
SECOND_SUMMARIZE = second.summarize_a


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def configurations() -> list[dict]:
    """重建通过行为预检的C1六配置；零效应是稳定V2对照。"""
    preflight = batch.read(PREFLIGHT)
    if preflight["passed_tasks"] != ["C1"] or preflight["failed_tasks"] != ["C2"]:
        raise ValueError("第三批行为预检结论漂移")
    task = next(row for row in preflight["tasks"] if row["task"] == "C1")
    rows = []
    for item in task["configurations"]:
        config_id = item["config_id"]
        path = _project_file(_PROJECT_ROOT, CONFIG_ROOT / config_id / "candidate.py")
        digest = sha256_bytes(path.read_bytes())
        if digest != item["source_sha256"]:
            raise ValueError("C1配置源码摘要漂移：" + config_id)
        rows.append({
            "config_id": config_id,
            "kind": "action_value_source",
            "family": "C1_CHI_PASS_OPPORTUNITY",
            "source": str(path),
            "source_sha256": digest,
            "scorer_name": "offline-structural-c1:" + digest,
            "candidate_id": "action_value_v1:offline-structural-c1:" + digest,
            "values": item["values"],
            "is_zero_effect": item["is_zero_effect"],
            "is_author_default": item["is_author_default"],
            "preference_signature": item["preference_signature"],
            "score_signature": item["score_signature"],
            "changed_preferred_vs_parent": item["changed_preferred_vs_base"],
            "changed_scores_vs_parent": item["changed_scores_vs_base"],
        })
    if len(rows) != 6 or len({row["config_id"] for row in rows}) != 6:
        raise ValueError("第三结构批次A必须恰有六个唯一C1配置")
    if [row["config_id"] for row in rows if row["is_zero_effect"]] != [PARENT_CONTROL]:
        raise ValueError("稳定V2零效应身份漂移")
    return rows


def bind_second_module() -> None:
    second.BATCH = BATCH
    second.OUT = OUT
    second.PREFLIGHT = PREFLIGHT
    second.CONFIG_ROOT = CONFIG_ROOT
    second.CONTRACT = CONTRACT
    second.PANEL_SEED = PANEL_SEED
    second.ROOTS = ROOTS
    second.MIXES = MIXES
    second.SEATS = SEATS
    second.PARENT_CONTROL = PARENT_CONTROL
    second.TABLE_BUDGET = TABLE_BUDGET
    second.configurations = configurations


bind_second_module()


def source_paths() -> list[Path]:
    result = [Path(__file__), Path(second.__file__), Path(second.first.__file__),
              Path(parameter.__file__), Path(wiring.__file__), Path(archive.__file__),
              Path(full.__file__), PREFLIGHT, CONTRACT]
    result.extend(Path(row["source"]) for row in configurations())
    return result


def prepare() -> None:
    """冻结六配置、共同新根和896桌上限；尚不运行模拟。"""
    if OUT.exists():
        raise SystemExit("第三结构批次A目录已存在；拒绝覆盖")
    if any(str(PANEL_SEED) in path.read_text(errors="ignore")
           for path in HERE.glob("**/*.json")):
        raise ValueError("第三结构批次A panel_seed 已出现在证据JSON")
    configs = configurations()
    contract = batch.read(CONTRACT)
    if contract["group"]["tables_per_group"] != 2:
        raise ValueError("预算只适用于每阶段2桌")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-structural-search-03-a",
        authorization_id="r10-structural-search-03-a-20260921",
        accounts={"tables_full": TABLE_BUDGET}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": (
            "第三批C1已通过静态、参数空间、稳定V2零效应和真实行为预检；"
            "C2无新行为已关闭。"
        ),
        "scope": "C1六配置开发筛选；H/M各8根、4座位、2桌；不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-structural-search-3a/1",
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
            "rule": (
                "按适应度降序、config_id升序取前2；稳定V2零效应对照强制占第3席"
                "（已在前2则顺延一席）"
            ),
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
    print("prepared structural phase 3A: 6 configs, 16 roots/config, 896 max tables")


def verify_inputs(plan: dict) -> list[dict]:
    guard.verify(plan["runtime"])
    for path_key, sha_key in (("behavior_preflight", "behavior_preflight_sha256"),
                              ("contract", "contract_sha256")):
        if sha256_bytes(Path(plan[path_key]).read_bytes()) != plan[sha_key]:
            raise ValueError(path_key + " 漂移")
    current = configurations()
    if current != plan["configurations"]:
        raise ValueError("C1结构配置清单漂移")
    return current


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    seats = {}
    for seat in SEATS:
        plans = second.first.plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {"table_ids": [item.table_id for item in plans],
                            "table_seeds": [item.seed for item in plans]}
    return wiring._digest({"generator": "r10-structural-search-3a/1",
                           "panel_seed": plan["panel_seed"], "opponent_mix": mix,
                           "root_index": root, "seats": seats})


def bind_execution() -> None:
    bind_second_module()
    second.bind_first_module()
    second.verify_inputs = verify_inputs
    second.root_digest = root_digest


def run_baseline_all() -> dict:
    bind_execution()
    return second.run_baseline_all()


def run_configuration(config_id: str) -> dict:
    bind_execution()
    return second.run_configuration(config_id)


def summarize_a() -> None:
    bind_execution()
    SECOND_SUMMARIZE()
    samples_path = _project_file(_PROJECT_ROOT, OUT / "phase-a-samples.json")
    samples = batch.read(samples_path)
    for sample in samples:
        sample["source_root_id"] = sample["source_root_id"].replace("r10s2a-", "r10s3a-", 1)
    batch.write(samples_path, samples)
    ranking_path = _project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json")
    ranking = batch.read(ranking_path)
    ranking["schema"] = "r10-structural-phase-3a-ranking/1"
    batch.write(ranking_path, ranking)
    freeze_path = _project_file(_PROJECT_ROOT, OUT / "phase-b-freeze.json")
    freeze = batch.read(freeze_path)
    freeze["schema"] = "r10-structural-phase-3b-freeze/1"
    freeze["forced_parent_control"] = PARENT_CONTROL
    batch.write(freeze_path, freeze)
    summary_path = _project_file(_PROJECT_ROOT, OUT / "summary.json")
    summary = batch.read(summary_path)
    summary["status"] = "COMPLETE_STRUCTURAL_PHASE_3A_DEVELOPMENT_RANKING"
    summary["next"] = "按phase-b-freeze补H/M各8根；阶段3A仅分配预算"
    batch.write(summary_path, summary)
    print(json.dumps({
        "status": summary["status"],
        "leader": summary["leader"]["config_id"],
        "fitness": summary["leader"]["fitness_mean_delta_low"],
        "parent_fitness": summary["parent_control"]["fitness_mean_delta_low"],
        "selected_for_b": summary["selected_for_b"],
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
        raise ValueError("第三结构批次A工作单元未全部完成")
    summarize_a()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-a", "summarize-a"))
    args = parser.parse_args()
    {"prepare": prepare, "run-a": run_a, "summarize-a": summarize_a}[args.operation]()
