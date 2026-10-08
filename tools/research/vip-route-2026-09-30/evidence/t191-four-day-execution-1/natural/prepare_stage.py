"""固定候选机械/条件资格后准备小块自然桌；不自动启动或扩大。"""

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
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1')
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, pin, save
from hangma_bot.offline.scoring_sources import source_manifest
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from four_worker_campaign import validate


def main(args):
    """前置资格必须真实全闭；候选身份、失败和费用保留，不用作者元数据冒充。"""
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, CAMPAIGN / "EXECUTION-BATCH.json"))
    initial = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / "EXECUTION-START.json")).read_text())
    parent = {"label": "online-S02", "source_file": str(_project_file(_PROJECT_ROOT, CAMPAIGN / "parent-source.py")),
        "identity": batch.identity((_project_file(_PROJECT_ROOT, CAMPAIGN / "parent-source.py")).read_text())}
    assert parent["identity"] == initial["baseline_identity"]
    roots = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / "FROZEN-OPPONENT-COMPOSITIONS.json")).read_text())["pools"]["development"]
    candidates, gates, candidate_files = [], [], []
    if not args.preflight:
        assert args.sources and len(args.sources) <= 2 and len(args.sources) == len(args.gates)
        for source_path, gate_path in zip(args.sources, args.gates):
            source_path, gate_path = source_path.resolve(), gate_path.resolve()
            assert source_path.is_relative_to(_project_file(_PROJECT_ROOT, CAMPAIGN / "candidates"))
            gate = json.loads(gate_path.read_text())
            identity = batch.identity(source_path.read_text())
            assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
            assert gate["identity"] == identity
            ActionValueExecutor(source_path.read_text(), max_operations=batch.max_operations,
                max_local_collection_size=batch.projection_limits.max_nodes)
            candidates.append({"label": source_path.parent.name, "source_file": str(source_path), "identity": identity})
            gates.append(gate_path)
            candidate_files.append(source_path)
        assert args.conditions and len(args.conditions) == len(candidates)
        for path in args.conditions:
            condition = json.loads(path.read_text())
            assert condition["complete"] and condition["source_stable"] and condition["resources_released"]
            assert condition["candidate_identity"] in [c["identity"] for c in candidates]
        assert len({c["identity"]["candidate_id"] for c in candidates}) == len(candidates)
    assert not {parent["identity"]["candidate_id"]} & {c["identity"]["candidate_id"] for c in candidates}
    indices = list(range(args.first, args.last + 1))
    assert 1 <= args.first <= args.last <= 32
    assert args.preflight and indices == [1] or not args.preflight and (args.first, args.last) in ((1, 8), (9, 16), (17, 32))
    path = _project_file(_PROJECT_ROOT, HERE / (args.label + "-PLAN.json"))
    tasks = [{"ordinal": o, "root": i, "rotation": r, "arm": a}
        for o, (i, r, a) in enumerate((i, r, a) for i in indices for r in range(4) for a in range(1 + len(candidates)))]
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "four_worker_campaign.py"), _project_file(_PROJECT_ROOT, HERE / "full_table_runtime.py"), _project_file(_PROJECT_ROOT, HERE / "read_stage.py"),
        _project_file(_PROJECT_ROOT, HERE / "source_helpers.py"), _project_file(_PROJECT_ROOT, HERE / "SOURCE-HELPERS-PROVENANCE.json"),
        _project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json"), _project_file(_PROJECT_ROOT, CAMPAIGN / "EXECUTION-BATCH.json"), _project_file(_PROJECT_ROOT, CAMPAIGN / "EXECUTION-START.json"),
        _project_file(_PROJECT_ROOT, CAMPAIGN / "DEVELOPMENT-PROTOCOL.md"), _project_file(_PROJECT_ROOT, CAMPAIGN / "FRESH-SOURCE-DESCRIPTORS.json"),
        _project_file(_PROJECT_ROOT, CAMPAIGN / "FROZEN-OPPONENT-COMPOSITIONS.json"), Path(parent["source_file"]),
        _project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json"), _project_file(_PROJECT_ROOT, PRIOR / "t185_run_development.py"),
        _project_file(_PROJECT_ROOT, PRIOR / "t185_close_development.py"), _project_file(_PROJECT_ROOT, PRIOR / "evaluation_sharding.py"), _project_file(_PROJECT_ROOT, PRIOR / "readout_compat.py"),
        *candidate_files, *gates, *args.conditions]
    manifest = dict(initial["baseline_identity"]["source_manifest"])
    manifest.update(source_manifest(("hangma_bot.offline.evaluate", "hangma_bot.offline.scoring_input_capture",
        "hangma_bot.offline.qualifier_opponents", "hangma_bot.offline.vip_route_development")))
    plan = {"schema": "t191-staged-development/1", "purpose": "runtime_preflight" if args.preflight else "minimal_repair_development",
        "plan_path": str(path), "cpu_worker_count": 4, "rounds": 8, "rotations": [0, 1, 2, 3],
        "root_indices": indices, "roots": roots, "parent": parent, "candidates": candidates, "tasks": tasks,
        "planned_table_instances": len(tasks), "maximum_actual_complete_table_instances": len(tasks),
        "independent_confirmation_auto_dispatch": False, "next_stage_auto_dispatch": False,
        "dispatch_directory": str(_project_file(_PROJECT_ROOT, HERE / (args.label + "-dispatch"))),
        "output_directory": str(_project_file(_PROJECT_ROOT, HERE / ("runtime-preflight-tables" if args.preflight else "natural-development"))),
        "prior_closed_pin": pin(_project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json")),
        "files": {str(p): pin(p) for p in files}, "source_manifest": manifest,
        "wall_seconds_per_table": 600, "minimum_free_bytes": 8589934592, "step_limit": 50000,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912, "max_unique_views": 4096},
        "initial_dealer_physical": 0, "initial_scores_0_1_2_3": [0, 0, 0, 0],
        "bootstrap": {"replicates": 20000, "seed": 20261005, "unit": "mother_source_four_seat_paired_mean",
            "exploratory_not_time_uniform": True},
        "human_engineering_candidates_not_new_model_outputs": True,
        "no_online_deadline_or_strength_admission": True}
    save(path, plan)
    validate(path)
    print(json.dumps({"prepared": True, "plan": str(path), "planned_complete_tables": len(tasks),
        "candidate_count": len(candidates), "actual_tables": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--sources", nargs="*", type=Path, default=[])
    parser.add_argument("--gates", nargs="*", type=Path, default=[])
    parser.add_argument("--conditions", nargs="*", type=Path, default=[])
    parser.add_argument("--first", type=int, default=1)
    parser.add_argument("--last", type=int, default=8)
    main(parser.parse_args())
