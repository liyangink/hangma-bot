"""R16/A：条件结算驱动的前二目标优先动作排序；信息不全时逐窗回退稳定 V2。"""


def stable_v2(view):
    """稳定 V2 的完整评分体，仅作为本程序的精确回退，不参与活动窗口的混分。"""
    actions = view.get("actions")
    visible = view.get("visible_state")
    if actions is None or visible is None or len(actions) == 0:
        return {"status": "ABSTAIN", "reason": "缺少动作表或公开可见状态"}
    seat = visible.get("seat")
    if seat is None or seat is True or seat is False or seat < 0 or seat > 3:
        return {"status": "ABSTAIN", "reason": "我方座位不可用"}
    hand = visible.get("my_hand")
    discards = visible.get("discards")
    melds = visible.get("melds")
    scores = visible.get("table_scores")
    rule_state = visible.get("rule_state")
    if hand is None or discards is None or melds is None or scores is None or rule_state is None:
        return {"status": "ABSTAIN", "reason": "基础公式所需公开状态缺失"}
    if len(discards) != 4 or len(melds) != 4 or len(scores) != 4:
        return {"status": "ABSTAIN", "reason": "四座公开状态长度不合法"}
    wealth = rule_state.get("wealth_god")
    if wealth is None:
        return {"status": "ABSTAIN", "reason": "财神牌码缺失"}
    own_meld_count = len(melds[seat])
    wealth_count = hand.count(wealth)
    drawn = visible.get("drawn_tile")
    if drawn is not None and len(hand) != 14 - 3 * own_meld_count and drawn == wealth:
        wealth_count += 1
    own_table_score = scores[seat]
    if own_table_score is None or own_table_score is True or own_table_score is False:
        return {"status": "ABSTAIN", "reason": "我方桌内积分缺失"}
    own_table_value = float(own_table_score)
    if own_table_value - own_table_value != 0:
        return {"status": "ABSTAIN", "reason": "我方桌内积分非有限"}
    table_rank = 1
    for item in scores:
        if item is None or item is True or item is False:
            return {"status": "ABSTAIN", "reason": "桌内积分缺失"}
        value = float(item)
        if value - value != 0:
            return {"status": "ABSTAIN", "reason": "桌内积分非有限"}
        if value > own_table_value:
            table_rank += 1
    dealer = visible.get("dealer_seat")
    if dealer is None or dealer is True or dealer is False or dealer < 0 or dealer > 3:
        return {"status": "ABSTAIN", "reason": "庄家座位不可用"}
    pending = []
    known = []
    best_shanten = None
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if key is None or kind is None or action.get("is_legal") is not True:
            return {"status": "ABSTAIN", "reason": "动作合法身份或键缺失"}
        direct = False
        base = None
        shanten = action.get("shanten_after")
        useful = action.get("useful_tiles")
        if kind == "hu":
            direct = True
            base = 1000.0
            if best_shanten is None or -1 < best_shanten:
                best_shanten = -1
        elif action.get("fact_kind") == "hand_progress" and shanten is not None and shanten is not True and shanten is not False and shanten >= 0:
            valid_useful = True
            support = 0.0
            for tile in useful:
                remaining = tile.get("remaining_estimate")
                if remaining is None or remaining is True or remaining is False:
                    valid_useful = False
                else:
                    amount = float(remaining)
                    if amount - amount != 0:
                        valid_useful = False
                    else:
                        support += amount
            if valid_useful:
                direct = True
                base = -100.0 * float(shanten) + round(support, 1)
                if kind != "pass" and (best_shanten is None or shanten < best_shanten):
                    best_shanten = shanten
        if kind == "pass" and direct:
            if action.get("best_followup_discard") is not None or action.get("replacement_draw_unknown") is not False:
                direct = False
                base = None
        produced = action.get("immediate_settlement") is not None
        routes = action.get("routes")
        branches = action.get("followup_branches")
        families = action.get("family_progress_entries")
        if routes is not None and len(routes) > 0:
            produced = True
        if branches is not None:
            produced = True
        if families is not None and len(families) > 0:
            produced = True
        if direct:
            pending.append({"action": action, "base": base, "basis": "direct_v2", "shanten": shanten})
            known.append(base)
        elif produced:
            pending.append({"action": action, "base": 0.0, "basis": "produced_outside_v2", "shanten": None})
            known.append(0.0)
        else:
            pending.append({"action": action, "base": None, "basis": "unknown", "shanten": None})
    if len(known) == 0:
        return {"status": "ABSTAIN", "reason": "全部动作均无已生产事实，未知不能取零分"}
    base_floor = min(known)
    entries = []
    for item in pending:
        action = item.get("action")
        key = action.get("action_key")
        kind = action.get("action_type")
        base = item.get("base")
        unknown = base is None
        total = base_floor - 1.0 if unknown else base
        retained_wealth = wealth_count
        tile_code = None
        if kind == "discard":
            tile_code = key[8:]
            if tile_code == wealth:
                retained_wealth -= 1
        wealth_part = 5.0 * retained_wealth
        total += wealth_part
        wealth_discard_part = 0.0
        river_part = 0.0
        risk_units = 0.0
        style_part = 0.0
        familiar = False
        if kind == "discard":
            if tile_code == wealth:
                wealth_discard_part = -60.0
                total += wealth_discard_part
            for river_seat in range(4):
                if river_seat != seat and discards[river_seat].count(tile_code) > 0:
                    familiar = True
            if familiar:
                river_part = 3.0
                total += river_part
            elif len(tile_code) >= 2 and tile_code[0] in "123456789" and tile_code[-1] in "wbt":
                suit = tile_code[-1]
                rank = int(tile_code[0])
                next_seat = (seat + 1) % 4
                near_next = False
                near_dealer = False
                for meld in melds[next_seat]:
                    for other in meld.get("tiles"):
                        if len(other) >= 2 and other[0] in "123456789" and other[-1] == suit and abs(int(other[0]) - rank) <= 2:
                            near_next = True
                if dealer != seat:
                    for meld in melds[dealer]:
                        for other in meld.get("tiles"):
                            if len(other) >= 2 and other[0] in "123456789" and other[-1] == suit and abs(int(other[0]) - rank) <= 2:
                                near_dealer = True
                if near_next:
                    risk_units += 1.0
                if near_dealer:
                    risk_units += 0.5
                total -= round(6.0 * risk_units, 1)
            if table_rank == 1 and familiar:
                style_part = 4.0
            elif table_rank == 4 and item.get("shanten") is not None and item.get("shanten") == best_shanten:
                style_part = 2.0
            total = round(total, 6)
            total += style_part
            total = round(total, 6)
        else:
            fixed = 0.0
            if kind == "peng":
                fixed = -6.0
            elif kind == "chi":
                fixed = -10.0
            elif kind == "gang":
                fixed = 40.0
            total += fixed
            total = round(total, 6)
        trace = {"basis": item.get("basis"), "base_score": base, "shanten_after": item.get("shanten"), "best_shanten_non_pass": best_shanten, "wealth_part": wealth_part, "wealth_discard_part": wealth_discard_part, "river_part": river_part, "risk_units": risk_units, "style_part": style_part, "unknown": unknown, "unknown_policy": "known_final_floor_minus_1" if unknown else None, "hu_sorting_layer": kind == "hu", "scope": "direct_v2_or_produced_outside_v2"}
        entries.append({"action_key": key, "action_type": kind, "score": total, "trace": trace})
    hu_level = None
    for entry in entries:
        if entry.get("trace").get("unknown") is not True and entry.get("action_type") != "hu":
            score = entry.get("score")
            if hu_level is None or score > hu_level:
                hu_level = score
    known_floor = None
    for entry in entries:
        if entry.get("trace").get("unknown") is not True:
            score = entry.get("score")
            if entry.get("action_type") == "hu" and hu_level is not None:
                score = hu_level + 1.0
            if known_floor is None or score < known_floor:
                known_floor = score
    if known_floor is None:
        return {"status": "ABSTAIN", "reason": "没有可用已知最终评分，未知不能取零分"}
    final_entries = []
    for entry in entries:
        score = entry.get("score")
        if entry.get("action_type") == "hu" and hu_level is not None:
            score = hu_level + 1.0
        if entry.get("trace").get("unknown") is True:
            score = known_floor - 1.0
        final_entries.append({"action_key": entry.get("action_key"), "score": score, "trace": entry.get("trace")})
    return {"status": "SCORED", "entries": final_entries, "reason": "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下"}


def finite_number(value):
    """读取有限公开数；无效值返回空，避免把未知伪造为零。"""
    if value is None or value is True or value is False:
        return None
    number = float(value)
    if number - number != 0 or number < -1000000000.0 or number > 1000000000.0:
        return None
    return number


def bounded_integer(value, low, high):
    """读取公开整数；区间只用于字段合同校验。"""
    number = finite_number(value)
    if number is None or number < low or number > high:
        return None
    whole = int(number)
    if number != float(whole):
        return None
    return whole


def support_total(tiles):
    """按路线本身的公开未见枚数求和；不是概率。"""
    if tiles is None or len(tiles) == 0:
        return None
    seen = set()
    total = 0.0
    for tile in tiles:
        code = tile.get("code")
        remaining = bounded_integer(tile.get("remaining_estimate"), 0, 4)
        if code is None or code is True or code is False or code in seen or remaining is None:
            return None
        seen.add(code)
        total += float(remaining)
    return total


def stage_account(view, seat):
    """只接受完整且已组合的当前阶段账，拒绝补账、重复加账或陈旧账。"""
    competition = view.get("competition")
    if competition is None:
        return None
    masks = competition.get("freshness_masks")
    if masks is None or len(masks) != 2:
        return None
    if masks[0] != "stage_account:complete" or masks[1] != "table_account:live":
        return None
    completed = competition.get("stage_scores")
    table = competition.get("table_scores")
    current = competition.get("current_stage_scores")
    if completed is None or table is None or current is None:
        return None
    if len(completed) != 4 or len(table) != 4 or len(current) != 4:
        return None
    values = []
    for index in range(4):
        done = finite_number(completed[index])
        live = finite_number(table[index])
        total = finite_number(current[index])
        if done is None or live is None or total is None or done + live != total:
            return None
        values.append(total)
    if seat < 0 or seat > 3:
        return None
    return tuple(values)


def rank_interval(values, seat):
    """返回同分未知裁决下的条件名次区间和相对前三门线的差。"""
    own = values[seat]
    lower = 1
    upper = 0
    for value in values:
        if value > own:
            lower += 1
        if value >= own:
            upper += 1
    ordered = sorted(values, reverse=True)
    margin = own - ordered[2]
    return (lower, upper, margin)


def conditions_record(conditions, action_type):
    """验证路线的完整条件身份，并返回只作词典序末级使用的动作链事实。"""
    if conditions is None:
        return None
    draw_kind = conditions.get("draw_kind")
    if action_type == "gang":
        if draw_kind != "replacement":
            return None
    elif draw_kind != "normal":
        return None
    hand = conditions.get("pre_draw_hand")
    meld_count = bounded_integer(conditions.get("meld_count"), 0, 4)
    chain_count = bounded_integer(conditions.get("chain_count"), 0, 64)
    chain_piao = bounded_integer(conditions.get("chain_piao"), 0, 64)
    baotou = conditions.get("baotou")
    if hand is None or meld_count is None or chain_count is None or chain_piao is None:
        return None
    if baotou is not True and baotou is not False:
        return None
    if len(hand) != 13 - 3 * meld_count or chain_piao > chain_count:
        return None
    for code in hand:
        if code is None or code is True or code is False or len(code) == 0:
            return None
    return (draw_kind, chain_count, chain_piao, int(baotou))


def matching_followup_key(action, followup):
    """只把吃碰路线绑定到同一 followup_discard 的唯一已生产后继。"""
    kind = action.get("action_type")
    if kind != "chi" and kind != "peng":
        if followup is not None:
            return None
        return ""
    if followup is None:
        return None
    branches = action.get("followup_branches")
    if branches is None:
        return None
    matched = None
    matches = 0
    for branch in branches:
        if branch.get("followup_discard") == followup:
            key = branch.get("followup_key")
            if key is None or key is True or key is False or len(key) == 0:
                return None
            matched = key
            matches += 1
    if matches != 1:
        return None
    return matched


def route_atom(route, action, seat, before):
    """把一条完整、相容的路线保留为不可拆分的条件目标见证。"""
    if route.get("support") != "conditional_witness":
        return None
    shanten = bounded_integer(route.get("shanten"), 0, 13)
    support = support_total(route.get("useful_tiles"))
    conditions = conditions_record(route.get("conditions"), action.get("action_type"))
    if shanten is None or support is None or conditions is None:
        return None
    if action.get("action_type") == "gang" and action.get("replacement_draw_unknown") is not False:
        return None
    followup = route.get("followup_discard")
    followup_key = matching_followup_key(action, followup)
    if followup_key is None:
        return None
    settlement = route.get("conditional_settlement")
    if settlement is None:
        return None
    raw_delta = settlement.get("score_delta")
    self_delta = finite_number(settlement.get("self_delta"))
    if raw_delta is None or len(raw_delta) != 4 or self_delta is None:
        return None
    delta = []
    for item in raw_delta:
        value = finite_number(item)
        if value is None:
            return None
        delta.append(value)
    if self_delta != delta[seat] or sum(delta) != 0.0:
        return None
    after = []
    for index in range(4):
        after.append(before[index] + delta[index])
    ranks = rank_interval(tuple(after), seat)
    before_ranks = rank_interval(before, seat)
    rank_low = ranks[0]
    rank_high = ranks[1]
    after_margin = ranks[2]
    before_margin = before_ranks[2]
    secure = 1 if rank_high <= 2 else 0
    possible = 1 if rank_low <= 2 else 0
    crossing = 1 if before_margin < 0.0 and after_margin >= 0.0 else 0
    target_priority = (1, secure, possible, crossing, -rank_high, -rank_low,
                       after_margin, after_margin - before_margin)
    if secure == 1:
        goal_target = "conditional_top2_secure"
    elif possible == 1:
        goal_target = "conditional_top2_tie_interval"
    else:
        goal_target = "conditional_outside_top2"
    rule_priority = (-shanten, support, conditions[1], conditions[2], conditions[3])
    return {
        "target_priority": target_priority,
        "rule_priority": rule_priority,
        "goal_target": goal_target,
        "selected_followup_key": None if followup_key == "" else followup_key,
        "selected_route_followup_discard": followup,
        "conditional_score_delta": tuple(delta),
        "conditional_rank_low": rank_low,
        "conditional_rank_high": rank_high,
        "boundary_margin_before": before_margin,
        "boundary_margin_after": after_margin,
        "route_shanten": shanten,
        "route_support": support,
        "route_draw_kind": conditions[0],
        "route_chain_count": conditions[1],
        "route_chain_piao": conditions[2],
        "route_baotou": conditions[3],
    }


def atom_better(left, right):
    """先按条件目标，再按该同一路线的规则读数，最后按稳定后继键。"""
    if right is None:
        return True
    if left.get("target_priority") != right.get("target_priority"):
        return left.get("target_priority") > right.get("target_priority")
    if left.get("rule_priority") != right.get("rule_priority"):
        return left.get("rule_priority") > right.get("rule_priority")
    left_key = left.get("selected_followup_key")
    right_key = right.get("selected_followup_key")
    if left_key is None:
        left_key = ""
    if right_key is None:
        right_key = ""
    return left_key < right_key


def direct_rule_priority(action, visible):
    """显式已知空路线的规则末级；缺行动链或牌效即不可比较。"""
    kind = action.get("action_type")
    chain = bounded_integer(visible.get("rule_state").get("chain_count"), 0, 64)
    piao_value = visible.get("chain_piao")
    if chain is None:
        return None
    if chain == 0 and piao_value is None:
        piao = 0
    else:
        piao = bounded_integer(piao_value, 0, 64)
    if piao is None or piao > chain:
        return None
    if kind == "chi" or kind == "peng":
        branches = action.get("followup_branches")
        if branches is None:
            return None
        best = None
        for branch in branches:
            shanten = bounded_integer(branch.get("combined_shanten"), 0, 13)
            support = bounded_integer(branch.get("support_remaining"), 0, 136)
            followup = branch.get("followup_discard")
            key = branch.get("followup_key")
            if shanten is None or support is None or followup is None or key is None:
                return None
            candidate = (-shanten, float(support), chain, piao, key)
            if best is None or candidate > best:
                best = candidate
        if best is None:
            return None
        return best
    if kind == "pass" and (action.get("best_followup_discard") is not None or action.get("replacement_draw_unknown") is not False):
        return None
    if kind == "gang" and action.get("replacement_draw_unknown") is not False:
        return None
    if action.get("fact_kind") != "hand_progress":
        return None
    shanten = bounded_integer(action.get("shanten_after"), 0, 13)
    support = support_total(action.get("useful_tiles"))
    if shanten is None or support is None:
        return None
    return (-shanten, support, chain, piao, "")


def goal_record(action, visible, seat, before):
    """生成一个动作的单一路线见证；任何不完整路线让整窗回退。"""
    if action.get("value_coverage") != "complete":
        return None
    issues = action.get("value_issues")
    if issues is None or len(issues) != 0:
        return None
    routes = action.get("routes")
    if routes is None:
        return None
    if len(routes) == 0:
        rule = direct_rule_priority(action, visible)
        if rule is None:
            return None
        return {
            "action_key": action.get("action_key"),
            "target_priority": (0, 0, 0, 0, 0, 0, 0.0, 0.0),
            "rule_priority": rule,
            "goal_target": "closed_empty_conditional_route_set",
            "selected_followup_key": None,
            "selected_route_followup_discard": None,
            "conditional_score_delta": None,
            "conditional_rank_low": None,
            "conditional_rank_high": None,
            "boundary_margin_before": None,
            "boundary_margin_after": None,
            "route_shanten": None,
            "route_support": None,
            "route_draw_kind": None,
            "route_chain_count": None,
            "route_chain_piao": None,
            "route_baotou": None,
        }
    best = None
    for route in routes:
        atom = route_atom(route, action, seat, before)
        if atom is None:
            return None
        if atom_better(atom, best):
            best = atom
    if best is None:
        return None
    return {
        "action_key": action.get("action_key"),
        "target_priority": best.get("target_priority"),
        "rule_priority": best.get("rule_priority"),
        "goal_target": best.get("goal_target"),
        "selected_followup_key": best.get("selected_followup_key"),
        "selected_route_followup_discard": best.get("selected_route_followup_discard"),
        "conditional_score_delta": best.get("conditional_score_delta"),
        "conditional_rank_low": best.get("conditional_rank_low"),
        "conditional_rank_high": best.get("conditional_rank_high"),
        "boundary_margin_before": best.get("boundary_margin_before"),
        "boundary_margin_after": best.get("boundary_margin_after"),
        "route_shanten": best.get("route_shanten"),
        "route_support": best.get("route_support"),
        "route_draw_kind": best.get("route_draw_kind"),
        "route_chain_count": best.get("route_chain_count"),
        "route_chain_piao": best.get("route_chain_piao"),
        "route_baotou": best.get("route_baotou"),
    }


def record_better(left, right):
    """全动作词典序：条件目标、路线/规则读数、稳定动作键。"""
    if right is None:
        return True
    if left.get("target_priority") != right.get("target_priority"):
        return left.get("target_priority") > right.get("target_priority")
    if left.get("rule_priority") != right.get("rule_priority"):
        return left.get("rule_priority") > right.get("rule_priority")
    return left.get("action_key") < right.get("action_key")


def fallback_result(baseline, stage_ready, reason):
    """保留 V2 的每个数值评分与动作顺序，仅补充本机制的回退审计字段。"""
    entries = []
    for entry in baseline.get("entries"):
        trace = {
            "mechanism_active": False,
            "stage_account_ready": stage_ready,
            "selected_followup_key": None,
            "selected_route_followup_discard": None,
            "conditional_score_delta": None,
            "conditional_rank_low": None,
            "conditional_rank_high": None,
            "boundary_margin_before": None,
            "boundary_margin_after": None,
            "target_priority": None,
            "fallback_exact_v2": True,
            "goal_target": "stable_v2_fallback",
            "reason": reason,
            "stable_v2_trace": entry.get("trace"),
        }
        entries.append({"action_key": entry.get("action_key"), "score": entry.get("score"), "trace": trace})
    return {"status": "SCORED", "entries": entries, "reason": reason}


def score_actions(view):
    """按完整阶段账下的条件前二目标排序；缺投影、未知或胡窗口均逐窗回退 V2。"""
    baseline = stable_v2(view)
    if baseline.get("status") != "SCORED":
        return baseline
    visible = view.get("visible_state")
    seat = bounded_integer(visible.get("seat"), 0, 3)
    if seat is None:
        return fallback_result(baseline, False, "目标机制座位不可用，精确回退稳定V2")
    before = stage_account(view, seat)
    if before is None:
        return fallback_result(baseline, False, "完整当前阶段账或freshness_masks不可用，精确回退稳定V2")
    actions = view.get("actions")
    for action in actions:
        if action.get("action_type") == "hu" and action.get("is_legal") is True:
            return fallback_result(baseline, True, "保留合法胡优先，精确回退稳定V2")
    records = []
    for action in actions:
        record = goal_record(action, visible, seat, before)
        if record is None:
            return fallback_result(baseline, True, "路线覆盖、条件身份、后继相容性或规则末级不可比，精确回退稳定V2")
        records.append(record)
    ordered = []
    used = set()
    for order in range(len(records)):
        best = None
        for record in records:
            if record.get("action_key") in used:
                continue
            if record_better(record, best):
                best = record
        if best is None:
            return fallback_result(baseline, True, "动作词典序未形成完整排列，精确回退稳定V2")
        used.add(best.get("action_key"))
        ordered.append(best)
    entries = []
    for order in range(len(ordered)):
        record = ordered[order]
        trace = {
            "mechanism_active": True,
            "stage_account_ready": True,
            "selected_followup_key": record.get("selected_followup_key"),
            "selected_route_followup_discard": record.get("selected_route_followup_discard"),
            "conditional_score_delta": record.get("conditional_score_delta"),
            "conditional_rank_low": record.get("conditional_rank_low"),
            "conditional_rank_high": record.get("conditional_rank_high"),
            "boundary_margin_before": record.get("boundary_margin_before"),
            "boundary_margin_after": record.get("boundary_margin_after"),
            "target_priority": record.get("target_priority"),
            "fallback_exact_v2": False,
            "goal_target": record.get("goal_target"),
            "reason": "条件前二目标、路线向听、公开支持与条件动作链的词典序",
            "route_shanten": record.get("route_shanten"),
            "route_support": record.get("route_support"),
            "route_draw_kind": record.get("route_draw_kind"),
            "route_chain_count": record.get("route_chain_count"),
            "route_chain_piao": record.get("route_chain_piao"),
            "route_baotou": record.get("route_baotou"),
            "rule_priority": record.get("rule_priority"),
            "route_combination": "single_compatible_conditional_route",
        }
        entries.append({"action_key": record.get("action_key"), "score": float(len(ordered) - order), "trace": trace})
    return {"status": "SCORED", "entries": entries, "reason": "活动窗口按条件目标优先完整排序"}
