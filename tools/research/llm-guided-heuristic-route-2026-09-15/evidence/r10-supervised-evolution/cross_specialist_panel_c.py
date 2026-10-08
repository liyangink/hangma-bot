"""R10 路线吃碰专长阶段 C：与完整路线、共同 V2 比较并形成开发裁定。"""
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
import cross_specialist_panel_b as phase_b  # noqa: E402
import cross_specialist_policy as policy  # noqa: E402
import followup_research_stage as research  # noqa: E402
import sitin_archive as archive  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
from confirmation_execution_probe import execute_arm  # noqa: E402


BATCH = phase_a.BATCH
OUT = BATCH / "effect-c"
A_OUT = phase_a.OUT
B_OUT = phase_b.OUT
A_SAMPLES = A_OUT / "phase-a-samples.json"
B_NEW_SAMPLES = B_OUT / "phase-b-new-samples.json"
B_MANIFEST = B_OUT / "manifest.json"
B_RANKING = B_OUT / "phase-b-ranking.json"
B_AUDITS = B_OUT / "phase-b-cumulative-audits.json"
B_FREEZE = B_OUT / "phase-c-freeze.json"
CONTRACT = phase_a.CONTRACT
ROUTE_SOURCE = phase_a.ROUTE_SOURCE
ROOTS = tuple(range(13, 29))
MIXES = phase_a.MIXES
SEATS = phase_a.SEATS
BASELINE_ID = phase_a.BASELINE_ID
MAX_TABLES = 768


def digest(path: Path) -> str:
    """计算冻结输入摘要。"""
    return phase_a.digest(path)


def selected_configurations() -> list[dict]:
    """恢复阶段 B 冻结的路线吃碰专长与完整路线父代。"""
    freeze = batch.read(B_FREEZE)
    ids = freeze["selected_configuration_ids"]
    if ids != ["route_claim_only", "route_all"]:
        raise ValueError("阶段 C 冻结配置清单漂移")
    rows = {row["config_id"]: row for row in phase_a.configurations()}
    return [rows[config_id] for config_id in ids]


def source_paths() -> list[Path]:
    """列出阶段 C 恢复时必须保持相同的代码与前序证据。"""
    return [
        Path(__file__),
        Path(phase_a.__file__),
        Path(phase_b.__file__),
        Path(policy.__file__),
        Path(research.__file__),
        Path(archive.__file__),
        Path(wiring.__file__),
        B_MANIFEST,
        B_RANKING,
        B_AUDITS,
        B_FREEZE,
        A_SAMPLES,
        B_NEW_SAMPLES,
        CONTRACT,
        ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结 768 桌阶段 C 预算和最终开发裁定规则。"""
    if OUT.exists():
        raise SystemExit("路线吃碰专长阶段 C 已存在；拒绝覆盖")
    b_plan = batch.read(B_MANIFEST)
    phase_b.verify_inputs(b_plan)
    b_summary = batch.read(B_OUT / "summary.json")
    if b_summary["status"] != "COMPLETE_CROSS_SPECIALIST_PHASE_B_CUMULATIVE_SCREEN":
        raise ValueError("阶段 B 尚未完整结束")
    configs = selected_configurations()
    freeze = batch.read(B_FREEZE)
    if freeze["new_root_indices"] != list(ROOTS) or freeze["planned_candidate_tables"] != 512:
        raise ValueError("阶段 C 根或候选预算漂移")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-cross-specialist-01-c",
        authorization_id="r10-cross-specialist-01-c-20260921",
        accounts={"tables_full": MAX_TABLES},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "阶段B累计筛选关闭负向交叉体并冻结路线吃碰专长、完整路线和V2三策略比较",
        "scope": "开发阶段C；两候选追加H/M各16根、4座位、每阶段2桌，另有共同V2基线；累计每类28根；不确认不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    research.natural.require_authorization(authorization)
    batch.write(OUT / "authorization.json", authorization)
    runtime = guard.capture(source_paths=source_paths() + [OUT / "authorization.json"])
    manifest = {
        "schema": "r10-route-claim-specialist-panel-c/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "phase_b_manifest": str(B_MANIFEST),
        "phase_b_manifest_sha256": digest(B_MANIFEST),
        "phase_b_ranking": str(B_RANKING),
        "phase_b_ranking_sha256": digest(B_RANKING),
        "phase_b_audits": str(B_AUDITS),
        "phase_b_audits_sha256": digest(B_AUDITS),
        "phase_c_freeze": str(B_FREEZE),
        "phase_c_freeze_sha256": digest(B_FREEZE),
        "phase_a_samples": str(A_SAMPLES),
        "phase_a_samples_sha256": digest(A_SAMPLES),
        "phase_b_new_samples": str(B_NEW_SAMPLES),
        "phase_b_new_samples_sha256": digest(B_NEW_SAMPLES),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "route_source": str(ROUTE_SOURCE),
        "route_source_sha256": digest(ROUTE_SOURCE),
        "rules_hash": research.natural.compute_rules_hash(research.natural.REPO),
        "panel_seed": b_plan["panel_seed"],
        "opponents": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "tables_per_arm": 2,
        "baseline_policy_id": BASELINE_ID,
        "configurations": configs,
        "configuration_ids": [row["config_id"] for row in configs],
        "baseline_tables": 256,
        "candidate_tables": 512,
        "max_full_tables": MAX_TABLES,
        "workers": 3,
        "decision": {
            "fitness": "A+B+C累计 H/M 等权根级保守差 d_low 均值",
            "positive_claim_specialist": (
                "route_claim_only 的 fitness_mean_delta_low>0、mean_delta>0、"
                "fitness 严格高于 route_all，且逐决策审计无事实/成本/执行回退。"
            ),
            "retain": (
                "满足 positive_claim_specialist 才进入全新panel_seed复核；否则关闭本结构。"
            ),
            "meaning": "开发选留，不是独立确认、显著性或发布结论。",
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
        "status": "PREPARED_ROUTE_CLAIM_SPECIALIST_C",
        "configurations": len(configs),
        "baseline_tables": 256,
        "candidate_tables": 512,
        "max_full_tables": MAX_TABLES,
    }, ensure_ascii=False))


def verify_inputs(plan: dict) -> None:
    """核对阶段 A/B 样本、阶段 C 冻结、源码与合同。"""
    guard.verify(plan["runtime"])
    for path_key, sha_key in (
        ("phase_b_manifest", "phase_b_manifest_sha256"),
        ("phase_b_ranking", "phase_b_ranking_sha256"),
        ("phase_b_audits", "phase_b_audits_sha256"),
        ("phase_c_freeze", "phase_c_freeze_sha256"),
        ("phase_a_samples", "phase_a_samples_sha256"),
        ("phase_b_new_samples", "phase_b_new_samples_sha256"),
        ("contract", "contract_sha256"),
        ("route_source", "route_source_sha256"),
    ):
        if digest(Path(plan[path_key])) != plan[sha_key]:
            raise ValueError(path_key + " 摘要漂移")
    phase_b.verify_inputs(batch.read(B_MANIFEST))
    if selected_configurations() != plan["configurations"]:
        raise ValueError("阶段 C 配置身份漂移")


def plans_for(contract: dict, mix: str, root: int, seat: int, plan: dict):
    """从相同 panel_seed 追加未见根 13–28。"""
    return research.natural.build_seat_stage_plans(
        contract=contract,
        opponent=mix,
        root_index=root,
        focal_seat=seat,
        panel_seed=plan["panel_seed"],
    )


def run_baseline_all() -> dict:
    """执行阶段 C 新根的共同 V2 基线。"""
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
                label = f"c-baseline-{mix}-r{root:02d}-s{seat}"
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
    """执行路线吃碰专长或完整路线父代的全部阶段 C 新根。"""
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
                label = f"c-{mode}-{mix}-r{root:02d}-s{seat}"
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


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    """冻结阶段 C 一个根的四座位和两桌种子集合。"""
    seats = {}
    for seat in SEATS:
        plans = plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {
            "table_ids": [item.table_id for item in plans],
            "table_seeds": [item.seed for item in plans],
        }
    return wiring._digest({
        "generator": "r10-route-claim-specialist-panel-c/1",
        "panel_seed": plan["panel_seed"],
        "opponent_mix": mix,
        "root_index": root,
        "seats": seats,
    })


def audit_summary(mode: str) -> dict:
    """汇总阶段 C 新根上的行为、回退和研究成本。"""
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
                label = f"c-{mode}-{mix}-r{root:02d}-s{seat}"
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


def summarize_c() -> None:
    """合并 28 根开发统计并裁定是否值得全新来源复核。"""
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": MAX_TABLES}
    )
    if ledger.spent("tables_full") != MAX_TABLES:
        raise ValueError("路线吃碰专长阶段 C 费用未完整结算")
    contract = batch.read(CONTRACT)
    previous_samples = batch.read(A_SAMPLES) + batch.read(B_NEW_SAMPLES)
    previous_audits = batch.read(B_AUDITS)
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
                    baseline_label = f"c-baseline-{mix}-r{root:02d}-s{seat}"
                    candidate_label = f"c-{mode}-{mix}-r{root:02d}-s{seat}"
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
                        "root_usage": "development_route_claim_specialist",
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
                            "baseline": phase_a.arm_view(baseline, BASELINE_ID),
                            "candidate": phase_a.arm_view(candidate, config["candidate_id"]),
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
        old = [
            sample for sample in previous_samples
            if sample["candidate_id"] == config["candidate_id"]
        ]
        cumulative = old + candidate_new
        stats = archive.paired_stage_statistics(cumulative, min_roots=28)
        if stats["invalid_count"] or stats["uncomputable_count"]:
            raise ValueError("路线专长累计样本无效：" + mode)
        normal = stats["by_candidate"][config["candidate_id"]]["panels"]["normal"]
        panels = normal["panels"]
        if set(panels) != set(MIXES) or any(
            panel["status"] != "ok" or not panel["manifest_complete"]
            for panel in panels.values()
        ):
            raise ValueError("路线专长累计根清单不完整：" + mode)
        cumulative_audits[mode] = phase_b.combine_audits(
            previous_audits[mode], audit_summary(mode)
        )
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
    claim = next(row for row in ordered if row["config_id"] == "route_claim_only")
    parent = next(row for row in ordered if row["config_id"] == "route_all")
    retain = (
        claim["fitness_mean_delta_low"] > 0.0
        and claim["mean_delta"] > 0.0
        and claim["fitness_mean_delta_low"] > parent["fitness_mean_delta_low"]
        and not claim["audit"]["has_fallback"]
    )
    disposition = (
        "RETAIN_ROUTE_CLAIM_FOR_NEW_SOURCE_REVIEW"
        if retain else
        "CLOSE_ROUTE_CLAIM_AND_REVIEW_LITERATURE"
    )
    batch.write(OUT / "phase-c-new-samples.json", new_samples)
    batch.write(OUT / "phase-c-cumulative-audits.json", cumulative_audits)
    batch.write(OUT / "phase-c-ranking.json", {
        "schema": "r10-route-claim-specialist-phase-c-ranking/1",
        "ranking": [
            {
                **row,
                "rank": index + 1,
                "disposition": (
                    "DEVELOPMENT_CHAMPION" if index == 0
                    else "CAUSAL_PARENT_CONTROL"
                ),
            }
            for index, row in enumerate(ordered)
        ],
        "route_claim_positive_and_beats_parent": retain,
        "decision_rule": plan["decision"],
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(OUT / "development-conclusion.json", {
        "schema": "r10-route-claim-specialist-development-conclusion/1",
        "created_after_complete_phase_c": True,
        "phase_c_manifest_sha256": digest(OUT / "manifest.json"),
        "phase_c_ranking_sha256": digest(OUT / "phase-c-ranking.json"),
        "route_claim_specialist": claim,
        "route_parent": parent,
        "route_claim_positive_and_beats_parent": retain,
        "disposition": disposition,
        "interpretation": (
            "阶段C只形成开发候选；即使保留，也必须使用全新panel_seed复核，"
            "并与稳定V2做同牌山换座位比较。"
        ),
        "next": (
            "冻结路线仅吃碰源码和全新panel_seed，先做64根/对手池的新来源复核"
            if retain else
            "回读EoH/ReEvo/LLaMEA-HPO/Lexicase及麻将副露价值文献，重构父代与信用分配"
        ),
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    batch.write(OUT / "summary.json", {
        "status": "COMPLETE_ROUTE_CLAIM_SPECIALIST_PHASE_C_DEVELOPMENT_CONCLUSION",
        "configurations": len(plan["configurations"]),
        "new_roots_per_mix": len(ROOTS),
        "cumulative_roots_per_mix": 28,
        "candidate_tables": 512,
        "baseline_tables": 256,
        "full_tables": MAX_TABLES,
        "development_champion": ordered[0],
        "route_claim_specialist": claim,
        "route_parent": parent,
        "route_claim_positive_and_beats_parent": retain,
        "disposition": disposition,
        "spent": ledger.account_summary(),
        "model_calls": 0,
        "confirmation_roots": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "COMPLETE_ROUTE_CLAIM_SPECIALIST_PHASE_C_DEVELOPMENT_CONCLUSION",
        "champion": ordered[0]["config_id"],
        "claim_fitness": claim["fitness_mean_delta_low"],
        "parent_fitness": parent["fitness_mean_delta_low"],
        "retain": retain,
        "disposition": disposition,
    }, ensure_ascii=False, indent=2))


def run_c() -> None:
    """并行执行共同基线和两个阶段 C 候选，结束后统一汇总。"""
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
        raise ValueError("路线吃碰专长阶段 C 工作单元未全部完成")
    summarize_c()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-c"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else run_c()
