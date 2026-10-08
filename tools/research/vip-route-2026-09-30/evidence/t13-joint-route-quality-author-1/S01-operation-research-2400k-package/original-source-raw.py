"""联合排名只使用冻结 View/2；评分点不是概率、番数或未来积分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/S01-operation-research-2400k-package'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

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
SELFMIN = 0.25
NATURALINTEGRITYCAP = 1.2


def pay_points(amount):
    """本家净积分除基础分后转排序点；晚饱和保留高支付差，非未来积分估计。"""
    return PAYCAP * amount / (PAYREF + abs(amount))


def route_support(codes, waiting, codeindex, drawscale, shaped):
    """一组相容码只计一次公开容量，返回支持点及原库存事实。

    返回向量为支持点、精确公开张数、相容码数、非精确码数、形状增量。
    公开容量包含他家暗牌。非精确零和 None 只用排序代理，不补造实体张数。
    形状只统计同花色缺一自然码的不同顺子伙伴；一次摸牌只能选一副。
    不重复累加模板库存，也不判断合法动作、胡资格或完整面子分解。
    """
    capacities = waiting["unseen_capacities"]
    evidence = waiting["unseen_evidence"]
    counts = waiting["structure"]["natural_counts33"]
    exact = 0
    variety = 0
    uncertain = 0
    excess = 0.0
    for code in codes:
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
    inventory = float(exact) + UNSEENSOFT * float(uncertain)
    weighted = inventory + excess
    diversity = float(variety) / (VARREF + float(variety))
    credit = drawscale * SPEEDCAP * weighted / (SPEEDREF + weighted) * diversity
    plain = drawscale * SPEEDCAP * inventory / (SPEEDREF + inventory) * diversity
    return credit, exact, variety, uncertain, credit - plain


def actual_route(shanten, support, costs):
    """真实向听不改；L=max(0,向听)+1 只是共同成型排序尺度。

    返回向量：原向听、L、精确公开张数、相容码数、非精确码数、
    支持点、形状增量、普通路线值。L 不保证本人还能摸这么多次。
    """
    length = max(0, shanten) + 1
    value = support[0] - costs[length]
    return shanten, length, support[1], support[2], support[3], support[0], support[4], value


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


def natural_resource_profile(waiting):
    """把自然伙伴按实体容量分摊，返回局部形状代理，不返回分解见证。

    33位均为本家依法可见的自然牌计数。先封存现有三张局部块；重叠
    模板按同码实体负载分摊，封存总量不超过实持量。剩余伙伴再按两张
    片段分摊；相同片段的两个出口只用一份伙伴，同一摸码最终至多一份。
    分数份额是保守资源账，不是分解、胡资格、独立成功率或未来续行动作。
    七对直接采用权威自然对子数，奇数余张仅作补自然对的局部支持。
    返回：普通型33码支持份额、七对33码支持份额、两家族封存自然张数、
    普通型两张片段份额和。局部表固定33项，片段表至多78项，无搜索。
    """
    structure = waiting["structure"]
    counts = structure["natural_counts33"]
    capacities = waiting["unseen_capacities"]
    evidence = waiting["unseen_evidence"]
    live = tuple([evidence[slot] != "exact" or capacities[slot] is None or capacities[slot] > 0
                  for slot in range(33)])
    sequences = tuple([min(counts[slot], counts[slot + 1], counts[slot + 2])
                       if slot < 27 and slot % 9 <= 6 else 0 for slot in range(33)])
    loads = []
    for slot in range(33):
        load = 3 if counts[slot] >= 3 else 0
        if slot < 27:
            load += sequences[slot]
            if slot % 9 >= 1:
                load += sequences[slot - 1]
            if slot % 9 >= 2:
                load += sequences[slot - 2]
        loads.append(max(1, load))
    triplets = tuple([min(1.0, float(counts[slot]) / float(loads[slot]))
                      if counts[slot] >= 3 else 0.0 for slot in range(33)])
    locked_sequences = tuple([
        float(sequences[slot]) * min(1.0, float(counts[slot]) / float(loads[slot]),
                                    float(counts[slot + 1]) / float(loads[slot + 1]),
                                    float(counts[slot + 2]) / float(loads[slot + 2]))
        if sequences[slot] > 0 else 0.0 for slot in range(33)
    ])
    residual = []
    for slot in range(33):
        used = 3.0 * triplets[slot]
        if slot < 27:
            used += locked_sequences[slot]
            if slot % 9 >= 1:
                used += locked_sequences[slot - 1]
            if slot % 9 >= 2:
                used += locked_sequences[slot - 2]
        remainder = max(0.0, float(counts[slot]) - used)
        # 浮点分摊产生的舍入余量不应凭空生成一条新的伙伴争用边。
        residual.append(0.0 if remainder < 0.000000001 else remainder)
    edges = []
    for slot in range(33):
        if residual[slot] > 0.0:
            if counts[slot] >= 2 and live[slot]:
                edges.append((slot, slot, slot, -1))
            if slot < 27:
                pos = slot % 9
                if pos <= 7 and residual[slot + 1] > 0.0:
                    left = slot - 1 if pos >= 1 else -1
                    right = slot + 2 if pos <= 6 else -1
                    if (left >= 0 and live[left]) or (right >= 0 and live[right]):
                        edges.append((slot, slot + 1, left, right))
                if pos <= 6 and residual[slot + 2] > 0.0 and live[slot + 1]:
                    edges.append((slot, slot + 2, slot + 1, -1))
    present = {(edge[0], edge[1]): True for edge in edges}
    demands = []
    for slot in range(33):
        demand = 2 if (slot, slot) in present else 0
        for offset in (-2, -1, 1, 2):
            other = slot + offset
            if (min(slot, other), max(slot, other)) in present:
                demand += 1
        demands.append(max(1, demand))
    weights = {(edge[0], edge[1]): min(1.0, residual[edge[0]] / float(demands[edge[0]]),
                                       residual[edge[1]] / float(demands[edge[1]]))
               for edge in edges}
    support = []
    for slot in range(33):
        strength = weights.get((slot, slot), 0.0)
        if slot < 27:
            pos = slot % 9
            if pos >= 2:
                strength += weights.get((slot - 2, slot - 1), 0.0)
            if pos >= 1 and pos <= 7:
                strength += weights.get((slot - 1, slot + 1), 0.0)
            if pos <= 6:
                strength += weights.get((slot + 1, slot + 2), 0.0)
        # 同码多个局部块是替代用途；不能把一张摸牌当成同时完成几个块。
        support.append(min(1.0, strength))
    seven_support = tuple([1.0 if count % 2 == 1 else 0.0 for count in counts])
    locked_standard = 3.0 * (sum(triplets) + sum(locked_sequences))
    locked_seven = 2.0 * float(structure["natural_pair_count"])
    return tuple(support), seven_support, locked_standard, locked_seven, sum(weights.values())


def resource_natural_offer(waiting, standard, seven, costs, widths, purposes, codeindex):
    """无当前胡时，以同目标自成支持替换裸码宽度，再与普通出口联合择优。

    不增加备用牌型信用。每个目标仍独立保留父代保白先验与共同成型成本，
    全部目标最后取最大项。只有该目标原有推进码才参与自然支持摘要。
    精确公开张数按码一次计，含他家暗牌；非精确证据沿用0.8排序代理，
    不补实体张数、不除墙余。自成份额只调节宽度，不扩大规则推进集合。
    裸宽度保留四分之一，避免把缺乏局部二张伙伴误写成目标不可能推进。
    已有自然块再给至多1.2点评分保护；先按目标可匹配自然张数封顶，并
    按自然弃下界作保守资产扣减。没有见证证明被封存块属于该最优目标。
    因而此保护仍是可证伪代理，不声称高番、保白或后续动作已经可实现。
    返回与父相同14字段最佳目标，以及平铺解释：目标号、原宽度点、
    支持份额、调整宽度点、资产保护点、两家族封存张数、片段份额和、
    支持容量代理、全部相容容量代理、非精确码数。
    """
    profile = natural_resource_profile(waiting)
    capacities = waiting["unseen_capacities"]
    evidence = waiting["unseen_evidence"]
    best = None
    explanation = None
    for index, target in enumerate(waiting["structure"]["targets"]):
        family = target["family"]
        length = standard[1] if family == "standard" else seven[1]
        support = profile[0] if family == "standard" else profile[1]
        locked = profile[2] if family == "standard" else profile[3]
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
                quality = quality * DEADPURPOSE
        totalmass = 0.0
        backedmass = 0.0
        uncertain = 0
        for code in target["conditional_need_improvement_codes"]:
            slot = codeindex[code]
            cap = capacities[slot]
            if evidence[slot] == "exact" and cap is not None:
                inventory = float(max(0, cap))
            else:
                inventory = UNSEENSOFT
                uncertain += 1
            totalmass += inventory
            backedmass += inventory * support[slot]
        backing = backedmass / totalmass if totalmass > 0.0 else 0.0
        widthcredit = widths[width] * (SELFMIN + (1.0 - SELFMIN) * backing)
        matched = max(0, target["target_natural_size"] - need)
        # 仅保护不超过已有匹配规模、且扣除必需自然弃张的资产量；不授见证。
        heldcover = max(0.0, min(locked, float(matched)) - float(naturaldrop))
        intact = heldcover / float(max(1, matched))
        preservation = NATURALINTEGRITYCAP * purposes[scale] * intact
        credit = widthcredit + preservation
        value = credit + quality - costs[scale]
        if best is None or value > best[13]:
            best = (index, family, target["target_stage"], retained, need, terminal,
                    scale, naturaldrop, whitedrop, width, quality, costs[scale], credit, value)
            explanation = (index, widths[width], backing, widthcredit, preservation,
                           profile[2], profile[3], profile[4], backedmass, totalmass, uncertain)
    return best, explanation


def wait_value(waiting, codeindex, seat, base, costs, widths, purposes,
               drawscale, pressure, discount, risk, anchor, unknowncost):
    """普通出口、全部自然用途和当前胡取舍共同评分；未知资格不填虚构支付。

    当前胡模式按已知局部条件支付差减暴露代价比较，并让真实保留路线给出
    小幅有界取舍。自然先验不能单独买到放弃当前胡，升级见证也不保证继续。
    暴露折减与代价来自公开副露、墙余，是未校准排序代理，不是他家先胡率。
    返回的事实元组只供根解释引用；规则、动作集合和条件节点均不变。
    """
    structure = waiting["structure"]
    shaped = drawscale > 0.0 and structure["whites_held"] > 0
    standard = actual_route(
        structure["standard_shanten"],
        route_support(waiting["standard_useful_codes"], waiting, codeindex, drawscale, shaped),
        costs,
    )
    seven = None
    main = standard
    family = "standard"
    if structure["seven_pairs_shanten"] is not None:
        seven = actual_route(
            structure["seven_pairs_shanten"],
            route_support(waiting["seven_pairs_useful_codes"], waiting, codeindex, drawscale, False),
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
    qualityfacts = None
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
        # 仅无当前合法胡、且仍有普通摸牌空间和实持白板时读取自然资源特征。
        # 普通出口与其条件支付点保留父值；目标仍全量联合评价，不串行筛选。
        if drawscale > 0.0 and structure["whites_held"] > 0:
            natural, qualityfacts = resource_natural_offer(
                waiting, standard, seven, costs, widths, purposes, codeindex,
            )
            joint = ordinary
            route = family
            if natural is not None and natural[13] > joint:
                joint = natural[13]
                route = "natural"
        value = WAITBASE + joint - qualcost - unknowncost - UNANCHOREXPOSURE * risk
    # 向量：普通型、七对、最佳自然目标、O、J、选中路线、条件支付摘要、
    # 未知资格码数、局部升级差、自然取舍点、资格未知罚、未知补牌罚、局部支付点、自然资源解释。
    facts = (standard, seven, natural, ordinary, joint, route, payment,
             unknown, gain, bias, qualcost, unknowncost, local, qualityfacts)
    return value, facts


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
    for action in view["actions"]:
        node = nodes[indexes[action["node_key"]]]
        if node["kind"] == "hu":
            amount = float(node["settlement"]["score_delta"][seat]) / base
            point = pay_points(amount)
            if anchor is None or point > anchor:
                anchor = point
                anchoramount = amount
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
                drawscale, pressure, discount, risk, anchor, unknowncost,
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
        facts = factslist[index]
        trace = {"u": "heuristic_rank_points", "f": "vip_joint_cash_natural_e2/1",
                 "ref": references[index], "agg": aggregates[index],
                 "a": (kind, action["pending_condition"] is not None,
                       action["skipped_seats"], round(adjustment, 3)),
                 "ctx": ctx}
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
                ])
            elif actioncount <= 64:
                trace = dict(list(trace.items()) + [
                    ("take", (facts[5], None if natural is None else natural[0])),
                    ("pay", (payment[0], payment[2], facts[7])),
                    ("oj", (round(facts[3], 3), round(facts[4], 3))),
                ])
        if anchor is None:
            trace = dict(list(trace.items()) + [("f", "vip_natural_resource_quality_m1/1")])
            if facts is not None and facts[13] is not None:
                # 平铺量均为排序点或资源代理份额，不标记任何概率或未来支付。
                trace = dict(list(trace.items()) + [
                    ("quality", tuple([round(item, 5) for item in facts[13]])),
                ])
        if actioncount > 64:
            # 只缩解释，所有根和所有图节点仍完整评分；输入动作绑定原节点。
            trace = {"u": "heuristic_rank_points", "r": references[index]}
        if actioncount > 256:
            trace = {"r": references[index]}
        if actioncount > 1024:
            # 极大数组共享首项的全批单位说明，后项用空字典避免解释超32KiB。
            # 每项原action_key仍能定位输入根，分值与条件聚合不因压缩改变。
            trace = {} if entries else {
                "u": "heuristic_rank_points", "f": "natural_resource_m1/1",
                "scope": "all_entries", "nodes": len(nodes), "roots": actioncount,
            }
        entries.append({"action_key": action["action_key"], "score": value, "trace": trace})
    return {"status": "SCORED", "entries": entries}