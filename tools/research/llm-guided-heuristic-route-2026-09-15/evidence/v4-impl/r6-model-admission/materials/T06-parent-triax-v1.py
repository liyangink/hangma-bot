# 来源：batch7 gen/m1/attempts/m1-d68785b86751/record.json parent.code（逐字）
# 用途：T06/T07/T08 的 must_differ_from 比对基线
"""候选机制说明：以「向听-支撑结构 × 条件路线潜力 × 立即结算」三轴对照评分：先从墙余量与赛事名次压力推导机会缩放，再对每个合法动作聚合后续分支结构值（-14×向听 + 路线证据状态加权的支撑凹曲线）与路线潜力（压力×墙机会×封顶番/自得分），胡/杠等立即结算按自得分与番直接入分并与继续值真实比较，未知事实显式降档带旗标，未知动作沉底 -40、已知动作保底 -39，结构事实不完整或胡缺结算时整批 ABSTAIN。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/materials'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

MECH = "triax-v1"
KNOWN_TYPES = ("discard", "chi", "peng", "gang", "hu", "pass")
WALL_MID = 22.0
SH_PEN = 14.0
SETTLE_BASE = 32.0
HU_BASE = 34.0


def num2(x):
    """数值读取兜底：None/布尔视为未知，返回 (占位值, 是否已知)。"""
    if x is None:
        return 0.0, False
    if x is True or x is False:
        return 0.0, False
    return x, True


def supcurve(s):
    """支撑张数到评分点的凹曲线：前 10 张每张 0.55，其后每张 0.12。"""
    if s <= 10.0:
        return 0.55 * s
    return 5.5 + 0.12 * (s - 10.0)


def evweight(rs):
    """路线证据状态到支撑项权重：已见证 1.0，开放不确定 0.75，已证封闭 0.1，未枚举 0.5（不按 0）。"""
    if rs == "WITNESSED":
        return 1.0
    if rs == "OPEN_UNCERTAIN":
        return 0.75
    if rs == "CLOSED_PROVEN":
        return 0.1
    return 0.5


def progadj(p):
    """动作相对进展到基线调整：ADVANCE +6，RETREAT -10，SAME/CLOSE/UNKNOWN 记 0 并由旗标区分。"""
    if p == "ADVANCE":
        return 6.0
    if p == "RETREAT":
        return -10.0
    return 0.0


def blend(vals):
    """非空结构值列表的 0.7 最优 + 0.3 均值混合；调用方保证非空。"""
    total = sum(vals)
    return 0.7 * max(vals) + 0.3 * (total / len(vals))


def branch_score(br):
    """单个后续分支的结构值：-14×向听 + 证据权重×支撑曲线；向听未知则整体弃用该分支。"""
    sh, shok = num2(br.get("combined_shanten"))
    sup, supok = num2(br.get("support_remaining"))
    if not shok:
        return 0.0, False, supok
    val = 0.0 - SH_PEN * sh
    if supok:
        val = val + evweight(br.get("route_state")) * supcurve(sup)
    return val, True, supok


def branch_fan(br):
    """分支自带潜在番，封顶 26；未知返回 (0.0, False)，不按已知 0 处理。"""
    f, fok = num2(br.get("fan"))
    if fok:
        return min(f, 26.0), True
    return 0.0, False


def route_score(rt):
    """条件路线：结构值（向听+有效牌未见枚数）与条件结算潜力；返回 (值, 任一已知, 潜力, 潜力已知)。"""
    sh, shok = num2(rt.get("shanten"))
    useful = rt.get("useful_tiles") or ()
    u = 0.0
    uok = False
    for tile in useful[:8]:
        rem, rok = num2(tile.get("remaining_estimate"))
        if rok:
            u = u + min(rem, 4.0)
            uok = True
    val = 0.0
    if shok:
        val = val - SH_PEN * sh
    if uok:
        val = val + 0.6 * supcurve(u)
    pot = 0.0
    potok = False
    cs = rt.get("conditional_settlement")
    if cs is not None:
        f, fok = num2(cs.get("fan"))
        d, dok = num2(cs.get("self_delta"))
        if fok:
            pot = 1.4 * min(f, 26.0)
            potok = True
        if dok and d > 0.0:
            pot = pot + 0.3 * min(d, 90.0)
            potok = True
    return val, shok or uok, pot, potok


def pressure_of(view, vs):
    """赛事名次压力：阶段基准优先，其次 competition 桌基准，再退 live 桌分；返回 (压力, 基准名, 名次)。"""
    comp = view.get("competition")
    scores = None
    basis = "none"
    if comp is not None:
        stg = comp.get("stage_scores")
        if stg is not None:
            scores = stg
            basis = "stage"
        else:
            tbl = comp.get("table_scores")
            if tbl is not None:
                scores = tbl
                basis = "table"
    if scores is None:
        live = vs.get("table_scores")
        if live is not None:
            scores = live
            basis = "table_live"
    if scores is None or len(scores) != 4:
        return 0.5, basis, -1
    for s in scores:
        if s is None or s is True or s is False:
            return 0.5, "bad_scores", -1
    seat, seok = num2(vs.get("seat"))
    if not seok:
        return 0.5, "bad_seat", -1
    si = round(seat)
    if si != seat or si < 0 or si > 3:
        return 0.5, "bad_seat", -1
    my = scores[si]
    higher = 0
    for s in scores:
        if s > my:
            higher = higher + 1
    if higher == 0:
        return 0.2, basis, 1
    if higher == 1:
        return 0.5, basis, 2
    return 0.85, basis, higher + 1


def score_actions(view):
    """按同一动作窗口的只读可见事实，为全部合法动作评分。"""
    schema = view.get("schema_version")
    if schema != "sitin-scoring-view/1":
        return {"status": "ABSTAIN", "reason": f"schema_version={schema!r} 不兼容 sitin-scoring-view/1，拒绝评分"}
    vs = view.get("visible_state")
    if vs is None:
        return {"status": "ABSTAIN", "reason": "visible_state 缺失，无法评分"}
    actions = view.get("actions")
    if not actions:
        return {"status": "ABSTAIN", "reason": "动作表缺失或为空，窗口必须先备合法紧急计划"}
    press, basis, rank = pressure_of(view, vs)
    wraw = vs.get("remaining_tile_count")
    wallok = False
    wallf = 0.6
    if wraw is not None and wraw is not True and wraw is not False:
        wc = min(max(wraw, 0), 160)
        wallf = wc / (wc + WALL_MID)
        wallok = True
    fut = 0.55 + 0.45 * wallf
    profile = view.get("analysis_profile")
    trunc = ""
    if profile is not None:
        raw = profile.get("truncation_note")
        if raw is not None and raw != "":
            trunc = raw
    entries = []
    for act in actions:
        key = act.get("action_key")
        atype = act.get("action_type")
        if key is None or atype is None:
            return {"status": "ABSTAIN", "reason": "动作条目缺 action_key/action_type，事实不完整"}
        prog = act.get("family_progress")
        flags = []
        known = atype in KNOWN_TYPES
        settle = act.get("immediate_settlement")
        branches = act.get("followup_branches")
        routes = act.get("routes") or ()
        brvals = []
        rtvals = []
        potmax = 0.0
        potok = False
        score = 0.0
        if atype == "hu":
            if settle is None:
                return {"status": "ABSTAIN", "reason": f"hu 动作 {key} 缺 immediate_settlement，compare_legal 无法比较"}
            f, fok = num2(settle.get("fan"))
            d, dok = num2(settle.get("self_delta"))
            if not fok or not dok:
                return {"status": "ABSTAIN", "reason": f"hu 动作 {key} 结算 fan/self_delta 非数值，无法比较"}
            score = HU_BASE + 0.45 * d + 1.7 * min(f, 26.0)
            if press >= 0.8:
                score = score * 1.1
            if wallf < 0.15:
                score = score + 4.0
            flags.append("hu")
        else:
            base = 0.0
            if atype == "pass":
                base = 1.0
            if atype == "chi" or atype == "peng":
                base = -1.5
            if atype == "gang":
                base = 2.0
            if not known:
                base = 0.0
                flags.append("type?")
            if settle is not None:
                f, fok = num2(settle.get("fan"))
                d, dok = num2(settle.get("self_delta"))
                if fok and dok:
                    base = base + SETTLE_BASE + 0.45 * d + 1.4 * min(f, 26.0)
                    flags.append("settle")
                    if atype == "gang" and wallf < 0.2:
                        base = base - 3.0
                else:
                    flags.append("settle?")
            bmiss = 0
            if branches is None:
                flags.append("brna")
            else:
                if len(branches) > 12:
                    flags.append("brtrunc")
                for br in branches[:12]:
                    val, shok, supok = branch_score(br)
                    if shok:
                        brvals.append(val)
                    else:
                        bmiss = bmiss + 1
                    if not supok and flags.count("brsup") == 0:
                        flags.append("brsup")
                    bf, bfok = branch_fan(br)
                    if bfok and bf > potmax:
                        potmax = bf
                        potok = True
                if bmiss > 0 and flags.count("brsh?") == 0:
                    flags.append("brsh?")
            if len(routes) > 0:
                if len(routes) > 10:
                    flags.append("rttrunc")
                for rt in routes[:10]:
                    val, anyok, pot, pok = route_score(rt)
                    if anyok:
                        rtvals.append(val)
                    if pok and pot > potmax:
                        potmax = pot
                        potok = True
            score = base + progadj(prog)
            if len(brvals) > 0:
                score = score + fut * blend(brvals)
            if len(rtvals) > 0:
                score = score + 0.8 * fut * blend(rtvals)
            if potok:
                score = score + (0.6 + 0.8 * press) * (0.3 + 0.7 * wallf) * potmax
            if branches is None and len(routes) == 0 and settle is None:
                flags.append("noan")
        if known:
            score = max(score, -39.0)
        else:
            score = -40.0
        if score != score:
            score = -39.0
            flags.append("nan")
        flagstr = ""
        for fl in flags:
            flagstr = flagstr + fl + ","
        if not wallok:
            flagstr = "wallna," + flagstr
        trace = {
            "mech": MECH,
            "type": atype,
            "prog": prog,
            "press": round(press, 2),
            "basis": basis,
            "rank": rank,
            "wall": round(wallf, 2),
            "fut": round(fut, 2),
            "brs": len(brvals),
            "rts": len(rtvals),
            "pot": round(potmax, 1),
            "flags": flagstr,
            "trunc": trunc[:12],
        }
        entries.append({"action_key": key, "score": round(score, 4), "trace": trace})
    return {"status": "SCORED", "entries": entries}
