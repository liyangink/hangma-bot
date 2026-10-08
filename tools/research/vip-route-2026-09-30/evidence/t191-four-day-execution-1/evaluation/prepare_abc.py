"""冻结T191共同续策三组计划；准备阶段不生成世界、不评分、不续打。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/evaluation'

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
from pathlib import Path

from abc_support import *
from hangma_bot.offline.vip_eoh_generate import VipEohBatch


def prepare(args):
    """输入工程候选源码及公开来源元数据，排他保存可供总筹批准的计划。"""
    batch_path, source_path = Path(args.batch).resolve(), Path(args.candidate_source).resolve()
    parent_path, source_plan = STAGE / "parent-source.py", Path(args.source_plan).resolve()
    batch = VipEohBatch.read(batch_path)
    sources = {"parent": parent_path.read_text(), "child": source_path.read_text()}
    identities = {name: batch.identity(source) for name, source in sources.items()}
    require(identities["child"]["candidate_id"] == args.candidate_id, "候选身份不同")
    original = read(source_plan)
    require(len(original["targets"]) == 14, "历史控制必须保留原14顺序")
    targets = [normalize_target(t, historical=True) for t in original["targets"]]
    files = [batch_path, parent_path, source_path, source_plan, *reused_files(),
        _project_file(_PROJECT_ROOT, HERE / "abc_support.py"), _project_file(_PROJECT_ROOT, HERE / "prepare_abc.py"), _project_file(_PROJECT_ROOT, HERE / "run_abc.py"), _project_file(_PROJECT_ROOT, HERE / "close_abc.py"),
        _project_file(_PROJECT_ROOT, HERE / "check_preflight.py")]
    if args.extra_targets:
        extra_path = Path(args.extra_targets).resolve()
        extra = read(extra_path)
        require(extra["selection_uses_outcomes_or_candidate_scores"] is False and len(extra["targets"]) <= 10,
            "新增公开来源不能按成绩或候选评分选择，最多10")
        targets += [normalize_target(t, historical=False) for t in extra["targets"]]
        files += [extra_path, *[Path(p) for p in extra.get("files", {})]]
        require(all(pin(Path(p)) == h for p, h in extra.get("files", {}).items()), "新增来源原件漂移")
    keys = [(t["case"]["window_key"]["game_id"], t["case"]["window_key"]["round_no"],
        t["case"]["window_key"]["trigger_seq"], t["focal_seat"]) for t in targets]
    require(len(keys) == len(set(keys)) and len(targets) <= 24, "目标重复或超过24")
    files += [Path(t["source_closure"]) for t in targets]
    manifest = {}
    for identity in identities.values():
        manifest.update(identity["source_manifest"])
    for module_path in ("src/hangma_bot/offline/evaluate.py", "src/hangma_bot/offline/forced_action.py",
        "src/hangma_bot/offline/qualifier_opponents.py", "src/hangma_bot/offline/scoring_input_capture.py",
        "src/hangma_bot/offline/vip_route_development.py", "src/hangma_bot/simulation/engine.py"):
        manifest[module_path] = pin(_project_file(_PROJECT_ROOT, ROOT / module_path))
    require(args.historical in ("included", "excluded"), "历史账选择不完整")
    historical = args.historical == "included"
    plan = {"schema": "t191-fixed-abc-condition/1", "candidate_label": args.label,
        "batch_file": str(batch_path), "targets": targets,
        "arms_sources": {name: {"source_file": str(parent_path if name == "parent" else source_path),
            "identity": identities[name]} for name in sources},
        "files": {str(p): pin(p) for p in files}, "source_manifest": manifest,
        "worlds_per_target": 2, "historical_original_world_for_first_14": historical,
        "planned_compatible_single_hand_instances": len(targets) * 2 * 3,
        "maximum_compatible_single_hand_instances": 144,
        "planned_historical_single_hand_instances": 14 * 3 if historical else 0,
        "maximum_historical_single_hand_instances": 42,
        "planned_single_hand_instances": len(targets) * 6 + (42 if historical else 0),
        "coverage": {"requested_public_sources": 24, "actual_public_sources": len(targets),
            "missing_public_sources": 24 - len(targets),
            "distinct_mother_sources": len({t['composition']['root_id'] for t in targets}),
            "complete_24_source_coverage": len(targets) == 24},
        "cpu_worker_count": 4, "step_limit": 50000, "wall_seconds_per_target": 1800,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912, "max_unique_views": 4096},
        "A": "全程S02真实完整评分，自行选择", "B": "公共窗口候选真实评分决定首手，ForceFirstActionPolicy(S02)仅强制一次，其后S02真实评分",
        "C": "全程候选真实完整评分，自行选择",
        "selector_score_calls_planned": len(targets), "forcing_is_c_self_scored": False,
        "logical_clock_monotonic_seconds": 800.0,
        "same_hidden_world_opponents_seat_rules_and_budget_per_ABC": True,
        "sample_key_prefix": "t191-fixed-abc", "historical_and_compatible_not_pooled": True,
        "sampler_is_true_posterior_or_natural_frequency": False,
        "readout": "四worker和所有目标自然闭合后统一读B-A/C-A/C-B；按母来源保留相关性；负例不重抽",
        "execution_requires_separate_root_approval": True, "automatic_dispatch": False,
        "preflight": {"target": 1, "same_plan_single_hand_instances": 9 if historical else 6,
            "not_additional_cost": True, "worker0_may_reuse_verified_preflight": True,
            "preflight_only_checks_scores_forcing_legality_not_performance": True},
        "new_scores_worlds_single_hands_complete_tables_model_calls_HTTP_at_preparation": 0,
        "strength_deadline_or_release_admission": False}
    save(Path(args.output).resolve(), plan)
    print(json.dumps({"complete": True, "coverage": plan["coverage"],
        "planned_single_hand_instances": plan["planned_single_hand_instances"],
        "candidate_id": args.candidate_id, "actual_new_business_calls": 0}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate-source", required=True)
    p.add_argument("--candidate-id", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--batch", default=str(STAGE / "EXECUTION-BATCH.json"))
    p.add_argument("--source-plan", default=str(EVIDENCE / "t188-joint-score-mechanism-1/CONDITION-PLAN.json"))
    p.add_argument("--extra-targets")
    p.add_argument("--historical", choices=("included", "excluded"), default="included")
    p.add_argument("--output", required=True)
    prepare(p.parse_args())
