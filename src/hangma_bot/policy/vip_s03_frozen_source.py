"""T110-S03确认公式、核心依赖和强度证据的逐字冻结；无IO或模型调用。"""

VIP_S03_IDENTITY = {'candidate_id': 'aba936cad941608e18722e07d7cdd1eed31526cc064c84c6b88ae2e250a7a546',
 'contract_path': 'review/vip-route-2026-09-30/FIXED-FRAMEWORK-CONTRACT-V3-NATURAL-PREPARATION.md',
 'contract_sha256': '4ee18be7935430f53b84cd096767a88b88252260ecc4afd63130ccb26791efca',
 'deps_digest': 'ebe4bfceb1b11450285fac2d46babaf1682db97d656fda77fa0655918542eb4a',
 'graph_schema_version': 'vip-route-action-graph/3',
 'math_backend': {'fallback_reason': None,
                  'implementation': 'c_grouped',
                  'native_binary': {'bytes': 52552,
                                    'sha256': 'c475cfd69a86317a2b42bde8085e9e14aa2a0c456a8dae656935c6ba45a18dd6'},
                  'semantics_version': 'hangma-standard-grouped-v1'},
 'natural_preparation_semantics_version': 'vip-natural-set-preparation/1',
 'normal_draw_hu_payment_semantics_version': 'vip-normal-draw-hu-payment/1',
 'params': {'max_local_collection_size': 8192,
            'max_operations': 4800000,
            'projection_limits': {'max_branches': 16384,
                                  'max_nodes': 8192,
                                  'max_replacement_depth': 1,
                                  'max_waiting_draw_witnesses': 65536},
            'route_limits': {'max_expansions': 8192, 'max_routes_per_candidate': 128},
            'rule_config': {'base_score': 1,
                            'ruleset_version': 'hangma-mvp-v10-public-counts',
                            'you_cai_bi_kao': False}},
 'source_manifest': {'src/hangma_bot/hangma/__init__.py': {'bytes': 145,
                                                           'sha256': 'd296ef41b84366aaa7c0bc449063655f174405a28d0a74138b61f9da8e4d5b4c'},
                     'src/hangma_bot/hangma/_grouped_native.c': {'bytes': 19322,
                                                                 'sha256': '778dd36debdb7d22768f937830237a11c3c23113c75b70736be3921f93d5c95b'},
                     'src/hangma_bot/hangma/_public_tile_reuse.py': {'bytes': 10595,
                                                                     'sha256': 'e22c0f3d7a4d38ef5f78fd7532ad963ae198b8e2914623c717af488139d8f934'},
                     'src/hangma_bot/hangma/_standard.py': {'bytes': 1542,
                                                            'sha256': 'f42b4cc20b1a53bb1fa1f6157db971c6341e075d6330fcdd5da444d11b456e98'},
                     'src/hangma_bot/hangma/_standard_python.py': {'bytes': 14730,
                                                                   'sha256': '6995a928be5b19405998393419f6aa50c2e65bcd3bf9a579d162e4243422a1e7'},
                     'src/hangma_bot/hangma/action_families.py': {'bytes': 20884,
                                                                  'sha256': '7de1f94141de192e07addf27f0d2c62284fd9cd0f3399f4c094912d8e34b7900'},
                     'src/hangma_bot/hangma/candidate_facts.py': {'bytes': 19139,
                                                                  'sha256': '2933603ac2ba342fffacb7fb486da4611536676ffb8e8e2e524acc4fe93ea1e2'},
                     'src/hangma_bot/hangma/catch_play.py': {'bytes': 10173,
                                                             'sha256': 'dad2a7c6a4d83642b0a985f67d0294e60ff408e6140459138a2a211249dba693'},
                     'src/hangma_bot/hangma/emergency.py': {'bytes': 4153,
                                                            'sha256': 'e8c8ab4686c29020b86490987fd9df7e1843957d40d19648288f6af4152772b7'},
                     'src/hangma_bot/hangma/engine.py': {'bytes': 32121,
                                                         'sha256': '12a14fcf45b76467cff9dbc6e282252a06eae0bd42db46a44ab35746ae9f8aac'},
                     'src/hangma_bot/hangma/hand_analysis.py': {'bytes': 25772,
                                                                'sha256': 'c11d0abbb6eebb9f724e230b42884b8dd1b0fa0a4560eda86104df1f6826f0fe'},
                     'src/hangma_bot/hangma/interface.py': {'bytes': 37378,
                                                            'sha256': 'be6f553faf2ed5b718cc2d040fea21f9792e7758a0cd244014a793baf20a7ffc'},
                     'src/hangma_bot/hangma/internal_types.py': {'bytes': 9019,
                                                                 'sha256': '3b959871ac740d27c43f6dec18df5e30bfef6a93080628d4b3e6f67cc45af5ea'},
                     'src/hangma_bot/hangma/natural_preparation.py': {'bytes': 5636,
                                                                      'sha256': 'c44fa2c317fc6cd95c4805cde70116e8f9d05449f30cf2bd55e5e451eb9e570b'},
                     'src/hangma_bot/hangma/observation_rules.py': {'bytes': 24098,
                                                                    'sha256': '25f4fa8bb66c881e8b7583f92aae110f099192c62cbcb8b6b5520cc33c7d0b03'},
                     'src/hangma_bot/hangma/progression.py': {'bytes': 44196,
                                                              'sha256': 'dac86f4675751954d57d63e2bfae362435e7f84bae609982f112d5c2b5240cc6'},
                     'src/hangma_bot/hangma/progression_payload.py': {'bytes': 15798,
                                                                      'sha256': '6c7d5576360c35ed09c2ae3b4b4a9c7d05eb848d68ed8ff9058226adccca8c9a'},
                     'src/hangma_bot/hangma/public_successor.py': {'bytes': 21173,
                                                                   'sha256': '75cb7032ff350a126048ce7808344d63310e8ae8561f227b37585b3beecfec8f'},
                     'src/hangma_bot/hangma/public_tile_counts.py': {'bytes': 35715,
                                                                     'sha256': 'b86866d7aa43a985292ec99fd39e7378b7c259e2799c21741d5fea0dbc78eb27'},
                     'src/hangma_bot/hangma/route_frontier.py': {'bytes': 11581,
                                                                 'sha256': '710b8e54605c652ae6554fa0699062aed37f3a2fd2660289bcbb5e9df741745a'},
                     'src/hangma_bot/hangma/route_hu_witness.py': {'bytes': 8183,
                                                                   'sha256': '56fa528132568eb7b56c94990508994228df19cfe75f5ce42fe3a501ade369e9'},
                     'src/hangma_bot/hangma/route_structure.py': {'bytes': 10649,
                                                                  'sha256': '9ad86564884466001dd9321aeb1842273129d62b64ad8f7b78a683d5b08f90cb'},
                     'src/hangma_bot/hangma/route_transition.py': {'bytes': 72647,
                                                                   'sha256': '800b595e33381ed355d9182e31ae977904fc7969ac5592f4a692faf5b62eac4f'},
                     'src/hangma_bot/hangma/settlement.py': {'bytes': 10643,
                                                             'sha256': '3e4497b8eedb344ddd974f693816adf520586c78efdd60593dfa49ed36c0e3d4'},
                     'src/hangma_bot/hangma/special_rules.py': {'bytes': 11609,
                                                                'sha256': '16cc575f5b73dfdebfe3729fb4147256fa457e906323fbd0c5719a591a4cdf70'},
                     'src/hangma_bot/hangma/value_analysis.py': {'bytes': 18251,
                                                                 'sha256': 'ec2a2416d654b4cec1dd4aa79b455d1cd5f12a2d6d46f6f11da91f722c50f0f8'},
                     'src/hangma_bot/kernel/actions.py': {'bytes': 10754,
                                                          'sha256': 'f598f7d5ad582858d0b9601b445ee53fef88f85c060eb26bb3aac3e2811781b9'},
                     'src/hangma_bot/kernel/config.py': {'bytes': 3236,
                                                         'sha256': 'd1e68457a187d05f609ae7b9681820d5dc9c4fe39d0b90eec119f9426f1efc97'},
                     'src/hangma_bot/kernel/observation.py': {'bytes': 17784,
                                                              'sha256': '03974493d930bc22adf47d4955d47cce1dc25ba2fea9be89919b8bd46e1b94b6'},
                     'src/hangma_bot/kernel/outcomes.py': {'bytes': 8643,
                                                           'sha256': 'b19fccb3a8587ad27ae27dcc96b682688895fb215c7023c8e3d637d7f03d8bc6'},
                     'src/hangma_bot/policy/action_value.py': {'bytes': 45125,
                                                               'sha256': '28229c2f18e0b72eea6d7119891b27754414382b951a1f2c1ef0bc3ada17395c'},
                     'src/hangma_bot/policy/action_value_executor.py': {'bytes': 106868,
                                                                        'sha256': '49cfd1a18bb8c392b2955e39cf338916c014b9523fc7fde303c450a287da5ceb'},
                     'src/hangma_bot/policy/errors.py': {'bytes': 372,
                                                         'sha256': '98701b3af228f088eeff0b13fc5cdae3a50564b49e29410fdba565c57f8044d9'},
                     'src/hangma_bot/policy/interface.py': {'bytes': 3546,
                                                            'sha256': '430fec41eb81b5cd72e3f4c884dd8cbe7820e36252545298cf89627a0304d0fa'},
                     'src/hangma_bot/policy/retry_backup.py': {'bytes': 1111,
                                                               'sha256': '71078b5ccd2cf3fb1295a8f6f0c563778bd046b11921824dbf007fc42da2360b'},
                     'src/hangma_bot/policy/route_heuristic_view.py': {'bytes': 28880,
                                                                       'sha256': 'c653f24b8a2266307f58480cc61a611564a98b5ad086c2ace67b3abef8d24fc1'},
                     'src/hangma_bot/policy/route_vip_heuristic.py': {'bytes': 37369,
                                                                      'sha256': 'c70b469d0aa2a4871e78436434f5ef5c49c9625492690b164a8f7f93fd6b299f'},
                     'src/hangma_bot/policy/safe_fallback.py': {'bytes': 2352,
                                                                'sha256': 'e6bc86c0a79f780f44c716f52a52eb980b2926bb9249861f1a3b07b58603d281'}},
 'source_sha256': 'bdd7d29736f1b2a00240648cbb8a837e29fbfb2b10434471272b8d8a84b190dd',
 'view_schema_version': 'vip-route-scoring-view/3'}

VIP_S03_REQUIRED_EVIDENCE_SHA256 = {'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1/CONFIRMATION-GATE-ACTUAL.json': '53240b3a09a2c66c7949b914cb39055b8cd751541da44cd7129b0b2890d2e233',
 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1/heavy-nominal-deadline-probe/CLOSED.json': 'c176eec90f8b9652c1ba337d7a79f7e6613c5bb3aaa6d13da20459ad57a51f90',
 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1/native-verification/CLOSED.json': 'e0d2c8eac01187d9f48f0c7c115877beaa7d27791688ccab1ba9e5d82e0adc6b',
 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1/original-deadline-probe/CLOSED.json': 'eca60c30a24ca98b4cab93880b9ebe1b36d8f449402fba68c5d8fa20298d0551',
 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/wait-confirmation-1/sealed-originals-1/CLOSED.json': 'b7c202d63ce777520f0d2a92e8949c9abbeba54c72679dcd735c42e2a65fba1a',
 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/wait-confirmation-1/wait-confirmation-001-dispatch/SUMMARY.json': 'f69035613e8b77a26b746956eb657001cf9c6a432bf7e150ece8dc75957e8e2c'}

VIP_S03_SOURCE = r'''"""m1联合公式：凸保白用途先验、单次额外物理负担与单一胡机会费的联合排序。"""

PAYCAP = 50.0
PAYREF = 192.0
HUBASE = 10.0
WAITBASE = 12.0
FORMCOST = 3.5
SPEEDCAP = 4.8
SPEEDREF = 12.0
VARREF = 4.0
UNSEENSOFT = 0.75
PURPOSES = (0.0, 2.5, 6.0, 13.0, 26.0)
DEALERBOOST = 1.20
HORIZONCOST = 0.35
RETENTION = 20
WALLSOFT = 8.0
UNKNOWNWALLSCALE = 0.70
OPPDECAY = 0.05
RISKBASE = 1.8
OPPRISK = 0.12
LATERISK = 3.4
UNKNOWNWALLRISK = 0.7
MATURELINEAR = 0.35
RESCUEDECAY = 0.30
EXITFLOOR = 0.40
EXITMASSREF = 6.0
EXITWIDTHREF = 3.0
EXITSTEPDECAY = 0.25
TARGETGATEBASE = 0.50
TARGETMASSREF = 2.0
PORTCAP = 2.2
PORTREF = 12.0
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
NETCARRY = 0.25
NETANCHORPRICE = 0.30
NETRISKFEE = 0.45
BRANCHGAP = 0.15
PREPBUDGET = 0.60
PAIRPRIORWEIGHT = 0.30


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
            cell = stock[codeindex[code]]
            if cell[0] > 0.0:
                mass += cell[0]
                exact += cell[1]
                width += 1
                uncertain += cell[2]
    credit = (drawscale * SPEEDCAP * mass / (SPEEDREF + mass)
              * float(width) / (VARREF + float(width)))
    return credit, mass, width, exact, uncertain


def purposescale(burden, room, drawscale, pressure):
    """墙余可行性与公开副露压力的条件折减；burden不是保证摸牌次数。"""
    excess = 0.0 if room is None else max(0.0, float(burden) - room)
    return drawscale * pressure / (1.0 + HORIZONCOST * excess)


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


def jointwait(waiting, standard, seven, prep, local, codeindex, room, drawscale,
              pressure, stock, dealerboost):
    """凸用途先验与单次额外负担的逐目标选择及共享条件图备用组合。

    每个目标只为超过其家族普通路线已付摸牌数的不同物理动作付一次
    线性成熟度；平方折减、白弃附加费、阶段差价与准备release加价删除，
    墙余只在可行性门按总负担计一次。主出口、已见证胡码与已选保白
    目标占用的码先删除，同码多来源取最大权重后统一饱和。
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
                prior = PURPOSES[retained] * dealerboost
            exitfactor = EXITFLOOR + (1.0 - EXITFLOOR) * exitgate
            purposecredit = (prior * purposescale(burden, room, drawscale, pressure)
                             * targetgate * maturity * exitfactor)
            rescued = local * rescue
            prospective = rescued + purposecredit
            value = route[6] + prospective
            if best is None or value > best[10]:
                best = (index, target["family"], retained, need, terminal, burden,
                        naturaldrop, whitedrop, width, prospective, value)
            gain = max(0.0, value - ordinary)
            if predecessor and retained > 0 and retained <= whites and gain > 0.0:
                if option is None or gain > option[8]:
                    option = (index, target["family"], retained, need, width, prior,
                              exitgate, targetgate, gain, targetmass, maturity, extra,
                              rescue, prospective)
    baseline = set(maincodes)
    knownhu = waiting["legal_hu_draw_codes"]
    if knownhu is not None:
        for code in knownhu:
            baseline.add(code)
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
            baseline.add(code)
        for code in selected["conditional_need_improvement_codes"]:
            baseline.add(code)
        if (selected["family"] == "standard" and selected["target_stage"] == "waiting_predecessor"
                and selected["retained_whites"] > 0):
            preparationoccupied = 1
            for code in waiting["natural_preparation"]["natural_need_improvement_codes"]:
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
    if preparationoccupied == 0 and prep[0] > 0 and prep[2] > 0:
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
        cell = stock[entry[0]]
        if cell[0] > 0.0:
            mass += entry[1] * cell[0]
            diversity += entry[1]
            exact += cell[1]
            codecount += 1
            uncertain += cell[2]
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
    """当前胡与继续等待的净比较；等待暴露只按一个合并费计一次。

    直接升级按同码包络差计算；远目标只消费超过备用信用的增量；
    确定胡的机会成本合并为锚价加风险费的单一exposure，不再分别收
    等待费与距离费。全部是排序点，不是期望积分或存活率。
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
    # 当前胡锚已支付成熟普通结构；保留其出口不构成额外等待收益。
    # 不按自然目标need归零：直接支付差及白用途/追加行动option仍独立保留。
    if main[0] <= 0:
        carry = 0.0
    exposure = (NETANCHORPRICE * anchor + NETRISKFEE * risk) * (1.0 - discount * maintained)
    net = offervalue + carry - exposure
    return (net, channel, upgrade, downside, maintained, carry, exposure,
            remote, remoteprice, fallback, offervalue)


def waitvalue(waiting, codeindex, seat, base, room, drawscale, pressure, discount,
              risk, anchor, unknowncost, dealerboost):
    """同一凸先验与单次负担成本下评价普通出口、七对、逐目标用途与当前胡。"""
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
                                        room, drawscale, pressure, stock, dealerboost)
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
    的下端加有界价差，不挑最好补牌；机械缺口显式弃权。庄家身份只作
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
                                     pressure, discount, risk, anchor, unknowncost, dealerboost)
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
                                        round(ready[3], 3), round(ready[4], 3))))
            pairs.append(("prep", (facts[3][0], facts[3][1], facts[3][2], round(facts[3][3], 3))))
        if not entries:
            pairs.append(("unit", "heuristic_rank_points"))
            pairs.append(("formula", "vip_convex_purpose_single_burden_m1/1"))
            if anchor is None:
                anchorvalue = None
            else:
                anchorvalue = round(anchor, 3)
            pairs.append(("context", (wall, opponents, round(dealerboost, 3),
                                      round(discount, 3), round(risk, 3), anchorvalue)))
            pairs.append(("unknown", "opponent_hu_and_future_draw_reachability"))
            pairs.append(("scope", "conditional_facts_not_probability_or_guaranteed_highfan"))
        entries.append({"action_key": action["action_key"], "score": value, "trace": dict(pairs)})
    return {"status": "SCORED", "entries": entries}'''
