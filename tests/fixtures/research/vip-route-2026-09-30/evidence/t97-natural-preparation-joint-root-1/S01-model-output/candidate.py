"""冻结视图/3的i1联合完成成本公式；历史T75仅作图处理与支付处理参考。"""

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
RETENTION = 20
WALLSOFT = 8.0
UNKNOWNWALLSCALE = 0.70
OPPDECAY = 0.05
RISKBASE = 1.8
OPPRISK = 0.12
LATERISK = 3.4
UNKNOWNWALLRISK = 0.7
COMPLETIONLINEAR = 0.75
COMPLETIONSQUARE = 0.35
WHITEDROPCOST = 0.25
RESCUEDECAY = 0.30
STAGEPRICE = 1.0
EXITFLOOR = 0.40
EXITMASSREF = 6.0
EXITWIDTHREF = 3.0
EXITSTEPDECAY = 0.25
TARGETMASSREF = 2.0
PORTCAP = 2.2
PORTREF = 12.0
OPTIONREF = 2.0
ENVELOPEBLEND = 0.25
SINGLESCOPE = 0.75
COVREF = 3.0
LOCALCAP = 6.0
LOCALREF = 8.0
KNOWNPAYLINEAR = 0.45
PAYMASSREF = 8.0
QUALUNKNOWN = 0.7
QUALUNANALYSED = 1.0
UNKNOWNDRAW = 2.5
ANCHREADY = 0.18
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
NETWAITFLOOR = 0.35
NETANCHORPRICE = 0.30
NETCARRY = 0.25
NETDISTANCE = 0.75


def pay_points(amount):
    """本家净积分除基础分后转有界排序点；不是未来积分估计。"""
    return PAYCAP * amount / (PAYREF + abs(amount))


def inventory_support(slot, waiting):
    """返回排序库存、精确张数和非精确标记；容量包含他家暗牌。

    精确零关闭本码；保守正下界支持排序，保守零与未知保留软支持。
    软支持不写回资格或支付，不除墙余当摸牌概率。
    """
    capacity = waiting["unseen_capacities"][slot]
    evidence = waiting["unseen_evidence"][slot]
    if evidence == "exact" and capacity is not None:
        return float(capacity), capacity, 0
    if evidence == "conservative" and capacity is not None and capacity > 0:
        return float(capacity), 0, 1
    return UNSEENSOFT, 0, 1


def route_support(codes, waiting, codeindex, drawscale):
    """按规范牌码去重进张，分别记录排序支持、库存、码数与未知。"""
    mass = 0.0
    exact = 0
    width = 0
    uncertain = 0
    seen = set()
    for code in codes:
        if code not in seen:
            seen.add(code)
            inventory, precise, unknown = inventory_support(codeindex[code], waiting)
            if inventory > 0.0:
                mass += inventory
                exact += precise
                width += 1
                uncertain += unknown
    credit = drawscale * SPEEDCAP * mass / (SPEEDREF + mass) * float(width) / (VARREF + float(width))
    return credit, mass, width, exact, uncertain


def purpose_scale(length, room, drawscale, pressure):
    """墙余和公开副露折减条件先验；length不是保证的本人摸牌次数。"""
    excess = 0.0 if room is None else max(0.0, float(length) - room)
    return drawscale * pressure / (1.0 + HORIZONCOST * excess)


def preparation_value(waiting):
    """自然面子准备（NaturalSetPreparationFacts，不借白、不含将的缺张事实）。

    返回缺张、自然弃牌下界、相容改善码数、实持白和成熟度诊断。
    最后一项是0—1的排序折减系数，绝不独立加入动作分或授予胡资格。
    只供普通型释放实持白时定价；七对使用自身目标，不借普通面子事实。
    """
    preparation = waiting["natural_preparation"]
    need = preparation["natural_draw_lower_bound"]
    discard = preparation["natural_discard_lower_bound"]
    width = waiting["natural_preparation_code_width"]
    whites = preparation["whites_held"]
    burden = float(max(need, discard))
    readiness = 1.0 / (1.0 + COMPLETIONLINEAR * burden + COMPLETIONSQUARE * burden * burden)
    if need > 0 and width == 0:
        readiness = 0.0
    return need, discard, width, whites, readiness


def actual_route(shanten, support, structural):
    """真实向听与普通出口的排序底座；L不是保证还需摸几次。

    返回真实向听、L、支持点、库存代理、相容码数、非精确码数、路线值。
    structural仅保留七对已有的有界自然对子先验，不加入独立自然面子奖励。
    """
    length = max(0, shanten) + 1
    value = support[0] - FORMCOST * float(length - 1) + structural
    return shanten, length, support[0], support[1], support[2], support[4], value


def payment_summary(waiting, seat, base):
    """条件胡支付（RouteConditionalHuPayment，给定下一本人普通摸牌立即胡的支付）。

    同码两抓打假设互斥，先合成下端加有界价差；单包络单独折减。
    容量只在已见证码内生成排序摘要，不是墙内概率或途中存活率。
    返回状态、支付点摘要、码数、精确容量、最小/最大点、单包络码数、
    最小见证番数、逐码摘要；末项每码为容量、支付点和包络行数。
    状态0未分析、1已知空、2有支付、3部分未知，未知码不当作零支付。
    """
    payments = waiting["normal_draw_hu_payments"]
    if payments is None:
        return 0, None, 0, 0.0, None, None, 0, None, ()
    partial = len(waiting["qualification_unknown_codes"]) > 0
    if not payments:
        return 3 if partial else 1, 0.0, 0, 0.0, None, None, 0, None, ()
    groups = []
    currentcode = None
    lower = 0.0
    upper = 0.0
    capacity = 0.0
    rows = 0
    minimumfan = None
    minimum = None
    maximum = None
    for payment in payments:
        amount = float(payment["settlement"]["score_delta"][seat]) / base
        point = pay_points(amount)
        fan = payment["settlement"]["fan"]
        minimum = point if minimum is None else min(minimum, point)
        maximum = point if maximum is None else max(maximum, point)
        minimumfan = fan if minimumfan is None else min(minimumfan, fan)
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
            lower = min(lower, point)
            upper = max(upper, point)
            rows += 1
    groups.append((capacity, lower, upper, rows))
    total = 0.0
    mass = 0.0
    singles = 0
    offers = []
    for capacity, lower, upper, rows in groups:
        if rows == 1:
            envelope = SINGLESCOPE * lower
            singles += 1
        else:
            envelope = lower + ENVELOPEBLEND * (upper - lower)
        total += capacity * envelope
        mass += capacity
        offers.append((capacity, envelope, rows))
    return (3 if partial else 2, total / mass, len(groups), mass, minimum, maximum,
            singles, minimumfan, tuple(offers))


def known_payment_credit(payment, coverage, drawscale, pressure):
    """同源支付转信用，保留较大支付差别；None和空表不填虚构积分。

    返回饱和信用、容量折减的线性信用及实际信用，单位均为排序点。
    两种变换择大，不相加；后续用途目标只能竞争这一共同信用槽。
    """
    point = payment[1]
    if point is None or point <= 0.0:
        return 0.0, 0.0, 0.0
    scale = coverage * drawscale * pressure
    saturated = LOCALCAP * point / (LOCALREF + point) * scale
    mass = payment[3]
    inventory = mass / (PAYMASSREF + mass)
    linear = KNOWNPAYLINEAR * point * inventory * scale
    return saturated, linear, max(saturated, linear)


def joint_routes(waiting, standard, seven, preparation, paymentcredit, codeindex,
                 room, drawscale, pressure):
    """联合完成成本：已有出口、实持白用途和同目标完成负担共用一个价值槽。

    每个目标先回收一部分普通支付信用，再用完成成熟度融资用途先验，
    最后扣该目标相对真实出口额外延后兑现的代价；与直接信用择大。
    普通型按保留白占实持白的比例消费自然准备负担；这是排序定价，
    不是增加规则必需动作，也不把所有白预先绑定具体自然孤张。
    七对只消费自身自然补弃目标。用途先验不是尚未发生的官方结算。
    组合只记普通基线与已见证胡码之外的新码，同码取最大并归一每路线预算。
    返回最佳目标、去重增量组合和相对普通基线的最佳有限净信用见证。
    """
    stock = tuple([inventory_support(slot, waiting) for slot in range(len(waiting["unseen_capacities"]))])
    main = standard
    basecodes = waiting["standard_useful_codes"]
    if seven is not None and seven[6] > main[6]:
        main = seven
        basecodes = waiting["seven_pairs_useful_codes"]
    baseline = set(basecodes)
    knownhu = waiting["legal_hu_draw_codes"]
    if knownhu is not None:
        for code in knownhu:
            baseline.add(code)
    local = paymentcredit[2]
    ordinary = main[6] + local
    plans = []
    # 普通/七对转换各先分摊一个预算，避免缺口较大的路线因改善码更多而免费加点。
    branches = [(standard, waiting["standard_useful_codes"])]
    if seven is not None:
        branches.append((seven, waiting["seven_pairs_useful_codes"]))
    for route, codes in branches:
        steps = float(route[1] - 1)
        weight = 1.0 / ((1.0 + steps * steps) * float(max(1, len(codes))))
        for code in codes:
            if code not in baseline:
                plans.append((codeindex[code], weight))
    best = None
    option = None
    whites = waiting["structure"]["whites_held"]
    for index, target in enumerate(waiting["structure"]["targets"]):
        route = standard if target["family"] == "standard" else seven
        terminal = 1 if target["requires_terminal_draw"] else 0
        need = target["natural_need"]
        naturaldrop = target["target_natural_discard_lower_bound"]
        whitedrop = target["target_white_discard_lower_bound"]
        retained = target["retained_whites"]
        scale = max(route[1], need + terminal, naturaldrop + whitedrop)
        width = waiting["target_improvement_code_widths"][index]
        predecessor = target["target_stage"] == "waiting_predecessor"
        targetmass = 0.0
        for code in target["conditional_need_improvement_codes"]:
            targetmass += stock[codeindex[code]][0]
        targetgate = 1.0
        if need > 0:
            targetgate = 0.0
            if width > 0 and targetmass > 0.0:
                targetgate = 0.50 + 0.50 * targetmass / (TARGETMASSREF + targetmass)
        effort = float(max(0, scale - 1))
        if predecessor and target["family"] == "standard" and retained > 0:
            release = float(retained) / float(max(1, whites))
            naturalburden = release * float(max(preparation[0], preparation[1]))
            effort = max(effort, naturalburden)
            # 正缺口精确无相容推进时不能把完成准备当作免费的用途信用。
            if preparation[0] > 0 and preparation[2] == 0:
                targetgate = 0.0
        earned = 1.0 / (1.0 + COMPLETIONLINEAR * effort + COMPLETIONSQUARE * effort * effort
                        + WHITEDROPCOST * float(whitedrop))
        rescue = 1.0 / (1.0 + RESCUEDECAY * effort)
        exitmass = max(0.0, route[3])
        exitwidth = float(route[4])
        exitgate = exitmass / (EXITMASSREF + exitmass) * exitwidth / (EXITWIDTHREF + exitwidth)
        exitgate /= 1.0 + EXITSTEPDECAY * float(route[1] - 1)
        prior = PURPOSES[retained] if predecessor else 0.0
        exitfactor = EXITFLOOR + (1.0 - EXITFLOOR) * exitgate
        purposecredit = prior * purpose_scale(scale, room, drawscale, pressure) * targetgate * earned * exitfactor
        rescued = local * rescue
        stagecost = STAGEPRICE * float(max(0, scale - route[1])) * (1.0 - rescue)
        prospective = rescued + purposecredit - stagecost
        # 目标总信用包含一次已有支付的回收份额；不再在它外面叠加同份支付。
        value = route[6] + prospective
        if best is None or value > best[10]:
            best = (index, target["family"], retained, need, terminal, scale,
                    naturaldrop, whitedrop, width, prospective, value)
        gain = max(0.0, value - ordinary)
        if predecessor and retained > 0 and retained <= whites and gain > 0.0:
            if option is None or gain > option[8]:
                option = (index, target["family"], retained, need, scale, width, prior,
                          exitgate, gain, targetmass, targetgate, effort, earned,
                          rescue, rescued, purposecredit, stagecost, prospective)
        # 仅有已付完成成本后仍优于基线的目标获得组合预算；码多会摊薄单码权重。
        weight = gain / (OPTIONREF + gain) * earned / float(max(1, width))
        if weight > 0.0:
            for code in target["conditional_need_improvement_codes"]:
                if code not in baseline:
                    plans.append((codeindex[code], weight))
    combined = []
    currentslot = None
    peak = 0.0
    for slot, weight in sorted(plans):
        if slot != currentslot:
            if currentslot is not None:
                combined.append((currentslot, peak))
            currentslot = slot
            peak = weight
        else:
            peak = max(peak, weight)
    if currentslot is not None:
        combined.append((currentslot, peak))
    mass = 0.0
    diversity = 0.0
    exact = 0
    codecount = 0
    uncertain = 0
    for slot, weight in combined:
        inventory, precise, unknown = stock[slot]
        if inventory > 0.0:
            mass += weight * inventory
            diversity += weight
            exact += precise
            codecount += 1
            uncertain += unknown
    credit = drawscale * pressure * PORTCAP * mass / (PORTREF + mass) * diversity / (VARREF + diversity)
    return best, (mass, diversity, exact, codecount, uncertain, credit), option


def net_hu_offer(anchor, discount, risk, payment, main, portfolio, option):
    """净弃胡取舍（NetHuOffer，逐码净支付差与已付完成成本的目标增量比较）。

    普通低支付只保全它支持的当前价值，不放大升级码宽；同码包络只记一次。
    远目标只消费相对直接普通基线的增量，不再把其中回收的支付当升级。
    直接升级与远增量择大，再共同扣确定胡的机会成本和等待费用。
    返回净点、信用来源、升级点、下降点、保听支持、升级码数及容量、
    升级支持、承接点、机会成本、等待费、退步费、远净信用、远弃胡价、
    远出口费及共用信用槽点；所有分值是排序点而非概率或保证积分。
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
    for capacity, point, rows in payment[8]:
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
    offer = direct
    channel = "conditional_net_upgrade"
    if option is not None:
        remoteprice = anchor * (ANCHOROPTIONBASE + ANCHOROPTIONSTEP * option[11])
        if payment[1] is None:
            fallback = ANCHORUNKNOWNCOST * anchor
        else:
            fallback = ANCHORFALLBACKCOST * max(0.0, anchor - max(0.0, payment[1]))
        remote = discount * option[8] - remoteprice - fallback
        if remote > offer:
            offer = remote
            channel = "completion_budget_gain"
    ordinarycore = max(0.0, main[6] + portfolio[5])
    carry = NETCARRY * discount * maintained * ordinarycore
    opportunity = NETANCHORPRICE * anchor * (1.0 - discount * maintained)
    waitfee = risk * (NETWAITFLOOR + (1.0 - NETWAITFLOOR) * (1.0 - maintained))
    distancefee = ANCHREADY * max(0.0, -main[6])
    net = offer + carry - opportunity - waitfee - distancefee
    return (net, channel, upgrade, downside, maintained, upgradewidth, upgrademass,
            upgradesupport, carry, opportunity, waitfee, distancefee, remote,
            remoteprice, fallback, offer)


def wait_value(waiting, codeindex, seat, base, room, drawscale, pressure, discount, risk,
               anchor, unknowncost):
    """用同一联合完成成本评价普通出口、白用途、已见证支付和当前胡。

    普通型不用独立准备奖励，七对保留有界实体对子先验；双方目标完整评价。
    直接支付与融资后的目标总信用择大，组合只记未重复的新推进。
    空表、未分析及部分未知保留各自状态；不虚构合法胡或筛掉合法根。
    """
    structure = waiting["structure"]
    preparation = preparation_value(waiting)
    standard = actual_route(structure["standard_shanten"],
                            route_support(waiting["standard_useful_codes"], waiting, codeindex, drawscale),
                            0.0)
    seven = None
    main = standard
    family = "standard"
    if structure["seven_pairs_shanten"] is not None:
        length = max(0, structure["seven_pairs_shanten"]) + 1
        # 自然四张按已有对子事实计先验，不自行授予豪华七对资格。
        pairprior = 0.30 * float(min(2, max(0, structure["natural_pair_count"] - 4))) / float(length)
        seven = actual_route(structure["seven_pairs_shanten"],
                             route_support(waiting["seven_pairs_useful_codes"], waiting, codeindex, drawscale),
                             pairprior * drawscale * pressure)
        if seven[6] > main[6]:
            main = seven
            family = "seven_pairs"
    payment = payment_summary(waiting, seat, base)
    known = payment[2]
    unknown = len(waiting["qualification_unknown_codes"])
    coverage = float(known) / (COVREF + float(known))
    qualcost = QUALUNANALYSED if payment[0] == 0 else QUALUNKNOWN * float(unknown) / float(1 + known + unknown)
    paymentcredit = known_payment_credit(payment, coverage, drawscale, pressure)
    local = paymentcredit[2]
    ordinary = main[6] + local
    natural, portfolio, option = joint_routes(waiting, standard, seven, preparation, paymentcredit,
                                             codeindex, room, drawscale, pressure)
    joint = ordinary
    chosen = family
    if natural is not None and natural[10] > joint:
        joint = natural[10]
        chosen = "completion_budget_target"
    basejoint = joint
    joint += portfolio[5]
    gain = 0.0
    bias = 0.0
    ready = None
    optionnet = 0.0
    anchorprice = 0.0
    fallbackcost = 0.0
    if anchor is not None:
        ready = net_hu_offer(anchor, discount, risk, payment, main, portfolio, option)
        gain = ready[2]
        bias = ready[15]
        optionnet = ready[12]
        anchorprice = ready[13]
        fallbackcost = ready[14]
        value = HUBASE + anchor + ready[0] - qualcost - unknowncost
    else:
        value = WAITBASE + joint - qualcost - unknowncost - UNANCHOREXPOSURE * risk
    # 与历史骨架共用诊断布局；18为加新码组合前的联合值，19为直接支付信用。
    facts = (standard, seven, natural, preparation, portfolio, payment,
             ordinary, joint, chosen, gain, bias, local, qualcost, ready,
             option, optionnet, anchorprice, fallbackcost, basejoint, paymentcredit)
    return value, facts


def score_actions(view):
    """对全部冻结后序节点评价并完整返回每个合法根的一条有限评分。

    choices才择优合法续行；杠补和互斥条件消费全部边的下端与有界均值价差。
    共享节点只计算一次，父摘要保留有序边及重复引用；不挑最好未来牌。
    机械缺口显式弃权；无文件、网络、时钟、随机或跨调用状态。
    """
    context = view["visible_state"]
    seat = context["seat"]
    base = float(view["binding"]["base_score"])
    wall = context["remaining_tile_count"]
    opponents = sum([len(melds) for otherseat, melds in enumerate(context["melds"]) if otherseat != seat])
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
            point = pay_points(amount)
            if anchor is None or point > anchor:
                anchor = point
    values = []
    references = []
    factslist = []
    aggregates = []
    for index, node in enumerate(nodes):
        if node["gap_kind"] is not None:
            return {"status": "ABSTAIN", "reason": "graph_gap"}
        kind = node["kind"]
        children = node["children"]
        if kind == "wait" or kind == "unknown_draw":
            unknowncost = UNKNOWNDRAW if kind == "unknown_draw" else 0.0
            value, facts = wait_value(node["waiting"], codeindex, seat, base, room, drawscale,
                                      pressure, discount, risk, anchor, unknowncost)
            reference = index
            aggregate = (kind, round(value, 3))
        elif kind == "hu":
            amount = float(node["settlement"]["score_delta"][seat]) / base
            value = HUBASE + pay_points(amount)
            facts = None
            reference = index
            aggregate = ("hu", amount)
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
            reference = references[bestindex]
            facts = factslist[bestindex]
            aggregate = (kind, len(children), bestindex)
        else:
            if not children:
                return {"status": "ABSTAIN", "reason": "empty_condition"}
            lowerindex = indexes[children[0]]
            lower = values[lowerindex]
            upper = lower
            total = 0.0
            for child in children:
                childindex = indexes[child]
                childvalue = values[childindex]
                total += childvalue
                if childvalue < lower:
                    lowerindex = childindex
                    lower = childvalue
                upper = max(upper, childvalue)
            mean = total / float(len(children))
            # 这是互斥条件的排序摘要，不是均匀摸牌假设或期望积分。
            blend = REPLACEMENTBLEND if kind == "replacement" else CONDITIONBLEND
            cap = REPLACEMENTCAP if kind == "replacement" else CONDITIONCAP
            value = lower + min(cap, blend * max(0.0, mean - lower))
            reference = references[lowerindex]
            facts = factslist[lowerindex]
            aggregate = (kind, len(children), round(lower, 3), round(upper, 3), round(mean, 3))
        values.append(value)
        references.append(reference)
        factslist.append(facts)
        aggregates.append(aggregate)
    entries = []
    actioncount = len(view["actions"])
    for action in view["actions"]:
        index = indexes[action["node_key"]]
        kind = action["action_type"]
        adjustment = 0.0
        if kind == "chi" or kind == "peng":
            # 跳座价值仅为获裁决条件下先验；七对关闭和目标改变已在续行体现。
            adjustment = SKIPVALUE * float(action["skipped_seats"]) * drawscale - CLAIMCOST
        elif kind == "gang":
            adjustment = -GANGCOST
        value = float(values[index] + adjustment)
        facts = factslist[index]
        trace = {}
        if actioncount <= 64:
            trace = {"ref": references[index], "agg": aggregates[index],
                     "condition": action["pending_condition"], "adjust": round(adjustment, 3)}
        if facts is not None and actioncount <= 16:
            standard = facts[0]
            seven = facts[1]
            natural = facts[2]
            preparation = facts[3]
            portfolio = facts[4]
            payment = facts[5]
            option = facts[14]
            trace = dict(list(trace.items()) + [
                ("std", tuple([round(part, 3) for part in standard])),
                ("seven", None if seven is None else tuple([round(part, 3) for part in seven])),
                ("natural", None if natural is None else
                 (natural[0], natural[1], natural[2], natural[3], natural[4], natural[5],
                  natural[6], natural[7], natural[8], round(natural[9], 3), round(natural[10], 3))),
                ("prep", (preparation[0], preparation[1], preparation[2], preparation[3], round(preparation[4], 3))),
                ("portfolio", tuple([round(part, 3) for part in portfolio])),
                ("pay", (payment[0], None if payment[1] is None else round(payment[1], 3),
                         payment[2], payment[3], payment[4], payment[5], payment[6], payment[7])),
                ("joint", (round(facts[6], 3), round(facts[7], 3), facts[8],
                           round(facts[9], 3), round(facts[10], 3), round(facts[11], 3), round(facts[12], 3))),
                ("option", None if option is None else
                 (option[0], option[1], option[2], option[3], option[4], option[5],
                  round(option[6], 3), round(option[7], 3), round(option[8], 3),
                  round(option[9], 3), round(option[10], 3), round(option[11], 3), round(option[12], 3))),
                ("completion", None if option is None else
                 tuple([round(part, 3) for part in option[13:18]])),
                ("pay_credit", tuple([round(part, 3) for part in facts[19]])),
                ("offer_cost", (round(facts[15], 3), round(facts[16], 3),
                                round(facts[17], 3), round(facts[18], 3))),
                ("net_offer", None if facts[13] is None else
                 (round(facts[13][0], 3), facts[13][1], round(facts[13][2], 3), round(facts[13][3], 3),
                  round(facts[13][4], 3), facts[13][5], facts[13][6], round(facts[13][7], 3),
                  round(facts[13][8], 3), round(facts[13][9], 3), round(facts[13][10], 3),
                  round(facts[13][11], 3), round(facts[13][12], 3), round(facts[13][13], 3),
                  round(facts[13][14], 3), round(facts[13][15], 3))),
            ])
        elif facts is not None and actioncount <= 40:
            trace = dict(list(trace.items()) + [
                ("prep", (facts[3][0], facts[3][2], round(facts[3][4], 3))),
                ("joint", (round(facts[6], 3), round(facts[7], 3), facts[8])),
                ("pay", (facts[5][0], facts[5][2], facts[5][6])),
                ("pay_credit", round(facts[19][2], 3)),
                ("net_offer", None if facts[13] is None else
                 (round(facts[13][0], 3), facts[13][1], round(facts[13][4], 3), facts[13][5],
                  round(facts[13][9], 3), round(facts[13][10], 3))),
                ("option", None if facts[14] is None else
                 (facts[14][2], facts[14][4], round(facts[14][8], 3), round(facts[15], 3))),
            ])
        if not entries:
            trace = dict(list(trace.items()) + [
                ("unit", "heuristic_rank_points"),
                ("formula", "vip_joint_completion_budget_i1/1"),
                ("context", (wall, opponents, round(discount, 3), round(risk, 3), anchor)),
                ("unknown", "opponent_hu_and_future_draw_reachability"),
                ("scope", "conditional_facts_not_probability_or_guaranteed_highfan"),
            ])
        entries.append({"action_key": action["action_key"], "score": value, "trace": trace})
    return {"status": "SCORED", "entries": entries}