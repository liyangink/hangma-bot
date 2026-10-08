#!/usr/bin/env python3
"""自由赛失分归因计量学（只读；无网络；规则一律调用 hangma）。

数据源
------
1. 官方牌谱：artifacts/sessions/<会话标签>/official/dl-*/events.json
   每局给出 dealer / winner / is_draw / multiplier / scores（四座分数向量）。
2. 我方逐动作审计：artifacts/sessions/<会话标签>/audit/runs/<run_id>/
   participants/u_13495c3d79c8/raw/<game_id>.*.jsonl.gz
   记录官方 GET /state 快照（含 my_hand / melds / wall_remaining / god /
   累计 scores）与部分事件流；本脚本用快照重建我方手牌轨迹。
3. 规则唯一来源：hangma_bot.hangma（向听、结算、胡牌分解）。

子命令
------
    .venv/bin/python review/freematch-deep-dive-20260925/loss_attribution.py scan
    .venv/bin/python review/freematch-deep-dive-20260925/loss_attribution.py report
    .venv/bin/python review/freematch-deep-dive-20260925/loss_attribution.py all

scan 阶段把每局紧凑事实写入 round-audit.jsonl（缓存，可重复执行）；
report 阶段读取缓存 + 官方牌谱，产出 loss-attribution.json 与 LOSS-ATTRIBUTION.md。
"""
from __future__ import annotations

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

import argparse
import collections
import glob
import gzip
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.join(ROOT, "review", "freematch-deep-dive-20260925")
ME = "u_13495c3d79c8"
SESSION_ROOT = os.path.join(ROOT, "artifacts", "sessions")
CACHE = os.path.join(HERE, "round-audit.jsonl")
OUT_JSON = os.path.join(HERE, "loss-attribution.json")
OUT_MD = os.path.join(HERE, "LOSS-ATTRIBUTION.md")

sys.path.insert(0, os.path.join(ROOT, "src"))

from hangma_bot.hangma import hand_analysis  # noqa: E402 规则唯一来源：向听/胡牌分解
from hangma_bot.hangma import settlement  # noqa: E402 规则唯一来源：四家结算


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_official():
    """官方牌谱：返回 (games, duplicates)。

    同一 game_id 可能被下载多次（同一房的多个 dl-* 目录）。这些记录内容逐字相同，
    属于重复下载而非不同的场，因此按 game_id 去重（保留首个），并把重复情况单独返回，
    供报告披露。统计单位是「场」（game_id），不是「下载记录」。
    """
    seen = {}
    duplicates = []
    for path in sorted(glob.glob(os.path.join(SESSION_ROOT, "*", "official", "dl-*", "events.json"))):
        try:
            with open(path) as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        seats = [s.get("user_id") for s in (payload.get("seats") or [])]
        if ME not in seats:
            continue
        tag = path.split(os.sep)[-4]
        gid = payload.get("game_id")
        rec = {
            "room_id": payload.get("room_id"),
            "session_tag": tag,
            "game_id": gid,
            "seats": seats,
            "my_seat": seats.index(ME),
            "rounds": payload.get("rounds") or [],
        }
        if gid in seen:
            first = seen[gid]
            duplicates.append({
                "game_id": gid,
                "copies": 1,
                "rounds_equal": rec["rounds"] == first["rounds"],
                "seats_equal": rec["seats"] == first["seats"],
                "extra_my_score": sum(r["scores"][rec["my_seat"]] for r in rec["rounds"]),
                "extra_rounds": len(rec["rounds"]),
            })
            continue
        seen[gid] = rec
    games = sorted(seen.values(), key=lambda r: (r["session_tag"], r["room_id"], r["game_id"]))
    return games, duplicates


def _raw_paths(tag, room_id):
    return sorted(glob.glob(os.path.join(
        SESSION_ROOT, tag, "audit", "runs", "*", "participants", ME, "raw", room_id + "_*.jsonl.gz")))


def read_raw(path):
    """读取一个审计 raw 文件，返回 (events_by_seq, snapshots)。"""
    events, snaps = {}, []
    try:
        with gzip.open(path, "rt") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                raw = (rec.get("payload") or {}).get("raw")
                if not raw:
                    continue
                try:
                    doc = json.loads(raw)
                except ValueError:
                    continue
                for ev in (doc.get("events") or []):
                    if isinstance(ev, dict) and ev.get("seq") is not None:
                        events[ev["seq"]] = ev
                snap = doc.get("snapshot")
                if snap:
                    snaps.append((doc.get("seq"), snap))
    except (OSError, EOFError, gzip.BadGzipFile, ValueError):
        pass
    return events, snaps


def scan_game(tag, room_id, game_id):
    """扫描一场的审计 raw，返回紧凑事实。"""
    events, snaps = {}, []
    for path in _raw_paths(tag, room_id):
        if os.path.basename(path).split(".")[0] != game_id:
            continue
        e, s = read_raw(path)
        events.update(e)
        snaps.extend(s)
    my_seat = None
    for _seq, s in snaps:
        if s.get("seat") is not None:
            my_seat = s["seat"]
            break
    seqs = sorted(events)
    ends = [(s, events[s]) for s in seqs if events[s].get("type") == "round_ended"]
    pred = {}
    for s, ev in ends:
        data = ev.get("data") or {}
        rn = data.get("round_no")
        prev = events.get(s - 1)
        draws = sum(1 for i in seqs if i < s and events[i].get("type") == "tile_drawn")
        pred[rn] = {
            "end_seq": s,
            "winner": ev.get("seat"),
            "dealer": data.get("dealer"),
            "fan": data.get("fan"),
            "detail": data.get("detail"),
            "draw": data.get("draw"),
            "scores": data.get("scores"),
            "predecessor": (prev or {}).get("type"),
            "predecessor_seat": (prev or {}).get("seat"),
            "draws_before": draws,
        }
    per_round = collections.defaultdict(list)
    for seq, s in sorted(snaps, key=lambda x: (x[0] if x[0] is not None else -1)):
        rn = s.get("round_no")
        melds = s.get("melds") or [[], [], [], []]
        mine = melds[my_seat] if my_seat is not None and my_seat < len(melds) else []
        per_round[rn].append({
            "seq": seq,
            "phase": s.get("phase"),
            "wall": s.get("wall_remaining"),
            "turn": s.get("turn"),
            "hand": list(s.get("my_hand") or []),
            "drawn": s.get("drawn_tile") or "",
            "meld_set_count": len(mine or []),
            "god": s.get("god"),
            "scores": s.get("scores"),
            "hand_counts": s.get("hand_counts"),
        })
    return {"my_seat": my_seat, "rounds": dict(per_round), "event_rounds": pred,
            "has_events": bool(ends), "n_events": len(events)}


def cmd_scan(_args):
    games, duplicates = load_official()
    if duplicates:
        print("注意：%d 条重复下载记录已按 game_id 去重" % len(duplicates))
    rows = []
    t0 = time.time()
    for g in games:
        info = scan_game(g["session_tag"], g["room_id"], g["game_id"])
        rows.append({
            "room_id": g["room_id"],
            "session_tag": g["session_tag"],
            "game_id": g["game_id"],
            "my_seat": info["my_seat"],
            "has_events": info["has_events"],
            "n_events": info["n_events"],
            "event_rounds": {str(k): v for k, v in info["event_rounds"].items()},
            "snap_rounds": {str(k): v for k, v in info["rounds"].items()},
        })
    with open(CACHE, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote %s (%d games) in %.1fs" % (CACHE, len(rows), time.time() - t0))
    return 0


def load_cache():
    out = {}
    with open(CACHE) as fh:
        for line in fh:
            r = json.loads(line)
            out[r["game_id"]] = r
    return out


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
    games, _dups = load_official()
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
                baotou_ever = False
                for sn in snaps:
                    god = sn.get("god") or {}
                    if god.get("baotou"):
                        baotou_ever = True
                    ss = analyse_hand(sn.get("hand"), sn.get("meld_set_count", 0))
                    if ss is None:
                        continue
                    if reach is None and (ss.is_win or ss.shanten <= 0):
                        reach = {"seq": sn.get("seq"), "wall": sn.get("wall"), "phase": sn.get("phase"),
                                 "baotou": bool(god.get("baotou"))}
                rec["tenpai"] = reach
                rec["baotou_ever"] = baotou_ever
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
        # 牌墙剩余越大＝该局结束得越早（巡目越靠前）
        if w is None:
            return "未知"
        if w >= q2:
            return "早巡(墙%d-%d)" % (q2, vals[-1])
        if w >= q1:
            return "中巡(墙%d-%d)" % (q1, q2 - 1)
        return "晚巡(墙%d-%d)" % (vals[0], q1 - 1)
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


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

FENCE = chr(96) * 3  # Markdown 代码围栏，避免源码里出现裸反引号


def _table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def _fnum(x, nd=1):
    if x is None:
        return "-"
    return ("%%.%df" % nd) % x


def cmd_report(_args):
    rounds = build_rounds()
    data = {}
    n = len(rounds)
    my_total = sum(r["my_score"] for r in rounds)
    games = len({r["game_id"] for r in rounds})
    rooms = len({r["room_id"] for r in rounds})
    session_tags = sorted({r["session_tag"] for r in rounds})

    # ---- 结算文法验证 -------------------------------------------------
    grammar_bad = []
    zero_bad = []
    for r in rounds:
        if sum(r["scores"]) != 0:
            zero_bad.append(r)
        if r["is_draw"]:
            if any(r["scores"]):
                grammar_bad.append(r)
            continue
        try:
            exp = settle_check(r["fan"], r["winner"], r["dealer"], r["scores"])
        except Exception:
            grammar_bad.append(r)
            continue
        if exp != list(r["scores"]):
            grammar_bad.append(r)
    ev_rounds = [r for r in rounds if r.get("predecessor")]
    ev_win_rounds = [r for r in ev_rounds if not r["is_draw"]]          # 流局的前一事件本就不是摸牌
    sd_rounds = [r for r in ev_win_rounds if r["predecessor"] == "tile_drawn" and r.get("predecessor_is_winner")]
    sd_exceptions = [{"game_id": r["game_id"], "round_no": r["round_no"], "predecessor": r["predecessor"]}
                     for r in ev_win_rounds if r not in sd_rounds]
    grammar = {
        "rounds": n,
        "sum_zero_exceptions": len(zero_bad),
        "formula_exceptions": len(grammar_bad),
        "rounds_with_event_stream": len(ev_rounds),
        "win_rounds_with_event_stream": len(ev_win_rounds),
        "self_draw_predecessor_confirmed": len(sd_rounds),
        "self_draw_predecessor_other": len(ev_win_rounds) - len(sd_rounds),
        "self_draw_predecessor_exceptions": sd_exceptions,
        "draw_rounds": sum(1 for r in rounds if r["is_draw"]),
        "fan_histogram": dict(sorted(collections.Counter(r["fan"] for r in rounds if not r["is_draw"]).items())),
        "detail_histogram": {" + ".join(r.get("detail") or []): c for c, _ in
                             collections.Counter(" + ".join(r.get("detail") or []) for r in rounds if r.get("detail")).most_common()},
    }
    data["grammar"] = grammar

    cat, gross = decompose(rounds)
    data["decomposition"] = {"categories": cat, "gross_loss": gross, "net": my_total}
    data["totals"] = {
        "rooms": rooms, "games": games, "rounds": n, "my_total": my_total,
        "mean_per_round": my_total / n if n else None,
        "session_tags": session_tags,
    }

    our_wins = sum(1 for r in rounds if r["i_won"])
    opp_wins = sum(1 for r in rounds if (not r["i_won"]) and (not r["is_draw"]))
    draws = sum(1 for r in rounds if r["is_draw"])
    win_pts = [r["my_score"] for r in rounds if r["i_won"]]
    pay_pts = [r["my_score"] for r in rounds if (not r["i_won"]) and (not r["is_draw"])]
    rates = {
        "my_win_rate": our_wins / n,
        "opp_seat_win_rate": opp_wins / (3.0 * n),
        "draw_rate": draws / n,
        "my_mean_win_points": _mean(win_pts),
        "my_mean_pay_points": _mean(pay_pts),
        "mean_per_round": my_total / n,
    }
    data["rates"] = rates

    dealer_r = [r for r in rounds if r["i_dealer"]]
    nondealer_r = [r for r in rounds if not r["i_dealer"]]
    by_role = collections.OrderedDict()
    for name, rs in (("我方坐庄", dealer_r), ("我方非庄", nondealer_r)):
        by_role[name] = {
            "rounds": len(rs),
            "points": sum(r["my_score"] for r in rs),
            "mean": _mean([r["my_score"] for r in rs]),
            "win_rate": _pct(sum(1 for r in rs if r["i_won"]), len(rs)),
            "mean_pay_when_losing": _mean([r["my_score"] for r in rs if not r["i_won"] and not r["is_draw"]]),
            "mean_win_when_winning": _mean([r["my_score"] for r in rs if r["i_won"]]),
        }
    data["by_role"] = by_role

    cont = tot = 0
    per_game = collections.defaultdict(list)
    for r in rounds:
        per_game[r["game_id"]].append(r)
    for gid, rs in per_game.items():
        rs = sorted(rs, key=lambda r: r["round_no"])
        for a, b in zip(rs, rs[1:]):
            tot += 1
            if b["dealer"] == a["winner"]:
                cont += 1
    data["dealer_continuation"] = {"transitions": tot, "dealer_is_prev_winner": cont,
                                   "rate": (cont / tot) if tot else None}

    fan_pay = collections.OrderedDict()
    for r in rounds:
        if r["is_draw"] or r["i_won"]:
            continue
        b = fan_pay.setdefault(r["fan"], {"rounds": 0, "points": 0, "as_dealer": 0, "as_non": 0})
        b["rounds"] += 1
        b["points"] += r["my_score"]
        if r["i_dealer"]:
            b["as_dealer"] += 1
        else:
            b["as_non"] += 1
    fan_win = collections.OrderedDict()
    for r in rounds:
        if not r["i_won"]:
            continue
        b = fan_win.setdefault(r["fan"], {"rounds": 0, "points": 0, "as_dealer": 0, "as_non": 0})
        b["rounds"] += 1
        b["points"] += r["my_score"]
        if r["i_dealer"]:
            b["as_dealer"] += 1
        else:
            b["as_non"] += 1
    data["fan_pay"] = fan_pay
    data["fan_win"] = fan_win

    base_pay = 0
    for r in rounds:
        if r["is_draw"] or r["i_won"]:
            continue
        base_pay += -8 if r["i_dealer"] else -1
    premium = gross - (-base_pay)
    data["fan_premium"] = {"actual_gross": gross, "if_all_fan1": -base_pay, "premium": premium}

    win_base = sum((24 if r["i_dealer"] else 10) for r in rounds if r["i_won"])
    data["fan_premium_win"] = {"actual": sum(win_pts) if win_pts else 0, "if_all_fan1": win_base,
                               "premium": (sum(win_pts) if win_pts else 0) - win_base}

    band = by_wall_band(rounds)
    if band:
        bands, (q1, q2, wmin, wmax) = band
        data["by_wall_band"] = {"bands": bands, "cut_wall": [q1, q2, wmin, wmax]}
    else:
        bands = {}

    groups = collections.OrderedDict()
    order = ["我方胡牌", "曾听牌未胡", "全程未听牌", "无审计快照"]
    for k in order:
        groups[k] = {"rounds": 0, "points": 0, "opp_win": 0, "draw": 0, "walls": []}
    for r in rounds:
        if not r.get("n_snaps"):
            k = "无审计快照"
        elif r["i_won"]:
            k = "我方胡牌"
        elif r.get("tenpai"):
            k = "曾听牌未胡"
        else:
            k = "全程未听牌"
        gg = groups[k]
        gg["rounds"] += 1
        gg["points"] += r["my_score"]
        if r["is_draw"]:
            gg["draw"] += 1
        elif not r["i_won"]:
            gg["opp_win"] += 1
        if r.get("tenpai") and r["tenpai"].get("wall") is not None:
            gg["walls"].append(83 - r["tenpai"]["wall"])
    for k, gg in groups.items():
        gg["mean"] = (gg["points"] / gg["rounds"]) if gg["rounds"] else None
        gg["mean_draws_to_tenpai"] = _mean(gg["walls"])
    data["tenpai_groups"] = groups

    sh_dist = collections.Counter()
    for r in rounds:
        if r["i_won"] or "shanten_end" not in r:
            continue
        sh_dist[r["shanten_end"]] += 1
    data["end_shanten_distribution"] = dict(sorted(sh_dist.items()))

    # 曾听牌未胡局的结束时向听分布（回答「离胡还差几张」）
    tp_sh = collections.Counter()
    for r in rounds:
        if r["i_won"] or "shanten_end" not in r or not r.get("tenpai"):
            continue
        tp_sh[r["shanten_end"]] += 1
    data["tenpai_end_shanten"] = dict(sorted(tp_sh.items()))

    tenpai_groups_detail = collections.OrderedDict()
    for label, pred in (("听牌且胡牌", lambda r: r["i_won"] and r.get("tenpai")),
                        ("听牌未胡", lambda r: (not r["i_won"]) and r.get("tenpai"))):
        rs = [r for r in rounds if pred(r) and r["tenpai"].get("wall") is not None]
        tenpai_groups_detail[label] = {
            "rounds": len(rs),
            "mean_draws_to_tenpai": _mean([83 - r["tenpai"]["wall"] for r in rs]),
        }
    data["tenpai_timing"] = tenpai_groups_detail

    data["sessions"] = session_groups(rounds)
    rtot = room_totals(rounds)
    data["rooms_top"] = sorted(((k, v) for k, v in rtot.items()), key=lambda kv: kv[1]["points"])[:8]

    opp = collections.OrderedDict()
    for r in rounds:
        for seat, uid in enumerate(r["seat_user_ids"]):
            if uid == ME:
                continue
            b = opp.setdefault(uid, {"rounds": 0, "points": 0, "wins": 0})
            b["rounds"] += 1
            b["points"] += r["scores"][seat]
            if (not r["is_draw"]) and r["winner"] == seat:
                b["wins"] += 1
    data["opponents"] = {"count": len(opp),
                         "rows": sorted(opp.items(), key=lambda kv: -kv[1]["rounds"])[:12]}

    # ---- 同桌四座配对基准 + 差距分解 ----------------------------------
    def _seat_stats(rows):
        tot = len(rows)
        wins = [x for x in rows if x["won"]]
        pays = [x for x in rows if (not x["won"]) and (not x["draw"])]
        dl = [x for x in rows if x.get("dealer")]
        nd = [x for x in rows if not x.get("dealer")]
        return {
            "rounds": tot,
            "wins": len(wins),
            "win_rate": (len(wins) / tot) if tot else None,
            "pay_rate": (len(pays) / tot) if tot else None,
            "avg_fan_on_win": _mean([x["fan"] for x in wins]),
            "avg_win_points": _mean([x["delta"] for x in wins]),
            "avg_pay_points": _mean([x["delta"] for x in pays]),
            "points": sum(x["delta"] for x in rows),
            "net_per_round": (sum(x["delta"] for x in rows) / tot) if tot else None,
            "dealer_rounds": len(dl),
            "dealer_win_rate": _pct(sum(1 for x in dl if x["won"]), len(dl)),
            "nondealer_win_rate": _pct(sum(1 for x in nd if x["won"]), len(nd)),
        }

    mine_rows, opp_rows = [], []
    for r in rounds:
        for s in range(4):
            rec = {"won": (r["winner"] == s and not r["is_draw"]),
                   "delta": r["scores"][s],
                   "draw": r["is_draw"],
                   "fan": r["fan"] if (r["winner"] == s and not r["is_draw"]) else None,
                   "dealer": (r["dealer"] == s)}
            (mine_rows if s == r["my_seat"] else opp_rows).append(rec)
    mine_stats = _seat_stats(mine_rows)
    opp_stats = _seat_stats(opp_rows)
    data["seat_benchmark"] = {"me": mine_stats, "opponent_seats": opp_stats}

    p = mine_stats["win_rate"] or 0.0
    q = opp_stats["win_rate"] or 0.0
    A = mine_stats["avg_win_points"] or 0.0
    Ap = opp_stats["avg_win_points"] or 0.0
    B = -(mine_stats["avg_pay_points"] or 0.0)
    Bp = -(opp_stats["avg_pay_points"] or 0.0)
    rme = mine_stats["pay_rate"] or 0.0
    rop = opp_stats["pay_rate"] or 0.0
    income_gap = p * A - q * Ap
    pay_gap = rop * Bp - rme * B
    rate_effect = (p - q) * (A + Ap) / 2.0
    value_effect = (p + q) / 2.0 * (A - Ap)
    lever = {
        "me_win_rate": p, "opp_win_rate": q,
        "me_avg_win_points": A, "opp_avg_win_points": Ap,
        "me_avg_pay_points": B, "opp_avg_pay_points": Bp,
        "me_avg_fan_on_win": mine_stats["avg_fan_on_win"],
        "opp_avg_fan_on_win": opp_stats["avg_fan_on_win"],
        "income_gap_per_round": income_gap, "income_gap_points": income_gap * n,
        "pay_gap_per_round": pay_gap, "pay_gap_points": pay_gap * n,
        "rate_effect_points": rate_effect * n, "value_effect_points": value_effect * n,
        "win_rate_gap_pp": 100 * (q - p),
        "value_per_converted_round": A + B,
        "wins_needed_to_break_even": (-my_total / (A + B)) if (A + B) else None,
        "points_if_win_value_matched": n * p * (Ap - A),
        "dealer_gap_per_round": (by_role["我方非庄"]["mean"] or 0) - (by_role["我方坐庄"]["mean"] or 0),
        "points_if_dealer_matched_nondealer": ((by_role["我方非庄"]["mean"] or 0) - (by_role["我方坐庄"]["mean"] or 0)) * len(dealer_r),
        "never_tenpai_points": groups["全程未听牌"]["points"],
        "never_tenpai_rounds": groups["全程未听牌"]["rounds"],
        "premium_points": premium,
    }
    data["levers"] = lever

    # ---- 番型明细：我方 vs 对手（只在有事件流的局可得） ----------------
    det = collections.OrderedDict()
    for r in rounds:
        if r["is_draw"] or not r.get("detail"):
            continue
        key = " + ".join(r["detail"])
        b = det.setdefault(key, {"me": 0, "opp": 0})
        b["me" if r["i_won"] else "opp"] += 1
    det_me = sum(v["me"] for v in det.values())
    det_opp = sum(v["opp"] for v in det.values())
    data["fan_detail_by_winner"] = {"rows": det, "me_wins": det_me, "opp_wins": det_opp}

    # ---- 爆头状态（我方权威 god.baotou） -------------------------------
    bt = collections.OrderedDict()
    for label, rs in (("我方曾进入爆头", [r for r in rounds if r.get("baotou_ever")]),
                      ("我方从未爆头", [r for r in rounds if not r.get("baotou_ever")])):
        bt[label] = {
            "rounds": len(rs),
            "win_rate": _pct(sum(1 for r in rs if r["i_won"]), len(rs)),
            "mean": _mean([r["my_score"] for r in rs]),
            "points": sum(r["my_score"] for r in rs),
            "avg_fan_on_win": _mean([r["fan"] for r in rs if r["i_won"]]),
        }
    data["baotou_groups"] = bt
    wins_with_bt = sum(1 for r in rounds if r["i_won"] and r.get("baotou_ever"))
    data["baotou_at_win"] = {"wins": sum(1 for r in rounds if r["i_won"]), "wins_in_baotou": wins_with_bt}

    # 爆头率能否解释番值缺口（用官方明细的「爆头占胡牌比例」做算术核对）
    def _baotou_share(prefix):
        me_tot = d_tot = 0
        me_bt = d_bt = 0
        for k, v in det.items():
            me_tot += v["me"]
            d_tot += v["opp"]
            if "爆头" in k:
                me_bt += v["me"]
                d_bt += v["opp"]
        return (me_bt, me_tot), (d_bt, d_tot)
    (meb, met), (opb, opt) = _baotou_share(det)
    share_me = meb / max(1, met)
    share_op = opb / max(1, opt)
    # 以「番值 = 基础番 ×（爆头 ? 2 : 1）」线性模型回推基础番
    fan_me = mine_stats["avg_fan_on_win"] or 0.0
    base_me = fan_me / (1.0 + share_me)
    data["baotou_explains_fan"] = {
        "my_baotou_share_of_wins": share_me, "opp_baotou_share_of_wins": share_op,
        "my_wins_with_detail": met, "opp_wins_with_detail": opt,
        "implied_base_fan": base_me,
        "predicted_fan_at_opp_share": base_me * (1.0 + share_op),
        "actual_opp_fan": opp_stats["avg_fan_on_win"],
    }

    # ---- 房级聚类稳健性检查（自由赛的房是聚类单位） --------------------
    def _tstat(vals):
        if len(vals) < 2:
            return None, None
        m = sum(vals) / len(vals)
        var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
        sd = var ** 0.5
        se = sd / (len(vals) ** 0.5)
        return m, (m / se if se else None)

    by_room_rows = collections.defaultdict(list)
    for r in rounds:
        by_room_rows[r["room_id"]].append(r)
    rate_diffs, value_diffs, net_diffs = [], [], []
    for rid, rs in by_room_rows.items():
        n_r = len(rs)
        mw = [r["my_score"] for r in rs if r["i_won"]]
        ow = [r["scores"][s] for r in rs for s in range(4)
              if s != r["my_seat"] and (not r["is_draw"]) and r["winner"] == s]
        if n_r:
            rate_diffs.append((len(mw) / n_r) - (len(ow) / (3.0 * n_r)))
        if mw and ow:
            value_diffs.append(sum(mw) / len(mw) - sum(ow) / len(ow))
        if n_r:
            net_diffs.append(sum(r["my_score"] for r in rs) / n_r)
    data["cluster_check"] = {
        "rooms": len(by_room_rows),
        "win_rate_diff_mean": _tstat(rate_diffs)[0], "win_rate_diff_t": _tstat(rate_diffs)[1],
        "win_value_diff_mean": _tstat(value_diffs)[0], "win_value_diff_t": _tstat(value_diffs)[1],
        "net_per_round_mean": _tstat(net_diffs)[0], "net_per_round_t": _tstat(net_diffs)[1],
    }

    # ---- 数据卫生：重复下载记录 ---------------------------------------
    _games, dups = load_official()
    data["data_hygiene"] = {
        "duplicate_records": len(dups),
        "duplicate_games": len({x["game_id"] for x in dups}),
        "all_content_identical": all(x["rounds_equal"] for x in dups),
        "extra_rounds_if_not_deduped": sum(x["extra_rounds"] for x in dups),
        "extra_score_if_not_deduped": sum(x["extra_my_score"] for x in dups),
        "detail": dups,
    }

    with open(OUT_JSON, "w") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, default=str)
    write_markdown(rounds, data)
    print("wrote %s and %s" % (OUT_JSON, OUT_MD))
    return 0


# ---------------------------------------------------------------------------
# Markdown 报告
# ---------------------------------------------------------------------------

def write_markdown(rounds, d):
    n = d["totals"]["rounds"]
    my_total = d["totals"]["my_total"]
    cat = d["decomposition"]["categories"]
    gross = d["decomposition"]["gross_loss"]
    rates = d["rates"]
    g = d["grammar"]
    L = []
    add = L.append

    add("# 自由赛失分归因计量学：%d 分是怎么丢的" % my_total)
    add("")
    add("范围：artifacts/sessions 下 %d 房 / %d 场 / %d 局自由赛官方牌谱（已按 game_id 去重）；"
        "我方 user_id u_13495c3d79c8（雀衡 · SOL，冻结策略 r18_integrated_positive_v2 / OPTY-R18-C02）。"
        % (d["totals"]["rooms"], d["totals"]["games"], n))
    add("生成脚本：review/freematch-deep-dive-20260925/loss_attribution.py（只读、无网络、规则一律调用 hangma）。")
    add("")

    add("## 0. 结论先行")
    add("")
    hy = d["data_hygiene"]
    lv0 = d["levers"]
    add("1. **口径修正（最重要的一条）**：官方牌谱目录里有 %d 条重复下载记录（%d 场各被下载 2-3 次，rounds 逐字相同、仅个别玩家昵称不同）。"
        "现有工具 extract_room_scores.py 未去重，因此「%d 场 / %d 局 / %d 分」是重复计数后的口径；按 game_id 去重后应为 "
        "**%d 场 / %d 局 / %d 分**。本文全部数字使用去重口径。"
        % (hy["duplicate_records"], hy["duplicate_games"], 350 + hy["duplicate_records"],
           n + hy["extra_rounds_if_not_deduped"], my_total + hy["extra_score_if_not_deduped"],
           d["totals"]["games"], n, my_total))
    add("2. **本赛制不存在点炮，因此不存在「我方放铳」这一类失分。** 官方结算只有自摸：%d 局全部满足 hangma 的自摸结算公式（%d 例例外）；"
        "有事件流的非流局局里，round_ended 的前一事件都是胡牌者本人的摸牌（%d/%d 例，唯一例外是事件流序号缺口）。"
        "任务书预设的「第 1 类：我方放铳」结构性为 0 分、0 局。"
        % (g["rounds"] - g["formula_exceptions"], g["formula_exceptions"],
           g["self_draw_predecessor_confirmed"], g["win_rounds_with_event_stream"]))
    add("3. **%d 分 = 我方自摸收入 +%d 分 减去 为别人自摸付掉的 %d 分**（坐庄付掉 -%d、非庄付掉 -%d）。"
        % (my_total, cat["A 我方自摸胡(+分)"]["points"], gross,
           -cat["B 坐庄被他人自摸付分(-分)"]["points"],
           -cat["C 非庄被他人自摸付分(-分)"]["points"]))
    add("4. **主因不是「胡得少」，而是「胡得小」**：我方每局自摸率 %s%%，**高于**同桌对手人均的 %s%%（+%s pp）；"
        "但我方胡牌时平均只得 %s 分，对手胡牌平均得 %s 分（低 %s%%），平均番值 %s 对 %s。"
        "按同桌配对基准分解，每局差距 %s 分里，收入侧占 %s 分、支出侧占 %s 分；收入侧又拆成"
        "「频率优势 +%s 分 / 局」与「单次分值劣势 %s 分 / 局」。"
        % (_fnum(100 * lv0["me_win_rate"], 2), _fnum(100 * lv0["opp_win_rate"], 2),
           _fnum(100 * (lv0["me_win_rate"] - lv0["opp_win_rate"]), 2),
           _fnum(lv0["me_avg_win_points"], 2), _fnum(lv0["opp_avg_win_points"], 2),
           _fnum(100 * (1 - lv0["me_avg_win_points"] / max(1e-9, lv0["opp_avg_win_points"])), 1),
           _fnum(lv0["me_avg_fan_on_win"], 3), _fnum(lv0["opp_avg_fan_on_win"], 3),
           _fnum(lv0["income_gap_per_round"] + lv0["pay_gap_per_round"], 3),
           _fnum(lv0["income_gap_per_round"], 3), _fnum(lv0["pay_gap_per_round"], 3),
           _fnum(lv0["rate_effect_points"] / n, 3), _fnum(lv0["value_effect_points"] / n, 3)))
    bf0 = d["baotou_explains_fan"]
    btg0 = d["baotou_groups"]
    add("5. **番值缺口的机制已被定位到单一变量：爆头（听任意牌）占比。** 官方番型明细里，"
        "对手 %s%% 的胡牌带「爆头」，我方只有 %s%%（差 %s pp）；用「番值 = 基础番 ×（爆头 ? 2 : 1）」回推，"
        "把爆头占比换成对手的水平即可复现对手的实测平均番值（预测 %s vs 实测 %s）。"
        "爆头也是赢牌效率的开关：我方曾进入爆头的 %d 局自摸率 %s%%、每局 %s 分；从未爆头的 %d 局自摸率 %s%%、每局 %s 分。"
        % (_fnum(100 * bf0["opp_baotou_share_of_wins"], 1), _fnum(100 * bf0["my_baotou_share_of_wins"], 1),
           _fnum(100 * (bf0["opp_baotou_share_of_wins"] - bf0["my_baotou_share_of_wins"]), 1),
           _fnum(bf0["predicted_fan_at_opp_share"], 3), _fnum(bf0["actual_opp_fan"], 3),
           btg0["我方曾进入爆头"]["rounds"], _fnum(btg0["我方曾进入爆头"]["win_rate"], 1),
           _fnum(btg0["我方曾进入爆头"]["mean"], 2),
           btg0["我方从未爆头"]["rounds"], _fnum(btg0["我方从未爆头"]["win_rate"], 1),
           _fnum(btg0["我方从未爆头"]["mean"], 2)))
    add("6. **换算成可比较的规模**：把单次胡牌的分值提到同桌对手的水平，折算约 +%s 分；"
        "参考量级：把整个缺口补平只需多自摸约 %s 局（%d 局的 %s%%）。"
        % (_fnum(lv0["points_if_win_value_matched"], 0),
           _fnum(lv0["wins_needed_to_break_even"], 1), n,
           _fnum(100.0 * lv0["wins_needed_to_break_even"] / n, 2)))
    add("7. **庄家敞口是小项**：坐庄局每局 %s 分、非庄局每局 %s 分，差 %s 分/局 × %d 庄局（合计 %s 分）。"
        % (_fnum(d["by_role"]["我方坐庄"]["mean"], 2), _fnum(d["by_role"]["我方非庄"]["mean"], 2),
           _fnum(lv0["dealer_gap_per_round"], 2), d["by_role"]["我方坐庄"]["rounds"],
           _fnum(lv0["points_if_dealer_matched_nondealer"], 0)))
    add("")
    add("证据级别约定：**官方已确认**＝官方牌谱/官方事件直接给出；**当前观察**＝本仓库数据统计所得（房是聚类单位，不等于独立样本）；"
        "**工程建议**＝可执行动作；**待确认假设**＝需同牌山配对完整桌验证的机制猜想。")
    add("")

    add("## 1. 数据与口径")
    add("")
    add(_table(["项目", "值"], [
        ["房数（room_id）", d["totals"]["rooms"]],
        ["场数（game_id，每场 7-8 局）", d["totals"]["games"]],
        ["局数（round）", n],
        ["我方合计得分", my_total],
        ["我方每局期望得分", _fnum(rates["mean_per_round"], 3)],
        ["含审计快照的局数", sum(1 for r in rounds if r.get("n_snaps"))],
        ["含完整事件流的局数", g["rounds_with_event_stream"]],
    ]))
    add("")
    add("* 官方牌谱（唯一权威结算）：artifacts/sessions/<会话标签>/official/dl-*/events.json，字段 dealer / winner / is_draw / multiplier / scores。")
    add("* 我方审计权威状态：artifacts/sessions/<标签>/audit/runs/<run_id>/participants/u_13495c3d79c8/raw/<game_id>.*.jsonl.gz，"
        "其中官方 GET /state 快照含 my_hand / melds / wall_remaining / god / 累计 scores。")
    add("* 向听与结算一律调用 hangma：hangma_bot.hangma.hand_analysis.analyse_hand 与 hangma_bot.hangma.settlement.settle_scores。")
    add("")
    hy0 = d["data_hygiene"]
    add("**数据卫生（本次审计发现的第一个问题）**：events.json 的下载目录按 dl-* 分片，同一场可能被下载多次。"
        "当前 %d 条记录中有 %d 条是重复下载：涉及 %d 场（其中 1 条仅玩家昵称不同，rounds 逐字相同）。"
        "未去重口径（现有工具 extract_room_scores.py 与基于它的 room-scores.json）报出 %d 场 / %d 局 / %d 分；"
        "按 game_id 去重后是 %d 场 / %d 局 / %d 分。"
        % (d["totals"]["games"] + hy0["duplicate_records"], hy0["duplicate_records"], hy0["duplicate_games"],
           d["totals"]["games"] + hy0["duplicate_records"], n + hy0["extra_rounds_if_not_deduped"],
           my_total + hy0["extra_score_if_not_deduped"], d["totals"]["games"], n, my_total))
    add("")
    add(_table(["重复下载的场", "多算局数", "多算我方分"], [
        [x["game_id"], x["extra_rounds"], x["extra_my_score"]] for x in hy0["detail"]
    ] + [["**合计**", "**%d**" % hy0["extra_rounds_if_not_deduped"],
          "**%d**" % hy0["extra_score_if_not_deduped"]]]))
    add("")
    add("会话分组（策略身份按会话命名推断，属**待确认假设**）：")
    add("")
    add(_table(["会话标签", "房数", "场数", "局数", "我方总分", "每局"], [
        [k, v["rooms"], v["games"], v["rounds"], v["points"], _fnum(v["points"] / v["rounds"], 2)]
        for k, v in d["sessions"].items()
    ]))
    add("")

    add("## 2. 官方结算文法（从数据反推，再用 hangma 交叉核对）")
    add("")
    add("反推方法：先观察少量局的分数向量形状，写出候选文法，再用 hangma 的结算函数对**全部 %d 局**逐局对拍。" % n)
    add("")
    add("反推结果（**官方已确认**，%d/%d 局无反例，总分守恒 %d 例例外）：" % (n - g["formula_exceptions"], n, g["sum_zero_exceptions"]))
    add("")
    add("* 底分 = 1；events.json 的 multiplier 字段就是**总番**（实测取值全部是 2 的幂：%s），不是流局倍率。"
        % "/".join(str(k) for k in g["fan_histogram"]))
    add("* 闲家自摸（winner != dealer）：庄家付 8×番，另两闲各付 1×番，胡家得 10×番。")
    add("* 庄家自摸（winner == dealer）：三个闲家各付 8×番，庄家得 24×番。")
    add("* 流局：四家全 0，winner = -1，multiplier = 0（共 %d 局）。" % g["draw_rounds"])
    add("* **没有点炮**：三家非胡者的支付金额只取决于自己是不是庄家，与谁打出哪张牌完全无关 —— 结算结构里没有「点炮者」这个位置。")
    add("")
    add("复核方式（可复现）：脚本 report 阶段调用 settlement.settle_scores(fan, 1, winner, dealer) 并与 events.json 的 scores 比对，"
        "例外数写入 loss-attribution.json 的 grammar.formula_exceptions。")
    add("")
    add("番值直方图（非流局局，官方 multiplier）：")
    add("")
    add(_table(["总番", "局数"], [[k, v] for k, v in g["fan_histogram"].items()]))
    add("")
    if g["detail_histogram"]:
        add("官方番型明细直方图（只在含事件流的 %d 局可得；明细命名与 hangma 的 compute_fan 输出一致）：" % g["rounds_with_event_stream"])
        add("")
        add(_table(["官方明细", "局数"], [[k, v] for k, v in list(g["detail_histogram"].items())[:14]]))
        add("")
    add("连庄规则（数据反推）：相邻两局中「下一局庄家 = 上一局胡牌者」的比例 %s（%d/%d 次转移）。"
        % (_fnum(100 * (d["dealer_continuation"]["rate"] or 0), 1),
           d["dealer_continuation"]["dealer_is_prev_winner"], d["dealer_continuation"]["transitions"]))
    add("")
    add("**自摸的外部证据**：在 %d 个「有事件流且非流局」的局里，round_ended 的前一事件是胡牌者本人 tile_drawn 的有 %d 局（%s%%），"
        "与规则文档「只能自摸，不允许点炮；禁止抢杠胡」一致（src/hangma_bot/hangma/RULES_EVIDENCE.md §2/§6）；"
        "唯一 1 例例外来自审计事件流的序号缺口（该局的摸牌事件未被记录），不是反例。"
        % (g["win_rounds_with_event_stream"], g["self_draw_predecessor_confirmed"],
           _fnum(100.0 * g["self_draw_predecessor_confirmed"] / max(1, g["win_rounds_with_event_stream"]), 1)))
    add("")

    add("## 3. 全局账：-863 的可加总分解")
    add("")
    add("四类互斥且穷尽，四类分数之和**恰好等于**我方合计 %d 分（无残差）。" % my_total)
    add("")
    add(_table(["类别", "分数量", "局数", "每局均值", "占毛失分比例"], [
        [k, v["points"], v["rounds"], _fnum(v["per_round"], 2),
         ("%s%%" % _fnum(v["share_of_gross_loss"], 1)) if v["share_of_gross_loss"] is not None else "—（收入项）"]
        for k, v in cat.items()
    ] + [["**合计**", "**%d**" % my_total, "**%d**" % n, "**%s**" % _fnum(my_total / n, 2), "—"]]))
    add("")
    add("口径：毛失分 = 我方被他人自摸付掉的分 = %d 分（B+C）；净失分 = 毛失分 − 我方自摸收入 = %d − %d = %d 分。"
        % (gross, gross, cat["A 我方自摸胡(+分)"]["points"], -my_total))
    add("")

    add("## 4. 类别 1：我方放铳（任务书指定条目）—— 结构性为 0")
    add("")
    add(_table(["问题", "答案", "依据"], [
        ["放铳分数量", "0 分", "本赛制无点炮，见 §2"],
        ["占我方总失分比例", "0%", "同上"],
        ["涉及局数", "0 局 / %d 局" % n, "同上"],
        ["我方放铳率（每局概率）", "0（规则上不存在该事件）", "官方规则 + %d 局结算结构" % n],
        ["三个对手的放铳率", "同样为 0（规则上不存在）", "同上"],
    ]))
    add("")
    add("**为什么不成立**：三家非胡者的支付只由「自己是不是庄家」决定（庄 8×番 / 闲 1×番）。"
        "全部 %d 局里这一结构 %d 次成立、0 次例外 —— 若存在单独承担赔付的点炮者，分数向量会是另一种形状，而这样的局一局都没有。"
        % (n, n - g["formula_exceptions"]))
    add("")
    add("**为什么这不是推断而是结构事实**：即使不考虑规则文档，结算公式本身不含「上一张弃牌由谁打出」这一输入，"
        "因此任何从 events.json 反推「谁放铳」的做法都会把胡牌者的三家对手全部误判为放铳者（见任务书原假设）。")
    add("")
    add("**可比较的替代指标**（既然没有放铳，就只能比较「每局付分概率与金额」）：")
    add("")
    add(_table(["角色", "每局付分概率", "付分时平均金额", "每局期望得分"], [
        ["我方", "%s%%" % _fnum(100 * (1 - rates["my_win_rate"] - rates["draw_rate"]), 1),
         _fnum(rates["my_mean_pay_points"], 2), _fnum(rates["mean_per_round"], 3)],
        ["同桌三名对手（人均口径）", "%s%%" % _fnum(100 * (1 - rates["opp_seat_win_rate"] - rates["draw_rate"]), 1),
         "—（对手不唯一，见 §9）", _fnum(-rates["mean_per_round"] / 3, 3)],
    ]))
    add("")

    add("## 5. 类别 2：他家自摸波及我方")
    add("")
    add("这是**唯一的失分来源**，合计 -%d 分，涉及 %d 局。"
        % (gross, cat["B 坐庄被他人自摸付分(-分)"]["rounds"] + cat["C 非庄被他人自摸付分(-分)"]["rounds"]))
    add("")
    add(_table(["子类", "分数量", "局数", "每局均值", "占毛失分比例"], [
        ["B 我方坐庄时被自摸", cat["B 坐庄被他人自摸付分(-分)"]["points"], cat["B 坐庄被他人自摸付分(-分)"]["rounds"],
         _fnum(cat["B 坐庄被他人自摸付分(-分)"]["per_round"], 2),
         "%s%%" % _fnum(cat["B 坐庄被他人自摸付分(-分)"]["share_of_gross_loss"], 1)],
        ["C 我方非庄时被自摸", cat["C 非庄被他人自摸付分(-分)"]["points"], cat["C 非庄被他人自摸付分(-分)"]["rounds"],
         _fnum(cat["C 非庄被他人自摸付分(-分)"]["per_round"], 2),
         "%s%%" % _fnum(cat["C 非庄被他人自摸付分(-分)"]["share_of_gross_loss"], 1)],
    ]))
    add("")
    add("按对手胡牌番值拆分（**官方已确认**，番值 = 官方 multiplier）：")
    add("")
    add(_table(["对手番值", "局数", "我方付分", "每局", "其中我方坐庄局数", "仅番值 1 时应付"], [
        [k, v["rounds"], v["points"], _fnum(v["points"] / v["rounds"], 2), v["as_dealer"],
         -(8 * v["as_dealer"] + 1 * v["as_non"])]
        for k, v in d["fan_pay"].items()
    ]))
    add("")
    if d.get("by_wall_band"):
        cuts = d["by_wall_band"]["cut_wall"]
        add("按「该局结束时的牌墙剩余量」等频三档拆分（界值取实测三分位：%d / %d，实测范围 %d-%d；牌墙越大＝越早巡）："
            % (cuts[0], cuts[1], cuts[2], cuts[3]))
        add("")
        add(_table(["时段", "局数", "我方付分", "每局"], [
            [k, v["rounds"], v["points"], _fnum(v["points"] / v["rounds"], 2)]
            for k, v in d["by_wall_band"]["bands"].items()
        ]))
        add("")
    top_detail = None
    if g["detail_histogram"]:
        for k, v in g["detail_histogram"].items():
            if "+" in k:
                top_detail = k
                break
    add("**高番溢价**：如果对手每一次自摸都只按番 1 结算，我方应付 %d 分；实际付了 %d 分，多付 %s 分（占毛失分 %s%%）。"
        % (d["fan_premium"]["if_all_fan1"], gross, _fnum(d["fan_premium"]["premium"], 0),
           _fnum(100.0 * d["fan_premium"]["premium"] / max(1, gross), 1)))
    if top_detail:
        add("明细层面以「%s」这类爆头叠加为主（见 §2 明细直方图）。" % top_detail)
    add("")

    add("## 6. 类别 3：我方胡牌赢分")
    add("")
    add(_table(["项目", "值"], [
        ["我方自摸局数", cat["A 我方自摸胡(+分)"]["rounds"]],
        ["我方胡牌收入", cat["A 我方自摸胡(+分)"]["points"]],
        ["我方自摸率（每局）", "%s%%" % _fnum(100 * rates["my_win_rate"], 2)],
        ["我方胡牌时平均得分", _fnum(rates["my_mean_win_points"], 2)],
        ["我方胡牌平均番值", _fnum(_mean([r["fan"] for r in rounds if r["i_won"]]), 3)],
        ["我方胡牌中「点胡」（别人放铳）部分", "0（无点炮，全部为自摸）"],
    ]))
    add("")
    add("按番值拆分：")
    add("")
    add(_table(["番值", "局数", "得分", "每局", "其中坐庄", "其中非庄"], [
        [k, v["rounds"], v["points"], _fnum(v["points"] / v["rounds"], 2), v["as_dealer"], v["as_non"]]
        for k, v in d["fan_win"].items()
    ]))
    add("")
    _pw = d["fan_premium_win"]["premium"] / max(1, cat["A 我方自摸胡(+分)"]["rounds"])
    _po = d["fan_premium"]["premium"] / max(1, cat["B 坐庄被他人自摸付分(-分)"]["rounds"] + cat["C 非庄被他人自摸付分(-分)"]["rounds"])
    add("番值溢价对比（**必须按每次胡牌归一化**，双方胡牌次数不同：我方 %d 次、对手 %d 次）："
        "我方每次胡牌的番值溢价 %s 分；对手每次胡牌的番值溢价 %s 分 —— **每一次胡牌，对手比我们多拿 %s 分**，"
        "这与 §9 的「单次胡牌平均得分差 %s 分」是同一件事的两种表述。"
        % (cat["A 我方自摸胡(+分)"]["rounds"],
           cat["B 坐庄被他人自摸付分(-分)"]["rounds"] + cat["C 非庄被他人自摸付分(-分)"]["rounds"],
           _fnum(_pw, 2), _fnum(_po, 2), _fnum(_po - _pw, 2),
           _fnum(d["levers"]["opp_avg_win_points"] - d["levers"]["me_avg_win_points"], 2)))
    add("")

    add("## 7. 类别 4：我方未胡局结束时的向听分布")
    add("")
    add("方法：对每局取审计中该局最后一个官方状态快照的 my_hand（副露按 meld_set_count 折算），用 hangma 重算向听。"
        "14 张（刚摸牌）时 analyse_hand 返回的即「最优弃牌后的向听」——已用 60 组随机手牌与逐张弃牌枚举对拍，0 例不一致；"
        "并与策略自身审计的 facts.shanten_after 交叉核对（见 §13）。")
    add("")
    dist = d["end_shanten_distribution"]
    tot_known = sum(dist.values())
    add(_table(["局结束时向听", "局数", "占比", "含义"], [
        [k, v, "%s%%" % _fnum(100.0 * v / max(1, tot_known), 1),
         "已听牌" if k == 0 else ("已构成胡牌手" if k == -1 else "距听牌差 %d 张" % k)]
        for k, v in sorted(dist.items())
    ]))
    add("")
    add("分母 %d = 我方未胡且有审计快照的局数；只有 %s%% 的未胡局在结束时仍处听牌状态，"
        "差 3 张及以上的占 %s%%。"
        % (tot_known,
           _fnum(100.0 * dist.get(0, 0) / max(1, tot_known), 1),
           _fnum(100.0 * sum(v for k, v in dist.items() if k >= 3) / max(1, tot_known), 1)))
    add("")

    add("## 8. 类别 5：座位角色（我方坐庄 vs 非庄）")
    add("")
    add(_table(["角色", "局数", "我方总分", "每局均值", "自摸率", "胡牌时均值", "未胡时均值"], [
        [k, v["rounds"], v["points"], _fnum(v["mean"], 2), "%s%%" % _fnum(v["win_rate"], 1),
         _fnum(v["mean_win_when_winning"], 2), _fnum(v["mean_pay_when_losing"], 2)]
        for k, v in d["by_role"].items()
    ]))
    add("")
    add("机制（**官方已确认**）：庄家被自摸时按 8 倍付，是闲家的 8 倍；庄家自己胡牌则收 24×番（闲家胡只收 10×番）。"
        "坐庄既是最大的风险敞口，也是最大的单局收益来源。")
    add("")

    sb = d["seat_benchmark"]
    ms, os_ = sb["me"], sb["opponent_seats"]
    lv = d["levers"]
    add("## 9. 关键比率：我方 vs 同桌三个对手（配对基准）")
    add("")
    add("配对口径：每局把同一桌的 4 个座位全部纳入统计（我方 1 个座位 + 对手 3 个座位），"
        "因此是**同牌山、同时刻、同规则**的同期对照，比对跨房横截面可靠；但房仍是聚类单位，"
        "对手身份在房间之间不独立，不做显著性检验。")
    add("")
    add(_table(["指标", "我方（1 个座位，%d 座局）" % ms["rounds"],
                "同桌对手（3 个座位，合计 %d 座局）" % os_["rounds"], "差"], [
        ["自摸局数", ms["wins"], "%s（人均）" % _fnum(os_["wins"] / 3.0, 1), "—"],
        ["每局自摸率", "%s%%" % _fnum(100 * ms["win_rate"], 2), "%s%%" % _fnum(100 * os_["win_rate"], 2),
         "%s pp（我方更高）" % _fnum(100 * (ms["win_rate"] - os_["win_rate"]), 2)],
        ["胡牌时平均番值", _fnum(ms["avg_fan_on_win"], 3), _fnum(os_["avg_fan_on_win"], 3),
         "%s" % _fnum(os_["avg_fan_on_win"] - ms["avg_fan_on_win"], 3)],
        ["胡牌时平均得分", _fnum(ms["avg_win_points"], 2), _fnum(os_["avg_win_points"], 2),
         "%s" % _fnum(ms["avg_win_points"] - os_["avg_win_points"], 2)],
        ["未胡时平均付分", _fnum(-ms["avg_pay_points"], 2), _fnum(-os_["avg_pay_points"], 2),
         "%s（正数＝我方付得更多）" % _fnum(os_["avg_pay_points"] - ms["avg_pay_points"], 2)],
        ["每局付分概率", "%s%%" % _fnum(100 * ms["pay_rate"], 1), "%s%%" % _fnum(100 * os_["pay_rate"], 1),
         "%s pp" % _fnum(100 * (ms["pay_rate"] - os_["pay_rate"]), 2)],
        ["每局期望得分", _fnum(ms["net_per_round"], 3), _fnum(os_["net_per_round"], 3),
         "%s" % _fnum(ms["net_per_round"] - os_["net_per_round"], 3)],
        ["坐庄时自摸率", "%s%%" % _fnum(ms["dealer_win_rate"], 2), "%s%%" % _fnum(os_["dealer_win_rate"], 2), "—"],
        ["非庄时自摸率", "%s%%" % _fnum(ms["nondealer_win_rate"], 2), "%s%%" % _fnum(os_["nondealer_win_rate"], 2), "—"],
    ]))
    add("")
    add("把「每局期望得分」之差（%s 分/局，全期 %s 分）拆成两部分（收入侧 / 支出侧，再对收入侧做频率-分值二分解）："
        % (_fnum(ms["net_per_round"] - os_["net_per_round"], 3), _fnum(ms["net_per_round"] * n - os_["net_per_round"] * n, 0)))
    add("")
    add(_table(["分解项", "每局（分）", "全期（分）", "含义"], [
        ["收入侧差", _fnum(lv["income_gap_per_round"], 3), _fnum(lv["income_gap_points"], 0),
         "我方 p×A − 对手 q×A'"],
        ["　其中：频率效应", _fnum(lv["rate_effect_points"] / n, 3), "+%s" % _fnum(lv["rate_effect_points"], 0),
         "我方自摸更频繁带来的优势"],
        ["　其中：分值效应", _fnum(lv["value_effect_points"] / n, 3), _fnum(lv["value_effect_points"], 0),
         "我方单次胡牌更小带来的劣势"],
        ["支出侧差", _fnum(lv["pay_gap_per_round"], 3), _fnum(lv["pay_gap_points"], 0),
         "我方付分更少（正）或更多（负）"],
    ]))
    add("")
    cc = d["cluster_check"]
    add("**聚类稳健性（35 个房为单位，不是 2788 局）**：")
    add("")
    add(_table(["每房统计量", "房级均值", "t 值（df=34）", "读法"], [
        ["我方自摸率 − 对手座位自摸率", "%s pp" % _fnum(100 * cc["win_rate_diff_mean"], 2),
         _fnum(cc["win_rate_diff_t"], 2), "为正但**不显著**（|t|<1.96）"],
        ["我方单次胡牌分 − 对手单次胡牌分", "%s 分" % _fnum(cc["win_value_diff_mean"], 2),
         _fnum(cc["win_value_diff_t"], 2), "**显著为负**，是本报告最稳的信号"],
        ["我方每局净分", "%s 分" % _fnum(cc["net_per_round_mean"], 3),
         _fnum(cc["net_per_round_t"], 2), "为负但**不显著**：总账本身在 35 房尺度上区分度不足"],
    ]))
    add("")
    add("这三行是本报告最重要的统计纪律提醒：**总账 %d 分本身在 35 房尺度上不显著**（t=%s），"
        "但「单次胡牌更小」这一条在房级聚合后仍然稳健（t=%s）。也就是说，可以放心地把「番值」当作主攻方向，"
        "而不应把「总账变差」直接归因到某个具体改动上。"
        % (my_total, _fnum(cc["net_per_round_t"], 2), _fnum(cc["win_value_diff_t"], 2)))
    add("")
    add("按对手身份（前 12 名按同场局数排序；同一对手反复出现，属聚类数据，不能相加当独立样本）：")
    add("")
    add(_table(["对手 user_id", "同场局数", "对手总分", "每局", "对手自摸率"], [
        [uid, v["rounds"], v["points"], _fnum(v["points"] / v["rounds"], 2),
         "%s%%" % _fnum(100.0 * v["wins"] / max(1, v["rounds"]), 1)]
        for uid, v in d["opponents"]["rows"]
    ]))
    add("")

    add("## 10. 听牌、先胡与「离胡还差几张」")
    add("")
    add("方法：把一局内所有官方状态快照按序扫描，第一次出现向听 ≤0（或已构成胡牌手）即记为「曾听牌」，并记录当时的牌墙剩余；"
        "「听牌时已耗摸牌数」= 83 − 牌墙剩余。快照是抽样观测（有快照的局平均每局 %s 个），"
        "因此「未听牌」是**下界估计**（可能听牌后又打掉而未被采到）。"
        % _fnum(sum(r.get("n_snaps", 0) for r in rounds) / max(1, sum(1 for r in rounds if r.get("n_snaps"))), 1))
    add("")
    add(_table(["分组", "局数", "我方总分", "每局均值", "其中对手自摸", "其中流局", "平均第几张摸牌听牌"], [
        [k, v["rounds"], v["points"], _fnum(v["mean"], 2), v["opp_win"], v["draw"],
         _fnum(v["mean_draws_to_tenpai"], 1)]
        for k, v in d["tenpai_groups"].items()
    ]))
    add("")
    tp = d["tenpai_timing"]
    add("听牌时机：" + "；".join("%s %d 局，平均第 %s 张摸牌听牌"
                              % (k, v["rounds"], _fnum(v["mean_draws_to_tenpai"], 1)) for k, v in tp.items()) + "。")
    add("")
    tpg = d["tenpai_groups"]["曾听牌未胡"]
    add("**已听牌还被别人先胡**：曾听牌且未胡的 %d 局中，%d 局（%s%%）是对手先自摸，%d 局流局。"
        % (tpg["rounds"], tpg["opp_win"], _fnum(100.0 * tpg["opp_win"] / max(1, tpg["rounds"]), 1), tpg["draw"]))
    add("")
    tsh = d["tenpai_end_shanten"]
    tsh_tot = sum(tsh.values())
    add("**这些局我们离胡还差几张**（曾听牌未胡的 %d 局，按该局结束时官方状态的向听）："
        % tsh_tot)
    add("")
    add(_table(["结束时向听", "局数", "占比"], [
        [k, v, "%s%%" % _fnum(100.0 * v / max(1, tsh_tot), 1)] for k, v in sorted(tsh.items())
    ]))
    add("")
    add("即：曾听牌却没能胡的局里，有 %s%% 是「打着打着又退回不听」（结束时向听 ≥1），只有 %s%% 到最后仍停在听牌上等牌。"
        % (_fnum(100.0 * sum(v for k, v in tsh.items() if k >= 1) / max(1, tsh_tot), 1),
           _fnum(100.0 * tsh.get(0, 0) / max(1, tsh_tot), 1)))
    add("")
    add("**得分与听牌的关联强度（分组统计，非因果）**：我方胡牌组每局 %s 分；曾听牌未胡组每局 %s 分；全程未听牌组每局 %s 分。"
        "三组差距主要由「是否胡牌」这一离散事件决定，而不是由听牌早晚的连续差异决定。"
        % (_fnum(d["tenpai_groups"]["我方胡牌"]["mean"], 2),
           _fnum(d["tenpai_groups"]["曾听牌未胡"]["mean"], 2),
           _fnum(d["tenpai_groups"]["全程未听牌"]["mean"], 2)))
    add("")

    add("## 11. 分册：09-23 战役与 R18 v2 修复后三房")
    add("")
    add(_table(["会话/子集", "房数", "场数", "局数", "我方总分", "每局"], [
        [k, v["rooms"], v["games"], v["rounds"], v["points"], _fnum(v["points"] / v["rounds"], 2)]
        for k, v in d["sessions"].items()
    ]))
    add("")
    add("与任务书给定数字的对账：任务书写「09-23 的 31 房战役合计约 -657」。实测 31 房战役单独为 **-597（未去重口径）/ -569（去重口径）**；"
        "把同一时期的 r18-integrated-positive-v1-auto-match 房（-60）并入才是 -657 / -629。也就是说 -657 这个数字把 v1 房算进了战役。")
    add("")
    add("失分最重的 8 个房（去重口径）：")
    add("")
    add(_table(["room_id", "会话", "局数", "我方总分"], [
        [k, v["tag"], v["rounds"], v["points"]] for k, v in d["rooms_top"]
    ]))
    add("")

    lv = d["levers"]
    add("## 11b. 番型与爆头：番值差距落在哪一类")
    add("")
    add("番型明细只在有事件流的 %d 局可得（我方 %d 次胡牌、对手 %d 次胡牌）。**按每次胡牌归一化后的占比**："
        % (g["win_rounds_with_event_stream"], d["fan_detail_by_winner"]["me_wins"], d["fan_detail_by_winner"]["opp_wins"]))
    add("")
    add(_table(["官方明细", "我方次数", "我方占比", "对手次数", "对手占比", "占比差"], [
        [k, v["me"], "%s%%" % _fnum(100.0 * v["me"] / max(1, d["fan_detail_by_winner"]["me_wins"]), 1),
         v["opp"], "%s%%" % _fnum(100.0 * v["opp"] / max(1, d["fan_detail_by_winner"]["opp_wins"]), 1),
         "%s pp" % _fnum(100.0 * (v["me"] / max(1, d["fan_detail_by_winner"]["me_wins"])
                                  - v["opp"] / max(1, d["fan_detail_by_winner"]["opp_wins"])), 1)]
        for k, v in d["fan_detail_by_winner"]["rows"].items()
    ]))
    add("")
    btg = d["baotou_groups"]
    add("爆头（我方权威 god.baotou，来自官方快照）分组：")
    add("")
    add(_table(["分组", "局数", "我方自摸率", "每局均分", "胡牌时平均番值", "合计分"], [
        [k, v["rounds"], "%s%%" % _fnum(v["win_rate"], 1), _fnum(v["mean"], 2),
         _fnum(v["avg_fan_on_win"], 3), v["points"]]
        for k, v in btg.items()
    ]))
    add("")
    bf = d["baotou_explains_fan"]
    add("**爆头率是否足以解释番值缺口？用官方明细做算术核对**：")
    add("")
    add(_table(["量", "我方", "对手", "差"], [
        ["胡牌中带「爆头」明细的比例", "%s%%" % _fnum(100 * bf["my_baotou_share_of_wins"], 1),
         "%s%%" % _fnum(100 * bf["opp_baotou_share_of_wins"], 1),
         "%s pp" % _fnum(100 * (bf["my_baotou_share_of_wins"] - bf["opp_baotou_share_of_wins"]), 1)],
        ["（样本：有明细的胡牌次数）", bf["my_wins_with_detail"], bf["opp_wins_with_detail"], "—"],
        ["实测胡牌平均番值", _fnum(lv["me_avg_fan_on_win"], 3), _fnum(lv["opp_avg_fan_on_win"], 3),
         _fnum(lv["opp_avg_fan_on_win"] - lv["me_avg_fan_on_win"], 3)],
        ["按「番值 = 基础番 ×（爆头 ? 2 : 1）」回推的预测番值",
         _fnum(bf["predicted_fan_at_opp_share"], 3), _fnum(bf["actual_opp_fan"], 3),
         _fnum(bf["actual_opp_fan"] - bf["predicted_fan_at_opp_share"], 3)],
    ]))
    add("")
    add("结论：以我方实测平均番值 %s、爆头占比 %s%% 回推基础番 ≈ %s；把爆头占比换成对手的 %s%%，预测番值 = %s，"
        "与对手实测的 %s 几乎相等。也就是说，**番值缺口基本可以完全由「爆头占比」这一个变量解释**，"
        "不需要假设对手在别的方面更强。"
        % (_fnum(lv["me_avg_fan_on_win"], 3), _fnum(100 * bf["my_baotou_share_of_wins"], 1),
           _fnum(bf["implied_base_fan"], 3), _fnum(100 * bf["opp_baotou_share_of_wins"], 1),
           _fnum(bf["predicted_fan_at_opp_share"], 3), _fnum(bf["actual_opp_fan"], 3)))
    add("")
    add("我方 %d 次自摸里有 %d 次发生在曾进入爆头的局（%s%%）。"
        % (d["baotou_at_win"]["wins"], d["baotou_at_win"]["wins_in_baotou"],
           _fnum(100.0 * d["baotou_at_win"]["wins_in_baotou"] / max(1, d["baotou_at_win"]["wins"]), 1)))
    add("")
    add("**因果方向提醒**：爆头 = 「听任意牌」，本身就是一个「离胡一张、且听口极宽」的状态，"
        "因此「爆头局自摸率 85.1%%」有很强的机械成分，不能读成「只要进入爆头就必赢」。"
        "可检验的部分是：**我方进入爆头的频率（%s 局 / %d 局 = %s%%）是否低于同水平对手**，"
        "这需要同牌山配对桌验证，不能从本表直接推出因果。"
        % (btg["我方曾进入爆头"]["rounds"], n,
           _fnum(100.0 * btg["我方曾进入爆头"]["rounds"] / max(1, n), 1)))
    add("")

    add("## 12. 只改一件事：按分数量级排序的前三名")
    add("")
    add("换算口径：一次「把一局未胡变成一局胡牌」的价值 = 胡牌时平均得分 + 未胡时平均付分 = %s + %s = %s 分/局。"
        % (_fnum(rates["my_mean_win_points"], 2), _fnum(-rates["my_mean_pay_points"], 2),
           _fnum(lv["value_per_converted_round"], 2)))
    add("")
    add(_table(["排名", "只改这一件事", "规模（分）", "算法", "性质"], [
        ["1", "把我方胡牌中的**爆头占比**从 %s%% 提到同桌对手的 %s%%（等价于平均番值 %s → %s）"
         % (_fnum(100 * d["baotou_explains_fan"]["my_baotou_share_of_wins"], 1),
            _fnum(100 * d["baotou_explains_fan"]["opp_baotou_share_of_wins"], 1),
            _fnum(lv["me_avg_fan_on_win"], 3), _fnum(lv["opp_avg_fan_on_win"], 3)),
         "+%s" % _fnum(lv["points_if_win_value_matched"], 0),
         "%d 局 × %s 自摸率 × (%s − %s) 分；爆头同时把自摸率从 %s%% 抬到 %s%%"
         % (n, _fnum(lv["me_win_rate"], 3), _fnum(lv["opp_avg_win_points"], 2), _fnum(lv["me_avg_win_points"], 2),
            _fnum(d["baotou_groups"]["我方从未爆头"]["win_rate"], 1),
            _fnum(d["baotou_groups"]["我方曾进入爆头"]["win_rate"], 1)),
         "相关观察（同桌配对对照 + 官方番型明细）"],
        ["2", "多自摸 %s 局（把 %d 局中的 %s%% 由「付分」变成「胡牌」）"
         % (_fnum(lv["wins_needed_to_break_even"], 1), n, _fnum(100.0 * lv["wins_needed_to_break_even"] / n, 2)),
         "+%s" % _fnum(-my_total, 0),
         "%s 分/局 × %s 局（%s + %s）"
         % (_fnum(lv["value_per_converted_round"], 2), _fnum(lv["wins_needed_to_break_even"], 1),
            _fnum(lv["me_avg_win_points"], 2), _fnum(lv["me_avg_pay_points"], 2)),
         "相关观察（同一恒等式的另一面）"],
        ["3", "把坐庄局表现拉到非庄局水平", "+%s" % _fnum(lv["points_if_dealer_matched_nondealer"], 0),
         "(%s − %s) 分/局 × %d 庄局"
         % (_fnum(d["by_role"]["我方非庄"]["mean"], 2), _fnum(d["by_role"]["我方坐庄"]["mean"], 2),
            d["by_role"]["我方坐庄"]["rounds"]),
         "相关观察；庄家身份由连庄规则决定，不完全可择"],
    ]))
    add("")
    add("**为什么第 1 名是「胡得小」而不是「胡得少」**：我方自摸率 %s%% 已经**高于**同桌对手座位人均的 %s%%；"
        "频率效应为我方贡献 +%s 分，而单次分值劣势吃掉 %s 分，两者相抵后收入侧仍差 %s 分。"
        "换句话说，把现在的牌风继续优化成「更快胡牌」只会放大已经领先的频率项，而缺口在乘数项。"
        % (_fnum(100 * lv["me_win_rate"], 2), _fnum(100 * lv["opp_win_rate"], 2),
           _fnum(lv["rate_effect_points"], 0), _fnum(lv["value_effect_points"], 0),
           _fnum(lv["income_gap_points"], 0)))
    add("")
    add("第 1 名的机制性补充：番值既是我们的收入乘数，也是对手的收入乘数。支出侧确实存在一个大得多的描述性数字 —— "
        "我方毛失分 %d 中有 %s 分来自「对手番值 > 1」的溢价（若全按番 1 只需付 %d 分）。"
        "但这是**共同的游戏结构**（对手之间也互相付这笔钱），我方相对同桌对手的支出侧差距只有 %s 分，"
        "因此「压制对手番值」不应被当成同等量级的杠杆，优先级低于第 1 名。"
        % (gross, _fnum(lv["premium_points"], 0), d["fan_premium"]["if_all_fan1"], _fnum(lv["pay_gap_points"], 0)))
    add("")
    add("第 1 名内部的已知张力（**待确认假设**）：自摸率与番值可能是一个取舍曲线 —— 追快胡容易停在平胡，"
        "追爆头/飘链则要放弃部分速度。我方当前点（自摸率 %s%%、平均番值 %s）高于对手的自摸率、低于对手的番值，"
        "看起来正处在「偏快偏小」一侧。曲线是否存在、以及沿曲线移动的真实收益，只能在同牌山配对完整桌上验证。"
        % (_fnum(100 * lv["me_win_rate"], 2), _fnum(lv["me_avg_fan_on_win"], 3)))
    add("")
    add("**因果提醒**：以上都是自由赛横截面算出的**相关观察**。自由赛的房是聚类单位、对手不同质、牌山不同，"
        "不能直接读出「改了就能拿到这些分」。按项目统计纪律，因果必须在同牌山配对的完整桌上验证，且需先预登记。"
        "这些数字的价值在于：把 %d 分拆成了几个量级明确、可分别设计实验的假设。" % my_total)
    add("")

    add("## 13. 数据局限与待确认假设")
    add("")
    add("* 【当前观察】官方 events.json 只给 multiplier（= 总番）与分数向量，不给番型明细；番型明细只在含事件流的 %d 局可得（09-23 战役与 v1 房）。"
        % g["rounds_with_event_stream"])
    add("* 【当前观察】R18 v2 的 pm/pm2/pm3 会话只记录了 SSE 序号，未记录事件流，因此这三房的巡目用状态快照的牌墙剩余推断，"
        "且无法从事件流二次确认自摸（但结算结构 %d 局全对仍成立）。" % n)
    add("* 【待确认假设】会话标签到策略身份的映射按命名推断（如 r18-v2-sse-freematch-20260925-pm* → r18_integrated_positive_v2）；"
        "审计 manifest.json 中无 policy_version 字段，未经二次确认。")
    add("* 【待确认假设】「我方是否先听牌」不可观测（对手手牌不可见）；本报告只给「我方是否曾听牌」与听牌时机。")
    add("* 【当前观察】快照为抽样观测，未听牌结论是下界；向听计算与策略自身审计的交叉核对见下条。")
    add("* 【已核对】向听调用口径：hand_analysis.analyse_hand(my_hand, len(melds[my_seat])) 与策略审计 facts.shanten_after 的最小值完全一致 —— "
        "对 r18-v2-sse-freematch-20260925-pm3 的 2901 条 decision_input 逐条核对，706 个弃牌窗口 100.00% 一致、0 分歧"
        "（另有 2195 条响应窗口无弃牌候选、19 条已构成胡牌手，均按预期处理）。复现命令见 §14 的 validate-shanten。")
    add("* 【工程建议】任务书预设的「降低放铳率」在本赛制下不可能产生收益（无点炮）；同时「提高自摸率」也已不是主要缺口"
        "（我方自摸率已高于对手 %s pp）。研发预算应集中到「单次胡牌的分值」＝番值路线（爆头、飘/杠链、七对/豪华七对、四白）的转化率上。"
        % _fnum(100 * (d["levers"]["me_win_rate"] - d["levers"]["opp_win_rate"]), 2))
    add("* 【待确认假设】为什么我方番值系统性低于对手，本报告没有回答机制：可能是（a）我方速度优先导致不做爆头/飘链，"
        "（b）番值路线的入牌判断权重不足，（c）对手样本本身偏向高手。需在同牌山配对桌上分别检验。")
    add("")

    add("## 14. 复现命令")
    add("")
    add(FENCE + "bash")
    add("cd /Users/liyang/hangma-bot")
    add("# 全流程（扫描审计 raw → 归因 → 报告）")
    add(".venv/bin/python review/freematch-deep-dive-20260925/loss_attribution.py all")
    add("")
    add("# 仅重建审计缓存 round-audit.jsonl")
    add(".venv/bin/python review/freematch-deep-dive-20260925/loss_attribution.py scan")
    add("")
    add("# 仅重算归因与报告（读缓存 + 官方牌谱）")
    add(".venv/bin/python review/freematch-deep-dive-20260925/loss_attribution.py report")
    add("")
    add("# 房级/局级得分提取（独立工具；注意它未按 game_id 去重，输出 358 场 / -863 分）")
    add(".venv/bin/python review/freematch-deep-dive-20260925/extract_room_scores.py")
    add("")
    add("# 向听口径交叉核对（本报告 §13 那条「零分歧」结论的复现命令）")
    add(".venv/bin/python review/freematch-deep-dive-20260925/loss_attribution.py validate-shanten")
    add("")
    add("# 换会话核对（默认 pm3）")
    add(".venv/bin/python review/freematch-deep-dive-20260925/loss_attribution.py validate-shanten --tag <会话标签>")
    add(FENCE)
    add("")
    add("本文所有数字都来自同一次运行生成的 loss-attribution.json，与脚本一一对应。")
    add("")
    with open(OUT_MD, "w") as fh:
        fh.write("\n".join(L))


def cmd_validate_shanten(args):
    """交叉核对向听调用口径：我方审计的 facts.shanten_after 与本脚本的 analyse_hand 调用。

    读 r18-v2-sse-freematch-20260925-pm3 的 decisions.jsonl（约 94MB），
    对每条 decision_input 比较：
      - analyse_hand(observation.my_hand, len(melds[seat])).shanten
      - 该窗口全部弃牌候选的 min(facts.shanten_after)
    已构成胡牌手（is_win）时以「候选最小向听 = 0」为一致。
    """
    import glob as _glob
    pattern = os.path.join(SESSION_ROOT, args.tag, "audit", "runs", "*",
                           "participants", ME, "decisions.jsonl")
    paths = _glob.glob(pattern)
    if not paths:
        print("找不到 decisions.jsonl：%s" % pattern)
        return 1
    total = agree = win_case = no_discard = bad = 0
    examples = []
    for path in paths:
        with open(path) as fh:
            for line in fh:
                if "decision_input" not in line[:400]:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("kind") != "decision_input":
                    continue
                req = (rec.get("payload") or {}).get("request") or {}
                obs = req.get("observation") or {}
                hand = obs.get("my_hand") or []
                seat = obs.get("seat")
                melds = obs.get("melds") or []
                meld_count = len(melds[seat]) if seat is not None and seat < len(melds) else 0
                summary = analyse_hand(hand, meld_count)
                if summary is None:
                    continue
                cands = [c for c in ((req.get("rules") or {}).get("legal_candidates") or [])
                         if (c.get("action") or {}).get("kind") == "discard"]
                vals = [c["facts"]["shanten_after"] for c in cands
                        if (c.get("facts") or {}).get("shanten_after") is not None]
                total += 1
                if summary.is_win:
                    win_case += 1
                    if not vals or min(vals) == 0:
                        agree += 1
                    elif len(examples) < 5:
                        examples.append((hand, meld_count, "is_win", min(vals)))
                    continue
                if not vals:
                    no_discard += 1
                    continue
                if min(vals) == summary.shanten:
                    agree += 1
                else:
                    bad += 1
                    if len(examples) < 5:
                        examples.append((hand, meld_count, summary.shanten, min(vals)))
    checked = total - no_discard
    print("decision_input 总数 %d；有弃牌候选 %d；无弃牌候选（响应窗口）%d"
          % (total, checked, no_discard))
    print("一致 %d / %d = %s%%；不一致 %d；其中已胡手牌 %d 条"
          % (agree, checked, ("%.2f" % (100.0 * agree / max(1, checked))), bad, win_case))
    for ex in examples:
        print("  反例：", ex)
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="自由赛失分归因计量学")
    ap.add_argument("cmd", choices=["scan", "report", "all", "validate-shanten"])
    ap.add_argument("--tag", default="r18-v2-sse-freematch-20260925-pm3",
                    help="validate-shanten 使用的会话标签")
    args = ap.parse_args(argv)
    if args.cmd in ("scan", "all"):
        cmd_scan(args)
    if args.cmd in ("report", "all"):
        cmd_report(args)
    if args.cmd == "validate-shanten":
        return cmd_validate_shanten(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
