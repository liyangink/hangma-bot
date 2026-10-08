"""公开规则态父代路由器：按吃碰响应的已生产路线/动作链投影互斥选择两个冻结完整父代。"""


def score_stable_parent(view):
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



def score_specialist_parent(view):
    """按同一动作窗口的只读可见事实，为全部合法动作评分。"""

    def finite_number(value):
        if value is None or value is True or value is False:
            return None
        number = float(value)
        if number - number != 0:
            return None
        return number

    def nonnegative_integer(value):
        number = finite_number(value)
        if number is None or number < 0:
            return None
        integer = int(number)
        if number != integer:
            return None
        return integer

    def shanten_value(value):
        number = finite_number(value)
        if number is None or number < -1:
            return None
        integer = int(number)
        if number != integer:
            return None
        return integer

    def tile_support(tiles):
        if tiles is None:
            return None
        total = 0.0
        codes = set()
        valid = True
        for tile in tiles:
            code = tile.get("code")
            amount = nonnegative_integer(tile.get("remaining_estimate"))
            if (code is None or code is True or code is False or amount is None
                    or amount > 4 or code in codes):
                valid = False
            else:
                codes.add(code)
                total += float(amount)
        if valid:
            return total
        return None

    def branch_support(value):
        amount = nonnegative_integer(value)
        if amount is None:
            return None
        return float(amount)

    def profile_record(shanten, support, basis, pattern, followup_key):
        if shanten is None:
            return None
        score = -90.0 * float(shanten)
        if support is not None:
            score += support
        if score - score != 0:
            return None
        return {
            "score": score,
            "basis": basis,
            "pattern": pattern,
            "shanten": shanten,
            "support": support,
            "support_known": support is not None,
            "followup_key": followup_key,
            "route_followup_discard": None
        }

    def settlement_read(settlement, focus_seat):
        if settlement is None:
            return None
        deltas = settlement.get("score_delta")
        self_delta = finite_number(settlement.get("self_delta"))
        if deltas is None or len(deltas) != 4 or self_delta is None:
            return None
        values = []
        valid = True
        for item in deltas:
            value = finite_number(item)
            if value is None:
                valid = False
            else:
                values.append(value)
        if not valid or len(values) != 4:
            return None
        if self_delta != values[focus_seat]:
            return None
        return {"deltas": values, "self_delta": self_delta}

    def four_scores(values):
        if values is None or len(values) != 4:
            return None
        result = []
        valid = True
        for item in values:
            value = finite_number(item)
            if value is None:
                valid = False
            else:
                result.append(value)
        if not valid:
            return None
        return result

    def current_stage_values(competition):
        if competition is None:
            return None
        masks = competition.get("freshness_masks")
        if masks is None or len(masks) != 2:
            return None
        if masks[0] != "stage_account:complete" or masks[1] != "table_account:live":
            return None
        return four_scores(competition.get("current_stage_scores"))

    def gate_change(before_values, delta_values, focus_seat):
        after_values = []
        for position in range(4):
            value = before_values[position] + delta_values[position]
            if value - value != 0:
                return None
            after_values.append(value)
        before_sorted = sorted(before_values)
        after_sorted = sorted(after_values)
        before_inside = before_values[focus_seat] - before_sorted[2]
        before_outside = before_values[focus_seat] - before_sorted[1]
        after_inside = after_values[focus_seat] - after_sorted[2]
        after_outside = after_values[focus_seat] - after_sorted[1]
        return {
            "inside_delta": after_inside - before_inside,
            "outside_delta": after_outside - before_outside
        }

    def family_signal(entries):
        best_value = None
        best_family = None
        best_state = None
        best_progress = None
        if entries is None:
            return (best_value, best_family, best_state, best_progress)
        for entry in entries:
            family = entry.get("family")
            state = entry.get("route_status")
            progress = entry.get("progress")
            value = None
            if family in ("branch", "chain", "four_white", "baotou"):
                if state == "witnessed":
                    if progress == "advance":
                        value = 8.0
                    elif progress == "same":
                        value = 2.0
                    elif progress == "retreat":
                        value = -3.0
                    elif progress == "close":
                        value = -6.0
                elif state == "open_uncertain":
                    if progress == "advance":
                        value = 2.0
                    elif progress == "same":
                        value = 0.0
                    elif progress == "retreat":
                        value = -1.0
                    elif progress == "close":
                        value = -2.0
                elif state == "closed_proven":
                    if progress == "same":
                        value = 0.0
                    elif progress == "retreat":
                        value = -2.0
                    elif progress == "close":
                        value = -4.0
            if value is not None:
                if family == "four_white":
                    if value > 0:
                        value += 4.0
                    elif value < 0:
                        value -= 2.0
                elif family == "baotou" and value > 0:
                    value += 2.0
                elif family == "chain" and value > 0:
                    value += 1.0
                if best_value is None or value > best_value:
                    best_value = value
                    best_family = family
                    best_state = state
                    best_progress = progress
        return (best_value, best_family, best_state, best_progress)

    def route_record(routes, focus_seat):
        selected = None
        if routes is None:
            return None
        for route in routes:
            shanten = shanten_value(route.get("shanten"))
            support = tile_support(route.get("useful_tiles"))
            settlement = settlement_read(route.get("conditional_settlement"), focus_seat)
            conditions = route.get("conditions")
            draw_kind = None
            conditions_known = False
            if conditions is not None:
                draw_kind = conditions.get("draw_kind")
                if draw_kind == "normal" or draw_kind == "replacement":
                    conditions_known = True
            if (shanten is not None and support is not None
                    and settlement is not None and conditions_known):
                score = (-90.0 * float(shanten) + support
                         + 0.10 * settlement.get("self_delta"))
                if score - score == 0:
                    record = {
                        "score": score,
                        "basis": "single_conditional_route",
                        "pattern": "conditional_route",
                        "shanten": shanten,
                        "support": support,
                        "support_known": True,
                        "followup_key": None,
                        "route_followup_discard": route.get("followup_discard"),
                        "route_draw_kind": draw_kind
                    }
                    if selected is None or score > selected.get("score"):
                        selected = record
        return selected

    def pick_record(records):
        selected = None
        for record in records:
            score = record.get("score")
            if selected is None or score > selected.get("score"):
                selected = record
        return selected

    actions = view.get("actions")
    visible = view.get("visible_state")
    if actions is None or visible is None or len(actions) == 0:
        return {"status": "ABSTAIN", "reason": "缺少动作表或公开可见状态"}

    seat_number = finite_number(visible.get("seat"))
    if seat_number is None:
        return {"status": "ABSTAIN", "reason": "我方座位不可用"}
    seat = int(seat_number)
    if seat_number != seat or seat < 0 or seat > 3:
        return {"status": "ABSTAIN", "reason": "我方座位不可用"}

    hand = visible.get("my_hand")
    melds = visible.get("melds")
    rule_state = visible.get("rule_state")
    if hand is None or melds is None or rule_state is None or len(melds) != 4:
        return {"status": "ABSTAIN", "reason": "财神机制所需公开状态缺失"}

    wealth = rule_state.get("wealth_god")
    if wealth is None or wealth is True or wealth is False:
        return {"status": "ABSTAIN", "reason": "财神牌码缺失"}

    own_meld_count = len(melds[seat])
    wealth_count = hand.count(wealth)
    drawn = visible.get("drawn_tile")
    if drawn == wealth and len(hand) != 14 - 3 * own_meld_count:
        wealth_count += 1

    stage_values = current_stage_values(view.get("competition"))
    pending = []
    known_scores = []
    seen_keys = set()

    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if (key is None or key is True or key is False or kind is None
                or action.get("is_legal") is not True):
            return {"status": "ABSTAIN", "reason": "动作合法身份或键缺失"}
        if kind not in ("discard", "chi", "peng", "gang", "hu", "pass"):
            return {"status": "ABSTAIN", "reason": "动作类型不在冻结枚举内"}
        if key in seen_keys:
            return {"status": "ABSTAIN", "reason": "动作键重复"}
        seen_keys.add(key)

        tile_code = None
        if kind == "discard":
            if len(key) <= 8 or key[0:8] != "discard:":
                return {"status": "ABSTAIN", "reason": "弃牌动作键格式不可用"}
            tile_code = key[8:]

        fact_kind = action.get("fact_kind")
        direct_allowed = True
        if kind == "pass":
            if (action.get("best_followup_discard") is not None
                    or action.get("replacement_draw_unknown") is not False):
                direct_allowed = False
        elif kind == "gang" and action.get("replacement_draw_unknown") is not False:
            direct_allowed = False

        records = []
        if kind == "hu":
            record = profile_record(-1, None, "legal_hu", "win", None)
            if record is not None:
                records.append(record)
        elif fact_kind == "hand_progress" and direct_allowed:
            combined = shanten_value(action.get("shanten_after"))
            combined_support = tile_support(action.get("useful_tiles"))
            record = profile_record(
                combined, combined_support, "action_hand_progress", "combined", None)
            if record is not None:
                records.append(record)

            standard = shanten_value(action.get("standard_shanten_after"))
            standard_support = tile_support(action.get("standard_useful_tiles"))
            record = profile_record(
                standard, standard_support, "action_hand_progress", "standard", None)
            if record is not None:
                records.append(record)

            seven_pairs = shanten_value(action.get("seven_pairs_shanten_after"))
            seven_pairs_support = tile_support(action.get("seven_pairs_useful_tiles"))
            record = profile_record(
                seven_pairs, seven_pairs_support, "action_hand_progress",
                "seven_pairs", None)
            if record is not None:
                records.append(record)

        branches = action.get("followup_branches")
        if branches is not None:
            if len(branches) == 0 and (kind == "chi" or kind == "peng"):
                records.append({
                    "score": 0.0,
                    "basis": "known_empty_followup_branches",
                    "pattern": "none",
                    "shanten": None,
                    "support": None,
                    "support_known": False,
                    "followup_key": None,
                    "route_followup_discard": None
                })
            for branch in branches:
                followup_key = branch.get("followup_key")
                if followup_key is not None:
                    support = branch_support(branch.get("support_remaining"))
                    combined = shanten_value(branch.get("combined_shanten"))
                    record = profile_record(
                        combined, support, "followup_branch", "combined", followup_key)
                    if record is not None:
                        records.append(record)

                    standard = shanten_value(branch.get("standard_shanten_after"))
                    record = profile_record(
                        standard, support, "followup_branch", "standard", followup_key)
                    if record is not None:
                        records.append(record)

                    seven_pairs = shanten_value(branch.get("seven_pairs_shanten_after"))
                    record = profile_record(
                        seven_pairs, support, "followup_branch", "seven_pairs",
                        followup_key)
                    if record is not None:
                        records.append(record)

        route = route_record(action.get("routes"), seat)
        if route is not None:
            records.append(route)

        family_value, family_name, family_state, family_progress = family_signal(
            action.get("family_progress_entries"))
        if family_value is None:
            summary = action.get("family_progress")
            if summary == "ADVANCE":
                family_value = 3.0
            elif summary == "SAME":
                family_value = 0.0
            elif summary == "RETREAT":
                family_value = -3.0
            elif summary == "CLOSE":
                family_value = -5.0
            if family_value is not None:
                family_name = "summary"
                family_state = "summary"
                family_progress = summary

        settlement = settlement_read(action.get("immediate_settlement"), seat)
        settlement_part = 0.0
        settlement_mode = None
        inside_delta = None
        outside_delta = None
        if settlement is not None:
            if stage_values is not None:
                change = gate_change(stage_values, settlement.get("deltas"), seat)
                if change is not None:
                    inside_delta = change.get("inside_delta")
                    outside_delta = change.get("outside_delta")
                    settlement_part = 0.15 * inside_delta + 0.05 * outside_delta
                    settlement_mode = "recompute_current_stage"
                else:
                    settlement_part = 0.10 * settlement.get("self_delta")
                    settlement_mode = "direct_self_delta_gate_unavailable"
            else:
                settlement_part = 0.10 * settlement.get("self_delta")
                settlement_mode = "direct_self_delta_no_stage_account"

        if len(records) == 0 and settlement is not None:
            records.append({
                "score": 0.0,
                "basis": "immediate_settlement",
                "pattern": "none",
                "shanten": None,
                "support": None,
                "support_known": False,
                "followup_key": None,
                "route_followup_discard": None
            })
        if len(records) == 0 and family_value is not None:
            records.append({
                "score": 0.0,
                "basis": "family_progress_only",
                "pattern": "none",
                "shanten": None,
                "support": None,
                "support_known": False,
                "followup_key": None,
                "route_followup_discard": None
            })
        if len(records) == 0 and fact_kind == "not_applicable":
            records.append({
                "score": 0.0,
                "basis": "known_not_applicable",
                "pattern": "none",
                "shanten": None,
                "support": None,
                "support_known": False,
                "followup_key": None,
                "route_followup_discard": None
            })

        selected = pick_record(records)
        if selected is None:
            unknown_facts = []
            if fact_kind is None or fact_kind == "analysis_failed":
                unknown_facts.append("fact_kind")
            if fact_kind == "hand_progress" and not direct_allowed:
                unknown_facts.append("replacement_or_followup_state")
            if branches is None:
                unknown_facts.append("followup_branches")
            routes = action.get("routes")
            if routes is None or len(routes) == 0:
                unknown_facts.append("conditional_routes")
            families = action.get("family_progress_entries")
            if families is None or len(families) == 0:
                unknown_facts.append("family_progress_entries")
            if action.get("immediate_settlement") is not None and settlement is None:
                unknown_facts.append("immediate_settlement")
            if len(unknown_facts) == 0:
                unknown_facts.append("no_usable_produced_readout")
            pending.append({
                "action_key": key,
                "known": False,
                "unknown_facts": unknown_facts
            })
        else:
            family_adjustment = 0.0
            if family_value is not None:
                family_adjustment = family_value
                if (family_name == "four_white" and kind == "discard"
                        and tile_code == wealth and family_adjustment > 0):
                    family_adjustment = 0.0

            wealth_adjustment = 0.0
            if kind == "discard" and tile_code == wealth:
                wealth_adjustment = -40.0
                if (family_name == "four_white" and family_state == "witnessed"
                        and (family_progress == "retreat"
                             or family_progress == "close")):
                    wealth_adjustment -= 25.0
                if selected.get("pattern") == "seven_pairs" and wealth_count >= 2:
                    wealth_adjustment -= 12.0

            score = (selected.get("score") + settlement_part
                     + family_adjustment + wealth_adjustment)
            if score - score != 0:
                return {"status": "ABSTAIN", "reason": "动作评分出现非有限数"}

            trace = {
                "mechanism_version": "conditional_route_wealth_recompute_v1",
                "basis": selected.get("basis"),
                "pattern": selected.get("pattern"),
                "shanten": selected.get("shanten"),
                "support": selected.get("support"),
                "support_known": selected.get("support_known"),
                "followup_key": selected.get("followup_key"),
                "route_followup_discard": selected.get("route_followup_discard"),
                "family": family_name,
                "family_state": family_state,
                "family_progress": family_progress,
                "family_adjustment": family_adjustment,
                "wealth_count_before": wealth_count,
                "wealth_adjustment": wealth_adjustment,
                "settlement_mode": settlement_mode,
                "settlement_part": settlement_part,
                "inside_gap_delta": inside_delta,
                "outside_gap_delta": outside_delta,
                "route_combination": "single_best_witness",
                "hu_compare_legal": kind == "hu",
                "unknown": False,
                "unknown_policy": None
            }
            pending.append({
                "action_key": key,
                "known": True,
                "score": score,
                "trace": trace
            })
            known_scores.append(score)

    if len(known_scores) == 0:
        return {
            "status": "ABSTAIN",
            "reason": "全部动作均无可用已生产读数，未知不能取零分"
        }

    known_floor = min(known_scores)
    if known_floor - known_floor != 0:
        return {"status": "ABSTAIN", "reason": "已知评分出现非有限数"}

    entries = []
    for item in pending:
        if item.get("known") is True:
            entries.append({
                "action_key": item.get("action_key"),
                "score": item.get("score"),
                "trace": item.get("trace")
            })
        else:
            score = known_floor - 1.0
            if score - score != 0:
                return {"status": "ABSTAIN", "reason": "未知锚定出现非有限数"}
            entries.append({
                "action_key": item.get("action_key"),
                "score": score,
                "trace": {
                    "mechanism_version": "conditional_route_wealth_recompute_v1",
                    "unknown": True,
                    "unknown_facts": item.get("unknown_facts"),
                    "unknown_policy": "known_final_floor_minus_1",
                    "route_combination": "not_scored"
                }
            })

    return {
        "status": "SCORED",
        "entries": entries,
        "reason": "条件路线仅取单个已证实见证；未分析动作按已知最终最低分减一锚定"
    }


def make_router_trace(selected_parent, rule_state, fallback_reason, unknown_fallback):
    """构造同一动作窗口所有评分条目共享的父代路由审计对象。"""
    return {
        "selected_parent": selected_parent,
        "rule_state": rule_state,
        "fallback_reason": fallback_reason,
        "unknown_fallback": unknown_fallback,
    }


def select_parent_route(view):
    """仅用公开吃碰候选的后继分支与路线/动作链投影选择完整父代。"""
    if view.get("schema_version") != "sitin-scoring-view/3":
        return make_router_trace(
            "stable_v2", "unknown_public_rule_state", "unsupported_scoring_view", True)
    actions = view.get("actions")
    visible = view.get("visible_state")
    if actions is None or visible is None or len(actions) == 0:
        return make_router_trace(
            "stable_v2", "unknown_public_rule_state", "missing_actions_or_visible_state", True)
    rule = visible.get("rule_state")
    if rule is None:
        return make_router_trace(
            "stable_v2", "unknown_public_rule_state", "missing_rule_state_projection", True)
    catch_play = rule.get("catch_play")
    if catch_play is not True and catch_play is not False:
        return make_router_trace(
            "stable_v2", "unknown_public_rule_state", "invalid_catch_play_projection", True)
    if catch_play is True:
        return make_router_trace(
            "stable_v2", "catch_play_restricted", None, False)

    has_response = False
    has_projected_route_chain = False
    for action in actions:
        if action.get("is_legal") is not True:
            return make_router_trace(
                "stable_v2", "unknown_public_rule_state", "invalid_legal_action_projection", True)
        kind = action.get("action_type")
        if kind not in ("discard", "chi", "peng", "gang", "hu", "pass"):
            return make_router_trace(
                "stable_v2", "unknown_public_rule_state", "unknown_action_type", True)
        if kind != "chi" and kind != "peng":
            continue
        has_response = True
        branches = action.get("followup_branches")
        entries = action.get("family_progress_entries")
        if branches is None or entries is None:
            return make_router_trace(
                "stable_v2", "unknown_public_rule_state", "incomplete_response_route_projection", True)
        response_has_route_chain = False
        for entry in entries:
            family = entry.get("family")
            state = entry.get("route_status")
            progress = entry.get("progress")
            if family not in ("branch", "chain", "four_white", "baotou"):
                continue
            if state not in ("witnessed", "open_uncertain", "closed_proven"):
                return make_router_trace(
                    "stable_v2", "unknown_public_rule_state", "invalid_route_chain_state", True)
            if progress not in ("advance", "same", "retreat", "close", "unknown"):
                return make_router_trace(
                    "stable_v2", "unknown_public_rule_state", "invalid_route_chain_progress", True)
            response_has_route_chain = True
        if response_has_route_chain:
            has_projected_route_chain = True

    if has_response and has_projected_route_chain:
        return make_router_trace(
            "specialist", "response_route_chain_projected", None, False)
    if has_response:
        return make_router_trace(
            "stable_v2", "response_route_chain_not_projected", None, False)
    return make_router_trace(
        "stable_v2", "no_projected_chi_peng_response", None, False)


def attach_parent_router(result, router):
    """只扩充 trace；动作键、评分值、状态和原因沿用所选父代。"""
    if result.get("status") != "SCORED":
        return result
    entries = []
    for entry in result.get("entries"):
        entries.append({
            "action_key": entry.get("action_key"),
            "score": entry.get("score"),
            "trace": {
                "selected_parent_trace": entry.get("trace"),
                "parent_router": router,
            },
        })
    return {
        "status": result.get("status"),
        "entries": entries,
        "reason": result.get("reason"),
    }


def score_actions(view):
    """按公开离散规则态选择一个冻结父代，并原样采用该父代的全部评分。"""
    router = select_parent_route(view)
    if router.get("selected_parent") == "specialist":
        result = score_specialist_parent(view)
    else:
        result = score_stable_parent(view)
    return attach_parent_router(result, router)
