"""R10 路线吃碰专长全新随机来源复核：候选与稳定 V2 的完整阶段配对。"""
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
import cross_specialist_panel_c as development  # noqa: E402
import cross_specialist_policy as policy  # noqa: E402
import followup_research_stage as research  # noqa: E402
import sitin_archive as archive  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
from confirmation_execution_probe import execute_arm  # noqa: E402


BATCH = phase_a.BATCH
OUT = BATCH / "new-source"
DEV_OUT = development.OUT
DEV_MANIFEST = DEV_OUT / "manifest.json"
DEV_RANKING = DEV_OUT / "phase-c-ranking.json"
DEV_CONCLUSION = DEV_OUT / "development-conclusion.json"
CONTRACT = phase_a.CONTRACT
ROUTE_SOURCE = phase_a.ROUTE_SOURCE
PANEL_SEED = 2026092203
ROOTS = tuple(range(1, 65))
MIXES = phase_a.MIXES
SEATS = phase_a.SEATS
MODE = "route_claim_only"
BASELINE_ID = phase_a.BASELINE_ID
CANDIDATE_ID = phase_a.identity_for(MODE)
MAX_TABLES = 2048


def digest(path: Path) -> str:
    """计算冻结输入摘要。"""
    return phase_a.digest(path)


def source_paths() -> list[Path]:
    """列出全新来源复核恢复时必须相同的代码与开发裁定。"""
    return [
        Path(__file__),
        Path(phase_a.__file__),
        Path(development.__file__),
        Path(policy.__file__),
        Path(research.__file__),
        Path(archive.__file__),
        Path(wiring.__file__),
        DEV_MANIFEST,
        DEV_RANKING,
        DEV_CONCLUSION,
        CONTRACT,
        ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结全新 panel_seed、2,048 桌上限和复核通过条件。"""
    if OUT.exists():
        raise SystemExit("路线吃碰专长全新来源复核已存在；拒绝覆盖")
    if any(
        str(PANEL_SEED) in path.read_text(encoding="utf-8", errors="ignore")
        for path in HERE.glob("**/*.json")
    ):
        raise ValueError("全新来源 panel_seed 已出现在既有证据 JSON")
    dev_plan = batch.read(DEV_MANIFEST)
    development.verify_inputs(dev_plan)
    conclusion = batch.read(DEV_CONCLUSION)
    if (
        conclusion["disposition"] != "RETAIN_ROUTE_CLAIM_FOR_NEW_SOURCE_REVIEW"
        or not conclusion["route_claim_positive_and_beats_parent"]
    ):
        raise ValueError("开发裁定未授权路线吃碰专长进入全新来源复核")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-route-claim-new-source",
        authorization_id="r10-route-claim-new-source-20260921",
        accounts={"tables_full": MAX_TABLES},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "路线吃碰专长通过累计28根开发选留；按冻结方案使用全新panel_seed复核",
        "scope": "全新来源开发复核；候选与V2在H/M各64根、4座位、每阶段2桌配对；不消耗正式确认账户，不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    research.natural.require_authorization(authorization)
    batch.write(OUT / "authorization.json", authorization)
    runtime = guard.capture(source_paths=source_paths() + [OUT / "authorization.json"])
    manifest = {
        "schema": "r10-route-claim-new-source/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "development_manifest": str(DEV_MANIFEST),
        "development_manifest_sha256": digest(DEV_MANIFEST),
        "development_ranking": str(DEV_RANKING),
        "development_ranking_sha256": digest(DEV_RANKING),
        "development_conclusion": str(DEV_CONCLUSION),
        "development_conclusion_sha256": digest(DEV_CONCLUSION),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "route_source": str(ROUTE_SOURCE),
        "route_source_sha256": digest(ROUTE_SOURCE),
        "rules_hash": research.natural.compute_rules_hash(research.natural.REPO),
        "candidate": {
            "mode": MODE,
            "candidate_id": CANDIDATE_ID,
            "source": str(Path(policy.__file__)),
            "source_sha256": digest(Path(policy.__file__)),
        },
        "panel_seed": PANEL_SEED,
        "opponents": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "tables_per_arm": 2,
        "baseline_policy_id": BASELINE_ID,
        "baseline_tables": 1024,
        "candidate_tables": 1024,
        "max_full_tables": MAX_TABLES,
        "workers": 2,
        "decision": {
            "fitness": "本批全新来源 H/M 等权根级保守差 d_low 均值",
            "retain_for_independent_confirmation": (
                "fitness_mean_delta_low>0、mean_delta>0、至少一个H/M面板95%区间下界>0、"
                "另一个面板95%区间上界>0，且逐决策审计无事实/成本/执行回退。"
            ),
            "otherwise": "关闭候选，回顾参考文献并重构父代或信用分配；不使用本批调参。",
            "meaning": "全新随机来源鲁棒性复核，不是正式独立确认、显著性或发布门禁。",
            "no_parameter_tuning": True,
        },
        "model_calls": 0,
        "confirmation_roots": 0,
        "formal_alpha_spent": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(OUT / "manifest.json", manifest)
    batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": MAX_TABLES}
    ).save()
    print(json.dumps({
        "status": "PREPARED_ROUTE_CLAIM_NEW_SOURCE",
        "panel_seed": PANEL_SEED,
        "roots_per_mix": len(ROOTS),
        "baseline_tables": 1024,
        "candidate_tables": 1024,
        "max_full_tables": MAX_TABLES,
    }, ensure_ascii=False))


def verify_inputs(plan: dict) -> None:
    """执行前后核对开发裁定、候选源码、合同和全新来源身份。"""
    guard.verify(plan["runtime"])
    for path_key, sha_key in (
        ("development_manifest", "development_manifest_sha256"),
        ("development_ranking", "development_ranking_sha256"),
        ("development_conclusion", "development_conclusion_sha256"),
        ("contract", "contract_sha256"),
        ("route_source", "route_source_sha256"),
    ):
        if digest(Path(plan[path_key])) != plan[sha_key]:
            raise ValueError(path_key + " 摘要漂移")
    candidate = plan["candidate"]
    if (
        candidate["mode"] != MODE
        or candidate["candidate_id"] != CANDIDATE_ID
        or digest(Path(candidate["source"])) != candidate["source_sha256"]
    ):
        raise ValueError("路线吃碰候选身份漂移")
    development.verify_inputs(batch.read(DEV_MANIFEST))


def plans_for(contract: dict, mix: str, root: int, seat: int, plan: dict):
    """从全新 panel_seed 构造同牌山换座位阶段。"""
    return research.natural.build_seat_stage_plans(
        contract=contract,
        opponent=mix,
        root_index=root,
        focal_seat=seat,
        panel_seed=plan["panel_seed"],
    )


def run_arm(arm: str) -> dict:
    """执行一个完整臂；基线与候选分别由独立工作进程串行推进。"""
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    contract = batch.read(CONTRACT)
    ledger = batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": MAX_TABLES}
    )
    route_source = ROUTE_SOURCE.read_text(encoding="utf-8")
    factory = phase_a.policy_factory(MODE, route_source, digest(ROUTE_SOURCE)[:16])
    count = 0
    for mix in MIXES:
        for root in ROOTS:
            for seat in SEATS:
                plans = plans_for(contract, mix, root, seat, plan)
                label = f"ns-{arm}-{mix}-r{root:02d}-s{seat}"
                identity = BASELINE_ID if arm == "baseline" else CANDIDATE_ID
                expected = {
                    "step_id": label,
                    "planned_tables": 2,
                    "manifest_digest": wiring._digest(plan),
                    "plans_digest": wiring._digest([item.to_json() for item in plans]),
                    "arm": arm,
                    "candidate_id": identity,
                }
                checked = execute_arm(
                    OUT / arm / label,
                    expected=expected,
                    ledger=ledger,
                    runner=lambda plans=plans, mix=mix, arm=arm: research.run_stage(
                        plans,
                        mix,
                        arm,
                        contract,
                        factory if arm == "candidate" else (lambda _config: None),
                    ),
                    verifier=lambda raw, plans=plans, arm=arm, identity=identity: research.verify_stage(
                        raw, plans, contract, plan["rules_hash"], arm, identity
                    ),
                )
                count += checked["tables"]
    verify_inputs(plan)
    return {"arm": arm, "tables": count}


def root_digest(plan: dict, mix: str, root: int, contract: dict) -> str:
    """冻结全新来源一个根的四座位和两桌种子集合。"""
    seats = {}
    for seat in SEATS:
        plans = plans_for(contract, mix, root, seat, plan)
        seats[str(seat)] = {
            "table_ids": [item.table_id for item in plans],
            "table_seeds": [item.seed for item in plans],
        }
    return wiring._digest({
        "generator": "r10-route-claim-new-source/1",
        "panel_seed": plan["panel_seed"],
        "opponent_mix": mix,
        "root_index": root,
        "seats": seats,
    })


def audit_summary() -> dict:
    """汇总全新来源候选的行为变化、回退与运行成本。"""
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
                label = f"ns-candidate-{mix}-r{root:02d}-s{seat}"
                raw = batch.read(OUT / "candidate" / label / "result.json")["raw"]
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


def summarize() -> None:
    """只用本批全新来源复算统计并裁定是否进入独立确认。"""
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    ledger = batch.search.ActionValueLedger.load(
        OUT / "ledger.json", authorized_budgets={"tables_full": MAX_TABLES}
    )
    if ledger.spent("tables_full") != MAX_TABLES:
        raise ValueError("全新来源复核费用未完整结算")
    contract = batch.read(CONTRACT)
    samples = []
    for mix in MIXES:
        for root in ROOTS:
            root_id = f"r10rcns-{mix}-{plan['panel_seed']}-root{root:02d}"
            content = root_digest(plan, mix, root, contract)
            for seat in SEATS:
                baseline_label = f"ns-baseline-{mix}-r{root:02d}-s{seat}"
                candidate_label = f"ns-candidate-{mix}-r{root:02d}-s{seat}"
                baseline = batch.read(OUT / "baseline" / baseline_label / "result.json")["raw"]
                candidate = batch.read(OUT / "candidate" / candidate_label / "result.json")["raw"]
                samples.append({
                    "schema": research.natural.NATURAL_SAMPLE_SCHEMA,
                    "source_root_id": root_id,
                    "root_content_digest": content,
                    "root_index": root,
                    "root_usage": "new_source_robustness_review",
                    "candidate_id": CANDIDATE_ID,
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
                        "candidate": phase_a.arm_view(candidate, CANDIDATE_ID),
                    },
                    "completeness": "complete",
                    "invalid_reasons": [],
                    "cost": {
                        "budget_units": 4,
                        "elapsed_ms": baseline["elapsed_ms"] + candidate["elapsed_ms"],
                    },
                })
    statistics = archive.paired_stage_statistics(samples, min_roots=64)
    if statistics["invalid_count"] or statistics["uncomputable_count"]:
        raise ValueError("全新来源复核存在无效样本")
    normal = statistics["by_candidate"][CANDIDATE_ID]["panels"]["normal"]
    panels = normal["panels"]
    if set(panels) != set(MIXES) or any(
        panel["status"] != "ok" or not panel["manifest_complete"]
        for panel in panels.values()
    ):
        raise ValueError("全新来源根清单不完整")
    audit = audit_summary()
    lower_positive = any(panels[mix]["interval_95"][0] > 0.0 for mix in MIXES)
    other_not_clear_negative = all(panels[mix]["interval_95"][1] > 0.0 for mix in MIXES)
    retain = (
        normal["declared_mix"]["mean_delta_low"] > 0.0
        and normal["declared_mix"]["mean_delta"] > 0.0
        and lower_positive
        and other_not_clear_negative
        and not audit["has_fallback"]
    )
    disposition = (
        "FREEZE_FOR_INDEPENDENT_CONFIRMATION"
        if retain else
        "CLOSE_ROUTE_CLAIM_AND_REVIEW_LITERATURE"
    )
    result = {
        "schema": "r10-route-claim-new-source-result/1",
        "candidate_id": CANDIDATE_ID,
        "panel_seed": PANEL_SEED,
        "roots_per_mix": len(ROOTS),
        "fitness_mean_delta_low": normal["declared_mix"]["mean_delta_low"],
        "mean_delta": normal["declared_mix"]["mean_delta"],
        "mean_delta_high": normal["declared_mix"]["mean_delta_high"],
        "H": {key: panels["H"][key] for key in (
            "n_roots", "mean_delta", "standard_error", "interval_95"
        )},
        "M": {key: panels["M"][key] for key in (
            "n_roots", "mean_delta", "standard_error", "interval_95"
        )},
        "audit": audit,
        "lower_positive_in_at_least_one_mix": lower_positive,
        "all_mixes_not_clearly_negative": other_not_clear_negative,
        "retain_for_independent_confirmation": retain,
        "decision_rule": plan["decision"],
        "disposition": disposition,
        "strength_claim": False,
        "confirmation_eligible": retain,
        "release_eligible": False,
    }
    batch.write(OUT / "samples.json", samples)
    batch.write(OUT / "statistics.json", statistics)
    batch.write(OUT / "result.json", result)
    batch.write(OUT / "summary.json", {
        "status": "COMPLETE_ROUTE_CLAIM_NEW_SOURCE_REVIEW",
        **result,
        "full_tables": MAX_TABLES,
        "baseline_tables": 1024,
        "candidate_tables": 1024,
        "spent": ledger.account_summary(),
        "model_calls": 0,
        "confirmation_roots": 0,
        "formal_alpha_spent": 0,
    })
    print(json.dumps({
        "status": "COMPLETE_ROUTE_CLAIM_NEW_SOURCE_REVIEW",
        "fitness": result["fitness_mean_delta_low"],
        "mean": result["mean_delta"],
        "H": result["H"],
        "M": result["M"],
        "retain": retain,
        "disposition": disposition,
    }, ensure_ascii=False, indent=2))


def run() -> None:
    """并行执行候选与基线两个臂，全部完成后统一复算。"""
    plan = batch.read(OUT / "manifest.json")
    verify_inputs(plan)
    context = multiprocessing.get_context("spawn")
    completed = []
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=plan["workers"], mp_context=context
    ) as pool:
        futures = [pool.submit(run_arm, arm) for arm in ("baseline", "candidate")]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            completed.append(result)
            print(result["arm"], "complete", result["tables"], "tables", flush=True)
    if len(completed) != 2:
        raise ValueError("全新来源候选与基线工作单元未全部完成")
    summarize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else run()
