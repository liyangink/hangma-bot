"""route_value_seed：路线价值——牌效基础叠加 family_progress 与有界结算因子（非期望积分）。"""

SHANTEN_WEIGHT = 3.0
SUPPORT_WEIGHT = 0.5
UNKNOWN_SHANTEN_PENALTY = 4.0
IMMEDIATE_FAN_WEIGHT = 4.0
ROUTE_FAN_WEIGHT = 0.5
DELTA_WEIGHT = 0.0625
MAX_DELTA = 64
UNKNOWN_FIELD = "combined_shanten"


def progress_bonus(progress):
    """进展加分查表（R1 执行器 /2 禁止模块级 dict 常量，改为纯函数）。"""
    if progress == "ADVANCE":
        return 2.0
    if progress == "RETREAT":
        return -2.0
    if progress == "CLOSE":
        return -1.0
    return 0.0


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


def route_fan_best(routes):
    """R2/S2 修正：条件路线番从真实 ValueRoute.conditional_settlement.fan 读取。"""
    best = 0.0
    for route in routes:
        settle = route.get("conditional_settlement")
        if settle is None:
            continue
        fan = settle.get("fan")
        if fan is None or fan is True or fan is False:
            continue
        if fan < 0:
            continue
        if fan > best:
            best = fan
    return best


def action_shanten(action):
    value = action.get("shanten_after")
    if value is None:
        return None
    if value is True or value is False:
        return None
    if value < -1:
        return None
    return value


def support_from_tiles(tiles):
    if tiles is None:
        return None
    total = 0.0
    for tile in tiles:
        remaining = tile.get("remaining_estimate")
        if remaining is None or remaining is True or remaining is False:
            return None
        total = total + remaining
    return total


def action_basis(action):
    branches = action.get("followup_branches")
    if branches is not None and len(branches) > 0:
        best = best_branch(branches)
        if best is not None:
            return (best[0], best[1], best[2], "followup_branch")
    shanten = action_shanten(action)
    if shanten is None:
        return None
    support = support_from_tiles(action.get("useful_tiles"))
    if support is None:
        support = 0.0
    return (shanten, support, None, "action_facts")


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
        basis = action_basis(action)
        shanten = None
        support = 0.0
        key = None
        source = "unknown"
        if basis is not None:
            shanten = basis[0]
            support = basis[1]
            key = basis[2]
            source = basis[3]
        basis_name = "route_value"
        if shanten is None:
            basis_name = "route_value_unknown_shanten"
            base = 0.0 - SHANTEN_WEIGHT * UNKNOWN_SHANTEN_PENALTY
        else:
            base = 0.0 - SHANTEN_WEIGHT * shanten + SUPPORT_WEIGHT * support
        progress = action.get("family_progress")
        if progress is None:
            progress = "UNKNOWN"
        bonus = progress_bonus(progress)
        settle = settlement_factor(action)
        route_fan = route_fan_best(action.get("routes"))
        score = base + bonus + settle[0] + fan_scale(route_fan) * ROUTE_FAN_WEIGHT
        trace = {"basis": basis_name, "fact_source": source, "combined_shanten": shanten, "support_remaining": support, "progress": progress, "immediate_fan": settle[1], "route_fan": route_fan, "note": "fan 因子为 log 界缩放，非期望积分；条件路线番取自 conditional_settlement"}
        if key is not None:
            entry = {"action_key": action["action_key"], "score": score, "trace": {"basis": basis_name, "fact_source": source, "combined_shanten": shanten, "support_remaining": support, "progress": progress, "immediate_fan": settle[1], "route_fan": route_fan, "followup_key": key, "note": "fan 因子为 log 界缩放，非期望积分；条件路线番取自 conditional_settlement"}}
        else:
            entry = {"action_key": action["action_key"], "score": score, "trace": trace}
        entries.append(entry)
    return {"status": "SCORED", "entries": entries, "reason": None}
