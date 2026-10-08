"""两种真实后继研究策略共用的阶段组合；生产驱动、规则与目标求值保持单一来源。"""

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
from collections import Counter
from time import monotonic

import followup_quality_panel as original

natural = original.natural


def run_stage(plans, mix, arm, contract, focal_factory):
    """每桌新建受信研究策略，只替换焦点位；阶段开始前注入已完成桌账。"""
    versions = natural.stage.contract_versions_block(contract)
    config = original.RuleConfig(**{k: versions[k] for k in ("ruleset_version", "base_score", "you_cai_bi_kao")})
    totals, points, tables = {}, {}, []
    start = monotonic()
    for index, plan in enumerate(plans):
        situation = natural.build_stage_situation(plan=plan, table_no=index + 1, tables_completed=index,
            totals=totals, place_totals=points, rounds_per_game=versions["rounds_per_game"])
        logical = natural.arm_logical_policies(arm="baseline", candidate_scorer=None,
            logical_participants=plan.logical_participants,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"], monotonic=lambda: 800.)
        if arm == "candidate":
            logical[natural.FOCAL_PARTICIPANT] = focal_factory(config)
        row = natural.execute_natural_table(plan=plan,
            policies_by_seat=natural.seat_policies_from(logical, plan.permutation, plan.logical_participants),
            versions_block=versions, step_limit=contract["stop"]["step_limit"],
            value_limits=natural.ValueAnalysisLimits(), stage_situation=situation)
        row["stage_situation"] = situation.to_json()
        if arm == "candidate":
            row["prototype_audit"] = logical[natural.FOCAL_PARTICIPANT].audit
        tables.append(row)
        assert row["match_status"] == "complete" and row["scores_by_seat"] is not None
        place = natural.stage.place_points_for_table(row["scores_by_seat"])
        for seat, participant in enumerate(plan.seats()):
            totals[participant] = totals.get(participant, 0) + row["scores_by_seat"][seat]
            points[participant] = points.get(participant, 0) + place[seat]
    utility = natural.stage.group_advance_utility([natural.stage.LedgerRow(participant_id=p, total_score=totals[p],
        place_points=points[p]) for p in sorted(totals)], focal_id=natural.FOCAL_PARTICIPANT)
    return {"arm": arm, "status": "complete", "usable": True, "error": None, "tables": tables,
        "stage_totals_by_participant": totals, "stage_place_points_by_participant": points,
        "focal_stage_score": totals[natural.FOCAL_PARTICIPANT], "u_low": float(utility["u_low"]),
        "u_high": float(utility["u_high"]), "u": float(utility["u_low"]) if utility["u_low"] == utility["u_high"] else None,
        "unresolved": utility["unresolved"], "u_interval": {k: utility[k] for k in ("a", "b", "tie_block")},
        "elapsed_ms": (monotonic() - start) * 1000,
        "execution_review": natural.execution_audit.review_tables(tables)}


def verify_stage(raw, plans, contract, rules_hash, arm, policy_id):
    """按完整桌结果复算阶段账，核对焦点身份及每次研究增强审计，不使用伪造策略标签。"""
    assert raw["arm"] == arm and raw["status"] == "complete" and raw["usable"] is True and raw["error"] is None
    assert len(raw["tables"]) == len(plans) == 2
    totals, points, statuses, counts = {}, {}, Counter(), Counter()
    for index, (row, plan) in enumerate(zip(raw["tables"], plans, strict=True)):
        assert row["table_id"] == plan.table_id and row["seed"] == plan.seed
        checked = original.verify_full_table(row, plan, contract, rules_hash, require_execution_audit=True)
        counts.update(checked["runtime_counts"])
        expected = natural.build_stage_situation(plan=plan, table_no=index + 1, tables_completed=index,
            totals=totals, place_totals=points, rounds_per_game=contract["versions"]["rounds_per_game"])
        assert row["stage_situation"] == expected.to_json()
        place = natural.stage.place_points_for_table(row["scores_by_seat"])
        for seat, participant in enumerate(plan.seats()):
            totals[participant] = totals.get(participant, 0) + row["scores_by_seat"][seat]
            points[participant] = points.get(participant, 0) + place[seat]
        if arm == "candidate":
            seat = list(plan.seats()).index(natural.FOCAL_PARTICIPANT)
            assert row["policy_execution"]["policy_ids_by_seat"][seat] == policy_id
            assert row["result"]["versions"]["natural_seat_policy:" + str(seat)] == policy_id
            audit = row["prototype_audit"]
            assert len(audit) == row["policy_execution"]["by_seat"][seat]["decision_count"]
            assert len({r["decision_id"] for r in audit}) == len(audit)
            for r in audit:
                assert r["status"] in ("EVALUATED", "NOT_APPLICABLE", "FACT_FALLBACK", "COST_FALLBACK", "ERROR_FALLBACK")
                assert 0 <= r["rule_calls"] <= original.policy.PROFILE["max_rule_calls"]
                assert r["changed"] == (r["selected_first"] != r["base_first"])
                assert r["status"] == "EVALUATED" or not r["changed"]
                statuses[r["status"]] += 1
                statuses["first_changed"] += int(r["changed"])
    value = natural.stage.group_advance_utility([natural.stage.LedgerRow(participant_id=p, total_score=totals[p],
        place_points=points[p]) for p in sorted(totals)], focal_id=natural.FOCAL_PARTICIPANT)
    assert raw["stage_totals_by_participant"] == totals and raw["stage_place_points_by_participant"] == points
    assert raw["focal_stage_score"] == totals[natural.FOCAL_PARTICIPANT]
    assert raw["u_low"] == value["u_low"] and raw["u_high"] == value["u_high"]
    assert raw["u"] == (float(value["u_low"]) if value["u_low"] == value["u_high"] else None)
    assert raw["unresolved"] == value["unresolved"] and raw["u_interval"] == {k: value[k] for k in ("a", "b", "tie_block")}
    assert raw["execution_review"] == natural.execution_audit.review_tables(raw["tables"])
    return {"tables": 2, "runtime_counts": dict(counts), "prototype_counts": dict(statuses), "release_eligible": False}
