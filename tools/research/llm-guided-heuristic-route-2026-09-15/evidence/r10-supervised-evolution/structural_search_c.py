"""R10 第一结构批次 C：3 配置补 H/M 各 16 根，累计每族 32 根后冻结冠军。"""
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
import structural_search_a as phase_a  # noqa: E402
import structural_search_b as phase_b  # noqa: E402
import v2_parameter_policy as parameter  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
from confirmation_execution_probe import execute_arm  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/effect-c')
A_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/effect-a-v2')
B_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/effect-b')
B_FREEZE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/effect-b/phase-c-freeze.json')
A_SAMPLES = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/effect-a-v2/phase-a-samples.json')
B_SAMPLES = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/effect-b/phase-b-new-samples.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
ROOTS = tuple(range(17, 33))
MIXES = ("H", "M")
SEATS = tuple(range(4))
DEFAULT_CONTROL = phase_a.DEFAULT_CONTROL


def digest(path: Path) -> str:
    return batch.digest(path.read_bytes())


def selected_rows() -> list[dict]:
    """只接受阶段 B 机器冻结的三个配置，并重验源码或参数身份。"""
    freeze = batch.read(B_FREEZE)
    ids = freeze["selected_configuration_ids"]
    if (len(ids) != 3 or freeze["new_root_indices"] != list(ROOTS)
            or freeze["forced_control"] != DEFAULT_CONTROL
            or freeze["planned_candidate_tables"] != 768
            or freeze["baseline_new_tables"] != 256):
        raise ValueError("结构阶段 C 冻结清单不符")
    rows = {row["config_id"]: row for row in phase_a.configurations()}
    if any(config_id not in rows for config_id in ids):
        raise ValueError("结构阶段 C 含未知配置")
    return [rows[config_id] for config_id in ids]


def source_paths() -> list[Path]:
    paths = [Path(__file__), Path(phase_a.__file__), Path(phase_b.__file__),
             Path(parameter.__file__), Path(wiring.__file__), Path(archive.__file__),
             CONTRACT, _project_file(_PROJECT_ROOT, B_OUT / "manifest.json"), B_FREEZE, A_SAMPLES, B_SAMPLES]
    paths.extend(Path(row["source"]) for row in selected_rows()
                 if row["kind"] == "action_value_source")
    return paths


def prepare() -> None:
    """冻结三个配置、三十二个新来源根和 1,024 桌预算。"""
    if OUT.exists():
        raise SystemExit("结构阶段 C 目录已存在；拒绝覆盖")
    if batch.read(_project_file(_PROJECT_ROOT, B_OUT / "summary.json"))["status"] != (
            "COMPLETE_STRUCTURAL_PHASE_B_DEVELOPMENT_RANKING"):
        raise ValueError("结构阶段 B 尚未完整结案")
    rows = selected_rows()
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-structural-search-01-c",
        authorization_id="r10-structural-search-01-c-20260921",
        accounts={"tables_full": 1024}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "结构阶段B机器选留完成，按冻结清单追加共同新来源根",
        "scope": "结构批次C开发筛选；3配置、H/M各新增16根、4座位、2桌；"
                 "累计每族32根后冻结1个开发冠军；不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    plan_b = batch.read(_project_file(_PROJECT_ROOT, B_OUT / "manifest.json"))
    manifest = {
        "schema": "r10-structural-search-c/1",
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
        "candidate_tables": 768,
        "baseline_tables": 256,
        "max_full_tables": 1024,
        "workers": 4,
        "selection": {
            "fitness": "阶段A+B+C累计H/M等权的根级保守差d_low均值",
            "keep": 1,
            "rule": "按适应度降序、config_id升序冻结一个开发冠军",
            "meaning": "开发冻结，不是显著性检验；只有非默认冠军且保守差为正才可进入新来源复核",
        },
        "model_calls": 0,
        "confirmation_roots": 0,
        "selection_eligible": True,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 1024}).save()
    print("prepared structural phase C: 3 configs, 32 new roots, 1024 tables")


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
        raise ValueError("结构阶段 C 配置身份漂移")
    return rows


def plans_for(contract: dict, mix: str, root: int, seat: int, plan: dict):
    return natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=plan["panel_seed"])


def run_baseline_all() -> dict:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(plan)
    contract = batch.read(CONTRACT)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": plan["max_full_tables"]})
    versions = natural.stage.contract_versions_block(contract)
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = plans_for(contract, mix, root, seat, plan)
                label = f"c-baseline-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label,
                    "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "baseline",
                    "candidate_id": plan["baseline_policy_id"],
                }
                checked = execute_arm(
                    _project_file(_PROJECT_ROOT, OUT / "baseline" / label), expected=expected, ledger=ledger,
                    runner=lambda plans=plans, mix=mix: natural.run_arm_stage(
                        arm="baseline", plans=plans, candidate_scorer=None,
                        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
                        versions_block=versions, step_limit=contract["stop"]["step_limit"],
                        value_limits=ValueAnalysisLimits()),
                    verifier=lambda raw, plans=plans: wiring._verify_stage(
                        raw, plans, contract, plan["baseline_policy_id"], None))
                count += checked["tables"]
    verify_inputs(plan)
    return {"kind": "baseline", "tables": count}


def run_configuration(config_id: str) -> dict:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    rows = verify_inputs(plan)
    row = next(item for item in rows if item["config_id"] == config_id)
    contract = batch.read(CONTRACT)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": plan["max_full_tables"]})
    versions = natural.stage.contract_versions_block(contract)
    source = (Path(row["source"]).read_text(encoding="utf-8")
              if row["kind"] == "action_value_source" else None)
    weights = (parameter.weights_from_record(row["weights"])
               if row["kind"] == "v2_weights" else None)
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = plans_for(contract, mix, root, seat, plan)
                label = f"c-{config_id}-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label,
                    "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "candidate",
                    "candidate_id": row["candidate_id"],
                }
                if row["kind"] == "action_value_source":
                    runner = lambda plans=plans, mix=mix: natural.run_arm_stage(
                        arm="candidate", plans=plans,
                        candidate_scorer=ActionValueScorer(row["scorer_name"], source),
                        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
                        versions_block=versions, step_limit=contract["stop"]["step_limit"],
                        value_limits=ValueAnalysisLimits())
                    weights_sha = None
                else:
                    runner = lambda plans=plans, mix=mix: wiring._run_configured_stage(
                        plans, mix, contract, weights)
                    weights_sha = row["weights_sha256"]
                checked = execute_arm(
                    _project_file(_PROJECT_ROOT, OUT / "candidates" / config_id / label),
                    expected=expected, ledger=ledger, runner=runner,
                    verifier=lambda raw, plans=plans, weights_sha=weights_sha: wiring._verify_stage(
                        raw, plans, contract, row["candidate_id"], weights_sha))
                count += checked["tables"]
    verify_inputs(plan)
    return {"kind": "candidate", "config_id": config_id, "tables": count}


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    seats = {}
    for seat in SEATS:
        plans = plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {
            "table_ids": [item.table_id for item in plans],
            "table_seeds": [item.seed for item in plans],
        }
    return wiring._digest({
        "generator": "r10-structural-search-c/1",
        "panel_seed": plan["panel_seed"],
        "opponent_mix": mix,
        "root_index": root,
        "seats": seats,
    })


def summarize_c() -> None:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    rows = verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 1024})
    if ledger.spent("tables_full") != 1024:
        raise ValueError("结构阶段 C 费用未完整结算")
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
                root_id = f"r10sc-{mix}-{plan['panel_seed']}-root{root:02d}"
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
                        "root_expected": {
                            "seats": 4,
                            "arms": ["baseline", "candidate"],
                            "tables_per_arm": 2,
                        },
                        "arms": {
                            "baseline": phase_a.arm_view(
                                baseline, plan["baseline_policy_id"]),
                            "candidate": phase_a.arm_view(candidate, row["candidate_id"]),
                        },
                        "completeness": "complete",
                        "invalid_reasons": [],
                        "cost": {
                            "budget_units": 4,
                            "elapsed_ms": baseline["elapsed_ms"] + candidate["elapsed_ms"],
                        },
                    }
                    current.append(sample)
                    new_samples.append(sample)
        cumulative = old_by_candidate.get(row["candidate_id"], []) + current
        if len(cumulative) != 256:
            raise ValueError("结构阶段 C 累计样本数异常：" + row["config_id"])
        stats = archive.paired_stage_statistics(cumulative, min_roots=32)
        if stats["invalid_count"] or stats["uncomputable_count"]:
            raise ValueError("结构阶段 C 累计样本无效：" + row["config_id"])
        normal = stats["by_candidate"][row["candidate_id"]]["panels"]["normal"]
        panels = normal["panels"]
        if (set(panels) != set(MIXES) or any(
                panel["status"] != "ok" or panel["n_roots"] != 32
                or not panel["manifest_complete"] for panel in panels.values())):
            raise ValueError("结构阶段 C 累计根清单不完整：" + row["config_id"])
        ranking_rows.append({
            "config_id": row["config_id"],
            "candidate_id": row["candidate_id"],
            "kind": row["kind"],
            "family": row["family"],
            "is_zero_effect": row["is_zero_effect"],
            "is_author_default": row["is_author_default"],
            "fitness_mean_delta_low": normal["declared_mix"]["mean_delta_low"],
            "mean_delta": normal["declared_mix"]["mean_delta"],
            "mean_delta_high": normal["declared_mix"]["mean_delta_high"],
            "H": {key: panels["H"][key] for key in
                  ("n_roots", "mean_delta", "standard_error", "interval_95")},
            "M": {key: panels["M"][key] for key in
                  ("n_roots", "mean_delta", "standard_error", "interval_95")},
        })
    ordered = phase_a.ranked(ranking_rows)
    champion = ordered[0]
    positive = (champion["config_id"] != DEFAULT_CONTROL
                and champion["fitness_mean_delta_low"] > 0)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-c-new-samples.json"), new_samples)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-c-ranking.json"), {
        "schema": "r10-structural-phase-c-ranking/1",
        "ranking": [{
            **row,
            "rank": index + 1,
            "disposition": ("DEVELOPMENT_CHAMPION" if index == 0
                            else "NOT_SELECTED_WITHIN_BUDGET"),
        } for index, row in enumerate(ordered)],
        "development_champion": champion["config_id"],
        "selection_rule": plan["selection"],
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "development-champion-freeze.json"), {
        "schema": "r10-structural-development-champion/1",
        "created_after_complete_phase_c": True,
        "phase_c_manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "phase_c_ranking_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "phase-c-ranking.json")),
        "config_id": champion["config_id"],
        "candidate_id": champion["candidate_id"],
        "kind": champion["kind"],
        "family": champion["family"],
        "positive_development_signal": positive,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    next_step = (
        "冻结非默认正向冠军；用全新panel_seed和来源根执行独立复核"
        if positive else
        "未得到非默认正向保守差；停止放大评测，回顾参考文献和H/M分解后重组下一结构批次")
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {
        "status": "COMPLETE_STRUCTURAL_PHASE_C_DEVELOPMENT_CHAMPION",
        "configurations": 3,
        "new_roots_per_configuration": 32,
        "cumulative_roots_per_configuration": 64,
        "candidate_tables": 768,
        "baseline_tables": 256,
        "full_tables": 1024,
        "development_champion": champion,
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
        "status": "COMPLETE_STRUCTURAL_PHASE_C_DEVELOPMENT_CHAMPION",
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
    if len(completed) != 4:
        raise ValueError("结构阶段 C 工作单元未全部完成")
    summarize_c()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-c", "summarize-c"))
    args = parser.parse_args()
    {"prepare": prepare, "run-c": run_c, "summarize-c": summarize_c}[args.operation]()
