# STRUCTURE_SPACE_JSON: {"parameters":{"FBV_GAIN":[4.0,0.0,2.0,8.0],"FBV_SUPPORT":[0.5,0.0,0.25,1.0],"FBV_SUPPORT_CAP":[12.0,0.0,6.0],"FBV_CAP":[16.0,0.0,8.0,24.0]},"zero_effect":{"FBV_GAIN":0.0,"FBV_SUPPORT":0.0,"FBV_SUPPORT_CAP":0.0,"FBV_CAP":0.0},"configs":[{"FBV_GAIN":4.0,"FBV_SUPPORT":0.5,"FBV_SUPPORT_CAP":12.0,"FBV_CAP":16.0},{"FBV_GAIN":0.0,"FBV_SUPPORT":0.0,"FBV_SUPPORT_CAP":0.0,"FBV_CAP":0.0},{"FBV_GAIN":4.0,"FBV_SUPPORT":0.0,"FBV_SUPPORT_CAP":12.0,"FBV_CAP":16.0},{"FBV_GAIN":0.0,"FBV_SUPPORT":0.5,"FBV_SUPPORT_CAP":12.0,"FBV_CAP":16.0},{"FBV_GAIN":2.0,"FBV_SUPPORT":0.25,"FBV_SUPPORT_CAP":6.0,"FBV_CAP":8.0},{"FBV_GAIN":8.0,"FBV_SUPPORT":1.0,"FBV_SUPPORT_CAP":12.0,"FBV_CAP":24.0}]}
# ACTIVE_CONFIG_JSON: {"config_id":"s2-cfg-01","values":{"FBV_CAP":0.0,"FBV_GAIN":0.0,"FBV_SUPPORT":0.0,"FBV_SUPPORT_CAP":0.0}}
# ACTIVE_CONFIG_JSON: {"config_id":"t2-cfg-03","values":{"FBV_CAP":16.0,"FBV_GAIN":4.0,"FBV_SUPPORT":0.0,"FBV_SUPPORT_CAP":12.0}}
"""候选机制说明：默认 V2 基础排序、胡排序层与严格未知锚定不变；fbv 以 S3 父代常数 (4.0/0.0/12.0/16.0) 为不动锚，参数只是选择性控制——直接牌效可比的动作按 min(FBV_GAIN/4,1) 有界收缩其后续项，直接牌效缺失的动作按 FBV_SUPPORT×min(support_remaining, FBV_SUPPORT_CAP) 且受 FBV_CAP 上界约束有界补充；全零配置下收缩与补充恒为零，逐分等价于 S3 父代；support_remaining 仅作有界计数加成，不作概率，不读取 H/M、隐藏状态或未来牌墙。"""

S3_FBV_GAIN = 4.0
S3_FBV_SUPPORT = 0.0
S3_FBV_SUPPORT_CAP = 12.0
S3_FBV_CAP = 16.0
FBV_GAIN = 0.0
FBV_SUPPORT = 0.0
FBV_SUPPORT_CAP = 0.0
FBV_CAP = 0.0
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
        fbv = 0.0
        fbv_shanten = None
        fbv_support_capped = 0.0
        fbv_gate = "no_branch_facts"
        if branches is not None:
            branch_best = None
            branch_support = 0.0
            for branch in branches:
                combined = branch.get("combined_shanten")
                if combined is None or combined is True or combined is False:
                    continue
                combined_value = float(combined)
                if combined_value - combined_value != 0:
                    continue
                if branch_best is None or combined_value < branch_best:
                    branch_best = combined_value
                    branch_support = 0.0
                remain = branch.get("support_remaining")
                if remain is None or remain is True or remain is False:
                    remain = 0.0
                else:
                    remain = float(remain)
                    if remain - remain != 0 or remain < 0.0:
                        remain = 0.0
                if combined_value == branch_best and remain > branch_support:
                    branch_support = remain
            if branch_best is None:
                fbv_gate = "branch_shanten_unknown_anchor_s3_zero"
            else:
                fbv_shanten = branch_best
                fbv_support_capped = min(branch_support, S3_FBV_SUPPORT_CAP)
                core = S3_FBV_GAIN * (1.0 - branch_best) + S3_FBV_SUPPORT * fbv_support_capped
                if core > S3_FBV_CAP:
                    core = S3_FBV_CAP
                if core < -S3_FBV_CAP:
                    core = -S3_FBV_CAP
                core = round(core, 6)
                if direct:
                    shrink = FBV_GAIN / S3_FBV_GAIN
                    if shrink > 1.0:
                        shrink = 1.0
                    if shrink < 0.0:
                        shrink = 0.0
                    fbv = round(core * (1.0 - shrink), 6)
                    if shrink > 0.0:
                        fbv_gate = "direct_comparable_selective_shrink"
                    else:
                        fbv_gate = "direct_comparable_full_s3_anchor"
                else:
                    fill = FBV_SUPPORT * min(branch_support, FBV_SUPPORT_CAP)
                    if fill > FBV_CAP:
                        fill = FBV_CAP
                    fill = round(fill, 6)
                    fbv = round(core + fill, 6)
                    if fill > 0.0:
                        fbv_gate = "direct_absent_selective_fill_in"
                    else:
                        fbv_gate = "direct_absent_s3_core"
        if direct:
            pending.append({"action": action, "base": base, "basis": "direct_v2", "shanten": shanten, "fbv": fbv, "fbv_best_combined_shanten": fbv_shanten, "fbv_support_capped": fbv_support_capped, "fbv_gate": fbv_gate})
            known.append(base)
        elif produced:
            pending.append({"action": action, "base": 0.0, "basis": "produced_outside_v2", "shanten": None, "fbv": fbv, "fbv_best_combined_shanten": fbv_shanten, "fbv_support_capped": fbv_support_capped, "fbv_gate": fbv_gate})
            known.append(0.0)
        else:
            pending.append({"action": action, "base": None, "basis": "unknown", "shanten": None, "fbv": 0.0, "fbv_best_combined_shanten": None, "fbv_support_capped": 0.0, "fbv_gate": "unknown_no_facts"})
    if len(known) == 0:
        return {"status": "ABSTAIN", "reason": "全部动作均无已生产事实，未知不能取零分"}
    base_floor = min(known)
    entries = []
    for item in pending:
        action = item.get("action")
        key = action.get("action_key")
        kind = action.get("action_type")
        base = item.get("base")
        fbv = item.get("fbv")
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
        total = round(total + fbv, 6)
        trace = {"basis": item.get("basis"), "base_score": base, "shanten_after": item.get("shanten"), "best_shanten_non_pass": best_shanten, "wealth_part": wealth_part, "wealth_discard_part": wealth_discard_part, "river_part": river_part, "risk_units": risk_units, "style_part": style_part, "fbv": fbv, "fbv_best_combined_shanten": item.get("fbv_best_combined_shanten"), "fbv_support_capped": item.get("fbv_support_capped"), "fbv_gate": item.get("fbv_gate"), "fbv_scope": "followup_branches_s3_anchored_selective_shrink_bounded", "unknown": unknown, "unknown_policy": "known_final_floor_minus_1" if unknown else None, "hu_sorting_layer": kind == "hu", "scope": "direct_v2_or_produced_outside_v2"}
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
    return {"status": "SCORED", "entries": final_entries, "reason": "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下；fbv 以 S3 父代常数为不动锚，全零配置逐分回到 S3 父代，非零配置仅在直接牌效可比时有界收缩、直接牌效缺失时有界补充"}
