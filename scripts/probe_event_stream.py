#!/usr/bin/env python3
# 事件流完整性探针（只读诊断工具，验证局专用）。
#
# 目的：用「严格游标纪律」实测官方 /state 事件流的覆盖面——
#   游标只在应用完事件或吸收快照水位后推进、永不跳跃；seq=0 仅用于
#   开局初始化与响应 gap:true。与现网 bot 的「每弃牌全量刷新」模式
#   （游标跳跃导致事件被跳过，实测只看到 19% 事件）形成对照。
#
# 部署方式：与正常 4 身份 bot **共用同一个 Token** 并行运行——探针只发
#   GET /api/me 与 GET /state（动作与生命周期全部由 bot 进程负责），
#   额外请求 ~1-2/s，在官方 16/s/用户额度内。两个进程同一 Token 仅
#   允许这种「一写多读」形态，禁止探针提交任何动作。
#
# 输出：runs/probe/<时间戳>/<game_id>.jsonl（逐响应留痕）+ 控制台与
#   SUMMARY 的覆盖率/词表/静默推进/时延分位/gap 位置统计。
# 运行：PYTHONPATH=src python3 scripts/probe_event_stream.py --token-file ...
# 依赖：仅 hangma_bot.adapters.official.transport（TLS 白名单/超时/认证复用）。

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig  # noqa: E402


def read_token(path):
    text = open(path, "r", encoding="utf-8").read().strip()
    try:
        doc = json.loads(text)
        if isinstance(doc, dict) and doc.get("token"):
            return str(doc["token"]).strip()
    except ValueError:
        pass
    return text


class GameProbe:
    """单场观察器：严格游标连续增量；记录一切响应。"""

    def __init__(self, transport, game_id, out_path, wall_ms):
        self._transport = transport
        self.game_id = game_id
        self._out = open(out_path, "a", encoding="utf-8")
        self.cursor = 0
        self.finished = False
        self.stats = {
            "game_id": game_id,
            "events_received": 0,
            "event_types": Counter(),
            "final_seq": 0,
            "silent_advances": 0,     # 无事件、无快照的游标前移
            "snapshot_absorptions": 0,  # 快照水位吸收（含其覆盖的未知事件）
            "gaps": [],               # (seq, wall_ms)
            "seq_skips": [],          # 事件不连续点（严格游标下应为空）
            "latencies_ms": [],       # 事件 ts(秒) → 响应到达墙钟
            "snap_with_events": 0,    # 快照与事件同响应出现（形态证据）
            "draw_own_with_tile": 0,
            "draw_own_without_tile": 0,
            "draw_other": 0,
            "round_ended": 0,
            "polls": 0,
            "errors": 0,
        }
        self._start_wall = wall_ms

    def _log(self, kind, payload):
        rec = {"wall_ms": int(time.time() * 1000), "kind": kind, "cursor": self.cursor}
        rec.update(payload)
        self._out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._out.flush()

    async def run(self):
        self._log("probe_start", {"game_id": self.game_id})
        while not self.finished:
            try:
                res = await self._transport.request(
                    "GET", "/api/games/{}/state".format(self.game_id),
                    params={"seq": self.cursor}, long_poll=True,
                )
                body = json.loads(res.text or "{}")
            except Exception as exc:  # 诊断工具：错误记录后退避重试
                self.stats["errors"] += 1
                self._log("poll_error", {"error": str(exc)[:160]})
                await asyncio.sleep(0.5)
                continue
            self.stats["polls"] += 1
            self._consume(body)
            await asyncio.sleep(0)
        self.stats["final_seq"] = self.cursor
        self._log("probe_end", {"final_seq": self.cursor})
        self._out.close()

    def _consume(self, body):
        wall = int(time.time() * 1000)
        seq = body.get("seq")
        gap = bool(body.get("gap"))
        pending = bool(body.get("pending"))
        snap = body.get("snapshot") or {}
        events = body.get("events") or []
        self._log("response", {
            "body_seq": seq, "gap": gap, "pending": pending,
            "snapshot": bool(snap), "events": [
                {"seq": e.get("seq"), "type": e.get("type"), "seat": e.get("seat"),
                 "tile": e.get("tile"), "ts": e.get("ts")} for e in events],
        })
        if body.get("finished") or snap.get("phase") == "finished":
            self.finished = True
        if gap:
            self.stats["gaps"].append([seq, wall])
            self.cursor = 0  # 官方语义：gap → seq=0 重建
            return
        if pending:
            return
        if snap:
            self.stats["snapshot_absorptions"] += 1
            if events:
                self.stats["snap_with_events"] += 1
        applied = 0
        for ev in events:
            eseq = ev.get("seq")
            if eseq is None:
                continue
            if eseq != self.cursor + 1:
                self.stats["seq_skips"].append([self.cursor, eseq])
            self.cursor = eseq
            applied += 1
            self.stats["events_received"] += 1
            self.stats["event_types"][ev.get("type")] += 1
            if ev.get("ts"):
                self.stats["latencies_ms"].append(wall - int(ev["ts"]) * 1000)
            if ev.get("type") == "tile_drawn":
                if ev.get("tile"):
                    self.stats["draw_own_with_tile"] += 1
                else:
                    self.stats["draw_other"] += 1
            if ev.get("type") == "round_ended":
                self.stats["round_ended"] += 1
        # 快照在场 → 水位吸收（覆盖 <=seq 的一切，含未逐条送达的事件）；
        # 无快照而水位高于游标 → 静默推进记录（严格游标下的关键观测指标）
        if snap and isinstance(seq, int) and seq > self.cursor:
            self.cursor = seq
        elif not snap and isinstance(seq, int) and seq > self.cursor:
            self.stats["silent_advances"] += seq - self.cursor
            self.cursor = seq


def percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * q))]


async def discover_and_observe(args, transport, out_dir):
    """轮询 /api/me 发现 active_games；为新场次启动观察器；全部结束后汇总。"""
    observers = {}
    token_hint = "probe"
    last_active_wall = int(time.time() * 1000)
    deadline = time.time() + args.duration_sec
    while time.time() < deadline:
        try:
            res = await transport.request("GET", "/api/me")
            me = json.loads(res.text or "{}")
            games = [g.get("game_id") for g in (me.get("active_games") or []) if g.get("game_id")]
        except Exception as exc:
            print("me_error:", str(exc)[:120], flush=True)
            games = []
        for gid in games:
            if gid and gid not in observers:
                path = os.path.join(out_dir, gid + ".jsonl")
                probe = GameProbe(transport, gid, path, int(time.time() * 1000))
                observers[gid] = asyncio.ensure_future(probe.run())
                print("observing", gid, flush=True)
        if games:
            last_active_wall = int(time.time() * 1000)
        done_ids = [gid for gid, t in observers.items() if t.done()]
        if done_ids and not games:
            idle_ms = int(time.time() * 1000) - last_active_wall
            if idle_ms > args.idle_exit_sec * 1000:
                break
        await asyncio.sleep(2.0)
    for task in observers.values():
        if not task.done():
            task.cancel()
    await asyncio.gather(*observers.values(), return_exceptions=True)
    return observers


async def main_async(args):
    token = read_token(args.token_file)
    config = TransportConfig(base_url=args.base_url, insecure_hosts=frozenset(args.insecure_hosts))
    transport = OfficialTransport(token, config)
    out_dir = os.path.join(args.out_dir, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    observers = await discover_and_observe(args, transport, out_dir)
    # 汇总：重新读取每场 jsonl 末尾的 probe 统计由内存对象不可得（task 已结束），
    # 改为从各场 jsonl 重算关键指标，保证 SUMMARY 与留痕一致。
    summary = {"out_dir": out_dir, "games": []}
    for path in sorted(glob_game_files(out_dir)):
        gid = os.path.basename(path)[:-6]
        stats = summarize_file(path)
        stats["game_id"] = gid
        summary["games"].append(stats)
        ev, fin = stats.get("events_received", 0), stats.get("final_seq", 0)
        absorbed = stats.get("snapshot_absorptions", 0)
        print("[{}] events={} final_seq={} silent={} gaps={} round_ended={} skips={}".format(
            gid, ev, fin, stats.get("silent_advances", 0), len(stats.get("gaps", [])),
            stats.get("round_ended", 0), len(stats.get("seq_skips", []))), flush=True)
    with open(os.path.join(out_dir, "SUMMARY.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print("SUMMARY ->", os.path.join(out_dir, "SUMMARY.json"), flush=True)
    await transport.aclose()


def glob_game_files(out_dir):
    return [os.path.join(out_dir, f) for f in sorted(os.listdir(out_dir)) if f.endswith(".jsonl")]


def summarize_file(path):
    """从逐响应留痕重算统计（与 GameProbe.stats 同口径）。"""
    stats = {"event_types": {}, "latencies_ms": [], "gaps": [], "seq_skips": []}
    events = 0
    final_seq = 0
    silent = 0
    absorptions = 0
    snap_with_events = 0
    draw_tile = draw_empty_other = round_ended = 0
    types = Counter()
    lat = []
    rec = {"cursor": 0}
    for line in open(path, "r", encoding="utf-8"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("kind") != "response":
            continue
        final_seq = rec.get("cursor", final_seq)
        if rec.get("gap"):
            stats["gaps"].append([rec.get("body_seq"), rec.get("wall_ms")])
            continue
        evs = rec.get("events") or []
        for e in evs:
            events += 1
            types[e.get("type")] += 1
            if e.get("ts"):
                lat.append(rec.get("wall_ms", 0) - int(e["ts"]) * 1000)
            if e.get("type") == "tile_drawn":
                if e.get("tile"):
                    draw_tile += 1
                else:
                    draw_empty_other += 1
            if e.get("type") == "round_ended":
                round_ended += 1
        if rec.get("snapshot"):
            absorptions += 1
            if evs:
                snap_with_events += 1
    lat.sort()
    stats.update({
        "events_received": events,
        "final_seq": final_seq or rec.get("cursor", 0),
        "event_types": dict(types),
        "snapshot_absorptions": absorptions,
        "snap_with_events": snap_with_events,
        "draw_own_with_tile": draw_tile,
        "draw_other_or_empty": draw_empty_other,
        "round_ended": round_ended,
        "latency_ms_p50": percentile(lat, 0.5),
        "latency_ms_p90": percentile(lat, 0.9),
        "latency_ms_p99": percentile(lat, 0.99),
        # 简单覆盖率：收到的事件数 / 最终游标（分母含开局快照吸收段，属保守低估）
        "coverage_hint": round(events / final_seq, 3) if final_seq else None,
    })
    stats["seq_skips"] = stats["seq_skips"][:20]
    stats["gaps"] = stats["gaps"][:40]
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description="事件流完整性探针（只读，与 bot 共用 Token）")
    parser.add_argument("--token-file", required=True, help="Token 文件（原始串或含 token 字段的 JSON）")
    parser.add_argument("--base-url", default="https://10.240.169.190:18080")
    parser.add_argument("--insecure-host", action="append", default=["10.240.169.190"],
                        help="允许关闭 TLS 校验的官方内网主机（默认测试平台）")
    parser.add_argument("--out-dir", default="runs/probe")
    parser.add_argument("--duration-sec", type=int, default=3600, help="最长观察秒数")
    parser.add_argument("--idle-exit-sec", type=int, default=120,
                        help="active_games 清空且观察器全部结束后再等待的秒数")
    args = parser.parse_args(argv)
    asyncio.run(main_async(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
