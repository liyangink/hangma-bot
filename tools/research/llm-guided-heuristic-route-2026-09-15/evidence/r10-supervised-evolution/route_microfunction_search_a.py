"""R10 路线微函数阶段 A：五个行为代表在 H/M 各四个共同新根上粗筛。

阶段 A 只分配后续预算。稳定 V2 零效应配置强制保留；其余席位覆盖弱/强
midrange、强 best_only 以及一个独特的 best_only 形状配置。
"""
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


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/effect-a')
PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/behavior-preflight-v2/summary.json')
CONFIG_ROOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/behavior-preflight-v2/configurations')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026092197
ROOTS = tuple(range(1, 5))
MIXES = ("H", "M")
SEATS = tuple(range(4))
PARENT_CONTROL = "r1-cfg-00"
REPRESENTATIVES = (
    "r1-cfg-00",  # 稳定 V2 零效应对照
    "r1-cfg-01",  # 弱 midrange
    "r1-cfg-02",  # 强 midrange
    "r2-cfg-02",  # 强 best_only
    "r2-cfg-04",  # 独特 best_only 行为签名
)
TABLE_BUDGET = 384


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def configurations() -> list[dict]:
    """从通过预检的十二配置中重建五个预登记行为代表。"""
    preflight = batch.read(PREFLIGHT)
    if preflight["passed_tasks"] != ["R1", "R2"] or preflight["failed_tasks"]:
        raise ValueError("路线微函数行为预检结论漂移")
    all_rows: dict[str, dict] = {}
    for task in preflight["tasks"]:
        for item in task["configurations"]:
            config_id = item["config_id"]
            path = _project_file(_PROJECT_ROOT, CONFIG_ROOT / config_id / "candidate.py")
            digest = sha256_bytes(path.read_bytes())
            if digest != item["source_sha256"]:
                raise ValueError("路线微函数配置源码摘要漂移：" + config_id)
            all_rows[config_id] = {
                "config_id": config_id,
                "kind": "action_value_source",
                "family": task["task"] + "_" + ("MIDRANGE" if task["task"] == "R1" else "BEST_ONLY"),
                "source": str(path),
                "source_sha256": digest,
                "scorer_name": "offline-route-microfunction:" + digest,
                "candidate_id": "action_value_v1:offline-route-microfunction:" + digest,
                "values": item["values"],
                "is_zero_effect": item["is_zero_effect"],
                "is_author_default": item["is_author_default"],
                "preference_signature": item["preference_signature"],
                "score_signature": item["score_signature"],
                "changed_preferred_vs_parent": item["changed_preferred_vs_base"],
                "changed_scores_vs_parent": item["changed_scores_vs_base"],
            }
    if any(config_id not in all_rows for config_id in REPRESENTATIVES):
        raise ValueError("预登记行为代表缺失")
    rows = [all_rows[config_id] for config_id in REPRESENTATIVES]
    if [row["config_id"] for row in rows if row["is_zero_effect"]] != [PARENT_CONTROL]:
        raise ValueError("稳定 V2 零效应身份漂移")
    if len({row["preference_signature"] for row in rows}) != 4:
        raise ValueError("五个代表必须覆盖四个首选行为签名")
    return rows


def bind_second_module() -> None:
    """让既有阶段执行器读取本批冻结常量。"""
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
    """冻结五代表、共同新来源和 384 桌上限；尚不运行模拟。"""
    if OUT.exists():
        raise SystemExit("路线微函数阶段 A 目录已存在；拒绝覆盖")
    if any(str(PANEL_SEED) in path.read_text(errors="ignore")
           for path in HERE.glob("**/*.json")):
        raise ValueError("路线微函数阶段 A panel_seed 已出现在证据 JSON")
    configs = configurations()
    contract = batch.read(CONTRACT)
    if contract["group"]["tables_per_group"] != 2:
        raise ValueError("预算只适用于每阶段 2 桌")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-route-microfunction-contrastive-a",
        authorization_id="r10-route-microfunction-contrastive-a-20260921",
        accounts={"tables_full": TABLE_BUDGET}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": (
            "R1/R2 已通过静态、稳定 V2 零效应、226 个真实观察行为预检和 "
            "144/144 条路线拆分/重排变形检查；阶段 A 只评估行为代表。"
        ),
        "scope": "五个行为代表开发粗筛；H/M 各4根、4座位、2桌；不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-route-microfunction-search-a/1",
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
        "behavior_archive": {
            "source_configurations": 12,
            "evaluated_representatives": list(REPRESENTATIVES),
            "covered_preference_signatures": 4,
            "rule": "先按真实观察首选行为去重，再保留映射家族与强度代表",
        },
        "baseline_policy_id": "ComparableHeuristicPolicyV2",
        "candidate_tables": 320,
        "baseline_tables": 64,
        "max_full_tables": TABLE_BUDGET,
        "workers": 4,
        "selection": {
            "fitness": "H/M 等权的根级保守差 d_low 均值",
            "keep": 3,
            "forced_parent_control": PARENT_CONTROL,
            "rule": (
                "按适应度降序、config_id 升序取前2个非父代；稳定 V2 零效应对照"
                "强制占第3席。阶段A固定完成后才选择，不以中途结果停表。"
            ),
            "meaning": "预算分配，不是显著性检验；未续评记 NOT_SELECTED_WITHIN_BUDGET",
        },
        "phase_plan": {
            "a": "5配置，H/M各4根，共384桌",
            "b": "3配置追加H/M各8根，共512桌；累计每类12根",
            "c": "冠军候选与V2追加H/M各16根，共768桌；累计每类28根",
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
    print("prepared route microfunction phase A: 5 configs, 8 roots/config, 384 tables")


def verify_inputs(plan: dict) -> list[dict]:
    guard.verify(plan["runtime"])
    for path_key, sha_key in (("behavior_preflight", "behavior_preflight_sha256"),
                              ("contract", "contract_sha256")):
        if sha256_bytes(Path(plan[path_key]).read_bytes()) != plan[sha_key]:
            raise ValueError(path_key + " 漂移")
    current = configurations()
    if current != plan["configurations"]:
        raise ValueError("路线微函数配置清单漂移")
    return current


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    seats = {}
    for seat in SEATS:
        plans = second.first.plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {"table_ids": [item.table_id for item in plans],
                            "table_seeds": [item.seed for item in plans]}
    return wiring._digest({"generator": "r10-route-microfunction-search-a/1",
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


def arm_view(raw: dict, identity: str) -> dict:
    return {key: raw.get(key) for key in (
        "status", "usable", "error", "focal_stage_score",
        "stage_totals_by_participant", "u", "u_low", "u_high",
        "unresolved", "elapsed_ms")} | {"candidate_id": identity, "policy_id": identity}


def select_for_b(ranking: list[dict]) -> list[str]:
    chosen = [row["config_id"] for row in ranking
              if row["config_id"] != PARENT_CONTROL][:2]
    chosen.append(PARENT_CONTROL)
    return chosen


def summarize_a() -> None:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    configs = verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": TABLE_BUDGET})
    if ledger.spent("tables_full") != TABLE_BUDGET:
        raise ValueError("路线微函数阶段 A 费用未完整结算")
    contract = batch.read(CONTRACT)
    samples, ranking_rows = [], []
    for row in configs:
        candidate_samples = []
        for mix in MIXES:
            for root in ROOTS:
                root_id = f"r10rmfa-{mix}-{plan['panel_seed']}-root{root:02d}"
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
        stats = archive.paired_stage_statistics(candidate_samples, min_roots=4)
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
                     key=lambda item: (-item["fitness_mean_delta_low"], item["config_id"]))
    selected = select_for_b(ordered)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-samples.json"), samples)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json"), {
        "schema": "r10-route-microfunction-phase-a-ranking/1",
        "ranking": [{**row, "rank": index + 1,
                     "disposition": ("ADVANCE_TO_B" if row["config_id"] in selected
                                     else "NOT_SELECTED_WITHIN_BUDGET")}
                    for index, row in enumerate(ordered)],
        "selected_for_b": selected,
        "selection_rule": plan["selection"],
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-b-freeze.json"), {
        "schema": "r10-route-microfunction-phase-b-freeze/1",
        "created_after_complete_phase_a": True,
        "phase_a_manifest_sha256": sha256_bytes((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_bytes()),
        "phase_a_ranking_sha256": sha256_bytes((_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json")).read_bytes()),
        "selected_configuration_ids": selected,
        "forced_parent_control": PARENT_CONTROL,
        "new_root_indices": list(range(5, 13)),
        "cumulative_roots_per_mix": 12,
        "planned_candidate_tables": 384,
        "baseline_new_tables": 128,
        "selection_keep": 2,
        "fitness": plan["selection"]["fitness"],
        "model_calls": 0,
        "confirmation_roots": 0,
        "release_eligible": False,
    })
    parent = next(item for item in ordered if item["config_id"] == PARENT_CONTROL)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {
        "status": "COMPLETE_ROUTE_MICROFUNCTION_PHASE_A_DEVELOPMENT_RANKING",
        "configurations": 5,
        "families": 2,
        "roots_per_mix": 4,
        "candidate_tables": 320,
        "baseline_tables": 64,
        "full_tables": TABLE_BUDGET,
        "selected_for_b": selected,
        "leader": ordered[0],
        "parent_control": parent,
        "spent": ledger.account_summary(),
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
        "next": "按 phase-b-freeze 补 H/M 各8根；阶段A仅分配预算",
    })
    print(json.dumps({
        "status": "COMPLETE_ROUTE_MICROFUNCTION_PHASE_A_DEVELOPMENT_RANKING",
        "leader": ordered[0]["config_id"],
        "fitness": ordered[0]["fitness_mean_delta_low"],
        "parent_fitness": parent["fitness_mean_delta_low"],
        "selected_for_b": selected,
    }, ensure_ascii=False), flush=True)


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
    if len(completed) != 6:
        raise ValueError("路线微函数阶段 A 工作单元未全部完成")
    summarize_a()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-a", "summarize-a"))
    args = parser.parse_args()
    {"prepare": prepare, "run-a": run_a, "summarize-a": summarize_a}[args.operation]()
