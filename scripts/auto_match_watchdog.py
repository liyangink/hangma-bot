#!/usr/bin/env python3
"""自由赛盯盘唯一入口（幂等，可被定时反复调用）。

一条命令覆盖完整生命周期：无会话则引导开第一房；会话存活只报进度；
会话退出则下载牌谱→结算→更新账本→止损判断→续开下一房。重复调用
安全：已结算的会话日志不会二次入账，止损后粘滞停止。

路径约定（2026-09-09）：审计落 artifacts/sessions/...（由
configs/auto-match.local.json 的 audit_root 决定）；官方牌谱经
scripts/audit_tool.py collect-test-room 下载进会话 official/；
账本、会话日志与文件锁等运行态放 runs/auto-match-watchdog/
（不入库、可清理；artifacts/ 只保存取证与制品）。

退出码：0 正常（含无事可做）；3 硬错误需人工介入（不重试）。
恢复止损后的战役：将账本 JSON 的 "stopped" 改回 false，或删账本重开。
""";

import fcntl
import glob
import json
import os
import re
import subprocess
import sys
import time


def _repo_root():
    """从脚本位置向上找到仓库根（含 pyproject.toml）；不依赖调用方 cwd。"""
    cur = os.path.dirname(os.path.abspath(__file__))
    while cur != os.path.dirname(cur):
        if os.path.isfile(os.path.join(cur, "pyproject.toml")):
            return cur
        cur = os.path.dirname(cur)
    raise SystemExit("未找到仓库根（pyproject.toml）")


ROOT = _repo_root()
# 运行态家目录：账本、会话日志、文件锁。放 runs/（gitignored、可随时清理），
# 与 artifacts/ 的取证语义分开——运行态数据不进制品区。
STATE = os.path.join(ROOT, "runs", "auto-match-watchdog")
RUNTIME_CONFIG = os.path.join(ROOT, "configs", "auto-match.local.json")
LEDGER = os.path.join(STATE, "auto-match-watchdog-state.json")
ME = "u_13495c3d79c8"
PGREP = "run_auto_match.py --config"
STOP_STREAK = 3          # 连续 3 房小计负分 → 止损
STOP_FLOOR = -1500       # 累计 < -1500 → 止损
HARD_ERRORS = {"authentication_failed", "incompatible_guide", "capacity_limit",
               "fatal_protocol_error"}


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def session_alive():
    return sh("pgrep -f '%s'" % PGREP).returncode == 0


def latest_session_log():
    logs = sorted(glob.glob(os.path.join(STATE, "session-*.log")), key=os.path.getmtime)
    return logs[-1] if logs else None


def audit_dir_of(log_path):
    # 审计目录行由 run_auto_match 打印；audit_root 迁入 artifacts 后路径不再固定，
    # 因此匹配任意非空白路径并相对仓库根拼接（绝对路径直接生效）。
    for line in open(log_path, encoding="utf-8", errors="replace"):
        m = re.search(r"审计目录: (\S+)", line)
        if m:
            return m.group(1) if os.path.isabs(m.group(1)) else os.path.join(ROOT, m.group(1))
    return None


def room_id_of(audit_dir):
    files = glob.glob(os.path.join(audit_dir, "participants", "*", "games", "*.jsonl"))
    ids = {os.path.basename(f).rsplit("_r1_", 1)[0] for f in files}
    ids.discard("unknown")
    return sorted(ids)[0] if ids else None


def audit_finals(audit_dir):
    """审计终局分：game_finished.final_scores，同 game_id 去重取后写。返回 {gid: [4分]}"""
    finals = {}
    for f in glob.glob(os.path.join(audit_dir, "participants", ME, "games", "*.jsonl")):
        gid = os.path.basename(f)[:-6]
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") == "game_finished":
                fs = (rec.get("payload") or {}).get("final_scores")
                if isinstance(fs, list):
                    finals[gid] = fs
    return finals


def _declared_batches():
    """从运行配置读自动房场次数（declared_max_games），决定要下载的批次范围。"""
    cfg = json.load(open(RUNTIME_CONFIG, encoding="utf-8"))
    return int(cfg.get("auto_match", {}).get("declared_max_games", 10))


def _room_downloaded(session_dir, room_id):
    """幂等判定：会话 official/ 已存在该房间任一批次的完整下载（source.json 匹配 room_id）。"""
    for src in glob.glob(os.path.join(session_dir, "official", "dl-*", "source.json")):
        try:
            if json.load(open(src, encoding="utf-8")).get("room_id") == room_id:
                return True
        except (OSError, json.JSONDecodeError):
            continue
    return False


def download(room_id, session_dir):
    """经 audit_tool collect-test-room 按批次下载官方牌谱到会话 official/。

    不再调用已废弃的 runs/download_auto_match.py 私有脚本；免认证采集、
    限速与失败证据隔离统一由标准入口负责。失败 30 秒后整房重试一次。
    返回会话目录（official/dl-*/events.json 供结算核对）或 None。
    """
    if _room_downloaded(session_dir, room_id):
        return session_dir
    batches = _declared_batches()
    for attempt in (1, 2):
        complete = True
        for batch in range(batches):
            r = sh(".venv/bin/python3 scripts/audit_tool.py collect-test-room "
                   "--runtime-config %s --room %s --batch %d --out %s" % (RUNTIME_CONFIG, room_id, batch, session_dir),
                   cwd=ROOT)
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip()[-200:]
                print("批次 %d 下载失败：%s" % (batch, tail))
                complete = False
                break
        if complete or _room_downloaded(session_dir, room_id):
            return session_dir
        if attempt == 1:
            print("牌谱下载失败，30 秒后重试一次…")
            time.sleep(30)
    print("!! 牌谱缺失：%s 两次下载均失败，本房仅按审计可结算场次记账" % room_id)
    return None


def official_table(dest):
    """官方牌谱 → {gid: (seat, 逐局求和终局分)}。"""
    table = {}
    if not dest:
        return table
    for f in glob.glob(os.path.join(dest, "official", "dl-*", "events.json")):
        d = json.load(open(f, encoding="utf-8"))
        seat = next((i for i, s in enumerate(d.get("seats", []))
                     if s.get("user_id") == ME), None)
        total = (sum(r["scores"][seat] for r in d["rounds"])
                 if seat is not None and d.get("rounds") else None)
        table[d["game_id"]] = (seat, total)
    return table


def settle(audit_dir, room_id):
    """结算一房：优先审计终局分，缺的用牌谱逐局求和补全。返回 (小计, games明细, 会话目录)。"""
    # audit_dir 形如 <session>/audit/runs/run-<id>；会话目录承接官方下载与赛后分析。
    session_dir = os.path.dirname(os.path.dirname(os.path.dirname(audit_dir)))
    dest = download(room_id, session_dir)
    table = official_table(dest)
    finals = audit_finals(audit_dir)
    games, subtotal = [], 0
    for gid in sorted(table or finals):
        seat, dl_total = table.get(gid, (None, None))
        if gid in finals and seat is not None and seat < len(finals[gid]):
            mine, src = finals[gid][seat], "audit"
        elif dl_total is not None:
            mine, src = dl_total, "official_download补全"
        else:
            print("!! %s 审计与牌谱均无终局分，该场不计（结果缺失）" % gid)
            continue
        subtotal += mine
        games.append({"game_id": gid, "seat": seat, "final_score": mine, "source": src})
    return subtotal, games, dest


def load_ledger():
    """加载账本；缺失时先尝试从旧战役会话迁移，再退回自动初始化。"""
    if not os.path.isfile(LEDGER):
        legacy = os.path.join(ROOT, "artifacts", "sessions", "auto-match-campaign-20260908",
                              "runtime", "auto-match-watchdog-state.json")
        os.makedirs(STATE, exist_ok=True)
        if os.path.isfile(legacy):
            import shutil
            shutil.copyfile(legacy, LEDGER)
        else:
            save_ledger({"cumulative_total": 0, "current_lose_streak": 0,
                         "rooms": [], "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    return json.load(open(LEDGER, encoding="utf-8"))


def save_ledger(s):
    json.dump(s, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def progress_line():
    """进程存活时的简报：最新会话的完赛数与本房快照小计（不作数，仅供参考）。"""
    log = latest_session_log()
    audit = audit_dir_of(log) if log else None
    if not audit or not os.path.isdir(audit):
        print("会话进程存活（审计目录尚未建立）")
        return
    finals = audit_finals(audit)
    print("会话进程存活：已完赛 %d/10 场（终局分以结算为准）" % len(finals))


def restart():
    os.makedirs(STATE, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    log = os.path.join(STATE, "session-%s.log" % ts)
    subprocess.Popen(
        ["nohup", ".venv/bin/python3", "scripts/run_auto_match.py",
         "--config", "configs/auto-match.local.json",
         "--token-file", "token/global/全局自由赛token"],
        cwd=ROOT, stdout=open(log, "w"), stderr=subprocess.STDOUT,
        start_new_session=True)
    time.sleep(40)
    if not session_alive():
        print("!! 续开失败：新会话 40 秒内未存活，日志 %s" % log)
        return None
    # 新会话可能还在匹配，房间号拿不到不算失败
    new_log = latest_session_log()
    audit = audit_dir_of(new_log) if new_log else None
    rid = room_id_of(audit) if audit else None
    print("已续开下一房：%s，日志 %s" % (rid or "（匹配中）", log))
    return rid


def maybe_restart():
    """按需续开：账本 stopped 或环境变量 WATCHDOG_NO_RESTART=1 时收工不续开。

    注意：stopped 只拦截"续开"，不拦截"结算"——已打完的房间仍会正常入账。
    """
    if os.environ.get("WATCHDOG_NO_RESTART") == "1":
        print("WATCHDOG_NO_RESTART=1：按指示本房结算后不再续开，托管收工")
        return None
    try:
        if json.load(open(LEDGER, encoding="utf-8")).get("stopped"):
            print("账本 stopped=true：本房结算后收工，不续开。恢复：改回 false 或删账本。")
            return None
    except (OSError, json.JSONDecodeError):
        pass
    return restart()


def main():
    # 文件锁：防止两次巡检并发看到"进程刚退出"而各开一房（双会话）
    os.makedirs(STATE, exist_ok=True)
    lock = open(os.path.join(STATE, ".auto-match-watchdog.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("已有一次巡检在执行，本次跳过")
        return 0
    try:
        return run_cycle()
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)


def run_cycle():
    ledger = load_ledger()
    if session_alive():
        progress_line()
        return 0

    log = latest_session_log()
    if not log:
        # 已收工且无会话记录：只报状态，不引导开房
        if ledger.get("stopped"):
            print("已收工（账本 stopped），累计 %d。恢复：改回 false 或删账本。"
                  % ledger["cumulative_total"])
            return 0
        # 无任何会话记录：引导启动第一房（expected_tournament_id 非 null 时拒绝）
        cfg = json.load(open(RUNTIME_CONFIG, encoding="utf-8"))
        if cfg.get("expected_tournament_id") is not None:
            print("!! expected_tournament_id 非 null，拒绝自动引导开房，请人工确认")
            return 3
        print("无会话记录：引导启动第一房")
        maybe_restart()
        return 0

    # 幂等：最新日志已结算过（续开失败/止损后重复巡检）→ 不二次入账，直接按需续开
    rel_log = os.path.relpath(log, ROOT)
    if ledger["rooms"] and ledger["rooms"][-1].get("session_log") == rel_log:
        maybe_restart()
        return 0

    last = open(log, encoding="utf-8", errors="replace").readlines()[-1].strip()
    m = re.match(r"RESULT (\{.*\})", last)
    if not m:
        print("!! 会话日志末行不是 RESULT：%s（会话异常中断，不猜结果）" % last[:120])
        return 3
    result = json.loads(m.group(1))
    reason = result.get("terminal_reason")
    audit_dir = result.get("audit_dir") and os.path.join(ROOT, result["audit_dir"])

    if reason in HARD_ERRORS:
        print("!! 硬错误终态 %s，按纪律不重试，请人工介入。日志 %s" % (reason, log))
        return 3

    if reason in ("tournament_void", "matching_unavailable", "cancelled"):
        print("本房无结算（%s），成绩不计入账本也不计入连败，直接重开。" % reason)
        cfg = json.load(open(RUNTIME_CONFIG, encoding="utf-8"))
        if cfg.get("expected_tournament_id") is not None:
            print("!! expected_tournament_id 非 null，按纪律不重开，请人工确认")
            return 3
        maybe_restart()
        return 0

    if reason not in ("tournament_finished", "tournament_closed"):
        print("!! 未知终态 %s，不自动处理，请人工确认。日志 %s" % (reason, log))
        return 3

    room_id = room_id_of(audit_dir) if audit_dir else None
    if not room_id:
        print("!! 无法从审计确定房间号，不结算不续开。审计目录 %s" % audit_dir)
        return 3
    subtotal, games, dest = settle(audit_dir, room_id)
    wins = sum(1 for g in games if g["final_score"] > 0)
    losses = sum(1 for g in games if g["final_score"] < 0)
    draws = len(games) - wins - losses

    ledger["cumulative_total"] += subtotal
    ledger["current_lose_streak"] = (ledger["current_lose_streak"] + 1
                                     if subtotal < 0 else 0)
    ledger["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    ledger["rooms"].append({
        "room_id": room_id,
        "session_log": rel_log,
        "audit_dir": os.path.relpath(audit_dir, ROOT),
        "download_dir": os.path.relpath(dest, ROOT) if dest else None,
        "terminal_reason": reason,
        "room_subtotal": subtotal,
        "games": games,
    })

    if ledger["current_lose_streak"] >= STOP_STREAK or ledger["cumulative_total"] < STOP_FLOOR:
        ledger["stopped"] = True
        save_ledger(ledger)
        why = "连败 3 房" if ledger["current_lose_streak"] >= STOP_STREAK else "累计破 -1500"
        print("第 %d 房 %s 结算：%d（%d胜%d负%d平），累计 %d。"
              % (len(ledger["rooms"]), room_id, subtotal, wins, losses, draws,
                 ledger["cumulative_total"]))
        print("=== 止损触发（%s），托管收工。恢复：账本 stopped 改 false 或删账本。===" % why)
        return 0
    save_ledger(ledger)
    print("第 %d 房 %s 结算：%d（%d胜%d负%d平），累计 %d，连败 %d 房"
          % (len(ledger["rooms"]), room_id, subtotal, wins, losses, draws,
             ledger["cumulative_total"], ledger["current_lose_streak"]))
    maybe_restart()
    return 0


if __name__ == "__main__":
    sys.exit(main())
