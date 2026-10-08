"""冻结并执行后继组合提案的完整开发阶段；根清单、费用和效果判据执行前确定。"""

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
from collections import Counter
from math import ceil
from statistics import mean, stdev

import followup_balance_checks as checks
import followup_balance_math as mathematics
import followup_research_stage as stage
import followup_quality_panel as parent

b, OUT, natural = checks.b, checks.OUT, parent.natural


def prepare():
    """冻结单份候选和132新桌；所有已见来源继续只用于开发筛选。"""
    assert not (OUT / "evaluation-plan.json").exists()
    assert b.read(OUT / "checks.json")["status"] == "PASS_OFFLINE_BEHAVIOR_ONLY"
    assert b.read(OUT / "math-checks.json")["status"] == "PASS_EXACT_RATIONAL_CHECK"
    parent_plan = b.read(parent.OUT / "evaluation-plan.json")
    parent.verify_inputs(parent_plan)
    checks.diagnosis.parent.guard.verify(b.read(OUT / "checks-plan.json")["runtime"])
    _, digest = checks.load_ranker()
    identity = {"ranking_sha256": digest,
        "wrapper_sha256": b.digest(b.Path(checks.wrapper.__file__).read_bytes()),
        "parent_sha256": b.read(parent.OUT / "manifest.json")["source_sha256"]}
    bound = [OUT / name for name in ("ranking.py", "proposal.md", "author-plan.json", "author-dispatch.json",
        "author-completion.json", "source-review.json", "checks-plan.json", "checks.json", "behavior-results.json", "math-checks.json")]
    bound += [parent.OUT / name for name in ("evaluation-plan.json", "effect-samples.json", "development-decision.json")]
    plan = {"schema": "followup-balance-effect/1", "created_at_utc": b.search.utc_now(),
        "candidate_id": "offline-followup-balance:" + parent._digest(identity), "identity": identity,
        "policy_id": "offline-followup-balance-v1:" + digest,
        "bound_files": {str(p): b.digest(p.read_bytes()) for p in bound},
        "runtime": parent.guard.capture(source_paths=[*b.HERE.glob("*.py"), OUT / "ranking.py"]),
        "contract": parent_plan["contract"], "contract_sha256": parent_plan["contract_sha256"],
        "rules_hash": parent_plan["rules_hash"], "panel_seed": 2026092001, "root_indices": list(range(1, 9)),
        "seats_per_root": 4, "candidate_tables": 128, "baseline_control_tables": 4,
        "max_new_full_tables": 132, "reused_baseline_tables": 128, "reused_parent_tables_for_comparison": 128,
        "max_process_seconds": 2400,
        "decision_rule": "完整132新桌及双臂对账、4基线控制桌复现；无事实/内部/成本回退及驱动错误，H/M各8根相对V2的mean_delta_low均>0才继续第二已见清单。父代差作为机制反馈，不替代V2门槛；性能片段独立报告，不据此否决研究价值。",
        "comparison_scope": "原核心已反复曝光；父代及V2原件复用并核验，根内4配置分别双臂同牌山，不冒充四座位共享牌山",
        "model_calls": 1, "repair_calls": 0, "confirmation_roots": 0, "release_eligible": False}
    b.write(OUT / "evaluation-plan.json", plan)
    auth = b.unified_document(batch_label="followup-balance", authorization_id="r10-followup-balance",
        accounts={"tables_full": 132}, issued_by="lead", issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth["issuance_basis"] = "用户持续进化及性能研究授权；单份Terra max提案，已见核心完整128候选桌和4V2控制桌"
    natural.require_authorization(auth)
    b.write(OUT / "evaluation-authorization.json", auth)
    print("frozen: 132 new tables; no confirmation", flush=True)


def verify_inputs(plan):
    """核对完整源码闭包及新旧产物摘要，拒绝中途改候选、判据或旧成绩。"""
    parent.guard.verify(plan["runtime"])
    parent.verify_inputs(b.read(parent.OUT / "evaluation-plan.json"))
    for name, digest in plan["bound_files"].items():
        assert b.digest(b.Path(name).read_bytes()) == digest, name
    assert b.digest(b.Path(plan["contract"]).read_bytes()) == plan["contract_sha256"]


def verify_result(raw, plans, contract, plan, arm):
    """核验真实策略装配与完整结果，并逐窗独立用有理数重算作者排序。"""
    verified = stage.verify_stage(raw, plans, contract, plan["rules_hash"], arm, plan["policy_id"])
    if arm == "candidate":
        for table in raw["tables"]:
            for row in table["prototype_audit"]:
                if row["status"] != "EVALUATED":
                    continue
                qualities = row["qualities"]
                ranking = row["ranking_rows"]
                context = row["ranking_context"]
                assert [r["action_key"] for r in ranking] == [q["action_key"] for q in qualities]
                assert 2 <= len(ranking) <= 14
                assert all(r["improvement_weighted_sum"] == q["improvement_weighted_sum"] for r, q in zip(ranking, qualities, strict=True))
                assert all(q["nonprogress_weight"] == context["nonprogress_weight"] for q in qualities)
                assert row["ranking_order"] == mathematics.expected_order(ranking, context)
                assert row["selected_first"] == row["ranking_order"][0]
                assert row["base_first"] == ranking[0]["action_key"]
                assert row["parent_selected_first"] == sorted(qualities, key=lambda q: -q["improvement_weighted_sum"])[0]["action_key"]
                assert row["parent_changed"] == (row["parent_selected_first"] != row["base_first"])
    return verified


def run():
    """先组合控制再执行全部根；已落盘完整阶段可恢复，半途阶段不盲目重跑。"""
    plan = b.read(OUT / "evaluation-plan.json")
    verify_inputs(plan)
    ranker, digest = checks.load_ranker()
    contract = b.read(b.Path(plan["contract"]))
    auth = b.read(OUT / "evaluation-authorization.json")
    natural.require_authorization(auth)
    ledger = b.search.ActionValueLedger.load(OUT / "evaluation-ledger.json", authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    previous = {(s["opponent_mix"], s["root_index"], s["focal_anchor_seat"]): s for s in b.read(parent.OUT / "effect-samples.json")}
    assert len(previous) == 64
    def execute(mix, root, seat, arm):
        verify_inputs(plan)
        plans = natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=root, focal_seat=seat, panel_seed=plan["panel_seed"])
        label = f"{mix}-root{root}-seat{seat}-{arm}"
        expected = {"step_id": label, "planned_tables": 2, "manifest_digest": parent._digest(plan),
            "plans_digest": parent._digest([p.to_json() for p in plans]), "arm": arm, "candidate_id": plan["candidate_id"]}
        folder = OUT / "arms" / label
        parent.execute_arm(folder, expected=expected, ledger=ledger,
            runner=lambda: stage.run_stage(plans, mix, arm, contract,
                lambda config: checks.wrapper.BalancedFollowupPolicy(config, lambda: 800., ranker, digest)),
            verifier=lambda raw: verify_result(raw, plans, contract, plan, arm))
        return b.read(folder / "result.json")["raw"]
    for mix in ("H", "M"):
        actual = execute(mix, 1, 0, "baseline")
        parent.terminal_equal(actual, previous[(mix, 1, 0)]["raw_arms"]["baseline"])
    b.write(OUT / "baseline-control.json", {"status": "PASS", "new_tables": 4, "terminals_reproduced": 4, "reuse_allowed": True})
    samples = []
    for mix in ("H", "M"):
        for root in plan["root_indices"]:
            for seat in range(4):
                old = previous[(mix, root, seat)]
                plans = natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=root, focal_seat=seat, panel_seed=plan["panel_seed"])
                baseline = old["raw_arms"]["baseline"]
                verify_result(baseline, plans, contract, plan, "baseline")
                result = execute(mix, root, seat, "candidate")
                slim = {k: result[k] for k in ("status", "usable", "error", "focal_stage_score", "stage_totals_by_participant", "u", "u_low", "u_high", "unresolved", "elapsed_ms")}
                slim.update({"candidate_id": plan["candidate_id"], "policy_id": plan["policy_id"]})
                samples.append({**old, "candidate_id": plan["candidate_id"],
                    "arms": {"baseline": old["arms"]["baseline"], "candidate": slim},
                    "raw_arms": {"baseline": baseline, "candidate": result},
                    "cost": {"new_candidate_tables": 2, "reused_baseline_tables": 2},
                    "selection_scope": "offline_balance_development_only"})
            print(mix, "root", root, "complete; new tables", ledger.spent("tables_full"), flush=True)
    verify_inputs(plan)
    assert ledger.spent("tables_full") == 132 and len(samples) == 64
    statistics = natural.paired_stage_statistics(samples, min_roots=8)
    assert statistics["invalid_count"] == 0 and statistics["uncomputable_count"] == 0
    b.write(OUT / "effect-samples.json", samples)
    b.write(OUT / "effect-statistics.json", statistics)
    print("complete; requires read-only closing audit", flush=True)


def close():
    """独立复算分层根均值和识别界；按预登记裁定，不冒充发布显著性。"""
    plan = b.read(OUT / "evaluation-plan.json")
    verify_inputs(plan)
    process = b.read(OUT / "effect-process.json")
    assert process["returncode"] == 0 and not process["timed_out"] and not process["group_still_alive"]
    assert not (OUT / "development-decision.json").exists()
    samples = b.read(OUT / "effect-samples.json")
    previous = {(s["opponent_mix"], s["root_index"], s["focal_anchor_seat"]): s for s in b.read(parent.OUT / "effect-samples.json")}
    expected = {(mix, root, seat) for mix in ("H", "M") for root in range(1, 9) for seat in range(4)}
    assert len(samples) == 64 and {(s["opponent_mix"], s["root_index"], s["focal_anchor_seat"]) for s in samples} == expected
    contract = b.read(b.Path(plan["contract"]))
    runtime, rows = Counter(), []
    for sample in samples:
        mix, root, seat = sample["opponent_mix"], sample["root_index"], sample["focal_anchor_seat"]
        old = previous[(mix, root, seat)]
        plans = natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=root, focal_seat=seat, panel_seed=plan["panel_seed"])
        assert sample["candidate_id"] == plan["candidate_id"] and sample["root_content_digest"] == old["root_content_digest"]
        assert sample["table_ids"] == [p.table_id for p in plans] and sample["table_seeds"] == [p.seed for p in plans]
        assert sample["raw_arms"]["baseline"] == old["raw_arms"]["baseline"]
        for arm in ("baseline", "candidate"):
            raw = sample["raw_arms"][arm]
            verified = verify_result(raw, plans, contract, plan, arm)
            assert all(raw[k] == sample["arms"][arm][k] for k in ("u", "u_low", "u_high", "status", "usable", "error", "focal_stage_score", "stage_totals_by_participant"))
            if arm == "candidate":
                runtime.update(verified["runtime_counts"])
                rows.extend(r for t in raw["tables"] for r in t["prototype_audit"])
    statistics = natural.paired_stage_statistics(samples, min_roots=8)
    assert statistics == b.read(OUT / "effect-statistics.json")
    block = statistics["by_candidate"][plan["candidate_id"]]["panels"]["normal"]
    comparisons = {}
    for reference_arm, label in (("baseline", "versus_v2"), ("candidate", "versus_parent")):
        comparisons[label] = {}
        for mix in ("H", "M"):
            low, high = [], []
            for root in range(1, 9):
                group = [s for s in samples if s["opponent_mix"] == mix and s["root_index"] == root]
                assert len(group) == 4
                refs = [previous[(mix, root, s["focal_anchor_seat"])]["raw_arms"][reference_arm] for s in group]
                low.append(mean(s["arms"]["candidate"]["u_low"] - ref["u_high"] for s, ref in zip(group, refs, strict=True)))
                high.append(mean(s["arms"]["candidate"]["u_high"] - ref["u_low"] for s, ref in zip(group, refs, strict=True)))
            midpoint = [(a + z) / 2 for a, z in zip(low, high, strict=True)]
            se = stdev(midpoint) / (8 ** .5)
            comparisons[label][mix] = {"mean_delta": mean(midpoint), "mean_delta_low": mean(low), "mean_delta_high": mean(high),
                "root_deltas_low": low, "root_deltas_high": high, "standard_error": se,
                "sampling_interval_95_normal_approx": [mean(midpoint) - 1.96 * se, mean(midpoint) + 1.96 * se]}
            if label == "versus_v2":
                official = block["panels"][mix]
                assert official["status"] == "ok" and official["manifest_complete"] and official["n_roots"] == 8
                assert mean(low) == official["delta_bounds"]["mean_delta_low"] and mean(high) == official["delta_bounds"]["mean_delta_high"]
                assert abs(stdev(low) / (8 ** .5) - official["delta_bounds"]["standard_error_low"]) < 1e-12
    statuses = Counter(r["status"] for r in rows)
    clean = not any(statuses[k] for k in ("ERROR_FALLBACK", "FACT_FALLBACK", "COST_FALLBACK"))
    reliable = not any(runtime[k] for k in ("illegal_choices", "fallbacks", "timeouts", "audit_missing", "auto_actions"))
    positive = all(v["mean_delta_low"] > 0 for v in comparisons["versus_v2"].values())
    measured = [r for r in rows if r["status"] == "EVALUATED"]
    timing = {}
    for field in ("elapsed_seconds", "ranking_elapsed_seconds"):
        values = sorted(r[field] for r in measured)
        timing[field] = {**{name: values[max(0, ceil(q * len(values)) - 1)] if values else None
            for name, q in (("p50", .5), ("p95", .95), ("p99", .99))}, "max": max(values, default=None), "total": sum(values)}
    auth = b.read(OUT / "evaluation-authorization.json")
    ledger = b.search.ActionValueLedger.load(OUT / "evaluation-ledger.json", authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    assert ledger.spent("tables_full") == 132
    assert b.read(OUT / "baseline-control.json")["status"] == "PASS"
    decision = {"status": "CONTINUE_SECOND_SEEN_DEVELOPMENT" if positive and clean and reliable else "NOT_PROMOTED_AFTER_CORE",
        "candidate_id": plan["candidate_id"], **comparisons, "declared_mix": block["declared_mix"],
        "effect_condition_passed": positive, "clean_prototype_execution": clean, "driver_reliable_in_logical_time": reliable,
        "continue_second_seen_panel": positive and clean and reliable,
        "prototype_decisions": len(rows), "prototype_statuses": dict(statuses),
        "first_changes_from_v2": sum(r["changed"] for r in rows),
        "first_changes_from_parent_on_candidate_trajectory": sum(r["selected_first"] != r["parent_selected_first"] for r in rows),
        "rule_calls": sum(r["rule_calls"] for r in rows), "timing_seconds": timing, "runtime_counts": dict(runtime),
        "performance_interpretation": "两个计时段为研究增强与纯排序片段，不含额外V2调用和生产全链；模拟逻辑时钟不证明真实窗口或并发性能",
        "interpretation": "识别界与抽样区间分开；已反复曝光核心、每层8根，不能声明发布显著性。父代对照沿各自完整轨迹，逐窗父代比较仅为当前候选轨迹旁路。",
        "new_full_tables": 132, "reused_baseline_tables": 128, "reused_parent_tables": 128,
        "spent": ledger.account_summary(), "model_calls": 1, "repair_calls": 0,
        "confirmation_roots": 0, "release_eligible": False}
    b.write(OUT / "development-decision.json", decision)
    print({k: decision[k] for k in ("status", "versus_v2", "versus_parent", "prototype_statuses", "first_changes_from_v2")}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "close"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "close": close}[args.operation]()
