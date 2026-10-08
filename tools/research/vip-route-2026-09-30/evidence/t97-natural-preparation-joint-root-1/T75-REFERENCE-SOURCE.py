"""冻结视图/3的海选联合启发式；逐码净升级、保听出口与弃胡机会成本联合取舍。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t97-natural-preparation-joint-root-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

PAYCAP = 50.0
PAYREF = 192.0
HUBASE = 10.0
WAITBASE = 12.0
FORMCOST = 3.5
SPEEDCAP = 4.8
SPEEDREF = 12.0
VARREF = 4.0
WIDTHCAP = 3.6
WIDTHREF = 5.0
UNSEENSOFT = 0.75
PURPOSES = (0.0, 3.4, 8.1, 13.0, 18.4)
DEADPURPOSE = 0.25
HORIZONCOST = 0.35
RETENTION = 20
WALLSOFT = 8.0
UNKNOWNWALLSCALE = 0.70
OPPDECAY = 0.05
RISKBASE = 1.8
OPPRISK = 0.12
LATERISK = 3.4
UNKNOWNWALLRISK = 0.7
PREPBASE = 1.1
PREPWHITE = 0.30
PREPLINEAR = 0.65
PREPSQUARE = 0.20
PREPDISCARD = 0.15
PREPWIDTHREF = 4.0
PREPPORT = 0.45
PORTCAP = 2.2
PORTREF = 12.0
PORTPURPOSE = 0.55
ORDINARYBRIDGE = 0.30
ENVELOPEBLEND = 0.25
SINGLESCOPE = 0.75
COVREF = 3.0
LOCALCAP = 6.0
LOCALREF = 8.0
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
OPTIONCAP = 8.0
OPTIONREF = 2.0
OPTIONFLOOR = 2.0
EXITMASSREF = 6.0
EXITWIDTHREF = 3.0
EXITSTEPDECAY = 0.25
ANCHOROPTIONBASE = 0.14
ANCHOROPTIONSTEP = 0.10
ANCHORFALLBACKCOST = 0.45
ANCHORUNKNOWNCOST = 0.35
KNOWNPAYLINEAR = 0.45
PAYMASSREF = 8.0
EARNDISTANCE = 0.18
TARGETMASSREF = 2.0
NETUPGRADEWEIGHT = 1.40
NETUPWIDTHREF = 4.0
NETEXITWIDTHREF = 4.0
NETWAITFLOOR = 0.35
NETANCHORPRICE = 0.30
NETCARRY = 0.25
NETDISTANCE = 0.75


def pay_points(amount):
    """本家净积分除基础分后转排序点；保留较大支付的差别，不估计未来积分。"""
    return PAYCAP * amount / (PAYREF + abs(amount))


def inventory_support(slot, waiting):
    """返回排序库存、精确张数和非精确标记；公开容量包含他家暗牌。

    exact零关闭本码；保守正下界可支持排序，保守零及未知仍保留软支持。
    软支持不写回容量、胡资格或支付，更不除以墙余当摸牌概率。
    """
    capacity = waiting["unseen_capacities"][slot]
    evidence = waiting["unseen_evidence"][slot]
    if evidence == "exact" and capacity is not None:
        return float(capacity), capacity, 0
    if evidence == "conservative" and capacity is not None and capacity > 0:
        return float(capacity), 0, 1
    return UNSEENSOFT, 0, 1


def route_support(codes, waiting, codeindex, drawscale):
    """去重进张支持同时保留码宽与库存证据；仅返回有界排序摘要。"""
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
    """墙余与公开副露只折减条件先验；length不是未来可保证的本人摸牌次数。"""
    excess = 0.0 if room is None else max(0.0, float(length) - room)
    return drawscale * pressure / (1.0 + HORIZONCOST * excess)


def preparation_value(waiting, room, drawscale, pressure):
    """自然面子准备（NaturalSetPreparationFacts，不借白、不含将的自然面子缺张）。

    只赋予可转换结构的有界保留价值，D=0不增加白库存、不授爆头或胡资格。
    零白仍保留结构价值；现持多白增加结构可让白用于其他用途的先验。
    缺张、弃牌下界、公开相容改善码宽度共同折减，故不是一律不拆自然组。
    返回向量：自然缺张、自然弃牌下界、相容改善码宽度、真实白库存、准备点。
    """
    preparation = waiting["natural_preparation"]
    need = preparation["natural_draw_lower_bound"]
    discard = preparation["natural_discard_lower_bound"]
    width = waiting["natural_preparation_code_width"]
    whites = preparation["whites_held"]
    denominator = 1.0 + PREPLINEAR * float(need) + PREPSQUARE * float(need * need)
    denominator += PREPDISCARD * float(max(0, discard - 1))
    readiness = (PREPBASE + PREPWHITE * float(min(3, whites))) / denominator
    if need > 0:
        readiness *= 0.35 + 0.65 * float(width) / (PREPWIDTHREF + float(width))
    # 这里只衡量准备的迟近；没有把自然目标完成当成终末合法摸牌。
    scale = max(1, need + 1, discard)
    credit = readiness * purpose_scale(scale, room, drawscale, pressure)
    return need, discard, width, whites, credit


def actual_route(shanten, support, structural):
    """真实向听不改；L=max(0,向听)+1统一成型排序尺度，而非保证摸牌次数。

    structural是有界结构偏好，不能改写L、合法胡集合或官方支付。
    返回向量：真实向听、L、支持点、库存代理、相容码数、非精确码数、路线值。
    """
    length = max(0, shanten) + 1
    value = support[0] - FORMCOST * float(length - 1) + structural
    return shanten, length, support[0], support[1], support[2], support[4], value


def payment_summary(waiting, seat, base):
    """条件胡支付（RouteConditionalHuPayment，给定下一本人普通摸牌立即合法胡的支付）。

    同码两个抓打假设先合成下端加有界价差，单包络单独折减，库存只算一次。
    容量加权仅在已见证码内产生排序摘要；没有墙内概率、存活率或未来必达。
    None、空表、部分资格未知分别保留；财飘和杠链只消费规则已算好的结算。
    返回向量：状态、支付点摘要、已见证码数、精确容量和、最小/最大支付点、
    单包络码数、最小已见证番数、逐码支付摘要；状态0未分析/1已知空/2有支付/3部分未知。
    最后一项每码恰一组（精确公开容量、包络支付点、原包络行数），不计两次机会。
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
    """已见证支付信用（KnownPaymentCredit，把同源条件支付保留为有界排序差）。

    输入支付摘要已经合并同码互斥包络；容量只在已见证码内支持排序，不是墙内概率。
    普通小支付保留父代饱和尺度；较大支付允许线性的映射点份额超过第二次饱和。
    pay_points本身仍有50点上限，线性份额最大22.5点，未知和空表状态不改写。
    返回父饱和信用、容量折减后的线性信用、实际信用，单位均为排序点。
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


def joint_routes(waiting, standard, seven, preparation, codeindex, room, drawscale, pressure):
    """真实普通/七对出口、全部目标、自然准备和逐码组合共同生成有限远信用。

    远结构信用（EarnedStructureCredit，尚未兑现的保白先验先接受自身进张和完成距离折减）
    保留父代8点上限及同尺度目标质量；多保白本身不能绕过补弃和自然完成距离。
    普通型同时消费真实自然面子准备，七对只用自身目标缺口，不假借普通面子准备。
    相同补弃约束取最大来折减，不相加伪造额外必需动作，更不改规则向听或下界。
    指定前驱正缺张而相容推进为零时不获新信用；每码库存含他家暗牌，不当摸牌概率。
    返回最佳目标、去重组合、远信用见证；目标信用取最大，保留全部原图边与合法根。
    """
    # 34码本调用局部库存表只复用同一冻结等待态，不跨节点或跨调用缓存。
    stock = tuple([inventory_support(slot, waiting) for slot in range(len(waiting["unseen_capacities"]))])
    plans = []
    steps = float(standard[1] - 1)
    ordinaryweight = 1.0 / (1.0 + steps * steps)
    for code in waiting["standard_useful_codes"]:
        plans.append((codeindex[code], ordinaryweight))
    if seven is not None:
        steps = float(seven[1] - 1)
        pairweight = 1.0 / (1.0 + steps * steps)
        for code in waiting["seven_pairs_useful_codes"]:
            plans.append((codeindex[code], pairweight))
    exitroute = standard
    if seven is not None and seven[6] > exitroute[6]:
        exitroute = seven
    exitmass = max(0.0, exitroute[3])
    exitwidth = float(exitroute[4])
    exitgate = exitmass / (EXITMASSREF + exitmass) * exitwidth / (EXITWIDTHREF + exitwidth)
    exitgate /= 1.0 + EXITSTEPDECAY * float(exitroute[1] - 1)
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
        prior = 0.0
        share = 0.0
        predecessor = target["target_stage"] == "waiting_predecessor"
        if predecessor:
            prior = PURPOSES[retained] * purpose_scale(scale, room, drawscale, pressure)
            if need > 0 and width == 0:
                prior *= DEADPURPOSE
            if target["family"] == "standard":
                share = preparation[4] * float(retained) / float(1 + whites)
        elif target["family"] == "standard":
            share = 0.25 * preparation[4]
        support = drawscale * WIDTHCAP * float(width) / (WIDTHREF + float(width))
        value = support + prior + share - FORMCOST * float(scale - 1)
        if best is None or value > best[10]:
            best = (index, target["family"], retained, need, terminal, scale,
                    naturaldrop, whitedrop, width, prior, value)
        steps = float(scale - 1)
        weight = (1.0 + PORTPURPOSE * prior / (PURPOSES[2] + prior)) / (1.0 + steps * steps)
        targetmass = 0.0
        for code in target["conditional_need_improvement_codes"]:
            slot = codeindex[code]
            targetmass += stock[slot][0]
            plans.append((slot, weight))
        if predecessor and retained > 0 and retained <= whites and (need == 0 or width > 0):
            quality = max(0.0, value - OPTIONFLOOR)
            targetgate = 1.0
            if need > 0:
                if targetmass <= 0.0:
                    targetgate = 0.0
                else:
                    targetgate = 0.50 + 0.50 * targetmass / (TARGETMASSREF + targetmass)
            completion = preparation[0] if target["family"] == "standard" else need
            effort = float(max(scale - 1, completion))
            earned = 1.0 / (1.0 + EARNDISTANCE * effort)
            # 完成准备只约束信用成熟度，不把目标D=0或自然准备D=0当胡资格。
            # 非精确容量沿inventory_support保留软支持，未写成已知墙内牌或规则资格。
            credit = drawscale * OPTIONCAP * quality / (OPTIONREF + quality) * exitgate * targetgate * earned
            if credit > 0.0 and (option is None or credit > option[8]):
                option = (index, target["family"], retained, need, scale, width, quality, exitgate,
                          credit, targetmass, targetgate, effort, earned)
    prepweight = PREPPORT * (1.0 + preparation[4] / (1.0 + preparation[4]))
    prepweight /= 1.0 + float(preparation[0] * preparation[0])
    for code in waiting["natural_preparation"]["natural_need_improvement_codes"]:
        plans.append((codeindex[code], prepweight))
    knownhu = waiting["legal_hu_draw_codes"]
    if knownhu is not None:
        for code in knownhu:
            plans.append((codeindex[code], 1.0))
    # 合并只在排序组合内进行，原图的有序边、重复引用和所有条件原样保留。
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
    credit = drawscale * PORTCAP * mass / (PORTREF + mass) * diversity / (VARREF + diversity)
    return best, (mass, diversity, exact, codecount, uncertain, credit), option


def net_hu_offer(anchor, discount, risk, payment, main, portfolio, option):
    """净弃胡取舍（NetHuOffer，用逐码支付差与保听事实比较现在胡和继续）。

    直接升级只使用支付高于当前胡的牌码；其容量和码宽单独饱和。
    普通低番出口不增加升级码宽或升级容量，只能说明保听的普通出口仍在。
    同码互斥包络已经合成一次；多个自然目标不再次产生该码的支付信用。
    普通出口保全度折减等待费用，并给普通牌效与去重组合有限承接价值。
    直接支付与有弃胡价的远结构取大，不叠加；之后共同扣当前支付机会成本。
    所有支持、discount和risk都是排序假设，不是摸牌、存活或竞争概率。
    返回向量：净取舍点、信用来源、升级点、支付下降点、保听支持、升级码数、
    升级精确容量、升级支持、联合承接点、机会成本、等待费用、成型退步费用、
    远结构净信用、远结构弃胡价、远结构出口费、共用信用槽中的点数。
    分值单位为排序点；容量含他家暗牌，码数按规范牌码去重。
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
        # 低支付出口只保全它实际支持的当前价值，不借较高支付码的最大值。
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
        # 分母与码宽只消费真正升级的码；宽普通出口不能放大单码升级。
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
        # 远结构先付其自身成熟度的弃胡价格；不把局部下降费用再加一次。
        remoteprice = anchor * (ANCHOROPTIONBASE + ANCHOROPTIONSTEP * option[11])
        if payment[1] is None:
            fallback = ANCHORUNKNOWNCOST * anchor
        else:
            fallback = ANCHORFALLBACKCOST * max(0.0, anchor - max(0.0, payment[1]))
        remote = discount * option[8] - remoteprice - fallback
        if remote > offer:
            offer = remote
            channel = "earned_structure"
    # 承接只取普通出口与去重组合；局部支付和远目标信用均不在此重复计账。
    ordinarycore = max(0.0, main[6] + portfolio[5])
    carry = NETCARRY * discount * maintained * ordinarycore
    # 支付越大、出口越窄、墙越短，放弃确定支付的价格越高；保听也不能免掉风险。
    opportunity = NETANCHORPRICE * anchor * (1.0 - discount * maintained)
    waitfee = risk * (NETWAITFLOOR + (1.0 - NETWAITFLOOR) * (1.0 - maintained))
    distancefee = ANCHREADY * max(0.0, -main[6])
    net = offer + carry - opportunity - waitfee - distancefee
    return (net, channel, upgrade, downside, maintained, upgradewidth, upgrademass,
            upgradesupport, carry, opportunity, waitfee, distancefee, remote,
            remoteprice, fallback, offer)


def wait_value(waiting, codeindex, seat, base, room, drawscale, pressure, discount, risk,
               anchor, unknowncost):
    """以同一联合公式评价普通出口、条件支付、远保白结构和当前胡。

    未锚定等待保留父代普通/七对、自然准备、全部用途目标及去重组合的竞争。
    已见证支付与未兑现结构共用信用槽取大，不叠成免费保白奖励。
    当前可胡时用逐码净支付差及保听普通出口重新形成净弃胡取舍。
    自然准备与所有目标照常计算；空表/未分析仍可保留远结构取舍，不能改成零未来价值。
    吃碰、杠补、未知资格、墙余和公开副露均沿同一条件图，不以来源或牌形模板触发。
    """
    structure = waiting["structure"]
    preparation = preparation_value(waiting, room, drawscale, pressure)
    standard = actual_route(structure["standard_shanten"],
                            route_support(waiting["standard_useful_codes"], waiting, codeindex, drawscale),
                            preparation[4])
    seven = None
    main = standard
    family = "standard"
    if structure["seven_pairs_shanten"] is not None:
        length = max(0, structure["seven_pairs_shanten"]) + 1
        # 自然对子只给有界保留先验，不据实体四张自行授豪华七对或胡资格。
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
    natural, portfolio, option = joint_routes(waiting, standard, seven, preparation, codeindex, room, drawscale, pressure)
    joint = ordinary
    chosen = family
    if natural is not None and natural[10] > joint:
        joint = natural[10]
        chosen = "natural"
    bridge = ORDINARYBRIDGE * min(FORMCOST, max(0.0, joint - ordinary))
    joint = joint - bridge + portfolio[5]
    basejoint = joint
    if option is not None:
        # 同一普通出口与组合只记一次；条件支付与未兑现结构共用信用槽取大。
        optionjoint = main[6] + portfolio[5] + option[8]
        if optionjoint > joint:
            joint = optionjoint
            chosen = "retained_option"
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
    # 9为直接净升级信用；10为共用信用槽；13为完整净弃胡取舍，14为远结构见证。
    # 15—18保存远结构净信用、远弃胡价、远出口费、加远信用前联合值；19为局部支付信用。
    facts = (standard, seven, natural, preparation, portfolio, payment,
             ordinary, joint, chosen, gain, bias, local, qualcost, ready,
             option, optionnet, anchorprice, fallbackcost, basejoint, paymentcredit)
    return value, facts


def score_actions(view):
    """对冻结后序图全部节点评分，再按原合法根表完整返回有限评分点。

    choices才可择优合法续行；杠补及互斥条件使用全部边的下端与有界均值价差。
    共享节点只计算一次，边顺序和重复引用仍参与其父摘要；不挑最好未来牌。
    图机械缺口显式弃权，不用保底补成研究成功；无文件、网络、时钟或跨调用状态。
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
            # 均值是互斥条件的排序摘要，既非均匀摸牌假设也非期望积分。
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
            # 跳座价值仅在获裁决条件下；七对关闭和自然组改变已在各续行联合值体现。
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
                ("formula", "vip_qualifier_net_upgrade_m1/1"),
                ("context", (wall, opponents, round(discount, 3), round(risk, 3), anchor)),
                ("unknown", "opponent_hu_and_future_draw_reachability"),
                ("scope", "conditional_facts_not_probability_or_guaranteed_highfan"),
            ])
        entries.append({"action_key": action["action_key"], "score": value, "trace": trace})
    return {"status": "SCORED", "entries": entries}