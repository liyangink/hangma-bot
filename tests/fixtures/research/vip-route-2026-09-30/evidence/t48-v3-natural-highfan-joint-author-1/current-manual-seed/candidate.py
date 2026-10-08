
def waiting_score(waiting, context_adjustment):
    structure = waiting["structure"]
    standard = structure["standard_shanten"]
    seven = structure["seven_pairs_shanten"]
    shanten = standard if seven is None else min(standard, seven)
    ordinary_width = waiting["useful_code_width"]
    hu_width = waiting["legal_hu_code_width"]
    backup = 0.0
    for target, width in zip(structure["targets"], waiting["target_improvement_code_widths"]):
        if target["target_stage"] == "waiting_predecessor":
            proposal = 3.0 - 1.4 * target["natural_need"]
            proposal += 0.04 * width
            proposal -= 0.7 * target["target_white_discard_lower_bound"]
            proposal -= 0.25 * target["target_natural_discard_lower_bound"]
            backup = max(backup, proposal)
    # 两种牌型共有码只计并集；五自然对只是有界经验奖励，不过滤四对两白。
    natural_pairs = 0.7 * min(2, max(0, structure["natural_pair_count"] - 4))
    chain = min(2.0, 0.5 * waiting["chain_count"]) if waiting["baotou"] else 0.0
    return 20.0 - 4.0 * shanten + 0.10 * ordinary_width + 0.08 * hu_width + backup + natural_pairs + chain + context_adjustment

def score_actions(view):
    context = view["visible_state"]
    wall = context["remaining_tile_count"]
    late = 0.0 if wall is None else 0.2 * max(0, 35 - wall)
    opponents = sum([len(melds) for seat, melds in enumerate(context["melds"]) if seat != context["seat"]])
    dealer = 0.25 if context["seat"] == context["dealer_seat"] else 0.0
    context_adjustment = dealer - late - 0.10 * opponents
    node_indexes = {node["node_key"]: index for index, node in enumerate(view["nodes"])}
    values = []
    chosen = []
    for node in view["nodes"]:
        kind = node["kind"]
        key = node["node_key"]
        if kind == "wait":
            value = waiting_score(node["waiting"], context_adjustment)
            selected = key
        elif kind == "unknown_draw":
            # 真正补牌前结构的保守代理；不声称已知补牌后最好合法动作。
            value = waiting_score(node["waiting"], context_adjustment) - 3.0
            selected = key
        elif kind == "hu":
            normalized = node["settlement"]["score_delta"][context["seat"]] / view["binding"]["base_score"]
            value = 23.0 + 8.0 * normalized / (6.0 + abs(normalized))
            selected = key
        elif kind == "choices":
            best = node["children"][0]
            for child in node["children"]:
                if values[node_indexes[child]] > values[node_indexes[best]]:
                    best = child
            value = values[node_indexes[best]]
            selected = chosen[node_indexes[best]]
        else:
            # 全相容补牌码下端；码宽度仅是启发式，不是概率或积分下界。
            lower = min([values[node_indexes[child]] for child in node["children"]])
            if kind == "replacement":
                improvements = sum([1 for child in node["children"] if values[node_indexes[child]] > lower + 1.0])
                value = lower + 0.06 * improvements
            else:
                value = lower
            selected = key
        values.append(value)
        chosen.append(selected)
    entries = []
    for action in view["actions"]:
        key = action["node_key"]
        entries.append({"action_key": action["action_key"], "score": values[node_indexes[key]], "trace": {
            "unit": "heuristic_rank_points", "selected_conditional_node": chosen[node_indexes[key]],
            "root_condition": action["pending_condition"], "formula": "vip_balanced_seed/1",
        }})
    return {"status": "SCORED", "entries": entries}
