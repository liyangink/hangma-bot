#!/usr/bin/env python3
"""参赛运行监控（人工值守用；只显示告警，不自动重启）。

用法：
  # 自动发现 audit_root 下最新的 run 目录并持续监控
  .venv/bin/python scripts/monitor_run.py --audit-root runs

  # 监控指定 run 目录（单身份入口的输出目录）
  .venv/bin/python scripts/monitor_run.py --run-dir runs/run-xxxx

  # 同时盯进程存活（可选；不给则按 run 目录审计判断）
  .venv/bin/python scripts/monitor_run.py --audit-root runs --pid 12345

判据（与集成阶段值守预案一致）：
  [ALARM] 停摆     状态=running 且 审计流 >60s 无新记录
  [ALARM] 未到位   状态=stage_open 且 >90s 无 ready 事件
  [WARN]  409风暴  INVALID_ACTION 占比 >30%（自愈型，先观察）
  [WARN]  预算饿死 SubmitNotSent 累计数明显增长（M>1 饥饿信号）
  [DEAD]  进程退出 pid 不存在时告警
处置建议：出现 ALARM 时，SIGTERM 该进程后用原命令重启（register/ready 幂等，
  代价仅丢在途窗口，服务端代打，不犯规）。
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


# ---- 可按需调整的阈值（秒 / 次数）----
STALL_SECONDS = 60        # running 状态下审计流无新记录的告警阈值
READY_SECONDS = 90        # stage_open 后未见 ready 的告警阈值
IDLE_QUIET_OK = 600       # 非运行态（registering/stage_done 等）安静多久才提示
CODE_RATE_WARN = 0.30     # INVALID_ACTION 占比告警线

TERMINAL_STATUSES = {"finished", "closed", "void"}


def _newest_run_dir(audit_root: Path) -> Path | None:
    candidates = sorted(
        (p for p in audit_root.glob("runs/*") if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
    )
    # 支持房间编排目录结构 runs/slot-X/runs/run-Y：向下再探一层
    if not candidates:
        nested = sorted(
            (p for p in audit_root.glob("*/runs/*") if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
        )
        candidates = nested
    return candidates[-1] if candidates else None


def _iter_jsonl(path: Path):
    """逐行读取 JSONL 记录；raw/ 的 gzip 分段（*.jsonl.gz）透明解压。

    损坏/截断文件（如进程被杀未写 gzip 尾部的段）按整文件容错跳过，
    监控只看活跃度，最终完整性由离线验证器把关。
    """

    try:
        if path.name.endswith(".jsonl.gz"):
            handle = gzip.open(
                path, "rt", encoding="utf-8", errors="replace", newline="\n"
            )
        else:
            handle = path.open("r", encoding="utf-8", errors="replace")
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except (OSError, EOFError):
        # EOFError：截断的 gzip 段在读取尾部抛出（不是 OSError 子类），一并容错
        return


def _collect(run_dir: Path):
    """读取 run 目录的当前状态摘要；全部容错，文件缺失返回部分信息。"""

    info = {
        "status": None,
        "status_at": None,
        "ready_seen": False,
        "stage_open_at": None,
        "outcomes": {},
        "intent_count": 0,
        "max_seq": -1,
        "last_record_at": None,  # 墙钟秒（取自审计 wall_time_unix_ms）
        "last_file_mtime": 0.0,
        "games": set(),
        "participant": None,
        "terminal_reason": None,
    }
    files = [run_dir / "lifecycle.jsonl"]
    files += sorted((run_dir / "participants").glob("*/decisions.jsonl"))
    if (run_dir / "participants").exists():
        files += sorted((run_dir / "participants").glob("*/games/*.jsonl"))
        # 原始协议事件（RAW_PROTOCOL_STATE）按场落在 raw/<game>.jsonl，
        # 可 gzip 分段（*.NNNNN.jsonl.gz）。打牌间歇只有 /state 轮询原文
        # 在写，漏扫 raw/ 会把运行误判为"审计停摆"（d6 返工登记项）：
        # raw 文件的写入时间与记录墙钟一并计入活跃度统计。
        files += sorted((run_dir / "participants").glob("*/raw/*.jsonl"))
        files += sorted((run_dir / "participants").glob("*/raw/*.jsonl.gz"))
    for path in files:
        if not path.exists():
            continue
        info["last_file_mtime"] = max(info["last_file_mtime"], path.stat().st_mtime)
        for rec in _iter_jsonl(path):
            ts = rec.get("wall_time_unix_ms")
            if ts:
                info["last_record_at"] = max(info["last_record_at"] or 0, ts / 1000.0)
            p = rec.get("payload", {})
            kind = rec.get("kind")
            if kind == "lifecycle_changed":
                ev = p.get("event")
                if ev == "status_changed":
                    info["status"] = p.get("to")
                    info["status_at"] = ts / 1000.0 if ts else None
                elif ev == "ready":
                    info["ready_seen"] = True
                elif ev == "stage_attempt_voided":
                    info["stage_open_at"] = ts / 1000.0 if ts else info["stage_open_at"]
                # stage_open 出现时刻：status 变化即近似
                if info["status"] == "stage_open" and info["status_at"]:
                    info["stage_open_at"] = info["status_at"]
                if ev == "participant_finished" or kind == "participant_finished":
                    info["terminal_reason"] = p.get("reason")
            elif kind == "submission_intent":
                info["intent_count"] += 1
            elif kind == "submission_outcome":
                out = p.get("outcome") or "?"
                info["outcomes"][out] = info["outcomes"].get(out, 0) + 1
            elif kind == "authoritative_state":
                seq = p.get("seq")
                if isinstance(seq, int):
                    info["max_seq"] = max(info["max_seq"], seq)
                gid = (p.get("window") or {}).get("game_id")
                if gid:
                    info["games"].add(gid)
            ctx = rec.get("context", {})
            if ctx.get("participant_id") and ctx["participant_id"] != "unknown":
                info["participant"] = ctx["participant_id"]
    return info


def _pid_alive(pid: int | None) -> bool | None:
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _fmt_outcomes(outcomes: dict) -> str:
    if not outcomes:
        return "-"
    total = sum(outcomes.values())
    invalid = outcomes.get("SubmitRejectedRetryable", 0)
    rate = invalid / total if total else 0.0
    flag = " ⚠409风暴" if rate > CODE_RATE_WARN and total >= 10 else ""
    notsent = outcomes.get("SubmitNotSent", 0)
    ns = f" ⚠not_sent={notsent}" if notsent else ""
    return f"accepted={outcomes.get('SubmitAccepted', 0)} retry={invalid} nosent={notsent}{flag}{ns}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="杭麻 Bot 参赛运行监控（人工值守）")
    ap.add_argument("--audit-root", type=Path, help="审计根目录（自动发现最新 run）")
    ap.add_argument("--run-dir", type=Path, help="直接指定 run 目录")
    ap.add_argument("--pid", type=int, default=None, help="可选：监控进程存活")
    ap.add_argument("--interval", type=float, default=5.0, help="刷新间隔秒（默认 5）")
    ap.add_argument("--once", action="store_true", help="打印一次快照后退出（快速检查用）")
    args = ap.parse_args(argv)

    run_dir = args.run_dir
    if run_dir is None:
        if args.audit_root is None:
            ap.error("需要 --run-dir 或 --audit-root 之一")
        run_dir = _newest_run_dir(args.audit_root)
        if run_dir is None:
            print(f"[monitor] {args.audit_root} 下未发现 run 目录", file=sys.stderr)
            return 2
    run_dir = run_dir.resolve()
    print(f"[monitor] 监控目录: {run_dir}（Ctrl-C 退出；重启处置=SIGTERM 后原命令重跑）")

    last_intent = None
    last_notified_stall = 0.0
    try:
        while True:
            info = _collect(run_dir)
            now = time.time()
            status = info["status"] or "未知"
            last_rec = info["last_record_at"] or info["last_file_mtime"] or now
            stale = now - last_rec
            alarms = []

            alive = _pid_alive(args.pid)
            if alive is False:
                alarms.append("[DEAD] 进程已退出")

            if status == "running" and stale > STALL_SECONDS:
                alarms.append(f"[ALARM] 停摆：running 状态下审计 {stale:.0f}s 无新记录 → 建议 SIGTERM+重启")
            if status == "stage_open" and not info["ready_seen"]:
                so = info["stage_open_at"] or 0
                if so and now - so > READY_SECONDS:
                    alarms.append(f"[ALARM] stage_open {now - so:.0f}s 未见 ready → 建议重启（幂等重确认）")
            if status in ("registering", "stage_done") and stale > IDLE_QUIET_OK:
                alarms.append(f"[INFO] {status} 已安静 {stale:.0f}s（阶段空窗可能合法，结合官方后台判断）")
            if info["terminal_reason"]:
                alarms.append(f"[DONE] 参赛者终态: {info['terminal_reason']}")

            intent_delta = ""
            if last_intent is not None and info["intent_count"] != last_intent:
                intent_delta = f" (+{info['intent_count'] - last_intent})"
            last_intent = info["intent_count"]

            verdict = "局势正常"
            if any(a.startswith("[ALARM]") or a.startswith("[DEAD]") for a in alarms):
                verdict = "!! 需要处置（见下）"
            elif any(a.startswith("[WARN]") for a in alarms):
                verdict = "~ 需注意"
            print(f"== {verdict} ==", flush=True) if args.once else None

            line = (
                f"{time.strftime('%H:%M:%S')} 状态={status} 身份={info['participant'] or '?'} "
                f"场次={len(info['games'])} seq≤{info['max_seq']} 提交={info['intent_count']}{intent_delta} "
                f"{_fmt_outcomes(info['outcomes'])} 审计停滞={stale:.0f}s"
            )
            print(line, flush=True)
            # 告警限频：同一停摆每 30s 重复提醒一次足够
            for a in alarms:
                if a.startswith("[ALARM]") and now - last_notified_stall < 30:
                    continue
                print(f"  {a}", flush=True)
                if a.startswith("[ALARM]"):
                    last_notified_stall = now
            if info["terminal_reason"]:
                print("[monitor] 已到终态，监控退出")
                return 0
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[monitor] 退出")
        return 0


if __name__ == "__main__":
    sys.exit(main())
