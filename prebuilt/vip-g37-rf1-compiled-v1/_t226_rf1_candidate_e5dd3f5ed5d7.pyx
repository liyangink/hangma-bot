from __future__ import annotations
import math
from _s02_meter cimport Meter
from hangma_bot.policy.action_value_executor import WorkloadExceeded, MAX_STRING_CHARS, MAX_INT_MAGNITUDE, _STRING_COST_CHUNK

cdef inline object _direct_pass(Meter meter, object value):
    meter.charge_one()
    if type(value) is str and len(value) > MAX_STRING_CHARS:
        raise WorkloadExceeded("字符串超过 {0} 字符上限".format(MAX_STRING_CHARS))
    return value

cdef inline object _direct_slice(object lower, object upper, object step):
    return slice(lower, upper, step)

cdef inline object _direct_bin(Meter meter, object fallback, object a, object op, object b):
    cdef object result
    if type(a) in (int, float, bool) and type(b) in (int, float, bool) and op in ("+", "-", "*", "/", "//", "%"):
        meter.charge_one()
        if op == "+": result = a + b
        elif op == "-": result = a - b
        elif op == "*": result = a * b
        elif op == "/": result = a / b
        elif op == "//": result = a // b
        else: result = a % b
        if isinstance(result, bool): return result
        if isinstance(result, int):
            if result > MAX_INT_MAGNITUDE or result < -MAX_INT_MAGNITUDE:
                raise WorkloadExceeded("整数结果超过 63 位界限：{0}".format(result))
            return result
        if isinstance(result, float):
            if not math.isfinite(result):
                raise WorkloadExceeded("非有限浮点结果（NaN/Inf）使整批失效")
            return result
        return result
    return fallback(a, op, b)

cdef inline object _direct_sub(Meter meter, object fallback, object cap, object value, object index):
    cdef object result
    if type(value) is dict and type(index) is str:
        meter.charge(len(index) // _STRING_COST_CHUNK)
        result = value[index]
        if isinstance(result, (set, frozenset, dict)) and len(result) > cap:
            raise WorkloadExceeded("局部集合超过 {0} 项上限".format(cap))
        return result
    return fallback(value, index)

# 仅供第一方差分验证的公开接缝；不绑定到候选的受限命名空间。
def probe_pass(Meter meter, object value):
    return _direct_pass(meter, value)

def probe_bin(Meter meter, object fallback, object a, object op, object b):
    return _direct_bin(meter, fallback, a, op, b)

def probe_sub(Meter meter, object fallback, object cap, object value, object index):
    return _direct_sub(meter, fallback, cap, value, index)

def make_candidate(runtime, Meter bound_meter, bound_cap):
    _av_bin = runtime['_av_bin']
    _av_cmp = runtime['_av_cmp']
    _av_dict_lit = runtime['_av_dict_lit']
    _av_fvalue = runtime['_av_fvalue']
    _av_iter = runtime['_av_iter']
    _av_key = runtime['_av_key']
    _av_method = runtime['_av_method']
    _av_pass = runtime['_av_pass']
    _av_set_lit = runtime['_av_set_lit']
    _av_sub = runtime['_av_sub']
    _av_un = runtime['_av_un']
    _av_wrap_dict = runtime['_av_wrap_dict']
    _av_wrap_list = runtime['_av_wrap_list']
    abs = runtime['abs']
    all = runtime['all']
    any = runtime['any']
    bool = runtime['bool']
    dict = runtime['dict']
    enumerate = runtime['enumerate']
    filter = runtime['filter']
    float = runtime['float']
    frozenset = runtime['frozenset']
    int = runtime['int']
    len = runtime['len']
    list = runtime['list']
    map = runtime['map']
    max = runtime['max']
    min = runtime['min']
    range = runtime['range']
    reversed = runtime['reversed']
    round = runtime['round']
    set = runtime['set']
    sorted = runtime['sorted']
    sum = runtime['sum']
    tuple = runtime['tuple']
    zip = runtime['zip']
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
    DEALERBOOST = 1.2
    WHITEHOLD = 0.3
    EXTRAPATH = 1.25
    ACTREF = 3.0
    DIVCAP = 1.6
    DIVREF = 4.0
    DIVGAP = 0.35
    DIVCLOSE = 0.3
    DIVTOTAL = 2.2
    PREPBASE = 0.6
    PREPMATURE = 0.35
    LOCALCAP = 6.0
    LOCALREF = 8.0
    COVREF = 3.0
    ENVELOPEBLEND = 0.25
    SINGLESCOPE = 0.75
    PAIRPRIORWEIGHT = 0.3
    HORIZONCOST = 0.35
    RETENTION = 20
    WALLSOFT = 8.0
    UNKNOWNWALLSCALE = 0.7
    OPPDECAY = 0.05
    RISKBASE = 1.8
    OPPRISK = 0.12
    LATERISK = 3.4
    UNKNOWNWALLRISK = 0.7
    QUALUNKNOWN = 0.7
    QUALUNANALYSED = 1.0
    UNKNOWNDRAW = 2.5
    UNANCHOREXPOSURE = 0.15
    CONDITIONBLEND = 0.2
    CONDITIONCAP = 1.0
    REPLACEMENTBLEND = 0.4
    REPLACEMENTCAP = 2.3
    CLAIMCOST = 0.25
    SKIPVALUE = 0.1
    GANGCOST = 0.12
    ANCHOROPTIONBASE = 0.14
    ANCHOROPTIONSTEP = 0.1
    ANCHORFALLBACKCOST = 0.45
    ANCHORUNKNOWNCOST = 0.35
    NETUPGRADEWEIGHT = 1.4
    NETUPWIDTHREF = 4.0
    NETEXITWIDTHREF = 4.0
    NETANCHORPRICE = 0.3
    NETRISKFEE = 0.45
    NETCARRY = 0.25
    
    def paypoints(amount):
        """本家净积分/基础分的有界排序点；不是期望积分或概率。"""
        return _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, PAYCAP, '*', amount), '/', _direct_bin(bound_meter, _av_bin, PAYREF, '+', _direct_pass(bound_meter, abs(amount))))
    
    def stockof(slot, waiting):
        """公开容量只作排序支持；精确零关闭本码，保守/未知软保留。
    
        不把容量除以墙余，也不改写资格或支付事实。
        """
        capacity = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'unseen_capacities'), slot)
        evidence = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'unseen_evidence'), slot)
        if _av_cmp(evidence, '==', 'exact') and _av_cmp(capacity, 'is not', None):
            return (_direct_pass(bound_meter, float(capacity)), capacity, 0)
        if _av_cmp(evidence, '==', 'conservative') and _av_cmp(capacity, 'is not', None) and _av_cmp(capacity, '>', 0):
            return (_direct_pass(bound_meter, float(capacity)), 0, 1)
        return (UNSEENSOFT, 0, 1)
    
    def summaryof(codes, codeindex, stock):
        """去重码集的支持摘要；单码质量按LINKCAP截顶，防一码四张冒充多码。"""
        mass = 0.0
        width = 0
        exact = 0
        uncertain = 0
        seen = _direct_pass(bound_meter, set())
        for code in _av_iter(codes):
            if _av_cmp(code, 'not in', seen):
                _direct_pass(bound_meter, _av_method(seen, 'add')(code))
                cell = _direct_sub(bound_meter, _av_sub, bound_cap, stock, _direct_sub(bound_meter, _av_sub, bound_cap, codeindex, code))
                if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, cell, 0), '>', 0.0):
                    mass = _direct_bin(bound_meter, _av_bin, mass, '+', _direct_pass(bound_meter, min(_direct_sub(bound_meter, _av_sub, bound_cap, cell, 0), LINKCAP)))
                    width = _direct_bin(bound_meter, _av_bin, width, '+', 1)
                    exact = _direct_bin(bound_meter, _av_bin, exact, '+', _direct_sub(bound_meter, _av_sub, bound_cap, cell, 1))
                    uncertain = _direct_bin(bound_meter, _av_bin, uncertain, '+', _direct_sub(bound_meter, _av_sub, bound_cap, cell, 2))
        return (mass, width, exact, uncertain)
    
    def speedof(mass, width, scale):
        """速度质量核：截顶质量与码宽的乘积饱和，仅是排序支持。"""
        return _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, scale, '*', SPEEDCAP), '*', mass), '/', _direct_bin(bound_meter, _av_bin, SPEEDREF, '+', mass)), '*', _direct_pass(bound_meter, float(width))), '/', _direct_bin(bound_meter, _av_bin, VARREF, '+', _direct_pass(bound_meter, float(width))))
    
    def ladder(steps):
        """共享凸节奏价：线性段加凸尾；steps是距离刻度，不是保证摸牌次数。"""
        linear = _direct_bin(bound_meter, _av_bin, FORMCOST, '*', steps)
        tail = _direct_bin(bound_meter, _av_bin, steps, '-', TAILOFF)
        if _av_cmp(tail, '>', 0):
            return _direct_bin(bound_meter, _av_bin, linear, '+', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, TAILQUAD, '*', tail), '*', tail))
        return linear
    
    def horizon(bound, room):
        """墙余对指定条件路径下界的一次折价；room不是保证本人摸牌额度。"""
        excess = 0.0 if _av_cmp(room, 'is', None) else _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(bound)), '-', room)))
        return _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, HORIZONCOST, '*', excess)))
    
    def paysummary(waiting, seat, base):
        """条件支付逐码合并互斥抓打包络；同码两假设不相加，未知码不填零。"""
        payments = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'normal_draw_hu_payments')
        if _av_cmp(payments, 'is', None):
            return (0, None, 0, 0.0, ())
        partial = _av_cmp(_direct_pass(bound_meter, len(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'qualification_unknown_codes'))), '>', 0)
        if _av_un('not', payments):
            return (3 if partial else 1, 0.0, 0, 0.0, ())
        groups = _av_wrap_list([])
        current = None
        lower = 0.0
        upper = 0.0
        capacity = 0.0
        rows = 0
        for payment in _av_iter(payments):
            point = _direct_pass(bound_meter, paypoints(_direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, payment, 'settlement'), 'score_delta'), seat))), '/', base)))
            code = _direct_sub(bound_meter, _av_sub, bound_cap, payment, 'draw_code')
            if _av_cmp(code, '!=', current):
                if _av_cmp(current, 'is not', None):
                    _direct_pass(bound_meter, _av_method(groups, 'append')((capacity, lower, upper, rows)))
                current = code
                lower = point
                upper = point
                capacity = _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 'draw_capacity_before')))
                rows = 1
            else:
                if _av_cmp(point, '<', lower):
                    lower = point
                if _av_cmp(point, '>', upper):
                    upper = point
                rows = _direct_bin(bound_meter, _av_bin, rows, '+', 1)
        _direct_pass(bound_meter, _av_method(groups, 'append')((capacity, lower, upper, rows)))
        total = 0.0
        mass = 0.0
        offers = _av_wrap_list([])
        for group in _av_iter(groups):
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, group, 3), '==', 1):
                envelope = _direct_bin(bound_meter, _av_bin, SINGLESCOPE, '*', _direct_sub(bound_meter, _av_sub, bound_cap, group, 1))
            else:
                envelope = _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, group, 1), '+', _direct_bin(bound_meter, _av_bin, ENVELOPEBLEND, '*', _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, group, 2), '-', _direct_sub(bound_meter, _av_sub, bound_cap, group, 1))))
            total = _direct_bin(bound_meter, _av_bin, total, '+', _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, group, 0), '*', envelope))
            mass = _direct_bin(bound_meter, _av_bin, mass, '+', _direct_sub(bound_meter, _av_sub, bound_cap, group, 0))
            _direct_pass(bound_meter, _av_method(offers, 'append')((_direct_sub(bound_meter, _av_sub, bound_cap, group, 0), envelope)))
        return (3 if partial else 2, _direct_bin(bound_meter, _av_bin, total, '/', mass), _direct_pass(bound_meter, len(offers)), mass, _direct_pass(bound_meter, tuple(offers)))
    
    def payroute(payment, coverage, scale):
        """已见证条件支付作为长度0路线的质量；容量与码宽只是排序门。"""
        point = _direct_sub(bound_meter, _av_sub, bound_cap, payment, 1)
        if _av_cmp(point, 'is', None) or _av_cmp(point, '<=', 0.0) or _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 2), '<=', 0):
            return 0.0
        gate = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, payment, 3), '/', _direct_bin(bound_meter, _av_bin, PAYMASSREF, '+', _direct_sub(bound_meter, _av_sub, bound_cap, payment, 3))), '*', _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 2)))), '/', _direct_bin(bound_meter, _av_bin, NETEXITWIDTHREF, '+', _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 2)))))
        return _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, LOCALCAP, '*', point), '/', _direct_bin(bound_meter, _av_bin, LOCALREF, '+', point)), '*', gate), '*', coverage), '*', scale)
    
    def huoffer(anchor, discount, risk, payment, option, plaincore):
        """当前胡与继续的净比较；等待暴露合并为一次锚价加风险费。
    
        直接升级按同码包络差计；远用途只领前沿净差；不把组合弹性当弃胡收益。
        """
        mass = _direct_sub(bound_meter, _av_sub, bound_cap, payment, 3)
        width = _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 2)))
        exitgate = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, mass, '/', _direct_bin(bound_meter, _av_bin, PAYMASSREF, '+', mass)), '*', width), '/', _direct_bin(bound_meter, _av_bin, NETEXITWIDTHREF, '+', width))
        preserved = 0.0
        upgradeamount = 0.0
        upgrademass = 0.0
        upgradewidth = 0
        downsideamount = 0.0
        for capacity, point in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 4)):
            preserved = _direct_bin(bound_meter, _av_bin, preserved, '+', _direct_bin(bound_meter, _av_bin, capacity, '*', _direct_pass(bound_meter, min(anchor, _direct_pass(bound_meter, max(0.0, point))))))
            difference = _direct_bin(bound_meter, _av_bin, point, '-', anchor)
            if _av_cmp(difference, '>', 0.0):
                upgradeamount = _direct_bin(bound_meter, _av_bin, upgradeamount, '+', _direct_bin(bound_meter, _av_bin, capacity, '*', difference))
                upgrademass = _direct_bin(bound_meter, _av_bin, upgrademass, '+', capacity)
                upgradewidth = _direct_bin(bound_meter, _av_bin, upgradewidth, '+', 1)
            else:
                downsideamount = _direct_bin(bound_meter, _av_bin, downsideamount, '+', _direct_bin(bound_meter, _av_bin, capacity, '*', _direct_pass(bound_meter, max(0.0, _av_un('-', difference)))))
        floorfraction = 0.0
        if _av_cmp(mass, '>', 0.0) and _av_cmp(anchor, '>', 0.0):
            floorfraction = _direct_bin(bound_meter, _av_bin, preserved, '/', _direct_bin(bound_meter, _av_bin, mass, '*', anchor))
        maintained = _direct_bin(bound_meter, _av_bin, exitgate, '*', floorfraction)
        upgradesupport = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, upgrademass, '/', _direct_bin(bound_meter, _av_bin, PAYMASSREF, '+', upgrademass)), '*', _direct_pass(bound_meter, float(upgradewidth))), '/', _direct_bin(bound_meter, _av_bin, NETUPWIDTHREF, '+', _direct_pass(bound_meter, float(upgradewidth))))
        upgrade = 0.0
        if _av_cmp(upgrademass, '>', 0.0):
            upgrade = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, NETUPGRADEWEIGHT, '*', discount), '*', upgradeamount), '/', upgrademass), '*', upgradesupport)
        downside = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, discount, '*', downsideamount), '/', _direct_bin(bound_meter, _av_bin, PAYMASSREF, '+', mass))
        offervalue = _direct_bin(bound_meter, _av_bin, upgrade, '-', downside)
        channel = 'direct_upgrade'
        remote = 0.0
        remoteprice = 0.0
        fallback = 0.0
        if _av_cmp(option, 'is not', None):
            remoteprice = _direct_bin(bound_meter, _av_bin, anchor, '*', _direct_bin(bound_meter, _av_bin, ANCHOROPTIONBASE, '+', _direct_bin(bound_meter, _av_bin, ANCHOROPTIONSTEP, '*', _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, option, 1))))))
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 1), 'is', None):
                fallback = _direct_bin(bound_meter, _av_bin, ANCHORUNKNOWNCOST, '*', anchor)
            else:
                fallback = _direct_bin(bound_meter, _av_bin, ANCHORFALLBACKCOST, '*', _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, anchor, '-', _direct_pass(bound_meter, max(0.0, _direct_sub(bound_meter, _av_sub, bound_cap, payment, 1)))))))
            remote = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, discount, '*', _direct_sub(bound_meter, _av_sub, bound_cap, option, 0)), '-', remoteprice), '-', fallback)
            if _av_cmp(remote, '>', offervalue):
                offervalue = remote
                channel = 'purpose_frontier_surplus'
        carry = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, NETCARRY, '*', discount), '*', maintained), '*', _direct_pass(bound_meter, max(0.0, plaincore)))
        exposure = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, NETANCHORPRICE, '*', anchor), '+', _direct_bin(bound_meter, _av_bin, NETRISKFEE, '*', risk)), '*', _direct_bin(bound_meter, _av_bin, 1.0, '-', _direct_bin(bound_meter, _av_bin, discount, '*', maintained)))
        net = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, offervalue, '+', carry), '-', exposure)
        return (net, channel, upgrade, downside, maintained, carry, exposure, remote, remoteprice, fallback)
    
    def routewait(waiting, codeindex, seat, base, room, drawscale, pressure, discount, risk, anchor, unknowncost, dealerboost):
        """一个等待态的阶梯前沿与独占红利；重叠码不重复购买。
    
        每条路线(普通、七对、已见证支付、自然准备、合格保白前驱)在同一
        凸阶梯上付距离价，前沿取最大；非赢家只按独占码领取封顶红利。
        保白用途按每张白常数持有价，先验随k跃升，负担不再随k双重加罚。
        """
        structure = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'structure')
        stock = _av_wrap_list([])
        for slot in _av_iter(_direct_pass(bound_meter, range(_direct_pass(bound_meter, len(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'unseen_capacities')))))):
            _direct_pass(bound_meter, _av_method(stock, 'append')(_direct_pass(bound_meter, stockof(slot, waiting))))
        scale = _direct_bin(bound_meter, _av_bin, drawscale, '*', pressure)
        payment = _direct_pass(bound_meter, paysummary(waiting, seat, base))
        coverage = _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 2))), '/', _direct_bin(bound_meter, _av_bin, COVREF, '+', _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 2)))))
        routes = _av_wrap_list([])
        standardsteps = _direct_pass(bound_meter, float(_direct_pass(bound_meter, max(0, _direct_sub(bound_meter, _av_sub, bound_cap, structure, 'standard_shanten')))))
        standardsummary = _direct_pass(bound_meter, summaryof(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'standard_useful_codes'), codeindex, stock))
        standardquote = _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, speedof(_direct_sub(bound_meter, _av_sub, bound_cap, standardsummary, 0), _direct_sub(bound_meter, _av_sub, bound_cap, standardsummary, 1), scale)), '-', _direct_pass(bound_meter, ladder(standardsteps)))
        _direct_pass(bound_meter, _av_method(routes, 'append')((standardquote, standardsteps, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'standard_useful_codes'), 'standard', None)))
        sevenquote = None
        sevensteps = 0.0
        if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, structure, 'seven_pairs_shanten'), 'is not', None) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'seven_pairs_useful_codes'), 'is not', None):
            sevensteps = _direct_pass(bound_meter, float(_direct_pass(bound_meter, max(0, _direct_sub(bound_meter, _av_sub, bound_cap, structure, 'seven_pairs_shanten')))))
            sevensummary = _direct_pass(bound_meter, summaryof(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'seven_pairs_useful_codes'), codeindex, stock))
            pairprior = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, PAIRPRIORWEIGHT, '*', _direct_pass(bound_meter, float(_direct_pass(bound_meter, min(2, _direct_pass(bound_meter, max(0, _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, structure, 'natural_pair_count'), '-', 4)))))))), '/', _direct_bin(bound_meter, _av_bin, sevensteps, '+', 1.0))
            sevenquote = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, speedof(_direct_sub(bound_meter, _av_sub, bound_cap, sevensummary, 0), _direct_sub(bound_meter, _av_sub, bound_cap, sevensummary, 1), scale)), '+', _direct_bin(bound_meter, _av_bin, pairprior, '*', scale)), '-', _direct_pass(bound_meter, ladder(sevensteps)))
            _direct_pass(bound_meter, _av_method(routes, 'append')((sevenquote, sevensteps, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'seven_pairs_useful_codes'), 'seven_pairs', None)))
        if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 2), '>', 0) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'legal_hu_draw_codes'), 'is not', None):
            _direct_pass(bound_meter, _av_method(routes, 'append')((_direct_pass(bound_meter, payroute(payment, coverage, scale)), 0.0, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'legal_hu_draw_codes'), 'witnessed_payment', None)))
        prep = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'natural_preparation')
        prepneed = _direct_sub(bound_meter, _av_sub, bound_cap, prep, 'natural_draw_lower_bound')
        prepdiscard = _direct_sub(bound_meter, _av_sub, bound_cap, prep, 'natural_discard_lower_bound')
        prepwidth = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'natural_preparation_code_width')
        if _av_cmp(prepneed, '<=', 0):
            readiness = 1.0
        elif _av_cmp(prepwidth, '>', 0):
            readiness = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, PREPMATURE, '*', _direct_pass(bound_meter, float(prepneed)))))
        else:
            readiness = 0.0
        prepsteps = _direct_pass(bound_meter, max(standardsteps, _direct_pass(bound_meter, float(prepneed))))
        prepquote = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, standardquote, '+', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, PREPBASE, '*', readiness), '*', scale), '*', _direct_pass(bound_meter, horizon(prepneed, room)))), '-', _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, ladder(prepsteps)), '-', _direct_pass(bound_meter, ladder(standardsteps))))
        _direct_pass(bound_meter, _av_method(routes, 'append')((prepquote, prepsteps, _direct_sub(bound_meter, _av_sub, bound_cap, prep, 'natural_need_improvement_codes'), 'natural_preparation', None)))
        plainroutes = _direct_pass(bound_meter, len(routes))
        whites = _direct_sub(bound_meter, _av_sub, bound_cap, structure, 'whites_held')
        for index, target in _av_iter(_direct_pass(bound_meter, enumerate(_direct_sub(bound_meter, _av_sub, bound_cap, structure, 'targets')))):
            retained = _direct_sub(bound_meter, _av_sub, bound_cap, target, 'retained_whites')
            eligible = _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, target, 'target_stage'), '==', 'waiting_predecessor') and _av_cmp(retained, '>', 0) and _av_cmp(retained, '<=', whites)
            familyquote = None
            familysteps = standardsteps
            familylabel = 'standard'
            if eligible:
                familyquote = standardquote
                if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, target, 'family'), '==', 'seven_pairs'):
                    familylabel = 'seven_pairs'
                    if _av_cmp(sevenquote, 'is not', None):
                        familyquote = sevenquote
                        familysteps = sevensteps
                    else:
                        familyquote = None
                if _av_cmp(familyquote, 'is not', None):
                    need = _direct_sub(bound_meter, _av_sub, bound_cap, target, 'natural_need')
                    terminal = 1 if _direct_sub(bound_meter, _av_sub, bound_cap, target, 'requires_terminal_draw') else 0
                    bound = _direct_pass(bound_meter, float(_direct_bin(bound_meter, _av_bin, need, '+', terminal)))
                    targetsummary = _direct_pass(bound_meter, summaryof(_direct_sub(bound_meter, _av_sub, bound_cap, target, 'conditional_need_improvement_codes'), codeindex, stock))
                    if _av_cmp(need, '<=', 0):
                        activation = 1.0
                    elif _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, targetsummary, 1), '>', 0) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, targetsummary, 2), '>', 0):
                        activation = _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, targetsummary, 2))), '/', _direct_bin(bound_meter, _av_bin, ACTREF, '+', _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, targetsummary, 2)))))
                    else:
                        activation = 0.0
                    prior = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, PURPOSES, retained), '*', dealerboost), '*', scale), '*', _direct_pass(bound_meter, horizon(bound, room))), '*', activation)
                    baseline = _direct_bin(bound_meter, _av_bin, familysteps, '+', 1.0)
                    steps = _direct_pass(bound_meter, max(baseline, bound))
                    extra = _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, steps, '-', baseline)))
                    quote = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, familyquote, '+', prior), '-', _direct_bin(bound_meter, _av_bin, WHITEHOLD, '*', _direct_pass(bound_meter, float(_direct_bin(bound_meter, _av_bin, retained, '-', 1))))), '-', _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, ladder(steps)), '-', _direct_pass(bound_meter, ladder(baseline))))
                    _direct_pass(bound_meter, _av_method(routes, 'append')((quote, steps, _direct_sub(bound_meter, _av_sub, bound_cap, target, 'conditional_need_improvement_codes'), _direct_bin(bound_meter, _av_bin, 'purpose:', '+', familylabel), (extra, retained, need, bound, index, activation))))
        plaincore = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, 0), 0)
        for position in _av_iter(_direct_pass(bound_meter, range(plainroutes))):
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, position), 0), '>', plaincore):
                plaincore = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, position), 0)
        core = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, 0), 0)
        winner = 0
        for position in _av_iter(_direct_pass(bound_meter, range(_direct_pass(bound_meter, len(routes))))):
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, position), 0), '>', core):
                core = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, position), 0)
                winner = position
        occupied = _direct_pass(bound_meter, set())
        for code in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, winner), 2)):
            _direct_pass(bound_meter, _av_method(occupied, 'add')(code))
        if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'legal_hu_draw_codes'), 'is not', None):
            for code in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'legal_hu_draw_codes')):
                _direct_pass(bound_meter, _av_method(occupied, 'add')(code))
        dividend = 0.0
        for position in _av_iter(_direct_pass(bound_meter, range(_direct_pass(bound_meter, len(routes))))):
            if _av_cmp(position, '!=', winner):
                route = _direct_sub(bound_meter, _av_sub, bound_cap, routes, position)
                gapvalue = _direct_bin(bound_meter, _av_bin, core, '-', _direct_sub(bound_meter, _av_sub, bound_cap, route, 0))
                if _av_cmp(gapvalue, '<', 0.0):
                    gapvalue = 0.0
                exclusive = 0
                for code in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, route, 2)):
                    if _av_cmp(code, 'not in', occupied):
                        cell = _direct_sub(bound_meter, _av_sub, bound_cap, stock, _direct_sub(bound_meter, _av_sub, bound_cap, codeindex, code))
                        if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, cell, 0), '>', 0.0):
                            exclusive = _direct_bin(bound_meter, _av_bin, exclusive, '+', 1)
                if _av_cmp(exclusive, '>', 0):
                    closeness = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, DIVCLOSE, '*', gapvalue)))
                    distgap = _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, route, 1), '-', _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, winner), 1))
                    if _av_cmp(distgap, '<', 0.0):
                        distgap = 0.0
                    maturity = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, DIVGAP, '*', distgap)))
                    dividend = _direct_bin(bound_meter, _av_bin, dividend, '+', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, DIVCAP, '*', _direct_pass(bound_meter, float(exclusive))), '/', _direct_bin(bound_meter, _av_bin, DIVREF, '+', _direct_pass(bound_meter, float(exclusive)))), '*', closeness), '*', maturity), '*', scale))
        if _av_cmp(dividend, '>', DIVTOTAL):
            dividend = DIVTOTAL
        joint = _direct_bin(bound_meter, _av_bin, core, '+', dividend)
        repair_shadow = None
        if _av_cmp(anchor, 'is not', None):
            shadow = dividend
            for position in _av_iter(_direct_pass(bound_meter, range(_direct_pass(bound_meter, len(routes))))):
                if _av_cmp(position, '==', winner):
                    continue
                route = _direct_sub(bound_meter, _av_sub, bound_cap, routes, position)
                detail = _direct_sub(bound_meter, _av_sub, bound_cap, route, 4)
                if _av_cmp(detail, 'is', None) or _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, detail, 5), '<=', 0.0):
                    continue
                overlap = 0
                for code in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, route, 2)):
                    if _av_cmp(code, 'in', occupied) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, stock, _direct_sub(bound_meter, _av_sub, bound_cap, codeindex, code)), 0), '>', 0.0):
                        overlap = _direct_bin(bound_meter, _av_bin, overlap, '+', 1)
                if _av_cmp(overlap, '>', 0):
                    gapvalue = _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, core, '-', _direct_sub(bound_meter, _av_sub, bound_cap, route, 0))))
                    distgap = _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, route, 1), '-', _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, winner), 1))))
                    closeness = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, DIVCLOSE, '*', gapvalue)))
                    maturity = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, DIVGAP, '*', distgap)))
                    shadow = _direct_bin(bound_meter, _av_bin, shadow, '+', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, DIVCAP, '*', _direct_pass(bound_meter, float(overlap))), '/', _direct_bin(bound_meter, _av_bin, DIVREF, '+', _direct_pass(bound_meter, float(overlap)))), '*', _direct_sub(bound_meter, _av_sub, bound_cap, detail, 5)), '*', closeness), '*', maturity), '*', scale))
            repair_shadow = _direct_bin(bound_meter, _av_bin, core, '+', _direct_pass(bound_meter, min(DIVTOTAL, shadow)))
        option = None
        for position in _av_iter(_direct_pass(bound_meter, range(plainroutes, _direct_pass(bound_meter, len(routes))))):
            detail = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, position), 4)
            if _av_cmp(detail, 'is not', None):
                gain = _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, position), 0), '-', plaincore)
                if _av_cmp(gain, '>', 0.0) and (_av_cmp(option, 'is', None) or _av_cmp(gain, '>', _direct_sub(bound_meter, _av_sub, bound_cap, option, 0))):
                    option = (gain, _direct_sub(bound_meter, _av_sub, bound_cap, detail, 0), _direct_sub(bound_meter, _av_sub, bound_cap, detail, 1), _direct_sub(bound_meter, _av_sub, bound_cap, detail, 2), _direct_sub(bound_meter, _av_sub, bound_cap, detail, 3), _direct_sub(bound_meter, _av_sub, bound_cap, detail, 4))
        known = _direct_sub(bound_meter, _av_sub, bound_cap, payment, 2)
        unknown = _direct_pass(bound_meter, len(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'qualification_unknown_codes')))
        if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 0), '==', 0):
            qualcost = QUALUNANALYSED
        else:
            qualcost = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, QUALUNKNOWN, '*', _direct_pass(bound_meter, float(unknown))), '/', _direct_pass(bound_meter, float(_direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, 1, '+', known), '+', unknown))))
        if _av_cmp(anchor, 'is not', None):
            ready = _direct_pass(bound_meter, huoffer(anchor, discount, risk, payment, option, plaincore))
            value = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, HUBASE, '+', anchor), '+', _direct_sub(bound_meter, _av_sub, bound_cap, ready, 0)), '-', qualcost), '-', unknowncost)
        else:
            ready = None
            value = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, WAITBASE, '+', joint), '-', qualcost), '-', unknowncost), '-', _direct_bin(bound_meter, _av_bin, UNANCHOREXPOSURE, '*', risk))
        prepstats = (prepneed, prepdiscard, prepwidth, readiness)
        facts = (value, joint, plaincore, core, dividend, _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, routes, winner), 3), payment, option, qualcost, ready, prepstats, repair_shadow)
        return (value, facts)
    
    def rank_continuation_ties(entries, quality_rows):
        """只细分主报价相同的弃牌；每组最高报价及所有Hu报价保持。
    
        辅助质量只用于已报价相同的继续动作，不补概率、不改变原不同
        价组的顺序，也不提高弃胡诱因。输入entries是本调用新建的输出。
        """
        bases = _av_wrap_dict({_av_key(_direct_pass(bound_meter, _direct_sub(bound_meter, _av_sub, bound_cap, entry, 'action_key'))): _direct_pass(bound_meter, _direct_sub(bound_meter, _av_sub, bound_cap, entry, 'score')) for entry in _av_iter(entries)})
        qualities = _av_wrap_dict({_av_key(_direct_pass(bound_meter, _direct_sub(bound_meter, _av_sub, bound_cap, row, 0))): _direct_pass(bound_meter, _direct_sub(bound_meter, _av_sub, bound_cap, row, 1)) for row in _av_iter(quality_rows)})
        ranked = _av_wrap_list([])
        for entry in _av_iter(entries):
            key = _direct_sub(bound_meter, _av_sub, bound_cap, entry, 'action_key')
            if _av_cmp(key, 'not in', qualities):
                _direct_pass(bound_meter, _av_method(ranked, 'append')(entry))
                continue
            base = _direct_sub(bound_meter, _av_sub, bound_cap, bases, key)
            peak = _direct_sub(bound_meter, _av_sub, bound_cap, qualities, key)
            members = 0
            for peer in _av_iter(entries):
                peerkey = _direct_sub(bound_meter, _av_sub, bound_cap, peer, 'action_key')
                if _av_cmp(peerkey, 'in', qualities) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, bases, peerkey), '==', base):
                    members = _direct_bin(bound_meter, _av_bin, members, '+', 1)
                    if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, qualities, peerkey), '>', peak):
                        peak = _direct_sub(bound_meter, _av_sub, bound_cap, qualities, peerkey)
            difference = _direct_bin(bound_meter, _av_bin, peak, '-', _direct_sub(bound_meter, _av_sub, bound_cap, qualities, key))
            if _av_cmp(members, '<', 2) or _av_cmp(difference, '<=', 0.0):
                _direct_pass(bound_meter, _av_method(ranked, 'append')(entry))
                continue
            gap = None
            for peer in _av_iter(entries):
                distance = _direct_bin(bound_meter, _av_bin, base, '-', _direct_sub(bound_meter, _av_sub, bound_cap, bases, _direct_sub(bound_meter, _av_sub, bound_cap, peer, 'action_key')))
                if _av_cmp(distance, '>', 0.0) and (_av_cmp(gap, 'is', None) or _av_cmp(distance, '<', gap)):
                    gap = distance
            limit = DIVTOTAL if _av_cmp(gap, 'is', None) else _direct_pass(bound_meter, min(DIVTOTAL, _direct_bin(bound_meter, _av_bin, gap, '/', 4.0)))
            penalty = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, limit, '*', difference), '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', difference))
            trace_rows = _av_wrap_list([_direct_pass(bound_meter, (name, value)) for name, value in _av_iter(_direct_pass(bound_meter, _av_method(_direct_sub(bound_meter, _av_sub, bound_cap, entry, 'trace'), 'items')()))])
            _direct_pass(bound_meter, _av_method(trace_rows, 'append')(('repair_base_score', base)))
            _direct_pass(bound_meter, _av_method(trace_rows, 'append')(('repair_tie_penalty', penalty)))
            _direct_pass(bound_meter, _av_method(ranked, 'append')(_av_dict_lit((('action_key', key), ('score', _direct_bin(bound_meter, _av_bin, base, '-', penalty)), ('trace', _direct_pass(bound_meter, dict(trace_rows)))))))
        return ranked
    
    def score_actions(view):
        """对冻结后序共享图一次计算；每个合法根恰一条有限评分与有界解释。
    
        choices在全部合法续行中择优；condition与replacement消费全部互斥边
        的下端加有界均值差，不挑最好补牌；未知补牌读真实前态并折价。无
        文件、网络、时钟、随机或跨调用缓存；不筛掉任何合法根。
        """
        if _av_cmp(_direct_pass(bound_meter, _av_method(view, 'get')('schema_version')), '!=', 'vip-route-scoring-view/3') or _av_cmp(_direct_pass(bound_meter, _av_method(view, 'get')('graph_schema_version')), '!=', 'vip-route-action-graph/3'):
            return _av_dict_lit((('status', 'ABSTAIN'), ('reason', 'unsupported_view')))
        context = _direct_sub(bound_meter, _av_sub, bound_cap, view, 'visible_state')
        seat = _direct_sub(bound_meter, _av_sub, bound_cap, context, 'seat')
        base = _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, view, 'binding'), 'base_score')))
        wall = _direct_sub(bound_meter, _av_sub, bound_cap, context, 'remaining_tile_count')
        dealerboost = DEALERBOOST if _av_cmp(seat, '==', _direct_sub(bound_meter, _av_sub, bound_cap, context, 'dealer_seat')) else 1.0
        opponents = 0
        for otherseat, melds in _av_iter(_direct_pass(bound_meter, enumerate(_direct_sub(bound_meter, _av_sub, bound_cap, context, 'melds')))):
            if _av_cmp(otherseat, '!=', seat):
                opponents = _direct_bin(bound_meter, _av_bin, opponents, '+', _direct_pass(bound_meter, len(melds)))
        pressure = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, OPPDECAY, '*', _direct_pass(bound_meter, float(opponents)))))
        if _av_cmp(wall, 'is', None):
            room = None
            drawscale = UNKNOWNWALLSCALE
            discount = _direct_bin(bound_meter, _av_bin, drawscale, '*', pressure)
            risk = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, RISKBASE, '+', _direct_bin(bound_meter, _av_bin, OPPRISK, '*', _direct_pass(bound_meter, float(opponents)))), '+', UNKNOWNWALLRISK)
        else:
            margin = _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(wall)), '-', _direct_pass(bound_meter, float(RETENTION)))))
            room = _direct_pass(bound_meter, max(1.0, _direct_bin(bound_meter, _av_bin, margin, '/', 4.0)))
            drawscale = 1.0 if _av_cmp(margin, '>', 0.0) else 0.0
            discount = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, drawscale, '*', pressure), '*', _direct_bin(bound_meter, _av_bin, 0.3, '+', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, 0.7, '*', margin), '/', _direct_bin(bound_meter, _av_bin, WALLSOFT, '+', margin))))
            risk = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, RISKBASE, '+', _direct_bin(bound_meter, _av_bin, OPPRISK, '*', _direct_pass(bound_meter, float(opponents)))), '+', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, LATERISK, '*', WALLSOFT), '/', _direct_bin(bound_meter, _av_bin, WALLSOFT, '+', margin)))
        codeindex = _av_wrap_dict({_av_key(_direct_pass(bound_meter, code)): _direct_pass(bound_meter, index) for index, code in _av_iter(_direct_pass(bound_meter, enumerate(_direct_sub(bound_meter, _av_sub, bound_cap, view, 'tile_order'))))})
        nodes = _direct_sub(bound_meter, _av_sub, bound_cap, view, 'nodes')
        indexes = _av_wrap_dict({_av_key(_direct_pass(bound_meter, _direct_sub(bound_meter, _av_sub, bound_cap, node, 'node_key'))): _direct_pass(bound_meter, index) for index, node in _av_iter(_direct_pass(bound_meter, enumerate(nodes)))})
        anchor = None
        for action in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, view, 'actions')):
            node = _direct_sub(bound_meter, _av_sub, bound_cap, nodes, _direct_sub(bound_meter, _av_sub, bound_cap, indexes, _direct_sub(bound_meter, _av_sub, bound_cap, action, 'node_key')))
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, node, 'kind'), '==', 'hu'):
                point = _direct_pass(bound_meter, paypoints(_direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, node, 'settlement'), 'score_delta'), seat))), '/', base)))
                if _av_cmp(anchor, 'is', None) or _av_cmp(point, '>', anchor):
                    anchor = point
        values = _av_wrap_list([])
        factslist = _av_wrap_list([])
        for node in _av_iter(nodes):
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, node, 'gap_kind'), 'is not', None):
                return _av_dict_lit((('status', 'ABSTAIN'), ('reason', 'graph_gap')))
            kind = _direct_sub(bound_meter, _av_sub, bound_cap, node, 'kind')
            children = _direct_sub(bound_meter, _av_sub, bound_cap, node, 'children')
            if _av_cmp(kind, '==', 'wait') or _av_cmp(kind, '==', 'unknown_draw'):
                if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, node, 'waiting'), 'is', None):
                    return _av_dict_lit((('status', 'ABSTAIN'), ('reason', 'missing_waiting')))
                unknowncost = UNKNOWNDRAW if _av_cmp(kind, '==', 'unknown_draw') else 0.0
                value, facts = _direct_pass(bound_meter, routewait(_direct_sub(bound_meter, _av_sub, bound_cap, node, 'waiting'), codeindex, seat, base, room, drawscale, pressure, discount, risk, anchor, unknowncost, dealerboost))
            elif _av_cmp(kind, '==', 'hu'):
                value = _direct_bin(bound_meter, _av_bin, HUBASE, '+', _direct_pass(bound_meter, paypoints(_direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, node, 'settlement'), 'score_delta'), seat))), '/', base))))
                facts = None
            elif _av_cmp(kind, '==', 'choices'):
                if _av_un('not', children):
                    return _av_dict_lit((('status', 'ABSTAIN'), ('reason', 'empty_choices')))
                selected = _direct_sub(bound_meter, _av_sub, bound_cap, indexes, _direct_sub(bound_meter, _av_sub, bound_cap, children, 0))
                for child in _av_iter(children):
                    candidate = _direct_sub(bound_meter, _av_sub, bound_cap, indexes, child)
                    if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, values, candidate), '>', _direct_sub(bound_meter, _av_sub, bound_cap, values, selected)):
                        selected = candidate
                value = _direct_sub(bound_meter, _av_sub, bound_cap, values, selected)
                facts = _direct_sub(bound_meter, _av_sub, bound_cap, factslist, selected)
            elif _av_cmp(kind, '==', 'replacement') or _av_cmp(kind, '==', 'condition'):
                if _av_un('not', children):
                    return _av_dict_lit((('status', 'ABSTAIN'), ('reason', 'empty_condition')))
                lower = _direct_sub(bound_meter, _av_sub, bound_cap, values, _direct_sub(bound_meter, _av_sub, bound_cap, indexes, _direct_sub(bound_meter, _av_sub, bound_cap, children, 0)))
                total = 0.0
                for child in _av_iter(children):
                    childvalue = _direct_sub(bound_meter, _av_sub, bound_cap, values, _direct_sub(bound_meter, _av_sub, bound_cap, indexes, child))
                    if _av_cmp(childvalue, '<', lower):
                        lower = childvalue
                    total = _direct_bin(bound_meter, _av_bin, total, '+', childvalue)
                mean = _direct_bin(bound_meter, _av_bin, total, '/', _direct_pass(bound_meter, float(_direct_pass(bound_meter, len(children)))))
                blend = REPLACEMENTBLEND if _av_cmp(kind, '==', 'replacement') else CONDITIONBLEND
                cap = REPLACEMENTCAP if _av_cmp(kind, '==', 'replacement') else CONDITIONCAP
                value = _direct_bin(bound_meter, _av_bin, lower, '+', _direct_pass(bound_meter, min(cap, _direct_bin(bound_meter, _av_bin, blend, '*', _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, mean, '-', lower)))))))
                facts = None
            else:
                return _av_dict_lit((('status', 'ABSTAIN'), ('reason', 'unknown_node_kind')))
            _direct_pass(bound_meter, _av_method(values, 'append')(value))
            _direct_pass(bound_meter, _av_method(factslist, 'append')(facts))
        entries = _av_wrap_list([])
        repair_quality_rows = _av_wrap_list([])
        actioncount = _direct_pass(bound_meter, len(_direct_sub(bound_meter, _av_sub, bound_cap, view, 'actions')))
        for action in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, view, 'actions')):
            index = _direct_sub(bound_meter, _av_sub, bound_cap, indexes, _direct_sub(bound_meter, _av_sub, bound_cap, action, 'node_key'))
            kind = _direct_sub(bound_meter, _av_sub, bound_cap, action, 'action_type')
            adjustment = 0.0
            if _av_cmp(kind, '==', 'chi') or _av_cmp(kind, '==', 'peng'):
                adjustment = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, SKIPVALUE, '*', _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, action, 'skipped_seats')))), '*', drawscale), '-', CLAIMCOST)
            elif _av_cmp(kind, '==', 'gang'):
                adjustment = _av_un('-', GANGCOST)
            value = _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, values, index), '+', adjustment)
            pairs = _av_wrap_list([('condition', _direct_sub(bound_meter, _av_sub, bound_cap, action, 'pending_condition')), ('adjust', _direct_pass(bound_meter, round(adjustment, 3)))])
            facts = _direct_sub(bound_meter, _av_sub, bound_cap, factslist, index)
            if _av_cmp(facts, 'is not', None) and _av_cmp(actioncount, '<=', 24):
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('frontier', (_direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 1), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 2), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 3), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 4), 3)), _direct_sub(bound_meter, _av_sub, bound_cap, facts, 5)))))
                payment = _direct_sub(bound_meter, _av_sub, bound_cap, facts, 6)
                if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 1), 'is', None):
                    average = None
                else:
                    average = _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 1), 3))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('pay', (_direct_sub(bound_meter, _av_sub, bound_cap, payment, 0), average, _direct_sub(bound_meter, _av_sub, bound_cap, payment, 2), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 3), 3))))))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('target', None if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 7), 'is', None) else (_direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 7), 0), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 7), 1), 3)), _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 7), 2), _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 7), 3), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 7), 4), 3))))))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('prep', (_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 10), 0), _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 10), 1), _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 10), 2), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 10), 3), 3))))))
                offer = _direct_sub(bound_meter, _av_sub, bound_cap, facts, 9)
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('offer', None if _av_cmp(offer, 'is', None) else (_direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, offer, 0), 3)), _direct_sub(bound_meter, _av_sub, bound_cap, offer, 1), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, offer, 4), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, offer, 5), 3))))))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('qualification_cost', _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 8), 3)))))
            if _av_cmp(facts, 'is not', None) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 11), 'is not', None):
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('repair_shadow', _direct_sub(bound_meter, _av_sub, bound_cap, facts, 11))))
                if _av_cmp(kind, '==', 'discard'):
                    _direct_pass(bound_meter, _av_method(repair_quality_rows, 'append')((_direct_sub(bound_meter, _av_sub, bound_cap, action, 'action_key'), _direct_sub(bound_meter, _av_sub, bound_cap, facts, 11))))
            if _av_un('not', entries):
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('unit', 'heuristic_rank_points')))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('formula', 'vip-g37-fee-and-continuation-tie/1')))
                if _av_cmp(anchor, 'is', None):
                    anchorvalue = None
                else:
                    anchorvalue = _direct_pass(bound_meter, round(anchor, 3))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('context', (wall, opponents, _direct_pass(bound_meter, round(dealerboost, 3)), _direct_pass(bound_meter, round(discount, 3)), _direct_pass(bound_meter, round(risk, 3)), anchorvalue))))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('unknown', 'opponent_hu_and_future_draw_reachability')))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('scope', 'conditional_facts_not_probability_or_guaranteed_highfan')))
            _direct_pass(bound_meter, _av_method(entries, 'append')(_av_dict_lit((('action_key', _direct_sub(bound_meter, _av_sub, bound_cap, action, 'action_key')), ('score', value), ('trace', _direct_pass(bound_meter, dict(pairs)))))))
        if _av_cmp(anchor, 'is not', None):
            entries = _direct_pass(bound_meter, rank_continuation_ties(entries, repair_quality_rows))
        return _av_dict_lit((('status', 'SCORED'), ('entries', entries)))
    return {"__builtins__": {},
        '_av_bin': _av_bin,
        '_av_cmp': _av_cmp,
        '_av_dict_lit': _av_dict_lit,
        '_av_fvalue': _av_fvalue,
        '_av_iter': _av_iter,
        '_av_key': _av_key,
        '_av_method': _av_method,
        '_av_pass': _av_pass,
        '_av_set_lit': _av_set_lit,
        '_av_sub': _av_sub,
        '_av_un': _av_un,
        '_av_wrap_dict': _av_wrap_dict,
        '_av_wrap_list': _av_wrap_list,
        'abs': abs,
        'all': all,
        'any': any,
        'bool': bool,
        'dict': dict,
        'enumerate': enumerate,
        'filter': filter,
        'float': float,
        'frozenset': frozenset,
        'int': int,
        'len': len,
        'list': list,
        'map': map,
        'max': max,
        'min': min,
        'range': range,
        'reversed': reversed,
        'round': round,
        'set': set,
        'sorted': sorted,
        'sum': sum,
        'tuple': tuple,
        'zip': zip,
        'PAYCAP': PAYCAP,
        'PAYREF': PAYREF,
        'PAYMASSREF': PAYMASSREF,
        'HUBASE': HUBASE,
        'WAITBASE': WAITBASE,
        'FORMCOST': FORMCOST,
        'TAILOFF': TAILOFF,
        'TAILQUAD': TAILQUAD,
        'SPEEDCAP': SPEEDCAP,
        'SPEEDREF': SPEEDREF,
        'VARREF': VARREF,
        'LINKCAP': LINKCAP,
        'UNSEENSOFT': UNSEENSOFT,
        'PURPOSES': PURPOSES,
        'DEALERBOOST': DEALERBOOST,
        'WHITEHOLD': WHITEHOLD,
        'EXTRAPATH': EXTRAPATH,
        'ACTREF': ACTREF,
        'DIVCAP': DIVCAP,
        'DIVREF': DIVREF,
        'DIVGAP': DIVGAP,
        'DIVCLOSE': DIVCLOSE,
        'DIVTOTAL': DIVTOTAL,
        'PREPBASE': PREPBASE,
        'PREPMATURE': PREPMATURE,
        'LOCALCAP': LOCALCAP,
        'LOCALREF': LOCALREF,
        'COVREF': COVREF,
        'ENVELOPEBLEND': ENVELOPEBLEND,
        'SINGLESCOPE': SINGLESCOPE,
        'PAIRPRIORWEIGHT': PAIRPRIORWEIGHT,
        'HORIZONCOST': HORIZONCOST,
        'RETENTION': RETENTION,
        'WALLSOFT': WALLSOFT,
        'UNKNOWNWALLSCALE': UNKNOWNWALLSCALE,
        'OPPDECAY': OPPDECAY,
        'RISKBASE': RISKBASE,
        'OPPRISK': OPPRISK,
        'LATERISK': LATERISK,
        'UNKNOWNWALLRISK': UNKNOWNWALLRISK,
        'QUALUNKNOWN': QUALUNKNOWN,
        'QUALUNANALYSED': QUALUNANALYSED,
        'UNKNOWNDRAW': UNKNOWNDRAW,
        'UNANCHOREXPOSURE': UNANCHOREXPOSURE,
        'CONDITIONBLEND': CONDITIONBLEND,
        'CONDITIONCAP': CONDITIONCAP,
        'REPLACEMENTBLEND': REPLACEMENTBLEND,
        'REPLACEMENTCAP': REPLACEMENTCAP,
        'CLAIMCOST': CLAIMCOST,
        'SKIPVALUE': SKIPVALUE,
        'GANGCOST': GANGCOST,
        'ANCHOROPTIONBASE': ANCHOROPTIONBASE,
        'ANCHOROPTIONSTEP': ANCHOROPTIONSTEP,
        'ANCHORFALLBACKCOST': ANCHORFALLBACKCOST,
        'ANCHORUNKNOWNCOST': ANCHORUNKNOWNCOST,
        'NETUPGRADEWEIGHT': NETUPGRADEWEIGHT,
        'NETUPWIDTHREF': NETUPWIDTHREF,
        'NETEXITWIDTHREF': NETEXITWIDTHREF,
        'NETANCHORPRICE': NETANCHORPRICE,
        'NETRISKFEE': NETRISKFEE,
        'NETCARRY': NETCARRY,
        'paypoints': paypoints,
        'stockof': stockof,
        'summaryof': summaryof,
        'speedof': speedof,
        'ladder': ladder,
        'horizon': horizon,
        'paysummary': paysummary,
        'payroute': payroute,
        'huoffer': huoffer,
        'routewait': routewait,
        'rank_continuation_ties': rank_continuation_ties,
        'score_actions': score_actions,
    }
