"""目标自身代价的m1联合排序；所有点数是标尺，均非概率或期望积分。"""

PAYCAP = 50.0
PAYREF = 192.0
HUBASE = 10.0
WAITBASE = 12.0
FORMCOST = 3.4
SPEEDCAP = 4.8
SPEEDREF = 12.0
WIDTHREF = 4.0
UNSEENSOFT = 0.65
PURPOSES = (0.0, 4.5, 18.0, 32.0, 48.0)
OWNDISCARD = 0.18
OWNWHITE = 0.32
OWNTERMINAL = 0.50
EARNLINEAR = 0.30
EARNSQUARE = 0.12
USEWHITEPRICE = 0.45
TARGETSTEP = 0.85
TARGETDISCARD = 0.18
TARGETWHITEDROP = 0.28
TARGETTERMINAL = 0.15
TARGETMASSREF = 3.0
EXITFLOOR = 0.40
EXITMASSREF = 6.0
EXITWIDTHREF = 3.0
EXITSTEP = 0.20
DEVELOPPRIOR = 1.8
PREPSTEP = 0.75
PREPDISCARD = 0.15
PREPWEIGHT = 0.90
TARGETWEIGHT = 0.75
BACKSTEPS = 0.35
BACKGAP = 0.16
BACKCAP = 2.6
BACKREF = 10.0
HORIZONCOST = 0.40
RETENTION = 20
WALLSOFT = 8.0
UNKNOWNWALLSCALE = 0.70
OPPDECAY = 0.05
RISKBASE = 1.8
OPPRISK = 0.12
LATERISK = 3.4
UNKNOWNWALLRISK = 0.7
ENVELOPEBLEND = 0.20
SINGLESCOPE = 0.70
LOCALCAP = 6.0
LOCALREF = 8.0
KNOWNPAYLINEAR = 0.55
PAYMASSREF = 8.0
PAYWIDTHREF = 3.0
QUALUNKNOWN = 0.70
QUALUNANALYSED = 1.0
UNKNOWNDRAW = 2.5
UNANCHOREXPOSURE = 0.15
NETUPGRADEWEIGHT = 1.40
NETUPWIDTHREF = 4.0
NETEXITWIDTHREF = 4.0
NETANCHORPRICE = 0.26
NETWAITFLOOR = 0.32
NETCARRY = 0.20
NETDISTANCE = 0.75
REMOTEANCHORBASE = 0.12
REMOTEANCHORSTEP = 0.14
REMOTEUNKNOWN = 0.35
REMOTEDOWNSIDE = 0.45
DISTANCEPRICE = 0.18
CONDITIONBLEND = 0.20
CONDITIONCAP = 1.0
REPLACEMENTBLEND = 0.40
REPLACEMENTCAP = 2.3
CLAIMCOST = 0.25
SKIPVALUE = 0.10
GANGCOST = 0.12


def pay_points(amount):
    """本家净积分除基础分后转有界排序点，积分向量仍按座位0—3读取。"""
    return PAYCAP * amount / (PAYREF + abs(amount))


def inventory_support(slot, waiting):
    """公开库存只作排序支持，返回支持张数、精确张数及非精确标记。

    exact零可关闭本码；保守零或未知仍保留软支持。容量包含他家暗牌，
    不除墙余，不对未知资格补造支付，也不把下界写成精确库存。
    """
    capacity = waiting["unseen_capacities"][slot]
    evidence = waiting["unseen_evidence"][slot]
    if evidence == "exact" and capacity is not None:
        return float(capacity), capacity, 0
    if evidence == "conservative" and capacity is not None and capacity > 0:
        return float(capacity), 0, 1
    return UNSEENSOFT, 0, 1


def code_support(codes, stock, codeindex, drawscale):
    """同码只计一次；返回支持点、支持量、码数、精确量、未知码数和槽位。

    第六项是规范牌序槽位，供后续联合去重，不能据此推断精确缺牌重数。
    支持点对库存及不同码各饱和一次，均非独立事件概率。
    """
    slots = set()
    for code in codes:
        slot = codeindex[code]
        if stock[slot][0] > 0.0:
            slots.add(slot)
    mass = 0.0
    exact = 0
    uncertain = 0
    for slot in slots:
        inventory, precise, unknown = stock[slot]
        mass += inventory
        exact += precise
        uncertain += unknown
    width = len(slots)
    credit = (drawscale * SPEEDCAP * mass / (SPEEDREF + mass)
              * float(width) / (WIDTHREF + float(width)))
    return credit, mass, width, exact, uncertain, tuple(sorted(slots))


def purpose_scale(length, room, drawscale, pressure):
    """公开墙余和副露仅折减先验；length是条件行动标尺而非未来摸牌次数。"""
    excess = 0.0 if room is None else max(0.0, float(length) - room)
    return drawscale * pressure / (1.0 + HORIZONCOST * excess)


def earned_scale(effort):
    """将自身补弃及终端条件成本转成有界成熟度，不授予规则资格。"""
    return 1.0 / (1.0 + EARNLINEAR * effort + EARNSQUARE * effort * effort)


def ordinary_route(family, shanten, support, prior):
    """真实普通出口的一条完整报价；成本是向听排序点，码是已用支持。

    prior只保留有界自然对子先验，不从自然四张重判豪华七对资格。
    所有路线用同一字典布局，字段的点数均为启发式排序单位。
    """
    length = max(0, shanten) + 1
    cost = FORMCOST * float(length - 1)
    return {"kind": "ordinary", "family": family, "index": -1,
            "retained": 0, "white_used": 0, "need": length - 1,
            "natural_drop": 0, "white_drop": 0, "terminal": 0,
            "effort": float(length - 1), "length": length,
            "value": support[0] - cost + prior, "purpose": prior,
            "cost": cost, "budget": 1.0, "codes": support[5],
            "support": support[:5], "shanten": shanten}


def payment_summary(waiting, codeindex, seat, base):
    """逐码条件胡支付（RouteConditionalHuPayment，给定下一普通摸牌的结算）。

    同码两抓打假设先取下端加有限价差，单包络另外折减；不是两次机会。
    输出状态、摘要点、码数、容量、单包络数、最小番、逐码报价和槽位。
    逐码报价为槽位/容量/点数/包络数/最小番/最大番/下端/上端；
    未分析状态0、已知空1、有支付2、部分未知3各自保留，未知不当零支付。
    只从同一行settlement读取净积分；不查询或发明任何规则见证。
    """
    payments = waiting["normal_draw_hu_payments"]
    if payments is None:
        return 0, None, 0, 0.0, 0, None, (), ()
    partial = len(waiting["qualification_unknown_codes"]) > 0
    if not payments:
        return 3 if partial else 1, 0.0, 0, 0.0, 0, None, (), ()
    groups = []
    current = None
    lower = 0.0
    upper = 0.0
    capacity = 0.0
    rows = 0
    lowfan = None
    highfan = None
    for payment in payments:
        code = payment["draw_code"]
        point = pay_points(float(payment["settlement"]["score_delta"][seat]) / base)
        fan = payment["settlement"]["fan"]
        if code != current:
            if current is not None:
                groups.append((codeindex[current], capacity, lower, upper, rows, lowfan, highfan))
            current = code
            lower = point
            upper = point
            capacity = float(payment["draw_capacity_before"])
            rows = 1
            lowfan = fan
            highfan = fan
        else:
            lower = min(lower, point)
            upper = max(upper, point)
            rows += 1
            lowfan = min(lowfan, fan)
            highfan = max(highfan, fan)
    groups.append((codeindex[current], capacity, lower, upper, rows, lowfan, highfan))
    offers = []
    total = 0.0
    mass = 0.0
    singles = 0
    minimumfan = None
    slots = []
    for slot, capacity, lower, upper, rows, lowfan, highfan in groups:
        if rows == 1:
            envelope = SINGLESCOPE * lower
            singles += 1
        else:
            envelope = lower + ENVELOPEBLEND * (upper - lower)
        offers.append((slot, capacity, envelope, rows, lowfan, highfan, lower, upper))
        slots.append(slot)
        total += capacity * envelope
        mass += capacity
        minimumfan = lowfan if minimumfan is None else min(minimumfan, lowfan)
    return (3 if partial else 2, total / mass, len(groups), mass,
            singles, minimumfan, tuple(offers), tuple(slots))


def local_payment_credit(payment, drawscale, pressure):
    """只给已见证的下一普通摸牌报价定价；不广播到远保白目标。

    同码已合并后的容量与码宽只作有限支持，饱和信用和线性信用择大。
    返回两种变换及共同槽信用，全部是排序点，不是长期期望积分。
    """
    point = payment[1]
    if point is None or point <= 0.0:
        return 0.0, 0.0, 0.0
    mass = payment[3]
    width = float(payment[2])
    gate = mass / (PAYMASSREF + mass) * width / (PAYWIDTHREF + width)
    scale = drawscale * pressure * gate
    saturated = LOCALCAP * point / (LOCALREF + point) * scale
    linear = KNOWNPAYLINEAR * point * scale
    return saturated, linear, max(saturated, linear)


def target_route(index, target, route, support, room, drawscale, pressure):
    """固定用途只承担自身成本；不读或补收全自然准备缺张。

    D、自然弃牌与待弃白单位为张/动作次；终端标记独立付费。
    effort=D+0.18自然弃+0.32待弃白+0.50终点，是排序成本，
    不是保证摸牌次数。同family的真实出口是条件退路，不提供胡资格。
    白用途（WhitePurpose，保留与块内百搭的条件用途）仅影响用途先验：
    用白较多时折减自然释放先验，但不假称已知具体白资源或分解。
    远路线完全不消费条件支付摘要，更不会领取整节点最高支付。
    """
    need = target["natural_need"]
    drawneed = target["target_natural_draw_lower_bound"]
    naturaldrop = target["target_natural_discard_lower_bound"]
    whitedrop = target["target_white_discard_lower_bound"]
    terminal = 1 if target["requires_terminal_draw"] else 0
    retained = target["retained_whites"]
    used = target["white_used"]
    effort = (float(drawneed) + OWNDISCARD * float(naturaldrop)
              + OWNWHITE * float(whitedrop) + OWNTERMINAL * float(terminal))
    length = max(1, drawneed + terminal)
    earned = earned_scale(effort)
    gate = 1.0
    if need > 0:
        gate = 0.0
        if support[2] > 0:
            gate = 0.50 + 0.50 * support[1] / (TARGETMASSREF + support[1])
    exitmass = route["support"][1]
    exitwidth = float(route["support"][2])
    exitgate = (exitmass / (EXITMASSREF + exitmass)
                * exitwidth / (EXITWIDTHREF + exitwidth))
    exitgate /= 1.0 + EXITSTEP * float(route["length"] - 1)
    usegate = 1.0 / (1.0 + USEWHITEPRICE * float(used))
    prior = PURPOSES[retained] if target["target_stage"] == "waiting_predecessor" else 0.0
    purpose = (prior * earned * gate * usegate
               * (EXITFLOOR + (1.0 - EXITFLOOR) * exitgate)
               * purpose_scale(length, room, drawscale, pressure))
    cost = (TARGETSTEP * float(max(0, length - route["length"]))
            + TARGETDISCARD * float(naturaldrop)
            + TARGETWHITEDROP * float(whitedrop)
            + TARGETTERMINAL * float(terminal))
    # codes只表示本报价占用过的公开支持码，不能作为精确目标分解或事件并集。
    codes = tuple(sorted(set(list(route["codes"]) + list(support[5]))))
    return {"kind": "target", "family": target["family"], "index": index,
            "retained": retained, "white_used": used, "need": need,
            "natural_drop": naturaldrop, "white_drop": whitedrop, "terminal": terminal,
            "effort": effort, "length": length, "value": route["value"] + purpose - cost,
            "purpose": purpose, "cost": cost,
            "budget": TARGETWEIGHT * earned * gate * usegate, "codes": codes,
            "support": support[:5], "shanten": route["shanten"]}


def preparation_route(waiting, standard, support, room, drawscale, pressure):
    """自然面子准备（NaturalSetPreparationFacts，不借白、不含将的目标）单列竞争。

    零白也能有自然发展先验；D=0只表明自然面子已备好，不能当作已胡、
    爆头或未来必摸白。这条路线只付自身D和弃牌，不向保白目标收费。
    发展先验与退路共同报价，最终仍与普通出口和已见证支付择大。
    """
    preparation = waiting["natural_preparation"]
    need = preparation["natural_draw_lower_bound"]
    discard = preparation["natural_discard_lower_bound"]
    effort = float(need) + 0.25 * float(discard)
    length = max(1, need + 1)
    earned = earned_scale(effort)
    gate = 1.0
    if need > 0:
        gate = 0.0
        if support[2] > 0:
            gate = support[1] / (TARGETMASSREF + support[1])
    development = DEVELOPPRIOR * earned * gate * purpose_scale(length, room, drawscale, pressure)
    cost = PREPSTEP * float(max(0, length - standard["length"])) + PREPDISCARD * float(discard)
    codes = tuple(sorted(set(list(standard["codes"]) + list(support[5]))))
    return {"kind": "natural_development", "family": "standard", "index": -2,
            "retained": preparation["whites_held"], "white_used": 0, "need": need,
            "natural_drop": discard, "white_drop": 0, "terminal": 1,
            "effort": effort, "length": length, "value": standard["value"] + development - cost,
            "purpose": development, "cost": cost, "budget": PREPWEIGHT * earned * gate,
            "codes": codes, "support": support[:5], "shanten": standard["shanten"]}


def marginal_backup(routes, primary, stock, room, drawscale, pressure):
    """备用只消费主报价以外的相容码；同码多用途取最大，不相加概率。

    复制同一条路线或只复制已有码，不改变最终信用。每个码的权重受自身
    成本、主路差距和墙余折减，再在至多34码上按库存/不同码各限幅。
    这只去重公开推进支持；distance_only不足以识别白资源或缺牌重数交叠。
    """
    occupied = set(primary["codes"])
    offers = []
    for route in routes:
        steps = float(max(0, route["length"] - 1))
        gap = max(0.0, primary["value"] - route["value"])
        excess = 0.0 if room is None else max(0.0, float(route["length"]) - room)
        weight = route["budget"] / ((1.0 + BACKSTEPS * steps * steps + BACKGAP * gap)
                                    * (1.0 + HORIZONCOST * excess))
        for slot in route["codes"]:
            if slot not in occupied and stock[slot][0] > 0.0 and weight > 0.0:
                offers.append((slot, weight))
    combined = []
    current = None
    peak = 0.0
    for slot, weight in sorted(offers):
        if slot != current:
            if current is not None:
                combined.append((current, peak))
            current = slot
            peak = weight
        else:
            peak = max(peak, weight)
    if current is not None:
        combined.append((current, peak))
    mass = 0.0
    diversity = 0.0
    exact = 0
    uncertain = 0
    for slot, weight in combined:
        inventory, precise, unknown = stock[slot]
        mass += weight * inventory
        diversity += weight
        exact += precise
        uncertain += unknown
    credit = (drawscale * pressure * BACKCAP * mass / (BACKREF + mass)
              * diversity / (WIDTHREF + diversity))
    return credit, mass, diversity, len(combined), exact, uncertain, len(occupied)


def joint_routes(waiting, codeindex, seat, base, room, drawscale, pressure):
    """完整联合报价：普通出口、逐码下一摸支付、所有用途及自然发展共同竞争。

    已知支付有自己的近端报价，远目标只有用途先验和自身代价。主报价择大，
    其后只增未覆盖码的有限备用支持。输出主报价、普通基准、最佳保白目标、
    自然准备、支付与备用摘要；既不先固定牌效首选，也不逐目标累加奖励。
    """
    structure = waiting["structure"]
    stock = tuple([inventory_support(slot, waiting) for slot in range(len(waiting["unseen_capacities"]))])
    standard = ordinary_route("standard", structure["standard_shanten"],
                              code_support(waiting["standard_useful_codes"], stock, codeindex, drawscale), 0.0)
    routes = [standard]
    ordinary = standard
    seven = None
    if structure["seven_pairs_shanten"] is not None:
        length = max(0, structure["seven_pairs_shanten"]) + 1
        pairprior = (0.30 * float(min(2, max(0, structure["natural_pair_count"] - 4)))
                     / float(length) * drawscale * pressure)
        seven = ordinary_route("seven_pairs", structure["seven_pairs_shanten"],
                               code_support(waiting["seven_pairs_useful_codes"], stock, codeindex, drawscale),
                               pairprior)
        routes.append(seven)
        if seven["value"] > ordinary["value"]:
            ordinary = seven
    payment = payment_summary(waiting, codeindex, seat, base)
    paymentcredit = local_payment_credit(payment, drawscale, pressure)
    benchmark = ordinary["value"]
    if payment[2] > 0:
        # 已见证一次摸后能胡时直接用该事实，不要求当前真实向听必须为0。
        support = code_support(waiting["legal_hu_draw_codes"], stock, codeindex, drawscale)
        near = {"kind": "given_normal_hu", "family": "qualified_union", "index": -1,
                "retained": 0, "white_used": 0, "need": 0, "natural_drop": 0,
                "white_drop": 0, "terminal": 1, "effort": 0.0, "length": 1,
                "value": support[0] + paymentcredit[2], "purpose": paymentcredit[2],
                "cost": 0.0, "budget": 0.85, "codes": support[5],
                "support": support[:5], "shanten": None}
        routes.append(near)
        benchmark = max(benchmark, near["value"])
    targetbest = None
    for index, target in enumerate(structure["targets"]):
        route = standard if target["family"] == "standard" else seven
        support = code_support(target["conditional_need_improvement_codes"], stock, codeindex, drawscale)
        proposal = target_route(index, target, route, support, room, drawscale, pressure)
        routes.append(proposal)
        if (target["target_stage"] == "waiting_predecessor" and target["retained_whites"] > 0
                and (targetbest is None or proposal["value"] > targetbest["value"])):
            targetbest = proposal
    preparation = preparation_route(waiting, standard,
                                    code_support(waiting["natural_preparation"]["natural_need_improvement_codes"],
                                                 stock, codeindex, drawscale), room, drawscale, pressure)
    routes.append(preparation)
    primary = routes[0]
    for route in routes:
        if route["value"] > primary["value"]:
            primary = route
    backup = marginal_backup(routes, primary, stock, room, drawscale, pressure)
    # 拒绝当前胡只消费超出普通/近端支付及备用的远净增量，不借宽进张重复融资。
    optiongain = 0.0 if targetbest is None else max(0.0, targetbest["value"] - benchmark - backup[0])
    return (primary, ordinary, targetbest, preparation, payment, paymentcredit,
            backup, benchmark, optiongain, standard, seven)


def net_hu_offer(anchor, discount, risk, joint):
    """当前胡的净继续报价：同码实际净升级与远用途净增量择大。

    直接升级只用该码的见证支付。远增量只用自己的用途成本，再支付随
    effort增加的确定胡机会成本。普通维持、未知支付、下降支付和等待费
    分开，备用信用不能独立推动弃胡。所有系数是排序折减，不是存活概率。
    返回净点/渠道/升级/下降/维持支持/升级码数/升级容量/远净点/远机会价/
    远出口价/承接/共用机会价/等待费/距离费/远目标净增量。
    """
    ordinary = joint[1]
    target = joint[2]
    payment = joint[4]
    mass = payment[3]
    width = float(payment[2])
    preserved = 0.0
    positive = 0.0
    negative = 0.0
    upgrademass = 0.0
    upgradewidth = 0
    for slot, capacity, point, rows, lowfan, highfan, lower, upper in payment[6]:
        preserved += capacity * min(anchor, max(0.0, point))
        difference = point - anchor
        if difference > 0.0:
            positive += capacity * difference
            upgrademass += capacity
            upgradewidth += 1
        else:
            negative += capacity * max(0.0, -difference)
    fraction = 0.0
    if mass > 0.0 and anchor > 0.0:
        fraction = preserved / (mass * anchor)
    # 有直接支付行就遵从一次给定摸牌事实；向听只约束未见证的普通退路。
    length = 1 if payment[2] > 0 else ordinary["length"]
    distancegate = 1.0 / (1.0 + NETDISTANCE * float(length - 1))
    maintained = (mass / (PAYMASSREF + mass) * width / (NETEXITWIDTHREF + width)
                  * fraction * distancegate)
    upgradesupport = (upgrademass / (PAYMASSREF + upgrademass)
                      * float(upgradewidth) / (NETUPWIDTHREF + float(upgradewidth)))
    upgrade = 0.0
    if upgrademass > 0.0:
        upgrade = NETUPGRADEWEIGHT * discount * positive / upgrademass * upgradesupport
    downside = discount * negative / (PAYMASSREF + mass)
    offer = upgrade - downside
    channel = "same_code_conditional_upgrade"
    remote = 0.0
    remoteprice = 0.0
    fallback = 0.0
    if target is not None and joint[8] > 0.0:
        remoteprice = anchor * (REMOTEANCHORBASE + REMOTEANCHORSTEP * target["effort"])
        if payment[1] is None:
            fallback = REMOTEUNKNOWN * anchor
        else:
            fallback = REMOTEDOWNSIDE * max(0.0, anchor - max(0.0, payment[1]))
        remote = discount * joint[8] - remoteprice - fallback
        if remote > offer:
            offer = remote
            channel = "own_target_purpose_surplus"
    carry = NETCARRY * discount * maintained * max(0.0, ordinary["value"])
    opportunity = NETANCHORPRICE * anchor * (1.0 - discount * maintained)
    waitfee = risk * (NETWAITFLOOR + (1.0 - NETWAITFLOOR) * (1.0 - maintained))
    distancefee = DISTANCEPRICE * max(0.0, -ordinary["value"])
    net = offer + carry - opportunity - waitfee - distancefee
    return (net, channel, upgrade, downside, maintained, upgradewidth, upgrademass,
            remote, remoteprice, fallback, carry, opportunity, waitfee, distancefee, joint[8])


def wait_value(waiting, codeindex, seat, base, room, drawscale, pressure, discount, risk,
               anchor, unknowncost):
    """共同路线报价映射等待动作；未知/空资格分开计价，所有合法根仍返回。

    有当前胡时用净升级门；没有当前胡时用主报价加边际备用。未知补牌的
    同一真实前态另付未知费，不能挑未来最好牌。返回分值与有限事实摘要。
    """
    joint = joint_routes(waiting, codeindex, seat, base, room, drawscale, pressure)
    payment = joint[4]
    known = payment[2]
    unknown = len(waiting["qualification_unknown_codes"])
    qualcost = (QUALUNANALYSED if payment[0] == 0 else
                QUALUNKNOWN * float(unknown) / float(1 + known + unknown))
    offer = None
    if anchor is None:
        value = WAITBASE + joint[0]["value"] + joint[6][0] - qualcost - unknowncost - UNANCHOREXPOSURE * risk
    else:
        offer = net_hu_offer(anchor, discount, risk, joint)
        value = HUBASE + anchor + offer[0] - qualcost - unknowncost
    return value, (joint, offer, qualcost, unknowncost)


def route_description(route):
    """有界诊断按种类/牌型/目标索引/白用途/缺弃/终点/成本/报价排列。

    index只是公开targets中的引用；负索引是本公式的路线种类标记，
    不是来源、牌码、序号或结局标识。无精确见证的目标不输出虚构分解。
    """
    if route is None:
        return None
    return (route["kind"], route["family"], route["index"], route["retained"], route["white_used"],
            route["need"], route["natural_drop"], route["white_drop"], route["terminal"],
            round(route["effort"], 3), route["length"], round(route["purpose"], 3),
            round(route["cost"], 3), round(route["value"], 3), route["support"][2])


def score_actions(view):
    """纯评分入口：所有完整合法根各返回一条有限分和有界解释。

    冻结后序共享节点只计算一次；choices才择优。补牌及未裁决条件均消费
    全部有序边，用下端加有限均值价差，不能选最好未来牌或删未知分支。
    机械缺口显式ABSTAIN使研究失败；没有文件/网络/时钟/随机/跨调用状态。
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
            point = pay_points(float(node["settlement"]["score_delta"][seat]) / base)
            anchor = point if anchor is None else max(anchor, point)
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
            adjustment = SKIPVALUE * float(action["skipped_seats"]) * drawscale - CLAIMCOST
        elif kind == "gang":
            adjustment = -GANGCOST
        value = float(values[index] + adjustment)
        facts = factslist[index]
        trace = {}
        if actioncount <= 64:
            trace = {"ref": references[index], "agg": aggregates[index],
                     "condition": action["pending_condition"], "adjust": round(adjustment, 3)}
        if facts is not None and actioncount <= 8:
            joint = facts[0]
            payment = joint[4]
            trace = dict(list(trace.items()) + [
                ("primary", route_description(joint[0])),
                ("ordinary", route_description(joint[1])),
                ("target", route_description(joint[2])),
                ("natural", route_description(joint[3])),
                ("backup", tuple([round(part, 3) for part in joint[6]])),
                ("pay", (payment[0], None if payment[1] is None else round(payment[1], 3),
                         payment[2], payment[3], payment[4], payment[5])),
                ("pay_credit", tuple([round(part, 3) for part in joint[5]])),
                ("joint", (round(joint[7], 3), round(joint[8], 3), round(facts[2], 3), round(facts[3], 3))),
                ("offer", None if facts[1] is None else
                 (round(facts[1][0], 3), facts[1][1]) + tuple([round(part, 3) for part in facts[1][2:]])),
            ])
        elif facts is not None and actioncount <= 32:
            joint = facts[0]
            trace = dict(list(trace.items()) + [
                ("primary", (joint[0]["kind"], joint[0]["family"], round(joint[0]["value"], 3))),
                ("target", route_description(joint[2])),
                ("natural", (joint[3]["need"], joint[3]["natural_drop"], round(joint[3]["value"], 3))),
                ("backup", (joint[6][3], round(joint[6][0], 3))),
                ("pay", (joint[4][0], joint[4][2], round(joint[5][2], 3))),
                ("offer", None if facts[1] is None else
                 (round(facts[1][0], 3), facts[1][1], round(facts[1][8], 3), round(facts[1][12], 3))),
                ("option_gain", round(joint[8], 3)),
            ])
        if not entries:
            trace = dict(list(trace.items()) + [
                ("unit", "heuristic_rank_points"),
                ("formula", "vip_target_specific_joint_m1/1"),
                ("context", (wall, opponents, round(discount, 3), round(risk, 3), anchor)),
                ("unknown", "opponent_hu_and_future_draw_reachability"),
                ("scope", "distance_only_support_not_probability_or_precise_target_witness"),
            ])
        entries.append({"action_key": action["action_key"], "score": value, "trace": trace})
    return {"status": "SCORED", "entries": entries}
