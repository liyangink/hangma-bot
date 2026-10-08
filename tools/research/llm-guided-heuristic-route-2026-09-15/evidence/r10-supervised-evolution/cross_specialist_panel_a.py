"""R10 多父代窗口交叉阶段 A：两个父代、两个消融与交叉体的共同新来源筛选。"""
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
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import cross_specialist_checks as preflight  # noqa: E402
import cross_specialist_policy as policy  # noqa: E402
import followup_research_stage as research  # noqa: E402
import sitin_archive as archive  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
from confirmation_execution_probe import execute_arm  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921/effect-a')
PREFLIGHT_MANIFEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921/manifest.json')
PREFLIGHT_CHECKS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921/checks.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
ROUTE_SOURCE = preflight.ROUTE_SOURCE
PANEL_SEED = 2026092202
ROOTS = tuple(range(1, 5))
MIXES = ("H", "M")
SEATS = tuple(range(4))
MODES = (
    "followup_discard",
    "route_all",
    "route_draw_only",
    "route_claim_only",
    "cross_followup_claim",
)
BASELINE_ID = "ComparableHeuristicPolicyV2"
MAX_TABLES = 384


def digest(path: Path) -> str:
    """计算冻结输入摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_for(mode: str) -> str:
    """返回模拟执行实际暴露的策略身份。"""
    return "offline-cross-specialist-v1:" + mode + ":" + digest(ROUTE_SOURCE)[:16]


def configurations() -> list[dict]:
    """构造冻结父代、消融和多父代交叉清单。"""
    families = {
        "followup_discard": "PARENT_FOLLOWUP_DISCARD",
        "route_all": "PARENT_ROUTE_ALL",
        "route_draw_only": "ABLATION_ROUTE_DRAW",
        "route_claim_only": "ABLATION_ROUTE_CLAIM",
        "cross_followup_claim": "CROSSOVER_FOLLOWUP_CLAIM",
    }
    return [
        {
            "config_id": mode,
            "mode": mode,
            "family": families[mode],
            "candidate_id": identity_for(mode),
            "is_parent": mode in {"followup_discard", "route_all"},
            "is_crossover": mode == "cross_followup_claim",
        }
        for mode in MODES
    ]


def source_paths() -> list[Path]:
    """列出恢复时必须保持相同的代码与证据输入。"""
    return [
        Path(__file__),
        Path(policy.__file__),
        Path(research.__file__),
        Path(archive.__file__),
        Path(wiring.__file__),
        PREFLIGHT_MANIFEST,
        PREFLIGHT_CHECKS,
        CONTRACT,
        ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结 384 桌开发预算和共同新来源；本阶段不形成强度或发布结论。"""
    if OUT.exists():
        raise SystemExit("多父代交叉阶段 A 已存在；拒绝覆盖")
    if any(
        str(PANEL_SEED) in path.read_text(encoding="utf-8", errors="ignore")
        for path in HERE.glob("**/*.json")
    ):
        raise ValueError("多父代交叉 panel_seed 已出现在既有证据 JSON")
    frozen_preflight = batch.read(PREFLIGHT_MANIFEST)
    preflight.verify(frozen_preflight)
    if batch.read(PREFLIGHT_CHECKS)["status"] != "PASS_OFFLINE_BEHAVIOR_ONLY":
        raise ValueError("多父代交叉行为预检尚未通过")
    contract = batch.read(CONTRACT)
    if contract["group"]["tables_per_group"] != 2:
        raise ValueError("阶段预算只适用于每阶段两桌")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-cross-specialist-01-a",
        authorization_id="r10-cross-specialist-01-a-20260921",
        accounts={"tables_full": MAX_TABLES},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "用户取消旧目标并要求按文献调研方向推进新目标；多父代窗口交叉已完成真实请求预检",
        "scope": "开发阶段A；两父代、两消融、一交叉体，H/M各4根、4座位、每阶段2桌；不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    research.natural.require_authorization(authorization)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-cross-specialist-panel-a/1",
        "created_at_utc": batch.search.utc_now(),
        "hypothesis": (
            "用后继质量父代处理摸牌弃牌、用路线父代处理 chi/peng 响应，"
            "可保留动作族专长并减少奖励跨动作族传播。"
        ),
        "runtime": runtime,
        "behavior_preflight": str(PREFLIGHT_MANIFEST),
        "behavior_preflight_sha256": digest(PREFLIGHT_MANIFEST),
        "behavior_checks": str(PREFLIGHT_CHECKS),
        "behavior_checks_sha256": digest(PREFLIGHT_CHECKS),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "route_source": str(ROUTE_SOURCE),
        "route_source_sha256": digest(ROUTE_SOURCE),
        "rules_hash": research.natural.compute_rules_hash(research.natural.REPO),
        "panel_seed": PANEL_SEED,
        "opponents": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "tables_per_arm": 2,
        "baseline_policy_id": BASELINE_ID,
        "configurations": configurations(),
        "configuration_ids": list(MODES),
        "baseline_tables": 64,
        "candidate_tables": 320,
        "max_full_tables": MAX_TABLES,
        "workers": 4,
        "selection": {
            "fitness": "H/M 等权的根级保守差 d_low 均值",
            "purpose": "组件归因和阶段B预算分配，不是强度检验",
            "rule": (
                "比较交叉体、两个原父代和两个单侧消融。只有交叉体至少满足："
                "H/M 任一面板的95%区间上界大于0，且行为审计无事实/成本/执行回退，"
                "才允许保留到下一批；两个父代强制保留作因果对照。"
            ),
            "no_parameter_tuning": True,
        },
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": MAX_TABLES}
    ).save()
    print(json.dumps({
        "status": "PREPARED_CROSS_SPECIALIST_A",
        "configurations": len(MODES),
        "baseline_tables": 64,
        "candidate_tables": 320,
        "max_full_tables": MAX_TABLES,
    }, ensure_ascii=False))


def verify_inputs(plan: dict) -> None:
    """每个工作单元执行前后核对源码、合同、预检和配置身份。"""
    guard.verify(plan["runtime"])
    for path_key, sha_key in (
        ("behavior_preflight", "behavior_preflight_sha256"),
        ("behavior_checks", "behavior_checks_sha256"),
        ("contract", "contract_sha256"),
        ("route_source", "route_source_sha256"),
    ):
        if digest(Path(plan[path_key])) != plan[sha_key]:
            raise ValueError(path_key + " 摘要漂移")
    preflight.verify(batch.read(PREFLIGHT_MANIFEST))
    if configurations() != plan["configurations"]:
        raise ValueError("多父代交叉配置身份漂移")


def plans_for(contract: dict, mix: str, root: int, seat: int, plan: dict):
    """从共同 panel_seed 构造同牌山、换座位阶段。"""
    return research.natural.build_seat_stage_plans(
        contract=contract,
        opponent=mix,
        root_index=root,
        focal_seat=seat,
        panel_seed=plan["panel_seed"],
    )


def policy_factory(mode: str, route_source: str, route_identity: str):
    """为每个完整阶段新建策略，避免审计或缓存跨阶段泄漏。"""
    return lambda config: policy.CrossSpecialistPolicy(
        config,
        lambda: 800.0,
        mode=mode,
        route_source=route_source,
        identity=route_identity,
        value_limits=ValueAnalysisLimits(),
    )


def run_baseline_all() -> dict:
    """执行所有配置共同复用的稳定 V2 基线。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(plan)
    contract = batch.read(CONTRACT)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": MAX_TABLES}
    )
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = plans_for(contract, mix, root, seat, plan)
                label = f"a-baseline-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label,
                    "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "baseline",
                    "candidate_id": BASELINE_ID,
                }
                checked = execute_arm(
                    _project_file(_PROJECT_ROOT, OUT / "baseline" / label),
                    expected=expected,
                    ledger=ledger,
                    runner=lambda plans=plans, mix=mix: research.run_stage(
                        plans, mix, "baseline", contract, lambda _config: None
                    ),
                    verifier=lambda raw, plans=plans: research.verify_stage(
                        raw, plans, contract, plan["rules_hash"], "baseline", BASELINE_ID
                    ),
                )
                count += checked["tables"]
    verify_inputs(plan)
    return {"kind": "baseline", "tables": count}


def run_configuration(mode: str) -> dict:
    """执行一个冻结父代、消融或交叉配置的全部 H/M 根。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(plan)
    row = next(item for item in plan["configurations"] if item["mode"] == mode)
    contract = batch.read(CONTRACT)
    route_source = ROUTE_SOURCE.read_text(encoding="utf-8")
    route_identity = digest(ROUTE_SOURCE)[:16]
    factory = policy_factory(mode, route_source, route_identity)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": MAX_TABLES}
    )
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = plans_for(contract, mix, root, seat, plan)
                label = f"a-{mode}-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label,
                    "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "candidate",
                    "candidate_id": row["candidate_id"],
                }
                checked = execute_arm(
                    _project_file(_PROJECT_ROOT, OUT / "candidates" / mode / label),
                    expected=expected,
                    ledger=ledger,
                    runner=lambda plans=plans, mix=mix: research.run_stage(
                        plans, mix, "candidate", contract, factory
                    ),
                    verifier=lambda raw, plans=plans: research.verify_stage(
                        raw, plans, contract, plan["rules_hash"],
                        "candidate", row["candidate_id"]
                    ),
                )
                count += checked["tables"]
    verify_inputs(plan)
    return {"kind": "candidate", "config_id": mode, "tables": count}


def arm_view(raw: dict, identity: str) -> dict:
    """保留阶段统计需要的结果，不把全量牌谱重复写入样本清单。"""
    return {key: raw.get(key) for key in (
        "status", "usable", "error", "focal_stage_score",
        "stage_totals_by_participant", "u", "u_low", "u_high",
        "unresolved", "elapsed_ms",
    )} | {"candidate_id": identity, "policy_id": identity}


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    """冻结一个根的四座位和两桌种子集合。"""
    seats = {}
    for seat in SEATS:
        plans = plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {
            "table_ids": [item.table_id for item in plans],
            "table_seeds": [item.seed for item in plans],
        }
    return wiring._digest({
        "generator": "r10-cross-specialist-panel-a/1",
        "panel_seed": plan["panel_seed"],
        "opponent_mix": mix,
        "root_index": root,
        "seats": seats,
    })


def audit_summary(mode: str) -> dict:
    """汇总逐决策父代分派、行为变化、回退与研究成本。"""
    statuses: Counter = Counter()
    components: Counter = Counter()
    changes: Counter = Counter()
    runtime: Counter = Counter()
    elapsed = []
    rule_calls = 0
    decisions = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                label = f"a-{mode}-{mix}-r{root:02d}-s{seat}"
                raw = batch.read(
                    _project_file(_PROJECT_ROOT, OUT / "candidates" / mode / label / "result.json")
                )["raw"]
                for table in raw["tables"]:
                    runtime.update(table["result"]["runtime_counts"])
                    for row in table["prototype_audit"]:
                        decisions += 1
                        statuses[row["status"]] += 1
                        components[row["component"]] += 1
                        changes[row["component"]] += int(row["changed"])
                        rule_calls += row["rule_calls"]
                        elapsed.append(row.get("wrapper_elapsed_seconds", row["elapsed_seconds"]))
    return {
        "decisions": decisions,
        "statuses": dict(statuses),
        "components": dict(components),
        "changes_by_component": dict(changes),
        "first_changes": sum(changes.values()),
        "rule_calls": rule_calls,
        "max_decision_seconds": max(elapsed, default=0.0),
        "total_decision_seconds": sum(elapsed),
        "runtime_counts": dict(runtime),
        "has_fallback": any(statuses[name] for name in (
            "FACT_FALLBACK", "COST_FALLBACK", "ERROR_FALLBACK"
        )),
    }


def summarize_a() -> None:
    """复算完整样本、组件归因和开发排序，再冻结是否进入下一批。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": MAX_TABLES}
    )
    if ledger.spent("tables_full") != MAX_TABLES:
        raise ValueError("多父代交叉阶段 A 费用未完整结算")
    contract = batch.read(CONTRACT)
    samples = []
    ranking = []
    audits = {}
    for config in plan["configurations"]:
        mode = config["mode"]
        candidate_samples = []
        for mix in MIXES:
            for root in ROOTS:
                root_id = f"r10cs-{mix}-{plan['panel_seed']}-root{root:02d}"
                content = root_digest(plan, mix, root, contract)
                for seat in SEATS:
                    baseline_label = f"a-baseline-{mix}-r{root:02d}-s{seat}"
                    candidate_label = f"a-{mode}-{mix}-r{root:02d}-s{seat}"
                    baseline = batch.read(
                        _project_file(_PROJECT_ROOT, OUT / "baseline" / baseline_label / "result.json")
                    )["raw"]
                    candidate = batch.read(
                        _project_file(_PROJECT_ROOT, OUT / "candidates" / mode / candidate_label / "result.json")
                    )["raw"]
                    sample = {
                        "schema": research.natural.NATURAL_SAMPLE_SCHEMA,
                        "source_root_id": root_id,
                        "root_content_digest": content,
                        "root_index": root,
                        "root_usage": "development_component_ablation",
                        "candidate_id": config["candidate_id"],
                        "opponent_mix": mix,
                        "scenario": "normal",
                        "focal_anchor_seat": seat,
                        "root_expected": {
                            "seats": 4,
                            "arms": ["baseline", "candidate"],
                            "tables_per_arm": 2,
                        },
                        "arms": {
                            "baseline": arm_view(baseline, BASELINE_ID),
                            "candidate": arm_view(candidate, config["candidate_id"]),
                        },
                        "completeness": "complete",
                        "invalid_reasons": [],
                        "cost": {
                            "budget_units": 4,
                            "elapsed_ms": baseline["elapsed_ms"] + candidate["elapsed_ms"],
                        },
                    }
                    candidate_samples.append(sample)
                    samples.append(sample)
        stats = archive.paired_stage_statistics(candidate_samples, min_roots=4)
        if stats["invalid_count"] or stats["uncomputable_count"]:
            raise ValueError("多父代配置存在无效样本：" + mode)
        normal = stats["by_candidate"][config["candidate_id"]]["panels"]["normal"]
        panels = normal["panels"]
        if set(panels) != set(MIXES) or any(
            panel["status"] != "ok" or not panel["manifest_complete"]
            for panel in panels.values()
        ):
            raise ValueError("多父代配置根清单不完整：" + mode)
        audits[mode] = audit_summary(mode)
        ranking.append({
            **config,
            "fitness_mean_delta_low": normal["declared_mix"]["mean_delta_low"],
            "mean_delta": normal["declared_mix"]["mean_delta"],
            "mean_delta_high": normal["declared_mix"]["mean_delta_high"],
            "H": {key: panels["H"][key] for key in (
                "n_roots", "mean_delta", "standard_error", "interval_95"
            )},
            "M": {key: panels["M"][key] for key in (
                "n_roots", "mean_delta", "standard_error", "interval_95"
            )},
            "audit": audits[mode],
        })
    ordered = sorted(
        ranking,
        key=lambda row: (-row["fitness_mean_delta_low"], row["config_id"]),
    )
    cross = next(row for row in ordered if row["is_crossover"])
    cross_has_positive_support = any(
        cross[mix]["interval_95"][1] > 0.0 for mix in MIXES
    )
    cross_allowed = cross_has_positive_support and not cross["audit"]["has_fallback"]
    selected = ["followup_discard", "route_all"]
    if cross_allowed:
        selected.append("cross_followup_claim")
        ablation = next(
            row for row in ordered
            if row["config_id"] in {"route_draw_only", "route_claim_only"}
        )
        selected.append(ablation["config_id"])
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-samples.json"), samples)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-audits.json"), audits)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json"), {
        "schema": "r10-cross-specialist-phase-a-ranking/1",
        "ranking": [
            {
                **row,
                "rank": index + 1,
                "disposition": (
                    "ADVANCE_TO_B" if row["config_id"] in selected
                    else "NOT_SELECTED_WITHIN_BUDGET"
                ),
            }
            for index, row in enumerate(ordered)
        ],
        "selected_for_b": selected,
        "cross_has_positive_support": cross_has_positive_support,
        "cross_allowed": cross_allowed,
        "selection_rule": plan["selection"],
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    disposition = (
        "EXTEND_CROSS_AND_COMPONENT_CONTROLS" if cross_allowed
        else "CLOSE_CROSS_AND_REVIEW_PARENTS_AGAINST_LITERATURE"
    )
    batch.write(_project_file(_PROJECT_ROOT, OUT / "development-conclusion.json"), {
        "schema": "r10-cross-specialist-development-conclusion/1",
        "created_after_complete_phase_a": True,
        "phase_a_manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "phase_a_ranking_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json")),
        "leader": ordered[0],
        "crossover": cross,
        "selected_for_b": selected,
        "disposition": disposition,
        "interpretation": (
            "阶段A仅回答动作窗口组件是否值得继续分配预算；四根/对手池不足以形成算法强度结论。"
        ),
        "next": (
            "使用同一panel_seed追加新根，比较交叉体、两父代和最佳单侧消融"
            if cross_allowed else
            "回读EoH/ReEvo/LLaMEA-HPO/Lexicase与麻将价值建模，检查父代选择和信用分配"
        ),
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {
        "status": "COMPLETE_CROSS_SPECIALIST_PHASE_A_COMPONENT_SCREEN",
        "configurations": len(MODES),
        "roots_per_mix": len(ROOTS),
        "candidate_tables": 320,
        "baseline_tables": 64,
        "full_tables": MAX_TABLES,
        "leader": ordered[0],
        "crossover": cross,
        "selected_for_b": selected,
        "disposition": disposition,
        "spent": ledger.account_summary(),
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "COMPLETE_CROSS_SPECIALIST_PHASE_A_COMPONENT_SCREEN",
        "leader": ordered[0]["config_id"],
        "leader_fitness": ordered[0]["fitness_mean_delta_low"],
        "crossover_fitness": cross["fitness_mean_delta_low"],
        "selected_for_b": selected,
        "disposition": disposition,
    }, ensure_ascii=False, indent=2))


def run_a() -> None:
    """并行执行共同基线和五个候选工作单元，结束后统一汇总。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(plan)
    context = multiprocessing.get_context("spawn")
    completed = []
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=plan["workers"], mp_context=context
    ) as pool:
        futures = [pool.submit(run_baseline_all)]
        futures.extend(pool.submit(run_configuration, mode) for mode in MODES)
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            completed.append(result)
            print(
                (result.get("config_id") or "baseline"),
                "complete",
                result["tables"],
                "tables",
                flush=True,
            )
    if len(completed) != len(MODES) + 1:
        raise ValueError("多父代交叉阶段 A 工作单元未全部完成")
    summarize_a()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-a"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else run_a()
