"""route_value_seed：路线价值——牌效基础叠加 family_progress 与有界结算因子（非期望积分）。"""

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
UNKNOWN_SHANTEN_PENALTY = 4.0
PROGRESS_BONUS = {"ADVANCE": 2.0, "SAME": 0.0, "RETREAT": -2.0, "CLOSE": -1.0, "UNKNOWN": 0.0}
IMMEDIATE_FAN_WEIGHT = 4.0
ROUTE_FAN_WEIGHT = 0.5
DELTA_WEIGHT = 0.0625
MAX_DELTA = 64
UNKNOWN_FIELD = "combined_shanten"


def num_or_none(branch, key):
    value = branch.get(key)
    if value is None:
        return None
    if value is True or value is False:
        return None
    if value < 0:
        return None
    return value


def fan_scale(fan):
    """有界 log 界缩放：fan 每达到 2/4/8/16/32 各记 1，封顶 5。"""
    marks = 0.0
    if fan >= 2:
        marks = marks + 1.0
    if fan >= 4:
        marks = marks + 1.0
    if fan >= 8:
        marks = marks + 1.0
    if fan >= 16:
        marks = marks + 1.0
    if fan >= 32:
        marks = marks + 1.0
    return marks


def best_branch(branches):
    best_shanten = None
    best_support = 0.0
    best_key = None
    for branch in branches:
        shanten = num_or_none(branch, "combined_shanten")
        if shanten is None:
            continue
        support = num_or_none(branch, "support_remaining")
        if support is None:
            support = 0.0
        if best_shanten is None or shanten < best_shanten:
            best_shanten = shanten
            best_support = support
            best_key = branch.get("followup_key")
    return (best_shanten, best_support, best_key)


def route_fan_best(branches):
    best = 0.0
    for branch in branches:
        fan = num_or_none(branch, "fan")
        if fan is not None and fan > best:
            best = fan
    return best


def settlement_factor(action):
    settle = action.get("immediate_settlement")
    factor = 0.0
    fan = 0.0
    if settle is not None:
        fan = settle.get("fan")
        if fan is None or fan < 0:
            fan = 0.0
        factor = factor + fan_scale(fan) * IMMEDIATE_FAN_WEIGHT
        delta = settle.get("self_delta")
        if delta is not None and delta > 0:
            if delta > MAX_DELTA:
                delta = MAX_DELTA
            factor = factor + delta * DELTA_WEIGHT
    return (factor, fan)


def score_actions(view):
    actions = view["actions"]
    entries = []
    for action in actions:
        branches = action.get("followup_branches")
        best = (None, 0.0, None)
        if branches is not None:
            best = best_branch(branches)
        shanten = best[0]
        support = best[1]
        key = best[2]
        basis = "route_value"
        if shanten is None:
            basis = "route_value_unknown_shanten"
            base = 0.0 - SHANTEN_WEIGHT * UNKNOWN_SHANTEN_PENALTY
        else:
            base = 0.0 - SHANTEN_WEIGHT * shanten + SUPPORT_WEIGHT * support
        progress = action.get("family_progress")
        if progress is None:
            progress = "UNKNOWN"
        bonus = PROGRESS_BONUS.get(progress)
        if bonus is None:
            bonus = 0.0
        settle = settlement_factor(action)
        route_fan = 0.0
        if branches is not None:
            route_fan = route_fan_best(branches)
        score = base + bonus + settle[0] + fan_scale(route_fan) * ROUTE_FAN_WEIGHT
        trace = {"basis": basis, "combined_shanten": shanten, "support_remaining": support, "progress": progress, "immediate_fan": settle[1], "route_fan": route_fan, "note": "fan 因子为 log 界缩放，非期望积分"}
        if key is not None:
            entry = {"action_key": action["action_key"], "score": score, "trace": {"basis": basis, "combined_shanten": shanten, "support_remaining": support, "progress": progress, "immediate_fan": settle[1], "route_fan": route_fan, "followup_key": key, "note": "fan 因子为 log 界缩放，非期望积分"}}
        else:
            entry = {"action_key": action["action_key"], "score": score, "trace": trace}
        entries.append(entry)
    return {"status": "SCORED", "entries": entries, "reason": None}
