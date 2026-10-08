"""候选机制说明：保留父代「就绪—宽度双权前沿」的全部骨架与纪律（未知显式化、compare_legal、逐动作证据折扣、完全无证据落声明下限、全部无证据整批 ABSTAIN、无跨调用状态），只按三段反馈机制假设段的三个候选方向做有界修订——以墙中段权重 band（归一余裕 [0.55, 0.75] 带内 0—1 连续过渡，带外 0）为唯一作用域：①依反馈三-1（墙中段分支聚合压低就绪分支权重、候选偏向宽度而未兑现）把双权插值输入提前 MID_TURN_ADVANCE 并把就绪锁定权重下限从 0 抬到 LOCK_FLOOR_MID；②依反馈三-2（最差半段均值+极差对离散度过敏）把分支聚合从「最差半段向听均值 + max-min 极差」切成「上四分位就绪分位 + 分位数间距」，并在动作级向听缺失时用分位就绪度按 band 折价替代未知；③依反馈三-3（partial 0.92 与缺失 0.78 差距过大、缺失事实被双重惩罚）把该差距按 band 收窄到 0.05；三处一律按 band 插值，故墙前段（band=0）与父代逐点相等，正是反馈三-4 要求保留的反例检验面。"""

# —— 声明常量（不可变；单位、参考尺度与未标定说明见行内注释）——
WALL_REFERENCE = 48.0        # 墙余量参考满值（张）；只把官方墙余量归一为 0—1 余裕
WALL_UNKNOWN_HORIZON = 0.5   # 官方未给墙余量时的声明中性余裕：不外推、不当 0
WALL_FRONT = 0.75            # 修订①②③作用域上界（归一余裕）：band=0，双权/聚合/折扣逐点等于父代
WALL_MID_KNEE = 0.55         # 修订①②③作用域下界（归一余裕）：band=1，三处修订全额生效
MID_TURN_ADVANCE = 0.12      # 修订①：墙中段把双权插值输入提前的归一余裕量（评分点尺度不变）
LOCK_FLOOR_MID = 0.5         # 修订①：墙中段就绪锁定权重下限（带外为 0=父代无下限）
QUANTILE_LOW = 0.25          # 修订②：下四分位（分位数间距下界）
QUANTILE_HIGH = 0.75         # 修订②：上四分位（就绪分位与分位数间距上界）
BRANCH_PROGRESS_STEP = 0.7   # 修订②：动作级向听缺失时分位就绪度的折价进展（评分点/级，<父代 1.1）
EVIDENCE_PARTIAL_MID = 0.95  # 修订③：墙中段 value_coverage=partial 的折扣（父代 0.92）
EVIDENCE_UNRUN_MID = 0.90    # 修订③：墙中段 value_coverage 缺失的折扣（父代 0.78，差距 0.14→0.05）
WIDTH_WEIGHT_LONG = 1.0      # 余裕充足时每张未见有效牌的权重（评分点/张）
WIDTH_WEIGHT_SHORT = 0.15    # 余裕将尽时同一权重被压到的倍率
WIDTH_CAP = 24.0             # 宽度（未见枚数估计）上限，防单一牌效口径吞掉全部排序
WIDTH_NEUTRAL = 6.0          # useful_tiles 未分析时的声明先验宽度（张），不是 0
LOCK_PLENTY_WEIGHT = 0.25    # 余裕充足时「就绪锁定」的权重倍率
LOCK_SCARCE_WEIGHT = 1.0     # 余裕将尽时「就绪锁定」的权重倍率
LOCK_UNIT = 3.0              # 向听 0（听牌）锁定的评分点基数
SHANTEN_REFERENCE = 5        # 中间阶段向听基准；只把向听差转成评分点
SHANTEN_STEP = 1.1           # 向听每减少 1 的评分点
WIN_TIER = 4.0               # 动作后已成胡（向听 -1 或 fact_kind=win）的进展档位
CERTAINTY_TIER = 6.0         # 携带立即结算动作的确定性档位（不参与证据折扣）
SETTLE_FAN_WEIGHT = 1.2      # 每番评分点（未标定参考尺度，不是实际积分读数）
SETTLE_DELTA_WEIGHT = 0.05   # 每分净积分评分点（未标定参考尺度）
ROUTE_WITNESS_BONUS = 0.7    # 每条被见证（或带条件结算）路线的加成
ROUTE_CLOSED_PENALTY = 0.9   # 每条 CLOSED_PROVEN 路线的扣减
ROUTE_CAP = 4                # 路线计数上限：每条路线最多计一次，防单动作撑爆
DISPERSION_WEIGHT = 0.8      # 后续分支向听离散度每档扣减（基由极差改为分位数间距，见修订②）
RETREAT_PENALTY = 1.5        # family_progress=RETREAT 的扣减
CLOSE_PENALTY = 2.5          # family_progress=CLOSE（路线被证关闭）的扣减
ADVANCE_BONUS = 0.8          # family_progress=ADVANCE 的加成
GANG_UNKNOWN_PENALTY = 1.0   # 杠后补牌未知（replacement_draw_unknown=True）的扣减
EVIDENCE_PARTIAL = 0.92      # 父代 partial 折扣（band=0 端点值，修订③带外保持）
EVIDENCE_UNAVAILABLE = 0.6   # value_coverage=unavailable 的折扣（显式不可用，两代一致）
EVIDENCE_UNRUN = 0.78        # 父代「未跑分值分析」折扣（band=0 端点值，修订③带外保持）
UNKNOWN_RANK_PENALTY = 0.6   # 关键口径缺失（向听或宽度）时的同分后置扣减
FLOOR_MARGIN = 1.0           # 完全无证据动作相对已分析最小值的固定间距
SCORE_REFERENCE = 64.0       # 桌内积分差的未标定参考尺度（追赶压力归一用）
AGGRESSION_GAIN = 1.0        # 归一积分差到宽度/锁定权重的线性增益
AGGRESSION_MIN = 0.6         # 追赶压力倍率下界（同时避免除零）
AGGRESSION_MAX = 1.6         # 追赶压力倍率上界


def horizon_of(state):
    """剩余墙比例（0—1）；官方未提供墙余量时返回声明中性值并标记口径。"""
    wall = state.get("remaining_tile_count")
    if wall is None:
        return (WALL_UNKNOWN_HORIZON, "wall_unknown")
    ratio = float(wall) / WALL_REFERENCE
    if ratio < 0.0:
        ratio = 0.0
    if ratio > 1.0:
        ratio = 1.0
    return (ratio, "wall_known")


def mid_band_of(horizon):
    """修订①②③的统一作用域权重 band（0—1）：带外 0、中段及以后 1，带内线性过渡。

    band=0 时三处修订的每一处都退化为父代表达式（提前量 0、锁定下限 0、离散度基
    为父代极差、证据折扣取父代端点），故墙前段排序与父代逐点一致。
    """
    if horizon >= WALL_FRONT:
        return 0.0
    if horizon <= WALL_MID_KNEE:
        return 1.0
    return (WALL_FRONT - horizon) / (WALL_FRONT - WALL_MID_KNEE)


def aggression_of(state, competition, seat):
    """追赶压力倍率：落后>1（偏宽度），领先<1（偏就绪锁定），无基准时中性 1。"""
    scores = None
    source = "unavailable"
    if competition is not None:
        scores = competition.get("stage_scores")
        if scores is None:
            scores = competition.get("table_scores")
        if scores is not None:
            source = "competition"
    if scores is None:
        scores = state.get("table_scores")
        if scores is not None:
            source = "table_scores"
    if scores is None or seat is None:
        return (1.0, "unavailable")
    if seat < 0 or seat >= len(scores):
        return (1.0, "seat_out_of_range")
    total = 0.0
    others = 0
    for index in range(len(scores)):
        if index != seat:
            total = total + float(scores[index])
            others = others + 1
    if others == 0:
        return (1.0, "no_other_seats")
    gap = (float(scores[seat]) - total / float(others)) / SCORE_REFERENCE
    if gap > 1.0:
        gap = 1.0
    if gap < -1.0:
        gap = -1.0
    value = 1.0 - AGGRESSION_GAIN * gap
    if value < AGGRESSION_MIN:
        value = AGGRESSION_MIN
    if value > AGGRESSION_MAX:
        value = AGGRESSION_MAX
    return (value, source)


def pick_shanten(action):
    """动作后向听：优先综合口径，退化到普通/七对较小者；三项全缺返回 None。"""
    combined = action.get("shanten_after")
    if combined is not None:
        return combined
    standard = action.get("standard_shanten_after")
    seven = action.get("seven_pairs_shanten_after")
    if standard is None and seven is None:
        return None
    if standard is None:
        return seven
    if seven is None:
        return standard
    if seven < standard:
        return seven
    return standard


def useful_width(tiles):
    """有效牌宽度：去重牌码数、未见枚数估计、枚数缺失计数；None=未分析。"""
    if tiles is None:
        return None
    seen = set()
    total = 0.0
    missing = 0
    for item in tiles:
        code = item.get("code")
        if code is None:
            return None
        seen.add(code)
        remaining = item.get("remaining_estimate")
        if remaining is None:
            total = total + 1.0
            missing = missing + 1
        else:
            total = total + float(remaining)
    return (len(seen), total, missing)


def branch_stats(branches):
    """修订②后续分支聚合：分支数、上四分位就绪分位、分位数间距、极差、平均支撑枚数。

    与父代差异：父代只用「最差半段向听均值 + max-min 极差」，单个极端分支即可
    撑爆聚合量；本版给出上四分位（QUANTILE_HIGH）就绪分位与「上四分位减下四分
    位」的分位数间距，另把父代极差一并返回，由调用方按 band 在两者间连续插值，
    使墙前段保持父代口径。None=未分析（与已知空元组区分）；不做「取最佳分支」预合并。
    """
    if branches is None:
        return None
    if len(branches) == 0:
        return (0, 0.0, 0.0, 0.0, 0.0)
    shantens = []
    supports = []
    for branch in branches:
        value = branch.get("combined_shanten")
        if value is None:
            value = branch.get("shanten")
        if value is None:
            value = branch.get("shanten_after")
        if value is not None:
            shantens.append(value)
        support = branch.get("support_remaining")
        if support is None:
            support = branch.get("useful_remaining")
        if support is None:
            support = branch.get("support")
        if support is not None:
            supports.append(float(support))
    if len(shantens) == 0:
        return (0, 0.0, 0.0, 0.0, 0.0)
    ordered = sorted(shantens)
    count = len(ordered)
    high_index = int(QUANTILE_HIGH * float(count - 1) + 0.5)
    low_index = int(QUANTILE_LOW * float(count - 1) + 0.5)
    if high_index < 0:
        high_index = 0
    if high_index > count - 1:
        high_index = count - 1
    if low_index < 0:
        low_index = 0
    if low_index > count - 1:
        low_index = count - 1
    ready_quantile = float(ordered[high_index])
    quantile_spread = float(ordered[high_index] - ordered[low_index])
    extreme_spread = float(ordered[count - 1] - ordered[0])
    support_mean = 0.0
    if len(supports) > 0:
        support_mean = sum(supports) / float(len(supports))
    return (count, ready_quantile, quantile_spread, extreme_spread, support_mean)


def route_witness(routes):
    """路线见证统计：路线数、被见证（或带条件结算）路线数、被证明关闭路线数。

    未枚举不等于机会为 0，故只用见证加成与关闭扣减，不做整体清零。
    """
    if routes is None:
        return (0, 0, 0)
    witnessed = 0
    closed = 0
    for route in routes:
        status = route.get("route_state")
        if status is None:
            status = route.get("route_status")
        if status == "CLOSED_PROVEN":
            closed = closed + 1
        elif status == "WITNESSED" or route.get("conditional_settlement") is not None:
            witnessed = witnessed + 1
    return (len(routes), witnessed, closed)


def score_actions(view):
    """按同一动作窗口的只读可见事实，为全部合法动作评分。"""
    actions = view.get("actions")
    state = view.get("visible_state")
    if actions is None or state is None:
        return {"status": "ABSTAIN", "reason": "scoring_view 缺 actions/visible_state，无法建立动作全集"}
    if len(actions) == 0:
        return {"status": "ABSTAIN", "reason": "输入动作表为空，本窗口无可评分动作"}
    competition = view.get("competition")
    seat = state.get("seat")
    horizon, horizon_basis = horizon_of(state)
    aggression, competition_basis = aggression_of(state, competition, seat)
    band = mid_band_of(horizon)
    turn = horizon - MID_TURN_ADVANCE * band
    if turn < 0.0:
        turn = 0.0
    width_weight = (WIDTH_WEIGHT_SHORT + (WIDTH_WEIGHT_LONG - WIDTH_WEIGHT_SHORT) * turn) * aggression
    lock_line = (LOCK_SCARCE_WEIGHT - (LOCK_SCARCE_WEIGHT - LOCK_PLENTY_WEIGHT) * turn) / aggression
    lock_weight = lock_line
    lock_floor = LOCK_FLOOR_MID * band
    if lock_weight < lock_floor:
        lock_weight = lock_floor
    evidence_partial = EVIDENCE_PARTIAL + band * (EVIDENCE_PARTIAL_MID - EVIDENCE_PARTIAL)
    evidence_unrun = EVIDENCE_UNRUN + band * (EVIDENCE_UNRUN_MID - EVIDENCE_UNRUN)
    keys = []
    scores = []
    traces = []
    for index in range(len(actions)):
        action = actions[index]
        key = action.get("action_key")
        if key is None:
            return {"status": "ABSTAIN", "reason": f"动作表第 {index} 项缺 action_key，无法满足逐动作输出合同"}
        keys.append(key)
        action_type = action.get("action_type")
        family = action.get("family_progress")
        coverage = action.get("value_coverage")
        fact_kind = action.get("fact_kind")
        shanten = pick_shanten(action)
        progress_term = 0.0
        progress_basis = "unavailable"
        if shanten is not None and shanten < 0:
            progress_term = WIN_TIER
            progress_basis = "shanten_win"
        elif shanten is not None:
            progress_term = SHANTEN_STEP * float(SHANTEN_REFERENCE - shanten)
            progress_basis = "shanten_after"
        elif fact_kind == "win":
            progress_term = WIN_TIER
            progress_basis = "fact_kind_win"
        combined_fact = None
        if fact_kind is not None and fact_kind != "analysis_failed":
            combined_fact = useful_width(action.get("useful_tiles"))
        standard_fact = useful_width(action.get("standard_useful_tiles"))
        seven_fact = useful_width(action.get("seven_pairs_useful_tiles"))
        width = None
        width_basis = "declared_prior"
        if combined_fact is not None and combined_fact[1] > 0.0:
            width = combined_fact
            width_basis = "combined"
        elif standard_fact is not None and standard_fact[1] > 0.0:
            width = standard_fact
            width_basis = "standard"
        elif seven_fact is not None and seven_fact[1] > 0.0:
            width = seven_fact
            width_basis = "seven_pairs"
        elif combined_fact is not None:
            width = combined_fact
            width_basis = "combined_empty"
        elif standard_fact is not None:
            width = standard_fact
            width_basis = "standard_empty"
        elif seven_fact is not None:
            width = seven_fact
            width_basis = "seven_pairs_empty"
        else:
            width = (0, WIDTH_NEUTRAL, 0)
        branches = branch_stats(action.get("followup_branches"))
        branch_basis = "unavailable"
        dispersion_penalty = 0.0
        ready_quantile = None
        spread_used = None
        substitute = 0.0
        if branches is not None:
            branch_basis = "analyzed"
            if branches[0] > 0:
                ready_quantile = branches[1]
                spread_used = branches[3] + band * (branches[2] - branches[3])
                dispersion_penalty = DISPERSION_WEIGHT * spread_used
                if progress_basis == "unavailable" and band > 0.0:
                    progress_term = band * BRANCH_PROGRESS_STEP * float(SHANTEN_REFERENCE - ready_quantile)
                    progress_basis = "branch_quantile"
                    substitute = band
                if width_basis == "declared_prior" and branches[4] > 0.0:
                    width = (0, branches[4], 0)
                    width_basis = "branch_support"
        width_term = min(width[1], WIDTH_CAP) * width_weight
        lock_term = 0.0
        if shanten is not None and shanten == 0:
            lock_term = LOCK_UNIT * lock_weight
        settlement = action.get("immediate_settlement")
        settle_term = 0.0
        settle_basis = "none"
        if settlement is not None:
            settle_basis = "unavailable"
            fan = settlement.get("fan")
            self_delta = settlement.get("self_delta")
            if fan is not None:
                settle_term = settle_term + SETTLE_FAN_WEIGHT * float(fan)
                settle_basis = "fan_only"
            if self_delta is not None:
                settle_term = settle_term + SETTLE_DELTA_WEIGHT * float(self_delta)
                if fan is not None:
                    settle_basis = "fan_and_delta"
        terminal_term = 0.0
        if settlement is not None or progress_basis == "shanten_win" or progress_basis == "fact_kind_win":
            terminal_term = CERTAINTY_TIER
        route = route_witness(action.get("routes"))
        route_bonus = ROUTE_WITNESS_BONUS * float(min(route[1], ROUTE_CAP))
        route_penalty = ROUTE_CLOSED_PENALTY * float(min(route[2], ROUTE_CAP))
        family_term = 0.0
        family_basis = "unknown"
        if family == "ADVANCE":
            family_term = ADVANCE_BONUS
            family_basis = "advance"
        elif family == "RETREAT":
            family_term = -RETREAT_PENALTY
            family_basis = "retreat"
        elif family == "CLOSE":
            family_term = -CLOSE_PENALTY
            family_basis = "close"
        elif family == "SAME":
            family_basis = "same"
        gang_penalty = 0.0
        if action.get("replacement_draw_unknown") is True:
            gang_penalty = GANG_UNKNOWN_PENALTY
        evidence = evidence_unrun
        evidence_basis = "unrun"
        if coverage == "complete":
            evidence = 1.0
            evidence_basis = "complete"
        elif coverage == "partial":
            evidence = evidence_partial
            evidence_basis = "partial"
        elif coverage == "unavailable":
            evidence = EVIDENCE_UNAVAILABLE
            evidence_basis = "unavailable"
        unknown_penalty = 0.0
        if progress_basis == "unavailable":
            unknown_penalty = unknown_penalty + UNKNOWN_RANK_PENALTY
        else:
            if progress_basis == "branch_quantile":
                unknown_penalty = unknown_penalty + UNKNOWN_RANK_PENALTY * (1.0 - substitute)
        if width_basis == "declared_prior":
            unknown_penalty = unknown_penalty + UNKNOWN_RANK_PENALTY
        penalty = dispersion_penalty + gang_penalty + unknown_penalty + route_penalty
        total = (
            progress_term
            + family_term
            + route_bonus
            + terminal_term
            + (settle_term + width_term + lock_term) * evidence
            - penalty
        )
        no_evidence = (
            progress_basis == "unavailable"
            and width_basis == "declared_prior"
            and branch_basis == "unavailable"
            and settle_basis == "none"
            and family_basis == "unknown"
            and route[0] == 0
        )
        if no_evidence:
            scores.append(None)
        else:
            scores.append(round(total, 6))
        traces.append({
            "mech": "ready_width_frontier_v2",
            "parts": {
                "prog": round(progress_term, 4),
                "settle": round(settle_term, 4),
                "width": round(width_term, 4),
                "lock": round(lock_term, 4),
                "fam": round(family_term, 4),
                "route": round(route_bonus, 4),
                "term": round(terminal_term, 4),
                "disp": round(dispersion_penalty, 4),
                "gang": round(gang_penalty, 4),
                "unk": round(unknown_penalty, 4),
                "ev": round(evidence, 4),
                "tot": round(total, 4),
            },
            "basis": f"{width_basis}|{progress_basis}|{settle_basis}|{branch_basis}|{evidence_basis}|{family_basis}|{horizon_basis}|{competition_basis}",
            "facts": f"type={action_type};sh={shanten};wid={width[0]},{round(width[1], 3)};br={branches[0] if branches is not None else None};q={ready_quantile};spr={spread_used};b={round(band, 3)};turn={round(turn, 3)};ww={round(width_weight, 3)};lw={round(lock_weight, 3)};aggr={round(aggression, 3)};rt={route[0]},{route[1]},{route[2]}",
        })
    analyzed_min = None
    for value in scores:
        if value is not None:
            if analyzed_min is None or value < analyzed_min:
                analyzed_min = value
    if analyzed_min is None:
        return {"status": "ABSTAIN", "reason": "全部动作都缺向听/有效牌/分支/结算/路线/家族证据，本窗口无法建立可比评分"}
    entries = []
    for index in range(len(keys)):
        value = scores[index]
        trace = traces[index]
        if value is None:
            value = round(analyzed_min - FLOOR_MARGIN, 6)
            trace = {
                "mech": trace.get("mech"),
                "parts": trace.get("parts"),
                "basis": trace.get("basis") + "|unanalyzed_floor",
                "facts": trace.get("facts"),
            }
        entries.append({"action_key": keys[index], "score": value, "trace": trace})
    return {"status": "SCORED", "entries": entries}
