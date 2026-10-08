"""R16 代际 1 候选 B：条件目标路线优先的两层动作排序。

第一层只比较同一动作内的一条相容、事实完整的 ValueRoute 目标：将该路线
的四家条件结算叠加到完整当前阶段账，得到本人条件名次区间和前二边界方向。
第二层只在同一目标级别内比较规则侧已经生产的向听、公开有效牌支持和相容
合法后续弃牌。它不读取 WorldState，也不把任何支持数解释为概率。
"""


def score_stable_v2(view):
    """稳定 V2 的完整排序，用于机制证据不足时的整窗精确回退。"""
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
        elif (action.get("fact_kind") == "hand_progress" and shanten is not None
              and shanten is not True and shanten is not False and shanten >= 0):
            valid_useful = True
            support = 0.0
            if useful is None:
                valid_useful = False
            else:
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
            if (action.get("best_followup_discard") is not None
                    or action.get("replacement_draw_unknown") is not False):
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
                        if (len(other) >= 2 and other[0] in "123456789"
                                and other[-1] == suit and abs(int(other[0]) - rank) <= 2):
                            near_next = True
                if dealer != seat:
                    for meld in melds[dealer]:
                        for other in meld.get("tiles"):
                            if (len(other) >= 2 and other[0] in "123456789"
                                    and other[-1] == suit and abs(int(other[0]) - rank) <= 2):
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
        trace = {
            "basis": item.get("basis"), "base_score": base,
            "shanten_after": item.get("shanten"),
            "best_shanten_non_pass": best_shanten,
            "wealth_part": wealth_part,
            "wealth_discard_part": wealth_discard_part,
            "river_part": river_part,
            "risk_units": risk_units,
            "style_part": style_part,
            "unknown": unknown,
            "unknown_policy": "known_final_floor_minus_1" if unknown else None,
            "hu_sorting_layer": kind == "hu",
            "scope": "direct_v2_or_produced_outside_v2",
        }
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
    return {
        "status": "SCORED", "entries": final_entries,
        "reason": "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下",
    }


def finite_value(value):
    if value is None or value is True or value is False:
        return None
    number = float(value)
    if number - number != 0:
        return None
    return number


def integer_value(value, low, high):
    number = finite_value(value)
    if number is None or number != int(number):
        return None
    integer = int(number)
    if integer < low or integer > high:
        return None
    return integer


def tile_support_value(tiles):
    if tiles is None or len(tiles) == 0:
        return None
    codes = set()
    total = 0
    for tile in tiles:
        code = tile.get("code")
        amount = integer_value(tile.get("remaining_estimate"), 0, 4)
        if code is None or code is True or code is False or len(code) == 0 or amount is None or code in codes:
            return None
        codes.add(code)
        total += amount
    return total


def stage_account_values(competition):
    if competition is None:
        return None
    masks = competition.get("freshness_masks")
    values = competition.get("current_stage_scores")
    if masks is None or len(masks) != 2:
        return None
    if masks[0] != "stage_account:complete" or masks[1] != "table_account:live":
        return None
    if values is None or len(values) != 4:
        return None
    result = []
    for value in values:
        integer = integer_value(value, -1000000000, 1000000000)
        if integer is None:
            return None
        result.append(integer)
    return result


def rank_interval(values, seat):
    own = values[seat]
    greater = 0
    equal = 0
    for index in range(4):
        if index == seat:
            continue
        if values[index] > own:
            greater += 1
        elif values[index] == own:
            equal += 1
    return (1 + greater, 1 + greater + equal)


def boundary_margin(values, seat):
    ordered = sorted(values, reverse=True)
    return values[seat] - ordered[1]


def rank_relation(interval):
    if interval[1] <= 2:
        return "inside"
    if interval[0] <= 2:
        return "boundary"
    return "outside"


def goal_level(before_relation, after_relation, before_margin, after_margin):
    if after_relation == "inside":
        if before_relation == "outside":
            return (6, "cross_top_two", "条件路线从前二外跨入条件前二")
        if before_relation == "boundary":
            return (5, "resolve_top_two", "条件路线把同分边界解析为条件前二")
        return (4, "preserve_top_two", "条件路线保持条件前二")
    if after_relation == "boundary":
        if before_relation == "outside":
            return (3, "approach_top_two", "条件路线接近前二边界但仍保留同分区间")
        if before_relation == "inside":
            return (1, "weaken_to_boundary", "条件路线把条件前二压到同分边界")
        return (2, "hold_boundary", "条件路线保持条件前二边界")
    if before_relation == "inside":
        return (0, "retreat_from_top_two", "条件路线落到条件前二之外")
    if before_relation == "boundary":
        return (0, "leave_boundary", "条件路线离开条件前二边界")
    if after_margin > before_margin:
        return (1, "improve_outside_margin", "条件路线扩大前二边界差")
    return (0, "outside_no_cross", "条件路线未跨越前二边界")


def settlement_values(route, seat):
    if route is None:
        return None
    settlement = route.get("conditional_settlement")
    if settlement is None:
        return None
    delta = settlement.get("score_delta")
    if delta is None or len(delta) != 4:
        return None
    values = []
    total = 0
    for item in delta:
        number = integer_value(item, -1000000000, 1000000000)
        if number is None:
            return None
        values.append(number)
        total += number
    if total != 0:
        return None
    self_delta = integer_value(settlement.get("self_delta"), -1000000000, 1000000000)
    if self_delta is None or self_delta != values[seat]:
        return None
    fan = finite_value(settlement.get("fan"))
    if fan is None or fan <= 0:
        return None
    if settlement.get("details") is None:
        return None
    return values


def conditions_complete(route):
    conditions = route.get("conditions")
    if conditions is None:
        return False
    draw_kind = conditions.get("draw_kind")
    if draw_kind != "normal" and draw_kind != "replacement":
        return False
    meld_count = integer_value(conditions.get("meld_count"), 0, 4)
    chain_count = integer_value(conditions.get("chain_count"), 0, 1000000000)
    chain_piao = integer_value(conditions.get("chain_piao"), 0, 1000000000)
    if meld_count is None or chain_count is None or chain_piao is None or chain_piao > chain_count:
        return False
    if conditions.get("baotou") is not True and conditions.get("baotou") is not False:
        return False
    pre_draw_hand = conditions.get("pre_draw_hand")
    if pre_draw_hand is None or len(pre_draw_hand) != 13 - 3 * meld_count:
        return False
    for code in pre_draw_hand:
        if code is None or code is True or code is False or len(code) == 0:
            return False
    if chain_piao + pre_draw_hand.count("白") > 4:
        return False
    return True


def route_complete(route):
    if route is None:
        return False
    if integer_value(route.get("shanten"), 0, 0) is None:
        return False
    if route.get("support") != "conditional_witness":
        return False
    if tile_support_value(route.get("useful_tiles")) is None:
        return False
    if settlement_values(route, 0) is None and settlement_values(route, 1) is None and settlement_values(route, 2) is None and settlement_values(route, 3) is None:
        return False
    if not conditions_complete(route):
        return False
    return True


def branch_for(action, route):
    kind = action.get("action_type")
    followup = route.get("followup_discard")
    if kind != "chi" and kind != "peng":
        if followup is not None:
            return None
        shanten = integer_value(action.get("shanten_after"), -1, 13)
        if shanten is None:
            shanten = 0
        return {"followup_key": None, "shanten": shanten, "support": tile_support_value(route.get("useful_tiles")), "chain": 1}
    if followup is None:
        return None
    branches = action.get("followup_branches")
    if branches is None:
        return None
    for branch in branches:
        if branch.get("followup_discard") != followup:
            continue
        key = branch.get("followup_key")
        if key is None or len(key) <= len(followup) + 1 or key[-len(followup):] != followup:
            continue
        shanten = integer_value(branch.get("combined_shanten"), -1, 13)
        support = integer_value(branch.get("support_remaining"), 0, 136)
        if shanten is None:
            shanten = integer_value(branch.get("standard_shanten_after"), -1, 13)
        if support is None:
            support = tile_support_value(route.get("useful_tiles"))
        if shanten is None or support is None:
            continue
        return {"followup_key": key, "shanten": shanten, "support": support, "chain": 2}
    return None


def route_for(action, routes, stage_values, seat):
    if routes is None:
        return None
    before_interval = rank_interval(stage_values, seat)
    before_relation = rank_relation(before_interval)
    before_margin = boundary_margin(stage_values, seat)
    selected = None
    for route in routes:
        if not route_complete(route):
            continue
        delta = settlement_values(route, seat)
        if delta is None:
            continue
        branch = branch_for(action, route)
        if branch is None:
            continue
        after_values = []
        for index in range(4):
            after_values.append(stage_values[index] + delta[index])
        after_interval = rank_interval(after_values, seat)
        after_relation = rank_relation(after_interval)
        after_margin = boundary_margin(after_values, seat)
        level = goal_level(before_relation, after_relation, before_margin, after_margin)
        candidate = {
            "order": level[0], "priority": level[1], "reason": level[2],
            "followup_key": branch.get("followup_key"),
            "followup_discard": route.get("followup_discard"),
            "delta": delta, "rank_low": after_interval[0],
            "rank_high": after_interval[1],
            "before_margin": before_margin, "after_margin": after_margin,
            "shanten": branch.get("shanten"), "support": branch.get("support"),
            "chain": branch.get("chain"),
        }
        if selected is None:
            selected = candidate
        elif candidate.get("order") > selected.get("order"):
            selected = candidate
        elif candidate.get("order") == selected.get("order"):
            if candidate.get("rank_low") < selected.get("rank_low"):
                selected = candidate
            elif candidate.get("rank_low") == selected.get("rank_low"):
                if candidate.get("rank_high") < selected.get("rank_high"):
                    selected = candidate
                elif candidate.get("rank_high") == selected.get("rank_high"):
                    if candidate.get("after_margin") > selected.get("after_margin"):
                        selected = candidate
                    elif (candidate.get("after_margin") == selected.get("after_margin")
                          and candidate.get("support") > selected.get("support")):
                        selected = candidate
    return selected


def fallback_v2(view, stage_ready, reason):
    result = score_stable_v2(view)
    if result.get("status") != "SCORED":
        return result
    entries = []
    for entry in result.get("entries"):
        trace = {"stable_v2_trace": entry.get("trace"), "goal_target": {
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
            "reason": reason,
        }}
        entries.append({"action_key": entry.get("action_key"), "score": entry.get("score"), "trace": trace})
    return {"status": "SCORED", "entries": entries, "reason": "整窗精确回退稳定 V2：" + reason}


def score_actions(view):
    """先选条件目标路线，再以牌效/支持/相容链完成整窗排序。"""
    actions = view.get("actions")
    visible = view.get("visible_state")
    if actions is None or visible is None or len(actions) == 0:
        return {"status": "ABSTAIN", "reason": "缺少动作表或公开可见状态"}
    if view.get("schema_version") != "sitin-scoring-view/3":
        return fallback_v2(view, False, "不支持的评分视图版本")

    seat = visible.get("seat")
    if seat is None or seat is True or seat is False or seat < 0 or seat > 3:
        return fallback_v2(view, False, "我方座位不可用")
    stage_values = stage_account_values(view.get("competition"))
    if stage_values is None:
        return fallback_v2(view, False, "当前阶段完整账不可用")

    seen = set()
    rows = []
    comparable = 0
    legal_hu = False
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if key is None or kind is None or action.get("is_legal") is not True:
            return fallback_v2(view, True, "动作合法身份或键缺失")
        if key in seen:
            return fallback_v2(view, True, "动作键重复")
        seen.add(key)
        if kind not in ("discard", "chi", "peng", "gang", "hu", "pass"):
            return fallback_v2(view, True, "动作类型超出冻结枚举")
        if kind == "hu":
            legal_hu = True
        route = route_for(action, action.get("routes"), stage_values, seat)
        if route is not None:
            comparable += 1
        rows.append({"action": action, "route": route})

    if comparable < 2:
        return fallback_v2(view, True, "完整相容目标路线少于两个可比较动作")

    pending = []
    max_non_hu = None
    for row in rows:
        action = row.get("action")
        route = row.get("route")
        kind = action.get("action_type")
        if kind == "hu":
            continue
        if route is None:
            shanten = integer_value(action.get("shanten_after"), -1, 13)
            support = tile_support_value(action.get("useful_tiles"))
            if shanten is None:
                shanten = -1
            if support is None:
                support = 0
            target_order = -1
            target_priority = "no_complete_route"
            reason = "本动作没有相容且事实完整的条件路线"
            chain = 0
            delta = None
            rank_low = None
            rank_high = None
            before_margin = None
            after_margin = None
            followup_key = None
            followup_discard = None
        else:
            shanten = route.get("shanten")
            support = route.get("support")
            target_order = route.get("order")
            target_priority = route.get("priority")
            reason = route.get("reason")
            chain = route.get("chain")
            delta = route.get("delta")
            rank_low = route.get("rank_low")
            rank_high = route.get("rank_high")
            before_margin = route.get("before_margin")
            after_margin = route.get("after_margin")
            followup_key = route.get("followup_key")
            followup_discard = route.get("followup_discard")
        score = ((target_order + 1) * 1000000.0
                 + (13 - shanten) * 1000.0
                 + support + chain * 0.01)
        if max_non_hu is None or score > max_non_hu:
            max_non_hu = score
        pending.append({
            "action_key": action.get("action_key"), "score": score,
            "target_order": target_order, "target_priority": target_priority,
            "reason": reason, "shanten": shanten, "support": support,
            "chain": chain, "delta": delta, "rank_low": rank_low,
            "rank_high": rank_high, "before_margin": before_margin,
            "after_margin": after_margin, "followup_key": followup_key,
            "followup_discard": followup_discard, "action_type": kind,
        })

    hu_level = None
    if legal_hu:
        if max_non_hu is None:
            hu_level = 9000000.0
        else:
            hu_level = max_non_hu + 1000000.0

    entries = []
    for row in rows:
        action = row.get("action")
        kind = action.get("action_type")
        if kind == "hu":
            settlement = action.get("immediate_settlement")
            delta = settlement_values({"conditional_settlement": settlement}, seat) if settlement is not None else None
            rank_low = None
            rank_high = None
            before_margin = boundary_margin(stage_values, seat)
            after_margin = None
            if delta is not None:
                after_values = []
                for index in range(4):
                    after_values.append(stage_values[index] + delta[index])
                interval = rank_interval(after_values, seat)
                rank_low = interval[0]
                rank_high = interval[1]
                after_margin = boundary_margin(after_values, seat)
            trace = {
                "mechanism_version": "goal_first_conditional_route_v1",
                "secondary_layer": "legal_hu_priority",
                "goal_target": {
                    "mechanism_active": True,
                    "stage_account_ready": True,
                    "selected_followup_key": None,
                    "selected_route_followup_discard": None,
                    "conditional_score_delta": delta,
                    "conditional_rank_low": rank_low,
                    "conditional_rank_high": rank_high,
                    "boundary_margin_before": before_margin,
                    "boundary_margin_after": after_margin,
                    "target_priority": "legal_hu",
                    "fallback_exact_v2": False,
                    "reason": "保留稳定 V2 的合法胡优先纪律",
                },
            }
            entries.append({"action_key": action.get("action_key"), "score": hu_level, "trace": trace})
            continue
        item = None
        for candidate in pending:
            if candidate.get("action_key") == action.get("action_key"):
                item = candidate
                break
        trace = {
            "mechanism_version": "goal_first_conditional_route_v1",
            "secondary_layer": "rule_shanten_then_public_support_then_legal_chain",
            "secondary_shanten": item.get("shanten"),
            "secondary_public_support": item.get("support"),
            "secondary_legal_chain": item.get("chain"),
            "goal_target": {
                "mechanism_active": True,
                "stage_account_ready": True,
                "selected_followup_key": item.get("followup_key"),
                "selected_route_followup_discard": item.get("followup_discard"),
                "conditional_score_delta": item.get("delta"),
                "conditional_rank_low": item.get("rank_low"),
                "conditional_rank_high": item.get("rank_high"),
                "boundary_margin_before": item.get("before_margin"),
                "boundary_margin_after": item.get("after_margin"),
                "target_priority": item.get("target_priority"),
                "fallback_exact_v2": False,
                "reason": item.get("reason"),
            },
        }
        entries.append({"action_key": item.get("action_key"), "score": item.get("score"), "trace": trace})
    return {
        "status": "SCORED", "entries": entries,
        "reason": "先按单条相容条件路线的前二目标分层，再按规则向听、公开支持和合法后续链排序",
    }
