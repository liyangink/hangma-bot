#!/usr/bin/env python3
"""榜上强手对手画像：把 35 房 358 场的官方牌谱与周榜/日榜/总榜快照按 user_id 联表。

只读分析，不发网络请求，不跑模拟。事实来源：
- artifacts/sessions/*/official/dl-*/events.json（官方权威结算 + 逐动作事件流）
- datasets/leaderboard/snapshots/<ts>/*.json（门户排行榜快照，标签时点以上午快照为准）

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/ranked_opponent_profile.py \
        [--snapshot datasets/leaderboard/snapshots/20260925T100009Z] \
        [--out review/freematch-deep-dive-20260925/ranked-opponent-profile.json] \
        [--pretty]

【规则事实】src/hangma_bot/hangma/RULES_EVIDENCE.md:38「只能自摸，不允许点炮；
禁止抢杠胡」——本规则集不存在点炮/放铳，胡候选只在本人摸牌窗口产生。
因此「自摸率」（恒 100%）、「点胡率」「放铳率」（概念不存在）不可区分，
本脚本不计算这三项，改以「胡牌率 / 平均胡牌分 / 大牌率 / 胡牌巡目」代替。
（同结论见 doc/implementation/evaluation-datamart-design.md:342 明确禁止统计自摸率。）
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
import datetime
import glob
import json
import os
import statistics

ME = "u_13495c3d79c8"
WEALTH_TILE = "白"  # 财神（白板）；规则来源 hangma/internal_types.is_wealth


def utc(sec):
    if not isinstance(sec, int):
        return None
    return datetime.datetime.fromtimestamp(sec, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


BOARDS = [
    ("leaderboard-week.json", "week", False),
    ("leaderboard-week.json", "week-prev", True),
    ("leaderboard-today.json", "today", False),
    ("leaderboard-today.json", "today-prev", True),
    ("leaderboard-all.json", "all", False),
    ("leaderboard-best-game.json", "best-game", False),
    ("leaderboard-huge-win.json", "huge-win", False),
]


def load_boards(snapshot_dir):
    boards = {}
    for fname, label, use_prev in BOARDS:
        path = os.path.join(snapshot_dir, fname)
        if not os.path.exists(path):
            continue
        doc = json.load(open(path))
        if use_prev:
            block = doc.get("prev") or {}
            rows = block.get("top") or []
            note = block.get("label") or label
            since, until = block.get("from"), block.get("to")
        else:
            rows, note = doc.get("top") or [], label
            since, until = doc.get("from"), None
        ranks = {}
        for row in rows:
            uid = row.get("user_id")
            if uid:
                ranks[uid] = {"rank": row.get("rank"), "name": row.get("name"),
                              "score": row.get("score"), "rooms": row.get("rooms")}
        boards[label] = {"file": fname, "note": note, "as_of": doc.get("as_of"),
                         "from": since, "to": until, "n_rows": len(rows),
                         "ranks": ranks, "me": doc.get("me")}
    return boards


# --------------------------------------------------------------- 牌谱解析

def iter_games(root):
    best = {}
    for path in sorted(glob.glob(os.path.join(root, "*", "official", "dl-*", "events.json"))):
        try:
            payload = json.load(open(path))
        except (OSError, ValueError):
            continue
        gid = payload.get("game_id")
        if not gid:
            continue
        tag = path.split(os.sep)[2]
        weight = sum(len(b.get("events") or []) for b in payload.get("blocks") or [])
        prev = best.get(gid)
        if prev is None or weight > prev[0]:
            best[gid] = (weight, payload, tag, path)
    for gid in sorted(best):
        _w, payload, tag, path = best[gid]
        yield gid, payload, tag, path


def parse_game(payload):
    """返回 per-round 事实；rounds[] 与 round_ended 事件取并集（12 场缺一条摘要）。"""
    seats = payload.get("seats") or []
    uids = [s.get("user_id") for s in seats]
    names = [s.get("name") for s in seats]
    if len(uids) != 4 or ME not in uids:
        return None

    summary = {rd.get("round_no"): rd for rd in payload.get("rounds") or []}
    ev = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    win_ctx, times = {}, []
    last_draw = {}
    # 财神（白板）守恒台账：起始手牌 → 摸到 → 打出，用于还原「胡牌时手上是否留财神」。
    white = {}

    def _white_slot(rno):
        if rno not in white:
            white[rno] = {"start": {i: None for i in range(4)},
                          "drawn": {i: 0 for i in range(4)},
                          "disc": {i: 0 for i in range(4)},
                          "drawn_then_disc": {i: 0 for i in range(4)}}
        return white[rno]

    for block in payload.get("blocks") or []:
        rno = block.get("round_no")
        slot = _white_slot(rno)
        starts = block.get("start_hands") or []
        if any(isinstance(h, list) and h for h in starts):
            for i in range(4):
                if slot["start"][i] is None and isinstance(starts[i], list):
                    slot["start"][i] = sum(1 for t in starts[i] if t == WEALTH_TILE)
        for e in block.get("events") or []:
            ts = e.get("ts")
            if isinstance(ts, int):
                times.append(ts)
            kind, seat = e.get("type"), e.get("seat")
            data = e.get("data") or {}
            if isinstance(seat, int) and 0 <= seat < 4:
                ev[rno][seat][kind] += 1
                if kind == "tile_drawn" and e.get("tile") == WEALTH_TILE:
                    slot["drawn"][seat] += 1
                    ev[rno][seat]["drew_wealth"] += 1
                if kind == "tile_discarded":
                    if last_draw.get((rno, seat)) == e.get("tile"):
                        ev[rno][seat]["discard_just_drawn"] += 1  # 摸切
                    if e.get("tile") == WEALTH_TILE:
                        ev[rno][seat]["discard_wealth"] += 1
                        slot["disc"][seat] += 1
                        if last_draw.get((rno, seat)) == WEALTH_TILE:
                            slot["drawn_then_disc"][seat] += 1
                    if data.get("catch_play"):
                        ev[rno][seat]["catch_play_discard"] += 1
                if kind == "timeout":
                    w = data.get("window")
                    ev[rno][seat]["timeout_" + str(w) if w else "timeout_other"] += 1
            if kind == "tile_drawn" and isinstance(seat, int):
                last_draw[(rno, seat)] = e.get("tile")
            if kind == "round_ended":
                held = {}
                for i in range(4):
                    st = slot["start"][i]
                    held[i] = None if st is None else st + slot["drawn"][i] - slot["disc"][i]
                win_ctx[rno] = {
                    "winner": seat if isinstance(seat, int) else None,
                    "draw": bool(data.get("draw")),
                    "fan": data.get("fan"),
                    "detail": tuple(data.get("detail") or ()),
                    "discards_before": {s: ev[rno][s]["tile_discarded"] for s in range(4)},
                    "white_held": held,
                    "seq_done": True,
                }
            if kind == "game_ended":
                win_ctx.setdefault(-1, {})["final_scores"] = tuple(data.get("final_scores") or ())

    # 出牌/摸牌总数（用于窗口分母）
    totals = {s: dict(ev[r][s]) for r in ev for s in range(4)}
    per_round_discards = {r: {s: ev[r][s]["tile_discarded"] for s in range(4)} for r in ev}

    rounds = []
    all_rno = sorted(set(list(summary) + [k for k in ev if isinstance(k, int)]))
    for rno in all_rno:
        rd, ctx = summary.get(rno, {}), win_ctx.get(rno, {})
        scores = tuple(rd.get("scores") or ctx.get("scores") or ())
        if len(scores) != 4:
            continue
        winner = rd.get("winner", ctx.get("winner"))
        is_draw = bool(rd.get("is_draw", ctx.get("draw", False)))
        fan = rd.get("multiplier")
        if fan is None:
            fan = ctx.get("fan")
        rounds.append({
            "round_no": rno,
            "dealer": rd.get("dealer"),
            "winner": winner,
            "is_draw": is_draw,
            "fan": fan if fan is not None else 0,
            "detail": tuple(ctx.get("detail") or ()),
            "white_held": ctx.get("white_held") or {},
            "scores": scores,
            "discards_before": ctx.get("discards_before") or {},
            "seat_events": {s: dict(ev[rno][s]) for s in range(4)},
            "summary_present": rno in summary,
        })
    return {"uids": uids, "names": names, "rounds": rounds, "times": times,
            "final": (win_ctx.get(-1) or {}).get("final_scores"),
            "per_round_discards": per_round_discards}


# --------------------------------------------------------------- 统计容器

def blank():
    return collections.Counter()


def accumulate(d, i, rd, seat_events):
    scores, winner, is_draw, fan = rd["scores"], rd["winner"], rd["is_draw"], rd["fan"] or 0
    d["rounds"] += 1
    d["net"] += scores[i]
    if is_draw:
        d["draws"] += 1
    elif winner == i:
        d["wins"] += 1
        d["win_points"] += scores[i]
        d["fan_hist_" + str(fan)] += 1
        d["fan_sum"] += fan
        if fan >= 4:
            d["big_wins"] += 1
        if fan >= 2:
            d["mid_wins"] += 1
        det = rd["detail"]
        if "爆头" in det:
            d["wins_baotou"] += 1
        if any(x.startswith(("杠开", "连杠", "财飘", "双财飘", "三财飘", "连飘", "杠飘链")) for x in det):
            d["wins_chain"] += 1
        if any("七对" in x for x in det):
            d["wins_chiitoi"] += 1
        if rd["dealer"] == i:
            d["dealer_wins"] += 1
        wh = rd.get("white_held", {}).get(i)
        if wh is not None:
            d["wins_white_known"] += 1
            if wh > 0:
                d["wins_held_white"] += 1
                if "爆头" in det:
                    d["wins_held_white_baotou"] += 1
        own = rd["discards_before"].get(i)
        if own is not None:
            d["win_turn_sum"] += own + 1
            d["win_turn_n"] += 1
            d["win_turn_le6"] += 1 if own + 1 <= 6 else 0
    else:
        d["loss_points"] += scores[i]
        if rd["dealer"] == i:
            d["dealer_losses"] += 1
    evs = seat_events.get(i, {})
    d["chi"] += evs.get("chi", 0)
    d["peng"] += evs.get("peng", 0)
    d["gang"] += evs.get("gang", 0)
    d["own_discards"] += evs.get("tile_discarded", 0)
    d["own_draws"] += evs.get("tile_drawn", 0)
    d["discard_wealth"] += evs.get("discard_wealth", 0)
    d["drew_wealth"] += evs.get("drew_wealth", 0)
    d["discard_just_drawn"] += evs.get("discard_just_drawn", 0)
    d["catch_play_discard"] += evs.get("catch_play_discard", 0)
    d["timeout_peng"] += evs.get("timeout_peng", 0)
    d["timeout_chi"] += evs.get("timeout_chi", 0)
    d["timeout_other"] += evs.get("timeout_other", 0)
    d["pass"] += evs.get("pass", 0)
    return d


def finalize(d):
    r = d["rounds"] or 1
    w = d["wins"] or 0
    losses = d["rounds"] - w - d["draws"]
    resp = d["timeout_peng"] + d["timeout_chi"] + d["pass"]
    return {
        "rounds": d["rounds"],
        "wins": w,
        "win_rate": round(w / r, 4),
        "draws": d["draws"],
        "draw_rate": round(d["draws"] / r, 4),
        "net_per_round": round(d["net"] / r, 3),
        "net_total": d["net"],
        "avg_win_points": round(d["win_points"] / w, 3) if w else None,
        "avg_loss_points": round(d["loss_points"] / losses, 3) if losses else None,
        "avg_win_fan": round(d["fan_sum"] / w, 3) if w else None,
        "big_win_rate": round(d["big_wins"] / w, 4) if w else None,
        "mid_win_rate": round(d["mid_wins"] / w, 4) if w else None,
        "baotou_win_rate": round(d["wins_baotou"] / w, 4) if w else None,
        "chain_win_rate": round(d["wins_chain"] / w, 4) if w else None,
        "chiitoi_win_rate": round(d["wins_chiitoi"] / w, 4) if w else None,
        "dealer_win_share": round(d["dealer_wins"] / w, 4) if w else None,
        "fan_hist": {k.split("_")[-1]: v for k, v in sorted(d.items())
                     if k.startswith("fan_hist_") and v},
        "chi_per_round": round(d["chi"] / r, 3),
        "peng_per_round": round(d["peng"] / r, 3),
        "gang_per_round": round(d["gang"] / r, 3),
        "melds_per_round": round((d["chi"] + d["peng"] + d["gang"]) / r, 3),
        "tsumogiri_rate": round(d["discard_just_drawn"] / d["own_discards"], 4) if d["own_discards"] else None,
        "discards_per_round": round(d["own_discards"] / r, 3),
        "draws_per_round": round(d["own_draws"] / r, 3),
        "white_draw_per_round": round(d["drew_wealth"] / r, 4),
        "white_discard_per_round": round(d["discard_wealth"] / r, 4),
        "white_discard_given_draw": round(d["discard_wealth"] / d["drew_wealth"], 4) if d["drew_wealth"] else None,
        "win_held_white_rate": round(d["wins_held_white"] / d["wins_white_known"], 4) if d["wins_white_known"] else None,
        "win_held_white_baotou_rate": round(d["wins_held_white_baotou"] / d["wins_held_white"], 4) if d["wins_held_white"] else None,
        "catch_play_discard_per_round": round(d["catch_play_discard"] / r, 4),
        "response_timeout_per_round": round((d["timeout_peng"] + d["timeout_chi"]) / r, 3),
        "response_timeout_share": round((d["timeout_peng"] + d["timeout_chi"]) / resp, 4) if resp else None,
        "win_turn_avg": round(d["win_turn_sum"] / d["win_turn_n"], 3) if d["win_turn_n"] else None,
        "win_turn_le6_rate": round(d["win_turn_le6"] / d["win_turn_n"], 4) if d["win_turn_n"] else None,
        "win_turn_n": d["win_turn_n"],
    }


def opponent_profiles(per_uid, games_out, rooms, boards):
    """按对手 user_id 汇总其在我们 350 场里的全部局级行为，附带榜位。"""
    out = {}
    for uid, st in per_uid.items():
        if uid == ME:
            continue
        games = [g for g in games_out if any(s["user_id"] == uid for s in g["seats"])]
        rooms_here = sorted({g["room_id"] for g in games})
        ranks = {label: (boards[label]["ranks"].get(uid) or {}).get("rank")
                 for label in boards if uid in boards[label]["ranks"]}
        out[uid] = dict(finalize(st), name=st["name"], games=len(games), rooms=rooms_here,
                        ranks=ranks, ranked=bool(ranks))
    return out


# --------------------------------------------------------------- 主流程

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="datasets/leaderboard/snapshots/20260925T100009Z")
    ap.add_argument("--alt-snapshot", default=None, help="可选：按房时点选用的更早快照目录前缀")
    ap.add_argument("--root", default="artifacts/sessions")
    ap.add_argument("--out", default=None)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args(argv)

    boards = load_boards(args.snapshot)
    week = boards.get("week", {}).get("ranks", {})
    week_prev = boards.get("week-prev", {}).get("ranks", {})
    labels = list(boards)
    sets = {}
    for label in labels:
        order = list(boards[label]["ranks"])
        sets[label] = {"top10": set(order[:10]), "top32": set(order)}
    week32 = sets["week"]["top32"] if "week" in sets else set()
    week_prev32 = sets["week-prev"]["top32"] if "week-prev" in sets else set()

    groups = {"me": blank(), "ranked": blank(), "other": blank()}
    groups_week = {"me": blank(), "ranked": blank(), "other": blank()}
    groups_wp = {"me": blank(), "ranked": blank(), "other": blank()}

    per_uid = {}
    games_out, rooms = [], collections.defaultdict(lambda: {"games": [], "opp": {}})

    for gid, payload, tag, path in iter_games(args.root):
        parsed = parse_game(payload)
        if parsed is None or not parsed["rounds"]:
            continue
        uids, names = parsed["uids"], parsed["names"]
        rid = payload.get("room_id")

        seat_rows = []
        for i, uid in enumerate(uids):
            tags = []
            if uid != ME:
                for label in labels:
                    if uid in sets[label]["top32"]:
                        tags.append(label)
            grp = "me" if uid == ME else ("ranked" if tags else "other")
            seat_rows.append({
                "seat": i, "user_id": uid, "name": names[i], "group": grp, "tags": tags,
                "ranks": {label: (boards[label]["ranks"].get(uid) or {}).get("rank")
                          for label in labels if uid in boards[label]["ranks"]},
            })
            if uid != ME:
                rooms[rid]["opp"].setdefault(uid, seat_rows[-1])

        my_seat = uids.index(ME)
        game_rounds = []
        for rd in parsed["rounds"]:
            for i, uid in enumerate(uids):
                st = per_uid.setdefault(uid, blank())
                st["name"] = names[i]
                accumulate(st, i, rd, rd["seat_events"])
                accumulate(groups["me" if uid == ME else seat_rows[i]["group"]], i, rd, rd["seat_events"])
                accumulate(groups_week["me" if uid == ME else ("ranked" if uid in week32 else "other")],
                           i, rd, rd["seat_events"])
                accumulate(groups_wp["me" if uid == ME else ("ranked" if uid in week_prev32 else "other")],
                           i, rd, rd["seat_events"])
            w = rd["winner"]
            wev = rd["seat_events"].get(w, {}) if isinstance(w, int) and 0 <= w < 4 else {}
            game_rounds.append({
                "round_no": rd["round_no"], "dealer": rd["dealer"], "winner": w,
                "winner_uid": uids[w] if isinstance(w, int) and 0 <= w < 4 else None,
                "winner_group": seat_rows[w]["group"] if isinstance(w, int) and 0 <= w < 4 else None,
                "is_draw": rd["is_draw"], "fan": rd["fan"], "scores": list(rd["scores"]),
                "detail": list(rd["detail"]),
                "winner_melds": wev.get("chi", 0) + wev.get("peng", 0) + wev.get("gang", 0),
                "winner_chi": wev.get("chi", 0), "winner_peng": wev.get("peng", 0),
                "winner_gang": wev.get("gang", 0),
                "winner_white_held": rd.get("white_held", {}).get(w),
                "winner_win_turn": (rd["discards_before"].get(w) or 0) + 1
                                    if isinstance(w, int) and 0 <= w < 4 and rd["discards_before"] else None,
                "summary_present": rd["summary_present"],
            })

        totals = [sum(r["scores"][i] for r in game_rounds) for i in range(4)]
        order = sorted(range(4), key=lambda i: -totals[i])
        my_total = totals[my_seat]
        ranked_here = [s for s in seat_rows if s["group"] == "ranked"]
        games_out.append({
            "game_id": gid, "room_id": rid, "session_tag": tag,
            "t_start": utc(min(parsed["times"])) if parsed["times"] else None,
            "t_end": utc(max(parsed["times"])) if parsed["times"] else None,
            "seats": seat_rows, "my_seat": my_seat, "my_total": my_total,
            "my_rank": order.index(my_seat) + 1, "gap_to_top": max(totals) - my_total,
            "n_ranked_opponents": len(ranked_here),
            "ranked_opponents": [{"user_id": s["user_id"], "name": s["name"],
                                  "week_rank": s["ranks"].get("week"),
                                  "week_prev_rank": s["ranks"].get("week-prev"),
                                  "tags": s["tags"]} for s in ranked_here],
            "rounds": game_rounds,
        })
        rooms[rid]["games"].append(gid)

    rooms_out = []
    for rid, info in sorted(rooms.items()):
        gs = [g for g in games_out if g["room_id"] == rid]
        opp = info["opp"]
        ranks = [s["ranks"].get("week") for s in opp.values() if s["ranks"].get("week")]
        ranks += [s["ranks"].get("week-prev") for s in opp.values()
                  if s["ranks"].get("week-prev") and not s["ranks"].get("week")]
        n = len(gs)
        rooms_out.append({
            "room_id": rid, "session_tag": gs[0]["session_tag"],
            "t_start": min(g["t_start"] for g in gs), "t_end": max(g["t_end"] for g in gs),
            "games": n,
            "my_total": sum(g["my_total"] for g in gs),
            "my_per_game": round(sum(g["my_total"] for g in gs) / n, 2),
            "my_rank1": sum(1 for g in gs if g["my_rank"] == 1),
            "my_rank4": sum(1 for g in gs if g["my_rank"] == 4),
            "mean_gap_to_top": round(sum(g["gap_to_top"] for g in gs) / n, 2),
            "n_ranked_opponents": sum(1 for s in opp.values() if s["group"] == "ranked"),
            "best_opp_rank": min(ranks) if ranks else None,
            "mean_opp_rank": round(statistics.mean(ranks), 1) if ranks else None,
            "ranked_opponents": [{"user_id": u, "name": s["name"], "ranks": s["ranks"]}
                                 for u, s in sorted(opp.items()) if s["group"] == "ranked"],
            "all_opponents": [{"user_id": u, "name": s["name"], "group": s["group"],
                               "ranks": s["ranks"]} for u, s in sorted(opp.items())],
        })

    doc = {
        "generated_from": {
            "snapshot_dir": args.snapshot,
            "boards": {k: {"note": v["note"], "as_of": v["as_of"], "as_of_utc": utc(v["as_of"]),
                           "rows": v["n_rows"], "me": v["me"]} for k, v in boards.items()},
            "sessions_root": args.root,
        },
        "rules_note": ("本规则集只能自摸、不允许点炮、禁止抢杠胡"
                       "（src/hangma_bot/hangma/RULES_EVIDENCE.md:38）；"
                       "自摸率恒 100%，点胡率/放铳率不可观测，故不计算。"),
        "groups_snapshot_union": {k: finalize(v) for k, v in groups.items()},
        "groups_week_top32": {k: finalize(v) for k, v in groups_week.items()},
        "groups_week_prev_top32": {k: finalize(v) for k, v in groups_wp.items()},
        "per_user": {
            u: dict(finalize(v), name=v["name"],
                     week_rank=(boards.get("week", {}).get("ranks", {}).get(u) or {}).get("rank"),
                     week_prev_rank=(boards.get("week-prev", {}).get("ranks", {}).get(u) or {}).get("rank"))
            for u, v in per_uid.items()},
        "opponent_profiles": opponent_profiles(per_uid, games_out, rooms, boards),
        "rooms": rooms_out,
        "games": games_out,
    }
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)

    print("房", len(rooms_out), "场", len(games_out),
          "局", sum(len(g["rounds"]) for g in games_out))
    for name, g in (("联表分组(union)", groups), ("本周榜前32", groups_week), ("上周榜前32", groups_wp)):
        print("--", name)
        for k in ("me", "ranked", "other"):
            f = finalize(g[k])
            print("   ", k, json.dumps({x: f[x] for x in
                  ("rounds", "wins", "win_rate", "net_per_round", "avg_win_points",
                   "avg_loss_points", "avg_win_fan", "big_win_rate", "baotou_win_rate",
                   "dealer_win_share", "melds_per_round", "white_discard_per_round",
                   "win_turn_avg", "response_timeout_share")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
