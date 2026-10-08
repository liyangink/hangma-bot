"""候选机制说明：以稳定 V2 为可执行骨架，仅当 chi/peng 携带完整 followup_branches 且相对可见闭手基线的提速、七对与财神机会损失全部可核时，对该动作叠加 ±24 有界的 claim_branch_rebase/1，未触发时全部动作逐点退化为 V2 排序。"""

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
    last_fact = visible.get("last_discard")
    last_tile = None
    if last_fact is not None:
        last_tile = last_fact.get("tile")

    def claim_rebase(kind, key, branches, wealth, wealth_count, baseline_sh, baseline_sev, last_tile, meld_count):
        triggered = False
        value = 0.0
        reason = None
        branch_shanten = None
        speed_gain = None
        seven_loss = None
        wealth_units = None
        followup = None
        branch_count = None
        if baseline_sh is None:
            reason = "closed_baseline_shanten_unavailable"
        elif branches is None:
            reason = "followup_branches_absent"
        elif len(branches) == 0:
            reason = "followup_branches_known_empty"
        elif last_tile is None or last_tile is True or last_tile is False:
            reason = "river_claim_tile_unavailable"
        elif meld_count == 0 and baseline_sev is None:
            reason = "seven_pairs_loss_unverifiable"
        else:
            meld_wealth_units = 0.0
            shape_ok = True
            if kind == "peng":
                if key[:5] != "peng:" or key.count(",") != 0 or last_tile != key[5:]:
                    shape_ok = False
                    reason = "peng_key_or_river_tile_invalid"
                elif key[5:] == wealth:
                    meld_wealth_units = 2.0
            else:
                if key[:4] != "chi:" or key.count(",") != 2:
                    shape_ok = False
                    reason = "chi_key_shape_invalid"
                else:
                    i1 = key.index(",", 4)
                    i2 = key.index(",", i1 + 1)
                    t1 = key[4:i1]
                    t2 = key[i1 + 1:i2]
                    t3 = key[i2 + 1:]
                    if last_tile != t1 and last_tile != t2 and last_tile != t3:
                        shape_ok = False
                        reason = "chi_river_tile_mismatch"
                    else:
                        if t1 == wealth:
                            meld_wealth_units += 1.0
                        if t2 == wealth:
                            meld_wealth_units += 1.0
                        if t3 == wealth:
                            meld_wealth_units += 1.0
                        if last_tile == wealth:
                            meld_wealth_units -= 1.0
                        if meld_wealth_units < 0.0:
                            shape_ok = False
                            reason = "chi_wealth_units_inconsistent"
            if shape_ok:
                best_value = None
                best_followup = None
                best_combined = None
                best_speed = None
                best_seven = None
                best_units = None
                for branch in branches:
                    combined = branch.get("combined_shanten")
                    if combined is None or combined is True or combined is False:
                        continue
                    cv = float(combined)
                    if cv - cv != 0:
                        continue
                    ci = int(cv)
                    if cv != float(ci) or ci < -1 or ci > 13:
                        continue
                    followup_code = branch.get("followup_discard")
                    if followup_code is None or followup_code is True or followup_code is False:
                        continue
                    units = meld_wealth_units
                    if followup_code == wealth:
                        units += 1.0
                    if units > float(wealth_count):
                        continue
                    gain = baseline_sh - ci
                    if gain >= 2:
                        speed_term = 16.0
                    elif gain == 1:
                        speed_term = 8.0
                    else:
                        speed_term = -6.0
                    loss7 = 0.0
                    if meld_count == 0 and baseline_sev is not None and baseline_sev <= baseline_sh + 1:
                        loss7 = 6.0
                    candidate_value = speed_term - loss7 - 12.0 * units
                    if candidate_value > 24.0:
                        candidate_value = 24.0
                    if candidate_value < -24.0:
                        candidate_value = -24.0
                    candidate_value = round(candidate_value, 6)
                    if best_value is None or candidate_value > best_value:
                        best_value = candidate_value
                        best_followup = followup_code
                        best_combined = ci
                        best_speed = gain
                        best_seven = loss7
                        best_units = units
                if best_value is None:
                    reason = "no_branch_with_verifiable_reading"
                else:
                    triggered = True
                    value = best_value
                    branch_shanten = best_combined
                    speed_gain = best_speed
                    seven_loss = best_seven
                    wealth_units = best_units
                    followup = best_followup
                    branch_count = len(branches)
        return {"structure": "claim_branch_rebase/1", "triggered": triggered, "value": value, "reason": reason, "evidence": {"closed_baseline_shanten": baseline_sh, "closed_baseline_seven_pairs": baseline_sev, "branch_shanten": branch_shanten, "speed_gain": speed_gain, "seven_pairs_loss": seven_loss, "wealth_units": wealth_units, "selected_followup": followup, "branch_count": branch_count}, "degrade": "exact_v2_when_not_triggered"}

    pending = []
    known = []
    best_shanten = None
    closed_baseline_shanten = None
    closed_baseline_seven = None
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
        if kind == "pass" or kind == "discard":
            if kind == "pass" and action.get("replacement_draw_unknown") is True:
                pass
            elif action.get("fact_kind") == "hand_progress":
                raw_sh = action.get("shanten_after")
                if raw_sh is not None and raw_sh is not True and raw_sh is not False:
                    sv = float(raw_sh)
                    if sv - sv == 0:
                        si = int(sv)
                        if sv == float(si) and si >= 0 and si <= 13:
                            if closed_baseline_shanten is None or si < closed_baseline_shanten:
                                closed_baseline_shanten = si
            raw_sev = action.get("seven_pairs_shanten_after")
            if raw_sev is not None and raw_sev is not True and raw_sev is not False:
                zv = float(raw_sev)
                if zv - zv == 0:
                    zi = int(zv)
                    if zv == float(zi) and zi >= -1 and zi <= 13:
                        if closed_baseline_seven is None or zi < closed_baseline_seven:
                            closed_baseline_seven = zi
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
        rebase_info = {"structure": "claim_branch_rebase/1", "triggered": False, "value": 0.0, "reason": "action_type_not_chi_or_peng", "evidence": None, "degrade": "exact_v2_when_not_triggered"}
        if kind == "chi" or kind == "peng":
            rebase_info = claim_rebase(kind, key, action.get("followup_branches"), wealth, wealth_count, closed_baseline_shanten, closed_baseline_seven, last_tile, own_meld_count)
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
            if rebase_info.get("triggered") is True:
                total += rebase_info.get("value")
            total = round(total, 6)
        trace = {"basis": item.get("basis"), "base_score": base, "shanten_after": item.get("shanten"), "best_shanten_non_pass": best_shanten, "wealth_part": wealth_part, "wealth_discard_part": wealth_discard_part, "river_part": river_part, "risk_units": risk_units, "style_part": style_part, "unknown": unknown, "unknown_policy": "known_final_floor_minus_1" if unknown else None, "hu_sorting_layer": kind == "hu", "scope": "direct_v2_or_produced_outside_v2", "claim_rebase": rebase_info}
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
    return {"status": "SCORED", "entries": final_entries, "reason": "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下；吃/碰仅在完整分支且提速、七对与财神损失可核时叠加有界重定基，未触发逐点退化为 V2"}
