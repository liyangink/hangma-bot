"""路线微函数开发冠军的新来源复核：H/M 各 128 根、4,096 桌。"""
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
import structural_new_source as base  # noqa: E402
import route_microfunction_search_a as phase_a  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402


BATCH = phase_a.BATCH
OUT = BATCH / "new-source-01"
C_OUT = BATCH / "effect-c"
CHAMPION = C_OUT / "development-champion-freeze.json"
C_SUMMARY = C_OUT / "summary.json"
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEEDS = (2026092198, 2026092199)
ROOTS = tuple(range(1, 65))
MIXES = ("H", "M")
SEATS = tuple(range(4))
ARMS = ("baseline", "candidate")
TABLE_BUDGET = 4096
BASE_SUMMARIZE = base.summarize


def digest(path: Path) -> str:
    return batch.digest(path.read_bytes())


def champion() -> tuple[dict, dict]:
    """读取机器冻结冠军，并重建、校验其源码身份。"""
    frozen = batch.read(CHAMPION)
    if (frozen.get("config_id") != "r2-cfg-02"
            or frozen.get("positive_development_signal") is not True
            or frozen.get("family") != "R2_BEST_ONLY"):
        raise ValueError("阶段 C 未冻结预期的正向路线微函数冠军")
    rows = {row["config_id"]: row for row in phase_a.configurations()}
    row = rows[frozen["config_id"]]
    if (row["candidate_id"] != frozen["candidate_id"]
            or row["family"] != frozen["family"]
            or row["values"] != frozen["values"]
            or digest(Path(row["source"])) != row["source_sha256"]):
        raise ValueError("路线微函数冠军源码身份漂移")
    return frozen, row


def root_digest(contract: dict, mix: str, panel_seed: int, root: int) -> str:
    seats = {}
    for seat in SEATS:
        plans = base.plans_for(contract, mix, panel_seed, root, seat)
        seats[str(seat)] = {"table_ids": [item.table_id for item in plans],
                            "table_seeds": [item.seed for item in plans]}
    return wiring._digest({
        "generator": "r10-route-microfunction-new-source/1",
        "panel_seed": panel_seed,
        "opponent_mix": mix,
        "root_index": root,
        "seats": seats,
    })


def bind_base() -> None:
    base.BATCH = BATCH
    base.OUT = OUT
    base.C_OUT = C_OUT
    base.CHAMPION = CHAMPION
    base.C_SUMMARY = C_SUMMARY
    base.CONTRACT = CONTRACT
    base.PANEL_SEEDS = PANEL_SEEDS
    base.ROOTS = ROOTS
    base.MIXES = MIXES
    base.SEATS = SEATS
    base.ARMS = ARMS
    base.phase_a = phase_a
    base.champion = champion
    base.verify_inputs = verify_inputs
    base.root_digest = root_digest


def source_paths() -> list[Path]:
    _frozen, row = champion()
    return [Path(__file__), Path(base.__file__), Path(phase_a.__file__),
            Path(wiring.__file__), Path(archive.__file__), Path(natural.__file__),
            Path(row["source"]), CHAMPION, C_SUMMARY, CONTRACT]


def ensure_new_seeds() -> None:
    """确认两个预定面板种子未出现在既有 JSON 证据中。"""
    base.HERE = HERE
    base.PANEL_SEEDS = PANEL_SEEDS
    base.ensure_new_seeds()


def prepare() -> None:
    """在读取任何新效果前冻结来源、样本量、分析和停止规则。"""
    if OUT.exists():
        raise SystemExit("路线微函数新来源复核目录已存在；拒绝覆盖")
    c_summary = batch.read(C_SUMMARY)
    if (c_summary.get("status") !=
            "COMPLETE_ROUTE_MICROFUNCTION_PHASE_C_DEVELOPMENT_CHAMPION"
            or c_summary.get("positive_development_signal") is not True):
        raise ValueError("路线微函数阶段 C 不满足新来源复核前提")
    frozen, row = champion()
    ensure_new_seeds()
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-route-microfunction-new-source",
        authorization_id="r10-route-microfunction-new-source-20260921",
        accounts={"tables_full": TABLE_BUDGET}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "路线微函数阶段C冠军为非父代且累计保守开发适应度大于0",
        "scope": (
            "冻结单一 best_only 冠军对稳定V2；两个全新 panel_seed 各 H/M 各64根、"
            "4座位、2桌、2臂；全量完成前不读结果改设计；不是正式确认"
        ),
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(OUT / "authorization.json", authorization)
    runtime = guard.capture(source_paths=source_paths() + [OUT / "authorization.json"])
    manifest = {
        "schema": "r10-route-microfunction-new-source/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "champion_freeze": str(CHAMPION),
        "champion_freeze_sha256": digest(CHAMPION),
        "phase_c_summary": str(C_SUMMARY),
        "phase_c_summary_sha256": digest(C_SUMMARY),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "config_id": frozen["config_id"],
        "candidate_id": frozen["candidate_id"],
        "family": frozen["family"],
        "source": row["source"],
        "source_sha256": row["source_sha256"],
        "scorer_name": row["scorer_name"],
        "values": row["values"],
        "baseline_policy_id": "ComparableHeuristicPolicyV2",
        "panel_seeds": list(PANEL_SEEDS),
        "root_indices_per_seed": list(ROOTS),
        "roots_per_mix": 128,
        "opponents": list(MIXES),
        "focal_seats": list(SEATS),
        "tables_per_arm": 2,
        "arms": list(ARMS),
        "max_full_tables": TABLE_BUDGET,
        "workers": 4,
        "analysis": {
            "primary": (
                "根级保守差L_r在H/M内各自均值后等权；"
                "SE=sqrt(s_H^2/n_H+s_M^2/n_M)/2；95%开发正态近似区间"
            ),
            "positive_but_interval_crosses_zero": (
                "INCONCLUSIVE_DEVELOPMENT；不自动扩评，保留为下一结构批次父代"
            ),
            "nonpositive_mean": "NO_POSITIVE_DEVELOPMENT；不提名正式确认",
            "positive_interval_lower": (
                "WORTH_INDEPENDENT_CONFIRMATION；仍须另冻正式确认"
            ),
            "family_regression": (
                "任一H/M点差或保守差95%开发区间上端小于0时阻止进入确认准备"
            ),
            "interval_status": "开发正态近似，不是正式显著性或发布证明",
        },
        "seed_selection": (
            "阶段C冠军冻结后选取两个未见固定panel_seed；prepare前对同层全部JSON精确查重"
        ),
        "model_calls": 0,
        "confirmation_roots": 0,
        "selection_eligible": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(OUT / "manifest.json", manifest)
    batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": TABLE_BUDGET}).save()
    print("prepared route microfunction new source: H/M each 128 roots, 4096 tables")


def verify_inputs(plan: dict) -> dict:
    guard.verify(plan["runtime"])
    for path_key, sha_key in (
            ("champion_freeze", "champion_freeze_sha256"),
            ("phase_c_summary", "phase_c_summary_sha256"),
            ("contract", "contract_sha256")):
        if digest(Path(plan[path_key])) != plan[sha_key]:
            raise ValueError(path_key + " 漂移")
    frozen, row = champion()
    if (frozen["candidate_id"] != plan["candidate_id"]
            or row["source_sha256"] != plan["source_sha256"]
            or row["values"] != plan["values"]):
        raise ValueError("路线微函数新来源冠军运行身份漂移")
    return row


bind_base()


def run_work_unit(panel_seed: int, mix: str, arm: str) -> dict:
    bind_base()
    return base.run_work_unit(panel_seed, mix, arm)


def summarize() -> None:
    bind_base()
    BASE_SUMMARIZE()
    path = OUT / "summary.json"
    summary = batch.read(path)
    summary["status"] = "COMPLETE_ROUTE_MICROFUNCTION_NEW_SOURCE_DEVELOPMENT"
    summary["next"] = (
        "冻结正式独立确认设计并复核统计入口"
        if summary["disposition"] == "WORTH_INDEPENDENT_CONFIRMATION"
        else "按文献与新来源分解重组多父代搜索空间，不追加本批根"
    )
    batch.write(path, summary)
    print(json.dumps({
        "status": summary["status"],
        "disposition": summary["disposition"],
        "conservative_mean": summary["conservative_equal_mix_sampling"]["mean"],
        "interval_95": summary["conservative_equal_mix_sampling"]["interval_95"],
    }, ensure_ascii=False), flush=True)


def run() -> None:
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    context = multiprocessing.get_context("spawn")
    completed = []
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=plan["workers"], mp_context=context) as pool:
        futures = [pool.submit(run_work_unit, seed, mix, arm)
                   for seed in PANEL_SEEDS for mix in MIXES for arm in ARMS]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            completed.append(result)
            print("complete", result["panel_seed"], result["mix"],
                  result["arm"], result["tables"], flush=True)
    if len(completed) != 8 or sum(row["tables"] for row in completed) != TABLE_BUDGET:
        raise ValueError("路线微函数新来源复核工作单元未完整完成")
    summarize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "summarize"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "summarize": summarize}[args.operation]()
