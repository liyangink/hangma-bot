"""R18 三财保财条件代理边界；稳定 V2 是完整回退。"""

def score_actions(view):
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
    overlay_name = "three_wealth_keep_proxy_boundary/v1"
    overlay_required_ratio = 1.25
    overlay_best_key = None
    overlay_best_proxy = None
    overlay_immediate_hu = None
    overlay_actual_ratio = None
    overlay_triggered = False
    overlay_degrade_reason = "目标机会窗口不成立"
    overlay_unknown_pool = None
    if rule_state.get("baotou") is True and wealth_count == 3 and hu_level is not None:
        overlay_degrade_reason = "立即胡结算事实不完整"
        for action in actions:
            if action.get("is_legal") is True and action.get("action_type") == "hu":
                settlement = action.get("immediate_settlement")
                if settlement is not None:
                    delta = settlement.get("score_delta")
                    if delta is not None and len(delta) == 4:
                        amount = delta[seat]
                        if amount is not None and amount is not True and amount is not False:
                            value = float(amount)
                            if value - value == 0 and value > 0.0:
                                overlay_immediate_hu = value
        remaining_count = visible.get("remaining_tile_count")
        hand_counts = visible.get("hand_counts")
        if remaining_count is not None and remaining_count is not True and remaining_count is not False and hand_counts is not None and len(hand_counts) == 4:
            pool = float(remaining_count)
            pool_ok = pool - pool == 0 and pool >= 0.0
            for other_seat in range(4):
                if other_seat != seat:
                    count = hand_counts[other_seat]
                    if count is None or count is True or count is False:
                        pool_ok = False
                    else:
                        count_value = float(count)
                        if count_value - count_value != 0 or count_value < 0.0:
                            pool_ok = False
                        else:
                            pool += count_value
            if pool_ok and pool > 0.0:
                overlay_unknown_pool = pool
        if overlay_immediate_hu is not None and overlay_unknown_pool is not None:
            overlay_degrade_reason = "没有完整且满足家族转移的目标弃牌"
            for action in actions:
                key = action.get("action_key")
                kind = action.get("action_type")
                if kind != "discard" or key is None:
                    continue
                tile_code = key[8:]
                target_shape = tile_code != wealth
                family_ok = False
                families = action.get("family_progress_entries")
                if families is not None:
                    for family in families:
                        if family.get("family") == "baotou" and family.get("route_status") == "witnessed" and family.get("progress") in ("same", "advance"):
                            family_ok = True
                facts_ok = target_shape and family_ok
                if action.get("value_coverage") != "complete":
                    facts_ok = False
                issues = action.get("value_issues")
                if issues is None or len(issues) != 0:
                    facts_ok = False
                routes = action.get("routes")
                if routes is None or len(routes) == 0:
                    facts_ok = False
                numerator = 0.0
                seen_codes = []
                if facts_ok:
                    for route in routes:
                        route_ok = route.get("followup_discard") is None
                        route_shanten = route.get("shanten")
                        if route_shanten is None or route_shanten is True or route_shanten is False or route_shanten != 0:
                            route_ok = False
                        if route.get("support") != "conditional_witness":
                            route_ok = False
                        conditional = route.get("conditional_settlement")
                        route_value = None
                        if conditional is not None:
                            route_delta = conditional.get("score_delta")
                            if route_delta is not None and len(route_delta) == 4:
                                route_amount = route_delta[seat]
                                if route_amount is not None and route_amount is not True and route_amount is not False:
                                    converted = float(route_amount)
                                    if converted - converted == 0 and converted >= 0.0:
                                        route_value = converted
                        if route_value is None:
                            route_ok = False
                        useful_tiles = route.get("useful_tiles")
                        if useful_tiles is None or len(useful_tiles) == 0:
                            route_ok = False
                        if route_ok:
                            for useful in useful_tiles:
                                code = useful.get("code")
                                estimate = useful.get("remaining_estimate")
                                if code is None or code in seen_codes or estimate is None or estimate is True or estimate is False:
                                    route_ok = False
                                else:
                                    estimate_value = float(estimate)
                                    if estimate_value - estimate_value != 0 or estimate_value < 0.0 or estimate_value > 4.0:
                                        route_ok = False
                                    else:
                                        seen_codes.append(code)
                                        numerator += route_value * estimate_value
                        if not route_ok:
                            facts_ok = False
                            break
                if facts_ok:
                    proxy = numerator / overlay_unknown_pool
                    if overlay_best_proxy is None or proxy > overlay_best_proxy or (proxy == overlay_best_proxy and key < overlay_best_key):
                        overlay_best_proxy = proxy
                        overlay_best_key = key
            if overlay_best_proxy is not None:
                overlay_actual_ratio = overlay_best_proxy / overlay_immediate_hu
                overlay_degrade_reason = "条件代理优势未达到预登记风险缓冲"
                if overlay_actual_ratio >= overlay_required_ratio:
                    overlay_triggered = True
                    overlay_degrade_reason = "触发"
    final_entries = []
    for entry in entries:
        score = entry.get("score")
        if entry.get("action_type") == "hu" and hu_level is not None:
            score = hu_level + 1.0
        if entry.get("trace").get("unknown") is True:
            score = known_floor - 1.0
        v2_score = score
        if overlay_triggered and entry.get("action_key") == overlay_best_key:
            score = hu_level + 2.0
        trace = entry.get("trace")
        if overlay_best_key is not None and entry.get("action_key") == overlay_best_key:
            trace = {"basis": trace.get("basis"), "base_score": trace.get("base_score"), "shanten_after": trace.get("shanten_after"), "best_shanten_non_pass": trace.get("best_shanten_non_pass"), "wealth_part": trace.get("wealth_part"), "wealth_discard_part": trace.get("wealth_discard_part"), "river_part": trace.get("river_part"), "risk_units": trace.get("risk_units"), "style_part": trace.get("style_part"), "unknown": trace.get("unknown"), "unknown_policy": trace.get("unknown_policy"), "hu_sorting_layer": trace.get("hu_sorting_layer"), "scope": trace.get("scope"), "r18_opportunity_overlay": {"structure": overlay_name, "triggered": overlay_triggered, "wealth_count": wealth_count, "immediate_hu_value": overlay_immediate_hu, "continue_proxy": overlay_best_proxy, "proxy_unknown_pool": overlay_unknown_pool, "required_ratio": overlay_required_ratio, "actual_ratio": overlay_actual_ratio, "score_delta": score - v2_score, "degrade_reason": overlay_degrade_reason, "limitation": "仅下一次本人自摸立即胡的条件代理，不是完整牌局期望；未建模他家先胡、鸣牌和轮转生存"}}
        final_entries.append({"action_key": entry.get("action_key"), "score": score, "trace": trace})
    reason = "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下"
    if overlay_triggered:
        reason = reason + "；R18机会边界触发，目标弃牌以胡层上方1分排序"
    return {"status": "SCORED", "entries": final_entries, "reason": reason}
