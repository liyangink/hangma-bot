# STRUCTURE_SPACE_JSON: {"parameters":{"LEEWAY_UNIT_WEIGHT":[0.2,0.0,0.35,0.1,0.5],"LEEWAY_UNIT_CLIP":[10.0,12.0,6.0,4.0],"OPTION_SUPPORT_CAP":[8.0,0.0,12.0,4.0,16.0],"OPTION_SUPPORT_DIVISOR":[4.0,2.0,8.0,16.0]},"zero_effect":{"LEEWAY_UNIT_WEIGHT":0.0,"LEEWAY_UNIT_CLIP":10.0,"OPTION_SUPPORT_CAP":0.0,"OPTION_SUPPORT_DIVISOR":4.0},"configs":[{"LEEWAY_UNIT_WEIGHT":0.2,"LEEWAY_UNIT_CLIP":10.0,"OPTION_SUPPORT_CAP":8.0,"OPTION_SUPPORT_DIVISOR":4.0},{"LEEWAY_UNIT_WEIGHT":0.0,"LEEWAY_UNIT_CLIP":10.0,"OPTION_SUPPORT_CAP":0.0,"OPTION_SUPPORT_DIVISOR":4.0},{"LEEWAY_UNIT_WEIGHT":0.35,"LEEWAY_UNIT_CLIP":12.0,"OPTION_SUPPORT_CAP":8.0,"OPTION_SUPPORT_DIVISOR":4.0},{"LEEWAY_UNIT_WEIGHT":0.2,"LEEWAY_UNIT_CLIP":10.0,"OPTION_SUPPORT_CAP":12.0,"OPTION_SUPPORT_DIVISOR":2.0},{"LEEWAY_UNIT_WEIGHT":0.1,"LEEWAY_UNIT_CLIP":6.0,"OPTION_SUPPORT_CAP":4.0,"OPTION_SUPPORT_DIVISOR":8.0},{"LEEWAY_UNIT_WEIGHT":0.5,"LEEWAY_UNIT_CLIP":4.0,"OPTION_SUPPORT_CAP":16.0,"OPTION_SUPPORT_DIVISOR":16.0}]}
"""候选机制说明：默认 V2 基础排序、胡排序层与严格未知锚定上，以互斥门控的单一「选择余地」choice_leeway_v1 重组残余凝聚度与七对次优选项：选项合格整体替换残余，否则残余独占，同一事实只计一次。"""

LEEWAY_UNIT_WEIGHT = 0.2
LEEWAY_UNIT_CLIP = 10.0
OPTION_SUPPORT_CAP = 8.0
OPTION_SUPPORT_DIVISOR = 4.0


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
        direct = False
        base = None
        shanten = action.get("shanten_after")
        useful = action.get("useful_tiles")
        if kind == "hu":
            direct = True
            base = 1000.0
            hu_present = True
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
        residual_part = 0.0
        residual_active = False
        residual_hand_source = None
        residual_complete_count = None
        residual_eligible_slots = None
        residual_connected_slots = None
        residual_orphan_slots = None
        residual_pair_slots = None
        residual_adjacent_slots = None
        residual_live_gap_slots = None
        residual_honor_pair_slots = None
        residual_wealth_slots = None
        residual_raw_units = None
        residual_units = None
        leeway_mode = "inactive"
        leeway_part = 0.0
        option_ready = False
        option_status = "off_trigger"
        option_gap = None
        option_unique_support = None
        option_bonus = None
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
            if item.get("basis") == "direct_v2" and action.get("fact_kind") == "hand_progress":
                standard_shanten = action.get("standard_shanten_after")
                standard_useful = action.get("standard_useful_tiles")
                structure_ready = True
                if standard_shanten is None or standard_shanten is True or standard_shanten is False:
                    structure_ready = False
                elif standard_shanten != item.get("shanten") or standard_shanten < 0:
                    structure_ready = False
                if item.get("shanten") != best_shanten:
                    structure_ready = False
                if standard_useful is None:
                    structure_ready = False
                complete_hand = []
                if drawn is None:
                    if len(hand) == 14 - 3 * own_meld_count:
                        for hand_tile in hand:
                            complete_hand.append(hand_tile)
                        residual_hand_source = "hand_only"
                    else:
                        structure_ready = False
                elif drawn is True or drawn is False:
                    structure_ready = False
                elif len(hand) == 13 - 3 * own_meld_count:
                    for hand_tile in hand:
                        complete_hand.append(hand_tile)
                    complete_hand.append(drawn)
                    residual_hand_source = "hand_plus_drawn"
                else:
                    structure_ready = False
                residual_complete_count = len(complete_hand)
                if residual_complete_count != 14 - 3 * own_meld_count:
                    structure_ready = False
                digits = "123456789"
                honors = "东南西北中发"
                natural_discard = False
                if len(tile_code) >= 2 and tile_code[0] in digits and tile_code[-1] in "wbt":
                    natural_discard = True
                elif len(tile_code) == 1 and tile_code in honors:
                    natural_discard = True
                if tile_code == wealth or natural_discard is not True or complete_hand.count(tile_code) < 1:
                    structure_ready = False
                standard_live_codes = []
                standard_all_codes = []
                if structure_ready:
                    for standard_tile in standard_useful:
                        standard_code = standard_tile.get("code")
                        standard_remaining = standard_tile.get("remaining_estimate")
                        if standard_code is None or standard_code is True or standard_code is False or standard_remaining is None or standard_remaining is True or standard_remaining is False:
                            structure_ready = False
                        else:
                            standard_amount = float(standard_remaining)
                            if standard_amount - standard_amount != 0 or standard_amount < 0 or standard_amount > 4:
                                structure_ready = False
                            else:
                                if standard_code not in standard_all_codes:
                                    standard_all_codes.append(standard_code)
                                if standard_amount > 0 and standard_code not in standard_live_codes:
                                    standard_live_codes.append(standard_code)
                if len(standard_live_codes) == 0:
                    structure_ready = False
                if structure_ready:
                    residual = []
                    removed = False
                    for hand_tile in complete_hand:
                        if hand_tile == tile_code and removed is False:
                            removed = True
                        else:
                            residual.append(hand_tile)
                    if removed is True:
                        residual_eligible_slots = 0
                        residual_connected_slots = 0
                        residual_orphan_slots = 0
                        residual_pair_slots = 0
                        residual_adjacent_slots = 0
                        residual_live_gap_slots = 0
                        residual_honor_pair_slots = 0
                        residual_wealth_slots = 0
                        for hand_tile in residual:
                            if hand_tile == wealth:
                                residual_wealth_slots += 1
                            elif len(hand_tile) >= 2 and hand_tile[0] in digits and hand_tile[-1] in "wbt":
                                residual_eligible_slots += 1
                                hand_rank = int(hand_tile[0])
                                hand_suit = hand_tile[-1]
                                paired = residual.count(hand_tile) > 1
                                adjacent = False
                                live_gap = False
                                if paired is not True:
                                    if hand_rank > 1 and residual.count(digits[hand_rank - 2] + hand_suit) > 0:
                                        adjacent = True
                                    if hand_rank < 9 and residual.count(digits[hand_rank] + hand_suit) > 0:
                                        adjacent = True
                                if paired is not True and adjacent is not True:
                                    if hand_rank > 2 and residual.count(digits[hand_rank - 3] + hand_suit) > 0 and digits[hand_rank - 2] + hand_suit in standard_live_codes:
                                        live_gap = True
                                    if hand_rank < 8 and residual.count(digits[hand_rank + 1] + hand_suit) > 0 and digits[hand_rank] + hand_suit in standard_live_codes:
                                        live_gap = True
                                if paired:
                                    residual_pair_slots += 1
                                    residual_connected_slots += 1
                                elif adjacent:
                                    residual_adjacent_slots += 1
                                    residual_connected_slots += 1
                                elif live_gap:
                                    residual_live_gap_slots += 1
                                    residual_connected_slots += 1
                                else:
                                    residual_orphan_slots += 1
                            elif len(hand_tile) == 1 and hand_tile in honors:
                                residual_eligible_slots += 1
                                if residual.count(hand_tile) > 1:
                                    residual_pair_slots += 1
                                    residual_honor_pair_slots += 1
                                    residual_connected_slots += 1
                                else:
                                    residual_orphan_slots += 1
                            else:
                                structure_ready = False
                        if residual_eligible_slots == 0:
                            structure_ready = False
                        if structure_ready:
                            residual_raw_units = residual_connected_slots - residual_orphan_slots
                            residual_units = residual_raw_units
                            if residual_units > LEEWAY_UNIT_CLIP:
                                residual_units = LEEWAY_UNIT_CLIP
                            elif residual_units < -LEEWAY_UNIT_CLIP:
                                residual_units = -LEEWAY_UNIT_CLIP
                            residual_part = round(LEEWAY_UNIT_WEIGHT * float(residual_units), 6)
                            residual_active = True
                if residual_active:
                    leeway_mode = "residual"
                    leeway_part = residual_part
                    option_status = "facts_missing_or_untrusted"
                    seven_shanten = action.get("seven_pairs_shanten_after")
                    seven_useful = action.get("seven_pairs_useful_tiles")
                    if hu_present:
                        option_status = "suppressed_by_legal_hu"
                    elif seven_shanten is None or seven_shanten is True or seven_shanten is False or seven_useful is None or action.get("pattern_progress_note") is not None:
                        option_status = "facts_missing_or_untrusted"
                    else:
                        seven_value = float(seven_shanten)
                        if seven_value - seven_value != 0 or seven_value < 0 or seven_value != int(seven_value):
                            option_status = "facts_missing_or_untrusted"
                        else:
                            seven_valid = True
                            unique_support = 0.0
                            seven_codes = set()
                            for tile in seven_useful:
                                code = tile.get("code")
                                remaining = tile.get("remaining_estimate")
                                if code is None or code is True or code is False or remaining is None or remaining is True or remaining is False:
                                    seven_valid = False
                                else:
                                    amount = float(remaining)
                                    if amount - amount != 0 or amount < 0 or amount > 4 or code in seven_codes:
                                        seven_valid = False
                                    else:
                                        seven_codes.add(code)
                                        if code not in standard_all_codes:
                                            unique_support += amount
                            option_unique_support = round(unique_support, 6)
                            if seven_valid is not True:
                                option_unique_support = None
                                option_status = "facts_missing_or_untrusted"
                            else:
                                combined_value = float(item.get("shanten"))
                                if combined_value - combined_value != 0:
                                    option_unique_support = None
                                    option_status = "facts_missing_or_untrusted"
                                else:
                                    gap_value = seven_value - combined_value
                                    if gap_value == 1.0 or gap_value == 2.0:
                                        option_gap = gap_value
                                        if unique_support > 0.0:
                                            option_bonus = round(min(unique_support, OPTION_SUPPORT_CAP) / (OPTION_SUPPORT_DIVISOR * gap_value), 6)
                                            if option_bonus > 0.0:
                                                option_ready = True
                                                option_status = "eligible_secondary_option"
                                                leeway_mode = "option"
                                                leeway_part = option_bonus
                                            else:
                                                option_status = "close_without_bonus"
                                        else:
                                            option_status = "close_without_unique_support"
                                    else:
                                        option_status = "secondary_too_far_no_option"
            if table_rank == 1 and familiar:
                style_part = 4.0
            elif table_rank == 4 and item.get("shanten") is not None and item.get("shanten") == best_shanten:
                style_part = 2.0
            total = round(total, 6)
            total += style_part
            total = round(total, 6)
            total += leeway_part
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
        trace = {"basis": item.get("basis"), "base_score": base, "shanten_after": item.get("shanten"), "best_shanten_non_pass": best_shanten, "wealth_part": wealth_part, "wealth_discard_part": wealth_discard_part, "river_part": river_part, "risk_units": risk_units, "style_part": style_part, "choice_leeway_v1": {"mode": leeway_mode, "part": leeway_part, "residual": {"active": residual_active, "hand_source": residual_hand_source, "complete_hand_count": residual_complete_count, "eligible_slots": residual_eligible_slots, "connected_slots": residual_connected_slots, "orphan_slots": residual_orphan_slots, "pair_slots": residual_pair_slots, "adjacent_slots": residual_adjacent_slots, "live_gap_slots": residual_live_gap_slots, "honor_pair_slots": residual_honor_pair_slots, "wealth_excluded_slots": residual_wealth_slots, "raw_units": residual_raw_units, "clipped_units": residual_units, "part": residual_part}, "option": {"eligible": option_ready, "status": option_status, "gap": option_gap, "unique_support": option_unique_support, "bonus": option_bonus}}, "unknown": unknown, "unknown_policy": "known_final_floor_minus_1" if unknown else None, "hu_sorting_layer": kind == "hu", "scope": "direct_v2_or_produced_outside_v2"}
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
    return {"status": "SCORED", "entries": final_entries, "reason": "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下；选择余地按互斥门控二选一计入弃牌总分"}
