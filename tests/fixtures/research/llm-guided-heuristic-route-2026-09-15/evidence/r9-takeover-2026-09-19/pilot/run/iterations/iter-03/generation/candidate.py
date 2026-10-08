"""候选机制说明：分支再校准——吃/碰 followup_branches 牌效刻度改为 5 分/向听 + 1.0×支持枚数（上限 16），结算/路线分量、frozen_line 权重档与「缺证据锚定已知最低分−1.0（未知≠0）」全部保持父代口径。"""

SUPPORT_CAP = 16.0
DIRECT_STEP = 8.0
DIRECT_SUPPORT = 0.5
BRANCH_STEP = 5.0
BRANCH_SUPPORT = 1.0
UNKNOWN_MARGIN = 1.0

def finite_value(item):
    """数值守卫：None/布尔/非有限 → None；其余转 float。"""
    if item is None or item is True or item is False:
        return None
    value = float(item)
    if value - value != 0:
        return None
    return value

def gate_potentials(scores, seat):
    """门线势差（唯一口径）：inside_gap=本座−第2名分数（升序下标2），outside_gap=本座−第3名分数（升序下标1）；任一座未知→None。"""
    if scores is None:
        return None
    if seat is None or seat is True or seat is False:
        return None
    if seat < 0 or seat > 3:
        return None
    if len(scores) != 4:
        return None
    values = []
    for item in scores:
        value = finite_value(item)
        if value is None:
            return None
        values.append(value)
    ordered = sorted(values)
    own = values[seat]
    return {"inside_line": ordered[2], "outside_line": ordered[1],
            "inside_gap": own - ordered[2], "outside_gap": own - ordered[1]}

def settlement_weight(potentials):
    """frozen_line 近似下的结算权重档位（本代不改）：落后追分 1.3 / 临界 1.1 / 大幅领先 0.9 / 缺账 1.0。"""
    if potentials is None:
        return 1.0
    gap = potentials["inside_gap"]
    if gap < -20.0:
        return 1.3
    if gap > 60.0:
        return 0.9
    return 1.1

def facts_present(action):
    """动作是否携带任一已生产事实（未知≠0 判定的输入；analysis_failed 不算）。"""
    if action.get("immediate_settlement") is not None:
        return True
    route_list = action.get("routes")
    if route_list is not None and len(route_list) > 0:
        return True
    branch_list = action.get("followup_branches")
    if branch_list is not None and len(branch_list) > 0:
        return True
    family_entries = action.get("family_progress_entries")
    if family_entries is not None and len(family_entries) > 0:
        return True
    kind = action.get("fact_kind")
    if kind == "hand_progress" or kind == "win" or kind == "not_applicable":
        return True
    return False

def useful_support_total(tiles):
    """动作级推进牌支持枚数之和（remaining_estimate 为未见枚数估计，非概率）；任一未知→None。"""
    if tiles is None:
        return None
    total = 0.0
    for entry in tiles:
        value = finite_value(entry.get("remaining_estimate"))
        if value is None:
            return None
        total += value
    return total

def best_branch_reading(branches):
    """本代唯一修订点：吃碰后逐分支评估改为 5 分/向听 + 1.0×支持枚数（上限 16，已成胡分支 48+1.0×支持）；不预合并不同弃牌；支持未知记 0 加成，不冒充已知枚数。"""
    best_value = None
    best_key = None
    for branch in branches:
        sh = branch.get("combined_shanten")
        if sh is None or sh is True or sh is False:
            continue
        shanten = float(sh)
        raw = branch.get("support_remaining")
        if raw is None or raw is True or raw is False:
            support = 0.0
        else:
            support = float(raw)
        if support > SUPPORT_CAP:
            support = SUPPORT_CAP
        if shanten < 0.0:
            value = 48.0 + BRANCH_SUPPORT * support
        else:
            value = 40.0 - BRANCH_STEP * shanten + BRANCH_SUPPORT * support
        if best_value is None or value > best_value:
            best_value = value
            best_key = branch.get("followup_key")
    return {"value": best_value, "key": best_key}

def best_route_reading(routes, weight):
    """条件见证路线读数（本代不改）：条件结算增益（截 120）×0.3×门线权重 + 支持枚数加成（截 16）×0.25；非概率。"""
    best_value = None
    best_gain = None
    for route in routes:
        settle = route.get("conditional_settlement")
        if settle is None:
            continue
        delta = finite_value(settle.get("self_delta"))
        if delta is None:
            continue
        gain = delta
        if gain < 0.0:
            gain = 0.0
        if gain > 120.0:
            gain = 120.0
        support_total = 0.0
        tiles = route.get("useful_tiles")
        if tiles is not None:
            for entry in tiles:
                value = finite_value(entry.get("remaining_estimate"))
                if value is not None:
                    support_total += value
        if support_total > SUPPORT_CAP:
            support_total = SUPPORT_CAP
        value = gain * 0.3 * weight + 0.25 * support_total
        if best_value is None or value > best_value:
            best_value = value
            best_gain = delta
    return {"value": best_value, "gain": best_gain}

def known_action_reading(action, weight):
    """已知动作三分量合成（直接弃牌/结算/路线保持父代口径，仅分支读数换新刻度）；无数值读数→None。"""
    settlement_delta = None
    settlement_part = 0.0
    settle = action.get("immediate_settlement")
    if settle is not None:
        delta = finite_value(settle.get("self_delta"))
        if delta is not None:
            part = delta * weight
            if delta > 0.0:
                part = part + 50.0
            settlement_delta = delta
            settlement_part = part
    hand_part = None
    hand_basis = "none"
    sh = action.get("shanten_after")
    if sh is not None and sh is not True and sh is not False:
        shanten = float(sh)
        support = useful_support_total(action.get("useful_tiles"))
        if support is None:
            support = 0.0
        if support > SUPPORT_CAP:
            support = SUPPORT_CAP
        if shanten < 0.0:
            hand_part = 48.0 + DIRECT_SUPPORT * support
        else:
            hand_part = 40.0 - DIRECT_STEP * shanten + DIRECT_SUPPORT * support
        hand_basis = "shanten_after"
    branch_list = action.get("followup_branches")
    if branch_list is not None and len(branch_list) > 0:
        picked = best_branch_reading(branch_list)
        if picked["value"] is not None:
            if hand_part is None or picked["value"] > hand_part:
                hand_part = picked["value"]
                hand_basis = picked["key"]
    route_part = None
    route_gain = None
    route_list = action.get("routes")
    if route_list is not None and len(route_list) > 0:
        route_reading = best_route_reading(route_list, weight)
        if route_reading["value"] is not None:
            route_part = route_reading["value"]
            route_gain = route_reading["gain"]
    total = 0.0
    produced = False
    if settlement_delta is not None:
        total += settlement_part
        produced = True
    if hand_part is not None:
        total += hand_part
        produced = True
    if route_part is not None:
        total += route_part
        produced = True
    if produced:
        return {"score": total, "trace": {"settlement_delta": settlement_delta,
                                          "settlement_part": settlement_part,
                                          "hand_part": hand_part,
                                          "hand_basis": hand_basis,
                                          "route_part": route_part,
                                          "route_gain": route_gain,
                                          "gate_weight": weight,
                                          "combination": "linear_sum_branch_rescaled"}}
    kind = action.get("fact_kind")
    if kind == "not_applicable":
        return {"score": 0.0, "trace": {"basis": "not_applicable_known_neutral",
                                        "gate_weight": weight}}
    if kind == "win":
        return {"score": 50.0, "trace": {"basis": "win_without_settlement_numbers"}}
    return None

def score_actions(view):
    """按同一动作窗口的只读可见事实，为全部合法动作评分。"""
    actions = view["actions"]
    if actions is None or len(actions) == 0:
        return {"status": "ABSTAIN", "reason": "动作表为空或缺失：无可评分对象",
                "entries": ()}
    visible = view["visible_state"]
    if visible is None:
        return {"status": "ABSTAIN", "reason": "visible_state 缺失：无法锚定座位",
                "entries": ()}
    seat = visible["seat"]
    competition = view["competition"]
    potentials = None
    if competition is not None:
        potentials = gate_potentials(competition.get("current_stage_scores"), seat)
    weight = settlement_weight(potentials)
    computed = []
    known_floor = None
    for action in actions:
        key = action.get("action_key")
        if facts_present(action):
            reading = known_action_reading(action, weight)
            if reading is None:
                computed.append({"key": key, "unknown": True, "score": None,
                                 "trace": {"basis": "facts_without_numeric_reading"}})
            else:
                score = reading["score"]
                computed.append({"key": key, "unknown": False, "score": score,
                                 "trace": reading["trace"]})
                if known_floor is None or score < known_floor:
                    known_floor = score
        else:
            computed.append({"key": key, "unknown": True, "score": None,
                             "trace": {"basis": "no_produced_facts"}})
    if known_floor is None:
        return {"status": "ABSTAIN",
                "reason": "窗口内没有任何动作携带已生产数值事实：未知不得取 0，只能整批弃权",
                "entries": ()}
    unknown_value = known_floor - UNKNOWN_MARGIN
    entries = []
    for item in computed:
        if item["unknown"] is False:
            entries.append({"action_key": item["key"], "score": item["score"],
                            "trace": item["trace"]})
        else:
            base_trace = item["trace"]
            merged = {"basis": base_trace["basis"],
                      "unknown_facts": True,
                      "unknown_policy": "known_floor_minus_margin",
                      "unknown_score": unknown_value,
                      "known_floor": known_floor}
            entries.append({"action_key": item["key"], "score": unknown_value,
                            "trace": merged})
    reason_text = "本代唯一改动：吃/碰 followup_branches 牌效刻度=5 分/向听+1.0×支持枚数（上限16，支持未知记0不冒充枚数），直接弃牌/结算/条件路线与 frozen_line 权重档保持父代（δ 逐动作不同，不声称门线移动或名次变化）；缺证据动作锚定已知最低分-1.0（未知≠0）；合法 Hu 与继续同池数值比较；剩余赛程不可见且未使用"
    return {"status": "SCORED", "entries": tuple(entries), "reason": reason_text}
