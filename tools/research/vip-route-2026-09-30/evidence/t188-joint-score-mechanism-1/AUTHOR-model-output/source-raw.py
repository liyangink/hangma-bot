"""e2联合机制：物理进张统一增量预算、凸k保白用途与锚点平滑饱和双远端通道的联合排序。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1/AUTHOR-model-output'

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
FORMCOST = 3.4
SPEEDCAP = 4.8
SPEEDREF = 12.0
VARREF = 4.0
UNSEENSOFT = 0.75
PURPOSES = (0.0, 3.0, 7.0, 14.0, 28.0)
DEALERBOOST = 1.15
HORIZONCOST = 0.30
RETENTION = 20
WALLSOFT = 8.0
UNKNOWNWALLSCALE = 0.70
OPPDECAY = 0.05
RISKBASE = 1.8
OPPRISK = 0.12
LATERISK = 3.4
UNKNOWNWALLRISK = 0.7
MATURELINEAR = 0.32
RESCUEDECAY = 0.30
EXITFLOOR = 0.40
EXITMASSREF = 6.0
EXITWIDTHREF = 3.0
EXITSTEPDECAY = 0.25
TARGETGATEBASE = 0.50
TARGETMASSREF = 2.0
PAIRPRIORWEIGHT = 0.30
GAPSCALE = 0.55
STEPGROWTH = 0.35
PORTCAP = 2.4
PORTREF = 12.0
MULTIROLEBOOST = 0.30
MULTIROLECAP = 1.5
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
NETCARRY = 0.20
NETANCHORPRICE = 0.30
NETRISKFEE = 0.45
BRANCHGAP = 0.15
PREPBUDGET = 0.60
REMOTEDECAY = 0.30
RELEASEBASEWHITE = 1
UNREACHPENALTY = 0.22
SATETHRESH = 8.0
SATESOFT = 0.22
CHAINSTEP = 0.08
CHAINCAP = 3
WHITECASHMARKERS = ("爆头", "财飘")


def paypoints(amount):
    """本家净积分除基础分后的有界排序点；不是未来积分或摸牌概率。"""
    return PAYCAP * amount / (PAYREF + abs(amount))


def stockof(slot, waiting):
    """返回排序库存、精确张数与未知标记；公开容量含他家暗牌，不除以墙余。"""
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
            cell = stock[codeindex[code]]
            if cell[0] > 0.0:
                mass += cell[0]
                exact += cell[1]
                width += 1
                uncertain += cell[2]
    credit = (drawscale * SPEEDCAP * mass / (SPEEDREF + mass)
              * float(width) / (VARREF + float(width)))
    return credit, mass, width, exact, uncertain


def reachscale(burden, room, drawscale, pressure):
    """墙余可行性的平方折减；burden与room都不是保证摸牌次数或概率。"""
    excess = 0.0 if room is None else max(0.0, float(burden) - room)
    return drawscale * pressure / (1.0 + HORIZONCOST * excess + UNREACHPENALTY * excess * excess)


def chainladder(waiting):
    """公开链证据的有界阶梯；追加链仍需未来合法动作，只是排序先验。"""
    if waiting["baotou"]:
        return 1.0 + CHAINSTEP * float(min(CHAINCAP, waiting["chain_count"]))
    return 1.0


def prepvalue(waiting):
    """不借白、不含将的自然面子准备事实与单一负担成熟度系数。"""
    prep = waiting["natural_preparation"]
    need = prep["natural_draw_lower_bound"]
    discard = prep["natural_discard_lower_bound"]
    width = waiting["natural_preparation_code_width"]
    burden = float(max(need, discard))
    readiness = 1.0 / (1.0 + MATURELINEAR * burden)
    if need > 0 and width == 0:
        readiness = 0.0
    return need, discard, width, readiness


def actualroute(shanten, support, structural):
    """真实向听加出口支持的路线上限；L不是保证还需摸几次。"""
    length = max(0, shanten) + 1
    value = support[0] - FORMCOST * float(length - 1) + structural
    return shanten, length, support[0], support[1], support[2], support[4], value


def paysummary(waiting, seat, base):
    """条件胡支付的逐码包络摘要；同码两抓打假设互斥，只取下端加有界价差。

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


def routepair(waiting, standard, seven):
    """主路线按家族价值取高者，跟随路线只保留独占码资格与折价权重。

    主路线共享进张已在主路线值内一次计满；跟随路线的增量机会只来自
    不在主路线码集中的独占码，折价权重按价值差与向听步差平方表达，
    速度、准备与用途的真实差异保留在各自路线值内。
    """
    leadseven = seven is not None and seven[6] > standard[6]
    if leadseven:
        leader = seven
        leadcodes = waiting["seven_pairs_useful_codes"]
        followcodes = waiting["standard_useful_codes"]
        follower = standard
    else:
        leader = standard
        leadcodes = waiting["standard_useful_codes"]
        if seven is None:
            followcodes = None
            follower = None
        else:
            followcodes = waiting["seven_pairs_useful_codes"]
            follower = seven
    leadset = set()
    for code in leadcodes:
        leadset.add(code)
    followweight = 0.0
    if follower is not None:
        gap = max(0.0, leader[6] - follower[6])
        stepdiff = abs(leader[1] - follower[1])
        followweight = 1.0 / (1.0 + GAPSCALE * gap + STEPGROWTH * float(stepdiff * stepdiff))
    return leader, leadseven, followcodes, follower, followweight, leadset


def jointwait(waiting, standard, seven, leadset, followcodes, follower,
              followweight, ordinary, local, prep, codeindex, room, drawscale,
              pressure, stock, dealerboost, anchorwhite, satefactor, chainboost):
    """逐目标价值-额外代价选择、释放与追加白双远端通道及统一物理进张预算。

    每个目标只为超过其家族普通路线已付摸牌数的不同物理动作付一次线性
    成熟度；凸k先验乘公开链数阶梯。追加白通道对retained至少1通用放行：
    need大于0由targetgate承担自然推进，need为0的成熟目标改乘自然准备
    成熟度，成形手不因成熟失去追加白事实，拆散成形搭子只按readiness
    折价；已持k至少2白释放通道沿用锚点结算明细基线。统一预算把跟随
    独占码与自然准备码按物理码归并：同码取最高有效增量，多角色只加
    有界组合奖励并设上限；主路线码、已见证胡码与已选保白目标占用码
    先记入credited，同码跨路线跨通道不重复计价。
    """
    whites = waiting["structure"]["whites_held"]
    best = None
    release = None
    option = None
    whitemass = stock[codeindex["白"]][0]
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
            burden = max(need + terminal, naturaldrop + whitedrop)
            extra = max(0, burden - route[1])
            maturity = 1.0 / (1.0 + MATURELINEAR * float(extra))
            rescue = 1.0 / (1.0 + RESCUEDECAY * float(extra))
            exitmass = max(0.0, route[3])
            exitwidth = float(route[4])
            exitgate = exitmass / (EXITMASSREF + exitmass) * exitwidth / (EXITWIDTHREF + exitwidth)
            exitgate = exitgate / (1.0 + EXITSTEPDECAY * float(route[1] - 1))
            prior = 0.0
            if predecessor and retained > 0:
                prior = PURPOSES[retained] * dealerboost * chainboost
            exitfactor = EXITFLOOR + (1.0 - EXITFLOOR) * exitgate
            purposecredit = (prior * reachscale(burden, room, drawscale, pressure)
                             * targetgate * maturity * exitfactor)
            rescued = local * rescue
            prospective = rescued + purposecredit
            value = route[6] + prospective
            if best is None or value > best[10]:
                best = (index, target["family"], retained, need, terminal, burden,
                        naturaldrop, whitedrop, width, prospective, value)
            gain = max(0.0, value - ordinary)
            if predecessor and retained > 0 and retained <= whites and gain > 0.0:
                if retained > 1:
                    releasegap = PURPOSES[retained] - anchorwhite
                    releasepending = float(burden)
                    releasefactor = (1.0 / (1.0 + REMOTEDECAY * releasepending)
                                     * reachscale(releasepending, room, drawscale, pressure))
                    releasecredit = (releasegap * dealerboost * chainboost * targetgate
                                     * exitfactor * releasefactor * satefactor)
                    if releasecredit > 0.0 and (release is None or releasecredit > release[0]):
                        release = (releasecredit, float(extra), releasegap,
                                   releasepending, float(gain), float(retained))
                naturalready = 1.0 if need > 0 else prep[3]
                upperk = retained + 1
                if upperk > 4:
                    upperk = 4
                purposegap = float(PURPOSES[upperk] - PURPOSES[retained])
                whitepending = float(need + terminal + whitedrop + 1)
                whitegate = 0.0
                if whitemass > 0.0:
                    whitegate = (TARGETGATEBASE + (1.0 - TARGETGATEBASE)
                                 * whitemass / (TARGETMASSREF + whitemass))
                whitefactor = (1.0 / (1.0 + REMOTEDECAY * whitepending)
                               * reachscale(whitepending, room, drawscale, pressure))
                whitecredit = (purposegap * dealerboost * chainboost * whitegate * targetgate
                               * exitfactor * whitefactor * satefactor * naturalready)
                if whitecredit > 0.0 and (option is None or whitecredit > option[0]):
                    option = (whitecredit, float(extra), purposegap,
                              whitepending, float(gain), float(retained), whitemass)
    credited = set()
    for code in leadset:
        credited.add(code)
    knownhu = waiting["legal_hu_draw_codes"]
    if knownhu is not None:
        for code in knownhu:
            credited.add(code)
    primaryvalue = ordinary
    preparationoccupied = 0
    if best is not None and best[10] > ordinary:
        primaryvalue = best[10]
        selected = waiting["structure"]["targets"][best[0]]
        if selected["family"] == "standard":
            selectedcodes = waiting["standard_useful_codes"]
        else:
            selectedcodes = waiting["seven_pairs_useful_codes"]
        for code in selectedcodes:
            credited.add(code)
        for code in selected["conditional_need_improvement_codes"]:
            credited.add(code)
        if (selected["family"] == "standard" and selected["target_stage"] == "waiting_predecessor"
                and selected["retained_whites"] > 0):
            preparationoccupied = 1
            for code in waiting["natural_preparation"]["natural_need_improvement_codes"]:
                credited.add(code)
    plans = []
    followcount = 0
    if follower is not None and followweight > 0.0:
        for code in followcodes:
            if code not in credited:
                slot = codeindex[code]
                if stock[slot][0] > 0.0:
                    plans.append((slot, followweight))
                    followcount += 1
    prepcount = 0
    if preparationoccupied == 0 and prep[0] > 0 and prep[2] > 0:
        preplength = max(standard[1], prep[0] + 1, prep[1])
        excess = 0.0 if room is None else max(0.0, float(preplength) - room)
        gapvalue = max(0.0, primaryvalue - (standard[6] + local))
        prepweight = PREPBUDGET * prep[3] / ((1.0 + BRANCHGAP * gapvalue)
                                             * (1.0 + HORIZONCOST * excess
                                                + UNREACHPENALTY * excess * excess))
        if prepweight > 0.0:
            for code in waiting["natural_preparation"]["natural_need_improvement_codes"]:
                slot = codeindex[code]
                if code not in credited and stock[slot][0] > 0.0:
                    plans.append((slot, prepweight))
                    prepcount += 1
    combined = []
    currentslot = None
    slotsum = 0.0
    slotmax = 0.0
    for plan in sorted(plans):
        if plan[0] != currentslot:
            if currentslot is not None:
                combined.append((currentslot, slotsum, slotmax))
            currentslot = plan[0]
            slotsum = plan[1]
            slotmax = plan[1]
        else:
            slotsum += plan[1]
            if plan[1] > slotmax:
                slotmax = plan[1]
    if currentslot is not None:
        combined.append((currentslot, slotsum, slotmax))
    mass = 0.0
    diversity = 0.0
    exact = 0
    codecount = 0
    uncertain = 0
    multirole = 0
    for entry in combined:
        cell = stock[entry[0]]
        if cell[0] > 0.0:
            slotvalue = entry[2]
            if entry[1] > entry[2]:
                slotvalue = min(entry[2] * MULTIROLECAP,
                                entry[2] + MULTIROLEBOOST * (entry[1] - entry[2]))
                multirole += 1
            mass += slotvalue * cell[0]
            diversity += slotvalue
            exact += cell[1]
            codecount += 1
            uncertain += cell[2]
    totalcredit = (drawscale * pressure * PORTCAP * mass / (PORTREF + mass)
                   * diversity / (VARREF + diversity))
    if option is not None and option[4] <= totalcredit:
        option = None
    if release is not None and release[4] <= totalcredit:
        release = None
    portfolio = (mass, diversity, float(exact), float(codecount), float(uncertain),
                 totalcredit, float(len(credited)), float(followcount),
                 float(prepcount), float(multirole))
    return best, portfolio, release, option


def huoffer(anchor, discount, risk, payment, leader, totalcredit, release, option):
    """当前胡与继续等待的净比较；等待暴露只按一个合并费计一次。

    直接升级按同码包络差计算，保留便宜真实升档与失胡避免反例；远端
    拆成已持白释放与追加白两条互斥代理通道取大，锚价与fallback只对
    胜出通道计一次；carry按主路线剩余向听步数折价。全部是排序点，
    不是期望积分或存活率；未分析支付按未知成本处理不当零，他家先胡、
    未来资格与抓打仍显式未知。
    """
    mass = payment[3]
    width = float(payment[2])
    exitgate = mass / (PAYMASSREF + mass) * width / (NETEXITWIDTHREF + width)
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
    maintained = exitgate * floorfraction
    upgradesupport = (upgrademass / (PAYMASSREF + upgrademass)
                      * float(upgradewidth) / (NETUPWIDTHREF + float(upgradewidth)))
    upgrade = 0.0
    if upgrademass > 0.0:
        upgrade = (NETUPGRADEWEIGHT * discount * upgradeamount / upgrademass
                   * upgradesupport)
    downside = discount * downsideamount / (PAYMASSREF + mass)
    direct = upgrade - downside
    remote = 0.0
    remoteprice = 0.0
    fallback = 0.0
    offervalue = direct
    channel = "direct_upgrade"
    releasecredit = 0.0
    whitecredit = 0.0
    if release is not None or option is not None:
        if payment[1] is None:
            fallback = ANCHORUNKNOWNCOST * anchor
        else:
            fallback = ANCHORFALLBACKCOST * max(0.0, anchor - max(0.0, payment[1]))
        winnervalue = None
        winnerprice = 0.0
        winnerchannel = ""
        if release is not None and release[0] > 0.0:
            releasecredit = release[0]
            winnerprice = anchor * (ANCHOROPTIONBASE + ANCHOROPTIONSTEP * release[1])
            winnervalue = releasecredit - winnerprice - fallback
            winnerchannel = "held_white_release"
        if option is not None and option[0] > 0.0:
            whitecredit = option[0]
            whiteprice = anchor * (ANCHOROPTIONBASE + ANCHOROPTIONSTEP * option[1])
            whitevalue = whitecredit - whiteprice - fallback
            if winnervalue is None or whitevalue > winnervalue:
                winnervalue = whitevalue
                winnerprice = whiteprice
                winnerchannel = "new_white_gap"
        if winnervalue is not None:
            remote = winnervalue
            remoteprice = winnerprice
            if remote > offervalue:
                offervalue = remote
                channel = winnerchannel
    ordinarycore = max(0.0, leader[6] + totalcredit)
    remaining = float(max(0, leader[1] - 1))
    exitneed = remaining / (1.0 + remaining)
    carry = NETCARRY * discount * maintained * ordinarycore * exitneed
    exposure = (NETANCHORPRICE * anchor + NETRISKFEE * risk) * (1.0 - discount * maintained)
    net = offervalue + carry - exposure
    return (net, channel, upgrade, downside, maintained, carry, exposure,
            remote, remoteprice, fallback, offervalue, releasecredit, whitecredit)


def waitvalue(waiting, codeindex, seat, base, room, drawscale, pressure, discount,
              risk, anchor, anchorwhite, unknowncost, dealerboost):
    """统一物理进张预算、逐目标凸k用途与锚点平滑饱和下评价普通出口、七对、保白用途与当前胡。"""
    structure = waiting["structure"]
    stock = []
    for slot in range(len(waiting["unseen_capacities"])):
        stock.append(stockof(slot, waiting))
    prep = prepvalue(waiting)
    standard = actualroute(structure["standard_shanten"],
                           routesupport(waiting["standard_useful_codes"], codeindex, drawscale, stock),
                           0.0)
    seven = None
    if structure["seven_pairs_shanten"] is not None:
        sevenlength = max(0, structure["seven_pairs_shanten"]) + 1
        pairprior = (PAIRPRIORWEIGHT
                     * float(min(2, max(0, structure["natural_pair_count"] - 4)))
                     / float(sevenlength))
        seven = actualroute(structure["seven_pairs_shanten"],
                            routesupport(waiting["seven_pairs_useful_codes"], codeindex, drawscale, stock),
                            pairprior * drawscale * pressure)
    leader, leadseven, followcodes, follower, followweight, leadset = routepair(
        waiting, standard, seven)
    family = "seven_pairs" if leadseven else "standard"
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
    ordinary = leader[6] + local
    chainboost = chainladder(waiting)
    satefactor = 1.0
    if anchor is not None:
        satefactor = 1.0 / (1.0 + SATESOFT * max(0.0, anchor - SATETHRESH))
    best, portfolio, release, option = jointwait(waiting, standard, seven, leadset,
                                                 followcodes, follower, followweight,
                                                 ordinary, local, prep, codeindex, room,
                                                 drawscale, pressure, stock, dealerboost,
                                                 anchorwhite, satefactor, chainboost)
    joint = ordinary
    chosen = family
    if best is not None and best[10] > joint:
        joint = best[10]
        chosen = "completion_budget"
    joint += portfolio[5]
    if anchor is not None:
        ready = huoffer(anchor, discount, risk, payment, leader, portfolio[5], release, option)
        value = HUBASE + anchor + ready[0] - qualcost - unknowncost
    else:
        ready = None
        value = WAITBASE + joint - qualcost - unknowncost - UNANCHOREXPOSURE * risk
    facts = (standard, seven, best, prep, portfolio, payment, ordinary, joint, chosen,
             local, qualcost, ready, release, option, followweight, chainboost)
    return value, facts


def score_actions(view):
    """对全部冻结后序节点一次共享计算，并给每个合法根恰一条有限评分。

    统一物理进张预算、逐目标价值-额外代价与双远端通道全部在wait节点
    一次算好；choices才在合法续行中择优；replacement与condition消费
    全部相容边的下端加有界价差，不挑最好补牌；墙余不高于保留区时
    drawscale为0硬性关闭未来通道；机械缺口显式弃权。庄家身份只作
    公开先验乘子。无文件、网络、时钟、随机或跨调用缓存。
    """
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
    anchorwhite = 0.0
    for action in view["actions"]:
        node = nodes[indexes[action["node_key"]]]
        if node["kind"] == "hu":
            amount = float(node["settlement"]["score_delta"][seat]) / base
            point = paypoints(amount)
            if anchor is None or point > anchor:
                anchor = point
                anchorwhite = 0.0
                for detail in node["settlement"]["details"]:
                    for marker in WHITECASHMARKERS:
                        if detail == marker:
                            anchorwhite = PURPOSES[RELEASEBASEWHITE]
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
                                     pressure, discount, risk, anchor, anchorwhite, unknowncost,
                                     dealerboost)
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
                pairs.append(("target", (best[0], best[1], best[2], best[3], best[5],
                                         round(best[9], 3), round(best[10], 3))))
            ready = facts[11]
            if ready is None:
                pairs.append(("offer", None))
            else:
                pairs.append(("offer", (round(ready[0], 3), ready[1], round(ready[2], 3),
                                        round(ready[3], 3), round(ready[4], 3),
                                        round(ready[11], 3), round(ready[12], 3))))
            pairs.append(("prep", (facts[3][0], facts[3][1], facts[3][2], round(facts[3][3], 3))))
        if not entries:
            pairs.append(("unit", "heuristic_rank_points"))
            pairs.append(("formula", "vip_unified_code_budget_e2/1"))
            if anchor is None:
                anchorvalue = None
                anchorwhitevalue = None
            else:
                anchorvalue = round(anchor, 3)
                anchorwhitevalue = round(anchorwhite, 3)
            pairs.append(("context", (wall, opponents, round(dealerboost, 3),
                                      round(discount, 3), round(risk, 3), anchorvalue,
                                      anchorwhitevalue)))
            pairs.append(("unknown", "opponent_hu_and_future_draw_reachability"))
            pairs.append(("scope", "conditional_facts_not_probability_or_guaranteed_highfan"))
        entries.append({"action_key": action["action_key"], "score": value, "trace": dict(pairs)})
    return {"status": "SCORED", "entries": entries}