"""R16 代际 2 候选 D：规则可行前沿后的路线集合最坏情形排序。

每个当前动作或吃碰后继先用规则已经投影的向听与公开支持张数进入 Pareto
比较。目标层只读取活动前沿，并消费其中每条路径的全部相容条件路线；只有
一个动作在最差名次、最小边界、最差目标关系和有效牌码覆盖上严格支配其余
前沿动作时才置顶。任何目标未知或不可比都整窗精确回退稳定 V2。
"""


def score_stable_v2(view):
    """稳定 V2 的完整排序；所有回退逐分逐序沿用本结果。"""
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


def integer_value(value, low, high):
    """校验规则投影整数；未知与布尔值均不补零。"""
    if value is None or value is True or value is False:
        return None
    number = float(value)
    if number - number != 0 or number != int(number):
        return None
    number = int(number)
    if number < low or number > high:
        return None
    return number


def support_value(tiles):
    """汇总公开支持张数；该数不是概率。"""
    if tiles is None:
        return None
    codes = set()
    total = 0
    for tile in tiles:
        code = tile.get("code")
        amount = integer_value(tile.get("remaining_estimate"), 0, 4)
        if code is None or code is True or code is False or len(code) == 0 or code in codes or amount is None:
            return None
        codes.add(code)
        total += amount
    return total


def stage_values(competition):
    """读取座位 0—3 当前阶段合计，不重复累计当前桌账。"""
    if competition is None:
        return None
    masks = competition.get("freshness_masks")
    scores = competition.get("current_stage_scores")
    if masks is None or len(masks) != 2 or masks[0] != "stage_account:complete" or masks[1] != "table_account:live":
        return None
    if scores is None or len(scores) != 4:
        return None
    values = []
    for score in scores:
        value = integer_value(score, -1000000000, 1000000000)
        if value is None:
            return None
        values.append(value)
    return values


def rank_facts(values, seat):
    """返回最差条件名次、前二边界差和 after 状态序数。"""
    low = 1
    high = 1
    for index in range(4):
        if index != seat:
            if values[index] > values[seat]:
                low += 1
            if values[index] >= values[seat]:
                high += 1
    relation = 0
    if high <= 2:
        relation = 2
    elif low <= 2:
        relation = 1
    return (low, high, values[seat] - sorted(values, reverse=True)[1], relation)


def goal_relation(before, after):
    """固定离散目标关系；只表达条件状态变化，不估计发生概率。"""
    if after[3] == 2:
        if before[3] == 0:
            return 6
        if before[3] == 1:
            return 5
        return 4
    if after[3] == 1:
        if before[3] == 0:
            return 3
        if before[3] == 2:
            return 1
        return 2
    if before[3] == 2 or before[3] == 1:
        return 0
    if after[2] > before[2]:
        return 1
    return 0


def conditional_goal(route, values, seat):
    """消费规则条件结算，不重算番数、支付、向听或有效牌。"""
    if route.get("support") != "conditional_witness" or integer_value(route.get("shanten"), 0, 0) is None:
        return None
    tiles = route.get("useful_tiles")
    if tiles is None or len(tiles) == 0 or support_value(tiles) is None:
        return None
    conditions = route.get("conditions")
    settlement = route.get("conditional_settlement")
    if conditions is None or settlement is None:
        return None
    draw_kind = conditions.get("draw_kind")
    if draw_kind != "normal" and draw_kind != "replacement":
        return None
    meld_count = integer_value(conditions.get("meld_count"), 0, 4)
    chain_count = integer_value(conditions.get("chain_count"), 0, 1000000000)
    chain_piao = integer_value(conditions.get("chain_piao"), 0, 1000000000)
    if meld_count is None or chain_count is None or chain_piao is None or chain_piao > chain_count:
        return None
    if conditions.get("baotou") is not True and conditions.get("baotou") is not False:
        return None
    hand = conditions.get("pre_draw_hand")
    if hand is None or len(hand) != 13 - 3 * meld_count:
        return None
    for tile in hand:
        if tile is None or tile is True or tile is False or len(tile) == 0:
            return None
    if chain_piao + hand.count("白") > 4:
        return None
    deltas = settlement.get("score_delta")
    if deltas is None or len(deltas) != 4 or settlement.get("details") is None:
        return None
    fan = integer_value(settlement.get("fan"), 1, 1000000000)
    if fan is None:
        return None
    after_values = []
    total = 0
    checked = []
    for index in range(4):
        delta = integer_value(deltas[index], -1000000000, 1000000000)
        if delta is None:
            return None
        checked.append(delta)
        total += delta
        after_values.append(values[index] + delta)
    self_delta = integer_value(settlement.get("self_delta"), -1000000000, 1000000000)
    if total != 0 or self_delta is None or self_delta != checked[seat]:
        return None
    before = rank_facts(values, seat)
    after = rank_facts(after_values, seat)
    return (after[1], after[2], goal_relation(before, after))


def action_paths(action):
    """把吃碰展开为全部后继；其他动作保持一个动作级规则路径。"""
    kind = action.get("action_type")
    key = action.get("action_key")
    paths = []
    if kind == "chi" or kind == "peng":
        branches = action.get("followup_branches")
        if branches is None or len(branches) == 0:
            return None
        seen = set()
        for branch in branches:
            discard = branch.get("followup_discard")
            followup_key = branch.get("followup_key")
            if discard is None or discard is True or discard is False or len(discard) == 0 or discard in seen:
                return None
            if followup_key != key + "#" + discard:
                return None
            shanten = integer_value(branch.get("combined_shanten"), -1, 13)
            support = integer_value(branch.get("support_remaining"), 0, 136)
            if shanten is None or support is None:
                return None
            seen.add(discard)
            paths.append({"action_key": key, "path_key": followup_key, "followup": discard, "shanten": shanten, "support": support})
        return paths
    shanten = integer_value(action.get("shanten_after"), -1, 13)
    support = support_value(action.get("useful_tiles"))
    if shanten is None or support is None:
        return None
    paths.append({"action_key": key, "path_key": key, "followup": None, "shanten": shanten, "support": support})
    return paths


def pareto_frontier(paths):
    """取向听不大且公开支持不少、至少一维严格更好的路径前沿。"""
    frontier = []
    for index in range(len(paths)):
        current = paths[index]
        dominated = False
        for other_index in range(len(paths)):
            if other_index != index:
                other = paths[other_index]
                no_worse = other.get("shanten") <= current.get("shanten") and other.get("support") >= current.get("support")
                strict = other.get("shanten") < current.get("shanten") or other.get("support") > current.get("support")
                if no_worse and strict:
                    dominated = True
        if not dominated:
            frontier.append(current)
    return frontier


def summarize_action(action, all_paths, active_paths, values, seat):
    """消费活动路径的全部相容路线，形成最坏情形目标包络。"""
    if action.get("value_coverage") != "complete":
        return None
    routes = action.get("routes")
    if routes is None or len(routes) == 0:
        return None
    seen_pairs = set()
    codes = set()
    prepared = []
    worst_rank = 0
    min_margin = None
    worst_relation = 6
    active_route_count = 0
    for route in routes:
        followup = route.get("followup_discard")
        matched = None
        for path in all_paths:
            if path.get("followup") == followup:
                matched = path
        if matched is None:
            return None
        goal = conditional_goal(route, values, seat)
        if goal is None:
            return None
        route_support = support_value(route.get("useful_tiles"))
        if route_support is None or matched.get("shanten") != 0:
            return None
        route_codes = []
        for tile in route.get("useful_tiles"):
            code = tile.get("code")
            pair = (matched.get("path_key"), code)
            if pair in seen_pairs:
                return None
            seen_pairs.add(pair)
            route_codes.append(code)
        prepared.append({"path_key": matched.get("path_key"), "support": route_support,
                         "codes": route_codes, "goal": goal})
    route_rows = []
    for path in active_paths:
        path_key = path.get("path_key")
        path_count = 0
        path_support = 0
        for row in prepared:
            if row.get("path_key") == path_key:
                path_count += 1
                path_support += row.get("support")
                goal = row.get("goal")
                active_route_count += 1
                for code in row.get("codes"):
                    codes.add(code)
                    route_rows.append((path_key + ":" + code, goal[0], goal[1], goal[2]))
                worst_rank = max(worst_rank, goal[0])
                min_margin = goal[1] if min_margin is None else min(min_margin, goal[1])
                worst_relation = min(worst_relation, goal[2])
        if path_count == 0 or path_support != path.get("support"):
            return None
    if active_route_count == 0 or min_margin is None:
        return None
    critical = []
    for row in sorted(route_rows):
        if row[1] == worst_rank or row[2] == min_margin or row[3] == worst_relation:
            critical.append(row[0])
    followups = []
    frontier_followups = []
    feasibility = []
    for path in sorted(all_paths, key=lambda item: item.get("path_key")):
        followups.append(path.get("path_key"))
        feasibility.append(path.get("path_key") + "|s=" + f'{path.get("shanten")}' + "|u=" + f'{path.get("support")}')
    for path in sorted(active_paths, key=lambda item: item.get("path_key")):
        frontier_followups.append(path.get("path_key"))
    return {"route_count": active_route_count, "distinct_followups": followups,
            "frontier_followups": frontier_followups,
            "worst_rank_high": worst_rank, "min_boundary_margin": min_margin,
            "worst_goal_relation": worst_relation, "distinct_codes": len(codes),
            "critical_routes": critical, "path_feasibility": feasibility}


def dominates(left, right):
    """四维逐项非劣且至少一维严格更好才构成严格支配。"""
    rank_ok = left.get("worst_rank_high") <= right.get("worst_rank_high")
    margin_ok = left.get("min_boundary_margin") >= right.get("min_boundary_margin")
    relation_ok = left.get("worst_goal_relation") >= right.get("worst_goal_relation")
    coverage_ok = left.get("distinct_codes") >= right.get("distinct_codes")
    strict = (left.get("worst_rank_high") < right.get("worst_rank_high")
              or left.get("min_boundary_margin") > right.get("min_boundary_margin")
              or left.get("worst_goal_relation") > right.get("worst_goal_relation")
              or left.get("distinct_codes") > right.get("distinct_codes"))
    return rank_ok and margin_ok and relation_ok and coverage_ok and strict


def summary_for(summaries, key):
    """按动作键读取局部摘要，不依赖可变模块状态。"""
    for row in summaries:
        if row.get("action_key") == key:
            return row.get("summary")
    return None


def finish(stable, summaries, frontier_actions, active, reason, winner):
    """胜者置顶、其余保持 V2；回退时所有 V2 分数和条目顺序不变。"""
    maximum = None
    for entry in stable.get("entries"):
        score = entry.get("score")
        if maximum is None or score > maximum:
            maximum = score
    entries = []
    for entry in stable.get("entries"):
        key = entry.get("action_key")
        summary = summary_for(summaries, key)
        route_count = 0 if summary is None else summary.get("route_count")
        followups = [] if summary is None else summary.get("distinct_followups")
        worst_rank = None if summary is None else summary.get("worst_rank_high")
        min_margin = None if summary is None else summary.get("min_boundary_margin")
        worst_relation = None if summary is None else summary.get("worst_goal_relation")
        critical = [] if summary is None else summary.get("critical_routes")[:4]
        critical_count = 0 if summary is None else len(summary.get("critical_routes"))
        distinct_codes = 0 if summary is None else summary.get("distinct_codes")
        path_feasibility = [] if summary is None else summary.get("path_feasibility")
        frontier_followups = [] if summary is None else summary.get("frontier_followups")
        goal_set = {"mechanism_active": active, "fallback_exact_v2": not active,
                    "reason": reason, "frontier_actions": frontier_actions,
                    "winner_action": winner, "route_count": route_count,
                    "distinct_followups": followups, "worst_rank_high": worst_rank,
                    "min_boundary_margin": min_margin, "worst_goal_relation": worst_relation,
                    "critical_routes": critical, "critical_route_count": critical_count,
                    "distinct_effective_codes": distinct_codes,
                    "path_feasibility": path_feasibility,
                    "frontier_followups": frontier_followups}
        score = entry.get("score")
        if active and key == winner:
            score = maximum + 1.0
        entries.append({"action_key": key, "score": score,
                        "trace": {"goal_set": goal_set, "stable_v2_trace": entry.get("trace")}})
    return {"status": "SCORED", "entries": entries, "reason": reason}


def score_actions(view):
    """执行 RouteSetMinimaxRanker；证据不足时整窗精确回退稳定 V2。"""
    stable = score_stable_v2(view)
    if stable.get("status") != "SCORED":
        return stable
    if view.get("schema_version") != "sitin-scoring-view/3":
        return finish(stable, [], [], False, "unsupported_scoring_view", None)
    actions = view.get("actions")
    visible = view.get("visible_state")
    seat = visible.get("seat")
    seen = set()
    for action in actions:
        key = action.get("action_key")
        kind = action.get("action_type")
        if key is None or kind is None or action.get("is_legal") is not True or key in seen:
            return finish(stable, [], [], False, "invalid_action_identity", None)
        seen.add(key)
        if kind == "hu":
            return finish(stable, [], [], False, "legal_hu_exact_v2", None)
    values = stage_values(view.get("competition"))
    if values is None:
        return finish(stable, [], [], False, "stage_account_unknown", None)
    all_paths = []
    action_rows = []
    for action in actions:
        key = action.get("action_key")
        paths = action_paths(action)
        if paths is None:
            return finish(stable, [], [], False, "rule_feasibility_unknown", None)
        action_rows.append({"action_key": key, "action": action, "paths": paths})
        for path in paths:
            all_paths.append(path)
    frontier = pareto_frontier(all_paths)
    frontier_keys = set()
    for path in frontier:
        frontier_keys.add(path.get("action_key"))
    frontier_actions = sorted(frontier_keys)
    if len(frontier_actions) < 2:
        return finish(stable, [], frontier_actions, False, "fewer_than_two_frontier_actions", None)
    summaries = []
    for key in frontier_actions:
        active_paths = []
        for path in frontier:
            if path.get("action_key") == key:
                active_paths.append(path)
        action = None
        all_action_paths = None
        for row in action_rows:
            if row.get("action_key") == key:
                action = row.get("action")
                all_action_paths = row.get("paths")
        summary = summarize_action(action, all_action_paths, active_paths, values, seat)
        if summary is None:
            return finish(stable, summaries, frontier_actions, False, "unknown_frontier_goal_set", None)
        summaries.append({"action_key": key, "summary": summary})
    winners = []
    for key in frontier_actions:
        wins_all = True
        for other_key in frontier_actions:
            if other_key != key and not dominates(summary_for(summaries, key), summary_for(summaries, other_key)):
                wins_all = False
        if wins_all:
            winners.append(key)
    if len(winners) != 1:
        return finish(stable, summaries, frontier_actions, False, "no_unique_strict_dominator", None)
    return finish(stable, summaries, frontier_actions, True, "route_set_minimax_strict_dominator", winners[0])
