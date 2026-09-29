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
import hashlib
import json
import os
import re
import shlex
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
STOP_FLOOR = -1500       # 累计 < -1500 → 止损（2026-09-10 用户确认：取消连败限制，只看累计分）
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
    # 一次会话出现多个房号时无法安全把终局归到单一房间，交给人工核对。
    return next(iter(ids)) if len(ids) == 1 and all(
        re.fullmatch(r"[A-Za-z0-9_-]+", room) for room in ids) else None


def audit_outcomes(audit_dir):
    """审计终局与本人座位；同 game_id 的后写终局覆盖重复记录。

    ``game_finished`` 只有四座分数，不带本人座位；座位从同一场的权威
    ``authoritative_state.payload.window.seat`` 读取。这样官方下载缺一个批次
    时，已完整落盘的审计场次仍能正确结算，不能被下载表的键集合静默丢掉。
    """
    outcomes = {}
    for f in glob.glob(os.path.join(audit_dir, "participants", ME, "games", "*.jsonl")):
        gid = os.path.basename(f)[:-6]
        seat = None
        final_scores = None
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") == "authoritative_state":
                observed = ((rec.get("payload") or {}).get("window") or {}).get("seat")
                if type(observed) is int and 0 <= observed < 4:
                    if seat is not None and seat != observed:
                        raise ValueError("同一场审计出现冲突座位：%s" % gid)
                    seat = observed
            if rec.get("kind") == "game_finished":
                fs = (rec.get("payload") or {}).get("final_scores")
                if isinstance(fs, list) and len(fs) == 4:
                    final_scores = fs
        if final_scores is not None:
            outcomes[gid] = {"seat": seat, "final_scores": final_scores}
    return outcomes


def audit_finals(audit_dir):
    """兼容进度统计：返回 ``{game_id: 四座终局分}``。"""

    return {gid: row["final_scores"] for gid, row in audit_outcomes(audit_dir).items()}


def provisional_audit_games(audit_dir, room_id):
    """只保留已取得本人座位及终局分的完整场次，不从未完牌谱推算分数。"""
    games = []
    for gid, outcome in sorted(audit_outcomes(audit_dir).items()):
        if not gid.startswith(room_id + "_r1_"):
            continue
        seat = outcome["seat"]
        scores = outcome["final_scores"]
        if type(seat) is int and 0 <= seat < 4 and all(type(s) is int for s in scores):
            games.append({"game_id": gid, "seat": seat,
                          "final_score": scores[seat], "source": "audit"})
    return games


def _declared_batches():
    """从运行配置读自动房场次数（declared_max_games），决定要下载的批次范围。"""
    cfg = json.load(open(RUNTIME_CONFIG, encoding="utf-8"))
    return int(cfg.get("auto_match", {}).get("declared_max_games", 10))


def _downloaded_batches(session_dir, room_id):
    """返回该房已完整下载的批次号；坏或无批次来源不冒充完成。"""
    batches = set()
    for src in glob.glob(os.path.join(session_dir, "official", "dl-*", "source.json")):
        try:
            source = json.load(open(src, encoding="utf-8"))
            batch = source.get("batch")
            if source.get("room_id") == room_id and type(batch) is int and batch >= 0:
                batches.add(batch)
        except (OSError, json.JSONDecodeError):
            continue
    return batches


def download(room_id, session_dir, *, max_attempts=2, max_elapsed_sec=None):
    """经 audit_tool collect-test-room 按批次下载官方牌谱到会话 official/。

    不再调用已废弃的 runs/download_auto_match.py 私有脚本；免认证采集、
    限速与失败证据隔离统一由标准入口负责。失败 30 秒后整房重试一次。
    返回会话目录（official/dl-*/events.json 供结算核对）或 None。
    """
    batches = _declared_batches()
    expected = set(range(batches))
    deadline = time.monotonic() + max_elapsed_sec if max_elapsed_sec is not None else None
    if expected.issubset(_downloaded_batches(session_dir, room_id)):
        return session_dir
    for attempt in range(1, max_attempts + 1):
        for batch in range(batches):
            if deadline is not None and time.monotonic() >= deadline:
                print("!! 牌谱下载超出时间预算，本房停止自动恢复")
                return None
            if batch in _downloaded_batches(session_dir, room_id):
                continue
            args = [".venv/bin/python3", "scripts/audit_tool.py", "collect-test-room",
                    "--runtime-config", RUNTIME_CONFIG, "--room", room_id,
                    "--batch", str(batch), "--out", session_dir]
            r = sh(" ".join(shlex.quote(arg) for arg in args), cwd=ROOT)
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip()[-200:]
                print("批次 %d 下载失败：%s" % (batch, tail))
                break
        if expected.issubset(_downloaded_batches(session_dir, room_id)):
            return session_dir
        if attempt < max_attempts:
            print("牌谱下载失败，30 秒后重试一次…")
            time.sleep(30)
    print("!! 牌谱缺失：%s 下载未补齐，本房仅按审计可结算场次记账" % room_id)
    return None


def _four_scores(value, label):
    """验证官方积分按座位 0—3 给出四个整数；布尔值不可冒充积分。"""
    if not isinstance(value, list) or len(value) != 4 or any(type(n) is not int for n in value):
        raise ValueError(label + "_invalid")
    if sum(value) != 0:
        raise ValueError(label + "_not_zero_sum")
    return value


def verified_official_room(session_dir, room_id, audit_dir):
    """验证同房十桌八局和桌末四座积分；只返回可直接入账的本人分数。"""
    batches = {}
    for source_path in glob.glob(os.path.join(session_dir, "official", "dl-*", "source.json")):
        source = json.load(open(source_path, encoding="utf-8"))
        if source.get("room_id") != room_id:
            continue
        batch = source.get("batch")
        if type(batch) is not int or batch not in range(10):
            raise ValueError("batch_invalid")
        events_path = os.path.join(os.path.dirname(source_path), "events.json")
        raw = open(events_path, "rb").read()
        if hashlib.sha256(raw).hexdigest() != source.get("original_sha256"):
            raise ValueError("source_digest_mismatch")
        doc = json.loads(raw)
        game_id = "%s_r1_b%d_t0" % (room_id, batch)
        if (doc.get("room_id") != room_id or type(doc.get("batch")) is not int or
                doc.get("batch") != batch or
                doc.get("game_id") != game_id or source.get("game_id") != game_id or
                doc.get("status") != "finished"):
            raise ValueError("official_identity_or_status_mismatch")
        seats = [s.get("user_id") for s in doc.get("seats", []) if isinstance(s, dict)]
        if (len(seats) != 4 or len(set(seats)) != 4 or
                any(not isinstance(s, str) or not s for s in seats) or
                seats.count(ME) != 1):
            raise ValueError("official_seat_identity_invalid")
        # 顶层 rounds 摘要在实房可缺项；以 blocks 的八个 round_ended 为准，
        # 再与 game_ended 四座总分对账，不能因摘要缺项丢弃完整事件事实。
        blocks = doc.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise ValueError("official_blocks_missing")
        endings, game_endings = {}, []
        for block in blocks:
            if not isinstance(block, dict) or type(block.get("round_no")) is not int:
                raise ValueError("official_block_invalid")
            for event in block.get("events", []):
                if not isinstance(event, dict):
                    raise ValueError("official_event_invalid")
                if event.get("type") == "round_ended":
                    no = block["round_no"]
                    if no in endings or no not in range(1, 9):
                        raise ValueError("official_round_end_duplicate_or_extra")
                    data = event.get("data") or {}
                    if type(data.get("round_no")) is not int or data.get("round_no") != no:
                        raise ValueError("official_round_end_number_mismatch")
                    scores = _four_scores(data.get("scores"), "round_end")
                    endings[no] = scores
                elif event.get("type") == "game_ended":
                    game_endings.append(event)
        if set(endings) != set(range(1, 9)) or len(game_endings) != 1:
            raise ValueError("official_terminal_events_incomplete")
        totals = [sum(endings[no][seat] for no in range(1, 9)) for seat in range(4)]
        ended = _four_scores((game_endings[0].get("data") or {}).get("final_scores"),
                             "game_end")
        if totals != ended:
            raise ValueError("official_game_total_mismatch")
        seat = seats.index(ME)
        row = {"game_id": game_id, "seat": seat, "final_score": totals[seat],
               "source": "official_recovered_round_ended"}
        if batch in batches and batches[batch][0] != hashlib.sha256(raw).hexdigest():
            raise ValueError("official_duplicate_batch_conflict")
        batches[batch] = (hashlib.sha256(raw).hexdigest(), row, totals)
    if set(batches) != set(range(10)):
        raise ValueError("official_ten_batches_incomplete")
    rows = [batches[batch][1] for batch in range(10)]
    for game_id, outcome in audit_outcomes(audit_dir).items():
        match = next((batch for batch in batches.values() if batch[1]["game_id"] == game_id), None)
        if match is None or outcome["final_scores"] != match[2] or outcome["seat"] != match[1]["seat"]:
            raise ValueError("official_audit_conflict")
    return rows


def official_table(dest, room_id=None):
    """官方牌谱 → {gid: (seat, 逐局求和终局分)}；room_id 给定时只统计该房。

    本战役所有会话共用同一 audit_root，官方下载也累积在同一 official/，
    不按房过滤会把历史房的场次重复计入本房结算（2026-09-09 实测踩坑）。
    """
    table = {}
    if not dest:
        return table
    for f in glob.glob(os.path.join(dest, "official", "dl-*", "events.json")):
        d = json.load(open(f, encoding="utf-8"))
        if room_id and d.get("room_id") != room_id:
            continue
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
    table = official_table(dest, room_id)
    outcomes = audit_outcomes(audit_dir)
    games, subtotal = [], 0
    for gid in sorted(set(table) | set(outcomes)):
        seat, dl_total = table.get(gid, (None, None))
        outcome = outcomes.get(gid)
        audit_seat = outcome and outcome.get("seat")
        if seat is not None and audit_seat is not None and seat != audit_seat:
            raise ValueError("审计与官方下载的本人座位冲突：%s" % gid)
        effective_seat = seat if seat is not None else audit_seat
        if outcome is not None and effective_seat is not None:
            mine, src = outcome["final_scores"][effective_seat], "audit"
        elif dl_total is not None:
            mine, src = dl_total, "official_download补全"
        else:
            print("!! %s 审计与牌谱均无终局分，该场不计（结果缺失）" % gid)
            continue
        subtotal += mine
        games.append({"game_id": gid, "seat": effective_seat, "final_score": mine, "source": src})
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


def reconcile_ledger(ledger):
    """用已落盘审计补齐历史房漏场，并重算累计；不删除既有场次。

    watchdog 旧版把 ``table or finals`` 当作场次集合，官方下载只要非空就会
    吞掉审计独有的终局。这里在每次持锁巡检开头复核已经入账的房：同场
    座位/分数冲突直接失败，只有审计给出确定座位与四座终局分时才补记。
    """
    repairs = []
    for room in ledger.get("rooms", []):
        audit_rel = room.get("audit_dir")
        if not isinstance(audit_rel, str) or not audit_rel:
            continue
        audit_dir = audit_rel if os.path.isabs(audit_rel) else os.path.join(ROOT, audit_rel)
        if not os.path.isdir(audit_dir):
            continue
        existing = {game.get("game_id"): game for game in room.get("games", [])}
        added = []
        for gid, outcome in sorted(audit_outcomes(audit_dir).items()):
            seat = outcome.get("seat")
            scores = outcome.get("final_scores")
            if type(seat) is not int or not 0 <= seat < 4 or not isinstance(scores, list):
                continue
            score = scores[seat]
            if gid in existing:
                prior = existing[gid]
                if prior.get("seat") != seat or prior.get("final_score") != score:
                    raise ValueError("账本与审计终局冲突：%s" % gid)
                continue
            row = {"game_id": gid, "seat": seat, "final_score": score,
                   "source": "audit_reconciled"}
            room.setdefault("games", []).append(row)
            existing[gid] = row
            added.append(gid)
        if added:
            room["games"].sort(key=lambda row: row["game_id"])
            before = room.get("room_subtotal")
            room["room_subtotal"] = sum(game["final_score"] for game in room["games"])
            repairs.append({"room_id": room.get("room_id"), "added_games": added,
                            "subtotal_before": before,
                            "subtotal_after": room["room_subtotal"]})
    if not repairs:
        return False
    ledger["cumulative_total"] = sum(
        room.get("room_subtotal", 0) for room in ledger.get("rooms", [])
    )
    streak = 0
    for room in reversed(ledger.get("rooms", [])):
        if room.get("room_subtotal", 0) < 0:
            streak += 1
        else:
            break
    ledger["current_lose_streak"] = streak
    ledger["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    ledger.setdefault("reconciliations", []).append({
        "at": ledger["updated_at"],
        "reason": "补齐审计已有但旧版下载键集合漏掉的终局场次",
        "repairs": repairs,
    })
    return True


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
    if reconcile_ledger(ledger):
        save_ledger(ledger)
        print("已按审计补齐历史漏场，累计重算为 %d" % ledger["cumulative_total"])
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

    # 幂等：已入账日志不可二次入账。matching_unavailable 不代表房间作废，
    # 其已有局可能计入官方周榜；此终态是永久停止原因，不能自动续开。
    rel_log = os.path.relpath(log, ROOT)
    accounted = next((room for room in ledger["rooms"]
                      if room.get("session_log") == rel_log), None)
    if accounted is not None:
        if accounted.get("terminal_reason") == "matching_unavailable":
            if accounted.get("settlement_status") != "official_recovered_complete":
                print("房间 %s 仍待官方结算核对；停止自动续开" % accounted.get("room_id"))
                return 3
            maybe_restart()
            return 0
        maybe_restart()
        return 0
    if any(row.get("session_log") == rel_log
           for row in ledger.get("unresolved_sessions", [])):
        print("最新会话仍无可确认房间结算；停止自动续开")
        return 3

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

    if reason == "matching_unavailable":
        # 该终态可由已有目标房 404 且缺 finished 证据产生；房间里的完整局
        # 仍可能已被官方计分。只在十桌八局牌谱及四座总分全部对齐后续开；
        # 否则保留审计已知分、粘滞停机，不把缺失场次记零分。
        room_id = room_id_of(audit_dir) if audit_dir and os.path.isdir(audit_dir) else None
        games = []
        already_accounted = any(room.get("room_id") == room_id
                                for room in ledger["rooms"]) if room_id else False
        if room_id:
            games = provisional_audit_games(audit_dir, room_id)
            if not already_accounted:
                try:
                    if _declared_batches() != 10:
                        raise ValueError("declared_games_not_ten")
                    session_dir = os.path.dirname(os.path.dirname(os.path.dirname(audit_dir)))
                    dest = download(room_id, session_dir, max_attempts=1,
                                    max_elapsed_sec=180)
                    if dest is None:
                        raise ValueError("official_download_incomplete")
                    complete = verified_official_room(dest, room_id, audit_dir)
                except Exception as exc:  # noqa: BLE001 - 未知/429/不完整均停机，不猜分
                    verification_issue = "%s:%s" % (type(exc).__name__, str(exc)[:100])
                else:
                    subtotal = sum(game["final_score"] for game in complete)
                    ledger["rooms"].append({
                        "room_id": room_id,
                        "session_log": rel_log,
                        "audit_dir": os.path.relpath(audit_dir, ROOT),
                        "download_dir": os.path.relpath(dest, ROOT),
                        "terminal_reason": reason,
                        "settlement_status": "official_recovered_complete",
                        "room_subtotal": subtotal,
                        "games": complete,
                    })
                    ledger["cumulative_total"] += subtotal
                    ledger["current_lose_streak"] = (ledger["current_lose_streak"] + 1
                                                     if subtotal < 0 else 0)
                    ledger["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                    if ledger["cumulative_total"] < STOP_FLOOR:
                        ledger["stopped"] = True
                        ledger["last_stop_reason"] = "score_stop_floor"
                    save_ledger(ledger)
                    print("第 %d 房 %s 官方追回完整十桌：%d，累计 %d" %
                          (len(ledger["rooms"]), room_id, subtotal, ledger["cumulative_total"]))
                    if not ledger.get("stopped"):
                        maybe_restart()
                    return 0
            if games and not already_accounted:
                subtotal = sum(game["final_score"] for game in games)
                ledger["rooms"].append({
                    "room_id": room_id,
                    "session_log": rel_log,
                    "audit_dir": os.path.relpath(audit_dir, ROOT),
                    "download_dir": None,
                    "terminal_reason": reason,
                    "settlement_status": "provisional",
                    "verification_issue": verification_issue,
                    "room_subtotal": subtotal,
                    "games": games,
                })
                ledger["cumulative_total"] += subtotal
        if not games or already_accounted:
            ledger.setdefault("unresolved_sessions", []).append({
                "session_log": rel_log,
                "audit_dir": os.path.relpath(audit_dir, ROOT) if audit_dir else None,
                "room_id": room_id,
                "terminal_reason": reason,
                "reason": "room_already_accounted" if already_accounted else "no_complete_game",
            })
        ledger["stopped"] = True
        ledger["last_stop_reason"] = reason
        ledger["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        save_ledger(ledger)
        print("!! matching_unavailable：房间 %s 已确认 %d 场、已知小计 %d；"
              "整房结果未获权威确认，停止自动续开" %
              (room_id or "未知", len(games), sum(g["final_score"] for g in games)))
        return 3

    if reason in ("tournament_void", "cancelled"):
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

    if ledger["cumulative_total"] < STOP_FLOOR:
        ledger["stopped"] = True
        save_ledger(ledger)
        print("第 %d 房 %s 结算：%d（%d胜%d负%d平），累计 %d。"
              % (len(ledger["rooms"]), room_id, subtotal, wins, losses, draws,
                 ledger["cumulative_total"]))
        print("=== 止损触发（累计破 %d），托管收工。恢复：账本 stopped 改 false 或删账本。===" % STOP_FLOOR)
        return 0
    save_ledger(ledger)
    print("第 %d 房 %s 结算：%d（%d胜%d负%d平），累计 %d，连败 %d 房"
          % (len(ledger["rooms"]), room_id, subtotal, wins, losses, draws,
             ledger["cumulative_total"], ledger["current_lose_streak"]))
    maybe_restart()
    return 0


if __name__ == "__main__":
    sys.exit(main())
