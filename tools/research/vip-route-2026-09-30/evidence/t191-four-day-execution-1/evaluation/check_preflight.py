"""首目标真实预检只核完整评分、B首手干预和合法动作；不汇总或打印积分。"""

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
import fcntl
from pathlib import Path

from abc_support import *
from close_abc import verify_scores


def main(args):
    """预检进程自然退出后验签小收据，供同计划worker复用，不另买9次续打。"""
    plan_path, output = Path(args.plan).resolve(), Path(args.output).resolve()
    plan = read(plan_path)
    index = plan["preflight"]["target"]
    directory = output / f"target-{index:03d}"
    target, start, closed = plan["targets"][index - 1], read(directory / "START.json"), read(directory / "CLOSURE.json")
    require(args.process_exit_code == 0 and unchanged(plan) and start["plan_pin"] == pin(plan_path)
        and start["target"] == closed["target"] == target and closed["complete"]
        and closed["source_stable"] and closed["failure"] is None, "真实首目标预检尚未完整闭合")
    with resource_slot_paths(OLD, 4)[(index - 1) % 4].open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    audit = verify_scores(directory, closed, plan, verify_settlement=False)
    require(closed["counts"]["single_hand_dispatched"] == closed["counts"]["single_hand_completed"]
        == plan["preflight"]["same_plan_single_hand_instances"], "真实预检单局费用不同")
    save(Path(args.verified_output).resolve(), {"schema": "t191-abc-preflight-verified/1", "complete": True,
        "source_stable": True, "resources_released": True, "target": index,
        "target_closure_pin": pin(directory / "CLOSURE.json"), "plan_pin": pin(plan_path),
        "candidate_identity": plan["arms_sources"]["child"]["identity"],
        "process_exit_code": args.process_exit_code, "audit": audit, "counts": closed["counts"],
        "performance_score_fields_accessed_or_aggregated": False, "not_additional_cost": True,
        "strength_deadline_or_release_admission": False})
    print({"complete": True, "actual_score_calls": audit["actual_score_calls"],
        "single_hand_instances": closed["counts"]["single_hand_dispatched"], "performance_scores_printed": False})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--process-exit-code", type=int, required=True)
    p.add_argument("--verified-output", required=True)
    main(p.parse_args())
