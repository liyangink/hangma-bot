# STRUCTURE_SPACE_JSON: {"parameters":{"RMF_SCALE":[0.0,4.0,8.0,12.0],"RMF_SHAPE":[32.0,64.0,96.0],"RMF_CAP":[4.0,8.0,12.0]},"zero_effect":{"RMF_SCALE":0.0,"RMF_SHAPE":64.0,"RMF_CAP":8.0},"configs":[{"RMF_SCALE":0.0,"RMF_SHAPE":64.0,"RMF_CAP":8.0},{"RMF_SCALE":4.0,"RMF_SHAPE":64.0,"RMF_CAP":4.0},{"RMF_SCALE":8.0,"RMF_SHAPE":64.0,"RMF_CAP":8.0},{"RMF_SCALE":12.0,"RMF_SHAPE":64.0,"RMF_CAP":12.0},{"RMF_SCALE":8.0,"RMF_SHAPE":32.0,"RMF_CAP":8.0},{"RMF_SCALE":8.0,"RMF_SHAPE":96.0,"RMF_CAP":8.0}]}
# ACTIVE_CONFIG_JSON: {"config_id":"r2-cfg-02","values":{"RMF_CAP":8.0,"RMF_SCALE":8.0,"RMF_SHAPE":64.0}}
"""候选机制：稳定V2骨架加条件路线价值微函数；模型只提供受限表达式。"""

RMF_SCALE = 8.0
RMF_SHAPE = 64.0
RMF_CAP = 8.0
RMF_MODE = "best_only"
def route_micro_value(direct_support, self_delta, fan, wall_remaining, shape):
    """把已校验的公开条件路线事实压缩为[-1,1]无量纲代理。"""
    value = 0.5 * self_delta / 48.0 + min(direct_support / wall_remaining, shape / 128.0) + 0.25 * (fan - 1.0) - 0.5
    if value - value != 0:
        return None
    if value > 1.0:
        return 1.0
    if value < -1.0:
        return -1.0
    return float(value)

def finite_number(value):
    """把非布尔有限数转换为浮点；未知保持未知。"""
    if value is None or value is True or value is False:
        return None
    number = float(value)
    if number - number != 0:
        return None
    return number


def support_total(tiles):
    """汇总规则给出的未见枚数；它是计数代理，不解释为概率。"""
    if tiles is None:
        return None
    total = 0.0
    codes = set()
    for tile in tiles:
        code = tile.get("code")
        amount = finite_number(tile.get("remaining_estimate"))
        if (code is None or code is True or code is False or amount is None
                or amount < 0.0 or amount > 4.0 or code in codes):
            return None
        codes.add(code)
        total += amount
    return total


def route_raw_value(action, visible, seat):
    """返回动作内最强已校验路线的无量纲原值；未知保持None。"""
    if action.get("value_coverage") != "complete":
        return (None, "coverage_not_complete", 0)
    issues = action.get("value_issues")
    if issues is None or len(issues) != 0:
        return (None, "value_issues", 0)
    wall = finite_number(visible.get("remaining_tile_count"))
    direct_support = support_total(action.get("useful_tiles"))
    if wall is None or wall <= 0.0 or direct_support is None or direct_support <= 0.0:
        return (None, "public_support_unavailable", 0)
    best = None
    valid_routes = 0
    routes = action.get("routes")
    if routes is None:
        return (None, "routes_unknown", 0)
    for route in routes:
        if route.get("shanten") != 0:
            continue
        route_support = support_total(route.get("useful_tiles"))
        if route_support is None or route_support <= 0.0:
            continue
        conditions = route.get("conditions")
        if conditions is None or conditions.get("draw_kind") not in ("normal", "replacement"):
            continue
        settlement = route.get("conditional_settlement")
        if settlement is None:
            continue
        self_delta = finite_number(settlement.get("self_delta"))
        fan = finite_number(settlement.get("fan"))
        deltas = settlement.get("score_delta")
        if (self_delta is None or self_delta <= 0.0 or fan is None or fan <= 0.0
                or deltas is None or len(deltas) != 4):
            continue
        seat_delta = finite_number(deltas[seat])
        if seat_delta is None or seat_delta != self_delta:
            continue
        raw = route_micro_value(direct_support, self_delta, fan, wall, RMF_SHAPE)
        if raw is None:
            continue
        valid_routes += 1
        if best is None or raw > best:
            best = raw
    if best is None:
        return (None, "no_valid_route", valid_routes)
    return (round(best, 12), "complete_route_raw_max", valid_routes)


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
        route_raw, route_delta_basis, route_valid_count = route_raw_value(
            action, visible, seat)
        if direct:
            pending.append({"action": action, "base": base, "basis": "direct_v2", "shanten": shanten, "route_raw": route_raw, "route_delta_basis": route_delta_basis, "route_valid_count": route_valid_count})
            known.append(base)
        elif produced:
            pending.append({"action": action, "base": 0.0, "basis": "produced_outside_v2", "shanten": None, "route_raw": route_raw, "route_delta_basis": route_delta_basis, "route_valid_count": route_valid_count})
            known.append(0.0)
        else:
            pending.append({"action": action, "base": None, "basis": "unknown", "shanten": None, "route_raw": None, "route_delta_basis": "unknown_action", "route_valid_count": 0})
    if len(known) == 0:
        return {"status": "ABSTAIN", "reason": "全部动作均无已生产事实，未知不能取零分"}
    base_floor = min(known)
    route_raw_values = []
    for pending_item in pending:
        pending_raw = pending_item.get("route_raw")
        if pending_raw is not None:
            route_raw_values.append(pending_raw)
    route_low = None
    route_high = None
    route_mean = None
    if len(route_raw_values) >= 2:
        route_low = min(route_raw_values)
        route_high = max(route_raw_values)
        if route_high > route_low:
            route_mean = sum(route_raw_values) / float(len(route_raw_values))
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
        route_raw = item.get("route_raw")
        route_delta = 0.0
        if (RMF_SCALE != 0.0 and route_raw is not None and route_low is not None
                and route_high is not None and route_high > route_low):
            span = route_high - route_low
            if RMF_MODE == "midrange":
                route_delta = RMF_SCALE * (
                    route_raw - (route_low + route_high) / 2.0) / span
            elif RMF_MODE == "best_only" and route_raw == route_high:
                route_delta = RMF_SCALE * (route_raw - route_low) / span
            if route_delta > RMF_CAP:
                route_delta = RMF_CAP
            if route_delta < -RMF_CAP:
                route_delta = -RMF_CAP
        route_delta = round(route_delta, 6)
        total = round(total + route_delta, 6)
        trace = {"basis": item.get("basis"), "base_score": base, "shanten_after": item.get("shanten"), "best_shanten_non_pass": best_shanten, "wealth_part": wealth_part, "wealth_discard_part": wealth_discard_part, "river_part": river_part, "risk_units": risk_units, "style_part": style_part, "route_delta": route_delta, "route_raw": route_raw, "route_low": route_low, "route_high": route_high, "route_mean": route_mean, "rmf_mode": RMF_MODE, "route_delta_basis": item.get("route_delta_basis"), "route_valid_count": item.get("route_valid_count"), "rmf_scale": RMF_SCALE, "rmf_shape": RMF_SHAPE, "rmf_cap": RMF_CAP, "unknown": unknown, "unknown_policy": "known_final_floor_minus_1" if unknown else None, "hu_sorting_layer": kind == "hu", "scope": "direct_v2_or_produced_outside_v2"}
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
