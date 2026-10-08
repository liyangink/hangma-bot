"""后继改良离线原型的完整阶段开发对照；复用生产驱动、规则、赛程及统计。"""

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
from time import monotonic

import followup_quality_checks as checks
import followup_quality_policy as policy
import confirmation_execution_identity as guard
from confirmation_execution_probe import execute_arm
from verify_full_natural_results import verify_full_table
from verify_natural_evidence import _digest
from hangma_bot.kernel.config import RuleConfig

b = checks.b
natural = checks.proof.natural
OUT = checks.OUT
REFERENCE = b.HERE / "tempo-opportunity-20260920/tempo-opportunity-terra-max"


def prepare():
    """先冻结128候选桌、4基线复现桌和128已见基线复用，不按中途成绩加减根。"""
    assert not (OUT / "evaluation-plan.json").exists()
    engineering = b.read(OUT / "manifest.json")
    guard.verify(engineering["runtime"])
    assert b.read(OUT / "checks.json")["status"] == "PASS_OFFLINE_PROTOTYPE_ONLY"
    old_freeze = b.read(REFERENCE / "pre-evaluation-freeze.json")
    guard.verify(old_freeze["runtime"])
    contract_path = b.ROUTE / "contracts/group-dev-v1.json"
    contract = b.read(contract_path)
    reference_paths = {mix: REFERENCE / "run/iterations/iter-01" / ("natural-" + mix) / "panel.json" for mix in ("H", "M")}
    plan = {"schema": "offline-followup-effect-plan/1", "created_at_utc": b.search.utc_now(),
        "candidate_id": "offline-followup:" + engineering["source_sha256"],
        "prototype_manifest_sha256": b.digest((OUT / "manifest.json").read_bytes()),
        "checks_sha256": b.digest((OUT / "checks.json").read_bytes()),
        "contract": str(contract_path), "contract_sha256": b.digest(contract_path.read_bytes()),
        "reference_panels": {mix: {"path": str(path), "sha256": b.digest(path.read_bytes())} for mix, path in reference_paths.items()},
        "reference_freeze": str(REFERENCE / "pre-evaluation-freeze.json"),
        "reference_freeze_sha256": b.digest((REFERENCE / "pre-evaluation-freeze.json").read_bytes()),
        "runtime": guard.capture(source_paths=[*b.HERE.glob("*.py")]),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": 2026092001, "root_indices": list(range(1, 9)), "seats_per_root": 4,
        "candidate_tables": 128, "baseline_control_tables": 4, "max_new_full_tables": 132,
        "reused_baseline_tables": 128, "max_process_seconds": 2400,
        "decision_rule": "完整132新桌对账、4基线控制桌复现；无原型事实/内部/成本回退及驱动错误，H/M各8根的开发配对mean_delta_low均>0才继续第二已见清单。性能成本独立报告，不据此否决机制研究；本批若发生回退只报告混合行为并另裁定",
        "baseline_reuse": "旧核心面板128桌V2臂；规则/模拟/对手生产依赖完全相同。先重跑H/M根1座位0各两桌核验新组合，再复用其他原件；消融关闭机制即V2",
        "pairing_scope": "每根四座位配置，各配置双臂同牌山；不同配置使用不同桌种子，不冒充同牌山四座位重复",
        "model_calls": 0, "confirmation_roots": 0, "release_eligible": False,
    }
    assert contract["group"]["tables_per_group"] == 2
    b.write(OUT / "evaluation-plan.json", plan)
    auth = b.unified_document(batch_label="followup-quality-prototype", authorization_id="r10-followup-quality-prototype",
        accounts={"tables_full": 132}, issued_by="lead", issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth["issuance_basis"] = "用户持续进化与有界性能研究授权；已见核心清单，128候选桌加4基线组合复现桌，0作者与确认"
    natural.require_authorization(auth)
    b.write(OUT / "evaluation-authorization.json", auth)
    print("frozen: 132 new full tables + 128 reused baseline tables, no confirmation", flush=True)


def verify_inputs(plan):
    """恢复或每阶段前核对新旧源码闭包和历史结果摘要，拒绝原件漂移。"""
    guard.verify(plan["runtime"])
    for name, key in (("manifest.json", "prototype_manifest_sha256"), ("checks.json", "checks_sha256")):
        assert b.digest((OUT / name).read_bytes()) == plan[key]
    assert b.digest(b.Path(plan["contract"]).read_bytes()) == plan["contract_sha256"]
    path = b.Path(plan["reference_freeze"])
    assert b.digest(path.read_bytes()) == plan["reference_freeze_sha256"]
    guard.verify(b.read(path)["runtime"])
    for ref in plan["reference_panels"].values():
        assert b.digest(b.Path(ref["path"]).read_bytes()) == ref["sha256"]


def run_stage(plans, mix, arm, contract):
    """只替换焦点位策略；阶段账投影、桌执行器、名次分和目标值复用既有实现。"""
    versions = natural.stage.contract_versions_block(contract)
    config = RuleConfig(**{key: versions[key] for key in ("ruleset_version", "base_score", "you_cai_bi_kao")})
    totals, points, tables = {}, {}, []
    started = monotonic()
    for index, table_plan in enumerate(plans):
        situation = natural.build_stage_situation(plan=table_plan, table_no=index + 1, tables_completed=index,
            totals=totals, place_totals=points, rounds_per_game=versions["rounds_per_game"])
        logical = natural.arm_logical_policies(arm="baseline", candidate_scorer=None,
            logical_participants=table_plan.logical_participants,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"], monotonic=lambda: 800.0)
        if arm == "candidate":
            logical[natural.FOCAL_PARTICIPANT] = policy.FollowupQualityPolicy(config, lambda: 800.0)
        actual = natural.seat_policies_from(logical, table_plan.permutation, table_plan.logical_participants)
        row = natural.execute_natural_table(plan=table_plan, policies_by_seat=actual, versions_block=versions,
            step_limit=contract["stop"]["step_limit"], value_limits=natural.ValueAnalysisLimits(), stage_situation=situation)
        row["stage_situation"] = situation.to_json()
        if arm == "candidate":
            row["prototype_audit"] = logical[natural.FOCAL_PARTICIPANT].audit
        tables.append(row)
        assert row["match_status"] == "complete" and row["scores_by_seat"] is not None
        per_seat_points = natural.stage.place_points_for_table(row["scores_by_seat"])
        for seat, participant in enumerate(table_plan.seats()):
            totals[participant] = totals.get(participant, 0) + row["scores_by_seat"][seat]
            points[participant] = points.get(participant, 0) + per_seat_points[seat]
    ledger_rows = [natural.stage.LedgerRow(participant_id=p, total_score=totals[p], place_points=points[p]) for p in sorted(totals)]
    utility = natural.stage.group_advance_utility(ledger_rows, focal_id=natural.FOCAL_PARTICIPANT)
    return {"arm": arm, "status": "complete", "usable": True, "error": None, "tables": tables,
        "stage_totals_by_participant": totals, "stage_place_points_by_participant": points,
        "focal_stage_score": totals[natural.FOCAL_PARTICIPANT],
        "u_low": float(utility["u_low"]), "u_high": float(utility["u_high"]),
        "u": float(utility["u_low"]) if utility["u_low"] == utility["u_high"] else None,
        "unresolved": utility["unresolved"], "u_interval": {k: utility[k] for k in ("a", "b", "tie_block")},
        "elapsed_ms": (monotonic() - started) * 1000,
        "execution_review": natural.execution_audit.review_tables(tables)}


def verify_stage(raw, plans, contract, plan, arm):
    """重新组装已完成阶段账；核对完整桌结果、实际焦点装配和每次增强审计。"""
    assert raw["arm"] == arm and raw["status"] == "complete" and raw["usable"] is True and raw["error"] is None
    assert len(raw["tables"]) == len(plans) == 2
    totals, points, statuses, counts = {}, {}, Counter(), Counter()
    for index, (row, expected) in enumerate(zip(raw["tables"], plans, strict=True)):
        assert row["table_id"] == expected.table_id and row["seed"] == expected.seed
        checked = verify_full_table(row, expected, contract, plan["rules_hash"], require_execution_audit=True)
        counts.update(checked["runtime_counts"])
        situation = natural.build_stage_situation(plan=expected, table_no=index + 1, tables_completed=index,
            totals=totals, place_totals=points, rounds_per_game=contract["versions"]["rounds_per_game"])
        assert row["stage_situation"] == situation.to_json()
        scores = row["scores_by_seat"]
        per_seat_points = natural.stage.place_points_for_table(scores)
        for seat, participant in enumerate(expected.seats()):
            totals[participant] = totals.get(participant, 0) + scores[seat]
            points[participant] = points.get(participant, 0) + per_seat_points[seat]
        if arm == "candidate":
            focal = list(expected.seats()).index(natural.FOCAL_PARTICIPANT)
            audit = row["prototype_audit"]
            assert row["policy_execution"]["policy_ids_by_seat"][focal] == policy.PROFILE["id"]
            assert row["result"]["versions"]["natural_seat_policy:" + str(focal)] == policy.PROFILE["id"]
            assert len(audit) == row["policy_execution"]["by_seat"][focal]["decision_count"]
            assert len({r["decision_id"] for r in audit}) == len(audit)
            for r in audit:
                assert r["status"] in ("EVALUATED", "NOT_APPLICABLE", "COST_FALLBACK", "FACT_FALLBACK", "ERROR_FALLBACK")
                assert 0 <= r["rule_calls"] <= policy.PROFILE["max_rule_calls"]
                assert r["changed"] == (r["base_first"] != r["selected_first"])
                assert r["status"] == "EVALUATED" or not r["changed"]
                statuses[r["status"]] += 1
                statuses["first_changed"] += int(r["changed"])
    utility = natural.stage.group_advance_utility([natural.stage.LedgerRow(participant_id=p, total_score=totals[p],
        place_points=points[p]) for p in sorted(totals)], focal_id=natural.FOCAL_PARTICIPANT)
    assert raw["stage_totals_by_participant"] == totals and raw["stage_place_points_by_participant"] == points
    assert raw["focal_stage_score"] == totals[natural.FOCAL_PARTICIPANT]
    assert raw["u_low"] == utility["u_low"] and raw["u_high"] == utility["u_high"]
    assert raw["unresolved"] == utility["unresolved"] and raw["u_interval"] == {k: utility[k] for k in ("a", "b", "tie_block")}
    assert raw["execution_review"] == natural.execution_audit.review_tables(raw["tables"])
    return {"tables": 2, "prototype_counts": dict(statuses), "runtime_counts": dict(counts), "release_eligible": False}


def terminal_equal(actual, old):
    """只比较终端和运行计数；不把同终端冒充逐动作轨迹等价。"""
    for key in ("stage_totals_by_participant", "stage_place_points_by_participant", "u_low", "u_high"):
        assert actual[key] == old[key]
    for a, z in zip(actual["tables"], old["tables"], strict=True):
        for key in ("scores_before", "scores_after", "completed_hands", "expected_hands", "runtime_counts", "status", "invalid_reasons"):
            assert a["result"][key] == z["result"][key], (a["table_id"], key)


def run():
    """先复现组合控制，再执行固定核心清单；只恢复已落完整产物，不重跑半个阶段。"""
    plan = b.read(OUT / "evaluation-plan.json")
    verify_inputs(plan)
    contract = b.read(b.Path(plan["contract"]))
    auth = b.read(OUT / "evaluation-authorization.json")
    natural.require_authorization(auth)
    ledger = b.search.ActionValueLedger.load(OUT / "evaluation-ledger.json", authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    panels = {mix: b.read(b.Path(ref["path"])) for mix, ref in plan["reference_panels"].items()}
    previous = {(mix, s["root_index"], s["focal_anchor_seat"]): s for mix, panel in panels.items() for s in panel["samples"]}
    assert len(previous) == 64
    def execute(mix, root, seat, arm):
        verify_inputs(plan)
        plans = natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=root, focal_seat=seat, panel_seed=plan["panel_seed"])
        label = f"{mix}-root{root}-seat{seat}-{arm}"
        expected = {"step_id": label, "planned_tables": 2, "manifest_digest": _digest(plan),
                    "plans_digest": _digest([p.to_json() for p in plans]), "arm": arm, "candidate_id": plan["candidate_id"]}
        folder = OUT / "arms" / label
        execute_arm(folder, expected=expected, ledger=ledger,
            runner=lambda: run_stage(plans, mix, arm, contract),
            verifier=lambda raw: verify_stage(raw, plans, contract, plan, arm))
        return b.read(folder / "result.json")["raw"]
    for mix in ("H", "M"):
        actual = execute(mix, 1, 0, "baseline")
        terminal_equal(actual, previous[(mix, 1, 0)]["raw_arms"]["baseline"])
    b.write(OUT / "baseline-control.json", {"status": "PASS", "new_tables": 4, "terminals_reproduced": 4, "reuse_allowed": True})
    samples = []
    for mix in ("H", "M"):
        for root in plan["root_indices"]:
            for seat in range(4):
                old = previous[(mix, root, seat)]
                plans = natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=root, focal_seat=seat, panel_seed=plan["panel_seed"])
                baseline = old["raw_arms"]["baseline"]
                verify_stage(baseline, plans, contract, plan, "baseline")
                result = execute(mix, root, seat, "candidate")
                slim = {key: result[key] for key in ("status", "usable", "error", "focal_stage_score", "stage_totals_by_participant", "u", "u_low", "u_high", "unresolved", "elapsed_ms")}
                slim.update({"candidate_id": plan["candidate_id"], "policy_id": policy.PROFILE["id"]})
                sample = {**old, "candidate_id": plan["candidate_id"],
                    "arms": {"baseline": old["arms"]["baseline"], "candidate": slim},
                    "raw_arms": {"baseline": baseline, "candidate": result},
                    "cost": {"new_candidate_tables": 2, "reused_baseline_tables": 2},
                    "selection_scope": "offline_prototype_development_only"}
                samples.append(sample)
            print(mix, "root", root, "complete; new tables", ledger.spent("tables_full"), flush=True)
    verify_inputs(plan)
    assert ledger.spent("tables_full") == 132 and len(samples) == 64
    statistics = natural.paired_stage_statistics(samples, min_roots=8)
    assert statistics["invalid_count"] == 0 and statistics["uncomputable_count"] == 0
    rows = [r for s in samples for t in s["raw_arms"]["candidate"]["tables"] for r in t["prototype_audit"]]
    statuses = Counter(r["status"] for r in rows)
    counts = Counter()
    for s in samples:
        for t in s["raw_arms"]["candidate"]["tables"]:
            counts.update(t["result"]["runtime_counts"])
    b.write(OUT / "effect-samples.json", samples)
    b.write(OUT / "effect-statistics.json", statistics)
    b.write(OUT / "effect-summary.json", {"status": "COMPLETE_OFFLINE_CORE_DEVELOPMENT", "new_full_tables": 132,
        "reused_baseline_tables": 128, "prototype_decisions": len(rows), "prototype_statuses": dict(statuses),
        "first_changes": sum(r["changed"] for r in rows), "rule_calls": sum(r["rule_calls"] for r in rows),
        "max_enhancement_seconds": max(r["elapsed_seconds"] for r in rows),
        "total_enhancement_seconds": sum(r["elapsed_seconds"] for r in rows), "runtime_counts": dict(counts),
        "spent": ledger.account_summary(), "model_calls": 0, "confirmation_roots": 0, "release_eligible": False})
    print("complete offline core development; inspect statistics before next action", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else run()
