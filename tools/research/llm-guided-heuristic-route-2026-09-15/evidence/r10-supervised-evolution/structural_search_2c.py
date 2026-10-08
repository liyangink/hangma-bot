"""R10 第二结构批次 C：候选与父代补 H/M 各 16 根并冻结开发冠军。"""
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
import structural_search_2a as phase_a  # noqa: E402
import structural_search_2b as phase_b  # noqa: E402
import structural_search_c as first  # noqa: E402
import v2_parameter_policy as parameter  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/effect-c')
A_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/effect-a')
B_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/effect-b')
B_FREEZE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/effect-b/phase-c-freeze.json')
A_SAMPLES = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/effect-a/phase-a-samples.json')
B_SAMPLES = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/effect-b/phase-b-new-samples.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
ROOTS = tuple(range(17, 33))
MIXES = ("H", "M")
SEATS = tuple(range(4))
PARENT_CONTROL = phase_a.PARENT_CONTROL
TABLE_BUDGET = 768


def digest(path: Path) -> str:
    return batch.digest(path.read_bytes())


def selected_rows() -> list[dict]:
    """只接受阶段2B机器冻结的候选和父代对照。"""
    freeze = batch.read(B_FREEZE)
    ids = freeze["selected_configuration_ids"]
    if (len(ids) != 2 or freeze["new_root_indices"] != list(ROOTS)
            or freeze["forced_parent_control"] != PARENT_CONTROL
            or freeze["planned_candidate_tables"] != 512
            or freeze["baseline_new_tables"] != 256):
        raise ValueError("第二结构批次C冻结清单不符")
    rows = {row["config_id"]: row for row in phase_a.configurations()}
    if any(config_id not in rows for config_id in ids):
        raise ValueError("第二结构批次C含未知配置")
    return [rows[config_id] for config_id in ids]


def bind_first_module() -> None:
    first.BATCH = BATCH
    first.OUT = OUT
    first.A_OUT = A_OUT
    first.B_OUT = B_OUT
    first.B_FREEZE = B_FREEZE
    first.A_SAMPLES = A_SAMPLES
    first.B_SAMPLES = B_SAMPLES
    first.CONTRACT = CONTRACT
    first.ROOTS = ROOTS
    first.MIXES = MIXES
    first.SEATS = SEATS
    first.selected_rows = selected_rows


bind_first_module()


def source_paths() -> list[Path]:
    paths = [Path(__file__), Path(first.__file__), Path(phase_a.__file__),
             Path(phase_b.__file__), Path(parameter.__file__), Path(wiring.__file__),
             Path(archive.__file__), CONTRACT, _project_file(_PROJECT_ROOT, B_OUT / "manifest.json"), B_FREEZE,
             A_SAMPLES, B_SAMPLES]
    paths.extend(Path(row["source"]) for row in selected_rows())
    return paths


def prepare() -> None:
    """冻结两个配置、三十二个新来源根和768桌预算。"""
    if OUT.exists():
        raise SystemExit("第二结构批次C目录已存在；拒绝覆盖")
    if batch.read(_project_file(_PROJECT_ROOT, B_OUT / "summary.json"))["status"] != (
            "COMPLETE_STRUCTURAL_PHASE_2B_DEVELOPMENT_RANKING"):
        raise ValueError("第二结构批次B尚未完整结案")
    rows = selected_rows()
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-structural-search-02-c",
        authorization_id="r10-structural-search-02-c-20260921",
        accounts={"tables_full": TABLE_BUDGET}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "阶段2B机器选留完成，按冻结清单追加共同新来源根",
        "scope": "第二结构批次C开发筛选；候选与父代、H/M各新增16根、4座位、2桌；"
                 "累计每类32根后冻结开发冠军；不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    plan_b = batch.read(_project_file(_PROJECT_ROOT, B_OUT / "manifest.json"))
    manifest = {
        "schema": "r10-structural-search-2c/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "phase_b_manifest": str(_project_file(_PROJECT_ROOT, B_OUT / "manifest.json")),
        "phase_b_manifest_sha256": digest(_project_file(_PROJECT_ROOT, B_OUT / "manifest.json")),
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
        "candidate_tables": 512,
        "baseline_tables": 256,
        "max_full_tables": TABLE_BUDGET,
        "workers": 4,
        "selection": {
            "fitness": "阶段2A+2B+2C累计H/M等权的根级保守差d_low均值",
            "keep": 1,
            "rule": "按适应度降序、config_id升序冻结一个开发冠军",
            "meaning": "开发冻结，不是显著性检验；只有非父代冠军且保守差为正才可进入新来源复核",
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
    print("prepared structural phase 2C: 2 configs, 32 new roots, 768 tables")


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
        raise ValueError("第二结构批次C配置身份漂移")
    return rows


def run_baseline_all() -> dict:
    bind_first_module()
    first.verify_inputs = verify_inputs
    return first.run_baseline_all()


def run_configuration(config_id: str) -> dict:
    bind_first_module()
    first.verify_inputs = verify_inputs
    return first.run_configuration(config_id)


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    seats = {}
    for seat in SEATS:
        plans = first.plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {
            "table_ids": [item.table_id for item in plans],
            "table_seeds": [item.seed for item in plans],
        }
    return wiring._digest({
        "generator": "r10-structural-search-2c/1",
        "panel_seed": plan["panel_seed"],
        "opponent_mix": mix,
        "root_index": root,
        "seats": seats,
    })


def summarize_c() -> None:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    rows = verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": TABLE_BUDGET})
    if ledger.spent("tables_full") != TABLE_BUDGET:
        raise ValueError("第二结构批次C费用未完整结算")
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
                root_id = f"r10s2c-{mix}-{plan['panel_seed']}-root{root:02d}"
                content = root_digest(plan, mix, root, contract)
                for seat in SEATS:
                    base_label = f"c-baseline-{mix}-r{root:02d}-s{seat}"
                    candidate_label = f"c-{row['config_id']}-{mix}-r{root:02d}-s{seat}"
                    baseline = batch.read(_project_file(_PROJECT_ROOT, OUT / "baseline" / base_label / "result.json"))["raw"]
                    candidate = batch.read(
                        _project_file(_PROJECT_ROOT, OUT / "candidates" / row["config_id"] /
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
                        "arms": {"baseline": phase_a.arm_view(
                                     baseline, plan["baseline_policy_id"]),
                                 "candidate": phase_a.arm_view(candidate, row["candidate_id"])},
                        "completeness": "complete",
                        "invalid_reasons": [],
                        "cost": {"budget_units": 4,
                                 "elapsed_ms": baseline["elapsed_ms"] + candidate["elapsed_ms"]},
                    }
                    current.append(sample)
                    new_samples.append(sample)
        cumulative = old_by_candidate.get(row["candidate_id"], []) + current
        if len(cumulative) != 256:
            raise ValueError("第二结构批次C累计样本数异常：" + row["config_id"])
        stats = archive.paired_stage_statistics(cumulative, min_roots=32)
        if stats["invalid_count"] or stats["uncomputable_count"]:
            raise ValueError("第二结构批次C累计样本无效：" + row["config_id"])
        normal = stats["by_candidate"][row["candidate_id"]]["panels"]["normal"]
        panels = normal["panels"]
        if (set(panels) != set(MIXES) or any(
                panel["status"] != "ok" or panel["n_roots"] != 32
                or not panel["manifest_complete"] for panel in panels.values())):
            raise ValueError("第二结构批次C累计根清单不完整：" + row["config_id"])
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
    champion = ordered[0]
    positive = (champion["config_id"] != PARENT_CONTROL
                and champion["fitness_mean_delta_low"] > 0)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-c-new-samples.json"), new_samples)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-c-ranking.json"), {
        "schema": "r10-structural-phase-2c-ranking/1",
        "ranking": [{**row, "rank": index + 1,
                     "disposition": ("DEVELOPMENT_CHAMPION" if index == 0
                                     else "NOT_SELECTED_WITHIN_BUDGET")}
                    for index, row in enumerate(ordered)],
        "development_champion": champion["config_id"],
        "selection_rule": plan["selection"],
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "development-champion-freeze.json"), {
        "schema": "r10-structural-development-champion-2/1",
        "created_after_complete_phase_c": True,
        "phase_c_manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "phase_c_ranking_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "phase-c-ranking.json")),
        "config_id": champion["config_id"],
        "candidate_id": champion["candidate_id"],
        "family": champion["family"],
        "values": champion["values"],
        "positive_development_signal": positive,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    next_step = (
        "冻结非父代正向冠军；用全新panel_seed和来源根执行独立复核"
        if positive else
        "未得到非父代正向保守差；停止本邻域，回顾参考文献和H/M触发覆盖后重组下一结构批次"
    )
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {
        "status": "COMPLETE_STRUCTURAL_PHASE_2C_DEVELOPMENT_CHAMPION",
        "configurations": 2,
        "new_roots_per_configuration": 32,
        "cumulative_roots_per_configuration": 64,
        "candidate_tables": 512,
        "baseline_tables": 256,
        "full_tables": TABLE_BUDGET,
        "development_champion": champion,
        "parent_control": next(row for row in ordered
                               if row["config_id"] == PARENT_CONTROL),
        "positive_development_signal": positive,
        "spent": ledger.account_summary(),
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
        "next": next_step,
    })
    print(json.dumps({
        "status": "COMPLETE_STRUCTURAL_PHASE_2C_DEVELOPMENT_CHAMPION",
        "champion": champion["config_id"],
        "fitness": champion["fitness_mean_delta_low"],
        "positive_development_signal": positive,
    }, ensure_ascii=False), flush=True)


def run_c() -> None:
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
    if len(completed) != 3:
        raise ValueError("第二结构批次C工作单元未全部完成")
    summarize_c()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-c", "summarize-c"))
    args = parser.parse_args()
    {"prepare": prepare, "run-c": run_c, "summarize-c": summarize_c}[args.operation]()
