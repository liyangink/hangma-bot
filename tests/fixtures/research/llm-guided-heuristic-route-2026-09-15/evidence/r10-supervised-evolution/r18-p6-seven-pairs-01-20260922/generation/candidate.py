"""R18 P5 覆盖 + 七对门清无损支配；稳定 P5 是完整回退。"""

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
    if wealth_count == 4:
        overlay_name = "four_wealth_piao_proxy_boundary/v1"
        overlay_required_ratio = 1.50
    elif wealth_count == 3:
        overlay_name = "three_wealth_piao_cf_supported/v1"
        overlay_required_ratio = 1.75
    else:
        overlay_name = None
        overlay_required_ratio = None
    overlay_best_key = None
    overlay_best_proxy = None
    overlay_immediate_hu = None
    overlay_actual_ratio = None
    overlay_triggered = False
    overlay_degrade_reason = "目标机会窗口不成立"
    overlay_unknown_pool = None
    if overlay_name is not None and rule_state.get("baotou") is True and hu_level is not None:
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
                target_shape = tile_code == wealth
                family_ok = False
                families = action.get("family_progress_entries")
                if families is not None:
                    for family in families:
                        if family.get("family") == "chain" and family.get("route_status") == "witnessed" and family.get("progress") == "advance":
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
    canonical_codes = (
        "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
        "1b", "2b", "3b", "4b", "5b", "6b", "7b", "8b", "9b",
        "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t",
        "东", "南", "西", "北", "中", "发", "白",
    )
    dominance_hu_value = None
    for action in actions:
        if action.get("is_legal") is True and action.get("action_type") == "hu":
            settlement = action.get("immediate_settlement")
            if settlement is not None:
                delta = settlement.get("score_delta")
                if delta is not None and len(delta) == 4:
                    amount = delta[seat]
                    if amount is not None and amount is not True and amount is not False:
                        value = float(amount)
                        if value - value == 0:
                            dominance_hu_value = value
    dominance_best_key = None
    dominance_best_value = None
    dominance_checks = None
    if dominance_hu_value is not None:
        for action in actions:
            key = action.get("action_key")
            added_gang = action.get("action_type") == "gang" and key is not None and key[:11] == "gang:added:"
            coverage_complete = action.get("value_coverage") == "complete"
            no_value_issues = action.get("value_issues") is not None and len(action.get("value_issues")) == 0
            replacement_unknown = action.get("replacement_draw_unknown") is True
            standard_shanten_zero = action.get("standard_shanten_after") is not True and action.get("standard_shanten_after") is not False and action.get("standard_shanten_after") == 0
            standard = action.get("standard_useful_tiles")
            standard_seen = []
            publicly_possible = []
            standard_ok = standard is not None and len(standard) == len(canonical_codes)
            if standard_ok:
                for useful in standard:
                    code = useful.get("code")
                    estimate = useful.get("remaining_estimate")
                    if code not in canonical_codes or code in standard_seen or estimate is None or estimate is True or estimate is False:
                        standard_ok = False
                    else:
                        remaining = float(estimate)
                        if remaining - remaining != 0 or remaining < 0.0 or remaining > 4.0:
                            standard_ok = False
                        else:
                            standard_seen.append(code)
                            if remaining > 0.0:
                                publicly_possible.append(code)
            standard_codes_all_34 = standard_ok and len(standard_seen) == len(canonical_codes)
            routes = action.get("routes")
            route = None
            if routes is not None and len(routes) == 1:
                route = routes[0]
            unique_route = route is not None
            conditions = None if route is None else route.get("conditions")
            replacement_route = conditions is not None and conditions.get("draw_kind") == "replacement"
            route_shanten = None if route is None else route.get("shanten")
            route_shanten_zero = route_shanten is not True and route_shanten is not False and route_shanten == 0
            route_no_followup_discard = route is not None and route.get("followup_discard") is None
            route_seen = []
            route_ok = route is not None and route.get("useful_tiles") is not None and len(route.get("useful_tiles")) > 0
            if route_ok:
                for useful in route.get("useful_tiles"):
                    code = useful.get("code")
                    estimate = useful.get("remaining_estimate")
                    if code not in canonical_codes or code in route_seen or estimate is None or estimate is True or estimate is False:
                        route_ok = False
                    else:
                        remaining = float(estimate)
                        if remaining - remaining != 0 or remaining <= 0.0 or remaining > 4.0:
                            route_ok = False
                        else:
                            route_seen.append(code)
            route_covers_publicly_possible = route_ok and sorted(route_seen) == sorted(publicly_possible)
            route_value = None
            conditional = None if route is None else route.get("conditional_settlement")
            if conditional is not None:
                delta = conditional.get("score_delta")
                if delta is not None and len(delta) == 4:
                    amount = delta[seat]
                    if amount is not None and amount is not True and amount is not False:
                        value = float(amount)
                        if value - value == 0:
                            route_value = value
            route_score_strictly_higher = route_value is not None and route_value > dominance_hu_value
            checks = {
                "added_gang": added_gang,
                "coverage_complete": coverage_complete,
                "no_value_issues": no_value_issues,
                "replacement_unknown": replacement_unknown,
                "standard_shanten_zero": standard_shanten_zero,
                "standard_codes_all_34": standard_codes_all_34,
                "unique_route": unique_route,
                "replacement_route": replacement_route,
                "route_shanten_zero": route_shanten_zero,
                "route_no_followup_discard": route_no_followup_discard,
                "route_covers_publicly_possible": route_covers_publicly_possible,
                "route_score_strictly_higher": route_score_strictly_higher,
            }
            predicate = True
            for passed in checks.values():
                if passed is not True:
                    predicate = False
            if predicate and (dominance_best_value is None or route_value > dominance_best_value or (route_value == dominance_best_value and key < dominance_best_key)):
                dominance_best_key = key
                dominance_best_value = route_value
                dominance_checks = checks
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
        before_dominance_score = score
        if dominance_best_key is not None and entry.get("action_key") == dominance_best_key:
            score = hu_level + 1.5
        trace = entry.get("trace")
        if overlay_best_key is not None and entry.get("action_key") == overlay_best_key:
            trace = {"basis": trace.get("basis"), "base_score": trace.get("base_score"), "shanten_after": trace.get("shanten_after"), "best_shanten_non_pass": trace.get("best_shanten_non_pass"), "wealth_part": trace.get("wealth_part"), "wealth_discard_part": trace.get("wealth_discard_part"), "river_part": trace.get("river_part"), "risk_units": trace.get("risk_units"), "style_part": trace.get("style_part"), "unknown": trace.get("unknown"), "unknown_policy": trace.get("unknown_policy"), "hu_sorting_layer": trace.get("hu_sorting_layer"), "scope": trace.get("scope"), "r18_opportunity_overlay": {"structure": overlay_name, "triggered": overlay_triggered, "wealth_count": wealth_count, "immediate_hu_value": overlay_immediate_hu, "continue_proxy": overlay_best_proxy, "proxy_unknown_pool": overlay_unknown_pool, "required_ratio": overlay_required_ratio, "actual_ratio": overlay_actual_ratio, "score_delta": score - v2_score, "degrade_reason": overlay_degrade_reason, "limitation": "仅下一次本人自摸立即胡的条件代理，不是完整牌局期望；未建模他家先胡、鸣牌和轮转生存"}}
        if dominance_best_key is not None and entry.get("action_key") == dominance_best_key:
            trace = {"basis": trace.get("basis"), "base_score": trace.get("base_score"), "shanten_after": trace.get("shanten_after"), "best_shanten_non_pass": trace.get("best_shanten_non_pass"), "wealth_part": trace.get("wealth_part"), "wealth_discard_part": trace.get("wealth_discard_part"), "river_part": trace.get("river_part"), "risk_units": trace.get("risk_units"), "style_part": trace.get("style_part"), "unknown": trace.get("unknown"), "unknown_policy": trace.get("unknown_policy"), "hu_sorting_layer": trace.get("hu_sorting_layer"), "scope": trace.get("scope"), "r18_gang_dominance_overlay": {"structure": "added_gang_all_draws_strictly_dominate_hu/v1", "triggered": True, "hu_focal_score": dominance_hu_value, "gang_route_focal_score": dominance_best_value, "local_gain": dominance_best_value - dominance_hu_value, "checks": dominance_checks, "score_delta": score - before_dominance_score, "fallback": "任一事实缺失或判据失败时逐点评分保持P3"}}
        final_entries.append({"action_key": entry.get("action_key"), "score": score, "trace": trace})
    seven_best_key = None
    seven_parent_key = None
    seven_parent_facts = None
    seven_best_facts = None
    seven_parent_support = None
    seven_best_support = None
    seven_triggered = False
    seven_degrade_reason = "目标纯弃牌门清窗口不成立"
    seven_rows = []
    pure_closed_discard = len(actions) >= 2 and own_meld_count == 0
    if pure_closed_discard:
        for action in actions:
            if action.get("is_legal") is not True or action.get("action_type") != "discard":
                pure_closed_discard = False
    if pure_closed_discard:
        seven_degrade_reason = "至少一个动作的分牌型事实未知或不完整"
        facts_complete = True
        for action in actions:
            key = action.get("action_key")
            standard_shanten = action.get("standard_shanten_after")
            seven_shanten = action.get("seven_pairs_shanten_after")
            standard_useful = action.get("standard_useful_tiles")
            seven_useful = action.get("seven_pairs_useful_tiles")
            valid = (
                key is not None
                and action.get("fact_kind") == "hand_progress"
                and action.get("pattern_progress_note") is None
                and standard_shanten is not None
                and standard_shanten is not True
                and standard_shanten is not False
                and standard_shanten >= 0
                and seven_shanten is not None
                and seven_shanten is not True
                and seven_shanten is not False
                and seven_shanten >= 0
                and standard_useful is not None
                and seven_useful is not None
            )
            standard_map = []
            seven_map = []
            if valid:
                for useful in standard_useful:
                    code = useful.get("code")
                    remaining = useful.get("remaining_estimate")
                    if code not in canonical_codes or remaining is None or remaining is True or remaining is False or remaining < 0 or remaining > 4:
                        valid = False
                    else:
                        for seen in standard_map:
                            if seen[0] == code:
                                valid = False
                        standard_map.append((code, remaining))
                for useful in seven_useful:
                    code = useful.get("code")
                    remaining = useful.get("remaining_estimate")
                    if code not in canonical_codes or remaining is None or remaining is True or remaining is False or remaining < 0 or remaining > 4:
                        valid = False
                    else:
                        for seen in seven_map:
                            if seen[0] == code:
                                valid = False
                        seven_map.append((code, remaining))
            if not valid:
                facts_complete = False
            seven_rows.append({"action_key": key, "standard_shanten": standard_shanten, "seven_shanten": seven_shanten, "standard_map": standard_map, "seven_map": seven_map})
        if facts_complete:
            seven_parent_key = None
            seven_parent_score = None
            for entry in final_entries:
                key = entry.get("action_key")
                score = entry.get("score")
                if seven_parent_score is None or score > seven_parent_score or (score == seven_parent_score and key < seven_parent_key):
                    seven_parent_key = key
                    seven_parent_score = score
            for row in seven_rows:
                if row.get("action_key") == seven_parent_key:
                    seven_parent_facts = row
            seven_degrade_reason = "没有与P5及普通型完全持平、且七对一步事实严格占优的动作"
            if seven_parent_facts is not None:
                for row in seven_rows:
                    key = row.get("action_key")
                    score = None
                    for entry in final_entries:
                        if entry.get("action_key") == key:
                            score = entry.get("score")
                    same_parent_score = score == seven_parent_score
                    same_standard = row.get("standard_shanten") == seven_parent_facts.get("standard_shanten") and row.get("standard_map") == seven_parent_facts.get("standard_map")
                    seven_dominates = row.get("seven_shanten") < seven_parent_facts.get("seven_shanten")
                    if row.get("seven_shanten") == seven_parent_facts.get("seven_shanten"):
                        weakly_greater = True
                        strictly_greater = False
                        for code in canonical_codes:
                            left = 0
                            right = 0
                            for item in row.get("seven_map"):
                                if item[0] == code:
                                    left = item[1]
                            for item in seven_parent_facts.get("seven_map"):
                                if item[0] == code:
                                    right = item[1]
                            if left < right:
                                weakly_greater = False
                            if left > right:
                                strictly_greater = True
                        if weakly_greater and strictly_greater:
                            seven_dominates = True
                    if same_parent_score and same_standard and seven_dominates:
                        support = 0
                        for item in row.get("seven_map"):
                            support += item[1]
                        choose = seven_best_facts is None
                        if seven_best_facts is not None:
                            best_support = 0
                            for item in seven_best_facts.get("seven_map"):
                                best_support += item[1]
                            if row.get("seven_shanten") < seven_best_facts.get("seven_shanten"):
                                choose = True
                            elif row.get("seven_shanten") == seven_best_facts.get("seven_shanten") and support > best_support:
                                choose = True
                            elif row.get("seven_shanten") == seven_best_facts.get("seven_shanten") and support == best_support and key < seven_best_key:
                                choose = True
                        if choose:
                            seven_best_key = key
                            seven_best_facts = row
            if seven_best_key is not None:
                seven_triggered = True
                seven_degrade_reason = "触发"
                seven_parent_support = 0
                for item in seven_parent_facts.get("seven_map"):
                    seven_parent_support += item[1]
                seven_best_support = 0
                for item in seven_best_facts.get("seven_map"):
                    seven_best_support += item[1]
                replaced_entries = []
                for entry in final_entries:
                    if entry.get("action_key") != seven_best_key:
                        replaced_entries.append(entry)
                    else:
                        trace = entry.get("trace")
                        score = seven_parent_score + 0.25
                        trace = {"basis": trace.get("basis"), "base_score": trace.get("base_score"), "shanten_after": trace.get("shanten_after"), "best_shanten_non_pass": trace.get("best_shanten_non_pass"), "wealth_part": trace.get("wealth_part"), "wealth_discard_part": trace.get("wealth_discard_part"), "river_part": trace.get("river_part"), "risk_units": trace.get("risk_units"), "style_part": trace.get("style_part"), "unknown": trace.get("unknown"), "unknown_policy": trace.get("unknown_policy"), "hu_sorting_layer": trace.get("hu_sorting_layer"), "scope": trace.get("scope"), "r18_seven_pairs_overlay": {"structure": "p5_and_standard_parity_seven_pairs_dominance/v1", "triggered": True, "parent_action": seven_parent_key, "parent_score": seven_parent_score, "parent_standard_shanten": seven_parent_facts.get("standard_shanten"), "dominant_standard_shanten": seven_best_facts.get("standard_shanten"), "parent_seven_pairs_shanten": seven_parent_facts.get("seven_shanten"), "dominant_seven_pairs_shanten": seven_best_facts.get("seven_shanten"), "parent_seven_pairs_support": seven_parent_support, "dominant_seven_pairs_support": seven_best_support, "score_delta": score - entry.get("score"), "fallback": "任一事实缺失、普通型不等或P5不同分时逐点评分保持P5", "limitation": "只证明P5评分与普通型一步事实不退化，不是完整牌局期望"}}
                        replaced_entries.append({"action_key": seven_best_key, "score": score, "trace": trace})
                final_entries = replaced_entries
    reason = "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下"
    if overlay_triggered:
        reason = reason + "；机会边界触发，目标弃牌以胡层上方1分排序"
    if dominance_best_key is not None:
        reason = reason + "；补杠严格支配判据触发，目标补杠排在胡层上方、已准入飘机会层下方"
    if seven_triggered:
        reason = reason + "；P5与普通型完全持平时，选择七对一步事实严格占优的弃牌"
    return {"status": "SCORED", "entries": final_entries, "reason": reason}
