"""候选机制说明：统一等待态刻度，互斥七对与条件路线择优，显式证据约束副露机会损失。"""

def score_actions(view):
    """按同一动作窗口的只读可见事实，为全部合法动作评分。"""
    def number(value):
        """读取有限数；空值与布尔均保持未知。"""
        if value is None or value is True or value is False:
            return None
        result = float(value)
        if result - result != 0:
            return None
        return result

    def shanten_value(value):
        """仅读取已生产向听，不重算牌型。"""
        result = number(value)
        if result is None or result < 0 or result > 13 or result != int(result):
            return None
        return result

    def support_value(tiles):
        """直接牌效或路线映射的未见枚数；空集合是已知零。"""
        if tiles is None:
            return None
        total = 0.0
        seen = set()
        for tile in tiles:
            code = tile.get("code")
            count = number(tile.get("remaining_estimate"))
            if code is None or count is None or count < 0 or count > 4 or code in seen:
                return None
            seen.add(code)
            total += count
        return total

    def progress_option(shanten, support, seven, seven_support):
        """互斥牌型取最大值，评分点刻度始终为负百倍向听加支持。"""
        core = None
        source = None
        if shanten is not None and support is not None:
            core = -100.0 * shanten + support
            source = "combined"
        if seven is not None and seven_support is not None:
            pair_score = -100.0 * seven + seven_support + 24.0 / (seven + 1.0)
            if core is None or pair_score > core:
                core = pair_score
                source = "seven_pairs"
        return {"core": core, "source": source}

    actions = view.get("actions")
    visible = view.get("visible_state")
    if actions is None or visible is None or len(actions) == 0:
        return {"status": "ABSTAIN", "reason": "缺少合法动作表或公开观察"}
    seat = visible.get("seat")
    hand = visible.get("my_hand")
    melds = visible.get("melds")
    rule = visible.get("rule_state")
    if seat is None or seat is True or seat is False or seat not in (0, 1, 2, 3):
        return {"status": "ABSTAIN", "reason": "我方座位不可用"}
    if hand is None or melds is None or len(melds) != 4 or rule is None:
        return {"status": "ABSTAIN", "reason": "手牌、副露或公开规则状态缺失"}
    wealth = rule.get("wealth_god")
    if wealth is None:
        return {"status": "ABSTAIN", "reason": "财神牌码缺失"}
    wealth_count = hand.count(wealth)
    drawn = visible.get("drawn_tile")
    if drawn == wealth and len(hand) != 14 - 3 * len(melds[seat]):
        wealth_count += 1

    def retained_wealth(kind, key, discard, branch_hand):
        """优先使用机械转移手牌；缺省只做公开动作的牌张收支。"""
        if branch_hand is not None:
            return branch_hand.count(wealth)
        count = wealth_count
        if kind == "peng" and key[5:] == wealth:
            count -= 2
        elif kind == "chi":
            removed = key.count(wealth)
            last = visible.get("last_discard")
            if last is not None and last.get("tile") == wealth:
                removed -= 1
            count -= max(0, removed)
        elif kind == "gang":
            if key == "gang:concealed:" + wealth:
                count -= 4
            elif key == "gang:added:" + wealth:
                count -= 1
            elif key == "gang:exposed:" + wealth:
                count -= 3
        if discard == wealth:
            count -= 1
        return max(0, count)

    def complete_option(core, source, discard, branch_key, retained, route_index, release):
        """完整选项包括同一个后续弃牌的牌效、财神保留与弃财神代价。"""
        penalty = 0.0
        if discard == wealth:
            penalty = -8.0 if release else -48.0
        score = core + 5.0 * retained + penalty
        return {"score": score, "source": source, "followup": branch_key,
                "discard": discard, "route": route_index,
                "retained_wealth": retained, "wealth_discard_cost": penalty}

    pass_families = []
    keys = set()
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if key is None or key in keys or action.get("is_legal") is not True:
            return {"status": "ABSTAIN", "reason": "动作键重复、缺失或合法身份缺失"}
        if kind not in ("discard", "chi", "peng", "gang", "hu", "pass"):
            return {"status": "ABSTAIN", "reason": "动作类型不受支持"}
        keys.add(key)
        if kind == "pass":
            families = action.get("family_progress_entries")
            if families is not None:
                for family in families:
                    if family.get("route_status") in ("witnessed", "open_uncertain"):
                        pass_families.append(family)

    records = []
    numerical_scores = []
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        branches = action.get("followup_branches")
        routes = action.get("routes")
        families = action.get("family_progress_entries")
        fact_kind = action.get("fact_kind")
        produced = action.get("immediate_settlement") is not None
        if fact_kind == "win":
            produced = True
        if fact_kind == "hand_progress" and action.get("shanten_after") is not None:
            produced = True
        if branches is not None or (routes is not None and len(routes) > 0):
            produced = True
        if families is not None and len(families) > 0:
            produced = True
        options = []
        missing = []
        family_cost = 0.0
        if kind in ("chi", "peng") and families is not None:
            for family in families:
                if family.get("route_status") == "closed_proven":
                    for before in pass_families:
                        if before.get("family") == family.get("family"):
                            loss = 8.0 if before.get("route_status") == "witnessed" else 3.0
                            family_cost = max(family_cost, loss)

        has_real_branches = kind in ("chi", "peng") and branches is not None and len(branches) > 0
        if fact_kind == "hand_progress" and not has_real_branches:
            pass_ok = kind != "pass" or (action.get("best_followup_discard") is None and action.get("replacement_draw_unknown") is False)
            if pass_ok:
                shanten = shanten_value(action.get("shanten_after"))
                support = support_value(action.get("useful_tiles"))
                seven = shanten_value(action.get("seven_pairs_shanten_after"))
                seven_support = support_value(action.get("seven_pairs_useful_tiles"))
                if kind in ("chi", "peng") or len(melds[seat]) > 0:
                    seven = None
                    seven_support = None
                option = progress_option(shanten, support, seven, seven_support)
                discard = key[8:] if kind == "discard" else action.get("best_followup_discard")
                if kind in ("chi", "peng") and discard is None:
                    missing.append("best_followup_discard")
                elif option.get("core") is not None:
                    retained = retained_wealth(kind, key, discard, None)
                    options.append(complete_option(option.get("core"), option.get("source"), discard, None, retained, None, False))
                else:
                    missing.append("direct_progress_or_support")
            else:
                missing.append("pass_waiting_baseline")

        if has_real_branches:
            for branch in branches:
                branch_key = branch.get("followup_key")
                discard = branch.get("followup_discard")
                if discard is None and branch_key is not None and branch_key[:len(key) + 1] == key + "#":
                    discard = branch_key[len(key) + 1:]
                if discard is None or branch_key is None or branch_key != key + "#" + discard:
                    return {"status": "ABSTAIN", "reason": "吃碰后续弃牌分支身份缺失或不一致"}
                shanten = shanten_value(branch.get("combined_shanten"))
                support = number(branch.get("support_remaining"))
                if support is not None and support < 0:
                    support = None
                option = progress_option(shanten, support, None, None)
                if option.get("core") is not None:
                    retained = retained_wealth(kind, key, discard, branch.get("hand_codes"))
                    options.append(complete_option(option.get("core"), "followup_combined", discard, branch_key, retained, None, False))
                else:
                    missing.append(branch_key)

        if routes is not None:
            for route_index, route in enumerate(routes):
                conditions = route.get("conditions")
                settlement = route.get("conditional_settlement")
                support = support_value(route.get("useful_tiles"))
                route_shanten = shanten_value(route.get("shanten"))
                if conditions is None or settlement is None or support is None or route_shanten != 0:
                    missing.append("route_numeric_or_conditions")
                    continue
                fan = number(settlement.get("fan"))
                draw_kind = conditions.get("draw_kind")
                if fan is None or fan <= 0 or draw_kind not in ("normal", "replacement"):
                    missing.append("route_fan_or_draw_kind")
                    continue
                if support <= 0:
                    continue
                discard = route.get("followup_discard")
                branch_key = None
                compatible = True
                if kind in ("chi", "peng"):
                    compatible = False
                    if branches is not None:
                        for branch in branches:
                            current_key = branch.get("followup_key")
                            if discard is not None and current_key == key + "#" + discard:
                                compatible = True
                                branch_key = current_key
                    if branches is None and discard is not None and discard == action.get("best_followup_discard"):
                        compatible = True
                elif discard is not None:
                    compatible = False
                if not compatible:
                    missing.append("route_followup_compatibility")
                    continue
                if kind == "discard":
                    discard = key[8:]
                # 一条路线是完整条件选项；不累加别的路线或整个直接支持集合。
                premium = 36.0 * support / (support + 8.0) * fan / (fan + 2.0)
                core = support + premium
                if draw_kind == "replacement":
                    core -= 4.0
                prehand = conditions.get("pre_draw_hand")
                retained = retained_wealth(kind, key, discard, prehand)
                piao = number(conditions.get("chain_piao"))
                release = conditions.get("baotou") is True or (piao is not None and piao > 0)
                options.append(complete_option(core, "conditional_route", discard, branch_key, retained, route_index, release))

        best = None
        for option in options:
            if best is None or option.get("score") > best.get("score"):
                best = option
            elif option.get("score") == best.get("score"):
                current = option.get("followup")
                previous = best.get("followup")
                if current is not None and previous is not None and current < previous:
                    best = option
        score = None
        source = "unknown"
        if kind == "hu" and produced:
            score = 1000.0
            source = "immediate_hu_priority"
        elif best is not None:
            produced = True
            score = best.get("score") - family_cost
            source = best.get("source")
        elif produced:
            source = "evidence_without_numeric_tempo"
            missing.append("usable_numeric_wait_option")
        else:
            missing.append("hand_progress/followup_branches/routes/immediate_settlement/family_progress_entries")
        if score is not None:
            if score - score != 0 or abs(score) > 1000000:
                return {"status": "ABSTAIN", "reason": "评分超出声明的有限数值范围"}
            numerical_scores.append(score)
        records.append({"key": key, "kind": kind, "score": score,
                        "produced": produced, "source": source, "best": best,
                        "family_cost": family_cost, "missing": missing})

    if len(numerical_scores) == 0:
        return {"status": "ABSTAIN", "reason": "没有可用数值事实，不能把全未知或仅家族证据写成零分"}
    evidence_anchor = min(numerical_scores) - 2.0
    provisional = []
    non_hu_high = None
    for record in records:
        score = record.get("score")
        if score is None and record.get("produced"):
            score = evidence_anchor - record.get("family_cost")
        if score is not None and record.get("kind") != "hu":
            if non_hu_high is None or score > non_hu_high:
                non_hu_high = score
        provisional.append({"record": record, "score": score})
    known_scores = []
    resolved = []
    for item in provisional:
        record = item.get("record")
        score = item.get("score")
        if score is not None and record.get("kind") == "hu" and non_hu_high is not None:
            score = non_hu_high + 1.0
        if score is not None:
            known_scores.append(score)
        resolved.append({"record": record, "score": score})
    if len(known_scores) == 0:
        return {"status": "ABSTAIN", "reason": "已知最终分为空"}
    unknown_score = min(known_scores) - 1.0
    entries = []
    for item in resolved:
        record = item.get("record")
        score = item.get("score")
        unknown = not record.get("produced")
        if score is None:
            score = unknown_score
        if score - score != 0 or abs(score) > 1000000:
            return {"status": "ABSTAIN", "reason": "最终评分超出声明范围"}
        entries.append({"action_key": record.get("key"), "score": score,
                        "trace": {"version": "wait-option-envelope/1",
                                  "basis": record.get("source"),
                                  "selected_option": record.get("best"),
                                  "family_opportunity_cost": record.get("family_cost"),
                                  "unknown": unknown,
                                  "unknown_facts": record.get("missing"),
                                  "unknown_policy": "known_final_floor_minus_1" if unknown else None,
                                  "evidence_only_anchor": evidence_anchor if record.get("source") == "evidence_without_numeric_tempo" else None,
                                  "stage_account_used": False}})
    return {"status": "SCORED", "entries": entries,
            "reason": "同刻度完整等待选项取最大；立即胡优先；未知严格低于全部已知最终分"}
