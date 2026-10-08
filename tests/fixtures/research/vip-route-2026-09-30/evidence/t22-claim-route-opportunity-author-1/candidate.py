"""联合排名只使用冻结 View/2；评分点不是概率、番数或未来积分。"""

PAYCAP = 48.0
PAYREF = 192.0
HUBASE = 10.0
WAITBASE = 12.0
FORMCOST = 3.4
SPEEDCAP = 4.5
SPEEDREF = 14.0
VARREF = 4.0
UNSEENSOFT = 0.8
SHAPEGAIN = 0.5
WIDTHCAP = 3.5
WIDTHREF = 5.0
PURPOSES = (0.0, 3.4, 7.4, 11.5, 15.7)
DEADPURPOSE = 0.25
HORIZONCOST = 0.30
RETENTION = 20
WALLSOFT = 8.0
UNKNOWNWALLSCALE = 0.75
OPPDECAY = 0.055
RISKBASE = 1.9
OPPRISK = 0.13
LATERISK = 3.2
UNKNOWNWALLRISK = 0.6
ENVELOPEBLEND = 0.35
SINGLESCOPE = 0.75
COVREF = 3.0
LOCALCAP = 6.0
LOCALREF = 8.0
QUALUNKNOWN = 0.8
QUALUNANALYSED = 0.9
UNKNOWNDRAW = 2.6
SMALLREADY = 0.45
NATURALBIASCAP = 1.1
GAINREF = 4.0
ANCHREADY = 0.20
UNANCHOREXPOSURE = 0.15
CONDITIONBLEND = 0.18
CONDITIONCAP = 1.0
REPLACEMENTBLEND = 0.35
REPLACEMENTCAP = 2.0
CLAIMCOST = 0.25
SKIPVALUE = 0.10
GANGCOST = 0.15
# 新常数只约束公开交互项；单位为排序点和无量纲特征权重，尚未评测。
PUBLICHELP_CAP = 0.75
PUBLICNEAR_GAIN = 0.10
# 新项仅用于当前胡的已见证保持听牌取舍；均是待验证排序常数。
READYGAIN_CAP = 4.5
READYWAIT_FEE = 0.25
READYSUPPORT_REF = 1.0
# 根吃碰的额外路线机会费封顶，单位排序点；不改变原鸣牌费或跳座点。
CLAIMOPTION_CAP = 0.75


def pay_points(amount):
    """本家净积分除基础分后转排序点；晚饱和保留高支付差，非未来积分估计。"""
    return PAYCAP * amount / (PAYREF + abs(amount))


def route_support(codes, waiting, codeindex, drawscale, shaped, lowerenabled):
    """相容码支持（RouteSupport，只用于排序的进张支持）按码保留证据身份。

    返回向量为新支持点、精确公开张数、相容码数、非精确码数、形状增量、
    保守下界补足量、原父支持点；补足量是支持权重，不是新增精确实体。
    lowerenabled 为调用方给定的全图及等待叶护栏，关闭时沿父代原算式。
    开启时按输入顺序去重，仅对 conservative 正下界补足超过0.8代理的部分。
    conservative 零、unknown 和 None 保留原代理及非精确身份，不排除牌码。
    公开未见张数包含他家暗牌，不是墙内张数、摸牌概率或未来可达性。
    形状仍只作用于精确容量，不把保守下界赋予顺子模板或合法胡资格。
    """
    capacities = waiting["unseen_capacities"]
    evidence = waiting["unseen_evidence"]
    counts = waiting["structure"]["natural_counts33"]
    exact = 0
    variety = 0
    uncertain = 0
    excess = 0.0
    lowerextra = 0.0
    supportcodes = codes
    if lowerenabled:
        # 激活分支显式去重；关闭分支保持父代对规范去重事实的原计算。
        supportcodes = []
        seen = set()
        for code in codes:
            if code not in seen:
                supportcodes.append(code)
                seen.add(code)
    for code in supportcodes:
        slot = codeindex[code]
        cap = capacities[slot]
        if evidence[slot] == "exact" and cap is not None:
            if cap > 0:
                exact += cap
                variety += 1
                if shaped and slot < 27 and counts[slot] == 0:
                    pos = slot % 9
                    templates = 0
                    if pos >= 2 and counts[slot - 2] > 0 and counts[slot - 1] > 0:
                        templates += 1
                    if pos >= 1 and pos <= 7 and counts[slot - 1] > 0 and counts[slot + 1] > 0:
                        templates += 1
                    if pos <= 6 and counts[slot + 1] > 0 and counts[slot + 2] > 0:
                        templates += 1
                    excess += SHAPEGAIN * float(cap) * float(min(templates, 2)) / 2.0
        else:
            variety += 1
            uncertain += 1
            if lowerenabled and evidence[slot] == "conservative" and cap is not None and cap > 0:
                # 只补足已有下界，仍计入非精确码；零和 None 不代表不存在。
                lowerextra += max(0.0, float(cap) - UNSEENSOFT)
    inventory = float(exact) + UNSEENSOFT * float(uncertain)
    weighted = inventory + excess
    diversity = float(variety) / (VARREF + float(variety))
    credit = drawscale * SPEEDCAP * weighted / (SPEEDREF + weighted) * diversity
    plain = drawscale * SPEEDCAP * inventory / (SPEEDREF + inventory) * diversity
    parentsupport = credit
    if lowerenabled and lowerextra > 0.0:
        # 同一饱和式接纳下界补足；原0.8代理已计入，不能再叠加整个cap。
        inventory = inventory + lowerextra
        weighted = inventory + excess
        credit = drawscale * SPEEDCAP * weighted / (SPEEDREF + weighted) * diversity
        plain = drawscale * SPEEDCAP * inventory / (SPEEDREF + inventory) * diversity
    return credit, exact, variety, uncertain, credit - plain, lowerextra, parentsupport


def actual_route(shanten, support, costs):
    """真实向听不改；L=max(0,向听)+1 只是共同成型排序尺度。

    返回向量：原向听、L、精确公开张数、相容码数、非精确码数、
    支持点、形状增量、普通路线值、保守下界补足量、原父支持点。
    后两项只供说明，不回灌其他费用或目标。L 不保证本人还能摸这么多次。
    """
    length = max(0, shanten) + 1
    value = support[0] - costs[length]
    return shanten, length, support[1], support[2], support[3], support[0], support[4], value, support[5], support[6]


def natural_offer(waiting, standard, seven, costs, widths, purposes):
    """全部固定自然目标各有完整基值，再择优；同库存用途不相加。

    自然牌缺口 D 保留在 r=max(L,D+t,自然弃下界+白弃下界)，t 为必需终末摸。
    补与弃可在本人一次行动中衔接，所以使用共同尺度，不把同一 D 再扣一次。
    前驱的递增保白先验只是排序点，既非已确认番数，也不把保 k 白解释为
    已完成 k 次飘白；公开压力与墙余只能折减先验，不能创造规则见证。
    返回最佳目标向量：目标号、家族、阶段、k、D、t、r、自然弃下界、
    白弃下界、相容推进码宽度、用途先验、成型成本、支持点、目标值。
    """
    best = None
    for index, target in enumerate(waiting["structure"]["targets"]):
        family = target["family"]
        length = standard[1] if family == "standard" else seven[1]
        need = target["natural_need"]
        terminal = 1 if target["requires_terminal_draw"] else 0
        naturaldrop = target["target_natural_discard_lower_bound"]
        whitedrop = target["target_white_discard_lower_bound"]
        retained = target["retained_whites"]
        scale = max(length, need + terminal, naturaldrop + whitedrop)
        width = waiting["target_improvement_code_widths"][index]
        quality = 0.0
        if target["target_stage"] == "waiting_predecessor":
            quality = PURPOSES[retained] * purposes[scale]
            if need > 0 and width == 0:
                # 精确耗尽固定自然推进码时降低此用途先验；其他转换和全部根仍保留。
                quality = quality * DEADPURPOSE
        credit = widths[width]
        value = credit + quality - costs[scale]
        if best is None or value > best[13]:
            best = (index, family, target["target_stage"], retained, need, terminal,
                    scale, naturaldrop, whitedrop, width, quality, costs[scale], credit, value)
    return best


def payment_summary(waiting, seat, base):
    """把同码互斥抓打包络合成一次条件支付摘要，不推算摸牌或存活概率。

    返回向量：状态0未分析/1已知空/2已知有支付/3部分资格未知、支付摘要、
    已见证码数、这些码的精确公开容量和、原支付点最小/最大、单包络码数。
    None 支付摘要保持未知；空表的0只表示已见证支付子集为空。
    两行同码先取下端加有界价差，单包络单独折减，容量仅计一次。
    最后容量加权是相容码内部的排序摘要，容量不除墙余，不是期望积分。
    """
    payments = waiting["normal_draw_hu_payments"]
    if payments is None:
        return 0, None, 0, 0.0, None, None, 0
    unknown = len(waiting["qualification_unknown_codes"])
    flag = 3 if unknown > 0 else 1
    if not payments:
        return flag, 0.0, 0, 0.0, None, None, 0
    flag = 3 if unknown > 0 else 2
    currentcode = None
    lower = 0.0
    upper = 0.0
    capacity = 0.0
    rows = 0
    total = 0.0
    mass = 0.0
    codecount = 0
    singlecount = 0
    minimum = None
    maximum = None
    for payment in payments:
        code = payment["draw_code"]
        amount = float(payment["settlement"]["score_delta"][seat]) / base
        point = pay_points(amount)
        if minimum is None or point < minimum:
            minimum = point
        if maximum is None or point > maximum:
            maximum = point
        if code != currentcode:
            if currentcode is not None:
                if rows == 1:
                    envelope = SINGLESCOPE * lower
                    singlecount += 1
                else:
                    envelope = lower + ENVELOPEBLEND * (upper - lower)
                total += capacity * envelope
                mass += capacity
                codecount += 1
            currentcode = code
            lower = point
            upper = point
            capacity = float(payment["draw_capacity_before"])
            rows = 1
        else:
            lower = min(lower, point)
            upper = max(upper, point)
            rows += 1
    if rows == 1:
        envelope = SINGLESCOPE * lower
        singlecount += 1
    else:
        envelope = lower + ENVELOPEBLEND * (upper - lower)
    total += capacity * envelope
    mass += capacity
    codecount += 1
    return flag, total / mass, codecount, mass, minimum, maximum, singlecount


def wait_value(waiting, codeindex, seat, base, costs, widths, purposes,
               drawscale, pressure, discount, risk, anchor, unknowncost, allowlower):
    """普通出口、全部自然用途和当前胡取舍共同评分；未知资格不填虚构支付。

    当前胡模式按已知局部条件支付差减暴露代价比较，并让真实保留路线给出
    小幅有界取舍。自然先验不能单独买到放弃当前胡，升级见证也不保证继续。
    暴露折减与代价来自公开副露、墙余，是未校准排序代理，不是他家先胡率。
    allowlower 由当前可见库存、当前胡及父普通摸牌代理共同控制；叶内再要求
    whites_held 正库存，条件杠补白不能绕过当前零白护栏。末项仅说明本叶护栏。
    返回的事实元组只供根解释引用；规则、动作集合和条件节点均不变。
    """
    structure = waiting["structure"]
    lowerenabled = allowlower and structure["whites_held"] > 0
    shaped = drawscale > 0.0 and structure["whites_held"] > 0
    standard = actual_route(
        structure["standard_shanten"],
        route_support(waiting["standard_useful_codes"], waiting, codeindex, drawscale, shaped, lowerenabled),
        costs,
    )
    seven = None
    main = standard
    family = "standard"
    if structure["seven_pairs_shanten"] is not None:
        seven = actual_route(
            structure["seven_pairs_shanten"],
            route_support(waiting["seven_pairs_useful_codes"], waiting, codeindex, drawscale, False, lowerenabled),
            costs,
        )
        if seven[7] > main[7]:
            main = seven
            family = "seven_pairs"
    natural = natural_offer(waiting, standard, seven, costs, widths, purposes)
    payment = payment_summary(waiting, seat, base)
    unknown = len(waiting["qualification_unknown_codes"])
    knowncodes = payment[2]
    coverage = float(knowncodes) / (COVREF + float(knowncodes))
    qualcost = QUALUNANALYSED if payment[0] == 0 else QUALUNKNOWN * float(unknown) / float(1 + knowncodes + unknown)
    local = 0.0
    if payment[1] is not None and payment[1] > 0.0:
        local = LOCALCAP * payment[1] / (LOCALREF + payment[1])
        local = local * coverage * drawscale * pressure
    ordinary = main[7] + local
    joint = ordinary
    route = family
    if natural is not None and natural[13] > joint:
        joint = natural[13]
        route = "natural"
    gain = 0.0
    bias = 0.0
    if anchor is not None:
        if payment[1] is not None and payment[1] > anchor:
            gain = (payment[1] - anchor) * coverage
        if gain > 0.0 and natural is not None:
            # 只按目标自身绝对值给有界取舍；主路变窄不能释放差集或差值奖励。
            strength = max(0.0, natural[13])
            bias = min(NATURALBIASCAP, strength) * gain / (GAINREF + gain)
        value = HUBASE + anchor + discount * gain + bias
        # 普通路线值降低时此项不增加；保留共同成型成本，避免选择基准错位。
        readiness = main[7]
        value = value + min(SMALLREADY, max(0.0, readiness)) - risk
        value = value - ANCHREADY * max(0.0, -readiness) - qualcost - unknowncost
    else:
        value = WAITBASE + joint - qualcost - unknowncost - UNANCHOREXPOSURE * risk
    # 向量：普通型、七对、最佳自然目标、O、J、选中路线、条件支付摘要、
    # 未知资格码数、局部升级差、自然取舍点、资格未知罚、未知补牌罚、局部支付点、
    # 本叶下界补足护栏；原十三项位置保留，不能把补足量塞入精确张数或支付字段。
    facts = (standard, seven, natural, ordinary, joint, route, payment,
             unknown, gain, bias, qualcost, unknowncost, local, lowerenabled)
    return value, facts


def public_interaction(code, waiting, context, codeindex, drawscale, opponents):
    """公开交互扣分（PublicInteractionCost，本窗口弃牌助攻与中断的粗排序项）。

    只读本窗口公开河、副露和该直接等待叶的未见容量，绝不判他家能否吃碰。
    exact 零是已知库存项0；conservative 零、unknown、None 仍是未测库存项，
    用 None 表达，未测项不贡献库存扣分，不表示不会鸣牌或没有他家暗牌。
    正保守容量仍标记为下界；只归一化本项，不回写 route_support 的精确张数。
    公开未见张数包含暗牌，不除墙余，不作摸牌或被鸣牌概率。
    返回向量：扣分点、原证据身份、原容量、参与本项的库存量或None、
    他座河熟张座位数、副露压力、同花色邻近强度、封顶前无量纲交互量。
    """
    slot = codeindex.get(code)
    if slot is None or slot >= 33:
        # 此新特征只描述自然牌；白板仍由父代完整用途公式处理。
        return None
    cap = waiting["unseen_capacities"][slot]
    evidence = waiting["unseen_evidence"][slot]
    inventory = None
    if evidence == "exact" and cap is not None:
        inventory = cap
    elif evidence == "conservative" and cap is not None and cap > 0:
        inventory = cap
    familiar = 0
    for otherseat, river in enumerate(context["discards"]):
        if otherseat != context["seat"] and code in river:
            # 同座多次出现只算一次，熟张不是安全证据。
            familiar += 1
    near = 0.0
    if slot < 27:
        for otherseat, melds in enumerate(context["melds"]):
            if otherseat != context["seat"]:
                for meld in melds:
                    for tile in meld["tiles"]:
                        otherslot = codeindex.get(tile)
                        if otherslot is not None and otherslot < 27:
                            if slot - slot % 9 == otherslot - otherslot % 9:
                                distance = abs(slot % 9 - otherslot % 9)
                                if distance <= 2:
                                    # 至多两格是弱邻近特征，不是可吃顺子或听牌判定。
                                    near = max(near, 1.0 / (1.0 + float(distance)))
    exposure = float(opponents) / (1.0 + float(opponents))
    load = PUBLICNEAR_GAIN * near
    if inventory is not None:
        load += exposure * float(inventory) / 4.0
    assist = load / (1.0 + float(familiar))
    cost = PUBLICHELP_CAP * drawscale * min(1.0, assist)
    return cost, evidence, cap, inventory, familiar, exposure, near, assist


def maintained_ready(waiting, anchor, anchorfan, discount, pressure, risk, payment):
    """保持听牌估值（MaintainedReadyOffer，当前胡时已见证单次普通摸路线的排名值）。

    不改支付表或父支付变换；只有真实零向听、叶仍持白、资格已分析且没有
    未知资格、全部支付码两抓打包络均有见证时才估本项。支付点下界和最小番
    必须同时严格超过当前胡；一个高支付码不能单独买到放弃普通胡的支持。
    覆盖是相容码类别比例，不是墙内概率。精确零可排除库存码，所有非精确
    码及None仍各算一个可能码类，不给它们补实体；S只取父已见证精确容量和。
    S/(1+S)是一张参考量的排序饱和核，公开S含他家暗牌，不承诺未来可达。
    副露、墙余沿父discount/pressure/risk，只作排名衰减和费用，对手资格未知。
    返回平铺向量：新offer点、条件需摸次数、可能码类数、非精确码类数、
    已见证两包络码数、其精确容量和、码类覆盖、支付点下界、父支付包络摘要、
    最小条件番、排名衰减、封顶升级点、单次等待费用、相对当前胡的净取舍点。
    """
    structure = waiting["structure"]
    if structure["whites_held"] <= 0:
        return None
    if structure["standard_shanten"] != 0 and structure["seven_pairs_shanten"] != 0:
        return None
    if waiting["qualification_scope"] != "conditional_witness":
        return None
    if len(waiting["qualification_unknown_codes"]) > 0 or payment[0] != 2 or payment[6] != 0:
        # 未知/未分析/单包络沿父估值；未授新支持不代表其支付为0或已排除。
        return None
    if payment[1] is None or payment[4] is None or payment[4] <= anchor:
        return None
    payments = waiting["normal_draw_hu_payments"]
    if payments is None or not payments:
        return None
    minimumfan = None
    for row in payments:
        fan = row["settlement"]["fan"]
        if minimumfan is None or fan < minimumfan:
            minimumfan = fan
    if minimumfan is None or minimumfan <= anchorfan:
        return None
    possible = 0
    uncertain = 0
    for cap, evidence in zip(waiting["unseen_capacities"], waiting["unseen_evidence"]):
        if evidence == "exact" and cap is not None:
            if cap > 0:
                possible += 1
        else:
            # 保守零和None保持未知；这里只计一个码类，绝不填张数或删资格。
            possible += 1
            uncertain += 1
    known = payment[2]
    mass = payment[3]
    if possible == 0 or known == 0 or mass <= 0.0:
        return None
    coverage = min(1.0, float(known) / float(possible))
    # 已有直接普通摸见证与真实零向听共同限定单次条件；不保证能等到这一摸。
    waits = 1
    attenuation = discount * coverage * mass / (READYSUPPORT_REF + mass) / float(waits)
    upgrade = min(READYGAIN_CAP, max(0.0, payment[1] - anchor))
    waitcost = READYWAIT_FEE * risk / pressure * float(waits)
    benefit = attenuation * upgrade - (1.0 - attenuation) * anchor - waitcost
    offer = HUBASE + anchor + benefit
    return (offer, waits, possible, uncertain, known, mass, coverage, payment[4],
            payment[1], minimumfan, attenuation, upgrade, waitcost, benefit)


def claim_natural_strength(target, width, length, reference, purposes):
    """保白用途强度（RetainedRouteStrength，固定公开用途的有界排序支持）。

    length是该家族真实向听加一，reference固定为过牌最短实际成形尺度，
    单位均为条件行动次数，不保证本人还能摸这么多次。两边共用reference。
    D、末摸和待弃下界沿父目标；purposes沿父墙余/副露折减。D=0只免自然
    补张支持要求，仍保留末摸和待弃成本。返回无量纲强度，不是番或概率。
    """
    retained = target["retained_whites"]
    if retained == 0:
        return 0.0
    terminal = 1 if target["requires_terminal_draw"] else 0
    scale = max(length, target["natural_need"] + terminal,
                target["target_natural_discard_lower_bound"] + target["target_white_discard_lower_bound"])
    support = 1.0
    if target["natural_need"] > 0:
        support = float(width) / (WIDTHREF + float(width))
    proximity = 1.0 / (1.0 + float(max(0, scale - reference)))
    purpose = PURPOSES[retained] / PURPOSES[-1] * purposes[scale]
    return purpose * support * proximity


def claim_route_cost(passwaiting, passfacts, waiting, facts, codeindex,
                     drawscale, pressure, purposes):
    """根鸣牌机会费（RootClaimOpportunityCost，只估本窗口吃碰的备选损失）。

    七对关闭只读规则的家族不适用；保白用途按家族、阶段和k匹配全部目标。
    缺失是完整目标表中用途不可用，尺度或相容面变差只称用途减弱。
    两类损失取最大值，不把共享码或互斥用途当独立机会相加。
    实际成形尺度和综合进张支持沿真实事实；route_support复用父证据身份、
    未知代理和原下界护栏，不填None实体，不除墙余或重判胡资格。
    返回七项平铺量：费用排序点、七对/保白损失强度、省条件行动次数、
    无量纲支持增量、过牌/鸣后成形尺度。费用为0至0.75排序点。
    """
    passlength = passfacts[0][1]
    if passfacts[1] is not None:
        passlength = min(passlength, passfacts[1][1])
    length = facts[0][1]
    if facts[1] is not None:
        length = min(length, facts[1][1])
    passsupport = route_support(passwaiting["combined_useful_codes"], passwaiting,
                                codeindex, drawscale, False, passfacts[13])
    support = route_support(waiting["combined_useful_codes"], waiting,
                            codeindex, drawscale, False, facts[13])
    speedgain = float(max(0, passlength - length))
    widthgain = max(0.0, support[0] - passsupport[0]) / SPEEDCAP
    sevenloss = 0.0
    if passfacts[1] is not None and facts[1] is None:
        # 此None为规则已确认七对不适用，与未知容量或未分析支付分开。
        sevenloss = pressure * passfacts[1][5] / SPEEDCAP
        sevenloss = sevenloss / (1.0 + float(max(0, passfacts[1][1] - passlength)))
    naturalloss = 0.0
    for passindex, target in enumerate(passwaiting["structure"]["targets"]):
        if target["retained_whites"] > 0:
            family = target["family"]
            familylength = passfacts[0][1] if family == "standard" else passfacts[1][1]
            before = claim_natural_strength(
                target, passwaiting["target_improvement_code_widths"][passindex],
                familylength, passlength, purposes,
            )
            after = 0.0
            for targetindex, nexttarget in enumerate(waiting["structure"]["targets"]):
                if (nexttarget["family"] == family
                        and nexttarget["target_stage"] == target["target_stage"]
                        and nexttarget["retained_whites"] == target["retained_whites"]):
                    nextlength = facts[0][1] if family == "standard" else facts[1][1]
                    strength = claim_natural_strength(
                        nexttarget, waiting["target_improvement_code_widths"][targetindex],
                        nextlength, passlength, purposes,
                    )
                    after = max(after, strength)
            naturalloss = max(naturalloss, max(0.0, before - after))
    loss = min(1.0, max(sevenloss, naturalloss))
    cost = CLAIMOPTION_CAP * loss / (1.0 + speedgain + widthgain)
    return cost, sevenloss, naturalloss, speedgain, widthgain, passlength, length


def claim_root_offer(index, nodes, indexes, values, references, factslist,
                     passwaiting, passfacts, codeindex, drawscale, pressure, purposes):
    """吃碰根汇总（ClaimRootOffer，全部原合法续行扣本根机会费再择优）。

    原节点值、事实和引用数组只读；不拼接不同分支的速度、宽度与保白能力。
    非choices沿原条件聚合，只在父保守wait引用估费，不挑最好条件或补牌。
    hu、unknown_draw或缺等待事实不授新费，None表示未估而非已知零。
    返回新根值及十项平铺说明：根减值、续行/叶号、续行费用、七对/保白
    损失、省次数、支持增量、过牌/鸣后尺度。父ref/agg仍解释未改图。
    """
    root = nodes[index]
    children = root["children"] if root["kind"] == "choices" else (root["node_key"],)
    best = None
    bestindex = None
    bestreference = None
    bestcost = None
    for child in children:
        childindex = indexes[child]
        reference = references[childindex]
        leaf = nodes[reference]
        value = values[childindex]
        cost = None
        if leaf["kind"] == "wait" and factslist[childindex] is not None:
            cost = claim_route_cost(
                passwaiting, passfacts, leaf["waiting"], factslist[childindex],
                codeindex, drawscale, pressure, purposes,
            )
            if cost[0] > 0.0:
                value = value - cost[0]
        if best is None or value > best:
            best = value
            bestindex = childindex
            bestreference = reference
            bestcost = cost
    reduction = max(0.0, values[index] - best)
    detail = (reduction, bestindex, bestreference, None, None, None, None, None, None, None)
    if bestcost is not None:
        detail = (reduction, bestindex, bestreference, bestcost[0], bestcost[1], bestcost[2],
                  bestcost[3], bestcost[4], bestcost[5], bestcost[6])
    return best, detail


def score_actions(view):
    """对冻结后序图全部节点评分，再按原根表给每个 action_key 恰一项。

    全部分析过的合法续行参与，choices 才能选最优合法操作；condition 和
    replacement 仅聚合互斥条件，补牌码不能由策略挑选。缺口整批 ABSTAIN，
    不用保底补研究成功。没有文件、网络、时钟、模型、世界状态或跨调用缓存。
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
        drawmode = 2
        drawscale = UNKNOWNWALLSCALE
        room = None
        discount = drawscale * pressure
        risk = RISKBASE + OPPRISK * float(opponents) + UNKNOWNWALLRISK
    else:
        margin = max(0.0, float(wall) - float(RETENTION))
        drawmode = 1 if margin > 0.0 else 0
        drawscale = 1.0 if drawmode == 1 else 0.0
        # 四座无人截断时的本人摸牌节奏只作先验折减尺度，不承诺真实再摸次数。
        room = max(1.0, margin / 4.0)
        discount = drawscale * pressure * (0.30 + 0.70 * margin / (WALLSOFT + margin))
        risk = RISKBASE + OPPRISK * float(opponents) + LATERISK * WALLSOFT / (WALLSOFT + margin)
    # 合法13-3m等待态的固定自然目标 D+t 与弃牌下界均小于16；不缩小真实D。
    costs = tuple([FORMCOST * float(max(0, length - 1)) for length in range(16)])
    widths = tuple([drawscale * WIDTHCAP * float(width) / (WIDTHREF + float(width)) for width in range(35)])
    if room is None:
        purposes = tuple([drawscale * pressure for length in range(16)])
    else:
        purposes = tuple([drawscale * pressure / (1.0 + HORIZONCOST * max(0.0, float(length) - room))
                          for length in range(16)])
    codeindex = {code: index for index, code in enumerate(view["tile_order"])}
    nodes = view["nodes"]
    indexes = {node["node_key"]: index for index, node in enumerate(nodes)}
    anchor = None
    anchoramount = None
    anchorfan = None
    for action in view["actions"]:
        node = nodes[indexes[action["node_key"]]]
        if node["kind"] == "hu":
            amount = float(node["settlement"]["score_delta"][seat]) / base
            point = pay_points(amount)
            if anchor is None or point > anchor:
                anchor = point
                anchoramount = amount
                anchorfan = node["settlement"]["fan"]
    # 当前库存只读View真实字段；摸牌可能与手牌重合，存在性OR无需猜重叠。
    whitecode = view["tile_order"][-1]
    currentwhite = whitecode in context["my_hand"] or context["drawn_tile"] == whitecode
    allowlower = anchor is None and currentwhite and drawscale > 0.0
    # 8张沿用父WALLSOFT的新启发式缓冲用途，非再摸保证；未知墙余不给新支持。
    allowready = (anchor is not None and currentwhite and wall is not None
                  and float(wall) - float(RETENTION) > WALLSOFT and drawscale > 0.0)
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
            value, facts = wait_value(
                node["waiting"], codeindex, seat, base, costs, widths, purposes,
                drawscale, pressure, discount, risk, anchor, unknowncost, allowlower,
            )
            reference = index
            aggregate = (kind, 0, round(value, 3))
        elif kind == "hu":
            amount = float(node["settlement"]["score_delta"][seat]) / base
            value = HUBASE + pay_points(amount)
            facts = None
            reference = index
            aggregate = ("hu", amount, round(value, 3))
        elif kind == "choices":
            if not children:
                return {"status": "ABSTAIN", "reason": "empty_choices"}
            bestindex = indexes[children[0]]
            value = values[bestindex]
            for child in children:
                childindex = indexes[child]
                childvalue = values[childindex]
                if childvalue > value:
                    bestindex = childindex
                    value = childvalue
            facts = factslist[bestindex]
            reference = references[bestindex]
            aggregate = ("choices", len(children), bestindex, round(value, 3))
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
                if childvalue > upper:
                    upper = childvalue
            mean = total / float(len(children))
            # 相容码/公开条件的均值仅是排名摘要，不是假定均匀摸牌的期望积分。
            # 全码下端保留，全部码参与价差；绝不把最大值作为必然补牌。
            if kind == "replacement":
                value = lower + min(REPLACEMENTCAP, REPLACEMENTBLEND * max(0.0, mean - lower))
            else:
                value = lower + min(CONDITIONCAP, CONDITIONBLEND * max(0.0, mean - lower))
            facts = factslist[lowerindex]
            reference = references[lowerindex]
            aggregate = (kind, len(children), round(lower, 3), round(upper, 3),
                         round(mean, 3), round(value, 3))
        values.append(value)
        references.append(reference)
        factslist.append(facts)
        aggregates.append(aggregate)
    entries = []
    actioncount = len(view["actions"])
    ctx = (drawmode, opponents, round(risk, 3), round(discount, 3),
           anchoramount, None if anchor is None else round(anchor, 3))
    # 无当前合法Hu且有直接过牌等待态才建立参考；过牌分值完全不改。
    claimpass = None
    if anchor is None:
        for action in view["actions"]:
            passindex = indexes[action["node_key"]]
            if action["action_type"] == "pass" and nodes[passindex]["kind"] == "wait":
                claimpass = passindex
    for action in view["actions"]:
        index = indexes[action["node_key"]]
        kind = action["action_type"]
        adjustment = 0.0
        if kind == "chi" or kind == "peng":
            # 跳座仅在获裁决的前提下发生；条件图已保留全部跟打，不保证抢到鸣牌。
            adjustment = SKIPVALUE * float(action["skipped_seats"]) * drawscale - CLAIMCOST
        elif kind == "gang":
            adjustment = -GANGCOST
        value = float(values[index] + adjustment)
        claimfacts = None
        if anchor is None and claimpass is not None and (kind == "chi" or kind == "peng"):
            offer = claim_root_offer(
                index, nodes, indexes, values, references, factslist,
                nodes[claimpass]["waiting"], factslist[claimpass],
                codeindex, drawscale, pressure, purposes,
            )
            claimfacts = offer[1]
            if offer[0] < values[index]:
                # 只改本吃碰根；保留原跳座点和鸣牌费，不把机会费倒灌子图。
                value = float(offer[0] + adjustment)
        publicfacts = None
        rootnode = nodes[index]
        if allowlower and kind == "discard" and rootnode["kind"] == "wait":
            waiting = rootnode["waiting"]
            if waiting["structure"]["whites_held"] > 0:
                actionkey = action["action_key"]
                if actionkey[:8] == "discard:":
                    # 只扣本次提交的明确弃牌；未来条件跟打不在此公开估值范围。
                    publicfacts = public_interaction(
                        actionkey[8:], waiting, context, codeindex, drawscale, opponents,
                    )
                    if publicfacts is not None and publicfacts[0] > 0.0:
                        # 全父值先完整计算；保护分支完全不做额外浮点加减。
                        value = value - publicfacts[0]
        facts = factslist[index]
        readyfacts = None
        readytaken = False
        if allowready and kind == "discard" and rootnode["kind"] == "wait":
            readykey = action["action_key"]
            if readykey[:8] == "discard:" and readykey[8:] != whitecode:
                readyfacts = maintained_ready(
                    rootnode["waiting"], anchor, anchorfan, discount, pressure, risk, facts[6],
                )
                # 只有严格正取舍且新offer胜过完整父值才提高本根；即时Hu完全不改。
                if readyfacts is not None and readyfacts[13] > 0.0 and readyfacts[0] > value:
                    value = readyfacts[0]
                    readytaken = True
        trace = {"u": "heuristic_rank_points", "f": "vip_maintained_ready_choice_m1/1",
                 "ref": references[index], "agg": aggregates[index],
                 "a": (kind, action["pending_condition"] is not None,
                       action["skipped_seats"], round(adjustment, 3)),
                 "ctx": ctx,
                 # 标量只解释本根扣分；None表示此根未估本项。
                 "public": None if publicfacts is None else round(publicfacts[0], 3),
                 # offer/净取舍/是否采用；agg仍为父节点值，新项仅解释本窗口根层取舍。
                 "ready": None if readyfacts is None else
                 (round(readyfacts[0], 3), round(readyfacts[13], 3), readytaken)}
        if claimfacts is not None:
            # 父ref/agg解释原图；cr另给本根取舍的合法续行引用。
            if actioncount <= 24:
                trace = dict(list(trace.items()) + [
                    ("cf", "vip_claim_route_opportunity_m1/1"),
                    ("cr", tuple([None if part is None else round(part, 3) for part in claimfacts])),
                ])
            elif actioncount <= 64:
                trace = dict(list(trace.items()) + [
                    ("cf", "vip_claim_route_opportunity_m1/1"),
                    ("cr", (round(claimfacts[0], 3), claimfacts[1], claimfacts[2])),
                ])
        if facts is not None:
            standard = facts[0]
            seven = facts[1]
            natural = facts[2]
            payment = facts[6]
            if actioncount <= 24:
                # 所有向量都平铺；ref 绑定原输入叶，未把最低叶解释成整个聚合。
                trace = dict(list(trace.items()) + [
                    ("std", (standard[0], standard[1], standard[2], standard[3], standard[4],
                             round(standard[5], 3), round(standard[6], 3), round(standard[7], 3))),
                    ("seven", None if seven is None else
                     (seven[0], seven[1], seven[2], seven[3], seven[4],
                      round(seven[5], 3), round(seven[7], 3))),
                    ("nat", None if natural is None else
                     (natural[0], natural[1], natural[2], natural[3], natural[4], natural[5],
                      natural[6], natural[7], natural[8], natural[9],
                      round(natural[10], 3), round(natural[11], 3),
                      round(natural[12], 3), round(natural[13], 3))),
                    ("oj", (round(facts[3], 3), round(facts[4], 3), facts[5])),
                    ("pay", (payment[0], payment[2], payment[3],
                             None if payment[1] is None else round(payment[1], 3),
                             None if payment[4] is None else round(payment[4], 3),
                             None if payment[5] is None else round(payment[5], 3), payment[6])),
                    ("trade", (facts[7], round(facts[8], 3), round(facts[9], 3),
                               round(facts[10], 3), round(facts[11], 3), round(facts[12], 3))),
                    # 向量：叶护栏、普通补足权重/原支持点、七对补足权重/原支持点。
                    # 新支持点仍在std/seven原支持位，精确库存与非精确码数保持身份。
                    ("lower", (facts[13], round(standard[8], 3), round(standard[9], 3),
                               None if seven is None else round(seven[8], 3),
                               None if seven is None else round(seven[9], 3))),
                    # 八项平铺，仅小根表保留；库存None仍保持未知身份。
                    ("public_facts", None if publicfacts is None else
                     (round(publicfacts[0], 3), publicfacts[1], publicfacts[2], publicfacts[3],
                      publicfacts[4], round(publicfacts[5], 3), round(publicfacts[6], 3),
                      round(publicfacts[7], 3))),
                    # 固定14项，只在父小根表界内给出完整本根条件估值。
                    ("ready_facts", None if readyfacts is None else
                     tuple([round(part, 3) for part in readyfacts])),
                ])
            elif actioncount <= 64:
                trace = dict(list(trace.items()) + [
                    ("take", (facts[5], None if natural is None else natural[0])),
                    ("pay", (payment[0], payment[2], facts[7])),
                    ("oj", (round(facts[3], 3), round(facts[4], 3))),
                    ("lower", (facts[13], round(standard[8], 3), round(standard[9], 3),
                               round(standard[5], 3),
                               None if seven is None else round(seven[8], 3),
                               None if seven is None else round(seven[9], 3),
                               None if seven is None else round(seven[5], 3))),
                ])
        if actioncount > 64:
            # 全图值已完整计算；大根表只保留叶引用，共用单位与公式说明写一次。
            trace = {"ref": references[index]}
            if not entries:
                trace = dict(list(trace.items()) + [
                    ("u", "heuristic_rank_points"),
                    ("f", "vip_maintained_ready_choice_m1/1"),
                    ("lower_enabled", allowlower), ("public_enabled", allowlower),
                    ("ready_enabled", allowready), ("anchor_fan", anchorfan),
                    ("cf", "vip_claim_route_opportunity_m1/1"), ("claim_enabled", claimpass is not None),
                    ("n", len(nodes)), ("roots", actioncount),
                ])
            if claimfacts is not None:
                trace = dict(list(trace.items()) + [
                    ("cr", (round(claimfacts[0], 3), claimfacts[1], claimfacts[2])),
                ])
        if actioncount > 256:
            # 超大根表仅首根保存共用说明；其余空trace不改变分值、根或子图。
            trace = {}
            if not entries:
                trace = {"u": "heuristic_rank_points", "f": "vip_maintained_ready_choice_m1/1",
                         "lower_enabled": allowlower, "public_enabled": allowlower,
                         "ready_enabled": allowready, "anchor_fan": anchorfan,
                         "cf": "vip_claim_route_opportunity_m1/1", "claim_enabled": claimpass is not None,
                         "n": len(nodes), "roots": actioncount}
        entries.append({"action_key": action["action_key"], "score": value, "trace": trace})
    return {"status": "SCORED", "entries": entries}
