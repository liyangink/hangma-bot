"""m1联合公式：逐目标自身完成成本、独立自然准备备用与近条件支付的联合排序。"""

PAYCAP = 50.0
PAYREF = 192.0
HUBASE = 10.0
WAITBASE = 12.0
FORMCOST = 3.5
SPEEDCAP = 4.8
SPEEDREF = 12.0
VARREF = 4.0
UNSEENSOFT = 0.75
PURPOSES = (0.0, 3.4, 8.1, 13.0, 18.4)
HORIZONCOST = 0.35
NATDROPCOST = 0.18
WHITEDROPCOST = 0.32
TERMDRAW = 0.50
TARGETMASSREF = 2.0
TARGETGATEBASE = 0.50
EXITFLOOR = 0.40
EXITMASSREF = 6.0
EXITWIDTHREF = 3.0
EXITSTEPDECAY = 0.25
PORTCAP = 2.2
PORTREF = 12.0
BRANCHGAP = 0.15
PREPBUDGET = 0.60
COMPLETIONLINEAR = 0.75
COMPLETIONSQUARE = 0.35
RESCUEDECAY = 0.30
STAGEPRICE = 1.0
LOCALCAP = 6.0
LOCALREF = 8.0
KNOWNPAYLINEAR = 0.45
PAYMASSREF = 8.0
SINGLESCOPE = 0.75
ENVELOPEBLEND = 0.25
COVREF = 3.0
QUALUNKNOWN = 0.7
QUALUNANALYSED = 1.0
UNKNOWNDRAW = 2.5
UNANCHOREXPOSURE = 0.15
CONDITIONBLEND = 0.20
CONDITIONCAP = 1.0
REPLACEMENTBLEND = 0.40
REPLACEMENTCAP = 2.3
CLAIMCOST = 0.25
SKIPVALUE = 0.10
GANGCOST = 0.12
PAIRPRIORWEIGHT = 0.30
NETUPGRADEWEIGHT = 1.40
NETUPWIDTHREF = 4.0
NETEXITWIDTHREF = 4.0
NETWAITFLOOR = 0.35
NETANCHORPRICE = 0.30
NETCARRY = 0.25
NETDISTANCE = 0.75
ANCHOROPTIONBASE = 0.14
ANCHOROPTIONSTEP = 0.10
ANCHORFALLBACKCOST = 0.45
ANCHORUNKNOWNCOST = 0.35
ANCHREADY = 0.18
RETENTION = 20
WALLSOFT = 8.0
UNKNOWNWALLSCALE = 0.70
OPPDECAY = 0.05
RISKBASE = 1.8
OPPRISK = 0.12
LATERISK = 3.4
UNKNOWNWALLRISK = 0.7


def paypoints(amount):
    """本家净积分除基础分后的有界排序点；不是未来积分或摸牌概率。"""
    return PAYCAP * amount / (PAYREF + abs(amount))


def stockof(slot, waiting):
    """返回排序库存、精确张数与未知标记；公开容量含他家暗牌。

    精确零关闭本码；保守正下界支持排序；保守零与未知保留软支持，
    不写回资格或支付，也不除以墙余冒充概率。
    """
    capacity = waiting["unseen_capacities"][slot]
    evidence = waiting["unseen_evidence"][slot]
    if evidence == "exact" and capacity is not None:
        return float(capacity), capacity, 0
    if evidence == "conservative" and capacity is not None and capacity > 0:
        return float(capacity), 0, 1
    return UNSEENSOFT, 0, 1


def routesupport(codes, codeindex, drawscale, stock):
    """按规范牌码去重的一步推进支持；同码只计一次，不跨路线相加。"""
    mass = 0.0
    exact = 0
    width = 0
    uncertain = 0
    seen = set()
    for code in codes:
        if code not in seen:
            seen.add(code)
            inventory, precise, unknown = stock[codeindex[code]]
            if inventory > 0.0:
                mass += inventory
                exact += precise
                width += 1
                uncertain += unknown
    credit = (drawscale * SPEEDCAP * mass / (SPEEDREF + mass)
              * float(width) / (VARREF + float(width)))
    return credit, mass, width, exact, uncertain


def purposescale(length, room, drawscale, pressure):
    """墙余与公开副露折减的条件先验；length不是保证的本人摸牌次数。"""
    excess = 0.0 if room is None else max(0.0, float(length) - room)
    return drawscale * pressure / (1.0 + HORIZONCOST * excess)


def prepvalue(waiting):
    """不借白、不含将的自然面子准备事实与0—1成熟度折减系数。"""
    prep = waiting["natural_preparation"]
    need = prep["natural_draw_lower_bound"]
    discard = prep["natural_discard_lower_bound"]
    width = waiting["natural_preparation_code_width"]
    burden = float(max(need, discard))
    readiness = 1.0 / (1.0 + COMPLETIONLINEAR * burden + COMPLETIONSQUARE * burden * burden)
    if need > 0 and width == 0:
        readiness = 0.0
    return need, discard, width, readiness


def actualroute(shanten, support, structural):
    """真实向听加出口支持的路线上限；L不是保证还需摸几次。"""
    length = max(0, shanten) + 1
    value = support[0] - FORMCOST * float(length - 1) + structural
    return shanten, length, support[0], support[1], support[2], support[4], value


def paysummary(waiting, seat, base):
    """条件胡支付的逐码流式摘要；同码两抓打假设互斥，只取下端加有界价差。

    返回状态、容量加权平均点、码数、总容量与逐码(容量,包络点)。
    状态0未分析、1已知空、2有支付、3部分未知；未知码不当零支付。
    """
    payments = waiting["normal_draw_hu_payments"]
    if payments is None:
        return 0, None, 0, 0.0, ()
    partial = len(waiting["qualification_unknown_codes"]) > 0
    if not payments:
        if partial:
            return 3, 0.0, 0, 0.0, ()
        return 1, 0.0, 0, 0.0, ()
    groups = []
    currentcode = None
    lower = 0.0
    upper = 0.0
    capacity = 0.0
    rows = 0
    for payment in payments:
        amount = float(payment["settlement"]["score_delta"][seat]) / base
        point = paypoints(amount)
        code = payment["draw_code"]
        if code != currentcode:
            if currentcode is not None:
                groups.append((capacity, lower, upper, rows))
            currentcode = code
            lower = point
            upper = point
            capacity = float(payment["draw_capacity_before"])
            rows = 1
        else:
            if point < lower:
                lower = point
            if point > upper:
                upper = point
            rows += 1
    groups.append((capacity, lower, upper, rows))
    total = 0.0
    mass = 0.0
    offers = []
    for group in groups:
        if group[3] == 1:
            envelope = SINGLESCOPE * group[1]
        else:
            envelope = group[1] + ENVELOPEBLEND * (group[2] - group[1])
        total += group[0] * envelope
        mass += group[0]
        offers.append((group[0], envelope))
    state = 3 if partial else 2
    return state, total / mass, len(offers), mass, tuple(offers)


def paycredit(payment, coverage, drawscale, pressure):
    """近条件支付转有限信用；两种变换择大，不重复计同码机会。"""
    point = payment[1]
    if point is None or point <= 0.0:
        return 0.0, 0.0, 0.0
    scale = coverage * drawscale * pressure
    saturated = LOCALCAP * point / (LOCALREF + point) * scale
    linear = KNOWNPAYLINEAR * point * (payment[3] / (PAYMASSREF + payment[3])) * scale
    if linear > saturated:
        return saturated, linear, linear
    return saturated, linear, saturated


def jointwait(waiting, standard, seven, prep, local, codeindex, room, drawscale, pressure, stock):
    """逐目标流式选择与共享34码边际支持上界的备用组合。

    每个目标用自身D、自然待弃、白待弃与终点摸牌定价，不再套同手
    全自然准备缺张；准备只作为主出口、已见证胡码与已选目标未占用
    码上的独立发展路线。同码多来源取最大权重后统一饱和，不把不同
    目标当独立概率，也不重复计同码机会。
    """
    main = standard
    maincodes = waiting["standard_useful_codes"]
    if seven is not None and seven[6] > main[6]:
        main = seven
        maincodes = waiting["seven_pairs_useful_codes"]
    whites = waiting["structure"]["whites_held"]
    ordinary = main[6] + local
    best = None
    option = None
    for index, target in enumerate(waiting["structure"]["targets"]):
        route = standard if target["family"] == "standard" else seven
        if route is not None:
            terminal = 1 if target["requires_terminal_draw"] else 0
            need = target["natural_need"]
            naturaldrop = target["target_natural_discard_lower_bound"]
            whitedrop = target["target_white_discard_lower_bound"]
            retained = target["retained_whites"]
            width = waiting["target_improvement_code_widths"][index]
            predecessor = target["target_stage"] == "waiting_predecessor"
            targetmass = 0.0
            for code in target["conditional_need_improvement_codes"]:
                targetmass += stock[codeindex[code]][0]
            targetgate = 1.0
            if need > 0:
                targetgate = 0.0
                if width > 0 and targetmass > 0.0:
                    targetgate = (TARGETGATEBASE + (1.0 - TARGETGATEBASE)
                                  * targetmass / (TARGETMASSREF + targetmass))
            own = (float(need) + NATDROPCOST * float(naturaldrop)
                   + WHITEDROPCOST * float(whitedrop) + TERMDRAW * float(terminal))
            effort = max(float(route[1]), own)
            earned = 1.0 / (1.0 + COMPLETIONLINEAR * effort + COMPLETIONSQUARE * effort * effort)
            rescue = 1.0 / (1.0 + RESCUEDECAY * effort)
            exitmass = max(0.0, route[3])
            exitwidth = float(route[4])
            exitgate = exitmass / (EXITMASSREF + exitmass) * exitwidth / (EXITWIDTHREF + exitwidth)
            exitgate = exitgate / (1.0 + EXITSTEPDECAY * float(route[1] - 1))
            prior = PURPOSES[retained] if predecessor else 0.0
            exitfactor = EXITFLOOR + (1.0 - EXITFLOOR) * exitgate
            purposecredit = (prior * purposescale(effort, room, drawscale, pressure)
                             * targetgate * earned * exitfactor)
            stagecost = STAGEPRICE * max(0.0, effort - float(route[1])) * (1.0 - rescue)
            rescued = local * rescue
            prospective = rescued + purposecredit - stagecost
            value = route[6] + prospective
            if best is None or value > best[10]:
                best = (index, target["family"], retained, need, terminal, effort,
                        naturaldrop, whitedrop, width, prospective, value)
            gain = max(0.0, value - ordinary)
            if predecessor and retained > 0 and retained <= whites and gain > 0.0:
                if option is None or gain > option[8]:
                    option = (index, target["family"], retained, need, width, prior,
                              exitgate, targetgate, gain, targetmass, earned, effort,
                              rescue, prospective)
    baseline = set(maincodes)
    knownhu = waiting["legal_hu_draw_codes"]
    if knownhu is not None:
        for code in knownhu:
            baseline.add(code)
    primaryvalue = ordinary
    if best is not None and best[10] > ordinary:
        primaryvalue = best[10]
        selected = waiting["structure"]["targets"][best[0]]
        if selected["family"] == "standard":
            selectedcodes = waiting["standard_useful_codes"]
        else:
            selectedcodes = waiting["seven_pairs_useful_codes"]
        for code in selectedcodes:
            baseline.add(code)
        for code in selected["conditional_need_improvement_codes"]:
            baseline.add(code)
    plans = []
    branches = [(standard, waiting["standard_useful_codes"])]
    if seven is not None:
        branches.append((seven, waiting["seven_pairs_useful_codes"]))
    for route, codes in branches:
        steps = float(route[1] - 1)
        gap = max(0.0, primaryvalue - (route[6] + local))
        excess = 0.0 if room is None else max(0.0, float(route[1]) - room)
        weight = 1.0 / ((1.0 + steps * steps + BRANCHGAP * gap) * (1.0 + HORIZONCOST * excess))
        for code in codes:
            slot = codeindex[code]
            if code not in baseline and stock[slot][0] > 0.0:
                plans.append((slot, weight))
    if prep[0] > 0 and prep[2] > 0:
        preplength = max(standard[1], prep[0] + 1, prep[1])
        excess = 0.0 if room is None else max(0.0, float(preplength) - room)
        gap = max(0.0, primaryvalue - (standard[6] + local))
        prepweight = PREPBUDGET * prep[3] / ((1.0 + BRANCHGAP * gap) * (1.0 + HORIZONCOST * excess))
        for code in waiting["natural_preparation"]["natural_need_improvement_codes"]:
            slot = codeindex[code]
            if code not in baseline and stock[slot][0] > 0.0:
                plans.append((slot, prepweight))
    combined = []
    currentslot = None
    peak = 0.0
    for plan in sorted(plans):
        if plan[0] != currentslot:
            if currentslot is not None:
                combined.append((currentslot, peak))
            currentslot = plan[0]
            peak = plan[1]
        elif plan[1] > peak:
            peak = plan[1]
    if currentslot is not None:
        combined.append((currentslot, peak))
    mass = 0.0
    diversity = 0.0
    exact = 0
    codecount = 0
    uncertain = 0
    for entry in combined:
        inventory = stock[entry[0]][0]
        if inventory > 0.0:
            mass += entry[1] * inventory
            diversity += entry[1]
            exact += stock[entry[0]][1]
            codecount += 1
            uncertain += stock[entry[0]][2]
    credit = (drawscale * pressure * PORTCAP * mass / (PORTREF + mass)
              * diversity / (VARREF + diversity))
    if option is not None:
        incremental = max(0.0, option[8] - credit)
        if incremental <= 0.0:
            option = None
        else:
            option = option[:8] + (incremental,) + option[9:]
    portfolio = (mass, diversity, exact, codecount, uncertain, credit, float(len(baseline)))
    return best, portfolio, option


def huoffer(anchor, discount, risk, payment, main, portfolio, option):
    """当前胡与继续等待的净取舍；只消费扣过备用支持的净目标增量。

    直接升级按同码包络差计算，远目标只吃超过备用信用的增量；
    再共同扣除确定胡的机会成本、等待费与距离费。全部是排序点，
    不是期望积分或存活率。
    """
    mass = payment[3]
    width = float(payment[2])
    exitgate = mass / (PAYMASSREF + mass) * width / (NETEXITWIDTHREF + width)
    distancegate = 1.0 / (1.0 + NETDISTANCE * float(main[1] - 1))
    preserved = 0.0
    upgradeamount = 0.0
    upgrademass = 0.0
    upgradewidth = 0
    downsideamount = 0.0
    for offer in payment[4]:
        capacity = offer[0]
        point = offer[1]
        preserved += capacity * min(anchor, max(0.0, point))
        difference = point - anchor
        if difference > 0.0:
            upgradeamount += capacity * difference
            upgrademass += capacity
            upgradewidth += 1
        else:
            downsideamount += capacity * max(0.0, -difference)
    floorfraction = 0.0
    if mass > 0.0 and anchor > 0.0:
        floorfraction = preserved / (mass * anchor)
    maintained = exitgate * floorfraction * distancegate
    upgradesupport = (upgrademass / (PAYMASSREF + upgrademass)
                      * float(upgradewidth) / (NETUPWIDTHREF + float(upgradewidth)))
    upgrade = 0.0
    if upgrademass > 0.0:
        upgrade = (NETUPGRADEWEIGHT * discount * upgradeamount / upgrademass
                   * upgradesupport * distancegate)
    downside = discount * downsideamount / (PAYMASSREF + mass)
    direct = upgrade - downside
    remote = 0.0
    remoteprice = 0.0
    fallback = 0.0
    offervalue = direct
    channel = "direct_upgrade"
    if option is not None:
        remoteprice = anchor * (ANCHOROPTIONBASE + ANCHOROPTIONSTEP * option[11])
        if payment[1] is None:
            fallback = ANCHORUNKNOWNCOST * anchor
        else:
            fallback = ANCHORFALLBACKCOST * max(0.0, anchor - max(0.0, payment[1]))
        remote = discount * option[8] - remoteprice - fallback
        if remote > offervalue:
            offervalue = remote
            channel = "completion_gain"
    ordinarycore = max(0.0, main[6] + portfolio[5])
    carry = NETCARRY * discount * maintained * ordinarycore
    opportunity = NETANCHORPRICE * anchor * (1.0 - discount * maintained)
    waitfee = risk * (NETWAITFLOOR + (1.0 - NETWAITFLOOR) * (1.0 - maintained))
    distancefee = ANCHREADY * max(0.0, -main[6])
    net = offervalue + carry - opportunity - waitfee - distancefee
    return (net, channel, upgrade, downside, maintained, carry, opportunity,
            waitfee, remote, remoteprice, fallback, offervalue)


def waitvalue(waiting, codeindex, seat, base, room, drawscale, pressure, discount, risk, anchor, unknowncost):
    """同一联合完成成本下评价普通出口、七对、逐目标用途与当前胡。"""
    structure = waiting["structure"]
    stock = []
    for slot in range(len(waiting["unseen_capacities"])):
        stock.append(stockof(slot, waiting))
    prep = prepvalue(waiting)
    standard = actualroute(structure["standard_shanten"],
                           routesupport(waiting["standard_useful_codes"], codeindex, drawscale, stock),
                           0.0)
    seven = None
    main = standard
    family = "standard"
    if structure["seven_pairs_shanten"] is not None:
        sevenlength = max(0, structure["seven_pairs_shanten"]) + 1
        pairprior = (PAIRPRIORWEIGHT
                     * float(min(2, max(0, structure["natural_pair_count"] - 4)))
                     / float(sevenlength))
        seven = actualroute(structure["seven_pairs_shanten"],
                            routesupport(waiting["seven_pairs_useful_codes"], codeindex, drawscale, stock),
                            pairprior * drawscale * pressure)
        if seven[6] > main[6]:
            main = seven
            family = "seven_pairs"
    payment = paysummary(waiting, seat, base)
    known = payment[2]
    unknown = len(waiting["qualification_unknown_codes"])
    coverage = float(known) / (COVREF + float(known))
    if payment[0] == 0:
        qualcost = QUALUNANALYSED
    else:
        qualcost = QUALUNKNOWN * float(unknown) / float(1 + known + unknown)
    credit = paycredit(payment, coverage, drawscale, pressure)
    local = credit[2]
    ordinary = main[6] + local
    best, portfolio, option = jointwait(waiting, standard, seven, prep, local, codeindex,
                                        room, drawscale, pressure, stock)
    joint = ordinary
    chosen = family
    if best is not None and best[10] > joint:
        joint = best[10]
        chosen = "completion_budget"
    joint += portfolio[5]
    if anchor is not None:
        ready = huoffer(anchor, discount, risk, payment, main, portfolio, option)
        value = HUBASE + anchor + ready[0] - qualcost - unknowncost
    else:
        ready = None
        value = WAITBASE + joint - qualcost - unknowncost - UNANCHOREXPOSURE * risk
    facts = (standard, seven, best, prep, portfolio, payment, ordinary, joint, chosen,
             local, qualcost, ready, option)
    return value, facts


def score_actions(view):
    """对全部冻结后序节点一次共享计算，并给每个合法根恰一条有限评分。

    choices才在合法续行中择优；replacement与condition消费全部相容边
    的下端加有界价差，不挑最好补牌；机械缺口显式弃权。无文件、网络、
    时钟、随机或跨调用缓存。
    """
    context = view["visible_state"]
    seat = context["seat"]
    base = float(view["binding"]["base_score"])
    wall = context["remaining_tile_count"]
    opponents = 0
    for otherseat, melds in enumerate(context["melds"]):
        if otherseat != seat:
            opponents += len(melds)
    pressure = 1.0 / (1.0 + OPPDECAY * float(opponents))
    if wall is None:
        room = None
        drawscale = UNKNOWNWALLSCALE
        discount = drawscale * pressure
        risk = RISKBASE + OPPRISK * float(opponents) + UNKNOWNWALLRISK
    else:
        margin = max(0.0, float(wall) - float(RETENTION))
        room = max(1.0, margin / 4.0)
        drawscale = 1.0 if margin > 0.0 else 0.0
        discount = drawscale * pressure * (0.30 + 0.70 * margin / (WALLSOFT + margin))
        risk = RISKBASE + OPPRISK * float(opponents) + LATERISK * WALLSOFT / (WALLSOFT + margin)
    codeindex = {code: index for index, code in enumerate(view["tile_order"])}
    nodes = view["nodes"]
    indexes = {node["node_key"]: index for index, node in enumerate(nodes)}
    anchor = None
    for action in view["actions"]:
        node = nodes[indexes[action["node_key"]]]
        if node["kind"] == "hu":
            amount = float(node["settlement"]["score_delta"][seat]) / base
            point = paypoints(amount)
            if anchor is None or point > anchor:
                anchor = point
    values = []
    factslist = []
    for node in nodes:
        if node["gap_kind"] is not None:
            return {"status": "ABSTAIN", "reason": "graph_gap"}
        kind = node["kind"]
        children = node["children"]
        if kind == "wait" or kind == "unknown_draw":
            unknowncost = UNKNOWNDRAW if kind == "unknown_draw" else 0.0
            value, facts = waitvalue(node["waiting"], codeindex, seat, base, room, drawscale,
                                     pressure, discount, risk, anchor, unknowncost)
        elif kind == "hu":
            amount = float(node["settlement"]["score_delta"][seat]) / base
            value = HUBASE + paypoints(amount)
            facts = None
        elif kind == "choices":
            if not children:
                return {"status": "ABSTAIN", "reason": "empty_choices"}
            bestindex = indexes[children[0]]
            value = values[bestindex]
            for child in children:
                childindex = indexes[child]
                if values[childindex] > value:
                    bestindex = childindex
                    value = values[childindex]
            facts = factslist[bestindex]
        else:
            if not children:
                return {"status": "ABSTAIN", "reason": "empty_condition"}
            value = values[indexes[children[0]]]
            total = 0.0
            for child in children:
                childvalue = values[indexes[child]]
                total += childvalue
                if childvalue < value:
                    value = childvalue
            lower = value
            mean = total / float(len(children))
            blend = REPLACEMENTBLEND if kind == "replacement" else CONDITIONBLEND
            cap = REPLACEMENTCAP if kind == "replacement" else CONDITIONCAP
            value = lower + min(cap, blend * max(0.0, mean - lower))
            facts = None
        values.append(value)
        factslist.append(facts)
    entries = []
    actioncount = len(view["actions"])
    for action in view["actions"]:
        index = indexes[action["node_key"]]
        kind = action["action_type"]
        adjustment = 0.0
        if kind == "chi" or kind == "peng":
            adjustment = SKIPVALUE * float(action["skipped_seats"]) * drawscale - CLAIMCOST
        elif kind == "gang":
            adjustment = -GANGCOST
        value = values[index] + adjustment
        pairs = [("condition", action["pending_condition"]), ("adjust", round(adjustment, 3))]
        facts = factslist[index]
        if facts is not None and actioncount <= 24:
            payment = facts[5]
            if payment[1] is None:
                avgpoint = None
            else:
                avgpoint = round(payment[1], 3)
            pairs.append(("pay", (payment[0], avgpoint, payment[2], round(payment[3], 3))))
            pairs.append(("joint", (round(facts[6], 3), round(facts[7], 3), facts[8],
                                   round(facts[9], 3), round(facts[10], 3))))
            pairs.append(("portfolio", tuple([round(part, 3) for part in facts[4]])))
            best = facts[2]
            if best is None:
                pairs.append(("target", None))
            else:
                pairs.append(("target", (best[0], best[1], best[2], best[3], round(best[5], 3),
                                         round(best[9], 3), round(best[10], 3))))
            ready = facts[11]
            if ready is None:
                pairs.append(("offer", None))
            else:
                pairs.append(("offer", (round(ready[0], 3), ready[1], round(ready[2], 3),
                                        round(ready[3], 3), round(ready[4], 3))))
            pairs.append(("prep", (facts[3][0], facts[3][1], facts[3][2], round(facts[3][3], 3))))
        if not entries:
            pairs.append(("unit", "heuristic_rank_points"))
            pairs.append(("formula", "vip_joint_target_cost_m1/1"))
            if anchor is None:
                anchorvalue = None
            else:
                anchorvalue = round(anchor, 3)
            pairs.append(("context", (wall, opponents, round(discount, 3), round(risk, 3), anchorvalue)))
            pairs.append(("unknown", "opponent_hu_and_future_draw_reachability"))
            pairs.append(("scope", "conditional_facts_not_probability_or_guaranteed_highfan"))
        entries.append({"action_key": action["action_key"], "score": value, "trace": dict(pairs)})
    return {"status": "SCORED", "entries": entries}