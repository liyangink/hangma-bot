"""候选机制说明：默认 V2 基础排序、胡排序层与严格未知锚定的可审计种子。"""

def score_stable_v2(view):
    """按同一动作窗口的只读可见事实，为全部合法动作评分。"""
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


def integer_value(value, low, high):
    """只验证投影数值，未知不补零。"""
    if value is None or value is True or value is False:
        return None
    number = float(value)
    if number - number != 0 or number != int(number):
        return None
    number = int(number)
    if number < low or number > high:
        return None
    return number


def support_value(tiles):
    """公开支持张数；空集合为已知零，None 为未知，不解释为概率。"""
    if tiles is None:
        return None
    codes = set()
    amount = 0
    for tile in tiles:
        code = tile.get("code")
        count = integer_value(tile.get("remaining_estimate"), 0, 4)
        if code is None or len(code) == 0 or code in codes or count is None:
            return None
        codes.add(code)
        amount += count
    return amount


def stage_values(competition):
    """读取座位 0—3 当前阶段合计，不累计第二遍桌内积分。"""
    if competition is None:
        return None
    masks = competition.get("freshness_masks")
    scores = competition.get("current_stage_scores")
    if masks is None or len(masks) != 2 or masks[0] != "stage_account:complete" or masks[1] != "table_account:live":
        return None
    if scores is None or len(scores) != 4:
        return None
    values = []
    for score in scores:
        value = integer_value(score, -1000000000, 1000000000)
        if value is None:
            return None
        values.append(value)
    return values


def rank_facts(values, seat):
    """只做阶段目标数学；同分保留名次区间，不猜官方同分裁决。"""
    low = 1
    high = 1
    for index in range(4):
        if index != seat:
            if values[index] > values[seat]:
                low += 1
            if values[index] >= values[seat]:
                high += 1
    margin = values[seat] - sorted(values, reverse=True)[1]
    relation = 0
    if high <= 2:
        relation = 2
    elif low <= 2:
        relation = 1
    return (high, margin, relation)


def conditional_goal(route, values, seat):
    """消费规则给定条件和四家净变分，不计算牌型、番数或支付。"""
    if route.get("support") != "conditional_witness" or integer_value(route.get("shanten"), 0, 0) is None:
        return None
    tiles = route.get("useful_tiles")
    if tiles is None or len(tiles) == 0 or support_value(tiles) is None:
        return None
    conditions = route.get("conditions")
    settlement = route.get("conditional_settlement")
    if conditions is None or settlement is None:
        return None
    if conditions.get("draw_kind") != "normal" and conditions.get("draw_kind") != "replacement":
        return None
    for name in ("meld_count", "chain_count", "chain_piao"):
        if integer_value(conditions.get(name), 0, 1000000000) is None:
            return None
    if conditions.get("baotou") is not True and conditions.get("baotou") is not False:
        return None
    hand = conditions.get("pre_draw_hand")
    if hand is None or len(hand) == 0:
        return None
    for tile in hand:
        if tile is None or len(tile) == 0:
            return None
    deltas = settlement.get("score_delta")
    if deltas is None or len(deltas) != 4 or settlement.get("details") is None:
        return None
    if integer_value(settlement.get("fan"), 1, 1000000000) is None:
        return None
    after = []
    total = 0
    for index in range(4):
        delta = integer_value(deltas[index], -1000000000, 1000000000)
        if delta is None:
            return None
        total += delta
        after.append(values[index] + delta)
    if total != 0 or integer_value(settlement.get("self_delta"), -1000000000, 1000000000) != deltas[seat]:
        return None
    return rank_facts(after, seat)


def action_set(action, values, seat):
    """构造全部后继的目标包络；任一路线缺证据则整个动作未知。"""
    if action.get("value_coverage") != "complete":
        return None
    routes = action.get("routes")
    if routes is None or len(routes) == 0:
        return None
    paths = []
    kind = action.get("action_type")
    if kind == "chi" or kind == "peng":
        branches = action.get("followup_branches")
        if branches is None or len(branches) == 0:
            return None
        followups = set()
        for branch in branches:
            discard = branch.get("followup_discard")
            key = branch.get("followup_key")
            if discard is None or len(discard) == 0 or key != action.get("action_key") + "#" + discard or discard in followups:
                return None
            followups.add(discard)
            shanten = integer_value(branch.get("combined_shanten"), -1, 13)
            support = integer_value(branch.get("support_remaining"), 0, 136)
            paths.append({"followup": discard, "key": key, "shanten": shanten, "support": support, "count": 0})
    else:
        shanten = integer_value(action.get("shanten_after"), -1, 13)
        support = support_value(action.get("useful_tiles"))
        paths.append({"followup": None, "key": action.get("action_key"), "shanten": shanten, "support": support, "count": 0})
    worst_rank = 0
    min_margin = None
    worst_relation = 2
    codes = set()
    seen_pairs = set()
    route_rows = []
    route_followups = []
    before = rank_facts(values, seat)
    degraded = False
    for route in routes:
        followup = route.get("followup_discard")
        path_index = None
        for index in range(len(paths)):
            if paths[index].get("followup") == followup:
                path_index = index
        if path_index is None:
            return None
        goal = conditional_goal(route, values, seat)
        if goal is None:
            return None
        path = paths[path_index]
        route_followups.append(path.get("key"))
        route_codes = []
        for tile in route.get("useful_tiles"):
            code = tile.get("code")
            pair = (path.get("key"), code)
            if pair in seen_pairs:
                return None
            seen_pairs.add(pair)
            codes.add(code)
            route_codes.append(code)
        worst_rank = max(worst_rank, goal[0])
        min_margin = goal[1] if min_margin is None else min(min_margin, goal[1])
        worst_relation = min(worst_relation, goal[2])
        if goal[2] < before[2] or goal[0] > before[0] or goal[1] < before[1]:
            degraded = True
        # 路线身份由后继键与有效牌码决定，顺序变化不改变关键见证。
        for code in sorted(route_codes):
            route_rows.append((path.get("key") + ":" + code, goal[0], goal[1], goal[2]))
    feasibility_known = True
    for path in paths:
        if route_followups.count(path.get("key")) == 0:
            return None
        if path.get("shanten") is None or path.get("support") is None:
            feasibility_known = False
    critical = []
    for row in sorted(route_rows):
        if row[1] == worst_rank or row[2] == min_margin or row[3] == worst_relation:
            critical.append(row[0])
    return {"paths": paths, "feasibility_known": feasibility_known,
            "route_count": len(routes), "distinct_followups": sorted([path.get("key") for path in paths]),
            "worst_rank_high": worst_rank, "min_boundary_margin": min_margin,
            "worst_goal_relation": worst_relation, "distinct_codes": len(codes),
            "degraded": degraded, "critical_routes": critical}


def feasibility(challenger, baseline):
    """所有挑战后继均不得被任一基准后继严格支配，不拼接分支牌效。"""
    if not challenger.get("feasibility_known") or not baseline.get("feasibility_known"):
        return "unknown"
    for challenge in challenger.get("paths"):
        for anchor in baseline.get("paths"):
            if anchor.get("shanten") <= challenge.get("shanten") and anchor.get("support") >= challenge.get("support"):
                if anchor.get("shanten") < challenge.get("shanten") or anchor.get("support") > challenge.get("support"):
                    return "strictly_dominated"
    return "all_paths_not_strictly_dominated"


def dominates(challenger, baseline):
    """两维目标包络严格支配；已知目标关系退化一票否决。"""
    if challenger.get("degraded") or challenger.get("worst_goal_relation") < baseline.get("worst_goal_relation"):
        return False
    rank = challenger.get("worst_rank_high")
    margin = challenger.get("min_boundary_margin")
    other_rank = baseline.get("worst_rank_high")
    other_margin = baseline.get("min_boundary_margin")
    return rank <= other_rank and margin >= other_margin and (rank < other_rank or margin > other_margin)


def finish(stable, ordered, summaries, reasons, active, reason, promoted):
    """保留未晋升原分数；晋升仅用独立序号编码，不与目标值相加。"""
    baseline_key = ordered[0].get("action_key")
    promoted_keys = [item[3] for item in promoted]
    entries = []
    for entry in stable.get("entries"):
        key = entry.get("action_key")
        summary = summaries.get(key)
        own_reason = reasons.get(key, reason)
        anchor = summaries.get(baseline_key)
        check = "not_evaluated"
        if summary is not None and anchor is not None:
            check = feasibility(summary, anchor)
        goal = {"mechanism_active": active, "fallback_exact_v2": not active,
                "reason": own_reason, "baseline_action": baseline_key,
                "promoted_action": promoted_keys[0] if active else None,
                "feasibility": check,
                "route_count": summary.get("route_count") if summary is not None else 0,
                "distinct_followups": summary.get("distinct_followups") if summary is not None else [],
                "worst_rank_high": summary.get("worst_rank_high") if summary is not None else None,
                "min_boundary_margin": summary.get("min_boundary_margin") if summary is not None else None,
                "worst_goal_relation": summary.get("worst_goal_relation") if summary is not None else None,
                "critical_routes": summary.get("critical_routes")[:3] if summary is not None else [],
                "critical_route_count": len(summary.get("critical_routes")) if summary is not None else 0,
                "distinct_effective_codes": summary.get("distinct_codes") if summary is not None else 0,
                "known_goal_degradation": summary.get("degraded") if summary is not None else None,
                "path_feasibility": [path.get("key") + "|s=" + f'{path.get("shanten")}' + "|u=" + f'{path.get("support")}' for path in summary.get("paths")] if summary is not None else []}
        score = entry.get("score")
        if active and key in promoted_keys:
            # 基准分仅提供大于全部原分的排序位置，目标值绝不进入数值分。
            score = ordered[0].get("score") + len(promoted_keys) - promoted_keys.index(key)
        entries.append({"action_key": key, "score": score,
                        "trace": {"goal_set": goal, "stable_v2_trace": entry.get("trace")}})
    return {"status": "SCORED", "entries": entries, "reason": reason}


def score_actions(view):
    """可行域约束的稳健目标晋升；缺证据整窗精确回退稳定 V2。"""
    stable = score_stable_v2(view)
    if stable.get("status") != "SCORED":
        return stable
    ordered = sorted(stable.get("entries"), key=lambda item: (-item.get("score"), item.get("action_key")))
    summaries = {}
    reasons = []
    for action in view.get("actions"):
        if action.get("action_type") == "hu":
            return finish(stable, ordered, summaries, dict(reasons), False, "legal_hu_exact_v2", [])
    values = stage_values(view.get("competition"))
    if values is None:
        return finish(stable, ordered, summaries, dict(reasons), False, "stage_account_unknown", [])
    seat = view.get("visible_state").get("seat")
    summary_pairs = []
    for action in view.get("actions"):
        key = action.get("action_key")
        summary = action_set(action, values, seat)
        if summary is None:
            return finish(stable, ordered, {}, {}, False, "goal_set_unknown_or_incompatible", [])
        summary_pairs.append((key, summary))
    summaries = dict(summary_pairs)
    baseline = summaries.get(ordered[0].get("action_key"))
    if not baseline.get("feasibility_known"):
        return finish(stable, ordered, summaries, dict(reasons), False, "baseline_feasibility_unknown", [])
    promoted = []
    for index in range(len(ordered)):
        key = ordered[index].get("action_key")
        summary = summaries.get(key)
        check = feasibility(summary, baseline)
        if index == 0:
            reasons.append((key, "stable_v2_baseline"))
        elif check != "all_paths_not_strictly_dominated":
            reasons.append((key, check))
        elif dominates(summary, baseline):
            promoted.append((summary.get("worst_rank_high"), -summary.get("min_boundary_margin"), -summary.get("distinct_codes"), key, index))
            reasons.append((key, "strict_robust_goal_promotion"))
        else:
            reasons.append((key, "no_strict_goal_improvement_or_known_degradation"))
    # 最后一键明确使用 V2 原次序，而不是动作字母顺序。
    promoted = sorted(promoted, key=lambda item: (item[0], item[1], item[2], item[4]))
    if len(promoted) == 0:
        return finish(stable, ordered, summaries, dict(reasons), False, "no_strict_feasible_promotion", [])
    return finish(stable, ordered, summaries, dict(reasons), True, "feasibility_constrained_goal_promotion", promoted)
