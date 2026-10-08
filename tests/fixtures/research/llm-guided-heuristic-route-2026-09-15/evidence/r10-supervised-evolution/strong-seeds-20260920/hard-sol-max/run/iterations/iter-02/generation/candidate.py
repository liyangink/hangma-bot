"""分支提速、七对选择权与财神保留的完整动作评分器。"""


def score_actions(view):
    """只使用 sitin-scoring-view/3 的可见事实，为全部合法动作评分。"""

    def number_value(item):
        if item is None or item is True or item is False:
            return None
        value = float(item)
        if value - value != 0:
            return None
        if value < -1000000000.0 or value > 1000000000.0:
            return None
        return value

    def shanten_value(item):
        value = number_value(item)
        if value is None or value < -1.0 or value > 13.0:
            return None
        whole = int(value)
        if value != float(whole):
            return None
        return whole

    def support_total(items):
        if items is None:
            return None
        total = 0.0
        for item in items:
            remaining = number_value(item.get("remaining_estimate"))
            if remaining is None or remaining < 0.0 or remaining > 4.0:
                return None
            whole = int(remaining)
            if remaining != float(whole):
                return None
            total += remaining
        if total > 256.0:
            return None
        return total

    def branch_support(item):
        value = number_value(item)
        if value is None or value < 0.0 or value > 256.0:
            return None
        whole = int(value)
        if value != float(whole):
            return None
        return value

    def support_score(amount):
        if amount <= 8.0:
            return 2.5 * amount
        if amount <= 24.0:
            return 20.0 + 1.5 * (amount - 8.0)
        return 44.0 + 0.75 * (amount - 24.0)

    def option_score(standard, seven):
        if standard is None or seven is None:
            return 0.0
        gap = abs(float(standard - seven))
        if gap == 0.0:
            return 18.0
        if gap == 1.0:
            return 10.0
        if gap == 2.0:
            return 4.0
        return 0.0

    def wealth_score(count):
        if count <= 0:
            return 0.0
        if count == 1:
            return 18.0
        if count == 2:
            return 46.0
        if count == 3:
            return 82.0
        return 126.0 + 10.0 * float(count - 4)

    def family_evidence(entries):
        adjustment = 0.0
        label = None
        present = False
        if entries is None:
            return {"adjustment": adjustment, "label": label, "present": present}
        for entry in entries:
            present = True
            progress = entry.get("progress")
            state = entry.get("route_status")
            candidate = 0.0
            candidate_label = None
            if progress == "close" and state == "closed_proven":
                candidate = -24.0
                candidate_label = "closed_proven_close"
            elif progress == "retreat" and state != "unanalyzed":
                candidate = -14.0
                candidate_label = "evidenced_retreat"
            elif progress == "advance" and state == "witnessed":
                candidate = 14.0
                candidate_label = "witnessed_advance"
            elif progress == "advance" and state == "open_uncertain":
                candidate = 7.0
                candidate_label = "open_uncertain_advance"
            elif progress == "same" and state == "witnessed":
                candidate = 2.0
                candidate_label = "witnessed_same"
            if abs(candidate) > abs(adjustment) or (
                    abs(candidate) == abs(adjustment) and candidate < adjustment):
                adjustment = candidate
                label = candidate_label
        return {"adjustment": adjustment, "label": label, "present": present}

    def branch_evidence(branch):
        progress = branch.get("progress")
        state = branch.get("route_state")
        if state is None:
            state = branch.get("route_status")
        if progress == "advance" or progress == "ADVANCE":
            if state == "witnessed" or state == "WITNESSED":
                return {"adjustment": 10.0, "label": "branch_witnessed_advance"}
            if state == "open_uncertain" or state == "OPEN_UNCERTAIN":
                return {"adjustment": 5.0, "label": "branch_open_uncertain_advance"}
        if progress == "close" or progress == "CLOSE":
            if state == "closed_proven" or state == "CLOSED_PROVEN":
                return {"adjustment": -18.0, "label": "branch_closed_proven_close"}
        if progress == "retreat" or progress == "RETREAT":
            return {"adjustment": -10.0, "label": "branch_retreat"}
        return {"adjustment": 0.0, "label": None}

    def dominant_evidence(action_evidence, branch_result):
        action_adjustment = action_evidence.get("adjustment")
        branch_adjustment = branch_result.get("adjustment")
        if abs(branch_adjustment) > abs(action_adjustment) or (
                abs(branch_adjustment) == abs(action_adjustment)
                and branch_adjustment < action_adjustment):
            return {"adjustment": branch_adjustment,
                    "label": branch_result.get("label")}
        return {"adjustment": action_adjustment,
                "label": action_evidence.get("label")}

    def route_signal(routes, followup_discard, filter_followup):
        found = False
        best = None
        best_support = None
        best_followup = None
        if routes is None:
            return {"found": found, "score": best, "support": best_support,
                    "followup": best_followup}
        for route in routes:
            route_followup = route.get("followup_discard")
            if filter_followup and route_followup != followup_discard:
                continue
            settlement = route.get("conditional_settlement")
            useful = route.get("useful_tiles")
            if settlement is None or useful is None:
                continue
            self_delta = number_value(settlement.get("self_delta"))
            route_support = support_total(useful)
            if self_delta is None or route_support is None:
                continue
            settlement_shape = 32.0 * self_delta / (abs(self_delta) + 100.0)
            candidate = 0.5 * support_score(route_support) + settlement_shape
            if best is None or candidate > best:
                found = True
                best = candidate
                best_support = route_support
                best_followup = route_followup
        return {"found": found, "score": best, "support": best_support,
                "followup": best_followup}

    def settlement_signal(settlement):
        if settlement is None:
            return None
        self_delta = number_value(settlement.get("self_delta"))
        score_delta = settlement.get("score_delta")
        if self_delta is None or score_delta is None or len(score_delta) != 4:
            return None
        for item in score_delta:
            if number_value(item) is None:
                return None
        return 100.0 + 64.0 * self_delta / (abs(self_delta) + 100.0)

    def retained_wealth(current, discard_code, hand_codes, wealth):
        if hand_codes is not None:
            if len(hand_codes) > 32:
                return None
            return hand_codes.count(wealth)
        retained = current
        if discard_code == wealth:
            retained -= 1
        if retained < 0:
            return None
        return retained

    if view.get("schema_version") != "sitin-scoring-view/3":
        return {"status": "ABSTAIN", "entries": [],
                "reason": "评分视图结构版本不匹配"}
    actions = view.get("actions")
    visible = view.get("visible_state")
    if actions is None or visible is None or len(actions) == 0:
        return {"status": "ABSTAIN", "entries": [],
                "reason": "缺少动作表或公开可见状态"}
    seat = visible.get("seat")
    if seat is None or seat is True or seat is False or seat < 0 or seat > 3:
        return {"status": "ABSTAIN", "entries": [],
                "reason": "我方座位不可用"}
    hand = visible.get("my_hand")
    melds = visible.get("melds")
    rule_state = visible.get("rule_state")
    if hand is None or melds is None or rule_state is None:
        return {"status": "ABSTAIN", "entries": [],
                "reason": "牌效取舍所需公开状态缺失"}
    if len(hand) > 32 or len(melds) != 4:
        return {"status": "ABSTAIN", "entries": [],
                "reason": "公开手牌或副露结构不合法"}
    wealth = rule_state.get("wealth_god")
    if wealth is None:
        return {"status": "ABSTAIN", "entries": [],
                "reason": "财神牌码缺失"}
    own_meld_count = len(melds[seat])
    wealth_count = hand.count(wealth)
    drawn = visible.get("drawn_tile")
    if drawn is not None and drawn == wealth and len(hand) != 14 - 3 * own_meld_count:
        wealth_count += 1

    seen = set()
    direct_rows = []
    best_closed_shanten = None
    best_closed_seven = None
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if key is None or kind is None or action.get("is_legal") is not True:
            return {"status": "ABSTAIN", "entries": [],
                    "reason": "动作合法身份、类型或键缺失"}
        if key in seen:
            return {"status": "ABSTAIN", "entries": [],
                    "reason": "动作键重复"}
        seen.add(key)
        if kind not in ("discard", "chi", "peng", "gang", "hu", "pass"):
            return {"status": "ABSTAIN", "entries": [],
                    "reason": "动作类型超出冻结枚举"}
        combined = shanten_value(action.get("shanten_after"))
        standard = shanten_value(action.get("standard_shanten_after"))
        seven = shanten_value(action.get("seven_pairs_shanten_after"))
        direct_support = support_total(action.get("useful_tiles"))
        direct_valid = (action.get("fact_kind") == "hand_progress"
                        and combined is not None and direct_support is not None)
        if kind == "pass" and (action.get("best_followup_discard") is not None
                               or action.get("replacement_draw_unknown") is not False):
            direct_valid = False
        if kind == "gang" and action.get("replacement_draw_unknown") is not False:
            direct_valid = False
        direct_rows.append({"combined": combined, "standard": standard,
                            "seven": seven, "support": direct_support,
                            "valid": direct_valid})
        if kind != "chi" and kind != "peng" and direct_valid:
            if best_closed_shanten is None or combined < best_closed_shanten:
                best_closed_shanten = combined
            if seven is not None and (
                    best_closed_seven is None or seven < best_closed_seven):
                best_closed_seven = seven

    pending = []
    for index in range(len(actions)):
        action = actions[index]
        direct = direct_rows[index]
        key = action.get("action_key")
        kind = action.get("action_type")
        routes = action.get("routes")
        branches = action.get("followup_branches")
        family = family_evidence(action.get("family_progress_entries"))
        known = False
        total = None
        basis = None
        selected_followup = None
        selected_shanten = None
        selected_support = None
        selected_support_score = None
        selected_option = 0.0
        selected_speed_gain = None
        selected_call_tradeoff = 0.0
        selected_seven_loss = 0.0
        selected_route_score = None
        selected_route_support = None
        selected_family_adjustment = family.get("adjustment")
        selected_family_label = family.get("label")
        retained = wealth_count

        if kind == "chi" or kind == "peng":
            best_branch_score = None
            if branches is not None:
                if len(branches) == 0:
                    known = True
                    total = -320.0 + wealth_score(wealth_count) + family.get("adjustment")
                    basis = "known_empty_followup_set"
                for branch in branches:
                    combined = shanten_value(branch.get("combined_shanten"))
                    support = branch_support(branch.get("support_remaining"))
                    if combined is None or support is None:
                        continue
                    standard = shanten_value(branch.get("standard_shanten_after"))
                    seven = shanten_value(branch.get("seven_pairs_shanten_after"))
                    followup = branch.get("followup_discard")
                    hand_codes = branch.get("hand_codes")
                    branch_retained = retained_wealth(
                        wealth_count, followup, hand_codes, wealth)
                    if branch_retained is None:
                        continue
                    transformed_support = support_score(support)
                    option = option_score(standard, seven)
                    core = -120.0 * float(combined) + transformed_support + option
                    route = route_signal(routes, followup, True)
                    route_alternative = None
                    if route.get("found"):
                        route_alternative = -70.0 + route.get("score")
                        if route_alternative > core:
                            core = route_alternative
                    speed_gain = None
                    call_tradeoff = 0.0
                    if best_closed_shanten is not None:
                        speed_gain = best_closed_shanten - combined
                        if speed_gain >= 2:
                            call_tradeoff = 10.0
                        elif speed_gain == 1:
                            call_tradeoff = 6.0
                        elif speed_gain == 0 and kind == "peng":
                            call_tradeoff = -8.0
                        elif speed_gain == 0:
                            call_tradeoff = -12.0
                        else:
                            call_tradeoff = -18.0 * float(-speed_gain)
                    seven_loss = 0.0
                    if seven is None and best_closed_seven is not None \
                            and best_closed_shanten is not None:
                        seven_gap = best_closed_seven - best_closed_shanten
                        raw_loss = 0.0
                        if seven_gap <= 0:
                            raw_loss = 20.0
                        elif seven_gap == 1:
                            raw_loss = 12.0
                        elif seven_gap == 2:
                            raw_loss = 5.0
                        if speed_gain is not None and speed_gain >= 2:
                            raw_loss = 0.0
                        elif speed_gain == 1:
                            raw_loss = 0.4 * raw_loss
                        seven_loss = -raw_loss
                    branch_family = branch_evidence(branch)
                    dominant = dominant_evidence(family, branch_family)
                    branch_score = (core + call_tradeoff + seven_loss
                                    + wealth_score(branch_retained)
                                    + dominant.get("adjustment"))
                    if best_branch_score is None or branch_score > best_branch_score:
                        best_branch_score = branch_score
                        known = True
                        total = branch_score
                        basis = "best_real_followup_branch"
                        selected_followup = followup
                        selected_shanten = combined
                        selected_support = support
                        selected_support_score = transformed_support
                        selected_option = option
                        selected_speed_gain = speed_gain
                        selected_call_tradeoff = call_tradeoff
                        selected_seven_loss = seven_loss
                        selected_route_score = route_alternative
                        selected_route_support = route.get("support")
                        selected_family_adjustment = dominant.get("adjustment")
                        selected_family_label = dominant.get("label")
                        retained = branch_retained
            if not known:
                route = route_signal(routes, None, False)
                if route.get("found"):
                    followup = route.get("followup")
                    branch_retained = retained_wealth(
                        wealth_count, followup, None, wealth)
                    if branch_retained is not None:
                        known = True
                        selected_followup = followup
                        retained = branch_retained
                        selected_route_score = -70.0 + route.get("score")
                        selected_route_support = route.get("support")
                        total = (selected_route_score + wealth_score(retained)
                                 + family.get("adjustment"))
                        basis = "best_compatible_route_only"
            if not known and family.get("present"):
                known = True
                total = -260.0 + wealth_score(retained) + family.get("adjustment")
                basis = "dominant_family_evidence_only"
        else:
            tile_code = None
            if kind == "discard":
                if key[:8] != "discard:":
                    return {"status": "ABSTAIN", "entries": [],
                            "reason": "弃牌动作键格式不合法"}
                tile_code = key[8:]
                retained = retained_wealth(wealth_count, tile_code, None, wealth)
                if retained is None:
                    return {"status": "ABSTAIN", "entries": [],
                            "reason": "财神保留量与弃牌动作矛盾"}
            route = route_signal(routes, None, True)
            if direct.get("valid"):
                selected_shanten = direct.get("combined")
                selected_support = direct.get("support")
                selected_support_score = support_score(selected_support)
                selected_option = option_score(
                    direct.get("standard"), direct.get("seven"))
                core = (-120.0 * float(selected_shanten)
                        + selected_support_score + selected_option)
                if route.get("found"):
                    selected_route_score = -70.0 + route.get("score")
                    selected_route_support = route.get("support")
                    if selected_route_score > core:
                        core = selected_route_score
                        basis = "best_direct_compatible_route"
                if basis is None:
                    basis = "direct_common_efficiency"
                known = True
                total = core + wealth_score(retained) + family.get("adjustment")
            elif route.get("found"):
                known = True
                selected_route_score = -70.0 + route.get("score")
                selected_route_support = route.get("support")
                total = (selected_route_score + wealth_score(retained)
                         + family.get("adjustment"))
                basis = "direct_route_only"
            settlement = settlement_signal(action.get("immediate_settlement"))
            if settlement is not None and (not known or settlement > total):
                known = True
                total = settlement + wealth_score(retained) + family.get("adjustment")
                basis = "immediate_settlement_shape"
            if kind == "hu":
                known = True
                if total is None:
                    total = 0.0
                basis = "legal_hu_dynamic_layer"
            elif not known and family.get("present"):
                known = True
                total = -260.0 + wealth_score(retained) + family.get("adjustment")
                basis = "dominant_family_evidence_only"

        if known:
            total = round(total, 6)
            if total < -4094.0 or total > 4094.0:
                return {"status": "ABSTAIN", "entries": [],
                        "reason": "已知评分超出候选声明数值范围"}
            trace = {
                "mechanism": "branch_route_tradeoff/1",
                "basis": basis,
                "selected_followup": selected_followup,
                "combined_shanten": selected_shanten,
                "support_remaining": selected_support,
                "support_transform": selected_support_score,
                "closed_baseline_shanten": best_closed_shanten,
                "closed_best_seven_pairs": best_closed_seven,
                "family_option": selected_option,
                "call_speed_gain": selected_speed_gain,
                "call_tradeoff": selected_call_tradeoff,
                "seven_pairs_option_loss": selected_seven_loss,
                "route_alternative": selected_route_score,
                "route_support": selected_route_support,
                "retained_wealth": retained,
                "wealth_option": wealth_score(retained),
                "dominant_family_evidence": selected_family_label,
                "family_adjustment": selected_family_adjustment,
                "combination": "max_compatible_evidence_then_corrections",
                "hu_sorting_layer": kind == "hu",
                "unknown": False
            }
            pending.append({"action_key": key, "action_type": kind,
                            "score": total, "trace": trace,
                            "unknown": False})
        else:
            trace = {
                "mechanism": "branch_route_tradeoff/1",
                "basis": "unknown_below_known_floor",
                "unknown": True,
                "unknown_facts": (
                    "usable_direct_efficiency",
                    "usable_followup_branch",
                    "compatible_route_or_settlement_or_family_evidence"
                ),
                "unknown_policy": "known_final_floor_minus_1"
            }
            pending.append({"action_key": key, "action_type": kind,
                            "score": None, "trace": trace,
                            "unknown": True})

    non_hu_max = None
    for item in pending:
        if item.get("unknown") is not True and item.get("action_type") != "hu":
            score = item.get("score")
            if non_hu_max is None or score > non_hu_max:
                non_hu_max = score
    hu_level = 1.0
    if non_hu_max is not None:
        hu_level = non_hu_max + 1.0

    known_floor = None
    for item in pending:
        if item.get("unknown") is not True:
            score = item.get("score")
            if item.get("action_type") == "hu":
                score = hu_level
            if known_floor is None or score < known_floor:
                known_floor = score
    if known_floor is None:
        return {"status": "ABSTAIN", "entries": [],
                "reason": "全部动作均无已生产可评分事实，未知不能取零分"}

    unknown_score = known_floor - 1.0
    if unknown_score < -4096.0:
        return {"status": "ABSTAIN", "entries": [],
                "reason": "未知锚定值超出候选声明数值范围"}
    entries = []
    for item in pending:
        score = item.get("score")
        if item.get("action_type") == "hu" and item.get("unknown") is not True:
            score = hu_level
        if item.get("unknown") is True:
            score = unknown_score
        entries.append({"action_key": item.get("action_key"),
                        "score": score, "trace": item.get("trace")})
    return {"status": "SCORED", "entries": entries,
            "reason": "未知动作严格锚定在最终已知最低分之下；互斥路线只取最佳相容证据"}
