#!/usr/bin/env python3
"""自由赛（官方自动匹配房）统计功效与积累计划：只读复算脚本。

设计约束（本仓纪律）：
- 只读：不联网、不启动任何官方房、不写任何数据文件（除 --json 显式指定的输出路径）。
- 可复跑：所有数字都由本脚本从既有官方产物重算，随机数种子固定。
- 聚类单位是「房」：每房 = 10 场（batch）× 每场 8 局（round），四家零和；
  所有区间都用房级 cluster bootstrap 或 CR0（房级三明治标准误），不用局级独立假设。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python review/freematch-deep-dive-20260925/freematch_power.py
    # 可选：--json /tmp/out.json --reps 20000 --seed 20260925

数据来源（全部只读）：
1. artifacts/**/events.json、datasets/**/events.json
   官方牌谱（/api/test-rooms/{id}/games/{batch}/events 原文）。按 game_id 去重（保 mtime 最新）。
2. runs/auto-match-watchdog/auto-match-watchdog-state.json
   当前战役（r18-sse-freematch-campaign-20260925b）的盯盘账本。
3. artifacts/sessions/*/audit/runs/run-*/manifest.json + lifecycle.jsonl
   逐房 run manifest 的 policy_version（策略身份）与墙上时钟（起止时间）。
4. artifacts/sessions/*/audit/runs/run-*/participants/<me>/games/*.jsonl
   官方 game_finished.final_scores，用于与牌谱逐局求和对拍（数据完整性）。
5. datasets/leaderboard/snapshots/*/leaderboard-{all,today,week}.json
   官方门户积分总榜快照，用于确认「平台真正的排序量」口径。
6. review/freematch-deep-dive-20260925/room-scores.json
   既有提取产物，用作交叉核对（本脚本不写它）。
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
import math
import os
import random
from statistics import NormalDist

# ---------------------------------------------------------------- 常量与口径

ME = "u_13495c3d79c8"          # 我方官方身份（牌谱 seats[].user_id）
TZ = datetime.timezone(datetime.timedelta(hours=8))  # 报告一律用北京时间
Z_ALPHA2 = 1.959963984540054   # 双侧 alpha=0.05 的 z 分位
Z_POWER = 0.8416212335729143   # 80% 功效的 z 分位
GAMES_PER_ROOM = 10            # 官方：满 4 人即开 M=10 场并发对局（接入指南 v35 /api/match）
R18_V1 = "r18_integrated_positive_v1"
R18_V2 = "r18_integrated_positive_v2"
CAMPAIGN_B = "r18-sse-freematch-campaign-20260925b"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def log(msg: str = "") -> None:
    print(msg)


def rule(title: str) -> None:
    log("")
    log("=" * 78)
    log(title)
    log("=" * 78)


def ms_to_bj(ms):
    """Unix 毫秒（UTC）→ 北京时间字符串。"""
    if not ms:
        return "-"
    return datetime.datetime.fromtimestamp(ms / 1000.0, TZ).strftime("%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 数据装载

def load_game_payloads(roots=("artifacts", "datasets")):
    """扫描官方牌谱原文，返回 {game_id: (mtime, payload, path)}，按 game_id 去重。

    去重口径与既有 extract_room_scores.py 一致：同一 game_id 保留 mtime 最新的一份
    （官方牌谱按 dl-* 分片下载，同一场可能被重复下载）。这里额外做的是递归扫描：
    既有脚本只匹配 artifacts/sessions/*/official/dl-*/events.json 与
    datasets/derived/*/official/*/official/dl-*/events.json，会漏掉
    artifacts/sessions/<tag>/official/official/dl-*/（多一层 official/）这类布局。
    """
    out = {}
    for root in roots:
        for path in glob.glob(os.path.join(ROOT, root, "**", "events.json"), recursive=True):
            try:
                with open(path) as fh:
                    payload = json.load(fh)
            except (OSError, ValueError):
                continue
            gid = payload.get("game_id")
            if not gid:
                continue
            mt = os.path.getmtime(path)
            if gid not in out or mt > out[gid][0]:
                out[gid] = (mt, payload, path)
    return out


def load_run_meta():
    """扫描全部 run manifest，返回 {room_id: 策略身份与墙上时钟}。

    wall_time_unix_ms 是墙上时钟（Unix 毫秒，UTC）；end_ms 取 lifecycle.jsonl
    最后一条事件的墙上时钟，即该房在场上的终止时刻。
    """
    meta = {}
    for path in glob.glob(os.path.join(ROOT, "artifacts/sessions/*/audit/runs/run-*/manifest.json")):
        try:
            with open(path) as fh:
                man = json.load(fh)
        except (OSError, ValueError):
            continue
        room = (man.get("context") or {}).get("tournament_id")
        if not room or room == "unknown":
            continue
        run_dir = os.path.dirname(path)
        start = man.get("wall_time_unix_ms")
        end = None
        life = os.path.join(run_dir, "lifecycle.jsonl")
        if os.path.exists(life):
            try:
                with open(life) as fh:
                    for line in fh:
                        try:
                            rec = json.loads(line)
                        except ValueError:
                            continue
                        t = rec.get("wall_time_unix_ms")
                        if t and (end is None or t > end):
                            end = t
            except OSError:
                pass
        parts = run_dir.split(os.sep)
        tag = parts[parts.index("sessions") + 1] if "sessions" in parts else ""
        prev = meta.get(room)
        if prev is None or (start or 0) < (prev.get("start_ms") or 0):
            meta[room] = {
                "policy_version": (man.get("payload") or {}).get("policy_version"),
                "session_tag": tag,
                "run_dir": run_dir,
                "start_ms": start,
                "end_ms": end,
            }
    return meta


def collect_rooms(payloads, meta, me=ME):
    """把牌谱按房聚合成房级记录（只收我方在席、房号以 a_ 开头的自动匹配房）。

    测试房（t_ 前缀）一律排除：官方积分总榜明确「测试房/正式赛不计」。
    """
    by_room = collections.defaultdict(list)
    for gid, (mt, payload, path) in payloads.items():
        seats = [s.get("user_id") for s in (payload.get("seats") or [])]
        if me not in seats:
            continue
        room = payload.get("room_id") or ""
        if not room.startswith("a_"):
            continue
        my = seats.index(me)
        rounds = payload.get("rounds") or []
        seat_total = [0, 0, 0, 0]
        my_score = 0
        for rnd in rounds:
            sc = rnd.get("scores") or [0, 0, 0, 0]
            for i in range(min(4, len(sc))):
                seat_total[i] += sc[i]
            my_score += sc[my] if my < len(sc) else 0
        order = sorted(range(4), key=lambda i: -seat_total[i])
        by_room[room].append({
            "game_id": payload.get("game_id"),
            "mtime": mt,
            "path": path,
            "my_seat": my,
            "my_score": my_score,             # 我方本场净分（逐局求和）
            "seat_total": seat_total,         # 四座本场总分（座位 0..3）
            "my_rank": order.index(my) + 1,   # 本场名次 1..4
            "n_rounds": len(rounds),
            "seats": tuple(seats),
        })
    rooms = []
    for room, games in by_room.items():
        games.sort(key=lambda g: g["game_id"])
        info = meta.get(room) or {}
        # 房级四家总分必须按 **user_id** 聚合：官方口径「同一 4 人、座次逐场重洗」，
        # 用座位号聚合会把同一玩家在不同场次算到不同列上。
        by_user = collections.Counter()
        for g in games:
            for i, uid in enumerate(g["seats"]):
                by_user[uid] += g["seat_total"][i]
        my_room_total = by_user.get(me, 0)
        ranked = sorted(by_user.items(), key=lambda kv: (-kv[1], kv[0]))
        room_rank = [uid for uid, _ in ranked].index(me) + 1 if me in by_user else None
        rooms.append((room, {
            "room_id": room,
            "games": games,
            "n_games": len(games),
            "net": sum(g["my_score"] for g in games),   # 房级净分 = 10 场净分之和
            "room_total": my_room_total,
            "room_totals": by_user,                     # user_id -> 房级总分（四家）
            "seat_variants": len({g["seats"] for g in games}),  # >1 表示房内座次重洗/换人
            "room_rank": room_rank,                     # 房级名次 1..4（按 user_id 聚合）
            "game_firsts": sum(1 for g in games if g["my_rank"] == 1),
            "min_rounds": min(g["n_rounds"] for g in games),
            "session_tag": info.get("session_tag", ""),
            "policy_version": info.get("policy_version"),
            "finished_ms": info.get("end_ms") or int(max(g["mtime"] for g in games) * 1000),
            "start_ms": info.get("start_ms"),
            "has_manifest": bool(info),
        }))
    rooms.sort(key=lambda kv: kv[1]["finished_ms"])
    return rooms


def verify_against_final_scores(rooms, meta, me=ME):
    """把牌谱逐局求和与官方 game_finished.final_scores 对拍（数据完整性）。

    返回 (对拍场数, 不一致清单)。
    """
    checked = 0
    bad = []
    for room, rec in rooms:
        info = meta.get(room) or {}
        run_dir = info.get("run_dir")
        if not run_dir:
            continue
        games_dir = os.path.join(run_dir, "participants", me, "games")
        if not os.path.isdir(games_dir):
            continue
        for gpath in glob.glob(os.path.join(games_dir, "*.jsonl")):
            gid = os.path.basename(gpath)[:-6]
            final = None
            try:
                with open(gpath) as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        if obj.get("kind") == "game_finished":
                            final = (obj.get("payload") or {}).get("final_scores")
            except OSError:
                continue
            mine = next((g for g in rec["games"] if g["game_id"] == gid), None)
            if final is None or mine is None:
                continue
            checked += 1
            if list(final) != list(mine["seat_total"]):
                bad.append((room, gid, list(final), mine["seat_total"]))
    return checked, bad


# ---------------------------------------------------------------- 统计工具

def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def sd(xs):
    """样本标准差（n-1）。"""
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def skew(xs):
    """Fisher-Pearson 偏度（含小样本校正 G1）：正值 = 右尾长。"""
    n = len(xs)
    if n < 3:
        return float("nan")
    m = mean(xs)
    s = sd(xs)
    if s == 0:
        return float("nan")
    g1 = sum(((x - m) / s) ** 3 for x in xs) / n
    return g1 * math.sqrt(n * (n - 1)) / (n - 2)


def cluster_stats(room_values, per_game_by_room):
    """房级聚类统计。

    room_values：每房的「每局均分」= 房净分 / 场数。
    per_game_by_room：每房的逐局净分列表（用于池化均值、ICC、设计效应）。
    """
    out = {}
    n_rooms = len(room_values)
    pooled = [x for vs in per_game_by_room for x in vs]
    out["n_rooms"] = n_rooms
    out["n_games"] = len(pooled)
    out["mean"] = mean(pooled) if pooled else float("nan")
    out["total"] = sum(pooled)
    out["sd_room"] = sd(room_values)
    out["cr0_se"] = out["sd_room"] / math.sqrt(n_rooms) if n_rooms else float("nan")
    out["ci_cr0"] = (out["mean"] - Z_ALPHA2 * out["cr0_se"],
                     out["mean"] + Z_ALPHA2 * out["cr0_se"])
    out["sd_game"] = sd(pooled)
    out["skew_game"] = skew(pooled)
    out["min_game"] = min(pooled) if pooled else float("nan")
    out["max_game"] = max(pooled) if pooled else float("nan")
    out["min_room"] = min(room_values) if n_rooms else float("nan")
    out["max_room"] = max(room_values) if n_rooms else float("nan")
    k = (len(pooled) / n_rooms) if n_rooms else 0
    if n_rooms > 1 and k > 1:
        grand = out["mean"]
        msb = sum(len(v) * (mean(v) - grand) ** 2 for v in per_game_by_room) / (n_rooms - 1)
        msw = sum(sum((x - mean(v)) ** 2 for x in v) for v in per_game_by_room) / (len(pooled) - n_rooms)
        denom = msb + (k - 1) * msw
        raw_icc = (msb - msw) / denom if denom > 0 else 0.0
        out["icc_raw"] = raw_icc
        out["icc"] = max(0.0, raw_icc)   # 负 ICC 无意义，展示时截断为 0
        out["design_effect"] = 1 + (k - 1) * out["icc"]
    else:
        out["icc"] = float("nan")
        out["design_effect"] = float("nan")
    out["naive_se"] = (out["sd_game"] / math.sqrt(len(pooled))) if pooled else float("nan")
    return out


def bootstrap_ci(room_values, reps=20000, seed=20260925, alpha=0.05):
    """房级 cluster bootstrap（整块重抽样，保留房内相关）。返回 (lo, hi)。"""
    if not room_values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(room_values)
    means = []
    for _ in range(reps):
        s = 0.0
        for _ in range(n):
            s += room_values[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[max(0, int(math.floor(alpha / 2 * reps)))]
    hi = means[min(reps - 1, int(math.ceil((1 - alpha / 2) * reps)) - 1)]
    return (lo, hi)


def betainc(a, b, x):
    """正则化不完全贝塔函数 I_x(a,b)，供 Student-t 分位使用。"""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    # 标准 Lentz 连分式：先算首项 h，再逐对更新偶、奇项。旧实现在
    # i=0 额外乘了一次 2，令 t_cdf(0.84, df=678)>1，低估功效房数。
    def continued_fraction(aa, bb, xx):
        tiny = 1e-30
        qab, qap, qam = aa + bb, aa + 1.0, aa - 1.0
        c = 1.0
        d = 1.0 - qab * xx / qap
        if abs(d) < tiny:
            d = tiny
        d = 1.0 / d
        h = d
        for m in range(1, 301):
            m2 = 2 * m
            term = m * (bb - m) * xx / ((qam + m2) * (aa + m2))
            d = 1.0 + term * d
            if abs(d) < tiny:
                d = tiny
            c = 1.0 + term / c
            if abs(c) < tiny:
                c = tiny
            d = 1.0 / d
            h *= d * c

            term = -(aa + m) * (qab + m) * xx / ((aa + m2) * (qap + m2))
            d = 1.0 + term * d
            if abs(d) < tiny:
                d = tiny
            c = 1.0 + term / c
            if abs(c) < tiny:
                c = tiny
            d = 1.0 / d
            change = d * c
            h *= change
            if abs(change - 1.0) < 1e-12:
                return h
        raise ArithmeticError("不完全贝塔连分式未收敛")

    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * continued_fraction(a, b, x) / a
    return 1.0 - front * continued_fraction(b, a, 1.0 - x) / b


def t_cdf(t, df):
    x = df / (df + t * t)
    p = 0.5 * betainc(df / 2.0, 0.5, x)
    return p if t <= 0 else 1 - p


def t_ppf(p, df):
    """t 分布分位数（二分法）。"""
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def required_rooms(delta, sd_room, alpha=0.05, power=0.80):
    """单样本检验（H0: 每局均分 = 0）所需房数。

    z 近似：R = (z_{1-a/2} + z_power)^2 * sd_room^2 / delta^2
    t 迭代：R <- (t_{R-1,1-a/2} + t_{R-1,power})^2 * sd_room^2 / delta^2，直到不动点
    """
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1 - alpha / 2)
    z_power = normal.inv_cdf(power)
    z_need = (z_alpha + z_power) ** 2 * sd_room ** 2 / delta ** 2
    r = max(2, int(math.ceil(z_need)))
    for _ in range(200):
        t1 = t_ppf(1 - alpha / 2, r - 1)
        t2 = t_ppf(power, r - 1)
        r_new = max(2, int(math.ceil((t1 + t2) ** 2 * sd_room ** 2 / delta ** 2)))
        if r_new == r:
            break
        r = r_new
    return {"z": int(math.ceil(z_need)), "t": r,
            "games_z": int(math.ceil(z_need)) * GAMES_PER_ROOM,
            "games_t": r * GAMES_PER_ROOM}


# ---------------------------------------------------------------- 各节分析

def section_rooms(rooms, meta, room_scores_path, me=ME):
    rule("0. 房集合与数据完整性")
    log("递归扫描得到我方自动匹配房（a_ 前缀，按 game_id 去重）：%d 房 / %d 场"
        % (len(rooms), sum(r["n_games"] for _, r in rooms)))
    log("  其中有 run manifest（可判定策略身份与墙上时钟）：%d 房"
        % sum(1 for _, r in rooms if r["has_manifest"]))
    dist = collections.Counter(r["n_games"] for _, r in rooms)
    log("  每房场数分布：%s（官方口径：每房 10 场 x 8 局，M=10）" % dict(sorted(dist.items())))

    if os.path.exists(room_scores_path):
        with open(room_scores_path) as fh:
            prev = json.load(fh)
        prev_ids = {r["room_id"] for r in prev.get("rooms", [])}
        mine = {r["room_id"] for _, r in rooms}
        missing = sorted(mine - prev_ids)
        extra = sorted(prev_ids - mine)
        log("  与既有 room-scores.json 交叉核对：该文件 %d 房，本脚本多出 %d 房，少 %d 房"
            % (len(prev_ids), len(missing), len(extra)))
        for rid in missing:
            rec = next(r for r_, r in rooms if r_ == rid)
            log("    + %s  场=%d  净分=%+d  策略=%s  结束=%s"
                % (rid, rec["n_games"], rec["net"], rec["policy_version"],
                   ms_to_bj(rec["finished_ms"])))
        if missing:
            log("    => 既有提取脚本的 glob 只覆盖 artifacts/sessions/*/official/dl-*/ 与")
            log("       datasets/derived/*/official/*/official/dl-*/，会漏掉")
            log("       artifacts/sessions/<tag>/official/official/dl-*/（多一层 official/）")
            log("       这类布局；本脚本递归扫描，故更全。room-scores.json 未被本脚本修改。")

    rule("0b. 牌谱逐局求和 x 官方 game_finished.final_scores 对拍")
    checked, bad = verify_against_final_scores(rooms, meta, me=me)
    log("对拍场数：%d；不一致：%d" % (checked, len(bad)))
    for row in bad[:5]:
        log("  %s" % (row,))
    log("（口径：牌谱 rounds[].scores 四座求和 vs audit 的 game_finished.final_scores 四座向量）")


def section_cadence(rooms, ledger):
    """实测每房耗时与开房节奏（决定「房数 → 小时」的换算系数）。"""
    rule("1. 墙上时钟：每房耗时与开房节奏（房数 → 小时）")
    durs, starts = [], []
    for _, r in rooms:
        if r["start_ms"] and r["finished_ms"]:
            durs.append((r["finished_ms"] - r["start_ms"]) / 60000.0)
            starts.append((r["start_ms"], r["room_id"]))
    starts.sort()
    gaps = [(starts[i + 1][0] - starts[i][0]) / 60000.0 for i in range(len(starts) - 1)]
    gaps = [g for g in gaps if 0 < g <= 60]     # 只取连续开房的相邻差
    durs_sorted = sorted(durs)
    if durs:
        log("房内耗时（manifest 起始 -> lifecycle 末条）n=%d：中位 %.2f min，均值 %.2f min，"
            "P10 %.2f，P90 %.2f"
            % (len(durs), durs_sorted[len(durs) // 2], mean(durs),
               durs_sorted[len(durs_sorted) // 10], durs_sorted[int(len(durs_sorted) * 0.9)]))
    if gaps:
        log("连续开房节奏（相邻房起始时间差，<=60 min 计）n=%d：中位 %.2f min/房，均值 %.2f min/房"
            % (len(gaps), sorted(gaps)[len(gaps) // 2], mean(gaps)))
    ledger_gap = None
    if ledger:
        ts = []
        for rm in ledger.get("rooms", []):
            fp = os.path.join(ROOT, rm["session_log"])
            if os.path.exists(fp):
                ts.append((os.path.getmtime(fp), rm["room_id"]))
        ts.sort()
        d = [(ts[i + 1][0] - ts[i][0]) / 60.0 for i in range(len(ts) - 1)]
        d = [x for x in d if 0 < x <= 60]
        if d:
            ledger_gap = sorted(d)[len(d) // 2]
            log("账本 session 日志 mtime 差（同口径，n=%d）：中位 %.2f min/房" % (len(d), ledger_gap))
    cadence = sorted(gaps)[len(gaps) // 2] if gaps else (ledger_gap or float("nan"))
    log("=> 规划用节奏：%.2f min/房（单实例、连续开房）。" % cadence)
    log("   官方约束：M=10 场并发 x 每场 8 局是在同一房内串行完成的，房与房之间串行；")
    log("   多开只能靠多个身份/实例（每身份一条全局 token），小时数按并行数线性摊薄。")
    return cadence, (mean(durs) if durs else float("nan")), \
           (durs_sorted[len(durs) // 2] if durs else float("nan"))


def section_leaderboard(rooms, snapshots_glob):
    """用官方积分总榜快照反推「平台真正的排序量」。"""
    rule("2. 平台真正的排序量：官方积分总榜口径复算")
    log("官方依据（接入指南 v35 /api/match 与排行榜三榜，2026-09-23 更新、本仓快照原文）：")
    log("  - 自由匹配房 = 满 4 人即开 M=10 场并发对局 x 每场 8 局（同一 4 人、座次逐场重洗），")
    log("    单会话样本 80 手/人；整场打完（finished 约 60s 宽限）房间自动关停。")
    log("  - 门户「排行榜」Tab = 积分总榜（全史/今日/周），行字段 rank/user_id/name/rooms/firsts/score；")
    log("    数据源 = 自动匹配房（kind=auto）整场完整打完的战绩；void/崩溃收敛/强关/测试房/正式赛不计。")
    log("  - 单场得分榜是另一张榜（行 = 每场 final_scores 最高座位），不是积分总榜的排序量。")
    log("")
    log("用我方本地复算去对官方行（窗口 [from, as_of]，按房终止时刻过滤）：")
    log("%-18s%-6s%7s%7s%11s%10s%11s%10s"
        % ("快照(UTC)", "期", "官方房", "本地房", "官方score", "本地净分", "官方firsts", "本地首名"))
    matched = []
    for path in sorted(glob.glob(snapshots_glob)):
        try:
            with open(path) as fh:
                snap = json.load(fh)
        except (OSError, ValueError):
            continue
        me_row = snap.get("me") if isinstance(snap, dict) else None
        if not me_row or "rooms" not in me_row:
            continue
        frm = (snap.get("from") or 0) * 1000
        as_of = snap.get("as_of") or 0
        sel = [r for _, r in rooms if as_of and frm <= r["finished_ms"] <= as_of * 1000]
        local_net = sum(r["net"] for r in sel)
        local_firsts = sum(1 for r in sel if r["room_rank"] == 1)
        utc = datetime.datetime.fromtimestamp(as_of, datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log("%-18s%-6s%7d%7d%11d%10d%11d%10d"
            % (utc, snap.get("period", ""), me_row["rooms"], len(sel),
               me_row["score"], local_net, me_row.get("firsts", -1), local_firsts))
        matched.append((utc, snap.get("period"), me_row["rooms"] == len(sel),
                        me_row["score"] == local_net,
                        me_row.get("firsts") == local_firsts))
    covered = [m for m in matched if m[2]]
    log("")
    log("=> 本地归档覆盖完整的面板（官方房数 == 本地房数）：%d 个" % len(covered))
    log("   其中 score 逐位相同：%d 个；firsts 逐位相同：%d 个"
        % (sum(1 for m in covered if m[3]), sum(1 for m in covered if m[4])))
    uncovered = [m for m in matched if not m[2]]
    if uncovered:
        log("   其余 %d 个面板是 all 期或 09-09/09-10 早期窗口：本仓 artifacts/ 只归档了"
            % len(uncovered))
        log("   09-23 起的房，早期房散落在 datasets/derived/**/events.json.gz（且接入指南明示")
        log("   早期长局 rounds 每场仅尾部 1-2 行），本地复算对不上，故不作为口径证据。")
    if covered:
        log("")
        log("   结论（官方口径 + 本仓实测复算）：官方积分总榜的")
        log("     rooms  = 房数（每房 = 10 场 x 8 局）；")
        log("     score  = 该期内全部已完结自动匹配房、每场我方净分（零和 final_scores）之累加；")
        log("     firsts = 房首名次数（房内 4 家房级总分第一，按 user_id 聚合）。")
        log("   排序量因此是**期间累计总分**，不是每局均分；只有在房数相同的前提下两者才等价。")
        log("   功效分析按每局均分 Δ 表达，等价于按「同房数下的累计总分 Δ x 10R」表达。")
        log("")
        log("   口径陷阱（本仓实测）：官方明示「同一 4 人、座次逐场重洗」，所以房级四家总分")
        log("   必须按 user_id 聚合；按座位号聚合会把同一玩家算到不同列，房级名次/首名全错。")
    return


def sectional_stats(rooms, strata):
    """按分层输出分布与聚类区间。"""
    rule("3. 每局净分的房级分布（分层）")
    log("口径：每房 10 场、每场 8 局；「每局净分」= 官方 final_scores 里我方那一格。")
    log("聚类单位 = 房：sd_room 是房级每局均分的标准差，CR0 = sd_room / sqrt(房数)。")
    log("")
    log("%-22s%4s%5s%10s%22s%9s%9s%7s%9s"
        % ("分层", "房", "场", "均分/局", "95% CI (CR0)", "sd_room", "sd_game", "ICC", "设计效应"))
    rows = {}
    for name, sel in strata:
        rs = [r for _, r in rooms if sel(r)]
        if not rs:
            continue
        per_room = [[g["my_score"] for g in r["games"]] for r in rs]
        room_vals = [sum(v) / len(v) for v in per_room]
        st = cluster_stats(room_vals, per_room)
        st["boot"] = bootstrap_ci(room_vals)
        rows[name] = st
        log("%-22s%4d%5d%10.3f%22s%9.2f%9.2f%7.3f%9.2f"
            % (name, st["n_rooms"], st["n_games"], st["mean"],
               "[%+.2f, %+.2f]" % st["ci_cr0"], st["sd_room"], st["sd_game"],
               st["icc"], st["design_effect"]))
    log("")
    log("%-22s%8s%8s%8s%11s%11s%24s"
        % ("分层", "偏度", "最小局", "最大局", "最小房均", "最大房均", "bootstrap 95% CI"))
    for name, st in rows.items():
        log("%-22s%8.2f%8.0f%8.0f%11.2f%11.2f%24s"
            % (name, st["skew_game"], st["min_game"], st["max_game"],
               st["min_room"], st["max_room"], "[%+.2f, %+.2f]" % st["boot"]))
        log("%-22s%s" % ("", "房净分极值（10 场之和）：%+.0f / %+.0f"
                         % (st["min_room"] * GAMES_PER_ROOM, st["max_room"] * GAMES_PER_ROOM)))
    log("")
    log("备注：sd_room（房级每局均分 SD）是功效换算的唯一输入；ICC 是房内局间相关，")
    log("      设计效应 = 1+(k-1)*ICC，说明「按局独立」会低估多少标准误。")
    for name, st in rows.items():
        if st.get("icc_raw") is not None:
            log("      %s：ICC 原始值 %+.4f（%s）"
                % (name, st["icc_raw"],
                   "房内局间无正相关，按局独立不会低估标准误" if st["icc_raw"] <= 0
                   else "存在房内正相关，必须用房级区间"))
    return rows


def section_power(rows, cadence):
    rule("4. 功效曲线：检出「真实每局优势 Δ」需要多少房 / 多少小时")
    log("检验：单样本双侧 alpha=0.05、功效 80%，单位 = 房。")
    log("  z 近似：R = (z_{1-a/2} + z_0.80)^2 * sd_room^2 / Δ^2   （z 值 1.9600 / 0.8416）")
    log("  t 迭代：R <- (t_{R-1,1-a/2} + t_{R-1,0.80})^2 * sd_room^2 / Δ^2 （小样本校正）")
    log("  时间换算：R 房 x %.2f min/房 / 60 = 小时（单实例连续开房）" % cadence)
    log("")
    for label in ("v2（当前部署）", "campaign-b（SSE 战役）", "全部 R18 房"):
        st = rows.get(label)
        if not st:
            continue
        log("-- sd_room = %.2f（%s，%d 房）" % (st["sd_room"], label, st["n_rooms"]))
        log("%14s%10s%10s%10s%10s%10s"
            % ("目标Δ 分/局", "房(z)", "房(t)", "场(z)", "小时(z)", "小时(t)"))
        for delta in (0.5, 1.0, 2.0, 3.0, 4.0):
            need = required_rooms(delta, st["sd_room"])
            log("%14.1f%10d%10d%10d%10.1f%10.1f"
                % (delta, need["z"], need["t"], need["games_z"],
                   need["z"] * cadence / 60, need["t"] * cadence / 60))
        log("")
    return


def section_segments(rooms):
    rule("5. v1 / v2 分段刷新（当前全部可用房）")
    log("策略身份取自逐房 run manifest 的 policy_version（不取战役标签，避免同一战役跨代）。")
    log("")
    seg = []
    for name, sel in (("v1", lambda r: r["policy_version"] == R18_V1),
                      ("v2", lambda r: r["policy_version"] == R18_V2)):
        rs = [r for _, r in rooms if sel(r)]
        if not rs:
            continue
        per_room = [[g["my_score"] for g in r["games"]] for r in rs]
        room_vals = [sum(v) / len(v) for v in per_room]
        st = cluster_stats(room_vals, per_room)
        st["boot"] = bootstrap_ci(room_vals)
        st["first"] = min(r["finished_ms"] for r in rs)
        st["last"] = max(r["finished_ms"] for r in rs)
        seg.append((name, st))
    log("%-5s%4s%5s%8s%10s%9s%22s%22s"
        % ("代", "房", "场", "总分", "均分/局", "sd_room", "95% CI (CR0)", "bootstrap"))
    for name, st in seg:
        log("%-5s%4d%5d%8.0f%10.3f%9.2f%22s%22s"
            % (name, st["n_rooms"], st["n_games"], st["total"], st["mean"], st["sd_room"],
               "[%+.2f, %+.2f]" % st["ci_cr0"], "[%+.2f, %+.2f]" % st["boot"]))
    for name, st in seg:
        log("  %s 时间窗：%s -> %s" % (name, ms_to_bj(st["first"]), ms_to_bj(st["last"])))
    v2 = dict(seg).get("v2")
    if v2:
        lo, hi = v2["ci_cr0"]
        log("")
        log("=> v2 每局均分 %+.3f，95%% CI [%+.2f, %+.2f]（房级 CR0）、[%+.2f, %+.2f]（房级 bootstrap）"
            % (v2["mean"], lo, hi, v2["boot"][0], v2["boot"][1]))
        log("   CI %s含 0 => %s"
            % ("" if lo <= 0 <= hi else "不", "仍与 0 不可区分" if lo <= 0 <= hi else "已可与 0 区分"))
    log("")
    log("边界（必须与上表一起引用）：v1 与 v2 跑在不同日期、不同时段、不同对手池上，")
    log("且 v2 期还叠加了 SSE 接线修复（跨局首弃牌 1/14 -> 0/112）。两代之差不是因果增益，")
    log("只能作为「当前部署代的水平读数」。要判因果必须在同一时间块内随机交错两代（按房聚类）。")
    return seg


def section_conclusion(rows, seg, cadence):
    rule("6. 工程结论")
    base = rows.get("v2（当前部署）") or rows.get("全部 R18 房")
    if not base:
        log("数据不足，无法给出结论。")
        return
    need05 = required_rooms(0.5, base["sd_room"])
    need1 = required_rooms(1.0, base["sd_room"])
    need2 = required_rooms(2.0, base["sd_room"])
    have = base["n_rooms"]
    log("基准：sd_room = %.2f（%d 房），已积累 %d 房。" % (base["sd_room"], have, have))
    log("目标 Δ 分/局 -> 需要房数（t 迭代）/ 小时（单实例）：")
    for delta, need in ((0.5, need05), (1.0, need1), (2.0, need2)):
        log("  %+.1f 分/局 -> %5d 房 ≈ %6.1f 小时；还差 %5d 房 ≈ %6.1f 小时"
            % (delta, need["t"], need["t"] * cadence / 60,
               max(0, need["t"] - have), max(0, need["t"] - have) * cadence / 60))
    log("")
    log("=> 一句话：在 v2 当前的房间波动（sd_room = %.2f，均分 %+.3f）下，"
        % (base["sd_room"], base["mean"]))
    log("   要「稳定证明我方在自由赛有优势」，按 +1.0 分/局的目标还需约 %d 房 ≈ %.0f 小时"
        % (max(0, need1["t"] - have), max(0, need1["t"] - have) * cadence / 60))
    log("   （累计 %d 房 ≈ %.0f 小时）；若真实效应只有 +0.5 分/局，需 %d 房 ≈ %.0f 小时，"
        % (need1["t"], need1["t"] * cadence / 60, need05["t"], need05["t"] * cadence / 60))
    log("   不建议走自由赛通道，应改走同墙四座轮转的配对完整桌。")


def main(argv=None):
    ap = argparse.ArgumentParser(description="自由赛统计功效与积累计划（只读复算）")
    ap.add_argument("--me", default=ME)
    ap.add_argument("--reps", type=int, default=20000, help="房级 bootstrap 次数")
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--json", default=None, help="把关键结果写成 JSON（可选，默认不写文件）")
    args = ap.parse_args(argv)

    me = args.me

    room_scores = os.path.join(ROOT, "review/freematch-deep-dive-20260925/room-scores.json")
    ledger_path = os.path.join(ROOT, "runs/auto-match-watchdog/auto-match-watchdog-state.json")

    log("自由赛统计功效与积累计划（只读复算）")
    log("运行时刻（北京）：%s" % datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"))
    log("我方身份：%s；聚类单位：房；随机种子：%d" % (me, args.seed))

    payloads = load_game_payloads()
    meta = load_run_meta()
    rooms = collect_rooms(payloads, meta, me=me)
    ledger = None
    if os.path.exists(ledger_path):
        with open(ledger_path) as fh:
            ledger = json.load(fh)

    section_rooms(rooms, meta, room_scores, me=me)
    cadence, dur_mean, dur_med = section_cadence(rooms, ledger)
    section_leaderboard(
        rooms, os.path.join(ROOT, "datasets/leaderboard/snapshots/*/leaderboard-*.json"))

    strata = [
        ("全部 R18 房", lambda r: r["policy_version"] in (R18_V1, R18_V2)),
        ("v1", lambda r: r["policy_version"] == R18_V1),
        ("v2（当前部署）", lambda r: r["policy_version"] == R18_V2),
        ("campaign-b（SSE 战役）", lambda r: r["session_tag"] == CAMPAIGN_B),
    ]
    rows = sectional_stats(rooms, strata)
    for name, sel in strata:
        rs = [r for _, r in rooms if sel(r)]
        if rs:
            vals = [r["net"] / r["n_games"] for r in rs]
            rows[name]["boot"] = bootstrap_ci(vals, reps=args.reps, seed=args.seed)
    section_power(rows, cadence)
    seg = section_segments(rooms)
    section_conclusion(rows, seg, cadence)

    if args.json:
        out = {
            "generated_at": datetime.datetime.now(TZ).isoformat(),
            "me": me,
            "cadence_min_per_room": cadence,
            "room_duration_min_mean": dur_mean,
            "room_duration_min_median": dur_med,
            "strata": rows,
            "segments": {k: v for k, v in seg},
        }
        with open(args.json, "w") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
        log("（已写出 %s）" % args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
