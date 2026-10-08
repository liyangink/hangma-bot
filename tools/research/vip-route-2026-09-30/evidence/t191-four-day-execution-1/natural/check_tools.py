"""用已闭开发原件验新路由与负例；不评分、不生成世界或新桌。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/natural'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import copy
import json
from pathlib import Path

import read_stage as reader
from source_helpers import preflight, account
from common import pin, save

HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1')


def rejected(function):
    """坏输入必须显式拒绝，不能用缺项补零通过。"""
    try:
        function()
    except (ValueError, AssertionError):
        return
    raise AssertionError("坏输入未拒绝")


def main():
    """逐值重算64个旧桌账本，匹配旧公开摘要，保留各源负差。"""
    plan_path = _project_file(_PROJECT_ROOT, OLD / "NATURAL-STAGE-001-PLAN.json")
    plan = json.loads(plan_path.read_text())
    tables = preflight(plan, pin(plan_path))
    ledgers, audit_calls = {}, 0
    context = dict(reader.dev.__dict__)
    context["decision_metadata"] = reader.metadata_adapter(reader.dev.decision_metadata)
    receipts = reader.function_copy(reader.dev.score_receipts, context)
    for table in tables:
        closed = json.loads((table.directory / "CLOSURE.json").read_text())
        settlements = copy.deepcopy(closed["settlements"])
        root_id = closed["root"]["root_id"]
        for row in settlements:
            row["match_id"] = "t191-development:" + root_id
        ledger, scores = account(settlements, table.rotation, root_id)
        assert scores == closed["outcome"]["final_scores"]
        for row in settlements:
            row["match_id"] = "t185-development:" + root_id
        reference, reference_scores = reader.dev.account(settlements, table.rotation, root_id)
        assert ledger == reference and scores == reference_scores
        ledgers[(table.index, table.rotation, table.arm_index)] = ledger
        if table.index == 1 and table.rotation == 0:
            audit, _ = receipts(table, closed, plan)
            audit_calls += audit["actual_score_calls"]
    old = json.loads((_project_file(_PROJECT_ROOT, OLD / "natural-stage-001-dispatch/SUMMARY.json")).read_text())
    per_source = []
    for index in plan["root_indices"]:
        totals = {key: sum(ledgers[(index, r, 1)][key] - ledgers[(index, r, 0)][key]
            for r in range(4)) for key in next(iter(ledgers.values()))}
        per_source.append(totals)
    mean = {key: sum(row[key] for row in per_source) / 32 for key in per_source[0]}
    assert mean == old["mean_delta_per_complete_table"]
    assert any(row["net"] < 0 for row in per_source)
    assert reader.interval([0] * 8, {"seed": 20261005, "replicates": 1000}) == [0, 0]
    assert reader.interval([-8] * 8, {"seed": 20261005, "replicates": 1000}) == [-2, -2]
    bad_plan = copy.deepcopy(plan)
    bad_plan["parent"]["identity"]["candidate_id"] = "invalid"
    rejected(lambda: preflight(bad_plan, pin(plan_path)))
    bad_plan = dict(plan, planned_table_instances=63)
    rejected(lambda: preflight(bad_plan, pin(plan_path)))
    example = json.loads((tables[0].directory / "CLOSURE.json").read_text())
    rows = copy.deepcopy(example["settlements"])
    root_id = example["root"]["root_id"]
    for row in rows:
        row["match_id"] = "t191-development:" + root_id
    for change in ("prefix", "sequence", "nonconservation", "unknown_draw"):
        bad = copy.deepcopy(rows)
        if change == "prefix":
            bad[0]["match_id"] = "wrong:" + root_id
        elif change == "sequence":
            bad[0]["round_no"] = 2
        elif change == "nonconservation":
            bad[0]["settlement"]["score_delta"][0] += 1
        else:
            bad[0]["settlement"]["is_draw"] = None
        rejected(lambda: account(bad, tables[0].rotation, root_id))
    save(_project_file(_PROJECT_ROOT, HERE / "TOOL-CHECKS.json"), {"complete": True,
        "existing_table_metadata_verified": len(tables), "existing_ledgers_exactly_equal": len(tables),
        "existing_score_receipts_verified": audit_calls,
        "paired_mean_all_fields_matches_existing_summary": True,
        "negative_source_deltas_preserved": True, "rejected_bad_inputs": 6,
        "degenerate_bootstrap_controls": 2,
        "new_scores_worlds_tables_models_HTTP": 0,
        "fixture_match_prefix_changed_only_in_memory": True,
        "files": {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "read_stage.py"),
            _project_file(_PROJECT_ROOT, HERE / "source_helpers.py"), plan_path, _project_file(_PROJECT_ROOT, OLD / "natural-stage-001-dispatch/SUMMARY.json"))}})
    print(json.dumps({"complete": True, "old_tables_verified": len(tables),
        "old_actual_score_receipts": audit_calls, "new_executions": 0}))


if __name__ == "__main__":
    main()
