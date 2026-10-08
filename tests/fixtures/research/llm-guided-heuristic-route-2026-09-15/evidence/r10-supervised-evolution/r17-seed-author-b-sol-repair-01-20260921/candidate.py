def score_actions(view):
    """低计费地组合公开双路线、家族进展和完整赛事账。"""
    window = view["window"]
    root = view["root"]
    leaf = view["next"]

    standard_after = leaf["standard_shanten_after"]
    standard_progress = root["standard_shanten_after"] - standard_after
    score = 0.28 - 0.10 * standard_after + 0.06 * standard_progress

    seven_after = leaf["seven_pairs_shanten_after"]
    seven_available = seven_after is not None
    if seven_available:
        score = score + 0.10 - 0.04 * seven_after
        seven_before = root["seven_pairs_shanten_after"]
        if seven_before is not None:
            score = score + 0.04 * (seven_before - seven_after)

    branch_value = 0.0
    chain_value = 0.0
    white_value = 0.0
    baotou_value = 0.0

    for fact in root["family_progress"]:
        progress = fact["progress"]
        route_status = fact["route_status"]
        direction = 0.0
        if route_status != "unanalyzed" and progress != "unknown":
            if progress == "advance":
                direction = 1.0
            elif progress == "retreat" or progress == "close":
                direction = -1.0
            if route_status == "open_uncertain":
                direction = 0.5 * direction

        family = fact["family"]
        if family == "branch":
            branch_value = direction
        elif family == "chain":
            chain_value = direction
        elif family == "four_white":
            white_value = direction
        elif family == "baotou":
            baotou_value = direction

    chain_count = window["chain_count"]
    baotou = window["baotou"]
    wealth_count = window["wealth_count"]
    family_score = 0.09 * branch_value
    family_score = family_score + (0.03 + 0.015 * chain_count) * chain_value
    family_score = family_score + (0.03 + 0.015 * wealth_count) * white_value
    if baotou:
        family_score = family_score + 0.025 * chain_value + 0.06 * baotou_value
    else:
        family_score = family_score + 0.03 * baotou_value

    chain_piao = window["chain_piao"]
    if chain_piao is not None and chain_piao > 0:
        family_score = family_score + 0.015 * white_value

    if root["discard_code"] == "白" and wealth_count > 0:
        special_value = chain_value + white_value + baotou_value
        if special_value < 0.0:
            family_score = family_score + 0.03 * special_value

    score = score + family_score

    current_stage_scores = window["current_stage_scores"]
    freshness_masks = window["freshness_masks"]
    if current_stage_scores is not None and freshness_masks is not None:
        if freshness_masks[0] == "stage_account:complete":
            own_score = current_stage_scores[window["seat"]]
            ahead_count = 0
            for stage_score in current_stage_scores:
                if stage_score > own_score:
                    ahead_count = ahead_count + 1
            if ahead_count >= 2:
                if standard_progress > 0:
                    score = score + 0.03 * standard_progress
                if family_score > 0.0:
                    score = score + 0.35 * family_score
            elif ahead_count == 0:
                if seven_available:
                    score = score + 0.03
                if family_score < 0.0:
                    score = score + 0.35 * family_score

    if leaf["action_type"] == "gang":
        score = 0.75 * score - 0.08

    if score > 1.0:
        return 1.0
    if score < -1.0:
        return -1.0
    return score
