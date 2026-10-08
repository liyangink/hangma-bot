"""R10 多父代窗口交叉阶段 B：四配置追加 H/M 各八个共同来源根。"""
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
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import cross_specialist_panel_a as phase_a  # noqa: E402
import cross_specialist_policy as policy  # noqa: E402
import followup_research_stage as research  # noqa: E402
import sitin_archive as archive  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
from confirmation_execution_probe import execute_arm  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402


BATCH = phase_a.BATCH
OUT = BATCH / "effect-b"
A_OUT = phase_a.OUT
A_MANIFEST = A_OUT / "manifest.json"
A_RANKING = A_OUT / "phase-a-ranking.json"
A_SAMPLES = A_OUT / "phase-a-samples.json"
A_CONCLUSION = A_OUT / "development-conclusion.json"
CONTRACT = phase_a.CONTRACT
ROUTE_SOURCE = phase_a.ROUTE_SOURCE
ROOTS = tuple(range(5, 13))
MIXES = phase_a.MIXES
SEATS = phase_a.SEATS
BASELINE_ID = phase_a.BASELINE_ID
MAX_TABLES = 640


def digest(path: Path) -> str:
    """计算冻结输入摘要。"""
    return phase_a.digest(path)


def selected_configurations() -> list[dict]:
    """只恢复阶段 A 事后冻结的四个配置。"""
    ranking = batch.read(A_RANKING)
    selected = ranking["selected_for_b"]
    expected = {"followup_discard", "route_all", "route_claim_only", "cross_followup_claim"}
    if len(selected) != 4 or set(selected) != expected:
        raise ValueError("阶段 A 冻结的四配置清单漂移")
    rows = {row["config_id"]: row for row in phase_a.configurations()}
    return [rows[config_id] for config_id in selected]


def source_paths() -> list[Path]:
    """列出阶段 B 恢复时必须保持相同的代码与阶段 A 证据。"""
    return [
        Path(__file__),
        Path(phase_a.__file__),
        Path(policy.__file__),
        Path(research.__file__),
        Path(archive.__file__),
        Path(wiring.__file__),
        A_MANIFEST,
        A_RANKING,
        A_SAMPLES,
        A_CONCLUSION,
        CONTRACT,
        ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结阶段 B 的 640 桌追加开发预算；仍不使用确认或发布账户。"""
    if OUT.exists():
        raise SystemExit("多父代交叉阶段 B 已存在；拒绝覆盖")
    a_plan = batch.read(A_MANIFEST)
    phase_a.verify_inputs(a_plan)
    a_summary = batch.read(A_OUT / "summary.json")
    if a_summary["status"] != "COMPLETE_CROSS_SPECIALIST_PHASE_A_COMPONENT_SCREEN":
        raise ValueError("阶段 A 尚未完整结束")
    configs = selected_configurations()
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-cross-specialist-01-b",
        authorization_id="r10-cross-specialist-01-b-20260921",
        accounts={"tables_full": MAX_TABLES},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "阶段A组件筛选已完整结束；按预冻结规则追加共同根区分交叉噪声与吃碰专长",
        "scope": "开发阶段B；四配置追加H/M各8根、4座位、每阶段2桌；累计每类12根；不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    research.natural.require_authorization(authorization)
    batch.write(OUT / "authorization.json", authorization)
    runtime = guard.capture(source_paths=source_paths() + [OUT / "authorization.json"])
    manifest = {
        "schema": "r10-cross-specialist-panel-b/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "phase_a_manifest": str(A_MANIFEST),
        "phase_a_manifest_sha256": digest(A_MANIFEST),
        "phase_a_ranking": str(A_RANKING),
        "phase_a_ranking_sha256": digest(A_RANKING),
        "phase_a_samples": str(A_SAMPLES),
        "phase_a_samples_sha256": digest(A_SAMPLES),
        "phase_a_conclusion": str(A_CONCLUSION),
        "phase_a_conclusion_sha256": digest(A_CONCLUSION),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "route_source": str(ROUTE_SOURCE),
        "route_source_sha256": digest(ROUTE_SOURCE),
        "rules_hash": research.natural.compute_rules_hash(research.natural.REPO),
        "panel_seed": a_plan["panel_seed"],
        "opponents": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "tables_per_arm": 2,
        "baseline_policy_id": BASELINE_ID,
        "configurations": configs,
        "configuration_ids": [row["config_id"] for row in configs],
        "baseline_tables": 128,
        "candidate_tables": 512,
        "max_full_tables": MAX_TABLES,
        "workers": 4,
        "selection": {
            "fitness": "阶段A+B累计 H/M 等权根级保守差 d_low 均值",
            "purpose": "阶段C预算分配，不是强度检验",
            "rule": (
                "路线仅吃碰与完整路线父代强制进入阶段C；交叉体只有累计H/M等权点估计>0、"
                "至少一个H/M区间上界>0且无回退才进入阶段C。后继质量父代不单独进入阶段C。"
            ),
            "final_reference": "未选入交叉体时，阶段C比较路线仅吃碰、完整路线和共同V2基线三种策略。",
            "no_parameter_tuning": True,
        },
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(OUT / "manifest.json", manifest)
    batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": MAX_TABLES}
    ).save()
    print(json.dumps({
        "status": "PREPARED_CROSS_SPECIALIST_B",
        "configurations": len(configs),
        "baseline_tables": 128,
        "candidate_tables": 512,
        "max_full_tables": MAX_TABLES,
    }, ensure_ascii=False))


def verify_inputs(plan: dict) -> None:
    """核对阶段 A 原件、当前源码、合同及冻结四配置。"""
    guard.verify(plan["runtime"])
    for path_key, sha_key in (
        ("phase_a_manifest", "phase_a_manifest_sha256"),
        ("phase_a_ranking", "phase_a_ranking_sha256"),
        ("phase_a_samples", "phase_a_samples_sha256"),
        ("phase_a_conclusion", "phase_a_conclusion_sha256"),
        ("contract", "contract_sha256"),
        ("route_source", "route_source_sha256"),
    ):
        if digest(Path(plan[path_key])) != plan[sha_key]:
            raise ValueError(path_key + " 摘要漂移")
    phase_a.verify_inputs(batch.read(A_MANIFEST))
    if selected_configurations() != plan["configurations"]:
        raise ValueError("阶段 B 配置身份漂移")


def plans_for(contract: dict, mix: str, root: int, seat: int, plan: dict):
    """从阶段 A 相同 panel_seed 追加未见根。"""
    return research.natural.build_seat_stage_plans(
        contract=contract,
        opponent=mix,
        root_index=root,
        focal_seat=seat,
        panel_seed=plan["panel_seed"],
    )


def run_baseline_all() -> dict:
    """执行阶段 B 新根的共同 V2 基线。"""
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    contract = batch.read(CONTRACT)
    ledger = batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": MAX_TABLES}
    )
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = plans_for(contract, mix, root, seat, plan)
                label = f"b-baseline-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label,
                    "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "baseline",
                    "candidate_id": BASELINE_ID,
                }
                checked = execute_arm(
                    OUT / "baseline" / label,
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
    """执行一个阶段 B 候选的全部新根。"""
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    row = next(item for item in plan["configurations"] if item["mode"] == mode)
    contract = batch.read(CONTRACT)
    route_source = ROUTE_SOURCE.read_text(encoding="utf-8")
    factory = phase_a.policy_factory(mode, route_source, digest(ROUTE_SOURCE)[:16])
    ledger = batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": MAX_TABLES}
    )
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = plans_for(contract, mix, root, seat, plan)
                label = f"b-{mode}-{mix}-r{root:02d}-s{seat}"
                expected = {
                    "step_id": label,
                    "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": "candidate",
                    "candidate_id": row["candidate_id"],
                }
                checked = execute_arm(
                    OUT / "candidates" / mode / label,
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
    """保留阶段统计需要的结果字段。"""
    return phase_a.arm_view(raw, identity)


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    """冻结阶段 B 一个根的四座位和两桌种子集合。"""
    seats = {}
    for seat in SEATS:
        plans = plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {
            "table_ids": [item.table_id for item in plans],
            "table_seeds": [item.seed for item in plans],
        }
    return wiring._digest({
        "generator": "r10-cross-specialist-panel-b/1",
        "panel_seed": plan["panel_seed"],
        "opponent_mix": mix,
        "root_index": root,
        "seats": seats,
    })


def audit_summary(mode: str) -> dict:
    """汇总阶段 B 新根上的行为、回退和研究成本。"""
    statuses: Counter = Counter()
    components: Counter = Counter()
    changes: Counter = Counter()
    runtime: Counter = Counter()
    elapsed = []
    decisions = 0
    rule_calls = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                label = f"b-{mode}-{mix}-r{root:02d}-s{seat}"
                raw = batch.read(
                    OUT / "candidates" / mode / label / "result.json"
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


def combine_audits(a: dict, b: dict) -> dict:
    """合并两个互斥根集合的逐决策计数与耗时。"""
    def merged_counter(key: str) -> dict:
        value = Counter(a.get(key, {}))
        value.update(b.get(key, {}))
        return dict(value)

    return {
        "decisions": a["decisions"] + b["decisions"],
        "statuses": merged_counter("statuses"),
        "components": merged_counter("components"),
        "changes_by_component": merged_counter("changes_by_component"),
        "first_changes": a["first_changes"] + b["first_changes"],
        "rule_calls": a["rule_calls"] + b["rule_calls"],
        "max_decision_seconds": max(a["max_decision_seconds"], b["max_decision_seconds"]),
        "total_decision_seconds": a["total_decision_seconds"] + b["total_decision_seconds"],
        "runtime_counts": merged_counter("runtime_counts"),
        "has_fallback": a["has_fallback"] or b["has_fallback"],
    }


def summarize_b() -> None:
    """合并 A/B 十二根统计，冻结阶段 C 的三策略或四策略比较。"""
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": MAX_TABLES}
    )
    if ledger.spent("tables_full") != MAX_TABLES:
        raise ValueError("多父代交叉阶段 B 费用未完整结算")
    contract = batch.read(CONTRACT)
    old_samples = batch.read(A_SAMPLES)
    old_audits = batch.read(A_OUT / "phase-a-audits.json")
    new_samples = []
    ranking = []
    cumulative_audits = {}
    for config in plan["configurations"]:
        mode = config["mode"]
        candidate_new = []
        for mix in MIXES:
            for root in ROOTS:
                root_id = f"r10cs-{mix}-{plan['panel_seed']}-root{root:02d}"
                content = root_digest(plan, mix, root, contract)
                for seat in SEATS:
                    baseline_label = f"b-baseline-{mix}-r{root:02d}-s{seat}"
                    candidate_label = f"b-{mode}-{mix}-r{root:02d}-s{seat}"
                    baseline = batch.read(
                        OUT / "baseline" / baseline_label / "result.json"
                    )["raw"]
                    candidate = batch.read(
                        OUT / "candidates" / mode / candidate_label / "result.json"
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
                    candidate_new.append(sample)
                    new_samples.append(sample)
        previous = [
            sample for sample in old_samples
            if sample["candidate_id"] == config["candidate_id"]
        ]
        cumulative = previous + candidate_new
        stats = archive.paired_stage_statistics(cumulative, min_roots=12)
        if stats["invalid_count"] or stats["uncomputable_count"]:
            raise ValueError("多父代配置累计样本无效：" + mode)
        normal = stats["by_candidate"][config["candidate_id"]]["panels"]["normal"]
        panels = normal["panels"]
        if set(panels) != set(MIXES) or any(
            panel["status"] != "ok" or not panel["manifest_complete"]
            for panel in panels.values()
        ):
            raise ValueError("多父代配置累计根清单不完整：" + mode)
        cumulative_audits[mode] = combine_audits(old_audits[mode], audit_summary(mode))
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
            "audit": cumulative_audits[mode],
        })
    ordered = sorted(
        ranking,
        key=lambda row: (-row["fitness_mean_delta_low"], row["config_id"]),
    )
    cross = next(row for row in ordered if row["is_crossover"])
    cross_allowed = (
        cross["mean_delta"] > 0.0
        and any(cross[mix]["interval_95"][1] > 0.0 for mix in MIXES)
        and not cross["audit"]["has_fallback"]
    )
    selected = ["route_claim_only", "route_all"]
    if cross_allowed:
        selected.append("cross_followup_claim")
    batch.write(OUT / "phase-b-new-samples.json", new_samples)
    batch.write(OUT / "phase-b-cumulative-audits.json", cumulative_audits)
    batch.write(OUT / "phase-b-ranking.json", {
        "schema": "r10-cross-specialist-phase-b-ranking/1",
        "ranking": [
            {
                **row,
                "rank": index + 1,
                "disposition": (
                    "ADVANCE_TO_C" if row["config_id"] in selected
                    else "NOT_SELECTED_WITHIN_BUDGET"
                ),
            }
            for index, row in enumerate(ordered)
        ],
        "selected_for_c": selected,
        "cross_allowed": cross_allowed,
        "selection_rule": plan["selection"],
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(OUT / "phase-c-freeze.json", {
        "schema": "r10-cross-specialist-phase-c-freeze/1",
        "created_after_complete_phase_b": True,
        "phase_b_manifest_sha256": digest(OUT / "manifest.json"),
        "phase_b_ranking_sha256": digest(OUT / "phase-b-ranking.json"),
        "selected_configuration_ids": selected,
        "new_root_indices": list(range(13, 29)),
        "cumulative_roots_per_mix": 28,
        "planned_candidate_tables": len(selected) * 256,
        "baseline_new_tables": 256,
        "comparison_policies_including_baseline": len(selected) + 1,
        "fitness": plan["selection"]["fitness"],
        "model_calls": 0,
        "confirmation_roots": 0,
        "release_eligible": False,
    })
    disposition = (
        "EXTEND_CROSS_TO_C" if cross_allowed
        else "CLOSE_CROSSOVER_KEEP_ROUTE_CLAIM_SPECIALIST"
    )
    batch.write(OUT / "development-conclusion.json", {
        "schema": "r10-cross-specialist-b-conclusion/1",
        "leader": ordered[0],
        "crossover": cross,
        "selected_for_c": selected,
        "disposition": disposition,
        "interpretation": (
            "累计十二根仍只用于开发选留；若关闭交叉，则后继质量父代不再消耗阶段C预算。"
        ),
        "next": "按 phase-c-freeze 追加 H/M 各16根，形成累计28根开发裁定。",
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(OUT / "summary.json", {
        "status": "COMPLETE_CROSS_SPECIALIST_PHASE_B_CUMULATIVE_SCREEN",
        "configurations": len(plan["configurations"]),
        "new_roots_per_mix": len(ROOTS),
        "cumulative_roots_per_mix": 12,
        "candidate_tables": 512,
        "baseline_tables": 128,
        "full_tables": MAX_TABLES,
        "leader": ordered[0],
        "crossover": cross,
        "selected_for_c": selected,
        "disposition": disposition,
        "spent": ledger.account_summary(),
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "COMPLETE_CROSS_SPECIALIST_PHASE_B_CUMULATIVE_SCREEN",
        "leader": ordered[0]["config_id"],
        "leader_fitness": ordered[0]["fitness_mean_delta_low"],
        "crossover_mean": cross["mean_delta"],
        "selected_for_c": selected,
        "disposition": disposition,
    }, ensure_ascii=False, indent=2))


def run_b() -> None:
    """并行执行共同基线和四个阶段 B 候选，结束后统一汇总。"""
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    context = multiprocessing.get_context("spawn")
    completed = []
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=plan["workers"], mp_context=context
    ) as pool:
        futures = [pool.submit(run_baseline_all)]
        futures.extend(
            pool.submit(run_configuration, row["mode"])
            for row in plan["configurations"]
        )
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
    if len(completed) != len(plan["configurations"]) + 1:
        raise ValueError("多父代交叉阶段 B 工作单元未全部完成")
    summarize_b()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-b"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else run_b()
