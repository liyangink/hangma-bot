"""候选机制说明：在可信分牌型事实下，以次优牌型的独有有效牌支持细化直接弃牌。"""

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
    hu_present = False
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if key is None or kind is None or action.get("is_legal") is not True:
            return {"status": "ABSTAIN", "reason": "动作合法身份或键缺失"}
        if kind == "hu":
            hu_present = True
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
        pattern_bonus = 0.0
        pattern_status = "not_direct_known_discard"
        pattern_ready = False
        pattern_primary = None
        pattern_secondary = None
        pattern_gap = None
        pattern_unique_support = None
        pattern_primary_support = None
        pattern_secondary_support = None
        if direct and kind == "discard":
            pattern_status = "facts_missing_or_untrusted"
            standard_shanten = action.get("standard_shanten_after")
            seven_shanten = action.get("seven_pairs_shanten_after")
            standard_useful = action.get("standard_useful_tiles")
            seven_useful = action.get("seven_pairs_useful_tiles")
            standard_valid = False
            seven_valid = False
            standard_codes = set()
            seven_codes = set()
            standard_support = None
            seven_support = None
            if standard_shanten is not None and standard_shanten is not True and standard_shanten is not False and seven_shanten is not None and seven_shanten is not True and seven_shanten is not False and standard_useful is not None and seven_useful is not None and action.get("pattern_progress_note") is None:
                standard_valid = True
                standard_support = 0.0
                for tile in standard_useful:
                    code = tile.get("code")
                    remaining = tile.get("remaining_estimate")
                    if code is None or code is True or code is False or remaining is None or remaining is True or remaining is False:
                        standard_valid = False
                    else:
                        amount = float(remaining)
                        if amount - amount != 0 or amount < 0.0 or amount > 4.0 or amount != int(amount) or code in standard_codes:
                            standard_valid = False
                        else:
                            standard_codes.add(code)
                            standard_support += amount
                seven_valid = True
                seven_support = 0.0
                for tile in seven_useful:
                    code = tile.get("code")
                    remaining = tile.get("remaining_estimate")
                    if code is None or code is True or code is False or remaining is None or remaining is True or remaining is False:
                        seven_valid = False
                    else:
                        amount = float(remaining)
                        if amount - amount != 0 or amount < 0.0 or amount > 4.0 or amount != int(amount) or code in seven_codes:
                            seven_valid = False
                        else:
                            seven_codes.add(code)
                            seven_support += amount
                if standard_valid and seven_valid:
                    standard_value = float(standard_shanten)
                    seven_value = float(seven_shanten)
                    combined_value = float(shanten)
                    if standard_value - standard_value == 0 and seven_value - seven_value == 0 and combined_value - combined_value == 0 and standard_value >= 0.0 and seven_value >= 0.0 and combined_value >= 0.0 and standard_value == int(standard_value) and seven_value == int(seven_value) and combined_value == int(combined_value) and min(standard_value, seven_value) == combined_value:
                        pattern_ready = True
                        pattern_status = "facts_valid_no_extra_option"
                        if standard_value < seven_value:
                            pattern_primary = "standard"
                            pattern_secondary = "seven_pairs"
                            pattern_primary_support = standard_support
                            pattern_secondary_support = seven_support
                            primary_codes = standard_codes
                            secondary_codes = seven_codes
                            secondary_useful = seven_useful
                            pattern_gap = seven_value - combined_value
                        elif seven_value < standard_value:
                            pattern_primary = "seven_pairs"
                            pattern_secondary = "standard"
                            pattern_primary_support = seven_support
                            pattern_secondary_support = standard_support
                            primary_codes = seven_codes
                            secondary_codes = standard_codes
                            secondary_useful = standard_useful
                            pattern_gap = standard_value - combined_value
                        else:
                            pattern_status = "same_best_shanten_no_extra_option"
                        if pattern_primary is not None and (pattern_gap == 1.0 or pattern_gap == 2.0):
                            pattern_unique_support = 0.0
                            for tile in secondary_useful:
                                code = tile.get("code")
                                if code not in primary_codes:
                                    pattern_unique_support += float(tile.get("remaining_estimate"))
                            if pattern_unique_support > 0.0:
                                pattern_bonus = round(min(pattern_unique_support, 8.0) / (4.0 * pattern_gap), 6)
                                if pattern_bonus > 0.0:
                                    pattern_status = "eligible_secondary_option"
                                else:
                                    pattern_status = "close_without_bonus"
                            else:
                                pattern_status = "close_without_unique_support"
                        elif pattern_primary is not None:
                            pattern_status = "secondary_too_far_no_extra_option"
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
            pending.append({"action": action, "base": base, "basis": "direct_v2", "shanten": shanten, "pattern_bonus": pattern_bonus, "pattern_status": pattern_status, "pattern_ready": pattern_ready, "pattern_primary": pattern_primary, "pattern_secondary": pattern_secondary, "pattern_gap": pattern_gap, "pattern_unique_support": pattern_unique_support, "pattern_primary_support": pattern_primary_support, "pattern_secondary_support": pattern_secondary_support})
            known.append(base)
        elif produced:
            pending.append({"action": action, "base": 0.0, "basis": "produced_outside_v2", "shanten": None, "pattern_bonus": pattern_bonus, "pattern_status": pattern_status, "pattern_ready": pattern_ready, "pattern_primary": pattern_primary, "pattern_secondary": pattern_secondary, "pattern_gap": pattern_gap, "pattern_unique_support": pattern_unique_support, "pattern_primary_support": pattern_primary_support, "pattern_secondary_support": pattern_secondary_support})
            known.append(0.0)
        else:
            pending.append({"action": action, "base": None, "basis": "unknown", "shanten": None, "pattern_bonus": pattern_bonus, "pattern_status": pattern_status, "pattern_ready": pattern_ready, "pattern_primary": pattern_primary, "pattern_secondary": pattern_secondary, "pattern_gap": pattern_gap, "pattern_unique_support": pattern_unique_support, "pattern_primary_support": pattern_primary_support, "pattern_secondary_support": pattern_secondary_support})
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
        pattern_applied_bonus = item.get("pattern_bonus")
        pattern_applied_status = item.get("pattern_status")
        if hu_present:
            if pattern_applied_bonus > 0.0:
                pattern_applied_status = "suppressed_by_legal_hu"
            pattern_applied_bonus = 0.0
        trace = {"basis": item.get("basis"), "base_score": base, "shanten_after": item.get("shanten"), "best_shanten_non_pass": best_shanten, "wealth_part": wealth_part, "wealth_discard_part": wealth_discard_part, "river_part": river_part, "risk_units": risk_units, "style_part": style_part, "unknown": unknown, "unknown_policy": "known_final_floor_minus_1" if unknown else None, "hu_sorting_layer": kind == "hu", "scope": "direct_v2_or_produced_outside_v2", "pattern_option_status": pattern_applied_status, "pattern_option_facts_ready": item.get("pattern_ready"), "pattern_primary": item.get("pattern_primary"), "pattern_secondary": item.get("pattern_secondary"), "pattern_gap": item.get("pattern_gap"), "pattern_unique_support": item.get("pattern_unique_support"), "pattern_primary_support": item.get("pattern_primary_support"), "pattern_secondary_support": item.get("pattern_secondary_support"), "pattern_option_candidate_bonus": item.get("pattern_bonus"), "pattern_option_bonus": pattern_applied_bonus}
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
        pattern_bonus = entry.get("trace").get("pattern_option_bonus")
        if pattern_bonus > 0.0:
            score = round(score + pattern_bonus, 6)
        final_entries.append({"action_key": entry.get("action_key"), "score": score, "trace": entry.get("trace")})
    return {"status": "SCORED", "entries": final_entries, "reason": "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下；分牌型选择余地只作用于无胡的直接弃牌"}
