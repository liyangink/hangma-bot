"""候选机制说明：以规则牌效为主刻度，用牌河熟张弱奖励与下家公开吃副露邻近压力重排弃牌，并保持胡牌动态优先和严格未知锚定。"""

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
    rule_state = visible.get("rule_state")
    if hand is None or discards is None or melds is None or rule_state is None:
        return {"status": "ABSTAIN", "reason": "基础评分所需公开状态缺失"}
    if len(discards) != 4 or len(melds) != 4:
        return {"status": "ABSTAIN", "reason": "四座牌河或副露长度不合法"}

    wealth = rule_state.get("wealth_god")
    if wealth is None:
        return {"status": "ABSTAIN", "reason": "财神牌码缺失"}

    own_meld_count = len(melds[seat])
    wealth_count = hand.count(wealth)
    drawn = visible.get("drawn_tile")
    if drawn is not None and len(hand) != 14 - 3 * own_meld_count and drawn == wealth:
        wealth_count += 1

    pending = []
    known_base_scores = []
    best_shanten = None
    seen_keys = set()

    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if key is None or kind is None or action.get("is_legal") is not True:
            return {"status": "ABSTAIN", "reason": "动作合法身份、类型或键缺失"}
        if key in seen_keys:
            return {"status": "ABSTAIN", "reason": "动作键重复"}
        seen_keys.add(key)

        fact_kind = action.get("fact_kind")
        shanten = action.get("shanten_after")
        useful = action.get("useful_tiles")
        direct = False
        base = None
        support = None

        if kind == "hu":
            direct = True
            base = 1000.0
            shanten = -1
            support = 0.0
        elif fact_kind == "hand_progress":
            if shanten is None or shanten is True or shanten is False or useful is None:
                return {"status": "ABSTAIN", "reason": "已标记牌效动作缺少可判读向听或有效牌"}
            shanten_value = float(shanten)
            if shanten_value - shanten_value != 0 or shanten_value < 0:
                return {"status": "ABSTAIN", "reason": "已标记牌效动作的向听非法"}
            support_value = 0.0
            for tile in useful:
                remaining = tile.get("remaining_estimate")
                if remaining is None or remaining is True or remaining is False:
                    return {"status": "ABSTAIN", "reason": "已标记牌效动作缺少有效牌剩余枚数"}
                amount = float(remaining)
                if amount - amount != 0 or amount < 0:
                    return {"status": "ABSTAIN", "reason": "有效牌剩余枚数非法"}
                support_value += amount
            direct = True
            support = round(support_value, 1)
            base = -100.0 * shanten_value + support
            if kind != "pass" and (best_shanten is None or shanten_value < best_shanten):
                best_shanten = shanten_value

        if kind == "pass" and direct:
            if action.get("best_followup_discard") is not None or action.get("replacement_draw_unknown") is not False:
                direct = False
                base = None
                support = None

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
        if fact_kind == "win" or fact_kind == "not_applicable":
            produced = True

        if direct:
            pending.append({"action": action, "base": base, "basis": "direct_progress", "shanten": shanten, "support": support})
            known_base_scores.append(base)
        elif produced:
            pending.append({"action": action, "base": 0.0, "basis": "produced_nonprogress_fact", "shanten": None, "support": None})
            known_base_scores.append(0.0)
        else:
            pending.append({"action": action, "base": None, "basis": "unknown", "shanten": None, "support": None})

    if len(known_base_scores) == 0:
        return {"status": "ABSTAIN", "reason": "全部动作均无已生产事实，未知不能取零分"}

    scored = []
    next_seat = (seat + 1) % 4
    for item in pending:
        action = item.get("action")
        key = action.get("action_key")
        kind = action.get("action_type")
        base = item.get("base")

        if base is None:
            unknown_trace = {
                "basis": "unknown_below_known_final_floor",
                "unknown": True,
                "unknown_facts": "缺少可用动作后牌效、后续分支、条件路线、立即结算或家族进展",
                "unknown_policy": "known_final_floor_minus_1",
                "mechanism_version": "river_claim_exposure/1"
            }
            scored.append({"action_key": key, "action_type": kind, "score": None, "trace": unknown_trace})
            continue

        total = float(base)
        retained_wealth = wealth_count
        wealth_discard_part = 0.0
        river_familiarity_part = 0.0
        claim_exposure_part = 0.0
        opponent_river_count = 0
        next_river_count = 0
        next_chi_near_groups = 0
        tile_code = None

        if kind == "discard":
            if key[:8] != "discard:":
                return {"status": "ABSTAIN", "reason": "弃牌动作键格式不可判读"}
            tile_code = key[8:]
            if tile_code == wealth:
                retained_wealth -= 1
                wealth_discard_part = -60.0
                total += wealth_discard_part

            for river_seat in range(4):
                if river_seat != seat:
                    copies = discards[river_seat].count(tile_code)
                    opponent_river_count += copies
                    if river_seat == next_seat:
                        next_river_count = copies
            river_familiarity_part = float(min(opponent_river_count, 2))
            total += river_familiarity_part

            if len(tile_code) >= 2 and tile_code[0] in "123456789" and tile_code[-1] in "wbt":
                suit = tile_code[-1]
                rank = int(tile_code[0])
                for meld in melds[next_seat]:
                    meld_kind = meld.get("kind")
                    meld_tiles = meld.get("tiles")
                    if meld_tiles is None:
                        return {"status": "ABSTAIN", "reason": "下家公开副露缺少牌码"}
                    near_in_meld = False
                    if meld_kind == "chi":
                        for other in meld_tiles:
                            if len(other) >= 2 and other[0] in "123456789" and other[-1] == suit and abs(int(other[0]) - rank) <= 2:
                                near_in_meld = True
                        if near_in_meld:
                            next_chi_near_groups += 1
                next_chi_near_groups = min(next_chi_near_groups, 2)
                claim_exposure_part = -5.0 * float(next_chi_near_groups)
                claim_exposure_part += 2.0 * float(min(next_river_count, 1)) * float(next_chi_near_groups)
                total += claim_exposure_part

        wealth_part = 5.0 * float(retained_wealth)
        total += wealth_part

        fixed_action_part = 0.0
        if kind == "peng":
            fixed_action_part = -6.0
        elif kind == "chi":
            fixed_action_part = -10.0
        elif kind == "gang":
            fixed_action_part = 40.0
        total += fixed_action_part
        total = round(total, 6)
        if total - total != 0:
            return {"status": "ABSTAIN", "reason": "已知动作评分非有限"}

        trace = {
            "basis": item.get("basis"),
            "base_score": base,
            "shanten_after": item.get("shanten"),
            "support_remaining": item.get("support"),
            "best_shanten_non_pass": best_shanten,
            "wealth_part": wealth_part,
            "wealth_discard_part": wealth_discard_part,
            "river_familiarity_part": river_familiarity_part,
            "opponent_river_count": opponent_river_count,
            "next_river_count": next_river_count,
            "next_chi_near_groups": next_chi_near_groups,
            "claim_exposure_part": claim_exposure_part,
            "fixed_action_part": fixed_action_part,
            "unknown": False,
            "hu_sorting_layer": kind == "hu",
            "mechanism_version": "river_claim_exposure/1"
        }
        scored.append({"action_key": key, "action_type": kind, "score": total, "trace": trace})

    nonhu_ceiling = None
    for entry in scored:
        if entry.get("trace").get("unknown") is not True and entry.get("action_type") != "hu":
            value = entry.get("score")
            if nonhu_ceiling is None or value > nonhu_ceiling:
                nonhu_ceiling = value

    known_floor = None
    for entry in scored:
        if entry.get("trace").get("unknown") is not True:
            value = entry.get("score")
            if entry.get("action_type") == "hu" and nonhu_ceiling is not None:
                value = nonhu_ceiling + 1.0
            if known_floor is None or value < known_floor:
                known_floor = value

    if known_floor is None:
        return {"status": "ABSTAIN", "reason": "没有可用已知最终评分，未知不能取零分"}

    final_entries = []
    for entry in scored:
        value = entry.get("score")
        if entry.get("trace").get("unknown") is True:
            value = known_floor - 1.0
        elif entry.get("action_type") == "hu" and nonhu_ceiling is not None:
            value = nonhu_ceiling + 1.0
        if value is None or value is True or value is False or value - value != 0:
            return {"status": "ABSTAIN", "reason": "最终动作评分不可用"}
        final_entries.append({"action_key": entry.get("action_key"), "score": value, "trace": entry.get("trace")})

    return {
        "status": "SCORED",
        "entries": final_entries,
        "reason": "公开接牌压力仅重排可比弃牌；胡牌动态优先；缺证动作严格取已知最终最低分减1"
    }
