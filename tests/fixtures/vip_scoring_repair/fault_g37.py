"""E1联合启发式：共享凸阶梯价前沿加独占码红利，并重定保白k取舍。

全部数值为启发式排序点；距离刻度、码宽与公开容量都不是摸牌概率、
期望积分或存活证明。只读冻结公开事实；条件支付与结构距离不提升为
必达高番。不生成后态、need-1曲线或杠补择优；原共享图只计算一次。
"""

PAYCAP = 50.0
PAYREF = 192.0
PAYMASSREF = 8.0
HUBASE = 10.0
WAITBASE = 12.0
FORMCOST = 3.5
TAILOFF = 2
TAILQUAD = 0.45
SPEEDCAP = 4.8
SPEEDREF = 12.0
VARREF = 4.0
LINKCAP = 2.0
UNSEENSOFT = 0.75
PURPOSES = (0.0, 2.5, 6.0, 13.0, 26.0)
DEALERBOOST = 1.20
WHITEHOLD = 0.30
EXTRAPATH = 1.25
ACTREF = 3.0
DIVCAP = 1.6
DIVREF = 4.0
DIVGAP = 0.35
DIVCLOSE = 0.30
DIVTOTAL = 2.2
PREPBASE = 0.60
PREPMATURE = 0.35
LOCALCAP = 6.0
LOCALREF = 8.0
COVREF = 3.0
ENVELOPEBLEND = 0.25
SINGLESCOPE = 0.75
PAIRPRIORWEIGHT = 0.30
HORIZONCOST = 0.35
RETENTION = 20
WALLSOFT = 8.0
UNKNOWNWALLSCALE = 0.70
OPPDECAY = 0.05
RISKBASE = 1.8
OPPRISK = 0.12
LATERISK = 3.4
UNKNOWNWALLRISK = 0.7
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
ANCHOROPTIONBASE = 0.14
ANCHOROPTIONSTEP = 0.10
ANCHORFALLBACKCOST = 0.45
ANCHORUNKNOWNCOST = 0.35
NETUPGRADEWEIGHT = 1.40
NETUPWIDTHREF = 4.0
NETEXITWIDTHREF = 4.0
NETANCHORPRICE = 0.30
NETRISKFEE = 0.45
NETCARRY = 0.25


def paypoints(amount):
    """本家净积分/基础分的有界排序点；不是期望积分或概率。"""
    return PAYCAP * amount / (PAYREF + abs(amount))


def stockof(slot, waiting):
    """公开容量只作排序支持；精确零关闭本码，保守/未知软保留。

    不把容量除以墙余，也不改写资格或支付事实。
    """
    capacity = waiting["unseen_capacities"][slot]
    evidence = waiting["unseen_evidence"][slot]
    if evidence == "exact" and capacity is not None:
        return float(capacity), capacity, 0
    if evidence == "conservative" and capacity is not None and capacity > 0:
        return float(capacity), 0, 1
    return UNSEENSOFT, 0, 1


def summaryof(codes, codeindex, stock):
    """去重码集的支持摘要；单码质量按LINKCAP截顶，防一码四张冒充多码。"""
    mass = 0.0
    width = 0
    exact = 0
    uncertain = 0
    seen = set()
    for code in codes:
        if code not in seen:
            seen.add(code)
            cell = stock[codeindex[code]]
            if cell[0] > 0.0:
                mass += min(cell[0], LINKCAP)
                width += 1
                exact += cell[1]
                uncertain += cell[2]
    return mass, width, exact, uncertain


def speedof(mass, width, scale):
    """速度质量核：截顶质量与码宽的乘积饱和，仅是排序支持。"""
    return (scale * SPEEDCAP * mass / (SPEEDREF + mass)
            * float(width) / (VARREF + float(width)))


def ladder(steps):
    """共享凸节奏价：线性段加凸尾；steps是距离刻度，不是保证摸牌次数。"""
    linear = FORMCOST * steps
    tail = steps - TAILOFF
    if tail > 0:
        return linear + TAILQUAD * tail * tail
    return linear


def horizon(bound, room):
    """墙余对指定条件路径下界的一次折价；room不是保证本人摸牌额度。"""
    excess = 0.0 if room is None else max(0.0, float(bound) - room)
    return 1.0 / (1.0 + HORIZONCOST * excess)


def paysummary(waiting, seat, base):
    """条件支付逐码合并互斥抓打包络；同码两假设不相加，未知码不填零。"""
    payments = waiting["normal_draw_hu_payments"]
    if payments is None:
        return 0, None, 0, 0.0, ()
    partial = len(waiting["qualification_unknown_codes"]) > 0
    if not payments:
        return (3 if partial else 1), 0.0, 0, 0.0, ()
    groups = []
    current = None
    lower = 0.0
    upper = 0.0
    capacity = 0.0
    rows = 0
    for payment in payments:
        point = paypoints(float(payment["settlement"]["score_delta"][seat]) / base)
        code = payment["draw_code"]
        if code != current:
            if current is not None:
                groups.append((capacity, lower, upper, rows))
            current = code
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
    return (3 if partial else 2), total / mass, len(offers), mass, tuple(offers)


def payroute(payment, coverage, scale):
    """已见证条件支付作为长度0路线的质量；容量与码宽只是排序门。"""
    point = payment[1]
    if point is None or point <= 0.0 or payment[2] <= 0:
        return 0.0
    gate = (payment[3] / (PAYMASSREF + payment[3])
            * float(payment[2]) / (NETEXITWIDTHREF + float(payment[2])))
    return LOCALCAP * point / (LOCALREF + point) * gate * coverage * scale


def huoffer(anchor, discount, risk, payment, option, plaincore):
    """当前胡与继续的净比较；等待暴露合并为一次锚价加风险费。

    直接升级按同码包络差计；远用途只领前沿净差；不把组合弹性当弃胡收益。
    """
    mass = payment[3]
    width = float(payment[2])
    exitgate = mass / (PAYMASSREF + mass) * width / (NETEXITWIDTHREF + width)
    preserved = 0.0
    upgradeamount = 0.0
    upgrademass = 0.0
    upgradewidth = 0
    downsideamount = 0.0
    for capacity, point in payment[4]:
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
    maintained = exitgate * floorfraction
    upgradesupport = (upgrademass / (PAYMASSREF + upgrademass)
                      * float(upgradewidth) / (NETUPWIDTHREF + float(upgradewidth)))
    upgrade = 0.0
    if upgrademass > 0.0:
        upgrade = NETUPGRADEWEIGHT * discount * upgradeamount / upgrademass * upgradesupport
    downside = discount * downsideamount / (PAYMASSREF + mass)
    offervalue = upgrade - downside
    channel = "direct_upgrade"
    remote = 0.0
    remoteprice = 0.0
    fallback = 0.0
    if option is not None:
        remoteprice = anchor * (ANCHOROPTIONBASE + ANCHOROPTIONSTEP * float(option[1]))
        if payment[1] is None:
            fallback = ANCHORUNKNOWNCOST * anchor
        else:
            fallback = ANCHORFALLBACKCOST * max(0.0, anchor - max(0.0, payment[1]))
        remote = discount * option[0] - remoteprice - fallback
        if remote > offervalue:
            offervalue = remote
            channel = "purpose_frontier_surplus"
    carry = NETCARRY * discount * maintained * max(0.0, plaincore)
    exposure = (NETANCHORPRICE * anchor + NETRISKFEE * risk) * (1.0 - discount * maintained)
    net = offervalue + carry - exposure
    return (net, channel, upgrade, downside, maintained, carry, exposure,
            remote, remoteprice, fallback)


def routewait(waiting, codeindex, seat, base, room, drawscale, pressure,
              discount, risk, anchor, unknowncost, dealerboost):
    """一个等待态的阶梯前沿与独占红利；重叠码不重复购买。

    每条路线(普通、七对、已见证支付、自然准备、合格保白前驱)在同一
    凸阶梯上付距离价，前沿取最大；非赢家只按独占码领取封顶红利。
    保白用途按每张白常数持有价，先验随k跃升，负担不再随k双重加罚。
    """
    structure = waiting["structure"]
    stock = []
    for slot in range(len(waiting["unseen_capacities"])):
        stock.append(stockof(slot, waiting))
    scale = drawscale * pressure
    payment = paysummary(waiting, seat, base)
    coverage = float(payment[2]) / (COVREF + float(payment[2]))
    routes = []
    standardsteps = float(max(0, structure["standard_shanten"]))
    standardsummary = summaryof(waiting["standard_useful_codes"], codeindex, stock)
    standardquote = speedof(standardsummary[0], standardsummary[1], scale) - ladder(standardsteps)
    routes.append((standardquote, standardsteps, waiting["standard_useful_codes"],
                   "standard", None))
    sevenquote = None
    sevensteps = 0.0
    if (structure["seven_pairs_shanten"] is not None
            and waiting["seven_pairs_useful_codes"] is not None):
        sevensteps = float(max(0, structure["seven_pairs_shanten"]))
        sevensummary = summaryof(waiting["seven_pairs_useful_codes"], codeindex, stock)
        pairprior = (PAIRPRIORWEIGHT * float(min(2, max(0, structure["natural_pair_count"] - 4)))
                     / (sevensteps + 1.0))
        sevenquote = (speedof(sevensummary[0], sevensummary[1], scale)
                      + pairprior * scale - ladder(sevensteps))
        routes.append((sevenquote, sevensteps, waiting["seven_pairs_useful_codes"],
                       "seven_pairs", None))
    if payment[2] > 0 and waiting["legal_hu_draw_codes"] is not None:
        routes.append((payroute(payment, coverage, scale), 0.0,
                       waiting["legal_hu_draw_codes"], "witnessed_payment", None))
    prep = waiting["natural_preparation"]
    prepneed = prep["natural_draw_lower_bound"]
    prepdiscard = prep["natural_discard_lower_bound"]
    prepwidth = waiting["natural_preparation_code_width"]
    if prepneed <= 0:
        readiness = 1.0
    elif prepwidth > 0:
        readiness = 1.0 / (1.0 + PREPMATURE * float(prepneed))
    else:
        readiness = 0.0
    prepsteps = max(standardsteps, float(prepneed))
    prepquote = (standardquote + PREPBASE * readiness * scale * horizon(prepneed, room)
                 - (ladder(prepsteps) - ladder(standardsteps)))
    routes.append((prepquote, prepsteps, prep["natural_need_improvement_codes"],
                   "natural_preparation", None))
    plainroutes = len(routes)
    whites = structure["whites_held"]
    for index, target in enumerate(structure["targets"]):
        retained = target["retained_whites"]
        eligible = (target["target_stage"] == "waiting_predecessor"
                    and retained > 0 and retained <= whites)
        familyquote = None
        familysteps = standardsteps
        familylabel = "standard"
        if eligible:
            familyquote = standardquote
            if target["family"] == "seven_pairs":
                familylabel = "seven_pairs"
                if sevenquote is not None:
                    familyquote = sevenquote
                    familysteps = sevensteps
                else:
                    familyquote = None
            if familyquote is not None:
                need = target["natural_need"]
                terminal = 1 if target["requires_terminal_draw"] else 0
                bound = float(need + terminal)
                targetsummary = summaryof(target["conditional_need_improvement_codes"],
                                          codeindex, stock)
                if need <= 0:
                    activation = 1.0
                elif targetsummary[1] > 0 and targetsummary[2] > 0:
                    activation = float(targetsummary[2]) / (ACTREF + float(targetsummary[2]))
                else:
                    activation = 0.0
                prior = (PURPOSES[retained] * dealerboost * scale
                         * horizon(bound, room) * activation)
                steps = max(familysteps, bound)
                extra = max(0.0, steps - familysteps)
                quote = (familyquote + prior - EXTRAPATH * extra
                         - WHITEHOLD * float(retained - 1)
                         - (ladder(steps) - ladder(familysteps)))
                routes.append((quote, steps, target["conditional_need_improvement_codes"],
                               "purpose:" + familylabel,
                               (extra, retained, need, bound, index, activation)))
    plaincore = routes[0][0]
    for position in range(plainroutes):
        if routes[position][0] > plaincore:
            plaincore = routes[position][0]
    core = routes[0][0]
    winner = 0
    for position in range(len(routes)):
        if routes[position][0] > core:
            core = routes[position][0]
            winner = position
    occupied = set()
    for code in routes[winner][2]:
        occupied.add(code)
    if waiting["legal_hu_draw_codes"] is not None:
        for code in waiting["legal_hu_draw_codes"]:
            occupied.add(code)
    dividend = 0.0
    for position in range(len(routes)):
        if position != winner:
            route = routes[position]
            gapvalue = core - route[0]
            if gapvalue < 0.0:
                gapvalue = 0.0
            exclusive = 0
            for code in route[2]:
                if code not in occupied:
                    cell = stock[codeindex[code]]
                    if cell[0] > 0.0:
                        exclusive += 1
            if exclusive > 0:
                closeness = 1.0 / (1.0 + DIVCLOSE * gapvalue)
                distgap = route[1] - routes[winner][1]
                if distgap < 0.0:
                    distgap = 0.0
                maturity = 1.0 / (1.0 + DIVGAP * distgap)
                dividend += (DIVCAP * float(exclusive) / (DIVREF + float(exclusive))
                             * closeness * maturity * scale)
    if dividend > DIVTOTAL:
        dividend = DIVTOTAL
    joint = core + dividend
    option = None
    for position in range(plainroutes, len(routes)):
        detail = routes[position][4]
        if detail is not None:
            gain = routes[position][0] - plaincore
            if gain > 0.0 and (option is None or gain > option[0]):
                option = (gain, detail[0], detail[1], detail[2], detail[3], detail[4])
    known = payment[2]
    unknown = len(waiting["qualification_unknown_codes"])
    if payment[0] == 0:
        qualcost = QUALUNANALYSED
    else:
        qualcost = QUALUNKNOWN * float(unknown) / float(1 + known + unknown)
    if anchor is not None:
        ready = huoffer(anchor, discount, risk, payment, option, plaincore)
        value = HUBASE + anchor + ready[0] - qualcost - unknowncost
    else:
        ready = None
        value = WAITBASE + joint - qualcost - unknowncost - UNANCHOREXPOSURE * risk
    prepstats = (prepneed, prepdiscard, prepwidth, readiness)
    facts = (value, joint, plaincore, core, dividend, routes[winner][3], payment,
             option, qualcost, ready, prepstats)
    return value, facts


def score_actions(view):
    """对冻结后序共享图一次计算；每个合法根恰一条有限评分与有界解释。

    choices在全部合法续行中择优；condition与replacement消费全部互斥边
    的下端加有界均值差，不挑最好补牌；未知补牌读真实前态并折价。无
    文件、网络、时钟、随机或跨调用缓存；不筛掉任何合法根。
    """
    if (view.get("schema_version") != "vip-route-scoring-view/3"
            or view.get("graph_schema_version") != "vip-route-action-graph/3"):
        return {"status": "ABSTAIN", "reason": "unsupported_view"}
    context = view["visible_state"]
    seat = context["seat"]
    base = float(view["binding"]["base_score"])
    wall = context["remaining_tile_count"]
    dealerboost = DEALERBOOST if seat == context["dealer_seat"] else 1.0
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
            point = paypoints(float(node["settlement"]["score_delta"][seat]) / base)
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
            if node["waiting"] is None:
                return {"status": "ABSTAIN", "reason": "missing_waiting"}
            unknowncost = UNKNOWNDRAW if kind == "unknown_draw" else 0.0
            value, facts = routewait(node["waiting"], codeindex, seat, base, room, drawscale,
                                     pressure, discount, risk, anchor, unknowncost, dealerboost)
        elif kind == "hu":
            value = HUBASE + paypoints(float(node["settlement"]["score_delta"][seat]) / base)
            facts = None
        elif kind == "choices":
            if not children:
                return {"status": "ABSTAIN", "reason": "empty_choices"}
            selected = indexes[children[0]]
            for child in children:
                candidate = indexes[child]
                if values[candidate] > values[selected]:
                    selected = candidate
            value = values[selected]
            facts = factslist[selected]
        elif kind == "replacement" or kind == "condition":
            if not children:
                return {"status": "ABSTAIN", "reason": "empty_condition"}
            lower = values[indexes[children[0]]]
            total = 0.0
            for child in children:
                childvalue = values[indexes[child]]
                if childvalue < lower:
                    lower = childvalue
                total += childvalue
            mean = total / float(len(children))
            blend = REPLACEMENTBLEND if kind == "replacement" else CONDITIONBLEND
            cap = REPLACEMENTCAP if kind == "replacement" else CONDITIONCAP
            value = lower + min(cap, blend * max(0.0, mean - lower))
            facts = None
        else:
            return {"status": "ABSTAIN", "reason": "unknown_node_kind"}
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
            pairs.append(("frontier", (round(facts[1], 3), round(facts[2], 3),
                                       round(facts[3], 3), round(facts[4], 3), facts[5])))
            payment = facts[6]
            if payment[1] is None:
                average = None
            else:
                average = round(payment[1], 3)
            pairs.append(("pay", (payment[0], average, payment[2], round(payment[3], 3))))
            pairs.append(("target", None if facts[7] is None else
                          (round(facts[7][0], 3), round(facts[7][1], 3), facts[7][2],
                           facts[7][3], round(facts[7][4], 3))))
            pairs.append(("prep", (facts[10][0], facts[10][1], facts[10][2],
                                   round(facts[10][3], 3))))
            offer = facts[9]
            pairs.append(("offer", None if offer is None else
                          (round(offer[0], 3), offer[1], round(offer[4], 3),
                           round(offer[5], 3))))
            pairs.append(("qualification_cost", round(facts[8], 3)))
        if not entries:
            pairs.append(("unit", "heuristic_rank_points"))
            pairs.append(("formula", "vip_ladder_frontier_exclusive_dividend_e1/1"))
            if anchor is None:
                anchorvalue = None
            else:
                anchorvalue = round(anchor, 3)
            pairs.append(("context", (wall, opponents, round(dealerboost, 3),
                                      round(discount, 3), round(risk, 3), anchorvalue)))
            pairs.append(("unknown", "opponent_hu_and_future_draw_reachability"))
            pairs.append(("scope", "conditional_facts_not_probability_or_guaranteed_highfan"))
        entries.append({"action_key": action["action_key"], "score": value,
                        "trace": dict(pairs)})
    return {"status": "SCORED", "entries": entries}