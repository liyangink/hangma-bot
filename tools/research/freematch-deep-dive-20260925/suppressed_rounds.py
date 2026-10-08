#!/usr/bin/env python3
"""被压制局与连庄解剖：官方牌谱全量统计（只读、无网络、不跑模拟）。

数据来源与口径
--------------
- 官方权威结算：artifacts/sessions/<会话标签>/official/dl-*/events.json。
  每份文件是一场（room_id + game_id，通常 8 局）。字段口径：
  - seats 按座位 0..3 顺序给 user_id；
  - rounds[i] = {dealer, winner, is_draw, multiplier(=番), scores[4], round_no}；
  - blocks[*].events 给逐动作流：tile_drawn / tile_discarded / chi / peng /
    gang / pass / timeout / round_ended。
- 规则唯一来源 src/hangma_bot/hangma：
  - RULES_EVIDENCE.md §2「只能自摸，不允许点炮；禁止抢杠胡」→ 平台不存在放铳；
  - §4「得分 = 底分 × 总番 ×（庄家 ×8 / 闲家 ×1）」，庄家倍率恒 ×8、连庄无递增；
  - §6 抓打圈：打出财神那一圈，其余玩家不能吃/碰/明杠，弃牌只能摸切；
  - 庄家轮转：非流局由本局赢家坐庄，流局保留庄家。

定义（固化为脚本常量）
----------------------
- 场 = 一份 events.json；局 = rounds 中的一项，round_no 从 1 开始。
- 连庄：dealer[i] == dealer[i-1]，等价于第 i-1 局庄家自己胡牌。
- 连庄段 run：同一庄家 d≠我方 的最大连续局区间 [r0, r1]；终结者 = winner[r1]。
  连庄段长度 L = r1-r0+1；L>=2 表示庄家至少连庄过一次。
- 被压制窗口（在第 i 局开打前判定）：
  D_self(N) = 我方最近 N 局每局得分 < 0；
  D_opp(M)  = 同一个非我方座位在最近 M 局连续胡牌；
  SUP_any   = D_self(2) 或 D_opp(2)；SUP_both = D_self(2) 且 D_opp(2)。
  窗口结局在第 i 局（及 i..i+2 三局窗口）上度量。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/suppressed_rounds.py
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
import json
import math
import os
import random

from hangma_bot.hangma.hand_analysis import analyse_hand
from hangma_bot.kernel.actions import Tile

ME = "u_13495c3d79c8"
# 数牌牌码形如 "4t"（万 w / 筒 b / 条 t），字牌是单字。中张 = 数牌 3-7。
SUIT_RANK = {c: i + 1 for i, c in enumerate("123456789")}


def tile_rank(tile):
    """返回数牌点数 1-9；字牌与非法值返回 None。"""
    if isinstance(tile, str) and len(tile) == 2 and tile[0] in SUIT_RANK:
        return SUIT_RANK[tile[0]]
    return None
WEALTH = "白"
OFFSET_LABEL = {1: "下家", 2: "对家", 3: "上家"}


# ================================================================ 统计工具

def wilson(k, n, z=1.96):
    """二项比例的 Wilson 置信区间；n=0 返回 (0.0, 0.0)。"""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def cluster_ci(rows, iters=4000, seed=20260925):
    """按房聚类的 bootstrap 比例置信区间。rows: [(room_id, hit_bool)]。

    房是聚类单位（同一房内 8-11 场高度相关），不能按局当独立样本。
    返回 (lo, hi, obs, n)。
    """
    by_room = collections.defaultdict(list)
    for room, hit in rows:
        by_room[room].append(1 if hit else 0)
    rooms = sorted(by_room)
    if not rooms:
        return (0.0, 0.0, 0.0, 0)
    rng = random.Random(seed)
    num = sum(sum(v) for v in by_room.values())
    den = sum(len(v) for v in by_room.values())
    obs = num / den if den else 0.0
    stats = []
    R = len(rooms)
    for _ in range(iters):
        a = b = 0
        for _ in range(R):
            r = rooms[rng.randrange(R)]
            a += sum(by_room[r])
            b += len(by_room[r])
        stats.append(a / b if b else 0.0)
    stats.sort()
    return (stats[int(0.025 * iters)], stats[min(iters - 1, int(0.975 * iters))], obs, den)


def cluster_boot_diff(rows_a, rows_b, iters=5000, seed=3):
    """按房聚类的两比例/两均值差 bootstrap；返回 (mean_a, mean_b, diff, [lo,hi])。"""
    A = collections.defaultdict(list)
    B = collections.defaultdict(list)
    for room, v in rows_a:
        A[room].append(v)
    for room, v in rows_b:
        B[room].append(v)
    rooms = sorted(set(A) | set(B))
    if not rooms:
        return (None, None, None, None)
    rng = random.Random(seed)
    diffs = []
    for _ in range(iters):
        a, b = [], []
        for _ in range(len(rooms)):
            r = rooms[rng.randrange(len(rooms))]
            a.extend(A.get(r, ()))
            b.extend(B.get(r, ()))
        if a and b:
            diffs.append(sum(a) / len(a) - sum(b) / len(b))
    diffs.sort()
    ma = sum(map(sum, A.values())) / sum(len(v) for v in A.values())
    mb = sum(map(sum, B.values())) / sum(len(v) for v in B.values())
    return (ma, mb, ma - mb,
            [diffs[int(0.025 * len(diffs))], diffs[min(len(diffs) - 1, int(0.975 * len(diffs)))]])


def rate(rows):
    """rows: [(room_id, hit)] → (k, n, rate, wilson_lo, wilson_hi, clus_lo, clus_hi)。"""
    k = sum(1 for _r, h in rows if h)
    n = len(rows)
    lo, hi = wilson(k, n)
    clo, chi, _obs, _n = cluster_ci(rows)
    return {"k": k, "n": n, "rate": (k / n if n else None),
            "wilson": [lo, hi], "cluster": [clo, chi]}


def mean_se(xs):
    """样本均值与正态近似标准误（仅作描述，不宣称独立性）。"""
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return {"n": len(xs), "mean": m, "se": None}
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return {"n": len(xs), "mean": m, "se": math.sqrt(var / len(xs)),
            "median": sorted(xs)[len(xs) // 2]}


# ================================================================ 数据装载

def load_official(root="artifacts/sessions"):
    """返回 {game_id: (path, session_tag, payload)}。"""
    out = {}
    for path in glob.glob(os.path.join(root, "*", "official", "dl-*", "events.json")):
        try:
            with open(path) as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        out[payload.get("game_id")] = (path, path.split(os.sep)[2], payload)
    return out


def round_events(payload):
    """按 round_no 聚合同一局的事件（一局可能跨多个 block）。"""
    buckets = collections.OrderedDict()
    for blk in payload.get("blocks") or []:
        buckets.setdefault(blk.get("round_no"), []).extend(blk.get("events") or [])
    return buckets


def seat_round_stats(events, seat):
    """从一局的官方事件流提取 seat 的行为计数（全部为公开可观测事实）。"""
    st = {
        "draws": 0, "discards": 0, "melds": 0, "chi": 0, "peng": 0, "gang": 0,
        "gang_kinds": [], "pass": 0, "timeout": 0, "teda": 0, "live_discards": 0,
        "middle_discards": 0, "wealth_discards": 0, "fed": 0, "fed_to": [],
        "claims": 0, "claims_as_circle_owner": 0, "claims_blocked_by_circle": 0,
        "wealth_played_at": [], "discard_after_wealth": 0,
    }
    seen_tiles = set()
    last_draw = {}
    last_discard_seat = None
    last_discard_tile = None
    circle_owner = None          # 当前抓打圈圈主（最近打出财神的座位）
    for idx, ev in enumerate(events):
        t = ev.get("type")
        s = ev.get("seat")
        if t == "tile_drawn":
            if s == seat:
                st["draws"] += 1
            last_draw[s] = ev.get("tile")
        elif t == "tile_discarded":
            tile = ev.get("tile")
            if s == seat:
                st["discards"] += 1
                if tile not in seen_tiles:
                    st["live_discards"] += 1
                _r = tile_rank(tile)
                if _r is not None and 3 <= _r <= 7:
                    st["middle_discards"] += 1
                if tile == WEALTH:
                    st["wealth_discards"] += 1
                    st["wealth_played_at"].append(idx)
                if last_draw.get(seat) == tile:
                    st["teda"] += 1
                if circle_owner is not None and circle_owner != seat:
                    st["discard_after_wealth"] += 1
            seen_tiles.add(tile)
            last_discard_seat = s
            last_discard_tile = tile
            # 抓打圈寿命（catch_play.py 文档串）：弃白开圈/换主；圈主的
            # 下一次非白弃牌关圈；摸牌与杠不关圈。
            if tile == WEALTH:
                circle_owner = s
            elif circle_owner == s:
                circle_owner = None
        elif t in ("chi", "peng", "gang"):
            data = ev.get("data") or {}
            is_concealed = (t == "gang" and data.get("kind") == "an")
            if s == seat:
                st["melds"] += 1
                st[t] += 1
                if t == "gang":
                    st["gang_kinds"].append(data.get("kind"))
            if not is_concealed:
                if last_discard_seat is not None and ev.get("tile") == last_discard_tile:
                    if last_discard_seat == seat:
                        st["fed"] += 1
                        st["fed_to"].append(("peng" if t == "peng" else t, ev.get("tile")))
                if circle_owner is not None:
                    if s == seat == circle_owner:
                        st["claims_as_circle_owner"] += 1
                    elif s == seat:
                        st["claims_blocked_by_circle"] += 1
        elif t in ("pass", "timeout"):
            if s == seat:
                st[t] += 1
            data = ev.get("data") or {}
            if t == "pass" or data.get("kind") == "response":
                last_discard_seat = None
                last_discard_tile = None
    return st


def parse_game(game_id, tag, payload):
    seats = [s.get("user_id") for s in payload.get("seats") or []]
    if ME not in seats:
        return None
    my = seats.index(ME)
    ev_by_round = round_events(payload)
    start_hands = {}
    for blk in payload.get("blocks") or []:
        sh = blk.get("start_hands")
        if (sh and blk.get("round_no") not in start_hands
                and any(isinstance(x, list) for x in sh)):
            start_hands[blk.get("round_no")] = sh

    re_info = {}
    for rn, evs in ev_by_round.items():
        for ev in evs:
            if ev.get("type") == "round_ended":
                d = ev.get("data") or {}
                if d.get("round_no") == rn and rn not in re_info:
                    re_info[rn] = {"fan": d.get("fan") or 0,
                                   "detail": list(d.get("detail") or []),
                                   "draw": bool(d.get("draw")),
                                   "winner": ev.get("seat")}
    stats = {rn: [seat_round_stats(ev_by_round[rn], k) for k in range(4)]
             for rn in ev_by_round}
    claim_edges = {}          # round_no -> [(供牌座位, 鸣牌座位, 种类, 牌)]
    for rn, evs in ev_by_round.items():
        edges = []
        last = None
        for ev in evs:
            t = ev.get("type")
            if t == "tile_discarded":
                last = (ev.get("seat"), ev.get("tile"))
            elif t in ("chi", "peng", "gang"):
                data = ev.get("data") or {}
                if t == "gang" and data.get("kind") == "an":
                    continue
                if last and ev.get("tile") == last[1]:
                    edges.append((last[0], ev.get("seat"), data.get("kind") or t,
                                  ev.get("tile")))
            elif t in ("pass", "timeout"):
                data = ev.get("data") or {}
                if t == "pass" or data.get("kind") == "response":
                    last = None
        claim_edges[rn] = edges

    rows = []
    for r in payload.get("rounds") or []:
        rn = r.get("round_no")
        sc = list(r.get("scores") or [0, 0, 0, 0])
        info = re_info.get(rn) or {}
        per = stats.get(rn) or [{} for _ in range(4)]
        sh = start_hands.get(rn)
        hands = []
        if sh and all(isinstance(x, list) and len(x) in (13, 14) for x in sh):
            try:
                hands = [_start_hand_summary(x) for x in sh]
            except ValueError:
                hands = []
        rows.append({
            "start_shanten": ([h.shanten for h in hands] if hands else None),
            "start_whites": ([h.whites_held for h in hands] if hands else None),
            "round_no": rn, "dealer": r.get("dealer"), "winner": r.get("winner"),
            "is_draw": bool(r.get("is_draw")),
            "fan": (info.get("fan") if info else r.get("multiplier")),
            "detail": info.get("detail") or [],
            "scores": sc, "my_score": sc[my],
            "me_won": r.get("winner") == my,
            "i_dealt": r.get("dealer") == my,
            "me": per[my], "all": per,
            "claim_edges": claim_edges.get(rn) or [],
            "opp_melds": sum(per[k].get("melds", 0) for k in range(4) if k != my),
            "opp_fed_by_me": sum(per[k].get("fed", 0) for k in range(4) if k != my),
            "me_fed_by_opp": per[my].get("fed", 0),
        })
    return {
        "game_id": game_id, "room_id": payload.get("room_id"), "session_tag": tag,
        "status": payload.get("status"), "seats": seats, "my_seat": my,
        "rounds": rows, "my_total": sum(x["my_score"] for x in rows),
        "truncated_blocks": sum(1 for b in (payload.get("blocks") or []) if b.get("truncated")),
    }


def _start_hand_summary(codes):
    """起手牌摘要；庄家起手 14 张时取「最优一张弃牌后」的 13 张向听。

    向听、财神数只调用 hangma 的 analyse_hand，不另写一套牌型算法。
    """
    tiles = tuple(Tile(c) for c in codes)
    if len(tiles) == 13:
        return analyse_hand(tiles, 0)
    best = None
    for drop in range(len(tiles)):
        rest = tiles[:drop] + tiles[drop + 1:]
        s = analyse_hand(rest, 0)
        if best is None or (s.shanten, -s.whites_held) < (best.shanten, -best.whites_held):
            best = s
    return best


def verify_settlement(g):
    """按 hangma settlement 复核官方结算；返回违例列表（空 = 逐字一致）。"""
    bad = []
    for r in g["rounds"]:
        sc, w, d, fan = r["scores"], r["winner"], r["dealer"], r["fan"]
        if r["is_draw"] or w is None or w < 0:
            if sc != [0, 0, 0, 0]:
                bad.append((r["round_no"], "draw_nonzero", sc))
            continue
        if fan is None:
            bad.append((r["round_no"], "fan_missing", sc))
            continue
        exp = [0, 0, 0, 0]
        if w == d:
            exp[w] = 24 * fan
            for k in range(4):
                if k != w:
                    exp[k] = -8 * fan
        else:
            exp[w] = 10 * fan
            exp[d] = -8 * fan
            for k in range(4):
                if k != w and k != d:
                    exp[k] = -fan
        if exp != sc:
            bad.append((r["round_no"], "mismatch", sc, exp))
    return bad


def contiguous(rs, i, j):
    """rs[i] 与 rs[j] 是否为官方 rounds 中真正相邻的连续局。

    有 12 场的官方 rounds 数组比 blocks 少一局（blocks 里 8 局都在），
    此时列表里相邻的两项并不是相邻的两局。跨缺口比较庄家会造出假连庄，
    所以所有「上一局」判断都必须先过这一关。
    """
    return rs[j]["round_no"] == rs[i]["round_no"] + (j - i)


def dealer_streak_at(rs, i, my):
    """第 i 局是否处于「对手庄家刚连庄」状态（第 i-1 局庄家自己胡）。"""
    return (i >= 1 and rs[i]["dealer"] is not None and rs[i]["dealer"] != my
            and rs[i]["dealer"] == rs[i - 1]["dealer"] and contiguous(rs, i - 1, i))


def dealer_runs(g):
    """对手（庄家≠我方）坐庄段列表。"""
    rs = g["rounds"]
    runs, i, n = [], 0, len(rs)
    while i < n:
        d = rs[i]["dealer"]
        if d is None:
            i += 1
            continue
        j = i
        while (j + 1 < n and rs[j + 1]["dealer"] == d
               and contiguous(rs, j, j + 1)):
            j += 1
        if d != g["my_seat"]:
            term = rs[j]["winner"]
            runs.append({"dealer": d, "r0": i, "r1": j, "rounds": j - i + 1,
                         "terminator": None if (term is None or term == d) else term,
                         "last_round_of_game": (j == n - 1)})
        i = j + 1
    return runs


# ================================================================ 分析主体

def sweep_streaks(games, res):
    """连庄段：分布、终结者构成、座位/偏移对照。"""
    runs = []
    for g in games:
        for r in dealer_runs(g):
            r.update({"game_id": g["game_id"], "room_id": g["room_id"],
                      "my_seat": g["my_seat"],
                      "offset_me": (g["my_seat"] - r["dealer"]) % 4})
            runs.append(r)
    res["dealer_runs"] = runs

    # 偏移基线：所有「有庄家且有赢家」的局，赢家相对庄家的偏移分布
    off_win = collections.Counter()
    off_tot = collections.Counter()
    for g in games:
        for r in g["rounds"]:
            d = r["dealer"]
            if d is None:
                continue
            off_tot[(g["my_seat"] - d) % 4] += 1     # 仅用于计数参考
            if r["winner"] is not None and r["winner"] >= 0:
                off_win[(r["winner"] - d) % 4] += 1
    res["winner_offset_distribution"] = {
        str(k): {"wins": off_win.get(k, 0),
                 "share_of_nondealer_wins": None} for k in (1, 2, 3)}
    tot_non = sum(off_win.get(k, 0) for k in (1, 2, 3))
    for k in (1, 2, 3):
        res["winner_offset_distribution"][str(k)]["share_of_nondealer_wins"] = (
            off_win.get(k, 0) / tot_non if tot_non else None)
    res["_offset_wins"] = {str(k): off_win.get(k, 0) for k in (1, 2, 3)}
    res["_offset_total_nondealer_wins"] = tot_non

    # 连庄段（L>=2，即庄家确实连过庄）终结者构成
    def bucket(L):
        if L == 1:
            return "L1_常规接庄"
        if L == 2:
            return "L2_连庄1次"
        if L == 3:
            return "L3_连庄2次"
        return "L4+_连庄3次以上"
    summary = collections.defaultdict(lambda: collections.Counter())
    rows_me = collections.defaultdict(list)
    rows_other = collections.defaultdict(list)
    for r in runs:
        b = bucket(r["rounds"])
        summary[b]["n"] += 1
        if r["terminator"] is None:
            summary[b]["censored"] += 1
            continue
        if r["terminator"] == r["my_seat"]:
            summary[b]["me"] += 1
            rows_me[b].append((r["room_id"], True))
            rows_me["ALL"].append((r["room_id"], True))
        else:
            summary[b]["other"] += 1
            rows_me[b].append((r["room_id"], False))
            rows_me["ALL"].append((r["room_id"], False))
        # 每个段贡献「我方」和「另两闲家合并」两条互斥记录
        rows_other[b].append((r["room_id"], r["terminator"] != r["my_seat"]))
        rows_other["ALL"].append((r["room_id"], r["terminator"] != r["my_seat"]))
    out = {}
    for b, c in sorted(summary.items()):
        dec = c["me"] + c["other"]
        out[b] = {"runs": c["n"], "censored": c["censored"],
                  "decided": dec, "me_terminated": c["me"], "other_terminated": c["other"],
                  "me_share": (c["me"] / dec if dec else None),
                  "me_ci": rate(rows_me[b]) if dec else None}
    res["streak_terminator_by_length"] = out

    # 连庄段（L>=2）合并口径 + 与偏移基线对照
    deep = [r for r in runs if r["rounds"] >= 2 and r["terminator"] is not None]
    pool = {"n_runs": len(deep),
            "me": sum(1 for r in deep if r["terminator"] == r["my_seat"])}
    pool["others"] = len(deep) - pool["me"]
    pool["me_share"] = pool["me"] / len(deep) if deep else None
    pool["me_share_wilson"] = list(wilson(pool["me"], len(deep)))
    pool["me_share_cluster"] = list(cluster_ci(
        [(r["room_id"], r["terminator"] == r["my_seat"]) for r in deep])[:2])
    # 偏移加权期望：给定段终结（赢家∈三闲家），我方按偏移基线应占的份额
    shares = res["winner_offset_distribution"]
    exp_num = exp_den = 0
    for r in deep:
        k = str(r["offset_me"])
        p_me = shares[k]["share_of_nondealer_wins"]
        exp_num += p_me
        exp_den += 1
    pool["expected_me_share_by_offset"] = exp_num / exp_den if exp_den else None
    # 逐偏移细分
    by_off = {}
    for k in (1, 2, 3):
        sub = [r for r in deep if r["offset_me"] == k]
        by_off[OFFSET_LABEL[k]] = {
            "n": len(sub),
            "me": sum(1 for r in sub if r["terminator"] == r["my_seat"]),
            "me_share": (sum(1 for r in sub if r["terminator"] == r["my_seat"]) / len(sub)
                         if sub else None),
            "baseline_share_for_this_offset": shares[str(k)]["share_of_nondealer_wins"],
        }
    pool["by_offset"] = by_off
    res["streak_breaker_L_ge_2"] = pool

    # 我方坐庄时的连庄能力（对照）
    our_deal = collections.Counter()
    opp_deal = collections.Counter()
    for g in games:
        my = g["my_seat"]
        for idx, r in enumerate(g["rounds"]):
            d = r["dealer"]
            if d is None:
                continue
            tgt = our_deal if d == my else opp_deal
            tgt["rounds"] += 1
            if r["is_draw"]:
                tgt["draw"] += 1
            elif r["winner"] == d:
                tgt["dealer_won"] += 1
    res["dealer_win_comparison"] = {
        "me_as_dealer": dict(our_deal), "opp_as_dealer": dict(opp_deal)}
    return runs


def streak_frames(games, res, tag="全量"):
    """同一现象在四种口径下的终结者构成，用于复核此前 4 房分析的 19.6/48.6。"""
    A = collections.Counter(); B = collections.Counter()
    C = collections.Counter()
    for g in games:
        my = g["my_seat"]
        rs = g["rounds"]
        for r in dealer_runs(g):
            if r["terminator"] is None:
                continue
            me = (r["terminator"] == my)
            if r["rounds"] >= 2:
                A["n"] += 1; A["me" if me else "other"] += 1
            C["n"] += 1; C["me" if me else "other"] += 1
        for i, r in enumerate(rs):
            if dealer_streak_at(rs, i, my):
                B["n"] += 1
                if r["is_draw"]:
                    B["draw"] += 1
                elif r["winner"] == my:
                    B["me"] += 1
                elif r["winner"] == r["dealer"]:
                    B["dealer_won"] += 1
                elif r["winner"] is not None and r["winner"] >= 0:
                    B["other"] += 1
    def rate_of(c, k, drop=()):
        dec = c["n"] - sum(c.get(x, 0) for x in drop)
        return {"k": c.get(k, 0), "n": dec,
                "rate": (c.get(k, 0) / dec if dec else None)}
    frames = {
        "A_连庄段已终结且段长>=2": {"raw": dict(A), "me_share": rate_of(A, "me")},
        "B_连庄局(含庄家续庄)": {"raw": dict(B),
                            "me_share": rate_of(B, "me", drop=("draw",))},
        "C_连庄段已终结(含段长1)": {"raw": dict(C), "me_share": rate_of(C, "me")},
    }
    for k in frames:
        r = frames[k]["me_share"]
        if r["n"]:
            lo, hi = wilson(r["k"], r["n"])
            r["wilson"] = [lo, hi]
    res.setdefault("streak_frames_by_dataset", {})[tag] = frames
    return frames


def sweep_suppression(games, res):
    """被压制窗口：定义、数量、恢复率、期间行为差异。"""
    win_rows = collections.defaultdict(lambda: collections.defaultdict(list))
    beh_rows = collections.defaultdict(lambda: collections.defaultdict(list))
    all_rows = collections.defaultdict(list)
    windows = []

    for g in games:
        rs = g["rounds"]
        my = g["my_seat"]
        for i in range(len(rs)):
            sc = [x["my_score"] for x in rs]
            wn = [x["winner"] for x in rs]
            d_self2 = (i >= 2 and contiguous(rs, i - 2, i - 1)
                       and all(sc[j] < 0 for j in (i - 2, i - 1)))
            d_self3 = (i >= 3 and contiguous(rs, i - 3, i - 1)
                       and all(sc[j] < 0 for j in (i - 3, i - 2, i - 1)))
            d_opp2 = (i >= 2 and contiguous(rs, i - 2, i - 1)
                      and wn[i - 1] is not None and wn[i - 1] >= 0
                      and wn[i - 1] != my and wn[i - 1] == wn[i - 2])
            d_opp3 = (i >= 3 and contiguous(rs, i - 3, i - 1)
                      and wn[i - 1] is not None and wn[i - 1] >= 0
                      and wn[i - 1] not in (None, my)
                      and wn[i - 1] == wn[i - 2] == wn[i - 3])
            tags = []
            if d_self2:
                tags.append("D_self2")
            if d_self3:
                tags.append("D_self3")
            if d_opp2:
                tags.append("D_opp2")
            if d_opp3:
                tags.append("D_opp3")
            if d_self2 or d_opp2:
                tags.append("SUP_any")
            if d_self2 and d_opp2:
                tags.append("SUP_both")
            if d_self3 and d_opp3:
                tags.append("SUP_both3")

            r = rs[i]
            fut = sc[i:i + 3]
            rec_now = r["my_score"] > 0
            rec_win = bool(r["me_won"])
            rec_3 = sum(fut) > 0
            persist = r["my_score"] < 0
            dealer_on_streak = dealer_streak_at(rs, i, my)
            feats = {
                "melds": r["me"].get("melds", 0),
                "discards": r["me"].get("discards", 0),
                "teda_rate": (r["me"].get("teda", 0) / r["me"]["discards"]
                              if r["me"].get("discards") else None),
                "live_rate": (r["me"].get("live_discards", 0) / r["me"]["discards"]
                              if r["me"].get("discards") else None),
                "middle_rate": (r["me"].get("middle_discards", 0) / r["me"]["discards"]
                                if r["me"].get("discards") else None),
                "wealth_discards": r["me"].get("wealth_discards", 0),
                "fed": r["me"].get("fed", 0),
                "opp_melds": r["opp_melds"],
                "opp_fed_by_me": r["opp_fed_by_me"],
                "pass": r["me"].get("pass", 0),
                "timeout": r["me"].get("timeout", 0),
                "draws": r["me"].get("draws", 0),
                "dealer_on_streak": int(dealer_on_streak),
                "me_is_dealer": int(r["i_dealt"]),
                "is_draw": int(r["is_draw"]),
                "my_score": r["my_score"],
                "i_won": int(rec_win),
            }
            windows.append({"game_id": g["game_id"], "room_id": g["room_id"],
                            "round_no": r["round_no"], "tags": tags,
                            "three_pos": (sum(fut) > 0 if len(fut) == 3 else None),
                            **feats})
            all_rows["ALL"].append((g["room_id"], rec_win))
            for t in tags:
                win_rows[t]["recover_now"].append((g["room_id"], rec_now))
                win_rows[t]["recover_win"].append((g["room_id"], rec_win))
                win_rows[t]["recover_3"].append((g["room_id"], rec_3))
                win_rows[t]["persist"].append((g["room_id"], persist))
                for k, v in feats.items():
                    if isinstance(v, (int, float)) and k not in ("dealer_on_streak",
                                                                 "me_is_dealer", "is_draw"):
                        beh_rows[t][k].append(v)

    for r in ["D_self2", "D_self3", "D_opp2", "D_opp3", "SUP_any", "SUP_both", "SUP_both3"]:
        pass

    def pack(tag):
        d = {}
        for k in ("recover_now", "recover_win", "recover_3", "persist"):
            if win_rows[tag].get(k):
                d[k] = rate(win_rows[tag][k])
        d["behavior"] = {k: mean_se(v) for k, v in sorted(beh_rows[tag].items())}
        return d

    normal = {}
    sup_tags = {"D_self2", "D_self3", "D_opp2", "D_opp3", "SUP_any", "SUP_both", "SUP_both3"}
    for k in ("melds", "discards", "teda_rate", "live_rate", "middle_rate",
              "wealth_discards", "fed", "opp_melds", "opp_fed_by_me", "pass",
              "timeout", "draws", "my_score", "i_won"):
        vals = [w[k] for w in windows if not (set(w["tags"]) & sup_tags)]
        normal[k] = mean_se(vals)
    res["behavior_normal"] = normal
    res["suppression"] = {t: pack(t) for t in sorted(sup_tags)}
    # 与全量基线的按房聚类差值（恢复率是否可分辨）
    base_now = [(w["room_id"], w["my_score"] > 0) for w in windows]
    base_three = [(w["room_id"], w["three_pos"]) for w in windows
                  if w.get("three_pos") is not None]
    for t in sorted(sup_tags):
        res["suppression"][t]["vs_baseline_recover_now"] = cluster_boot_diff(
            win_rows[t]["recover_now"], base_now)
        res["suppression"][t]["vs_baseline_recover_3"] = cluster_boot_diff(
            win_rows[t]["recover_3"], base_three)
    # 全量基线（用于恢复率对照）
    res["baseline_all_rounds"] = {
        "recover_win": rate([(w["room_id"], bool(w["i_won"])) for w in windows]),
        "recover_now": rate([(w["room_id"], w["my_score"] > 0) for w in windows]),
    }
    three = []
    for g in games:
        sc = [x["my_score"] for x in g["rounds"]]
        for i in range(len(sc)):
            if i + 2 < len(sc):
                three.append((g["room_id"], sum(sc[i:i + 3]) > 0))
    res["baseline_all_rounds"]["recover_3"] = rate(three)
    res["_windows"] = windows
    return windows


CONTEXT_FEATURES = ("melds", "discards", "teda_rate", "live_rate", "middle_rate",
                    "wealth_discards", "fed", "opp_melds", "opp_fed_by_me", "pass",
                    "timeout", "draws", "my_score", "i_won")


def _ctx_of(rs, i, my):
    """第 i 局开打前的窗口情境标签（互斥优先级：连庄 > 连胡 > 连失 > 其他）。"""
    r = rs[i]
    dealer_streak = dealer_streak_at(rs, i, my)
    opp_streak = (i >= 2 and contiguous(rs, i - 2, i - 1)
                  and rs[i - 1]["winner"] not in (None, my)
                  and rs[i - 1]["winner"] >= 0 and rs[i - 1]["winner"] == rs[i - 2]["winner"])
    me_lost2 = (i >= 2 and contiguous(rs, i - 2, i - 1)
                and rs[i - 1]["my_score"] < 0 and rs[i - 2]["my_score"] < 0)
    if dealer_streak:
        return "CTX_对手连庄中"
    if opp_streak:
        return "CTX_对手连胡2局"
    if me_lost2:
        return "CTX_我方连失2局"
    return "CTX_其他"


def sweep_contexts(games, res):
    """按「局面情境」分层的我方行为对比；差异用按房聚类 bootstrap 给区间。"""
    buckets = collections.defaultdict(list)
    for g in games:
        rs = g["rounds"]
        my = g["my_seat"]
        for i, r in enumerate(rs):
            bucket = buckets[_ctx_of(rs, i, my)]
            bucket.append({
                "room_id": g["room_id"], "game_id": g["game_id"], "round_no": r["round_no"],
                "melds": r["me"].get("melds", 0),
                "discards": r["me"].get("discards", 0),
                "teda_rate": (r["me"].get("teda", 0) / r["me"]["discards"]
                              if r["me"].get("discards") else None),
                "live_rate": (r["me"].get("live_discards", 0) / r["me"]["discards"]
                              if r["me"].get("discards") else None),
                "middle_rate": (r["me"].get("middle_discards", 0) / r["me"]["discards"]
                                if r["me"].get("discards") else None),
                "wealth_discards": r["me"].get("wealth_discards", 0),
                "fed": r["me"].get("fed", 0),
                "opp_melds": r["opp_melds"],
                "opp_fed_by_me": r["opp_fed_by_me"],
                "pass": r["me"].get("pass", 0),
                "timeout": r["me"].get("timeout", 0),
                "draws": r["me"].get("draws", 0),
                "my_score": r["my_score"],
                "i_won": int(r["me_won"]),
            })
    ref = buckets["CTX_其他"]

    def boot_diff(a, b, key, iters=4000, seed=7):
        """按房聚类的 bootstrap：a-b 的均值差区间（重抽房，不重抽局）。"""
        ra = collections.defaultdict(list); rb = collections.defaultdict(list)
        for x in a:
            if x[key] is not None:
                ra[x["room_id"]].append(x[key])
        for x in b:
            if x[key] is not None:
                rb[x["room_id"]].append(x[key])
        ka, kb = sorted(ra), sorted(rb)
        if not ka or not kb:
            return None
        rng = random.Random(seed)
        diffs = []
        for _ in range(iters):
            va = [v for _ in ka for v in ra[ka[rng.randrange(len(ka))]]]
            vb = [v for _ in kb for v in rb[kb[rng.randrange(len(kb))]]]
            if va and vb:
                diffs.append(sum(va) / len(va) - sum(vb) / len(vb))
        diffs.sort()
        ma = sum(v for vs in ra.values() for v in vs) / sum(len(v) for v in ra.values())
        mb = sum(v for vs in rb.values() for v in vs) / sum(len(v) for v in rb.values())
        return {"mean_a": ma, "mean_b": mb, "diff": ma - mb,
                "ci": [diffs[int(0.025 * len(diffs))], diffs[min(len(diffs) - 1,
                                                               int(0.975 * len(diffs)))]],
                "n_a": sum(len(v) for v in ra.values()), "n_b": sum(len(v) for v in rb.values())}

    out = {}
    for name, rows in sorted(buckets.items()):
        d = {"n": len(rows)}
        d["win_rate"] = rate([(x["room_id"], bool(x["i_won"])) for x in rows])
        d["mean_score"] = mean_se([x["my_score"] for x in rows])
        d["vs_other"] = {k: boot_diff(rows, ref, k) for k in CONTEXT_FEATURES
                         if k != "i_won"}
        out[name] = d
    res["context_behavior"] = out
    return out


def sweep_momentum(games, res):
    """序列动量：P(胡 | 最近 k 局的表现) 对照 P(胡)。"""
    cond = collections.defaultdict(lambda: collections.defaultdict(list))
    for g in games:
        rs = g["rounds"]
        my = g["my_seat"]
        for i in range(len(rs)):
            r = rs[i]
            keys = ["ALL"]
            if i >= 1:
                keys.append("prev_me_won" if rs[i - 1]["me_won"] else "prev_me_lost")
            if i >= 2 and contiguous(rs, i - 2, i - 1):
                if all(rs[j]["my_score"] < 0 for j in (i - 2, i - 1)):
                    keys.append("lost_last2")
                if all(rs[j]["me_won"] for j in (i - 2, i - 1)):
                    keys.append("won_last2")
                if (rs[i - 1]["winner"] == rs[i - 2]["winner"]
                        and rs[i - 1]["winner"] not in (None, my) and rs[i - 1]["winner"] >= 0):
                    keys.append("opp_won_last2")
            if (i >= 3 and contiguous(rs, i - 3, i - 1)
                    and all(rs[j]["my_score"] < 0 for j in (i - 3, i - 2, i - 1))):
                keys.append("lost_last3")
            for k in keys:
                cond[k][g["room_id"]].append((g["room_id"], r["me_won"]))
    out = {}
    for k, by_room in sorted(cond.items()):
        rows = [x for v in by_room.values() for x in v]
        d = rate(rows)
        d["n_games"] = len(by_room)
        out[k] = {"k": d["k"], "n": d["n"], "rate": d["rate"],
                  "wilson": d["wilson"], "cluster": d["cluster"]}
    res["momentum"] = out
    return out


def sweep_attribution(games, res):
    """我方总分亏空来自哪些局面：按情境分解 my_score 合计。"""
    tot = collections.Counter(); cnt = collections.Counter()
    for g in games:
        rs = g["rounds"]
        my = g["my_seat"]
        for i, r in enumerate(rs):
            key = _ctx_of(rs, i, my)
            tot[key] += r["my_score"]
            cnt[key] += 1
        tot["_场总分"] += g["my_total"]
    grand = sum(v for k, v in tot.items() if not k.startswith("_"))
    res["score_attribution"] = {
        k: {"rounds": cnt.get(k, 0), "my_score_sum": tot[k],
            "share": (tot[k] / grand if grand else None)}
        for k in sorted(cnt)}
    res["score_attribution"]["_grand_my_score"] = grand
    return res["score_attribution"]


def binom_p(k, n, p0=1 / 3):
    """两尾二项检验（正态近似 + 小样本精确枚举），用于终结者份额检验。"""
    if n == 0:
        return None
    phat = k / n
    se = math.sqrt(p0 * (1 - p0) / n)
    z = (phat - p0) / se if se else 0.0
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    exact = 0.0
    if n <= 200:
        from math import comb
        for j in range(n + 1):
            pj = comb(n, j) * p0 ** j * (1 - p0) ** (n - j)
            if pj <= comb(n, k) * p0 ** k * (1 - p0) ** (n - k) + 1e-18:
                exact += pj
    return {"k": k, "n": n, "p0": p0, "z": z, "p_normal": p,
            "p_exact": (exact if n <= 200 else None)}


def sweep_start_hands(games, res):
    """用官方起手牌（start_hands）+ hangma 向听控制「牌山效应」。

    起手向听是牌山直接发的，与打法无关；若对手连庄段的庄家起手并不更好，
    或我方在连庄终结局的起手并不更差，则「我方更少终结连庄」更难归因于
    牌山。分析用途，线上不可见他家起手。
    """
    groups = collections.defaultdict(list)
    for g in games:
        my = g["my_seat"]
        rs = g["rounds"]
        for i, r in enumerate(rs):
            sh, wh = r.get("start_shanten"), r.get("start_whites")
            if not sh or r["dealer"] is None:
                continue
            d = r["dealer"]
            me_sh = sh[my] - wh[my]        # 财神每张约抵 1 向听（近似下界）
            d_sh = sh[d] - wh[d]
            on_streak = dealer_streak_at(rs, i, my)
            groups["我方起手向听_全量"].append(sh[my])
            groups["我方起手向听_对手连庄中"].append(sh[my]) if on_streak else None
            groups["我方有效向听_全量"].append(me_sh)
            if on_streak:
                groups["我方有效向听_对手连庄中"].append(me_sh)
                groups["庄家有效向听_连庄中"].append(d_sh)
                groups["庄家起手向听_连庄中"].append(sh[d])
            if d != my and not on_streak:
                groups["庄家有效向听_非连庄"].append(d_sh)
                groups["庄家起手向听_非连庄"].append(sh[d])
            if dealer_streak_at(rs, i, my):
                if r["winner"] == my:
                    groups["我方有效向听_终结连庄局"].append(me_sh)
                elif r["winner"] == d:
                    groups["我方有效向听_连庄续庄局"].append(me_sh)
                else:
                    groups["我方有效向听_他闲终结局"].append(me_sh)
    out = {k: mean_se(v) for k, v in sorted(groups.items())}
    res["start_hand_control"] = out
    return out


def sweep_style(games, res):
    """我方与对手的「番数结构」对比：爆头率、财神弃出、胡均分与盈亏平衡胡率。

    这是本报告里唯一在所有情境下都稳定可分的行为/结果差异；全部输入都是
    官方公开事件与官方 detail（爆头/财飘等），不使用我方私有状态。
    """
    me = collections.Counter()
    opp = collections.Counter()
    by_seat = collections.defaultdict(collections.Counter)
    role_tab = collections.defaultdict(collections.Counter)
    start_sh = collections.defaultdict(list)
    for g in games:
        my = g["my_seat"]
        for r in g["rounds"]:
            me["rounds"] += 1
            me["melds"] += r["me"].get("melds", 0)
            me["disc"] += r["me"].get("discards", 0)
            me["w_disc"] += r["me"].get("wealth_discards", 0)
            for d in (r["detail"] or []):
                me["detail_" + d] += 1
            if r["me_won"]:
                me["won"] += 1
                me["win_score"] += r["my_score"]
                if "爆头" in (r["detail"] or []):
                    me["bt"] += 1
                    me["bt_score"] += r["my_score"]
            else:
                me["lose_score"] += r["my_score"]
            if r["me_won"]:
                me["win_fan_sum"] += (r["fan"] or 0)
            sh = r.get("start_shanten")
            if sh:
                start_sh["me"].append(sh[my] - (r["start_whites"][my] if r.get("start_whites") else 0))
                for k in range(4):
                    if k != my:
                        start_sh["opp"].append(sh[k] - (r["start_whites"][k] if r.get("start_whites") else 0))
            wk = "%s_%s" % ("me" if r["dealer"] == my else "opp", g["game_id"])
            del wk
            for k in range(4):
                if k == my:
                    continue
                a = by_seat[g["seats"][k]]
                a["rounds"] += 1
                a["melds"] += r["all"][k].get("melds", 0)
                a["disc"] += r["all"][k].get("discards", 0)
                a["w_disc"] += r["all"][k].get("wealth_discards", 0)
                if r["is_draw"]:
                    continue
                opp["rounds"] += 1
                opp["melds"] += r["all"][k].get("melds", 0)
                opp["disc"] += r["all"][k].get("discards", 0)
                opp["w_disc"] += r["all"][k].get("wealth_discards", 0)
                if r["winner"] == k:
                    opp["won"] += 1
                    opp["win_fan_sum"] += (r["fan"] or 0)
                    if "爆头" in (r["detail"] or []):
                        opp["bt"] += 1
                    for d in (r["detail"] or []):
                        opp["detail_" + d] += 1
            # 鸣牌 x 爆头 交叉
            for k in range(4):
                st = r["all"][k]
                key = ("me" if k == my else "opp", st.get("melds", 0) > 0)
                role_tab[key]["n"] += 1
                if r["winner"] == k:
                    role_tab[key]["won"] += 1
                    if "爆头" in (r["detail"] or []):
                        role_tab[key]["bt"] += 1

    def pack(c):
        d = {
            "rounds": c["rounds"], "won": c["won"],
            "win_rate": c["won"] / c["rounds"] if c["rounds"] else None,
            "baotou_on_win": c["bt"] / c["won"] if c.get("won") else None,
            "baotou_rate": c["bt"] / c["rounds"] if c["rounds"] else None,
            "mean_fan_on_win": (c["win_fan_sum"] / c["won"] if c.get("won") else None),
            "melds_per_round": c["melds"] / c["rounds"] if c["rounds"] else None,
            "wealth_discards_per_1000": (1000 * c["w_disc"] / c["disc"]
                                         if c.get("disc") else None),
            "detail_share": {k[len("detail_"):]: v / c["won"]
                             for k, v in c.items() if k.startswith("detail_") and c.get("won")},
        }
        if c.get("won") and c.get("lose_score") is not None and c.get("win_score") is not None:
            mw = c["win_score"] / c["won"]
            ml = c["lose_score"] / (c["rounds"] - c["won"])
            d["mean_win_score"] = mw
            d["mean_lose_score"] = ml
            d["break_even_win_rate"] = -ml / (mw - ml)
        return d

    res["style_me_vs_opp"] = {"me": pack(me), "opp": pack(opp)}
    res["style_by_meld_status"] = {
        "%s_meld=%s" % (k[0], k[1]): {"n": v["n"], "win_rate": v["won"] / v["n"],
                                      "baotou_on_win": (v["bt"] / v["won"] if v["won"] else None),
                                      "baotou_rate": v["bt"] / v["n"]}
        for k, v in sorted(role_tab.items())}
    res["start_shanten_me_vs_opp"] = {
        "me": mean_se(start_sh["me"]), "opp": mean_se(start_sh["opp"])}
    # 三项最稳定差异的按房聚类 bootstrap 区间
    sig = {}
    for name, getter in (
            ("胡时爆头率", lambda r, k, my: (r["detail"] is not None,
                                          "爆头" in (r["detail"] or []))),
            ("鸣牌数每局", lambda r, k, my: (True, r["all"][k].get("melds", 0))),
            ("弃财神数每局", lambda r, k, my: (True, r["all"][k].get("wealth_discards", 0)))):
        a, b = [], []
        for g in games:
            my = g["my_seat"]
            for r in g["rounds"]:
                if name == "胡时爆头率":
                    if r["me_won"]:
                        a.append((g["room_id"], int(getter(r, my, my)[1])))
                    for k in range(4):
                        if k != my and r["winner"] == k:
                            b.append((g["room_id"], int(getter(r, k, my)[1])))
                else:
                    a.append((g["room_id"], getter(r, my, my)[1]))
                    for k in range(4):
                        if k != my:
                            b.append((g["room_id"], getter(r, k, my)[1]))
        ma, mb, d, ci = cluster_boot_diff(a, b)
        sig[name] = {"me": ma, "opp": mb, "diff": d, "ci": ci, "n_me": len(a), "n_opp": len(b)}
    res["style_difference_tests"] = sig
    top = []
    for uid, a in by_seat.items():
        if a["rounds"] < 100:
            continue
        top.append({"uid": uid, "rounds": a["rounds"],
                    "win_rate": a["won"] / a["rounds"] if a["rounds"] else None,
                    "baotou_on_win": (a["bt"] / a["won"] if a["won"] else None),
                    "melds_per_round": a["melds"] / a["rounds"],
                    "wealth_discards_per_1000": (1000 * a["w_disc"] / a["disc"]
                                                 if a["disc"] else None)})
    top.sort(key=lambda x: -(x["win_rate"] or 0))
    res["opponents"] = top
    return res["style_me_vs_opp"]


def sweep_uplift(games, res):
    """番数结构对齐的算术外推（不是因果预测，标注为口径 A/B）。

    结算公式（hangma settlement.settle_scores）：庄家胡 24×番、闲家胡 10×番。
    爆头在 compute_fan 里恰好把总番 <<= 1，因此「某局从非爆头变爆头」等价于
    该局我方得分翻倍。
    """
    n_d = n_nd = 0
    fan_d = fan_nd = 0
    bt_scores, nobt_scores = [], []
    for g in games:
        my = g["my_seat"]
        for r in g["rounds"]:
            if not r["me_won"]:
                continue
            if r["dealer"] == my:
                n_d += 1
                fan_d += (r["fan"] or 0)
            else:
                n_nd += 1
                fan_nd += (r["fan"] or 0)
            (bt_scores if "爆头" in (r["detail"] or []) else nobt_scores).append(r["my_score"])
    won = n_d + n_nd
    actual = sum(bt_scores) + sum(nobt_scores)
    opp_fan_mean = res["style_me_vs_opp"]["opp"]["mean_fan_on_win"]
    opp_bt_on_win = res["style_me_vs_opp"]["opp"]["baotou_on_win"]
    uplift = {"wins": won, "wins_as_dealer": n_d, "wins_as_nondealer": n_nd,
              "actual_win_score_sum": actual,
              "mean_fan_me": (fan_d + fan_nd) / won if won else None}
    # 口径 A：只把爆头率补到对手水平，其余不变（每局得分翻倍）
    target_bt = int(round(opp_bt_on_win * won))
    extra = max(0, target_bt - len(bt_scores))
    mean_nobt = (sum(nobt_scores) / len(nobt_scores)) if nobt_scores else 0.0
    uplift["A_target_baotou_wins"] = target_bt
    uplift["A_extra_converted_wins"] = extra
    uplift["A_mean_score_of_converted"] = mean_nobt
    uplift["A_win_score_uplift"] = extra * mean_nobt
    uplift["A_new_win_score_sum"] = actual + extra * mean_nobt
    # 口径 B：整番分布对齐对手均值（庄/闲结构不变）
    cf = n_d * 24 * opp_fan_mean + n_nd * 10 * opp_fan_mean
    uplift["B_new_win_score_sum"] = cf
    uplift["B_win_score_uplift"] = cf - actual
    me = res["style_me_vs_opp"]["me"]
    rounds = me["rounds"]
    ml = me["mean_lose_score"]
    for tag, wsum in (("A", uplift["A_new_win_score_sum"]),
                      ("B", uplift["B_new_win_score_sum"])):
        mw = wsum / won
        uplift[tag + "_mean_win_score"] = mw
        uplift[tag + "_break_even_win_rate"] = -ml / (mw - ml)
        uplift[tag + "_total_my_score"] = mw * won + ml * (rounds - won)
    uplift["actual_total_my_score"] = actual + ml * (rounds - won)
    res["fan_uplift_extrapolation"] = uplift
    return uplift


def sweep_magnitude(games, res):
    """分数量级：连庄继续 vs 被终结的期望分差。"""
    rows = {"dealer_streak_continues": [], "me_breaks": [], "other_breaks": [],
            "no_streak": []}
    fan_w = {"dealer": [], "me": [], "other": []}
    for g in games:
        rs = g["rounds"]
        my = g["my_seat"]
        for i in range(len(rs)):
            r = rs[i]
            if r["is_draw"]:
                continue
            on_streak = dealer_streak_at(rs, i, my)
            key = "no_streak" if not on_streak else (
                "dealer_streak_continues" if r["winner"] == r["dealer"] else
                ("me_breaks" if r["winner"] == my else "other_breaks"))
            rows[key].append(r["my_score"])
            if r["winner"] == r["dealer"]:
                fan_w["dealer"].append(r["fan"])
            elif r["winner"] == my:
                fan_w["me"].append(r["fan"])
            else:
                fan_w["other"].append(r["fan"])
    out = {k: mean_se(v) for k, v in rows.items()}
    out["fan_by_winner_role"] = {k: mean_se(v) for k, v in fan_w.items()}
    # 期望分差：把「庄家续庄」翻成「我方终结」，我方增量为 my_break - dealer_wins
    md = out.get("dealer_streak_continues", {}).get("mean")
    mb = out.get("me_breaks", {}).get("mean")
    ob = out.get("other_breaks", {}).get("mean")
    if md is not None and mb is not None:
        out["swing_dealer_win_to_me_win"] = mb - md
    if md is not None and ob is not None:
        out["swing_dealer_win_to_other_win"] = ob - md
    res["magnitude"] = out
    # 场级：终结次数 vs 场分（相关，不是因果）
    by_game = collections.defaultdict(lambda: {"breaks": 0, "total": 0})
    for g in games:
        rec = by_game[g["game_id"]]
        rec["total"] = g["my_total"]
        for r in dealer_runs(g):
            if r["rounds"] >= 2 and r["terminator"] == g["my_seat"]:
                rec["breaks"] += 1
    grp = collections.defaultdict(list)
    for v in by_game.values():
        grp[min(v["breaks"], 3)].append(v["total"])
    res["game_total_by_break_count"] = {
        str(k): mean_se(v) for k, v in sorted(grp.items())}
    return out


def sweep_circle(games, res):
    """抓打圈（打出财神那一圈）实测：圈主鸣牌权与对手鸣牌封锁。"""
    owner_rounds, other_owner_rounds, no_wealth_rounds = [], [], []
    claims_by_owner = claims_by_nonowner = 0
    for g in games:
        my = g["my_seat"]
        for r in g["rounds"]:
            st = r["me"]
            if st.get("wealth_discards", 0) > 0:
                owner_rounds.append((r, "me"))
            elif any((r["all"][k].get("wealth_discards", 0) > 0) for k in range(4) if k != my):
                other_owner_rounds.append((r, "other"))
            else:
                no_wealth_rounds.append((r, "none"))
            for k in range(4):
                claims_by_owner += r["all"][k].get("claims_as_circle_owner", 0)
                claims_by_nonowner += r["all"][k].get("claims_blocked_by_circle", 0)
    def pack(items, name):
        if not items:
            return {"n": 0}
        return {
            "n": len(items),
            "my_win_rate": rate([(r["my_round_room"], r["me_won"]) for r, _ in items]),
            "my_mean_score": mean_se([r["my_score"] for r, _ in items]),
            "my_melds_mean": mean_se([r["me"].get("melds", 0) for r, _ in items]),
            "opp_melds_mean": mean_se([r["opp_melds"] for r, _ in items]),
        }
    for g in games:
        for r in g["rounds"]:
            r["my_round_room"] = g["room_id"]
    res["circle_by_wealth_owner"] = {
        "me_owns_circle": pack(owner_rounds, "me"),
        "opponent_owns_circle": pack(other_owner_rounds, "other"),
        "no_wealth_discarded": pack(no_wealth_rounds, "none"),
    }
    res["circle_claim_accounting"] = {
        "claims_made_by_circle_owner": claims_by_owner,
        "claims_made_by_non_owner_inside_circle": claims_by_nonowner,
    }
    return res["circle_by_wealth_owner"]


def _fmt_diff(d):
    """把 bootstrap 差值格式化成 "a→b [lo,hi]" 的紧凑串。"""
    if not d:
        return "-"
    return "{0:.3f}→{1:.3f} [{2:.3f},{3:.3f}]".format(
        d["mean_b"], d["mean_a"], d["ci"][0], d["ci"][1])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="artifacts/sessions")
    ap.add_argument("--scores", default="review/freematch-deep-dive-20260925/room-scores.json")
    ap.add_argument("--out", default="review/freematch-deep-dive-20260925/suppressed-rounds.json")
    args = ap.parse_args(argv)

    official = load_official(args.root)
    games, seen, dup = [], set(), []
    records = json.load(open(args.scores))["games"]
    for g0 in records:
        # 同一 game_id 在多个 dl-* 目录重复下载时只计一场：场是 (room_id,
        # game_id) 唯一确定的一次对局，重复计数会污染总分与聚类单位。
        if g0["game_id"] in seen:
            dup.append({"game_id": g0["game_id"], "room_id": g0["room_id"],
                        "my_total": g0["my_total"]})
            continue
        seen.add(g0["game_id"])
        got = official.get(g0["game_id"])
        if not got:
            continue
        g = parse_game(g0["game_id"], got[1], got[2])
        if g:
            games.append(g)

    res = {
        "meta": {"me": ME, "games": len(games),
                 "records_in_room_scores": len(records),
                 "duplicate_records_dropped": len(dup),
                 "duplicate_my_total_dropped": sum(d["my_total"] for d in dup),
                 "my_total_undeduped": sum(g0["my_total"] for g0 in records),
                 "games_dup": dup,
                 "rooms": len(set(g["room_id"] for g in games)),
                 "my_total": sum(g["my_total"] for g in games),
                 "session_tags": dict(collections.Counter(g["session_tag"] for g in games)),
                 "truncated_blocks": sum(g["truncated_blocks"] for g in games)},
        "settlement_violations": [dict({"game_id": g["game_id"], "round_no": b[0],
                                        "kind": b[1]}, observed=b[2],
                                       expected=(b[3] if len(b) > 3 else None))
                                  for g in games for b in verify_settlement(g)],
    }
    print("[装载] 场 {0} 房 {1} 我方合计 {2}".format(
        res["meta"]["games"], res["meta"]["rooms"], res["meta"]["my_total"]))
    print("[复核] 结算违例 {0}".format(len(res["settlement_violations"])))

    sweep_streaks(games, res)
    p = res["streak_breaker_L_ge_2"]
    print("[连庄] 段 {0}（L>=2 且已终结 {1}）：我方终结 {2} = {3:.4f} "
          "Wilson{4} 偏移期望 {5}".format(
              len(res["dealer_runs"]), p["n_runs"], p["me"], p["me_share"],
              [round(x, 4) for x in p["me_share_wilson"]],
              round(p["expected_me_share_by_offset"], 4)))
    print("[连庄] 按长度 " + json.dumps(
        {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()
             if kk != "me_ci"} for k, v in res["streak_terminator_by_length"].items()},
        ensure_ascii=False))
    print("[连庄] 偏移细分 " + json.dumps(p["by_offset"], ensure_ascii=False))

    FIX = ("a_da9bfc607719", "a_5e16dfc1305b", "a_70b2ae92fe29")
    streak_frames(games, res, "全量去重后{0}场".format(len(games)))
    streak_frames([g for g in games if g["room_id"] in FIX], res, "修复后三房")
    for tag, fr in res["streak_frames_by_dataset"].items():
        print("[口径] {0} ".format(tag) + json.dumps(
            {k: {"me_share": round(v["me_share"]["rate"], 4) if v["me_share"]["rate"] else None,
                 "n": v["me_share"]["n"], "raw": v["raw"]} for k, v in fr.items()},
            ensure_ascii=False))

    sweep_suppression(games, res)
    print("[基线] 全量局 " + json.dumps(
        {k: {"k": v["k"], "n": v["n"], "rate": round(v["rate"], 4)}
         for k, v in res["baseline_all_rounds"].items()}, ensure_ascii=False))
    for t in ("D_self2", "D_opp2", "D_self3", "D_opp3", "SUP_any", "SUP_both", "SUP_both3"):
        d = res["suppression"][t]
        print("[压制] {0:9} n={1:5} 当场恢复 {2} ({3}) 三局恢复 {4} ({5})".format(
            t, d["recover_win"]["n"], round(d["recover_now"]["rate"], 4),
            "-".join("{0:.4f}".format(x) for x in d["recover_now"]["wilson"]),
            round(d["recover_3"]["rate"], 4),
            "-".join("{0:.4f}".format(x) for x in d["recover_3"]["wilson"])))
        vn = d.get("vs_baseline_recover_now")
        v3 = d.get("vs_baseline_recover_3")
        if vn and v3:
            print("[压制] {0:9} vs基线(聚类bootstrap) 当场 {1:+.4f} [{2:+.4f},{3:+.4f}]"
                  " 三局 {4:+.4f} [{5:+.4f},{6:+.4f}]".format(
                      t, vn[2], vn[3][0], vn[3][1], v3[2], v3[3][0], v3[3][1]))

    save_contexts = sweep_contexts(games, res)
    for name, d in sorted(save_contexts.items()):
        print("[情境] {0:14} n={1:5} 胡率 {2:.4f} 均分 {3:7.3f} | vs其他: 鸣牌 {4} 摸切率 {5} 生张率 {6} 喂牌 {7}".format(
            name, d["n"], d["win_rate"]["rate"], d["mean_score"]["mean"],
            _fmt_diff(d["vs_other"]["melds"]), _fmt_diff(d["vs_other"]["teda_rate"]),
            _fmt_diff(d["vs_other"]["live_rate"]), _fmt_diff(d["vs_other"]["fed"])))

    mom = sweep_momentum(games, res)
    for k, d in sorted(mom.items()):
        print("[动量] {0:16} n={1:5} 胡率 {2:.4f} Wilson[{3:.4f},{4:.4f}]".format(
            k, d["n"], d["rate"], d["wilson"][0], d["wilson"][1]))

    att = sweep_attribution(games, res)
    for k, d in sorted(att.items()):
        if k.startswith("_"):
            continue
        print("[归因] {0:14} 局数 {1:5} 我方合计 {2:7d} 占比 {3:.3f}".format(
            k, d["rounds"], d["my_score_sum"], d["share"]))
    print("[归因] 全量我方合计 {0}".format(att["_grand_my_score"]))

    sh = sweep_start_hands(games, res)
    for k, v in sorted(sh.items()):
        if v:
            print("[起手] {0:24} n={1:5} 均 {2:.3f} 中位 {3}".format(
                k, v["n"], v["mean"], v.get("median")))

    print("[检验] 连庄终结份额 全量 " + json.dumps(
        binom_p(res["streak_breaker_L_ge_2"]["me"],
                res["streak_breaker_L_ge_2"]["n_runs"], 1 / 3), ensure_ascii=False))
    print("[检验] 连庄终结份额 修复后三房 " + json.dumps(
        binom_p(7, 34, 1 / 3), ensure_ascii=False))
    res["tests"] = {
        "streak_breaker_all_dedup": binom_p(res["streak_breaker_L_ge_2"]["me"],
                                            res["streak_breaker_L_ge_2"]["n_runs"], 1 / 3),
        "streak_breaker_fixed3": binom_p(7, 34, 1 / 3),
    }

    st = sweep_style(games, res)
    print("[风格] 我方 " + json.dumps(
        {k: (round(v, 4) if isinstance(v, float) else v)
         for k, v in st["me"].items() if k != "detail_share"}, ensure_ascii=False))
    print("[风格] 对手 " + json.dumps(
        {k: (round(v, 4) if isinstance(v, float) else v)
         for k, v in st["opp"].items() if k != "detail_share"}, ensure_ascii=False))
    print("[风格] 起手有效向听 " + json.dumps(res["start_shanten_me_vs_opp"], ensure_ascii=False))
    print("[风格] 差异检验 " + json.dumps(
        {k: {"me": round(v["me"], 4), "opp": round(v["opp"], 4), "diff": round(v["diff"], 4),
             "ci": [round(x, 4) for x in v["ci"]]}
         for k, v in res["style_difference_tests"].items()}, ensure_ascii=False))
    print("[风格] 鸣牌x爆头 " + json.dumps(res["style_by_meld_status"], ensure_ascii=False))

    up = sweep_uplift(games, res)
    print("[外推] " + json.dumps(
        {k: (round(v, 3) if isinstance(v, float) else v) for k, v in up.items()},
        ensure_ascii=False))

    sweep_magnitude(games, res)
    m = res["magnitude"]
    print("[量级] 续庄均值 {0} 我方终结均值 {1} 他闲终结均值 {2} 无连庄均值 {3}".format(
        round(m["dealer_streak_continues"]["mean"], 3), round(m["me_breaks"]["mean"], 3),
        round(m["other_breaks"]["mean"], 3), round(m["no_streak"]["mean"], 3)))
    print("[量级] 番数均值 " + json.dumps(
        {k: round(v["mean"], 3) for k, v in m["fan_by_winner_role"].items()}, ensure_ascii=False))
    print("[量级] 翻转增益 " + json.dumps(
        {k: (round(v, 3) if isinstance(v, float) else v)
         for k, v in m.items() if k.startswith("swing")}, ensure_ascii=False))

    sweep_circle(games, res)
    print("[抓打圈] " + json.dumps(
        {k: {"n": v.get("n"),
             "my_win": (round(v["my_win_rate"]["rate"], 4) if v.get("n") else None),
             "my_mean_score": (round(v["my_mean_score"]["mean"], 2) if v.get("n") else None),
             "opp_melds": (round(v["opp_melds_mean"]["mean"], 3) if v.get("n") else None)}
         for k, v in res["circle_by_wealth_owner"].items()}, ensure_ascii=False))
    print("[抓打圈] 鸣牌权账 " + json.dumps(res["circle_claim_accounting"], ensure_ascii=False))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    def_dump = {k: v for k, v in res.items() if not k.startswith("_")}
    with open(args.out, "w") as fh:
        json.dump(def_dump, fh, ensure_ascii=False, indent=1)
    print("[写出] {0}".format(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
