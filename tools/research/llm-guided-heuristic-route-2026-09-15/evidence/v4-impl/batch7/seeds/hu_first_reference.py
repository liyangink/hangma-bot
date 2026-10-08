"""hu_first_reference：立即胡优先对照——合法 Hu 恒最高分，其余按牌效种子评分。"""

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
HU_BONUS = 1000000.0
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
        return {"basis": "hu_first_efficiency", "combined_shanten": shanten, "support_remaining": support}
    return {"basis": "hu_first_efficiency", "combined_shanten": shanten, "support_remaining": support, "followup_key": key}


def min_score(entries):
    lowest = None
    for entry in entries:
        value = entry["score"]
        if value is None:
            continue
        if lowest is None or value < lowest:
            lowest = value
    return lowest


def score_actions(view):
    actions = view["actions"]
    entries = []
    hu_entries = []
    for action in actions:
        if action["action_type"] == "hu" and action.get("is_legal") is True:
            trace = {"basis": "hu_first_reference", "legal_hu": True}
            hu_entries.append({"action_key": action["action_key"], "score": HU_BONUS, "trace": trace})
            continue
        branches = action.get("followup_branches")
        best = None
        if branches is not None:
            best = best_branch(branches)
        if best is None:
            key = action["action_key"]
            anchor_entry = {"action_key": key, "score": None, "trace": {"basis": "unknown_field_basis", "field": UNKNOWN_FIELD}}
            entries.append(anchor_entry)
            continue
        shanten = best[0]
        support = best[1]
        branch_key = best[2]
        score = 0.0 - SHANTEN_WEIGHT * shanten + SUPPORT_WEIGHT * support
        entries.append({"action_key": action["action_key"], "score": score, "trace": make_trace(shanten, support, branch_key)})
    if min_score(entries) is None:
        anchor = -1.0
    else:
        anchor = min_score(entries) - 1.0
    results = []
    for entry in entries:
        if entry["score"] is None:
            trace = {"basis": "unknown_field_basis", "field": UNKNOWN_FIELD, "anchor": anchor}
            results.append({"action_key": entry["action_key"], "score": anchor, "trace": trace})
        else:
            results.append(entry)
    for entry in hu_entries:
        results.append(entry)
    return {"status": "SCORED", "entries": results, "reason": None}
