#!/usr/bin/env python3
"""自由赛战况细查（只读，无网络请求，无副作用）。

输出当前进行中的整场比赛（自动房 = 10 场×8 局）的明细：
已开几场、完赛几场、每场当前比分（进行中为场内快照，不作数）、
已完赛小计、账本历史累计。数据全部来自本机审计目录与盯盘账本。

固定指令（盯盘 agent 用它回答用户"现在打得怎么样"）：
    bash /Users/liyang/Projects/Opensource/hangma-bot/scripts/auto_match_status.sh
"""

import glob
import json
import os
import re
import subprocess
import sys

ME = "u_13495c3d79c8"
PGREP = "run_auto_match.py --config"
LEDGER = os.path.join("runs", "auto-match-watchdog", "auto-match-watchdog-state.json")


def _repo_root():
    cur = os.path.dirname(os.path.abspath(__file__))
    while cur != os.path.dirname(cur):
        if os.path.isfile(os.path.join(cur, "pyproject.toml")):
            return cur
        cur = os.path.dirname(cur)
    raise SystemExit("未找到仓库根")


ROOT = _repo_root()
os.chdir(ROOT)


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def alive():
    return sh("pgrep -f '%s'" % PGREP).returncode == 0


def latest_log():
    logs = sorted(glob.glob(os.path.join(ROOT, "runs", "auto-match-watchdog", "session-*.log")),
                  key=os.path.getmtime)
    return logs[-1] if logs else None


def audit_dir_of(log_path):
    for line in open(log_path, encoding="utf-8", errors="replace"):
        m = re.search(r"审计目录: (\S+)", line)
        if m:
            p = m.group(1)
            return p if os.path.isabs(p) else os.path.join(ROOT, p)
    return None


def read_ledger():
    try:
        return json.load(open(LEDGER, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def game_states(audit_dir):
    """返回 {game_id: {finished, final_scores, seat, round_no, snapshot, phase}}。"""
    games = {}
    for f in sorted(glob.glob(os.path.join(audit_dir, "participants", "*", "games", "*.jsonl"))):
        gid = os.path.basename(f)[:-6]
        st = games.setdefault(gid, {"finished": False, "final_scores": None,
                                    "seat": None, "round_no": None,
                                    "snapshot": None, "phase": None})
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") == "game_finished":
                fs = (r.get("payload") or {}).get("final_scores")
                if isinstance(fs, list):
                    st["finished"] = True
                    st["final_scores"] = fs
    dec = os.path.join(audit_dir, "participants", ME, "decisions.jsonl")
    alt = glob.glob(os.path.join(audit_dir, "participants", "*", "decisions.jsonl"))
    for path in ([dec] if os.path.isfile(dec) else alt):
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") != "decision_input":
                continue
            req = ((r.get("payload") or {}).get("request") or {})
            obs = req.get("observation") or {}
            gid = obs.get("game_id")
            if gid not in games:
                continue
            st = games[gid]
            st["seat"] = obs.get("seat", st["seat"])
            st["round_no"] = obs.get("round_no", st["round_no"])
            st["snapshot"] = obs.get("scores", st["snapshot"])
            st["phase"] = (req.get("window_key") or {}).get("phase", st["phase"])
    return games


def fmt_vec(v):
    return "[" + ",".join("%+d" % x for x in v) + "]" if isinstance(v, list) else "?"


def main():
    print("== 自由赛战况（%s） ==" % time_str())
    ledger = read_ledger()
    log = latest_log()
    audit = audit_dir_of(log) if log else None
    if alive():
        print("会话进程：存活")
    else:
        print("会话进程：未运行（结算与续开请运行 auto_match_watch.sh）")
    if not audit or not os.path.isdir(audit):
        if ledger:
            print("无进行中房间。账本：累计 %d，%d 房，最近一房 %s（%+d）"
                  % (ledger.get("cumulative_total", 0), len(ledger.get("rooms", [])),
                     ledger["rooms"][-1]["room_id"], ledger["rooms"][-1]["room_subtotal"]))
        else:
            print("无进行中房间，无账本。")
        return 0

    games = game_states(audit)
    if not games:
        print("审计目录已建立但尚未开赛：%s" % audit)
        return 0
    room = next(iter(games)).rsplit("_r1_", 1)[0]
    finished = [g for g in games.values() if g["finished"]]
    running = [g for g in games.values() if not g["finished"]]
    print("房间：%s ｜ 场次：%d ｜ 已完赛：%d ｜ 进行中：%d"
          % (room, len(games), len(finished), len(running)))

    subtotal = 0
    if finished:
        print("-- 已完赛（终局分，作数） --")
        for gid in sorted(games):
            st = games[gid]
            if not st["finished"]:
                continue
            seat = st["seat"] if st["seat"] is not None else -1
            fs = st["final_scores"] or []
            mine = fs[seat] if 0 <= seat < len(fs) else None
            if mine is not None:
                subtotal += mine
            print("  %s  我方 %+s  四座 %s" % (short(gid), ("%d" % mine) if mine is not None else "?", fmt_vec(fs)))
        print("  本房已完赛小计：%+d" % subtotal)

    snap_sum = 0
    if running:
        print("-- 进行中（场内快照，不作数） --")
        for gid in sorted(games):
            st = games[gid]
            if st["finished"]:
                continue
            seat = st["seat"]
            snap = st["snapshot"] or []
            mine = snap[seat] if seat is not None and seat < len(snap) else None
            if isinstance(mine, (int, float)):
                snap_sum += mine
            print("  %s  第 %s/8 局  当前 %+s  快照 %s"
                  % (short(gid), st["round_no"] if st["round_no"] is not None else "?",
                     ("%d" % mine) if mine is not None else "?", fmt_vec(snap)))
        print("  本房进行中快照累计：%+d（不作数）" % snap_sum)
    if finished or running:
        print("本房当前合计：%+d（其中作数 %+d，快照不作数 %+d）"
              % (subtotal + snap_sum, subtotal, snap_sum))

    if ledger:
        print("账本历史累计：%+d（%d 房已结算） ｜ 含本房已完赛：%+d"
              % (ledger.get("cumulative_total", 0), len(ledger.get("rooms", [])),
                 ledger.get("cumulative_total", 0) + subtotal))
    if ledger and ledger.get("stopped"):
        print("（账本 stopped=true：本房结束后不再续开）")
    return 0


def time_str():
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S")


def short(gid):
    m = re.search(r"_r1_b(\d+)_t0$", gid)
    return "第%s场" % (int(m.group(1)) + 1) if m else gid


if __name__ == "__main__":
    sys.exit(main())
