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
    """m1联合公式：凸保白用途先验、单次额外物理负担与单一胡机会费的联合排序。"""
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
    DEALERBOOST = 1.2
    HORIZONCOST = 0.35
    RETENTION = 20
    WALLSOFT = 8.0
    UNKNOWNWALLSCALE = 0.7
    OPPDECAY = 0.05
    RISKBASE = 1.8
    OPPRISK = 0.12
    LATERISK = 3.4
    UNKNOWNWALLRISK = 0.7
    MATURELINEAR = 0.35
    RESCUEDECAY = 0.3
    EXITFLOOR = 0.4
    EXITMASSREF = 6.0
    EXITWIDTHREF = 3.0
    EXITSTEPDECAY = 0.25
    TARGETGATEBASE = 0.5
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
    NETCARRY = 0.25
    NETANCHORPRICE = 0.3
    NETRISKFEE = 0.45
    BRANCHGAP = 0.15
    PREPBUDGET = 0.6
    PAIRPRIORWEIGHT = 0.3
    
    def paypoints(amount):
        """本家净积分除基础分后的有界排序点；不是未来积分或摸牌概率。"""
        return _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, PAYCAP, '*', amount), '/', _direct_bin(bound_meter, _av_bin, PAYREF, '+', _direct_pass(bound_meter, abs(amount))))
    
    def stockof(slot, waiting):
        """返回排序库存、精确张数与未知标记；公开容量含他家暗牌。
    
        精确零关闭本码；保守正下界支持排序；保守零与未知保留软支持，
        不写回资格或支付，也不除以墙余冒充概率。
        """
        capacity = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'unseen_capacities'), slot)
        evidence = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'unseen_evidence'), slot)
        if _av_cmp(evidence, '==', 'exact') and _av_cmp(capacity, 'is not', None):
            return (_direct_pass(bound_meter, float(capacity)), capacity, 0)
        if _av_cmp(evidence, '==', 'conservative') and _av_cmp(capacity, 'is not', None) and _av_cmp(capacity, '>', 0):
            return (_direct_pass(bound_meter, float(capacity)), 0, 1)
        return (UNSEENSOFT, 0, 1)
    
    def routesupport(codes, codeindex, drawscale, stock):
        """按规范牌码去重的一步推进支持；同码只计一次，不跨路线相加。"""
        mass = 0.0
        exact = 0
        width = 0
        uncertain = 0
        seen = _direct_pass(bound_meter, set())
        for code in _av_iter(codes):
            if _av_cmp(code, 'not in', seen):
                _direct_pass(bound_meter, _av_method(seen, 'add')(code))
                cell = _direct_sub(bound_meter, _av_sub, bound_cap, stock, _direct_sub(bound_meter, _av_sub, bound_cap, codeindex, code))
                if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, cell, 0), '>', 0.0):
                    mass = _direct_bin(bound_meter, _av_bin, mass, '+', _direct_sub(bound_meter, _av_sub, bound_cap, cell, 0))
                    exact = _direct_bin(bound_meter, _av_bin, exact, '+', _direct_sub(bound_meter, _av_sub, bound_cap, cell, 1))
                    width = _direct_bin(bound_meter, _av_bin, width, '+', 1)
                    uncertain = _direct_bin(bound_meter, _av_bin, uncertain, '+', _direct_sub(bound_meter, _av_sub, bound_cap, cell, 2))
        credit = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, drawscale, '*', SPEEDCAP), '*', mass), '/', _direct_bin(bound_meter, _av_bin, SPEEDREF, '+', mass)), '*', _direct_pass(bound_meter, float(width))), '/', _direct_bin(bound_meter, _av_bin, VARREF, '+', _direct_pass(bound_meter, float(width))))
        return (credit, mass, width, exact, uncertain)
    
    def purposescale(burden, room, drawscale, pressure):
        """墙余可行性与公开副露压力的条件折减；burden不是保证摸牌次数。"""
        excess = 0.0 if _av_cmp(room, 'is', None) else _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(burden)), '-', room)))
        return _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, drawscale, '*', pressure), '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, HORIZONCOST, '*', excess)))
    
    def prepvalue(waiting):
        """不借白、不含将的自然面子准备事实与单一负担成熟度系数。"""
        prep = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'natural_preparation')
        need = _direct_sub(bound_meter, _av_sub, bound_cap, prep, 'natural_draw_lower_bound')
        discard = _direct_sub(bound_meter, _av_sub, bound_cap, prep, 'natural_discard_lower_bound')
        width = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'natural_preparation_code_width')
        burden = _direct_pass(bound_meter, float(_direct_pass(bound_meter, max(need, discard))))
        readiness = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, MATURELINEAR, '*', burden)))
        if _av_cmp(need, '>', 0) and _av_cmp(width, '==', 0):
            readiness = 0.0
        return (need, discard, width, readiness)
    
    def actualroute(shanten, support, structural):
        """真实向听加出口支持的路线上限；L不是保证还需摸几次。"""
        length = _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, max(0, shanten)), '+', 1)
        value = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, support, 0), '-', _direct_bin(bound_meter, _av_bin, FORMCOST, '*', _direct_pass(bound_meter, float(_direct_bin(bound_meter, _av_bin, length, '-', 1))))), '+', structural)
        return (shanten, length, _direct_sub(bound_meter, _av_sub, bound_cap, support, 0), _direct_sub(bound_meter, _av_sub, bound_cap, support, 1), _direct_sub(bound_meter, _av_sub, bound_cap, support, 2), _direct_sub(bound_meter, _av_sub, bound_cap, support, 4), value)
    
    def paysummary(waiting, seat, base):
        """条件胡支付的逐码包络摘要；同码两抓打假设互斥，只取下端加有界价差。
    
        返回状态、容量加权平均点、码数、总容量与逐码(容量,包络点)。
        状态0未分析、1已知空、2有支付、3部分未知；未知码不当零支付。
        """
        payments = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'normal_draw_hu_payments')
        if _av_cmp(payments, 'is', None):
            return (0, None, 0, 0.0, ())
        partial = _av_cmp(_direct_pass(bound_meter, len(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'qualification_unknown_codes'))), '>', 0)
        if _av_un('not', payments):
            if partial:
                return (3, 0.0, 0, 0.0, ())
            return (1, 0.0, 0, 0.0, ())
        groups = _av_wrap_list([])
        currentcode = None
        lower = 0.0
        upper = 0.0
        capacity = 0.0
        rows = 0
        for payment in _av_iter(payments):
            amount = _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, payment, 'settlement'), 'score_delta'), seat))), '/', base)
            point = _direct_pass(bound_meter, paypoints(amount))
            code = _direct_sub(bound_meter, _av_sub, bound_cap, payment, 'draw_code')
            if _av_cmp(code, '!=', currentcode):
                if _av_cmp(currentcode, 'is not', None):
                    _direct_pass(bound_meter, _av_method(groups, 'append')((capacity, lower, upper, rows)))
                currentcode = code
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
        state = 3 if partial else 2
        return (state, _direct_bin(bound_meter, _av_bin, total, '/', mass), _direct_pass(bound_meter, len(offers)), mass, _direct_pass(bound_meter, tuple(offers)))
    
    def paycredit(payment, coverage, drawscale, pressure):
        """近条件支付转有限信用；两种变换择大，不重复计同码机会。"""
        point = _direct_sub(bound_meter, _av_sub, bound_cap, payment, 1)
        if _av_cmp(point, 'is', None) or _av_cmp(point, '<=', 0.0):
            return (0.0, 0.0, 0.0)
        scale = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, coverage, '*', drawscale), '*', pressure)
        saturated = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, LOCALCAP, '*', point), '/', _direct_bin(bound_meter, _av_bin, LOCALREF, '+', point)), '*', scale)
        linear = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, KNOWNPAYLINEAR, '*', point), '*', _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, payment, 3), '/', _direct_bin(bound_meter, _av_bin, PAYMASSREF, '+', _direct_sub(bound_meter, _av_sub, bound_cap, payment, 3)))), '*', scale)
        if _av_cmp(linear, '>', saturated):
            return (saturated, linear, linear)
        return (saturated, linear, saturated)
    
    def jointwait(waiting, standard, seven, prep, local, codeindex, room, drawscale, pressure, stock, dealerboost):
        """凸用途先验与单次额外负担的逐目标选择及共享条件图备用组合。
    
        每个目标只为超过其家族普通路线已付摸牌数的不同物理动作付一次
        线性成熟度；平方折减、白弃附加费、阶段差价与准备release加价删除，
        墙余只在可行性门按总负担计一次。主出口、已见证胡码与已选保白
        目标占用的码先删除，同码多来源取最大权重后统一饱和。
        """
        main = standard
        maincodes = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'standard_useful_codes')
        if _av_cmp(seven, 'is not', None) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, seven, 6), '>', _direct_sub(bound_meter, _av_sub, bound_cap, main, 6)):
            main = seven
            maincodes = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'seven_pairs_useful_codes')
        whites = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'structure'), 'whites_held')
        ordinary = _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, main, 6), '+', local)
        best = None
        option = None
        for index, target in _av_iter(_direct_pass(bound_meter, enumerate(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'structure'), 'targets')))):
            route = standard if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, target, 'family'), '==', 'standard') else seven
            if _av_cmp(route, 'is not', None):
                terminal = 1 if _direct_sub(bound_meter, _av_sub, bound_cap, target, 'requires_terminal_draw') else 0
                need = _direct_sub(bound_meter, _av_sub, bound_cap, target, 'natural_need')
                naturaldrop = _direct_sub(bound_meter, _av_sub, bound_cap, target, 'target_natural_discard_lower_bound')
                whitedrop = _direct_sub(bound_meter, _av_sub, bound_cap, target, 'target_white_discard_lower_bound')
                retained = _direct_sub(bound_meter, _av_sub, bound_cap, target, 'retained_whites')
                width = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'target_improvement_code_widths'), index)
                predecessor = _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, target, 'target_stage'), '==', 'waiting_predecessor')
                targetmass = 0.0
                for code in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, target, 'conditional_need_improvement_codes')):
                    targetmass = _direct_bin(bound_meter, _av_bin, targetmass, '+', _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, stock, _direct_sub(bound_meter, _av_sub, bound_cap, codeindex, code)), 0))
                targetgate = 1.0
                if _av_cmp(need, '>', 0):
                    targetgate = 0.0
                    if _av_cmp(width, '>', 0) and _av_cmp(targetmass, '>', 0.0):
                        targetgate = _direct_bin(bound_meter, _av_bin, TARGETGATEBASE, '+', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, 1.0, '-', TARGETGATEBASE), '*', targetmass), '/', _direct_bin(bound_meter, _av_bin, TARGETMASSREF, '+', targetmass)))
                burden = _direct_pass(bound_meter, max(_direct_bin(bound_meter, _av_bin, need, '+', terminal), _direct_bin(bound_meter, _av_bin, naturaldrop, '+', whitedrop)))
                extra = _direct_pass(bound_meter, max(0, _direct_bin(bound_meter, _av_bin, burden, '-', _direct_sub(bound_meter, _av_sub, bound_cap, route, 1))))
                maturity = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, MATURELINEAR, '*', _direct_pass(bound_meter, float(extra)))))
                rescue = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, RESCUEDECAY, '*', _direct_pass(bound_meter, float(extra)))))
                exitmass = _direct_pass(bound_meter, max(0.0, _direct_sub(bound_meter, _av_sub, bound_cap, route, 3)))
                exitwidth = _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, route, 4)))
                exitgate = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, exitmass, '/', _direct_bin(bound_meter, _av_bin, EXITMASSREF, '+', exitmass)), '*', exitwidth), '/', _direct_bin(bound_meter, _av_bin, EXITWIDTHREF, '+', exitwidth))
                exitgate = _direct_bin(bound_meter, _av_bin, exitgate, '/', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, EXITSTEPDECAY, '*', _direct_pass(bound_meter, float(_direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, route, 1), '-', 1))))))
                prior = 0.0
                if predecessor and _av_cmp(retained, '>', 0):
                    prior = _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, PURPOSES, retained), '*', dealerboost)
                exitfactor = _direct_bin(bound_meter, _av_bin, EXITFLOOR, '+', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, 1.0, '-', EXITFLOOR), '*', exitgate))
                purposecredit = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, prior, '*', _direct_pass(bound_meter, purposescale(burden, room, drawscale, pressure))), '*', targetgate), '*', maturity), '*', exitfactor)
                rescued = _direct_bin(bound_meter, _av_bin, local, '*', rescue)
                prospective = _direct_bin(bound_meter, _av_bin, rescued, '+', purposecredit)
                value = _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, route, 6), '+', prospective)
                if _av_cmp(best, 'is', None) or _av_cmp(value, '>', _direct_sub(bound_meter, _av_sub, bound_cap, best, 10)):
                    best = (index, _direct_sub(bound_meter, _av_sub, bound_cap, target, 'family'), retained, need, terminal, burden, naturaldrop, whitedrop, width, prospective, value)
                gain = _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, value, '-', ordinary)))
                if predecessor and _av_cmp(retained, '>', 0) and _av_cmp(retained, '<=', whites) and _av_cmp(gain, '>', 0.0):
                    if _av_cmp(option, 'is', None) or _av_cmp(gain, '>', _direct_sub(bound_meter, _av_sub, bound_cap, option, 8)):
                        option = (index, _direct_sub(bound_meter, _av_sub, bound_cap, target, 'family'), retained, need, width, prior, exitgate, targetgate, gain, targetmass, maturity, extra, rescue, prospective)
        baseline = _direct_pass(bound_meter, set(maincodes))
        knownhu = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'legal_hu_draw_codes')
        if _av_cmp(knownhu, 'is not', None):
            for code in _av_iter(knownhu):
                _direct_pass(bound_meter, _av_method(baseline, 'add')(code))
        primaryvalue = ordinary
        preparationoccupied = 0
        if _av_cmp(best, 'is not', None) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, best, 10), '>', ordinary):
            primaryvalue = _direct_sub(bound_meter, _av_sub, bound_cap, best, 10)
            selected = _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'structure'), 'targets'), _direct_sub(bound_meter, _av_sub, bound_cap, best, 0))
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, selected, 'family'), '==', 'standard'):
                selectedcodes = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'standard_useful_codes')
            else:
                selectedcodes = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'seven_pairs_useful_codes')
            for code in _av_iter(selectedcodes):
                _direct_pass(bound_meter, _av_method(baseline, 'add')(code))
            for code in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, selected, 'conditional_need_improvement_codes')):
                _direct_pass(bound_meter, _av_method(baseline, 'add')(code))
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, selected, 'family'), '==', 'standard') and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, selected, 'target_stage'), '==', 'waiting_predecessor') and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, selected, 'retained_whites'), '>', 0):
                preparationoccupied = 1
                for code in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'natural_preparation'), 'natural_need_improvement_codes')):
                    _direct_pass(bound_meter, _av_method(baseline, 'add')(code))
        plans = _av_wrap_list([])
        branches = _av_wrap_list([(standard, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'standard_useful_codes'))])
        if _av_cmp(seven, 'is not', None):
            _direct_pass(bound_meter, _av_method(branches, 'append')((seven, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'seven_pairs_useful_codes'))))
        for route, codes in _av_iter(branches):
            steps = _direct_pass(bound_meter, float(_direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, route, 1), '-', 1)))
            gap = _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, primaryvalue, '-', _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, route, 6), '+', local))))
            excess = 0.0 if _av_cmp(room, 'is', None) else _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, route, 1))), '-', room)))
            weight = _direct_bin(bound_meter, _av_bin, 1.0, '/', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, steps, '*', steps)), '+', _direct_bin(bound_meter, _av_bin, BRANCHGAP, '*', gap)), '*', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, HORIZONCOST, '*', excess))))
            for code in _av_iter(codes):
                slot = _direct_sub(bound_meter, _av_sub, bound_cap, codeindex, code)
                if _av_cmp(code, 'not in', baseline) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, stock, slot), 0), '>', 0.0):
                    _direct_pass(bound_meter, _av_method(plans, 'append')((slot, weight)))
        if _av_cmp(preparationoccupied, '==', 0) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, prep, 0), '>', 0) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, prep, 2), '>', 0):
            preplength = _direct_pass(bound_meter, max(_direct_sub(bound_meter, _av_sub, bound_cap, standard, 1), _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, prep, 0), '+', 1), _direct_sub(bound_meter, _av_sub, bound_cap, prep, 1)))
            excess = 0.0 if _av_cmp(room, 'is', None) else _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(preplength)), '-', room)))
            gap = _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, primaryvalue, '-', _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, standard, 6), '+', local))))
            prepweight = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, PREPBUDGET, '*', _direct_sub(bound_meter, _av_sub, bound_cap, prep, 3)), '/', _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, BRANCHGAP, '*', gap)), '*', _direct_bin(bound_meter, _av_bin, 1.0, '+', _direct_bin(bound_meter, _av_bin, HORIZONCOST, '*', excess))))
            for code in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'natural_preparation'), 'natural_need_improvement_codes')):
                slot = _direct_sub(bound_meter, _av_sub, bound_cap, codeindex, code)
                if _av_cmp(code, 'not in', baseline) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, stock, slot), 0), '>', 0.0):
                    _direct_pass(bound_meter, _av_method(plans, 'append')((slot, prepweight)))
        combined = _av_wrap_list([])
        currentslot = None
        peak = 0.0
        for plan in _av_iter(_direct_pass(bound_meter, sorted(plans))):
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, plan, 0), '!=', currentslot):
                if _av_cmp(currentslot, 'is not', None):
                    _direct_pass(bound_meter, _av_method(combined, 'append')((currentslot, peak)))
                currentslot = _direct_sub(bound_meter, _av_sub, bound_cap, plan, 0)
                peak = _direct_sub(bound_meter, _av_sub, bound_cap, plan, 1)
            elif _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, plan, 1), '>', peak):
                peak = _direct_sub(bound_meter, _av_sub, bound_cap, plan, 1)
        if _av_cmp(currentslot, 'is not', None):
            _direct_pass(bound_meter, _av_method(combined, 'append')((currentslot, peak)))
        mass = 0.0
        diversity = 0.0
        exact = 0
        codecount = 0
        uncertain = 0
        for entry in _av_iter(combined):
            cell = _direct_sub(bound_meter, _av_sub, bound_cap, stock, _direct_sub(bound_meter, _av_sub, bound_cap, entry, 0))
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, cell, 0), '>', 0.0):
                mass = _direct_bin(bound_meter, _av_bin, mass, '+', _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, entry, 1), '*', _direct_sub(bound_meter, _av_sub, bound_cap, cell, 0)))
                diversity = _direct_bin(bound_meter, _av_bin, diversity, '+', _direct_sub(bound_meter, _av_sub, bound_cap, entry, 1))
                exact = _direct_bin(bound_meter, _av_bin, exact, '+', _direct_sub(bound_meter, _av_sub, bound_cap, cell, 1))
                codecount = _direct_bin(bound_meter, _av_bin, codecount, '+', 1)
                uncertain = _direct_bin(bound_meter, _av_bin, uncertain, '+', _direct_sub(bound_meter, _av_sub, bound_cap, cell, 2))
        credit = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, drawscale, '*', pressure), '*', PORTCAP), '*', mass), '/', _direct_bin(bound_meter, _av_bin, PORTREF, '+', mass)), '*', diversity), '/', _direct_bin(bound_meter, _av_bin, VARREF, '+', diversity))
        if _av_cmp(option, 'is not', None):
            incremental = _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, option, 8), '-', credit)))
            if _av_cmp(incremental, '<=', 0.0):
                option = None
            else:
                option = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, option, _direct_slice(None, 8, None)), '+', (incremental,)), '+', _direct_sub(bound_meter, _av_sub, bound_cap, option, _direct_slice(9, None, None)))
        portfolio = (mass, diversity, exact, codecount, uncertain, credit, _direct_pass(bound_meter, float(_direct_pass(bound_meter, len(baseline)))))
        return (best, portfolio, option)
    
    def huoffer(anchor, discount, risk, payment, main, portfolio, option):
        """当前胡与继续等待的净比较；等待暴露只按一个合并费计一次。
    
        直接升级按同码包络差计算；远目标只消费超过备用信用的增量；
        确定胡的机会成本合并为锚价加风险费的单一exposure，不再分别收
        等待费与距离费。全部是排序点，不是期望积分或存活率。
        """
        mass = _direct_sub(bound_meter, _av_sub, bound_cap, payment, 3)
        width = _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 2)))
        exitgate = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, mass, '/', _direct_bin(bound_meter, _av_bin, PAYMASSREF, '+', mass)), '*', width), '/', _direct_bin(bound_meter, _av_bin, NETEXITWIDTHREF, '+', width))
        preserved = 0.0
        upgradeamount = 0.0
        upgrademass = 0.0
        upgradewidth = 0
        downsideamount = 0.0
        for offer in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 4)):
            capacity = _direct_sub(bound_meter, _av_sub, bound_cap, offer, 0)
            point = _direct_sub(bound_meter, _av_sub, bound_cap, offer, 1)
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
        direct = _direct_bin(bound_meter, _av_bin, upgrade, '-', downside)
        remote = 0.0
        remoteprice = 0.0
        fallback = 0.0
        offervalue = direct
        channel = 'direct_upgrade'
        if _av_cmp(option, 'is not', None):
            remoteprice = _direct_bin(bound_meter, _av_bin, anchor, '*', _direct_bin(bound_meter, _av_bin, ANCHOROPTIONBASE, '+', _direct_bin(bound_meter, _av_bin, ANCHOROPTIONSTEP, '*', _direct_sub(bound_meter, _av_sub, bound_cap, option, 11))))
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 1), 'is', None):
                fallback = _direct_bin(bound_meter, _av_bin, ANCHORUNKNOWNCOST, '*', anchor)
            else:
                fallback = _direct_bin(bound_meter, _av_bin, ANCHORFALLBACKCOST, '*', _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, anchor, '-', _direct_pass(bound_meter, max(0.0, _direct_sub(bound_meter, _av_sub, bound_cap, payment, 1)))))))
            remote = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, discount, '*', _direct_sub(bound_meter, _av_sub, bound_cap, option, 8)), '-', remoteprice), '-', fallback)
            if _av_cmp(remote, '>', offervalue):
                offervalue = remote
                channel = 'completion_gain'
        ordinarycore = _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, main, 6), '+', _direct_sub(bound_meter, _av_sub, bound_cap, portfolio, 5))))
        carry = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, NETCARRY, '*', discount), '*', maintained), '*', ordinarycore)
        if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, main, 0), '<=', 0):
            carry = 0.0
        exposure = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, NETANCHORPRICE, '*', anchor), '+', _direct_bin(bound_meter, _av_bin, NETRISKFEE, '*', risk)), '*', _direct_bin(bound_meter, _av_bin, 1.0, '-', _direct_bin(bound_meter, _av_bin, discount, '*', maintained)))
        net = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, offervalue, '+', carry), '-', exposure)
        return (net, channel, upgrade, downside, maintained, carry, exposure, remote, remoteprice, fallback, offervalue)
    
    def waitvalue(waiting, codeindex, seat, base, room, drawscale, pressure, discount, risk, anchor, unknowncost, dealerboost):
        """同一凸先验与单次负担成本下评价普通出口、七对、逐目标用途与当前胡。"""
        structure = _direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'structure')
        stock = _av_wrap_list([])
        for slot in _av_iter(_direct_pass(bound_meter, range(_direct_pass(bound_meter, len(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'unseen_capacities')))))):
            _direct_pass(bound_meter, _av_method(stock, 'append')(_direct_pass(bound_meter, stockof(slot, waiting))))
        prep = _direct_pass(bound_meter, prepvalue(waiting))
        standard = _direct_pass(bound_meter, actualroute(_direct_sub(bound_meter, _av_sub, bound_cap, structure, 'standard_shanten'), _direct_pass(bound_meter, routesupport(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'standard_useful_codes'), codeindex, drawscale, stock)), 0.0))
        seven = None
        main = standard
        family = 'standard'
        if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, structure, 'seven_pairs_shanten'), 'is not', None):
            sevenlength = _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, max(0, _direct_sub(bound_meter, _av_sub, bound_cap, structure, 'seven_pairs_shanten'))), '+', 1)
            pairprior = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, PAIRPRIORWEIGHT, '*', _direct_pass(bound_meter, float(_direct_pass(bound_meter, min(2, _direct_pass(bound_meter, max(0, _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, structure, 'natural_pair_count'), '-', 4)))))))), '/', _direct_pass(bound_meter, float(sevenlength)))
            seven = _direct_pass(bound_meter, actualroute(_direct_sub(bound_meter, _av_sub, bound_cap, structure, 'seven_pairs_shanten'), _direct_pass(bound_meter, routesupport(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'seven_pairs_useful_codes'), codeindex, drawscale, stock)), _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, pairprior, '*', drawscale), '*', pressure)))
            if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, seven, 6), '>', _direct_sub(bound_meter, _av_sub, bound_cap, main, 6)):
                main = seven
                family = 'seven_pairs'
        payment = _direct_pass(bound_meter, paysummary(waiting, seat, base))
        known = _direct_sub(bound_meter, _av_sub, bound_cap, payment, 2)
        unknown = _direct_pass(bound_meter, len(_direct_sub(bound_meter, _av_sub, bound_cap, waiting, 'qualification_unknown_codes')))
        coverage = _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(known)), '/', _direct_bin(bound_meter, _av_bin, COVREF, '+', _direct_pass(bound_meter, float(known))))
        if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 0), '==', 0):
            qualcost = QUALUNANALYSED
        else:
            qualcost = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, QUALUNKNOWN, '*', _direct_pass(bound_meter, float(unknown))), '/', _direct_pass(bound_meter, float(_direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, 1, '+', known), '+', unknown))))
        credit = _direct_pass(bound_meter, paycredit(payment, coverage, drawscale, pressure))
        local = _direct_sub(bound_meter, _av_sub, bound_cap, credit, 2)
        ordinary = _direct_bin(bound_meter, _av_bin, _direct_sub(bound_meter, _av_sub, bound_cap, main, 6), '+', local)
        best, portfolio, option = _direct_pass(bound_meter, jointwait(waiting, standard, seven, prep, local, codeindex, room, drawscale, pressure, stock, dealerboost))
        joint = ordinary
        chosen = family
        if _av_cmp(best, 'is not', None) and _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, best, 10), '>', joint):
            joint = _direct_sub(bound_meter, _av_sub, bound_cap, best, 10)
            chosen = 'completion_budget'
        joint = _direct_bin(bound_meter, _av_bin, joint, '+', _direct_sub(bound_meter, _av_sub, bound_cap, portfolio, 5))
        if _av_cmp(anchor, 'is not', None):
            ready = _direct_pass(bound_meter, huoffer(anchor, discount, risk, payment, main, portfolio, option))
            value = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, HUBASE, '+', anchor), '+', _direct_sub(bound_meter, _av_sub, bound_cap, ready, 0)), '-', qualcost), '-', unknowncost)
        else:
            ready = None
            value = _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, _direct_bin(bound_meter, _av_bin, WAITBASE, '+', joint), '-', qualcost), '-', unknowncost), '-', _direct_bin(bound_meter, _av_bin, UNANCHOREXPOSURE, '*', risk))
        facts = (standard, seven, best, prep, portfolio, payment, ordinary, joint, chosen, local, qualcost, ready, option)
        return (value, facts)
    
    def score_actions(view):
        """对全部冻结后序节点一次共享计算，并给每个合法根恰一条有限评分。
    
        choices才在合法续行中择优；replacement与condition消费全部相容边
        的下端加有界价差，不挑最好补牌；机械缺口显式弃权。庄家身份只作
        公开先验乘子。无文件、网络、时钟、随机或跨调用缓存。
        """
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
                amount = _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, node, 'settlement'), 'score_delta'), seat))), '/', base)
                point = _direct_pass(bound_meter, paypoints(amount))
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
                unknowncost = UNKNOWNDRAW if _av_cmp(kind, '==', 'unknown_draw') else 0.0
                value, facts = _direct_pass(bound_meter, waitvalue(_direct_sub(bound_meter, _av_sub, bound_cap, node, 'waiting'), codeindex, seat, base, room, drawscale, pressure, discount, risk, anchor, unknowncost, dealerboost))
            elif _av_cmp(kind, '==', 'hu'):
                amount = _direct_bin(bound_meter, _av_bin, _direct_pass(bound_meter, float(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, node, 'settlement'), 'score_delta'), seat))), '/', base)
                value = _direct_bin(bound_meter, _av_bin, HUBASE, '+', _direct_pass(bound_meter, paypoints(amount)))
                facts = None
            elif _av_cmp(kind, '==', 'choices'):
                if _av_un('not', children):
                    return _av_dict_lit((('status', 'ABSTAIN'), ('reason', 'empty_choices')))
                bestindex = _direct_sub(bound_meter, _av_sub, bound_cap, indexes, _direct_sub(bound_meter, _av_sub, bound_cap, children, 0))
                value = _direct_sub(bound_meter, _av_sub, bound_cap, values, bestindex)
                for child in _av_iter(children):
                    childindex = _direct_sub(bound_meter, _av_sub, bound_cap, indexes, child)
                    if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, values, childindex), '>', value):
                        bestindex = childindex
                        value = _direct_sub(bound_meter, _av_sub, bound_cap, values, childindex)
                facts = _direct_sub(bound_meter, _av_sub, bound_cap, factslist, bestindex)
            else:
                if _av_un('not', children):
                    return _av_dict_lit((('status', 'ABSTAIN'), ('reason', 'empty_condition')))
                value = _direct_sub(bound_meter, _av_sub, bound_cap, values, _direct_sub(bound_meter, _av_sub, bound_cap, indexes, _direct_sub(bound_meter, _av_sub, bound_cap, children, 0)))
                total = 0.0
                for child in _av_iter(children):
                    childvalue = _direct_sub(bound_meter, _av_sub, bound_cap, values, _direct_sub(bound_meter, _av_sub, bound_cap, indexes, child))
                    total = _direct_bin(bound_meter, _av_bin, total, '+', childvalue)
                    if _av_cmp(childvalue, '<', value):
                        value = childvalue
                lower = value
                mean = _direct_bin(bound_meter, _av_bin, total, '/', _direct_pass(bound_meter, float(_direct_pass(bound_meter, len(children)))))
                blend = REPLACEMENTBLEND if _av_cmp(kind, '==', 'replacement') else CONDITIONBLEND
                cap = REPLACEMENTCAP if _av_cmp(kind, '==', 'replacement') else CONDITIONCAP
                value = _direct_bin(bound_meter, _av_bin, lower, '+', _direct_pass(bound_meter, min(cap, _direct_bin(bound_meter, _av_bin, blend, '*', _direct_pass(bound_meter, max(0.0, _direct_bin(bound_meter, _av_bin, mean, '-', lower)))))))
                facts = None
            _direct_pass(bound_meter, _av_method(values, 'append')(value))
            _direct_pass(bound_meter, _av_method(factslist, 'append')(facts))
        entries = _av_wrap_list([])
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
                payment = _direct_sub(bound_meter, _av_sub, bound_cap, facts, 5)
                if _av_cmp(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 1), 'is', None):
                    avgpoint = None
                else:
                    avgpoint = _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 1), 3))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('pay', (_direct_sub(bound_meter, _av_sub, bound_cap, payment, 0), avgpoint, _direct_sub(bound_meter, _av_sub, bound_cap, payment, 2), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, payment, 3), 3))))))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('joint', (_direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 6), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 7), 3)), _direct_sub(bound_meter, _av_sub, bound_cap, facts, 8), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 9), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 10), 3))))))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('portfolio', _direct_pass(bound_meter, tuple(_av_wrap_list([_direct_pass(bound_meter, _direct_pass(bound_meter, round(part, 3))) for part in _av_iter(_direct_sub(bound_meter, _av_sub, bound_cap, facts, 4))]))))))
                best = _direct_sub(bound_meter, _av_sub, bound_cap, facts, 2)
                if _av_cmp(best, 'is', None):
                    _direct_pass(bound_meter, _av_method(pairs, 'append')(('target', None)))
                else:
                    _direct_pass(bound_meter, _av_method(pairs, 'append')(('target', (_direct_sub(bound_meter, _av_sub, bound_cap, best, 0), _direct_sub(bound_meter, _av_sub, bound_cap, best, 1), _direct_sub(bound_meter, _av_sub, bound_cap, best, 2), _direct_sub(bound_meter, _av_sub, bound_cap, best, 3), _direct_sub(bound_meter, _av_sub, bound_cap, best, 5), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, best, 9), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, best, 10), 3))))))
                ready = _direct_sub(bound_meter, _av_sub, bound_cap, facts, 11)
                if _av_cmp(ready, 'is', None):
                    _direct_pass(bound_meter, _av_method(pairs, 'append')(('offer', None)))
                else:
                    _direct_pass(bound_meter, _av_method(pairs, 'append')(('offer', (_direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, ready, 0), 3)), _direct_sub(bound_meter, _av_sub, bound_cap, ready, 1), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, ready, 2), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, ready, 3), 3)), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, ready, 4), 3))))))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('prep', (_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 3), 0), _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 3), 1), _direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 3), 2), _direct_pass(bound_meter, round(_direct_sub(bound_meter, _av_sub, bound_cap, _direct_sub(bound_meter, _av_sub, bound_cap, facts, 3), 3), 3))))))
            if _av_un('not', entries):
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('unit', 'heuristic_rank_points')))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('formula', 'vip_convex_purpose_single_burden_m1/1')))
                if _av_cmp(anchor, 'is', None):
                    anchorvalue = None
                else:
                    anchorvalue = _direct_pass(bound_meter, round(anchor, 3))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('context', (wall, opponents, _direct_pass(bound_meter, round(dealerboost, 3)), _direct_pass(bound_meter, round(discount, 3)), _direct_pass(bound_meter, round(risk, 3)), anchorvalue))))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('unknown', 'opponent_hu_and_future_draw_reachability')))
                _direct_pass(bound_meter, _av_method(pairs, 'append')(('scope', 'conditional_facts_not_probability_or_guaranteed_highfan')))
            _direct_pass(bound_meter, _av_method(entries, 'append')(_av_dict_lit((('action_key', _direct_sub(bound_meter, _av_sub, bound_cap, action, 'action_key')), ('score', value), ('trace', _direct_pass(bound_meter, dict(pairs)))))))
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
        'HUBASE': HUBASE,
        'WAITBASE': WAITBASE,
        'FORMCOST': FORMCOST,
        'SPEEDCAP': SPEEDCAP,
        'SPEEDREF': SPEEDREF,
        'VARREF': VARREF,
        'UNSEENSOFT': UNSEENSOFT,
        'PURPOSES': PURPOSES,
        'DEALERBOOST': DEALERBOOST,
        'HORIZONCOST': HORIZONCOST,
        'RETENTION': RETENTION,
        'WALLSOFT': WALLSOFT,
        'UNKNOWNWALLSCALE': UNKNOWNWALLSCALE,
        'OPPDECAY': OPPDECAY,
        'RISKBASE': RISKBASE,
        'OPPRISK': OPPRISK,
        'LATERISK': LATERISK,
        'UNKNOWNWALLRISK': UNKNOWNWALLRISK,
        'MATURELINEAR': MATURELINEAR,
        'RESCUEDECAY': RESCUEDECAY,
        'EXITFLOOR': EXITFLOOR,
        'EXITMASSREF': EXITMASSREF,
        'EXITWIDTHREF': EXITWIDTHREF,
        'EXITSTEPDECAY': EXITSTEPDECAY,
        'TARGETGATEBASE': TARGETGATEBASE,
        'TARGETMASSREF': TARGETMASSREF,
        'PORTCAP': PORTCAP,
        'PORTREF': PORTREF,
        'ENVELOPEBLEND': ENVELOPEBLEND,
        'SINGLESCOPE': SINGLESCOPE,
        'COVREF': COVREF,
        'LOCALCAP': LOCALCAP,
        'LOCALREF': LOCALREF,
        'KNOWNPAYLINEAR': KNOWNPAYLINEAR,
        'PAYMASSREF': PAYMASSREF,
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
        'NETCARRY': NETCARRY,
        'NETANCHORPRICE': NETANCHORPRICE,
        'NETRISKFEE': NETRISKFEE,
        'BRANCHGAP': BRANCHGAP,
        'PREPBUDGET': PREPBUDGET,
        'PAIRPRIORWEIGHT': PAIRPRIORWEIGHT,
        'paypoints': paypoints,
        'stockof': stockof,
        'routesupport': routesupport,
        'purposescale': purposescale,
        'prepvalue': prepvalue,
        'actualroute': actualroute,
        'paysummary': paysummary,
        'paycredit': paycredit,
        'jointwait': jointwait,
        'huoffer': huoffer,
        'waitvalue': waitvalue,
        'score_actions': score_actions,
    }
