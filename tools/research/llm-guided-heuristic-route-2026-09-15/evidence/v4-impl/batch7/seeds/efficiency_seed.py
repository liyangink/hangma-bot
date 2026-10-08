"""efficiency_seed：牌效优先——followup 分支 combined_shanten 最小 + support_remaining 加权。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch7/seeds'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

SHANTEN_WEIGHT = 3.0
SUPPORT_WEIGHT = 0.5
UNKNOWN_FIELD = "combined_shanten"


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


def make_trace(shanten, support, key):
    if key is None:
        return {"basis": "efficiency", "combined_shanten": shanten, "support_remaining": support}
    return {"basis": "efficiency", "combined_shanten": shanten, "support_remaining": support, "followup_key": key}


def known_entries(actions):
    entries = []
    for action in actions:
        branches = action.get("followup_branches")
        if branches is None:
            continue
        best = best_branch(branches)
        if best is None:
            continue
        shanten = best[0]
        support = best[1]
        key = best[2]
        score = 0.0 - SHANTEN_WEIGHT * shanten + SUPPORT_WEIGHT * support
        entries.append({"action_key": action["action_key"], "score": score, "trace": make_trace(shanten, support, key)})
    return entries


def has_entry(entries, key):
    for entry in entries:
        if entry["action_key"] == key:
            return True
    return False


def min_score(entries):
    lowest = None
    for entry in entries:
        value = entry["score"]
        if lowest is None or value < lowest:
            lowest = value
    return lowest


def score_actions(view):
    actions = view["actions"]
    entries = known_entries(actions)
    if len(entries) == 0:
        results = []
        for action in actions:
            trace = {"basis": "unknown_field_basis", "field": UNKNOWN_FIELD}
            results.append({"action_key": action["action_key"], "score": 0.0, "trace": trace})
        return {"status": "SCORED", "entries": results, "reason": None}
    anchor = min_score(entries) - 1.0
    for action in actions:
        key = action["action_key"]
        if has_entry(entries, key):
            continue
        trace = {"basis": "unknown_field_basis", "field": UNKNOWN_FIELD, "anchor": anchor}
        entries.append({"action_key": key, "score": anchor, "trace": trace})
    return {"status": "SCORED", "entries": entries, "reason": None}
