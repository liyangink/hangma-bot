"""dev-parent-hold-v1：路线节奏（route-pace）——按分支最优向听与支撑余量排序，无分支事实的动作按动作族基线补齐。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/slim/package/materials'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

PACE_SHANTEN_WEIGHT = 3.0
PACE_SUPPORT_WEIGHT = 0.5
BASELINE_DISCARD = 2.0
BASELINE_PASS = 1.0
BASELINE_OTHER = 0.5


def branch_number(branch, key):
    value = branch.get(key)
    if value is None:
        return None
    if value is True or value is False:
        return None
    if value < 0:
        return None
    return value


def best_branch(branches):
    best_shanten = None
    best_support = 0.0
    best_key = None
    for branch in branches:
        shanten = branch_number(branch, "combined_shanten")
        if shanten is None:
            continue
        support = branch_number(branch, "support_remaining")
        if support is None:
            support = 0.0
        if best_shanten is None or shanten < best_shanten:
            best_shanten = shanten
            best_support = support
            best_key = branch.get("followup_key")
    if best_shanten is None:
        return None
    return (best_shanten, best_support, best_key)


def family_baseline(action_type):
    if action_type == "discard":
        return BASELINE_DISCARD
    if action_type == "pass":
        return BASELINE_PASS
    return BASELINE_OTHER


def pace_entry(action):
    branches = action.get("followup_branches")
    if branches is None or len(branches) == 0:
        return None
    best = best_branch(branches)
    if best is None:
        return None
    score = 0.0 - PACE_SHANTEN_WEIGHT * best[0] + PACE_SUPPORT_WEIGHT * best[1]
    trace = {"basis": "route_pace", "followup_key": best[2], "combined_shanten": best[0], "support_remaining": best[1]}
    return {"action_key": action["action_key"], "score": score, "trace": trace}


def score_actions(view):
    entries = []
    for action in view["actions"]:
        entry = pace_entry(action)
        if entry is None:
            action_type = action.get("action_type")
            score = family_baseline(action_type)
            trace = {"basis": "family_baseline", "action_type": action_type}
            entry = {"action_key": action["action_key"], "score": score, "trace": trace}
        entries.append(entry)
    return {"status": "SCORED", "entries": entries, "reason": None}
