"""R10 第一结构批次 A：24 配置在 H/M 各 8 个共同新来源根上的完整阶段筛选。"""
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
import v2_parameter_policy as parameter  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
import verify_full_natural_results as full  # noqa: E402
from confirmation_execution_probe import execute_arm  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921')
FAILED_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/effect-a')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/effect-a-v2')
PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/behavior-preflight-v2/summary.json')
CONFIG_ROOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/behavior-preflight-v2/configurations')
V2_DESIGN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/parameter-search-design-20260920.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026092055
ROOTS = tuple(range(1, 9))
MIXES = ("H", "M")
SEATS = tuple(range(4))
V2_CONTROL_IDS = ("v2_joint_02", "v2_joint_14", "v2_joint_03",
                  "v2_joint_06", "v2_joint_07")
DEFAULT_CONTROL = "v2-control-default"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def configurations() -> list[dict]:
    """重建冻结 18 个结构配置和 6 个 V2 配置对照。"""
    preflight = batch.read(PREFLIGHT)
    if preflight["passed_tasks"] != ["S1", "S2", "S3"]:
        raise ValueError("行为预检通过任务漂移")
    rows = []
    for task in preflight["tasks"]:
        if task["task"] not in preflight["passed_tasks"]:
            continue
        for item in task["configurations"]:
            path = _project_file(_PROJECT_ROOT, CONFIG_ROOT / item["config_id"] / "candidate.py")
            digest = sha256_bytes(path.read_bytes())
            if digest != item["source_sha256"]:
                raise ValueError("结构配置源码摘要漂移：" + item["config_id"])
            rows.append({
                "config_id": item["config_id"],
                "kind": "action_value_source",
                "family": task["task"],
                "source": str(path),
                "source_sha256": digest,
                "scorer_name": "offline-structural-v1:" + digest,
                "candidate_id": "action_value_v1:offline-structural-v1:" + digest,
                "values": item["values"],
                "is_zero_effect": item["is_zero_effect"],
                "is_author_default": item["is_author_default"],
                "preference_signature": item["preference_signature"],
                "changed_preferred_vs_base": item["changed_preferred_vs_base"],
            })
    design = batch.read(V2_DESIGN)
    selected = {item["config_id"]: item for item in design["selected"]}
    default_weights = design["baseline_weights"]
    default = parameter.weights_from_record(default_weights)
    rows.append({
        "config_id": DEFAULT_CONTROL,
        "kind": "v2_weights",
        "family": "V2_CONTROL",
        "weights": default_weights,
        "weights_sha256": parameter.weights_digest(default),
        "candidate_id": parameter.PREFIX + parameter.weights_digest(default),
        "is_zero_effect": True,
        "is_author_default": True,
        "source_design": "baseline_weights",
    })
    for old_id in V2_CONTROL_IDS:
        item = selected[old_id]
        weights = parameter.weights_from_record(item["weights"])
        digest = parameter.weights_digest(weights)
        rows.append({
            "config_id": "v2-control-" + old_id.removeprefix("v2_joint_"),
            "kind": "v2_weights",
            "family": "V2_CONTROL",
            "weights": item["weights"],
            "weights_sha256": digest,
            "candidate_id": parameter.PREFIX + digest,
            "is_zero_effect": False,
            "is_author_default": False,
            "source_design": old_id,
        })
    if len(rows) != 24 or len({row["config_id"] for row in rows}) != 24:
        raise ValueError("阶段 A 必须恰有 24 个唯一配置")
    if [row["family"] for row in rows].count("S1") != 6 or [row["family"] for row in rows].count("S2") != 6 or [row["family"] for row in rows].count("S3") != 6 or [row["family"] for row in rows].count("V2_CONTROL") != 6:
        raise ValueError("阶段 A 四个配置家族各须六席")
    return rows


def source_paths() -> list[Path]:
    result = [Path(__file__), Path(parameter.__file__), Path(wiring.__file__),
              Path(archive.__file__), Path(full.__file__), PREFLIGHT, V2_DESIGN, CONTRACT]
    result.extend(Path(row["source"]) for row in configurations()
                  if row["kind"] == "action_value_source")
    return result


def prepare() -> None:
    """冻结 24 配置、共同新来源和 3,200 桌上限；尚不运行模拟。"""
    if OUT.exists():
        raise SystemExit("结构阶段 A 目录已存在；拒绝覆盖")
    if FAILED_OUT.exists() and not (_project_file(_PROJECT_ROOT, FAILED_OUT / "closure.json")).exists():
        batch.write(_project_file(_PROJECT_ROOT, FAILED_OUT / "closure.json"), {
            "schema": "r10-structural-effect-a-closure/1",
            "status": "CLOSED_AUTHORIZATION_ISSUER_ERROR",
            "reason": "初次 prepare 把 issued_by 写成 Codex root；统一入口只信任 lead，"
                      "在任何桌赛、账本或清单落盘前 fail-closed。",
            "tables_started": 0,
            "model_calls": 0,
            "replacement": str(OUT),
        })
    if any(str(PANEL_SEED) in path.read_text(errors="ignore")
           for path in HERE.glob("**/*.json")):
        raise ValueError("结构阶段 A panel_seed 已出现在证据 JSON")
    configs = configurations()
    contract = batch.read(CONTRACT)
    if contract["group"]["tables_per_group"] != 2:
        raise ValueError("预算只适用于每阶段 2 桌")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-structural-search-01-a",
        authorization_id="r10-structural-search-01-a-20260921",
        accounts={"tables_full": 3200}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "用户要求按文献复盘方向继续新目标；结构生成与真实行为预检已完成",
        "scope": "结构批次A开发筛选；24配置、H/M各8根、4座位、2桌；不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-structural-search-a/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "behavior_preflight": str(PREFLIGHT),
        "behavior_preflight_sha256": sha256_bytes(PREFLIGHT.read_bytes()),
        "contract": str(CONTRACT), "contract_sha256": sha256_bytes(CONTRACT.read_bytes()),
        "v2_design": str(V2_DESIGN), "v2_design_sha256": sha256_bytes(V2_DESIGN.read_bytes()),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": PANEL_SEED,
        "opponents": list(MIXES), "root_indices": list(ROOTS),
        "focal_seats": list(SEATS), "tables_per_arm": 2,
        "configurations": configs,
        "configuration_ids": [row["config_id"] for row in configs],
        "baseline_policy_id": "ComparableHeuristicPolicyV2",
        "candidate_tables": 3072, "baseline_tables": 128,
        "max_full_tables": 3200, "workers": 4,
        "selection": {
            "fitness": "H/M等权的根级保守差d_low均值",
            "keep": 10,
            "forced_control": DEFAULT_CONTROL,
            "rule": "按适应度降序、config_id升序取前9；默认V2强制占第10席（已在前9则顺延一席）",
            "meaning": "预算分配，不是显著性检验；未续评记NOT_SELECTED_WITHIN_BUDGET",
        },
        "model_calls": 0, "confirmation_roots": 0,
        "selection_eligible": True, "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 3200}).save()
    print("prepared structural phase A: 24 configs, 16 roots/config, 3200 max tables")


def verify_inputs(plan: dict) -> list[dict]:
    guard.verify(plan["runtime"])
    for path_key, sha_key in (("behavior_preflight", "behavior_preflight_sha256"),
                              ("contract", "contract_sha256"),
                              ("v2_design", "v2_design_sha256")):
        if sha256_bytes(Path(plan[path_key]).read_bytes()) != plan[sha_key]:
            raise ValueError(path_key + " 漂移")
    current = configurations()
    if current != plan["configurations"]:
        raise ValueError("结构配置清单漂移")
    return current


def plans_for(contract, mix, root, seat, plan):
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
                label = f"a-baseline-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label, "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "baseline", "candidate_id": plan["baseline_policy_id"],
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
    count = 0
    source = Path(row["source"]).read_text(encoding="utf-8") if row["kind"] == "action_value_source" else None
    weights = parameter.weights_from_record(row["weights"]) if row["kind"] == "v2_weights" else None
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = plans_for(contract, mix, root, seat, plan)
                label = f"a-{config_id}-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label, "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "candidate", "candidate_id": row["candidate_id"],
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


def arm_view(raw, identity):
    return {key: raw.get(key) for key in (
        "status", "usable", "error", "focal_stage_score",
        "stage_totals_by_participant", "u", "u_low", "u_high",
        "unresolved", "elapsed_ms")} | {"candidate_id": identity, "policy_id": identity}


def root_digest(plan, mix, root, contract):
    seats = {}
    for seat in SEATS:
        plans = plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {"table_ids": [item.table_id for item in plans],
                            "table_seeds": [item.seed for item in plans]}
    return wiring._digest({"generator": "r10-structural-search-a/1",
                           "panel_seed": plan["panel_seed"], "opponent_mix": mix,
                           "root_index": root, "seats": seats})


def ranked(rows):
    return sorted(rows, key=lambda row: (-row["fitness_mean_delta_low"], row["config_id"]))


def select_for_b(ranking: list[dict]) -> list[str]:
    chosen = [row["config_id"] for row in ranking if row["config_id"] != DEFAULT_CONTROL][:9]
    chosen.append(DEFAULT_CONTROL)
    return chosen


def summarize_a() -> None:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    configs = verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 3200})
    if ledger.spent("tables_full") != 3200:
        raise ValueError("结构阶段 A 费用未完整结算")
    contract = batch.read(CONTRACT)
    samples, ranking_rows = [], []
    for row in configs:
        candidate_samples = []
        for mix in MIXES:
            for root in ROOTS:
                root_id = f"r10sa-{mix}-{plan['panel_seed']}-root{root:02d}"
                content = root_digest(plan, mix, root, contract)
                for seat in SEATS:
                    baseline_label = f"a-baseline-{mix}-r{root:02d}-s{seat}"
                    candidate_label = f"a-{row['config_id']}-{mix}-r{root:02d}-s{seat}"
                    baseline = batch.read(_project_file(_PROJECT_ROOT, OUT / "baseline" / baseline_label / "result.json"))["raw"]
                    candidate = batch.read(_project_file(_PROJECT_ROOT, OUT / "candidates" / row["config_id"] /
                                           candidate_label / "result.json"))["raw"]
                    sample = {
                        "schema": natural.NATURAL_SAMPLE_SCHEMA,
                        "source_root_id": root_id, "root_content_digest": content,
                        "root_index": root, "root_usage": "development_core",
                        "candidate_id": row["candidate_id"], "opponent_mix": mix,
                        "scenario": "normal", "focal_anchor_seat": seat,
                        "root_expected": {"seats": 4, "arms": ["baseline", "candidate"],
                                          "tables_per_arm": 2},
                        "arms": {"baseline": arm_view(baseline, plan["baseline_policy_id"]),
                                 "candidate": arm_view(candidate, row["candidate_id"])},
                        "completeness": "complete", "invalid_reasons": [],
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
            "config_id": row["config_id"], "candidate_id": row["candidate_id"],
            "kind": row["kind"], "family": row["family"],
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
    ordered = ranked(ranking_rows)
    selected = select_for_b(ordered)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-samples.json"), samples)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json"), {
        "schema": "r10-structural-phase-a-ranking/1",
        "ranking": [{**row, "rank": index + 1,
                     "disposition": ("ADVANCE_TO_B" if row["config_id"] in selected
                                     else "NOT_SELECTED_WITHIN_BUDGET")}
                    for index, row in enumerate(ordered)],
        "selected_for_b": selected,
        "selection_rule": plan["selection"],
        "strength_claim": False, "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-b-freeze.json"), {
        "schema": "r10-structural-phase-b-freeze/1",
        "created_after_complete_phase_a": True,
        "phase_a_manifest_sha256": sha256_bytes((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_bytes()),
        "phase_a_ranking_sha256": sha256_bytes((_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json")).read_bytes()),
        "selected_configuration_ids": selected,
        "forced_control": DEFAULT_CONTROL,
        "new_root_indices": list(range(9, 17)),
        "cumulative_roots_per_mix": 16,
        "planned_candidate_tables": 1280,
        "baseline_new_tables": 128,
        "selection_keep": 3,
        "fitness": plan["selection"]["fitness"],
        "model_calls": 0, "confirmation_roots": 0,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {
        "status": "COMPLETE_STRUCTURAL_PHASE_A_DEVELOPMENT_RANKING",
        "configurations": 24, "families": 4, "roots_per_configuration": 16,
        "candidate_tables": 3072, "baseline_tables": 128,
        "full_tables": 3200, "selected_for_b": selected,
        "leader": ordered[0], "spent": ledger.account_summary(),
        "model_calls": 0, "confirmation_roots": 0,
        "strength_claim": False, "confirmation_eligible": False,
        "release_eligible": False,
        "next": "按 phase-b-freeze 补 H/M 各8根；阶段A仅分配预算",
    })
    print(json.dumps({"status": "COMPLETE_STRUCTURAL_PHASE_A_DEVELOPMENT_RANKING",
                      "leader": ordered[0]["config_id"],
                      "fitness": ordered[0]["fitness_mean_delta_low"],
                      "selected_for_b": selected}, ensure_ascii=False))


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
    if len(completed) != 25:
        raise ValueError("结构阶段 A 工作单元未全部完成")
    summarize_a()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-a", "summarize-a"))
    args = parser.parse_args()
    {"prepare": prepare, "run-a": run_a, "summarize-a": summarize_a}[args.operation]()
