
from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)


# ---------------------------------------------------------------------------
# 规则调用（一律走 hangma；本文件不实现第二套杭麻规则）
# ---------------------------------------------------------------------------

Q = chr(96)  # 反引号，仅用于生成 Markdown 行内代码


def _tiles(codes):
    from hangma_bot.kernel.actions import Tile
    return tuple(Tile(c) for c in codes)


def analyse_hand(hand_codes, meld_set_count):
    """调用 hangma 求手牌摘要；异常返回 None，不臆造数值。"""
    if not hand_codes:
        return None
    try:
        return hand_analysis.analyse_hand(_tiles(hand_codes), meld_set_count)
    except Exception:
        return None


def settle_check(fan, winner, dealer, scores):
    """用 hangma 结算函数复核官方分数向量（底分 1）。"""
    return list(settlement.settle_scores(int(fan), 1, int(winner), int(dealer)))


# ---------------------------------------------------------------------------
# 数据集
# ---------------------------------------------------------------------------

def build_rounds():
    """官方牌谱 + 审计快照 join；返回逐局记录列表。"""
    games = load_official()
    cache = load_cache()
    rounds = []
    for g in games:
        c = cache.get(g["game_id"], {})
        snap_rounds = c.get("snap_rounds") or {}
        ev_rounds = c.get("event_rounds") or {}
        my = g["my_seat"]
        cum = [0, 0, 0, 0]
        for rnd in g["rounds"]:
            rn = rnd.get("round_no")
            sc = list(rnd.get("scores") or [0, 0, 0, 0])
            for i in range(4):
                cum[i] += sc[i]
            win = rnd.get("winner")
            is_draw = bool(rnd.get("is_draw"))
            fan = rnd.get("multiplier") or 0
            rec = {
                "room_id": g["room_id"],
                "session_tag": g["session_tag"],
                "game_id": g["game_id"],
                "round_no": rn,
                "my_seat": my,
                "seat_user_ids": g["seats"],
                "dealer": rnd.get("dealer"),
                "winner": win,
                "is_draw": is_draw,
                "fan": int(fan),
                "scores": sc,
                "my_score": sc[my],
                "i_won": (win == my and not is_draw),
                "i_dealer": (rnd.get("dealer") == my),
                "cum_scores": list(cum),
            }
            # 官方明细（仅旧适配器会话有事件流）
            ev = ev_rounds.get(str(rn))
            if ev:
                rec["detail"] = ev.get("detail")
                rec["predecessor"] = ev.get("predecessor")
                rec["predecessor_is_winner"] = (ev.get("predecessor_seat") == ev.get("winner"))
                rec["draws_before"] = ev.get("draws_before")
            # 审计快照
            snaps = snap_rounds.get(str(rn)) or []
            rec["n_snaps"] = len(snaps)
            if snaps:
                last = snaps[-1]
                rec["wall_end"] = last.get("wall")
                rec["scores_snap"] = last.get("scores")
                s = analyse_hand(last.get("hand"), last.get("meld_set_count", 0))
                if s is not None:
                    rec["shanten_end"] = s.shanten
                    rec["end_is_win"] = bool(s.is_win)
                    rec["end_useful"] = sorted({u.code for u in (s.useful_tiles or ())})
                    rec["end_melds"] = last.get("meld_set_count")
                    rec["end_hand"] = last.get("hand")
                # 是否曾听牌（含已胡手牌）
                reach = None
                for sn in snaps:
                    ss = analyse_hand(sn.get("hand"), sn.get("meld_set_count", 0))
                    if ss is None:
                        continue
                    if ss.is_win or ss.shanten <= 0:
                        reach = {"seq": sn.get("seq"), "wall": sn.get("wall"), "phase": sn.get("phase")}
                        break
                rec["tenpai"] = reach
                # 快照累计分与官方累计分的对齐校验
                rec["join_ok"] = (list(last.get("scores") or []) == list(cum)
                                  or list(last.get("scores") or []) == [c - d for c, d in zip(cum, sc)])
            rounds.append(rec)
    return rounds


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def _pct(a, b):
    return (100.0 * a / b) if b else 0.0


# ---------------------------------------------------------------------------
# 归因聚合
# ---------------------------------------------------------------------------

def decompose(rounds):
    """可加总分解：四类互斥且穷尽，合计等于我方总分。"""
    cat = collections.OrderedDict()
    for name in ("A 我方自摸胡(+分)", "B 坐庄被他人自摸付分(-分)",
                 "C 非庄被他人自摸付分(-分)", "D 流局(0分)"):
        cat[name] = {"points": 0, "rounds": 0, "per_round": 0.0}
    for r in rounds:
        if r["is_draw"]:
            k = "D 流局(0分)"
        elif r["i_won"]:
            k = "A 我方自摸胡(+分)"
        elif r["i_dealer"]:
            k = "B 坐庄被他人自摸付分(-分)"
        else:
            k = "C 非庄被他人自摸付分(-分)"
        cat[k]["points"] += r["my_score"]
        cat[k]["rounds"] += 1
    for k, v in cat.items():
        v["per_round"] = (v["points"] / v["rounds"]) if v["rounds"] else 0.0
    gross = -(cat["B 坐庄被他人自摸付分(-分)"]["points"] + cat["C 非庄被他人自摸付分(-分)"]["points"])
    for k, v in cat.items():
        v["share_of_gross_loss"] = _pct(-v["points"], gross) if v["points"] < 0 else None
    return cat, gross


def by_fan(rounds, kinds):
    """按番值拆分类别的付分/收入。"""
    out = collections.OrderedDict()
    for r in rounds:
        if r["is_draw"]:
            continue
        if r["i_won"]:
            key = ("WIN", r["fan"], "庄" if r["i_dealer"] else "闲")
        elif r["i_dealer"]:
            key = ("PAY", r["fan"], "庄")
        else:
            key = ("PAY", r["fan"], "闲")
        if key[0] not in kinds:
            continue
        b = out.setdefault(key, {"points": 0, "rounds": 0})
        b["points"] += r["my_score"]
        b["rounds"] += 1
    return out


def by_wall_band(rounds):
    """按牌墙剩余（= 巡目进度）分档的付分。"""
    vals = [r["wall_end"] for r in rounds if r.get("wall_end") is not None]
    if not vals:
        return {}
    vals.sort()
    q1 = vals[len(vals) // 3]
    q2 = vals[2 * len(vals) // 3]

    def band(w):
        if w is None:
            return "未知"
        if w >= q1:
            return "早期(墙%d-%d)" % (q1, vals[-1])
        if w >= q2:
            return "中期(墙%d-%d)" % (q2, q1 - 1)
        return "晚期(墙%d-%d)" % (vals[0], q2 - 1)
    out = collections.OrderedDict()
    for r in rounds:
        if r["is_draw"] or r["i_won"]:
            continue
        k = band(r.get("wall_end"))
        b = out.setdefault(k, {"points": 0, "rounds": 0})
        b["points"] += r["my_score"]
        b["rounds"] += 1
    return out, (q1, q2, vals[0], vals[-1])


def session_groups(rounds):
    """按会话/策略分组的总分。"""
    out = collections.OrderedDict()
    for r in rounds:
        b = out.setdefault(r["session_tag"], {"points": 0, "rounds": 0, "games": set(), "rooms": set()})
        b["points"] += r["my_score"]
        b["rounds"] += 1
        b["games"].add(r["game_id"])
        b["rooms"].add(r["room_id"])
    for k, v in out.items():
        v["games"] = len(v["games"])
        v["rooms"] = len(v["rooms"])
    return out


def room_totals(rounds):
    out = collections.OrderedDict()
    for r in rounds:
        b = out.setdefault(r["room_id"], {"points": 0, "rounds": 0, "tag": r["session_tag"]})
        b["points"] += r["my_score"]
        b["rounds"] += 1
    return out
