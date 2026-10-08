"""候选机制说明：互斥路线取最大值，吃碰读取真实弃牌分支，并条件化扣除七对与财神机会损失。"""

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
    melds = visible.get("melds")
    rule_state = visible.get("rule_state")
    if hand is None or melds is None or rule_state is None or len(melds) != 4:
        return {"status": "ABSTAIN", "reason": "财神机会损失所需公开状态缺失"}
    wealth = rule_state.get("wealth_god")
    if wealth is None:
        return {"status": "ABSTAIN", "reason": "财神牌码缺失"}
    own_meld_count = len(melds[seat])
    wealth_count = hand.count(wealth)
    drawn = visible.get("drawn_tile")
    if drawn is not None and len(hand) != 14 - 3 * own_meld_count and drawn == wealth:
        wealth_count += 1

    seen_keys = set()
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if key is None or kind is None or action.get("is_legal") is not True:
            return {"status": "ABSTAIN", "reason": "动作合法身份、类型或键缺失"}
        if key in seen_keys:
            return {"status": "ABSTAIN", "reason": "动作键重复"}
        seen_keys.add(key)

    pass_standard = None
    pass_seven = None
    for action in actions:
        if action.get("action_type") != "pass" or action.get("fact_kind") != "hand_progress":
            continue
        standard_shanten = action.get("standard_shanten_after")
        standard_tiles = action.get("standard_useful_tiles")
        if standard_shanten is not None and standard_shanten is not True and standard_shanten is not False and standard_shanten >= -1 and standard_tiles is not None:
            standard_support = 0.0
            standard_valid = True
            for tile in standard_tiles:
                remaining = tile.get("remaining_estimate")
                if remaining is None or remaining is True or remaining is False:
                    standard_valid = False
                else:
                    amount = float(remaining)
                    if amount - amount != 0 or amount < 0:
                        standard_valid = False
                    else:
                        standard_support += amount
            if standard_valid:
                pass_standard = -100.0 * float(standard_shanten) + standard_support
        seven_shanten = action.get("seven_pairs_shanten_after")
        seven_tiles = action.get("seven_pairs_useful_tiles")
        if seven_shanten is not None and seven_shanten is not True and seven_shanten is not False and seven_shanten >= -1 and seven_tiles is not None:
            seven_support = 0.0
            seven_valid = True
            for tile in seven_tiles:
                remaining = tile.get("remaining_estimate")
                if remaining is None or remaining is True or remaining is False:
                    seven_valid = False
                else:
                    amount = float(remaining)
                    if amount - amount != 0 or amount < 0:
                        seven_valid = False
                    else:
                        seven_support += amount
            if seven_valid:
                pass_seven = -100.0 * float(seven_shanten) + seven_support

    pending = []
    known_scores = []
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        fact_kind = action.get("fact_kind")
        branches = action.get("followup_branches")
        routes = action.get("routes")
        families = action.get("family_progress_entries")
        settlement = action.get("immediate_settlement")
        if routes is None or families is None:
            return {"status": "ABSTAIN", "reason": "路线或家族事实容器缺失"}

        produced = False
        if fact_kind is not None and fact_kind != "analysis_failed":
            produced = True
        if branches is not None or len(routes) > 0 or len(families) > 0 or settlement is not None:
            produced = True

        direct_score = None
        direct_route = None
        direct_shanten = None
        direct_support = None
        if fact_kind == "hand_progress" and kind != "chi" and kind != "peng":
            direct_allowed = True
            if kind == "gang" and action.get("replacement_draw_unknown") is not False:
                direct_allowed = False
            if direct_allowed:
                standard_score = None
                standard_shanten = action.get("standard_shanten_after")
                standard_tiles = action.get("standard_useful_tiles")
                if standard_shanten is not None and standard_shanten is not True and standard_shanten is not False and standard_shanten >= -1 and standard_tiles is not None:
                    support = 0.0
                    valid = True
                    for tile in standard_tiles:
                        remaining = tile.get("remaining_estimate")
                        if remaining is None or remaining is True or remaining is False:
                            valid = False
                        else:
                            amount = float(remaining)
                            if amount - amount != 0 or amount < 0:
                                valid = False
                            else:
                                support += amount
                    if valid:
                        standard_score = -100.0 * float(standard_shanten) + support
                seven_score = None
                seven_shanten = action.get("seven_pairs_shanten_after")
                seven_tiles = action.get("seven_pairs_useful_tiles")
                if seven_shanten is not None and seven_shanten is not True and seven_shanten is not False and seven_shanten >= -1 and seven_tiles is not None:
                    support = 0.0
                    valid = True
                    for tile in seven_tiles:
                        remaining = tile.get("remaining_estimate")
                        if remaining is None or remaining is True or remaining is False:
                            valid = False
                        else:
                            amount = float(remaining)
                            if amount - amount != 0 or amount < 0:
                                valid = False
                            else:
                                support += amount
                    if valid:
                        seven_score = -100.0 * float(seven_shanten) + support
                if standard_score is not None:
                    direct_score = standard_score
                    direct_route = "standard"
                    direct_shanten = standard_shanten
                    direct_support = standard_score + 100.0 * float(standard_shanten)
                if seven_score is not None and (direct_score is None or seven_score > direct_score):
                    direct_score = seven_score
                    direct_route = "seven_pairs"
                    direct_shanten = seven_shanten
                    direct_support = seven_score + 100.0 * float(seven_shanten)
                combined_shanten = action.get("shanten_after")
                combined_tiles = action.get("useful_tiles")
                if direct_score is None and combined_shanten is not None and combined_shanten is not True and combined_shanten is not False and combined_shanten >= -1 and combined_tiles is not None:
                    support = 0.0
                    valid = True
                    for tile in combined_tiles:
                        remaining = tile.get("remaining_estimate")
                        if remaining is None or remaining is True or remaining is False:
                            valid = False
                        else:
                            amount = float(remaining)
                            if amount - amount != 0 or amount < 0:
                                valid = False
                            else:
                                support += amount
                    if valid:
                        direct_score = -100.0 * float(combined_shanten) + support
                        direct_route = "combined"
                        direct_shanten = combined_shanten
                        direct_support = support

        branch_best = None
        branch_key = None
        branch_discard = None
        branch_route = None
        branch_shanten = None
        branch_support = None
        branch_wealth_loss = 0
        if branches is not None:
            for branch in branches:
                support = branch.get("support_remaining")
                valid_support = True
                if support is None or support is True or support is False:
                    valid_support = False
                else:
                    support_value = float(support)
                    if support_value - support_value != 0 or support_value < 0:
                        valid_support = False
                selected_shanten = None
                selected_route = None
                standard_shanten = branch.get("standard_shanten_after")
                seven_shanten = branch.get("seven_pairs_shanten_after")
                combined_shanten = branch.get("combined_shanten")
                if standard_shanten is not None and standard_shanten is not True and standard_shanten is not False and standard_shanten >= -1:
                    selected_shanten = standard_shanten
                    selected_route = "standard"
                if seven_shanten is not None and seven_shanten is not True and seven_shanten is not False and seven_shanten >= -1 and (selected_shanten is None or seven_shanten < selected_shanten):
                    selected_shanten = seven_shanten
                    selected_route = "seven_pairs"
                if selected_shanten is None and combined_shanten is not None and combined_shanten is not True and combined_shanten is not False and combined_shanten >= -1:
                    selected_shanten = combined_shanten
                    selected_route = "combined"
                if valid_support and selected_shanten is not None:
                    branch_score = -100.0 * float(selected_shanten) + support_value
                    loss = 0
                    hand_codes = branch.get("hand_codes")
                    if hand_codes is not None:
                        after_wealth = hand_codes.count(wealth)
                        if after_wealth < wealth_count:
                            loss = wealth_count - after_wealth
                        branch_score -= 14.0 * float(loss)
                    followup_key = branch.get("followup_key")
                    if branch_best is None or branch_score > branch_best or (branch_score == branch_best and followup_key is not None and (branch_key is None or followup_key < branch_key)):
                        branch_best = branch_score
                        branch_key = followup_key
                        branch_discard = branch.get("followup_discard")
                        branch_route = selected_route
                        branch_shanten = selected_shanten
                        branch_support = support_value
                        branch_wealth_loss = loss

        family_adjust = 0.0
        family_choice = None
        family_seen = False
        for family in families:
            progress = family.get("progress")
            adjustment = None
            if progress == "advance":
                adjustment = 18.0
            elif progress == "same":
                adjustment = 2.0
            elif progress == "retreat":
                adjustment = -18.0
            elif progress == "close":
                adjustment = -35.0
            elif progress == "unknown":
                adjustment = 0.0
            if adjustment is not None and (family_seen is False or adjustment > family_adjust):
                family_adjust = adjustment
                family_choice = family.get("family")
                family_seen = True

        route_best = None
        route_followup = None
        route_support = None
        route_self_delta = None
        for route in routes:
            followup_discard = route.get("followup_discard")
            compatible = True
            if branch_best is not None and followup_discard != branch_discard:
                compatible = False
            if branch_best is None and followup_discard is not None:
                compatible = False
            shanten = route.get("shanten")
            useful = route.get("useful_tiles")
            conditional = route.get("conditional_settlement")
            if compatible and shanten is not None and shanten is not True and shanten is not False and shanten >= -1 and useful is not None and conditional is not None:
                support = 0.0
                valid = True
                for tile in useful:
                    remaining = tile.get("remaining_estimate")
                    if remaining is None or remaining is True or remaining is False:
                        valid = False
                    else:
                        amount = float(remaining)
                        if amount - amount != 0 or amount < 0:
                            valid = False
                        else:
                            support += amount
                self_delta = conditional.get("self_delta")
                if self_delta is None or self_delta is True or self_delta is False:
                    valid = False
                else:
                    delta_value = float(self_delta)
                    if delta_value - delta_value != 0:
                        valid = False
                if valid:
                    settlement_proxy = delta_value / 20.0
                    if settlement_proxy > 30.0:
                        settlement_proxy = 30.0
                    if settlement_proxy < -20.0:
                        settlement_proxy = -20.0
                    route_score = -100.0 * float(shanten) + 0.5 * support + settlement_proxy - 25.0
                    if route_best is None or route_score > route_best:
                        route_best = route_score
                        route_followup = followup_discard
                        route_support = support
                        route_self_delta = delta_value

        open_opportunity_cost = 0.0
        wealth_open_cost = 0.0
        if kind == "chi" or kind == "peng":
            if pass_seven is not None:
                if pass_standard is None:
                    open_opportunity_cost = 30.0
                elif pass_seven > pass_standard:
                    route_gap = pass_seven - pass_standard
                    if route_gap <= 40.0:
                        open_opportunity_cost = 0.25 * route_gap
                    else:
                        open_opportunity_cost = 10.0 + 0.5 * (route_gap - 40.0)
                    if open_opportunity_cost > 60.0:
                        open_opportunity_cost = 60.0
            if own_meld_count == 0 and wealth_count >= 2:
                wealth_open_cost = 8.0 * float(wealth_count - 1)

        score = None
        basis = None
        if kind == "hu":
            score = 0.0
            basis = "hu_dynamic_layer"
        elif branch_best is not None:
            score = branch_best + family_adjust - open_opportunity_cost - wealth_open_cost
            basis = "best_followup_branch"
            if route_best is not None and route_best + family_adjust - open_opportunity_cost - wealth_open_cost > score:
                score = route_best + family_adjust - open_opportunity_cost - wealth_open_cost
                basis = "compatible_conditional_route"
        elif direct_score is not None:
            score = direct_score + family_adjust
            basis = "best_exclusive_direct_route"
            if route_best is not None and route_best + family_adjust > score:
                score = route_best + family_adjust
                basis = "compatible_conditional_route"
        elif settlement is not None:
            self_delta = settlement.get("self_delta")
            if self_delta is not None and self_delta is not True and self_delta is not False:
                delta_value = float(self_delta)
                if delta_value - delta_value == 0:
                    score = delta_value / 10.0 + family_adjust
                    basis = "immediate_settlement_proxy"
        elif route_best is not None:
            score = route_best + family_adjust - open_opportunity_cost - wealth_open_cost
            basis = "conditional_route_only"
        elif family_seen:
            score = -300.0 + family_adjust - open_opportunity_cost - wealth_open_cost
            basis = "family_evidence_only"
        elif produced:
            score = -400.0 - open_opportunity_cost - wealth_open_cost
            basis = "produced_low_information"

        wealth_discard_cost = 0.0
        if score is not None and kind == "discard" and len(key) > 8 and key[8:] == wealth:
            wealth_discard_cost = 50.0
            score -= wealth_discard_cost
        if score is not None and (score - score != 0):
            return {"status": "ABSTAIN", "reason": "已生产评分产生非有限数"}

        unknown = score is None
        trace = {
            "mechanism_version": "exclusive_route_branch_tradeoff/1",
            "basis": basis,
            "unknown": unknown,
            "unknown_facts": "no_produced_action_branch_route_settlement_or_family_fact" if unknown else None,
            "unknown_policy": "known_final_floor_minus_1" if unknown else None,
            "direct_route": direct_route,
            "direct_shanten": direct_shanten,
            "direct_support_remaining": direct_support,
            "selected_followup_key": branch_key,
            "selected_followup_discard": branch_discard,
            "branch_route": branch_route,
            "branch_shanten": branch_shanten,
            "branch_support_remaining": branch_support,
            "branch_wealth_loss": branch_wealth_loss,
            "family_choice": family_choice,
            "family_adjust": family_adjust,
            "open_opportunity_cost": open_opportunity_cost,
            "wealth_open_cost": wealth_open_cost,
            "conditional_route_followup": route_followup,
            "conditional_route_support": route_support,
            "conditional_route_self_delta": route_self_delta,
            "wealth_discard_cost": wealth_discard_cost,
            "combination": "max_compatible_route_then_conditional_costs",
            "competition_used": False
        }
        pending.append({"action_key": key, "action_type": kind, "score": score, "trace": trace})
        if score is not None:
            known_scores.append(score)

    if len(known_scores) == 0:
        return {"status": "ABSTAIN", "reason": "全部动作均无已生产事实，未知不能取零分"}

    non_hu_top = None
    for item in pending:
        if item.get("score") is not None and item.get("action_type") != "hu":
            value = item.get("score")
            if non_hu_top is None or value > non_hu_top:
                non_hu_top = value
    hu_score = 1000.0
    if non_hu_top is not None:
        hu_score = non_hu_top + 1.0

    known_floor = None
    for item in pending:
        value = item.get("score")
        if value is not None:
            if item.get("action_type") == "hu":
                value = hu_score
            if known_floor is None or value < known_floor:
                known_floor = value
    if known_floor is None:
        return {"status": "ABSTAIN", "reason": "没有可用已知最终评分，未知不能取零分"}

    entries = []
    for item in pending:
        score = item.get("score")
        if item.get("action_type") == "hu":
            score = hu_score
        elif score is None:
            score = known_floor - 1.0
        score = round(score, 6)
        entries.append({"action_key": item.get("action_key"), "score": score, "trace": item.get("trace")})
    return {"status": "SCORED", "entries": entries, "reason": "互斥路线取最大值；吃碰按真实弃牌分支；未知严格锚定在已知最终最低分以下"}
