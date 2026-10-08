"""候选机制说明：在父代「证据分层线性评分 + 吃/碰分支相容聚合」上做唯一机制改动——牌效读数的支持枚数加成由 0.5×min(u,16)（16 截顶）换成严格单调有界饱和映射 8u/(u+16)（上界 8 分=恰一个 8 分向听步长，16 以上仍可区分），直接动作与吃/碰分支同映射；由 M1 备注+真实请求 a90eb7c7（87/79 同向听4、父代均 16 分平分）触发；其余语义逐字保留。"""

def finite_value(item):
    """数值守卫：None/布尔/非有限 → None；其余转 float。"""
    if item is None or item is True or item is False:
        return None
    value = float(item)
    if value - value != 0:
        return None
    return value

def gate_potentials(scores, seat):
    """门线势差：inside_gap=本座−第2名分数（升序下标2），outside_gap=本座−第3名分数（升序下标1）；任一座未知→None。"""
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
    """frozen_line 近似权重档位：落后追分 1.3 / 临界 1.1 / 大幅领先 0.9 / 缺账 1.0（M1 不改）。"""
    if potentials is None:
        return 1.0
    gap = potentials["inside_gap"]
    if gap < -20.0:
        return 1.3
    if gap > 60.0:
        return 0.9
    return 1.1

def facts_present(action):
    """动作是否携带任一已生产事实（未知≠0 判定的输入；analysis_failed 不算；M1 不改）。"""
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
    """动作级推进牌支持枚数之和（多种牌 remaining_estimate 合计，可>16；非概率）；任一未知→None。"""
    if tiles is None:
        return None
    total = 0.0
    for entry in tiles:
        value = finite_value(entry.get("remaining_estimate"))
        if value is None:
            return None
        total += value
    return total

def support_bonus(support):
    """M1 唯一机制改动：支持枚数 u → 加成 8u/(u+16)；严格单调、上界 8 分=一个 8 分向听步长（渐近不可达），
    16 以上仍有分辨率（87→6.7573、79→6.6526）；u<=0 → 0；None/布尔/非有限 → None（不冒充已知枚数）。"""
    if support is None or support is True or support is False:
        return None
    value = float(support)
    if value - value != 0:
        return None
    if value <= 0.0:
        return 0.0
    return 8.0 * value / (value + 16.0)

def hand_base_value(shanten, support):
    """牌效基值：已成胡 48+bonus，否则 40−8×向听+bonus；bonus=support_bonus（替换父代 0.5×min(u,16)）。"""
    bonus = support_bonus(support)
    if bonus is None:
        bonus = 0.0
    if shanten < 0.0:
        return 48.0 + bonus
    return 40.0 - 8.0 * shanten + bonus

def branch_support_value(raw):
    """分支支持枚数守卫：未知→0.0（沿用父代「不冒充已知枚数」），负值截 0；不再 16 截顶，>16 交由饱和映射区分。"""
    if raw is None or raw is True or raw is False:
        return 0.0
    value = float(raw)
    if value - value != 0:
        return 0.0
    if value < 0.0:
        return 0.0
    return value

def route_reading(route, weight):
    """单条条件路线读数：结算增益（截 0—120）×0.3×门线权重 + 支持枚数（截 16）×0.25；非概率。M1 按提案要求不改本函数。"""
    settle = route.get("conditional_settlement")
    if settle is None:
        return None
    delta = finite_value(settle.get("self_delta"))
    if delta is None:
        return None
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
    if support_total > 16.0:
        support_total = 16.0
    return {"value": gain * 0.3 * weight + 0.25 * support_total, "gain": delta}

def best_plain_route(routes, weight):
    """未对齐回退：路线表内独立取最优读数（父代语义保留）。"""
    if routes is None:
        return None
    best = None
    for route in routes:
        reading = route_reading(route, weight)
        if reading is None:
            continue
        if best is None or reading["value"] > best["value"]:
            best = reading
    return best

def claim_hand_candidates(action, branches):
    """吃/碰的分支牌效候选（不预合并不同弃牌）：每分支一项 + 动作级 shanten_after 兜底；
    分支 support_remaining 与动作级 useful_tiles 合计走同一饱和映射（M1），不再 16 截顶。"""
    candidates = []
    if branches is not None:
        for branch in branches:
            sh = branch.get("combined_shanten")
            if sh is None or sh is True or sh is False:
                continue
            shanten = float(sh)
            if shanten - shanten != 0:
                continue
            support = branch_support_value(branch.get("support_remaining"))
            candidates.append({"discard": branch.get("followup_discard"),
                               "value": hand_base_value(shanten, support),
                               "basis": branch.get("followup_key")})
    sh = action.get("shanten_after")
    if sh is not None and sh is not True and sh is not False:
        shanten = float(sh)
        if shanten - shanten == 0:
            support_total = useful_support_total(action.get("useful_tiles"))
            if support_total is None:
                support_total = 0.0
            candidates.append({"discard": action.get("best_followup_discard"),
                               "value": hand_base_value(shanten, support_total),
                               "basis": "shanten_after"})
    return candidates

def aligned_route_buckets(routes, weight, known_discards):
    """分支相容聚合（沿用父代 AV-SUB-008 修复形态）：局部列表 append + 不可变重建，每个 followup_discard 只留最优路线读数；无法归属的路线只计数。M1 不改本函数。"""
    bucket_list = []
    unmatched = 0
    if routes is not None:
        for route in routes:
            discard = route.get("followup_discard")
            if discard is None:
                unmatched += 1
                continue
            if known_discards.count(discard) == 0:
                unmatched += 1
                continue
            reading = route_reading(route, weight)
            if reading is None:
                continue
            rebuilt = []
            seen = False
            for entry in bucket_list:
                if entry["discard"] == discard:
                    seen = True
                    if reading["value"] > entry["value"]:
                        rebuilt.append({"discard": discard,
                                        "value": reading["value"],
                                        "gain": reading["gain"]})
                    else:
                        rebuilt.append(entry)
                else:
                    rebuilt.append(entry)
            if seen is False:
                rebuilt.append({"discard": discard,
                                "value": reading["value"],
                                "gain": reading["gain"]})
            bucket_list = rebuilt
    return {"buckets": bucket_list, "unmatched": unmatched}

def bucket_lookup(bucket_list, discard):
    """读取方线性查找（列表构造，无下标写入；父代语义保留）。"""
    if bucket_list is None or discard is None:
        return None
    for entry in bucket_list:
        if entry["discard"] == discard:
            return entry
    return None

def aligned_claim_reading(action, branches, weight):
    """吃/碰对齐读数：每弃牌分支取 牌效 + 同弃牌路线 bonus 的最大；未对齐路线只计数不计分（父代语义保留）。"""
    candidates = claim_hand_candidates(action, branches)
    known_discards = []
    for cand in candidates:
        discard = cand["discard"]
        if discard is not None and known_discards.count(discard) == 0:
            known_discards.append(discard)
    packed = aligned_route_buckets(action.get("routes"), weight, known_discards)
    buckets = packed["buckets"]
    best = None
    for cand in candidates:
        bonus = 0.0
        bonus_gain = None
        if cand["discard"] is not None:
            reading = bucket_lookup(buckets, cand["discard"])
            if reading is not None:
                bonus = reading["value"]
                bonus_gain = reading["gain"]
        total = cand["value"] + bonus
        if best is None or total > best["total"]:
            best = {"total": total, "hand_value": cand["value"],
                    "hand_basis": cand["basis"], "discard": cand["discard"],
                    "route_bonus": bonus, "route_gain": bonus_gain}
    return {"best": best, "unmatched": packed["unmatched"]}

def known_action_reading(action, weight):
    """已知动作三分量合成：结算 + 牌效（吃/碰走 branch_aligned_max；hand 分量用 M1 饱和映射）+ 对齐条件路线；无数值读数→None。"""
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
    branches = action.get("followup_branches")
    action_kind = action.get("action_type")
    claim_like = False
    if branches is not None and len(branches) > 0:
        claim_like = True
    if action_kind == "chi" or action_kind == "peng":
        claim_like = True
    hand_part = None
    hand_basis = "none"
    route_part = None
    route_gain = None
    aligned_discard = None
    unmatched_routes = 0
    combination = "linear_sum"
    if claim_like:
        combination = "branch_aligned_max"
        aligned = aligned_claim_reading(action, branches, weight)
        unmatched_routes = aligned["unmatched"]
        best = aligned["best"]
        if best is not None:
            hand_part = best["hand_value"]
            hand_basis = best["hand_basis"]
            aligned_discard = best["discard"]
            if best["route_bonus"] > 0.0:
                route_part = best["route_bonus"]
                route_gain = best["route_gain"]
        else:
            fallback = best_plain_route(action.get("routes"), weight)
            if fallback is not None:
                route_part = fallback["value"]
                route_gain = fallback["gain"]
                hand_basis = "no_aligned_hand_route_only"
    else:
        sh = action.get("shanten_after")
        if sh is not None and sh is not True and sh is not False:
            shanten = float(sh)
            support = useful_support_total(action.get("useful_tiles"))
            if support is None:
                support = 0.0
            hand_part = hand_base_value(shanten, support)
            hand_basis = "shanten_after"
        picked = best_plain_route(action.get("routes"), weight)
        if picked is not None:
            route_part = picked["value"]
            route_gain = picked["gain"]
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
        return {"score": total,
                "trace": {"settlement_delta": settlement_delta,
                          "settlement_part": settlement_part,
                          "hand_part": hand_part,
                          "hand_basis": hand_basis,
                          "support_map": "8u/(u+16)",
                          "route_part": route_part,
                          "route_gain": route_gain,
                          "gate_weight": weight,
                          "combination": combination,
                          "aligned_discard": aligned_discard,
                          "unmatched_routes": unmatched_routes}}
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
    unknown_value = known_floor - 1.0
    entries = []
    for item in computed:
        if item["unknown"] is False:
            entries.append({"action_key": item["key"], "score": item["score"],
                            "trace": item["trace"]})
        else:
            base_trace = item["trace"]
            merged = {"basis": base_trace["basis"],
                      "unknown_score": unknown_value,
                      "known_floor": known_floor}
            entries.append({"action_key": item["key"], "score": unknown_value,
                            "trace": merged})
    reason_text = "M1：牌效支持枚数加成用严格单调有界饱和映射 8u/(u+16)（上界 8 分=恰一个 8 分向听步长，16 以上仍可区分；直接动作与吃/碰分支同映射；未知/布尔/非有限仍按父代合同不冒充已知枚数）；frozen_line 门线近似（δ 逐动作不同，不据此声称门线移动或名次变化）；吃/碰按同一 followup_discard 分支对齐 牌效+相容路线 后取最优（局部列表构造，无下标赋值；不跨弃牌拼合，未归属路线只计数）；条件路线读数/即时结算/门线权重/未知锚定沿用父代；缺证据动作锚定为已知最低分−1.0（未知≠0）；剩余赛程不可见且未使用"
    return {"status": "SCORED", "entries": tuple(entries), "reason": reason_text}
