"""冻结视图/3的联合启发式；评分点不是摸牌概率、规则资格或未来积分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t48-v3-natural-highfan-joint-author-1/S01-research-capacity'

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
SMALLREADY = 0.40
ANCHREADY = 0.18
NATURALBIASCAP = 1.4
GAINREF = 4.0
UNANCHOREXPOSURE = 0.15
READYGAINCAP = 5.2
READYWAITFEE = 0.24
READYSUPPORTREF = 1.0
CONDITIONBLEND = 0.20
CONDITIONCAP = 1.0
REPLACEMENTBLEND = 0.40
REPLACEMENTCAP = 2.3
CLAIMCOST = 0.25
SKIPVALUE = 0.10
GANGCOST = 0.12


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
    单包络码数、最小已见证番数；状态0未分析/1已知空/2有支付/3部分未知。
    """
    payments = waiting["normal_draw_hu_payments"]
    if payments is None:
        return 0, None, 0, 0.0, None, None, 0, None
    partial = len(waiting["qualification_unknown_codes"]) > 0
    if not payments:
        return 3 if partial else 1, 0.0, 0, 0.0, None, None, 0, None
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
    for capacity, lower, upper, rows in groups:
        if rows == 1:
            envelope = SINGLESCOPE * lower
            singles += 1
        else:
            envelope = lower + ENVELOPEBLEND * (upper - lower)
        total += capacity * envelope
        mass += capacity
    return 3 if partial else 2, total / mass, len(groups), mass, minimum, maximum, singles, minimumfan


def joint_routes(waiting, standard, seven, preparation, codeindex, room, drawscale, pressure):
    """全部普通、七对、保白目标及自然准备共同形成逐码路线组合。

    指定目标r=max(真实L,D+终末摸,自然弃+白弃)，不重复扣同一次补弃。
    所有目标均计算后才能取最高路线值；较高保白用途递增先验只是排序偏好。
    多路线共有码取最大权重，按规范码排序合并，不当成多个独立摸牌机会。
    D=0且改善集空时不虚构终末码；真正合法胡码只来自原支付/资格事实。
    返回最佳自然目标向量及组合向量，均不回写图、合法动作或规则结果。
    """
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
    best = None
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
        if target["target_stage"] == "waiting_predecessor":
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
        for code in target["conditional_need_improvement_codes"]:
            plans.append((codeindex[code], weight))
    prepweight = PREPPORT * (1.0 + preparation[4] / (1.0 + preparation[4]))
    prepweight /= 1.0 + float(preparation[0] * preparation[0])
    for code in waiting["natural_preparation"]["natural_need_improvement_codes"]:
        plans.append((codeindex[code], prepweight))
    knownhu = waiting["legal_hu_draw_codes"]
    if knownhu is not None:
        for code in knownhu:
            plans.append((codeindex[code], 1.0))
    # 合并只用于本评分组合；原图边和每条条件均未删除或去重。
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
        inventory, precise, unknown = inventory_support(slot, waiting)
        if inventory > 0.0:
            mass += weight * inventory
            diversity += weight
            exact += precise
            codecount += 1
            uncertain += unknown
    credit = drawscale * PORTCAP * mass / (PORTREF + mass) * diversity / (VARREF + diversity)
    return best, (mass, diversity, exact, codecount, uncertain, credit)


def maintained_ready(waiting, anchor, anchorfan, discount, pressure, risk, payment):
    """保持听牌（MaintainedReadyOffer，用完整已见证更高支付与当前胡联合比较）。

    要求真实听牌、已分析且无未知资格、每码双包络、最低支付点和番数均更高。
    全相容码类覆盖及精确库存的饱和核只是保守排序折减，不表示再摸概率。
    自然准备或多白先验不能单独买到放弃当前胡；一个最高支付码也不够。
    返回相对当前胡净取舍点、折减、已见证码类覆盖；无支持时返回None。
    """
    structure = waiting["structure"]
    if structure["standard_shanten"] != 0 and structure["seven_pairs_shanten"] != 0:
        return None
    if payment[0] != 2 or payment[6] != 0 or payment[4] is None:
        return None
    if payment[4] <= anchor or payment[7] is None or payment[7] <= anchorfan:
        return None
    possible = 0
    for capacity, evidence in zip(waiting["unseen_capacities"], waiting["unseen_evidence"]):
        if evidence != "exact" or capacity is None or capacity > 0:
            possible += 1
    if possible == 0 or payment[2] == 0 or payment[3] <= 0.0:
        return None
    coverage = min(1.0, float(payment[2]) / float(possible))
    attenuation = discount * coverage * payment[3] / (READYSUPPORTREF + payment[3])
    upgrade = min(READYGAINCAP, max(0.0, payment[1] - anchor))
    fee = READYWAITFEE * risk / pressure
    benefit = attenuation * upgrade - (1.0 - attenuation) * anchor - fee
    return benefit, attenuation, coverage


def wait_value(waiting, codeindex, seat, base, room, drawscale, pressure, discount, risk,
               anchor, anchorfan, readyenabled, unknowncost):
    """一套共同取舍用于所有真实等待叶；未知补牌叶保留真实补牌前态及明确代价。

    无当前胡时真实普通/七对、准备、保白条件和已见证支付共同选路。
    有当前胡时只让已见证支付差支持延后，结构差作为小幅取舍并支付暴露代价。
    未知资格不填已合法或零支付；输出事实向量只为解释，不改变动作集合。
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
        # 自然对子只是有界牌型保留先验；不据四张自然牌自行授豪华或胡资格。
        pairprior = 0.30 * float(min(2, max(0, structure["natural_pair_count"] - 4))) / float(length)
        seven = actual_route(structure["seven_pairs_shanten"],
                             route_support(waiting["seven_pairs_useful_codes"], waiting, codeindex, drawscale),
                             pairprior * drawscale * pressure)
        if seven[6] > main[6]:
            main = seven
            family = "seven_pairs"
    natural, portfolio = joint_routes(waiting, standard, seven, preparation, codeindex, room, drawscale, pressure)
    payment = payment_summary(waiting, seat, base)
    known = payment[2]
    unknown = len(waiting["qualification_unknown_codes"])
    coverage = float(known) / (COVREF + float(known))
    qualcost = QUALUNANALYSED if payment[0] == 0 else QUALUNKNOWN * float(unknown) / float(1 + known + unknown)
    local = 0.0
    if payment[1] is not None and payment[1] > 0.0:
        local = LOCALCAP * payment[1] / (LOCALREF + payment[1]) * coverage * drawscale * pressure
    ordinary = main[6] + local
    joint = ordinary
    chosen = family
    if natural is not None and natural[10] > joint:
        joint = natural[10]
        chosen = "natural"
    # 普通出口变窄不释放额外信用；桥接函数对O及J均单调。
    bridge = ORDINARYBRIDGE * min(FORMCOST, max(0.0, joint - ordinary))
    joint = joint - bridge + portfolio[5]
    gain = 0.0
    bias = 0.0
    ready = None
    if anchor is not None:
        if payment[1] is not None and payment[1] > anchor:
            gain = (payment[1] - anchor) * coverage
        if gain > 0.0:
            strength = preparation[4]
            if natural is not None:
                strength += max(0.0, natural[10])
            bias = min(NATURALBIASCAP, strength) * gain / (GAINREF + gain)
        value = HUBASE + anchor + discount * gain + bias - risk - qualcost - unknowncost
        value += min(SMALLREADY, max(0.0, main[6])) - ANCHREADY * max(0.0, -main[6])
        if readyenabled and unknowncost == 0.0:
            ready = maintained_ready(waiting, anchor, anchorfan, discount, pressure, risk, payment)
            if ready is not None:
                value = max(value, HUBASE + anchor + ready[0])
    else:
        value = WAITBASE + joint - qualcost - unknowncost - UNANCHOREXPOSURE * risk
    facts = (standard, seven, natural, preparation, portfolio, payment,
             ordinary, joint, chosen, gain, bias, local, qualcost, ready)
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
        readyenabled = False
    else:
        margin = max(0.0, float(wall) - float(RETENTION))
        room = max(1.0, margin / 4.0)
        drawscale = 1.0 if margin > 0.0 else 0.0
        discount = drawscale * pressure * (0.30 + 0.70 * margin / (WALLSOFT + margin))
        risk = RISKBASE + OPPRISK * float(opponents) + LATERISK * WALLSOFT / (WALLSOFT + margin)
        readyenabled = margin > WALLSOFT
    codeindex = {code: index for index, code in enumerate(view["tile_order"])}
    nodes = view["nodes"]
    indexes = {node["node_key"]: index for index, node in enumerate(nodes)}
    anchor = None
    anchorfan = None
    for action in view["actions"]:
        node = nodes[indexes[action["node_key"]]]
        if node["kind"] == "hu":
            amount = float(node["settlement"]["score_delta"][seat]) / base
            point = pay_points(amount)
            if anchor is None or point > anchor:
                anchor = point
                anchorfan = node["settlement"]["fan"]
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
                                      pressure, discount, risk, anchor, anchorfan, readyenabled, unknowncost)
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
                ("ready", None if facts[13] is None else tuple([round(part, 3) for part in facts[13]])),
            ])
        elif facts is not None and actioncount <= 40:
            trace = dict(list(trace.items()) + [
                ("prep", (facts[3][0], facts[3][2], round(facts[3][4], 3))),
                ("joint", (round(facts[6], 3), round(facts[7], 3), facts[8])),
                ("pay", (facts[5][0], facts[5][2], facts[5][6])),
            ])
        if not entries:
            trace = dict(list(trace.items()) + [
                ("unit", "heuristic_rank_points"),
                ("formula", "vip_natural_preparation_joint_i1/1"),
                ("context", (wall, opponents, round(discount, 3), round(risk, 3), anchor)),
                ("unknown", "opponent_hu_and_future_draw_reachability"),
                ("scope", "conditional_facts_not_probability_or_guaranteed_highfan"),
            ])
        entries.append({"action_key": action["action_key"], "score": value, "trace": trace})
    return {"status": "SCORED", "entries": entries}
