"""候选机制说明：在互斥的闭手、后续弃牌与条件胡路线中取一条同刻度路线，再用可见的确定事实作有界校正。"""

def score_actions(view):
    """按同一动作窗口的只读可见事实，为全部合法动作评分。"""
    if view.get("schema_version") != "sitin-scoring-view/3":
        return {"status": "ABSTAIN", "reason": "候选视图结构版本不兼容"}
    actions = view.get("actions")
    visible = view.get("visible_state")
    if actions is None or visible is None or len(actions) == 0:
        return {"status": "ABSTAIN", "reason": "缺少动作表或公开可见状态"}
    seat = visible.get("seat")
    if seat is None or seat is True or seat is False:
        return {"status": "ABSTAIN", "reason": "我方座位不可用"}
    if seat < 0 or seat > 3 or seat != int(seat):
        return {"status": "ABSTAIN", "reason": "我方座位范围不合法"}
    dealer = visible.get("dealer_seat")
    if dealer is None or dealer is True or dealer is False:
        return {"status": "ABSTAIN", "reason": "庄家座位不可用"}
    if dealer < 0 or dealer > 3 or dealer != int(dealer):
        return {"status": "ABSTAIN", "reason": "庄家座位范围不合法"}
    hand = visible.get("my_hand")
    discards = visible.get("discards")
    melds = visible.get("melds")
    visible_scores = visible.get("table_scores")
    rule_state = visible.get("rule_state")
    if hand is None or discards is None or melds is None or visible_scores is None or rule_state is None:
        return {"status": "ABSTAIN", "reason": "基础公开状态缺失"}
    if len(discards) != 4 or len(melds) != 4 or len(visible_scores) != 4:
        return {"status": "ABSTAIN", "reason": "四座公开状态长度不合法"}
    wealth = rule_state.get("wealth_god")
    if wealth is None:
        return {"status": "ABSTAIN", "reason": "财神牌码缺失"}
    visible_values = []
    for raw_score in visible_scores:
        if raw_score is None or raw_score is True or raw_score is False:
            return {"status": "ABSTAIN", "reason": "本桌积分缺失"}
        score_value = float(raw_score)
        if score_value - score_value != 0:
            return {"status": "ABSTAIN", "reason": "本桌积分非有限"}
        visible_values.append(score_value)
    seen_keys = set()
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if key is None or kind is None or action.get("is_legal") is not True:
            return {"status": "ABSTAIN", "reason": "动作身份、键或合法性缺失"}
        if (kind != "discard" and kind != "chi" and kind != "peng" and
                kind != "gang" and kind != "hu" and kind != "pass"):
            return {"status": "ABSTAIN", "reason": "动作类型不在冻结枚举内"}
        if key in seen_keys:
            return {"status": "ABSTAIN", "reason": "动作键重复"}
        seen_keys.add(key)
    own_meld_count = len(melds[seat])
    wealth_count = hand.count(wealth)
    drawn = visible.get("drawn_tile")
    if drawn == wealth and len(hand) == 14 - 3 * own_meld_count:
        wealth_count += 1
    baotou = rule_state.get("baotou")
    chain_count = rule_state.get("chain_count")
    chain_piao = visible.get("chain_piao")
    gang_draw = visible.get("gang_draw")
    catch_play = rule_state.get("catch_play")
    catch_owner = rule_state.get("catch_play_owner_seat")

    gate_available = False
    gate_inside_before = None
    gate_outside_before = None
    current_values = []
    competition = view.get("competition")
    if competition is not None:
        current_scores = competition.get("current_stage_scores")
        stage_scores = competition.get("stage_scores")
        competition_scores = competition.get("table_scores")
        freshness_masks = competition.get("freshness_masks")
        if (current_scores is not None and stage_scores is not None and
                competition_scores is not None and freshness_masks is not None and
                len(current_scores) == 4 and len(stage_scores) == 4 and
                len(competition_scores) == 4 and len(freshness_masks) == 2 and
                freshness_masks[0] == "stage_account:complete" and
                freshness_masks[1] == "table_account:live"):
            account_ok = True
            for index in range(4):
                raw_current = current_scores[index]
                raw_stage = stage_scores[index]
                raw_table = competition_scores[index]
                if (raw_current is None or raw_current is True or raw_current is False or
                        raw_stage is None or raw_stage is True or raw_stage is False or
                        raw_table is None or raw_table is True or raw_table is False):
                    account_ok = False
                else:
                    current_value = float(raw_current)
                    stage_value = float(raw_stage)
                    table_value = float(raw_table)
                    if (current_value - current_value != 0 or
                            stage_value - stage_value != 0 or
                            table_value - table_value != 0):
                        account_ok = False
                    elif current_value != stage_value + table_value:
                        account_ok = False
                    elif table_value != visible_values[index]:
                        account_ok = False
                    else:
                        current_values.append(current_value)
            if account_ok:
                ordered_current = sorted(current_values)
                gate_inside_before = current_values[seat] - ordered_current[2]
                gate_outside_before = current_values[seat] - ordered_current[1]
                gate_available = True

    temporary = []
    known_scores = []
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        fact_kind = action.get("fact_kind")
        branches = action.get("followup_branches")
        routes = action.get("routes")
        families = action.get("family_progress_entries")
        direct_allowed = True
        if kind == "pass":
            if (action.get("best_followup_discard") is not None or
                    action.get("replacement_draw_unknown") is not False):
                direct_allowed = False
        produced = False
        if fact_kind == "hand_progress" and direct_allowed:
            produced = True
        if fact_kind == "win" or fact_kind == "not_applicable":
            produced = True
        if action.get("immediate_settlement") is not None:
            produced = True
        if (kind == "chi" or kind == "peng") and branches is not None:
            produced = True
        if routes is not None and len(routes) > 0:
            produced = True
        if families is not None and len(families) > 0:
            produced = True
        summary_progress = action.get("family_progress")
        if summary_progress is not None and summary_progress != "UNKNOWN":
            produced = True
        if kind == "hu":
            produced = True

        family_adjust = 0.0
        family_name = None
        family_progress = None
        family_status = None
        family_available = False
        if families is not None:
            for family in families:
                progress = family.get("progress")
                status = family.get("route_status")
                effect = 0.0
                if status == "witnessed":
                    if progress == "advance":
                        effect = 6.0
                    elif progress == "retreat":
                        effect = -6.0
                    elif progress == "close":
                        effect = -8.0
                elif status == "open_uncertain":
                    if progress == "advance":
                        effect = 2.0
                    elif progress == "retreat":
                        effect = -2.0
                    elif progress == "close":
                        effect = -3.0
                elif status == "closed_proven":
                    if progress == "retreat" or progress == "close":
                        effect = -1.0
                if (progress == "advance" or progress == "same" or
                        progress == "retreat" or progress == "close"):
                    family_available = True
                if abs(effect) > abs(family_adjust):
                    family_adjust = effect
                    family_name = family.get("family")
                    family_progress = progress
                    family_status = status
        if not family_available:
            if summary_progress == "ADVANCE":
                family_adjust = 1.0
                family_available = True
                family_name = "summary"
                family_progress = "advance"
                family_status = "unknown"
            elif summary_progress == "RETREAT":
                family_adjust = -1.0
                family_available = True
                family_name = "summary"
                family_progress = "retreat"
                family_status = "unknown"
            elif summary_progress == "CLOSE":
                family_adjust = -2.0
                family_available = True
                family_name = "summary"
                family_progress = "close"
                family_status = "unknown"

        direct_score = None
        direct_basis = None
        direct_shanten = None
        direct_support = None
        seven_pairs_guard = 0.0
        if direct_allowed and fact_kind == "hand_progress":
            combined_shanten = action.get("shanten_after")
            combined_tiles = action.get("useful_tiles")
            if (combined_shanten is not None and combined_shanten is not True and
                    combined_shanten is not False and combined_shanten >= -1 and
                    combined_tiles is not None):
                combined_ok = True
                combined_support = 0.0
                for tile in combined_tiles:
                    remaining = tile.get("remaining_estimate")
                    if remaining is None or remaining is True or remaining is False:
                        combined_ok = False
                    else:
                        amount = float(remaining)
                        if amount - amount != 0 or amount < 0:
                            combined_ok = False
                        else:
                            combined_support += amount
                combined_value = float(combined_shanten)
                if combined_value - combined_value != 0 or combined_value < -1:
                    combined_ok = False
                if combined_ok:
                    direct_score = -100.0 * combined_value + combined_support
                    direct_basis = "combined_hand"
                    direct_shanten = combined_value
                    direct_support = combined_support
            standard_shanten = action.get("standard_shanten_after")
            standard_tiles = action.get("standard_useful_tiles")
            if (standard_shanten is not None and standard_shanten is not True and
                    standard_shanten is not False and standard_shanten >= -1 and
                    standard_tiles is not None):
                standard_ok = True
                standard_support = 0.0
                for tile in standard_tiles:
                    remaining = tile.get("remaining_estimate")
                    if remaining is None or remaining is True or remaining is False:
                        standard_ok = False
                    else:
                        amount = float(remaining)
                        if amount - amount != 0 or amount < 0:
                            standard_ok = False
                        else:
                            standard_support += amount
                standard_value = float(standard_shanten)
                if standard_value - standard_value != 0 or standard_value < -1:
                    standard_ok = False
                if standard_ok:
                    candidate_value = -100.0 * standard_value + standard_support
                    if direct_score is None or candidate_value > direct_score:
                        direct_score = candidate_value
                        direct_basis = "standard_hand"
                        direct_shanten = standard_value
                        direct_support = standard_support
            seven_shanten = action.get("seven_pairs_shanten_after")
            seven_tiles = action.get("seven_pairs_useful_tiles")
            if (own_meld_count == 0 and seven_shanten is not None and
                    seven_shanten is not True and seven_shanten is not False and
                    seven_shanten >= -1 and seven_tiles is not None):
                seven_ok = True
                seven_support = 0.0
                for tile in seven_tiles:
                    remaining = tile.get("remaining_estimate")
                    if remaining is None or remaining is True or remaining is False:
                        seven_ok = False
                    else:
                        amount = float(remaining)
                        if amount - amount != 0 or amount < 0:
                            seven_ok = False
                        else:
                            seven_support += amount
                seven_value = float(seven_shanten)
                if seven_value - seven_value != 0 or seven_value < -1:
                    seven_ok = False
                if seven_ok:
                    candidate_value = -100.0 * seven_value + seven_support
                    if direct_score is None or candidate_value > direct_score:
                        direct_score = candidate_value
                        direct_basis = "seven_pairs_hand"
                        direct_shanten = seven_value
                        direct_support = seven_support
        if direct_basis == "seven_pairs_hand":
            direct_score += 6.0
            seven_pairs_guard = 6.0

        branch_score = None
        branch_key = None
        branch_discard = None
        branch_shanten = None
        branch_support_selected = None
        branch_family_selected = 0.0
        branch_wealth_selected = 0.0
        if (kind == "chi" or kind == "peng") and branches is not None:
            for branch in branches:
                branch_support_raw = branch.get("support_remaining")
                branch_ok = True
                if (branch_support_raw is None or branch_support_raw is True or
                        branch_support_raw is False):
                    branch_ok = False
                    branch_support_value = None
                else:
                    branch_support_value = float(branch_support_raw)
                    if branch_support_value - branch_support_value != 0 or branch_support_value < 0:
                        branch_ok = False
                branch_candidate = None
                branch_value = branch.get("combined_shanten")
                if (branch_ok and branch_value is not None and branch_value is not True and
                        branch_value is not False and branch_value >= -1):
                    branch_shanten_value = float(branch_value)
                    if branch_shanten_value - branch_shanten_value == 0 and branch_shanten_value >= -1:
                        branch_candidate = -100.0 * branch_shanten_value + branch_support_value
                standard_branch = branch.get("standard_shanten_after")
                if (branch_ok and standard_branch is not None and standard_branch is not True and
                        standard_branch is not False and standard_branch >= -1):
                    standard_branch_value = float(standard_branch)
                    if standard_branch_value - standard_branch_value == 0 and standard_branch_value >= -1:
                        candidate_value = -100.0 * standard_branch_value + branch_support_value
                        if branch_candidate is None or candidate_value > branch_candidate:
                            branch_candidate = candidate_value
                            branch_shanten_value = standard_branch_value
                seven_branch = branch.get("seven_pairs_shanten_after")
                if (branch_ok and seven_branch is not None and seven_branch is not True and
                        seven_branch is not False and seven_branch >= -1):
                    seven_branch_value = float(seven_branch)
                    if seven_branch_value - seven_branch_value == 0 and seven_branch_value >= -1:
                        candidate_value = -100.0 * seven_branch_value + branch_support_value
                        if branch_candidate is None or candidate_value > branch_candidate:
                            branch_candidate = candidate_value
                            branch_shanten_value = seven_branch_value
                if branch_candidate is not None:
                    branch_progress = branch.get("progress")
                    branch_status = branch.get("route_state")
                    branch_family_part = 0.0
                    if branch_status == "witnessed":
                        if branch_progress == "advance":
                            branch_family_part = 4.0
                        elif branch_progress == "retreat":
                            branch_family_part = -4.0
                        elif branch_progress == "close":
                            branch_family_part = -5.0
                    elif branch_status == "open_uncertain":
                        if branch_progress == "advance":
                            branch_family_part = 1.0
                        elif branch_progress == "retreat":
                            branch_family_part = -1.0
                        elif branch_progress == "close":
                            branch_family_part = -2.0
                    branch_hand = branch.get("hand_codes")
                    branch_wealth_part = 0.0
                    if branch_hand is not None:
                        branch_wealth_part = 5.0 * (branch_hand.count(wealth) - wealth_count)
                    branch_candidate += branch_family_part + branch_wealth_part
                    if branch_score is None or branch_candidate > branch_score:
                        branch_score = branch_candidate
                        branch_key = branch.get("followup_key")
                        branch_discard = branch.get("followup_discard")
                        branch_shanten = branch_shanten_value
                        branch_support_selected = branch_support_value
                        branch_family_selected = branch_family_part
                        branch_wealth_selected = branch_wealth_part

        expected_meld_count = own_meld_count
        expected_draw_kind = "normal"
        if kind == "chi" or kind == "peng":
            expected_meld_count += 1
        elif kind == "gang":
            expected_draw_kind = "replacement"
            if key[5:11] != "added:":
                expected_meld_count += 1
        route_score = None
        route_discard = None
        route_support_selected = None
        route_fan = None
        route_baotou = None
        route_chain = None
        route_piao = None
        if routes is not None:
            for route in routes:
                conditions = route.get("conditions")
                conditional = route.get("conditional_settlement")
                route_shanten = route.get("shanten")
                if conditions is None or conditional is None:
                    continue
                if conditions.get("draw_kind") != expected_draw_kind:
                    continue
                route_meld_count = conditions.get("meld_count")
                if (route_meld_count is None or route_meld_count is True or
                        route_meld_count is False):
                    continue
                route_meld_value = float(route_meld_count)
                if route_meld_value - route_meld_value != 0 or route_meld_value != expected_meld_count:
                    continue
                if (route_shanten is None or route_shanten is True or route_shanten is False or
                        route_shanten < 0):
                    continue
                route_shanten_value = float(route_shanten)
                if route_shanten_value - route_shanten_value != 0:
                    continue
                route_tiles = route.get("useful_tiles")
                if route_tiles is None:
                    continue
                route_ok = True
                route_support = 0.0
                for tile in route_tiles:
                    remaining = tile.get("remaining_estimate")
                    if remaining is None or remaining is True or remaining is False:
                        route_ok = False
                    else:
                        amount = float(remaining)
                        if amount - amount != 0 or amount < 0:
                            route_ok = False
                        else:
                            route_support += amount
                route_self = conditional.get("self_delta")
                if route_self is None or route_self is True or route_self is False:
                    route_ok = False
                else:
                    route_self_value = float(route_self)
                    if route_self_value - route_self_value != 0:
                        route_ok = False
                route_fan_value = 0.0
                raw_fan = conditional.get("fan")
                if raw_fan is not None and raw_fan is not True and raw_fan is not False:
                    candidate_fan = float(raw_fan)
                    if candidate_fan - candidate_fan == 0 and candidate_fan >= 0:
                        route_fan_value = candidate_fan
                if route_ok:
                    candidate_value = (-100.0 * route_shanten_value + route_support +
                                       0.08 * route_self_value + 1.5 * route_fan_value)
                    if route_score is None or candidate_value > route_score:
                        route_score = candidate_value
                        route_discard = route.get("followup_discard")
                        route_support_selected = route_support
                        route_fan = route_fan_value
                        route_baotou = conditions.get("baotou")
                        route_chain = conditions.get("chain_count")
                        route_piao = conditions.get("chain_piao")

        settlement_known = False
        settlement_part = 0.0
        settlement_score = None
        settlement_self = None
        gate_mode = None
        gate_inside_delta = None
        gate_outside_delta = None
        settlement = action.get("immediate_settlement")
        if settlement is not None:
            settlement_delta = settlement.get("score_delta")
            settlement_values = []
            settlement_ok = True
            if settlement_delta is None or len(settlement_delta) != 4:
                settlement_ok = False
            else:
                for raw_delta in settlement_delta:
                    if raw_delta is None or raw_delta is True or raw_delta is False:
                        settlement_ok = False
                    else:
                        delta_value = float(raw_delta)
                        if delta_value - delta_value != 0:
                            settlement_ok = False
                        else:
                            settlement_values.append(delta_value)
            if settlement_ok:
                settlement_known = True
                settlement_self = settlement_values[seat]
                settlement_part = 0.15 * settlement_self
                gate_mode = "no_stage_account"
                if gate_available:
                    updated_values = []
                    for index in range(4):
                        updated_values.append(current_values[index] + settlement_values[index])
                    ordered_updated = sorted(updated_values)
                    inside_after = updated_values[seat] - ordered_updated[2]
                    outside_after = updated_values[seat] - ordered_updated[1]
                    gate_inside_delta = inside_after - gate_inside_before
                    gate_outside_delta = outside_after - gate_outside_before
                    settlement_part += 0.30 * gate_inside_delta + 0.10 * gate_outside_delta
                    gate_mode = "recompute_current_stage_scores"
                settlement_score = 150.0 + settlement_part

        progress_score = direct_score
        progress_basis = direct_basis
        progress_shanten = direct_shanten
        progress_support = direct_support
        if branch_score is not None and (progress_score is None or branch_score > progress_score):
            progress_score = branch_score
            progress_basis = "followup_branch"
            progress_shanten = branch_shanten
            progress_support = branch_support_selected

        base_score = None
        basis = None
        applied_family_part = 0.0
        if kind == "hu":
            base_score = 1000.0
            basis = "immediate_hu_priority"
            if settlement_known:
                base_score += settlement_part
        else:
            if progress_score is not None:
                base_score = progress_score
                basis = progress_basis
            if route_score is not None and (base_score is None or route_score > base_score):
                base_score = route_score
                basis = "conditional_route"
            if settlement_score is not None and (base_score is None or settlement_score > base_score):
                base_score = settlement_score
                basis = "immediate_settlement"
            if (basis == "combined_hand" or basis == "standard_hand" or
                    basis == "seven_pairs_hand"):
                base_score += family_adjust
                applied_family_part = family_adjust
            elif base_score is None and family_available:
                base_score = family_adjust
                basis = "family_evidence_only"
                applied_family_part = family_adjust
            elif base_score is None and produced:
                base_score = 0.0
                basis = "produced_no_numeric_lane"

        call_commitment = 0.0
        if base_score is not None:
            if kind == "chi":
                call_commitment = -4.0
            elif kind == "peng":
                call_commitment = -5.0

        wealth_delta = 0.0
        wealth_discard_penalty = 0.0
        river_part = 0.0
        open_speed_risk = 0.0
        catch_part = 0.0
        familiar = False
        if basis == "followup_branch":
            wealth_delta = branch_wealth_selected
        if kind == "discard":
            tile_code = key[8:]
            if tile_code == wealth:
                wealth_delta = -5.0
                wealth_discard_penalty = -60.0
            for river in discards:
                if river.count(tile_code) > 0:
                    familiar = True
            if familiar:
                river_part = 3.0
            elif (len(tile_code) >= 2 and tile_code[0] in "123456789" and
                    tile_code[-1] in "wbt"):
                suit = tile_code[-1]
                rank = int(tile_code[0])
                next_seat = (seat + 1) % 4
                near_next = False
                near_dealer = False
                for meld in melds[next_seat]:
                    meld_tiles = meld.get("tiles")
                    if meld_tiles is not None:
                        for other in meld_tiles:
                            if (len(other) >= 2 and other[0] in "123456789" and
                                    other[-1] == suit and abs(int(other[0]) - rank) <= 2):
                                near_next = True
                if dealer != seat:
                    for meld in melds[dealer]:
                        meld_tiles = meld.get("tiles")
                        if meld_tiles is not None:
                            for other in meld_tiles:
                                if (len(other) >= 2 and other[0] in "123456789" and
                                        other[-1] == suit and abs(int(other[0]) - rank) <= 2):
                                    near_dealer = True
                if near_next:
                    open_speed_risk -= 4.0
                if near_dealer:
                    open_speed_risk -= 2.0
                if catch_play is True:
                    if catch_owner == next_seat:
                        catch_part = -1.0
                    elif dealer != seat and catch_owner == dealer:
                        catch_part = -0.5

        unknown = base_score is None
        unknown_facts = []
        if unknown:
            unknown_facts.append("no_produced_hand_branch_route_settlement_or_family_fact")
            total = None
        else:
            total = base_score + call_commitment
            if kind == "discard":
                total += wealth_delta + wealth_discard_penalty
                total += river_part + open_speed_risk + catch_part
            if total - total != 0:
                return {"status": "ABSTAIN", "reason": "候选计算得到非有限评分"}
            known_scores.append(total)
        temporary.append({
            "action_key": key,
            "action_type": kind,
            "score": total,
            "unknown": unknown,
            "basis": basis,
            "progress_shanten": progress_shanten,
            "progress_support": progress_support,
            "branch_key": branch_key,
            "branch_discard": branch_discard,
            "branch_family_part": branch_family_selected,
            "branch_wealth_part": branch_wealth_selected,
            "route_discard": route_discard,
            "route_support": route_support_selected,
            "route_fan": route_fan,
            "route_baotou": route_baotou,
            "route_chain": route_chain,
            "route_piao": route_piao,
            "family_name": family_name,
            "family_progress": family_progress,
            "family_status": family_status,
            "family_part": applied_family_part,
            "seven_pairs_guard": seven_pairs_guard,
            "call_commitment": call_commitment,
            "wealth_delta": wealth_delta,
            "wealth_discard_penalty": wealth_discard_penalty,
            "river_part": river_part,
            "open_speed_risk": open_speed_risk,
            "catch_part": catch_part,
            "settlement_part": settlement_part,
            "settlement_self": settlement_self,
            "gate_mode": gate_mode,
            "gate_inside_delta": gate_inside_delta,
            "gate_outside_delta": gate_outside_delta,
            "unknown_facts": unknown_facts
        })
    if len(known_scores) == 0:
        return {"status": "ABSTAIN", "reason": "全部动作均无已生产事实，未知不能取零分"}
    known_floor = min(known_scores)
    entries = []
    for item in temporary:
        final_score = item.get("score")
        unknown_policy = None
        if item.get("unknown") is True:
            final_score = known_floor - 1.0
            unknown_policy = "known_final_floor_minus_1"
        trace = {
            "basis": item.get("basis"),
            "action_type": item.get("action_type"),
            "progress_shanten": item.get("progress_shanten"),
            "progress_support": item.get("progress_support"),
            "selected_branch": item.get("branch_key"),
            "branch_discard": item.get("branch_discard"),
            "branch_family_part": item.get("branch_family_part"),
            "branch_wealth_part": item.get("branch_wealth_part"),
            "route_discard": item.get("route_discard"),
            "route_support": item.get("route_support"),
            "route_fan": item.get("route_fan"),
            "route_condition_baotou": item.get("route_baotou"),
            "route_condition_chain_count": item.get("route_chain"),
            "route_condition_chain_piao": item.get("route_piao"),
            "family": item.get("family_name"),
            "family_progress": item.get("family_progress"),
            "family_route_status": item.get("family_status"),
            "family_part": item.get("family_part"),
            "seven_pairs_guard": item.get("seven_pairs_guard"),
            "call_commitment": item.get("call_commitment"),
            "wealth_delta": item.get("wealth_delta"),
            "wealth_discard_penalty": item.get("wealth_discard_penalty"),
            "river_part": item.get("river_part"),
            "open_speed_risk": item.get("open_speed_risk"),
            "catch_play_part": item.get("catch_part"),
            "settlement_part": item.get("settlement_part"),
            "settlement_self_delta": item.get("settlement_self"),
            "gate_mode": item.get("gate_mode"),
            "gate_inside_delta": item.get("gate_inside_delta"),
            "gate_outside_delta": item.get("gate_outside_delta"),
            "observed_baotou": baotou,
            "observed_chain_count": chain_count,
            "observed_chain_piao": chain_piao,
            "observed_gang_draw": gang_draw,
            "unknown": item.get("unknown"),
            "unknown_facts": item.get("unknown_facts"),
            "unknown_policy": unknown_policy,
            "route_combination": "one_best_lane_no_mutually_exclusive_sum"
        }
        entries.append({"action_key": item.get("action_key"), "score": final_score, "trace": trace})
    return {
        "status": "SCORED",
        "entries": entries,
        "reason": "互斥路线只取一条；没有已生产事实的动作严格锚定在已知最终最低分以下"
    }
