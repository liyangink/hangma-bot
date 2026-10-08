"""dev-parent-hold-v2：牌效-直投影混合（pace-mix）——分支事实优先，动作级直投影兜底；无事实动作锚定在全部已知评分之下。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/materials'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

MIX_SHANTEN_WEIGHT = 3.0
MIX_SUPPORT_WEIGHT = 0.5
MIX_TILE_SUPPORT_WEIGHT = 0.25
UNKNOWN_ANCHOR_MARGIN = 1.0


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


def direct_shanten(action):
    value = action.get("shanten_after")
    if value is not None and value is not True and value is not False and value >= 0:
        return value
    value = action.get("standard_shanten_after")
    if value is not None and value is not True and value is not False and value >= 0:
        return value
    value = action.get("seven_pairs_shanten_after")
    if value is not None and value is not True and value is not False and value >= 0:
        return value
    return None


def tile_support(tiles):
    if tiles is None:
        return None
    total = 0.0
    for tile in tiles:
        remaining = tile.get("remaining_estimate")
        if remaining is None or remaining is True or remaining is False:
            return None
        total = total + remaining
    return total


def mix_basis(action):
    branches = action.get("followup_branches")
    if branches is not None and len(branches) > 0:
        best = best_branch(branches)
        if best is not None:
            return (best[0], best[1], "followup_branch")
    shanten = direct_shanten(action)
    if shanten is None:
        return None
    support = tile_support(action.get("useful_tiles"))
    if support is None:
        support = 0.0
    return (shanten, support, "action_facts")


def basis_score(basis):
    if basis[2] == "followup_branch":
        return 0.0 - MIX_SHANTEN_WEIGHT * basis[0] + MIX_SUPPORT_WEIGHT * basis[1]
    return 0.0 - MIX_SHANTEN_WEIGHT * basis[0] + MIX_TILE_SUPPORT_WEIGHT * basis[1]


def min_known(entries):
    lowest = None
    for entry in entries:
        value = entry["score"]
        if lowest is None or value < lowest:
            lowest = value
    return lowest


def has_entry(entries, key):
    for entry in entries:
        if entry["action_key"] == key:
            return True
    return False


def score_actions(view):
    entries = []
    for action in view["actions"]:
        basis = mix_basis(action)
        if basis is None:
            continue
        score = basis_score(basis)
        trace = {"basis": "pace_mix", "fact_source": basis[2], "combined_shanten": basis[0], "support_remaining": basis[1]}
        entries.append({"action_key": action["action_key"], "score": score, "trace": trace})
    anchor = None
    if len(entries) > 0:
        anchor = min_known(entries) - UNKNOWN_ANCHOR_MARGIN
    for action in view["actions"]:
        key = action["action_key"]
        if has_entry(entries, key):
            continue
        score = anchor
        if score is None:
            score = 0.0
        trace = {"basis": "unknown_anchor", "anchor": score}
        entries.append({"action_key": key, "score": score, "trace": trace})
    return {"status": "SCORED", "entries": entries, "reason": None}
