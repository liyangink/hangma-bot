"""有界后继信用原源码的第二已见开发清单；复用核验过的V2臂，不新增作者。"""

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

import followup_balance_panel as core
import selfdraw_tempo_second_panel as old_run

b, natural = core.b, core.natural
OUT = b.HERE / "followup-balance-second-dev-20260920"
REFERENCE = old_run.OUT


def load_references():
    """只提取旧基线用于效果比较；旧候选不充当本机制父代。"""
    return {(mix, s["root_index"], s["focal_anchor_seat"]): s
        for mix in ("H", "M") for s in b.read(REFERENCE / ("natural-" + mix) / "panel.json")["samples"]}


def verify_baseline_policy_ids(raw, plans, contract, mix):
    """核对全部座位的实际策略身份，基线不能只靠arm标签宣称为V2。"""
    for table, plan in zip(raw["tables"], plans, strict=True):
        logical = natural.arm_logical_policies(arm="baseline", candidate_scorer=None,
            logical_participants=plan.logical_participants,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"], monotonic=lambda: 800.)
        policies = natural.seat_policies_from(logical, plan.permutation, plan.logical_participants)
        identities = [str(getattr(p, "policy_id", type(p).__name__)) for p in policies]
        assert table["policy_execution"]["policy_ids_by_seat"] == identities
        for seat, identity in enumerate(identities):
            assert table["result"]["versions"]["natural_seat_policy:" + str(seat)] == identity


def prepare():
    """花费前核验核心继续资格、全部旧面板、来源与基线身份，再冻结132新桌。"""
    assert not OUT.exists()
    first = b.read(core.OUT / "evaluation-plan.json")
    core.verify_inputs(first)
    decision = b.read(core.OUT / "development-decision.json")
    assert decision["continue_second_seen_panel"] is True and decision["candidate_id"] == first["candidate_id"]
    old_plan = b.read(REFERENCE / "manifest.json")
    old_run.verify(old_plan)
    assert old_plan["panel_seed"] == 2026092097 and old_plan["roots"] == list(range(1, 9))
    assert old_plan["rules_hash"] == first["rules_hash"] and old_plan["contract_sha256"] == first["contract_sha256"]
    contract = b.read(b.Path(first["contract"]))
    checks = {}
    for mix in ("H", "M"):
        panel = b.read(REFERENCE / ("natural-" + mix) / "panel.json")
        assert panel["identity"]["panel_seed"] == old_plan["panel_seed"]
        assert panel["identity"]["candidate_source_sha256"] == old_plan["source"]["sha256"]
        checked = old_run.verify_full_panel(panel, contract, expected_identity=panel["identity"],
            expected_root_indices=old_plan["roots"], expected_rules_hash=first["rules_hash"])
        assert checked["full_results_verified"] == 128
        checks[mix] = {"full_results_verified": 128, "verification_digest": core.parent._digest(checked)}
        for sample in panel["samples"]:
            plans = natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=sample["root_index"],
                focal_seat=sample["focal_anchor_seat"], panel_seed=old_plan["panel_seed"])
            core.verify_result(sample["raw_arms"]["baseline"], plans, contract, first, "baseline")
            verify_baseline_policy_ids(sample["raw_arms"]["baseline"], plans, contract, mix)
    bound = [core.OUT / name for name in ("evaluation-plan.json", "development-decision.json", "effect-process.json", "NEXT-STAGE-PLAN.md")]
    bound += [REFERENCE / name for name in ("manifest.json", "summary.json", "local-artifacts.json", "natural-H/panel.json", "natural-M/panel.json")]
    plan = {"schema": "followup-balance-second-seen/1", "created_at_utc": b.search.utc_now(),
        "candidate_id": first["candidate_id"], "identity": first["identity"], "policy_id": first["policy_id"],
        "bound_files": {str(p): b.digest(p.read_bytes()) for p in bound},
        "runtime": core.parent.guard.capture(source_paths=[*b.HERE.glob("*.py"), core.OUT / "ranking.py"]),
        "contract": first["contract"], "contract_sha256": first["contract_sha256"], "rules_hash": first["rules_hash"],
        "panel_seed": 2026092097, "root_indices": list(range(1, 9)), "seats_per_root": 4,
        "candidate_tables": 128, "baseline_control_tables": 4, "max_new_full_tables": 132,
        "reused_baseline_tables": 128, "reused_parent_tables": 0, "max_process_seconds": 2400,
        "decision_rule": "第二清单相对V2的H/M根均值下识别界分别>0，等权下界>0，且完整对账与执行通过才允许未见开发；不合并两清单覆盖失败。仅性能/成本问题且效果正时单列研究复审，不抹去机制价值。",
        "scope": "已曝光第二清单；各配置双臂同牌山，四座位配置使用不同桌种子；不是独立确认",
        "prior_goal_turn_classification": "progress: 新提案91请求验收及132新桌完整结案，改变下一行动为第二清单",
        "model_calls": 0, "confirmation_roots": 0, "formal_alpha_spent": 0, "release_eligible": False}
    OUT.mkdir()
    b.write(OUT / "evaluation-plan.json", plan)
    b.write(OUT / "reference-verification.json", {"status": "PASS_FULL_REFERENCE_REVIEW", "old_panels": checks,
        "reusable_baseline_tables": 128, "all_baseline_policy_ids_verified": True,
        "new_tables": 0, "model_calls": 0, "confirmation_roots": 0})
    auth = b.unified_document(batch_label="followup-balance-second-dev", authorization_id="r10-followup-balance-second-dev",
        accounts={"tables_full": 132}, issued_by="lead", issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth["issuance_basis"] = "用户持续演化授权与核心通过后的既定方案；同源码132新桌及128V2旧桌复用，0作者和正式确认"
    natural.require_authorization(auth)
    b.write(OUT / "evaluation-authorization.json", auth)
    verify_inputs(plan)
    print("second seen frozen: 132 new tables; all 128 reused V2 tables verified", flush=True)


def verify_inputs(plan):
    """恢复及每个阶段前核对来源、候选和源码闭包，防止借旧继续状态绕过第二结果。"""
    core.parent.guard.verify(plan["runtime"])
    core.verify_inputs(b.read(core.OUT / "evaluation-plan.json"))
    old_run.verify(b.read(REFERENCE / "manifest.json"))
    for name, digest in plan["bound_files"].items():
        assert b.digest(b.Path(name).read_bytes()) == digest, name
    assert b.digest(b.Path(plan["contract"]).read_bytes()) == plan["contract_sha256"]


def run():
    """先4控制桌，再顺序执行冻结的128候选桌；沿用整阶段事务恢复。"""
    plan = b.read(OUT / "evaluation-plan.json")
    verify_inputs(plan)
    ranker, digest = core.checks.load_ranker()
    contract = b.read(b.Path(plan["contract"]))
    auth = b.read(OUT / "evaluation-authorization.json")
    natural.require_authorization(auth)
    ledger = b.search.ActionValueLedger.load(OUT / "evaluation-ledger.json", authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    previous = load_references()
    assert len(previous) == 64
    def execute(mix, root, seat, arm):
        verify_inputs(plan)
        plans = natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=root, focal_seat=seat, panel_seed=plan["panel_seed"])
        label = f"{mix}-root{root}-seat{seat}-{arm}"
        expected = {"step_id": label, "planned_tables": 2, "manifest_digest": core.parent._digest(plan),
            "plans_digest": core.parent._digest([p.to_json() for p in plans]), "arm": arm, "candidate_id": plan["candidate_id"]}
        folder = OUT / "arms" / label
        core.parent.execute_arm(folder, expected=expected, ledger=ledger,
            runner=lambda: core.stage.run_stage(plans, mix, arm, contract,
                lambda config: core.checks.wrapper.BalancedFollowupPolicy(config, lambda: 800., ranker, digest)),
            verifier=lambda raw: core.verify_result(raw, plans, contract, plan, arm))
        return b.read(folder / "result.json")["raw"]
    for mix in ("H", "M"):
        actual = execute(mix, 1, 0, "baseline")
        plans = natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=1, focal_seat=0, panel_seed=plan["panel_seed"])
        verify_baseline_policy_ids(actual, plans, contract, mix)
        core.parent.terminal_equal(actual, previous[(mix, 1, 0)]["raw_arms"]["baseline"])
    b.write(OUT / "baseline-control.json", {"status": "PASS", "new_tables": 4, "terminals_reproduced": 4, "reuse_allowed": True})
    samples = []
    for mix in ("H", "M"):
        for root in plan["root_indices"]:
            for seat in range(4):
                old = previous[(mix, root, seat)]
                result = execute(mix, root, seat, "candidate")
                slim = {k: result[k] for k in ("status", "usable", "error", "focal_stage_score", "stage_totals_by_participant", "u", "u_low", "u_high", "unresolved", "elapsed_ms")}
                slim.update({"candidate_id": plan["candidate_id"], "policy_id": plan["policy_id"]})
                samples.append({**old, "candidate_id": plan["candidate_id"],
                    "arms": {"baseline": old["arms"]["baseline"], "candidate": slim},
                    "raw_arms": {"baseline": old["raw_arms"]["baseline"], "candidate": result},
                    "cost": {"new_candidate_tables": 2, "reused_baseline_tables": 2},
                    "selection_scope": "offline_balance_second_seen_development_only"})
            print(mix, "root", root, "complete; new tables", ledger.spent("tables_full"), flush=True)
    verify_inputs(plan)
    assert ledger.spent("tables_full") == 132 and len(samples) == 64
    stats = natural.paired_stage_statistics(samples, min_roots=8)
    assert stats["invalid_count"] == 0 and stats["uncomputable_count"] == 0
    b.write(OUT / "effect-samples.json", samples)
    b.write(OUT / "effect-statistics.json", stats)
    print("second seen complete; closing audit required", flush=True)


def close():
    """复算完整清单与分层统计，费用核销后明确签发或拒绝未见开发。"""
    plan = b.read(OUT / "evaluation-plan.json")
    verify_inputs(plan)
    process = b.read(OUT / "effect-process.json")
    assert process["returncode"] == 0 and not process["timed_out"] and not process["group_still_alive"]
    assert not (OUT / "development-decision.json").exists()
    previous = load_references()
    samples = b.read(OUT / "effect-samples.json")
    assert len(samples) == 64 and {(s["opponent_mix"], s["root_index"], s["focal_anchor_seat"]) for s in samples} == set(previous)
    contract = b.read(b.Path(plan["contract"]))
    rows, runtime = [], Counter()
    for sample in samples:
        mix, root, seat = sample["opponent_mix"], sample["root_index"], sample["focal_anchor_seat"]
        old = previous[(mix, root, seat)]
        plans = natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=root, focal_seat=seat, panel_seed=plan["panel_seed"])
        assert sample["candidate_id"] == plan["candidate_id"] and sample["root_content_digest"] == old["root_content_digest"]
        assert sample["table_ids"] == [p.table_id for p in plans] and sample["table_seeds"] == [p.seed for p in plans]
        assert sample["raw_arms"]["baseline"] == old["raw_arms"]["baseline"]
        verify_baseline_policy_ids(sample["raw_arms"]["baseline"], plans, contract, mix)
        for arm in ("baseline", "candidate"):
            raw = sample["raw_arms"][arm]
            check = core.verify_result(raw, plans, contract, plan, arm)
            assert all(raw[k] == sample["arms"][arm][k] for k in ("u", "u_low", "u_high", "status", "usable", "error", "focal_stage_score", "stage_totals_by_participant"))
            if arm == "candidate":
                rows.extend(r for table in raw["tables"] for r in table["prototype_audit"])
                runtime.update(check["runtime_counts"])
    stats = natural.paired_stage_statistics(samples, min_roots=8)
    assert stats == b.read(OUT / "effect-statistics.json")
    block = stats["by_candidate"][plan["candidate_id"]]["panels"]["normal"]
    measures = {}
    for mix in ("H", "M"):
        low, high = [], []
        for root in range(1, 9):
            group = [s for s in samples if s["opponent_mix"] == mix and s["root_index"] == root]
            assert len(group) == 4
            low.append(mean(s["arms"]["candidate"]["u_low"] - s["arms"]["baseline"]["u_high"] for s in group))
            high.append(mean(s["arms"]["candidate"]["u_high"] - s["arms"]["baseline"]["u_low"] for s in group))
        midpoint = [(a + z) / 2 for a, z in zip(low, high, strict=True)]
        se = stdev(midpoint) / (8 ** .5)
        official = block["panels"][mix]
        assert official["status"] == "ok" and official["manifest_complete"] and official["n_roots"] == 8
        assert mean(midpoint) == official["mean_delta"]
        assert mean(low) == official["delta_bounds"]["mean_delta_low"] and mean(high) == official["delta_bounds"]["mean_delta_high"]
        assert abs(stdev(low) / (8 ** .5) - official["delta_bounds"]["standard_error_low"]) < 1e-12
        measures[mix] = {"mean_delta": mean(midpoint), "mean_delta_low": mean(low), "mean_delta_high": mean(high),
            "root_deltas_low": low, "root_deltas_high": high, "standard_error": se,
            "sampling_interval_95_normal_approx": [mean(midpoint) - 1.96 * se, mean(midpoint) + 1.96 * se]}
    statuses = Counter(r["status"] for r in rows)
    positive = all(m["mean_delta_low"] > 0 for m in measures.values()) and block["declared_mix"]["mean_delta_low"] > 0
    clean = not any(statuses[k] for k in ("FACT_FALLBACK", "COST_FALLBACK", "ERROR_FALLBACK"))
    reliable = not any(runtime[k] for k in ("illegal_choices", "fallbacks", "timeouts", "audit_missing", "auto_actions"))
    auth = b.read(OUT / "evaluation-authorization.json")
    ledger = b.search.ActionValueLedger.load(OUT / "evaluation-ledger.json", authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    assert ledger.spent("tables_full") == 132 and not any(r["status"] == "reserved" for r in b.read(OUT / "evaluation-ledger.json")["reservations"])
    assert b.read(OUT / "baseline-control.json")["status"] == "PASS"
    timing = {}
    for field in ("elapsed_seconds", "ranking_elapsed_seconds"):
        values = sorted(r[field] for r in rows if r["status"] == "EVALUATED")
        timing[field] = {**{name: values[max(0, ceil(q * len(values)) - 1)] if values else None
            for name, q in (("p50", .5), ("p95", .95), ("p99", .99))}, "max": max(values, default=None), "total": sum(values)}
    status = "CONTINUE_UNSEEN_DEVELOPMENT" if positive and clean and reliable else "RESEARCH_EXECUTION_REVIEW" if positive else "NOT_PROMOTED_AFTER_SECOND_SEEN"
    result = {"status": status, "candidate_id": plan["candidate_id"], "versus_v2": measures, "declared_mix": block["declared_mix"],
        "effect_condition_passed": positive, "clean_prototype_execution": clean, "driver_reliable_in_logical_time": reliable,
        "continue_unseen_development": positive and clean and reliable, "effect_positive_needs_execution_review": positive and not (clean and reliable),
        "prototype_decisions": len(rows), "prototype_statuses": dict(statuses), "first_changes_from_v2": sum(r["changed"] for r in rows),
        "first_changes_from_parent_on_candidate_trajectory": sum(r["selected_first"] != r["parent_selected_first"] for r in rows),
        "rule_calls": sum(r["rule_calls"] for r in rows), "timing_seconds": timing, "runtime_counts": dict(runtime),
        "full_candidate_tables_verified": 128, "full_reused_baseline_tables_verified": 128, "new_baseline_control_tables": 4,
        "new_full_tables": 132, "spent": ledger.account_summary(), "model_calls": 0, "confirmation_roots": 0, "formal_alpha_spent": 0,
        "interpretation": "第二已曝光清单，根为统计单位；平分识别界与抽样区间分开，两清单不合并覆盖失败。片段时延和逻辑时钟不代替真实全链及并发验收。",
        "release_eligible": False}
    verify_inputs(plan)
    b.write(OUT / "development-decision.json", result)
    b.write(OUT / "next-stage-prerequisite.json", {"candidate_id": plan["candidate_id"],
        "development_decision_sha256": b.digest((OUT / "development-decision.json").read_bytes()),
        "unseen_development_allowed": result["continue_unseen_development"], "confirmation_allowed": False,
        "core_pass_does_not_override_second_result": True, "source_generation_started": False, "new_stage_spent": 0})
    print({k: result[k] for k in ("status", "versus_v2", "prototype_statuses", "first_changes_from_v2")}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "close"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "close": close}[args.operation]()
