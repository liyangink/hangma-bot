"""汇总"等待可观测性"字段：跨局发现查询是否被饿死、队列构成与发前撤销。

为什么需要
----------
2026-09-25 的根因分析（同目录 ROOT-CAUSE-2026-09-25.md）发现，M=10 单 Token
自由赛里本人跨局首弃牌查询**连续 7.58 秒一次都没获准**，但既有审计只记录
已获准请求（`http_request` 的 `phase=started`），无法判定这条查询究竟是
"已入队但被反复撤销"还是"从未入队"。

本次修复补了两类只读观测，本脚本把它们汇总成可判定的指标：

1. `request_timing["state_queue_at_grant"]`：获准瞬间的等待者构成
   （总数、按优先级、按类别、就绪 state 数、未撤销预约数、窗口内已用额度）。
2. `AUTHORITATIVE_STATE` 审计行 `state_wait_outcome="cancelled_before_send"`：
   未发送即被撤销的等待，含 `query_purpose`、`scheduler_priority`、
   `waited_sec`、`had_reservation` 与当时队列构成。

判据
----
- `sse_settled_long_poll` 的 `cancelled_before_send` 次数与 `waited_sec` 分布，
  是"跨局发现查询有没有再被饿死"的直接证据；
- `state_queue_at_grant.waiters_total` 与 `state_used_in_window` 是容量水位；
- 与 M=10 基线对照即可判断 M=16 是否仍在可接受范围。

输入：测试房/自由赛审计根（含 `slot-*/runs/*/participants/*/decisions.jsonl`）。
输出：文本报告 + 可选 JSON 汇总。

用法::

    python summarize_wait_observability.py <audit_root> [--json-out <路径>]

本脚本只读审计，不访问网络、不导入 hangma_bot、不写输入文件。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/wiring-queue-rootcause-2026-09-25'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def _percentiles(values: list[float], ps=(50, 90, 99)) -> dict:
    """返回百分位字典；空输入返回全 None，避免把"没有观测"写成 0。"""

    if not values:
        return {("p%d" % p): None for p in ps} | {"max": None, "n": 0}
    ordered = sorted(values)

    def pick(p: float):
        index = min(len(ordered) - 1, max(0, int(round(p / 100.0 * (len(ordered) - 1)))))
        return ordered[index]

    out = {("p%d" % p): pick(p) for p in ps}
    out["max"] = ordered[-1]
    out["n"] = len(ordered)
    return out


# 两种审计布局都要支持：四席测试房是 slot-*/runs/...，单 Token 自由赛没有
# slot 层（runs/...），用参与者目录名代替，避免自由赛被统计成"零席位"。
_LAYOUTS = ("slot-*/runs/*/participants/*/decisions.jsonl",
            "runs/*/participants/*/decisions.jsonl")


def iter_audit_files(audit_root: Path):
    """产出 (slot, 路径)；两种布局去重，同一文件不会被算两次。"""

    seen: set[Path] = set()
    for pattern in _LAYOUTS:
        for path in sorted(audit_root.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            parts = path.relative_to(audit_root).parts
            slot = parts[0] if parts and parts[0].startswith("slot-") else (
                parts[-2] if len(parts) >= 2 else "unknown")
            yield slot, path


def iter_records(audit_root: Path):
    """逐条产出 (slot, 记录)；槽位名取自路径，便于按身份聚合。"""

    for slot, path in iter_audit_files(audit_root):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    yield slot, json.loads(line)
                except ValueError:
                    continue


def summarize(audit_root: Path) -> dict:
    slots: dict[str, dict] = defaultdict(lambda: {
        "state_requests": 0,
        "by_purpose": Counter(),
        "queue_wait_ms": [],
        "http_429": 0,
        "cancelled_before_send": Counter(),
        "cancelled_wait_sec": [],
        "cancelled_wait_sec_by_purpose": defaultdict(list),
        "cancelled_with_reservation": 0,
        "queue_at_grant_waiters": [],
        "queue_at_grant_state_used": [],
        "queue_at_grant_ready_state": [],
        "decisions": 0,
        "rounds": set(),
    })
    for slot, record in iter_records(audit_root):
        bucket = slots[slot]
        kind = record.get("kind")
        payload = record.get("payload") or {}
        if kind == "http_request":
            endpoint = payload.get("endpoint") or ""
            if payload.get("phase") != "started" or not endpoint.endswith("/state"):
                if payload.get("phase") == "finished" and payload.get("http_status") == 429:
                    bucket["http_429"] += 1
                continue
            timing = payload.get("request_timing") or {}
            bucket["state_requests"] += 1
            purpose = timing.get("query_purpose") or "(unknown)"
            bucket["by_purpose"][purpose] += 1
            queued, granted = timing.get("queued_at_monotonic"), timing.get("granted_at_monotonic")
            if queued is not None and granted is not None:
                bucket["queue_wait_ms"].append((granted - queued) * 1000.0)
            queue = timing.get("state_queue_at_grant")
            if isinstance(queue, dict):
                if isinstance(queue.get("waiters_total"), int):
                    bucket["queue_at_grant_waiters"].append(queue["waiters_total"])
                if isinstance(queue.get("state_used_in_window"), int):
                    bucket["queue_at_grant_state_used"].append(queue["state_used_in_window"])
                if isinstance(queue.get("ready_state"), int):
                    bucket["queue_at_grant_ready_state"].append(queue["ready_state"])
        elif kind == "authoritative_state":
            if payload.get("state_wait_outcome") == "cancelled_before_send":
                purpose = payload.get("query_purpose") or "(unknown)"
                bucket["cancelled_before_send"][purpose] += 1
                waited = payload.get("waited_sec")
                if isinstance(waited, (int, float)):
                    bucket["cancelled_wait_sec"].append(float(waited))
                    bucket["cancelled_wait_sec_by_purpose"][purpose].append(float(waited))
                if payload.get("had_reservation"):
                    bucket["cancelled_with_reservation"] += 1
        elif kind == "decision_input":
            bucket["decisions"] += 1
            context = record.get("context") or {}
            if context.get("game_id") and context.get("round_no") is not None:
                bucket["rounds"].add((context["game_id"], context["round_no"]))

    result = {"audit_root": str(audit_root), "slots": {}}
    totals = {
        "state_requests": 0, "http_429": 0, "decisions": 0,
        "cancelled_before_send": Counter(), "rounds": set(),
    }
    for slot, bucket in sorted(slots.items()):
        rounds = len(bucket["rounds"])
        result["slots"][slot] = {
            "state_requests": bucket["state_requests"],
            "by_purpose": dict(bucket["by_purpose"]),
            "queue_wait_ms": _percentiles(bucket["queue_wait_ms"]),
            "http_429": bucket["http_429"],
            "cancelled_before_send": dict(bucket["cancelled_before_send"]),
            "cancelled_wait_sec": _percentiles(bucket["cancelled_wait_sec"]),
            "cancelled_wait_sec_by_purpose": {
                purpose: _percentiles(values)
                for purpose, values in sorted(bucket["cancelled_wait_sec_by_purpose"].items())
            },
            "cancelled_with_reservation": bucket["cancelled_with_reservation"],
            "queue_at_grant_waiters": _percentiles([float(v) for v in bucket["queue_at_grant_waiters"]]),
            "queue_at_grant_state_used": _percentiles([float(v) for v in bucket["queue_at_grant_state_used"]]),
            "queue_at_grant_ready_state": _percentiles([float(v) for v in bucket["queue_at_grant_ready_state"]]),
            "decisions": bucket["decisions"],
            "game_rounds": rounds,
            "state_per_decision": (round(bucket["state_requests"] / bucket["decisions"], 3)
                                   if bucket["decisions"] else None),
            "state_per_round": (round(bucket["state_requests"] / rounds, 1) if rounds else None),
        }
        totals["state_requests"] += bucket["state_requests"]
        totals["http_429"] += bucket["http_429"]
        totals["decisions"] += bucket["decisions"]
        totals["cancelled_before_send"] += bucket["cancelled_before_send"]
        totals["rounds"] |= bucket["rounds"]
    result["totals"] = {
        "slots": len(slots),
        "state_requests": totals["state_requests"],
        "http_429": totals["http_429"],
        "decisions": totals["decisions"],
        "game_rounds": len(totals["rounds"]),
        "cancelled_before_send": dict(totals["cancelled_before_send"]),
        "state_per_decision": (round(totals["state_requests"] / totals["decisions"], 3)
                               if totals["decisions"] else None),
        "state_per_round": (round(totals["state_requests"] / len(totals["rounds"]), 1)
                            if totals["rounds"] else None),
    }
    return result


def render(summary: dict) -> str:
    lines = ["审计根: " + summary["audit_root"], ""]
    for slot, row in summary["slots"].items():
        lines.append("== %s ==" % slot)
        lines.append("  state 查询 %d  决策 %d  单局组 %d  state/决策 %s  state/单局 %s"
                     % (row["state_requests"], row["decisions"], row["game_rounds"],
                        row["state_per_decision"], row["state_per_round"]))
        wait = row["queue_wait_ms"]
        lines.append("  排队 ms: p50 %s  p90 %s  p99 %s  max %s" %
                     (wait["p50"], wait["p90"], wait["p99"], wait["max"]))
        lines.append("  GET 429: %d" % row["http_429"])
        cancelled = row["cancelled_before_send"]
        lines.append("  发前撤销: 合计 %d  %s" % (sum(cancelled.values()), cancelled or "{}"))
        for purpose, stats in row["cancelled_wait_sec_by_purpose"].items():
            lines.append("    %-26s n=%d  等待秒 p50 %s p90 %s max %s"
                         % (purpose, stats["n"], stats["p50"], stats["p90"], stats["max"]))
        q = row["queue_at_grant_waiters"]
        lines.append("  获准时等待者数: p50 %s p90 %s max %s" % (q["p50"], q["p90"], q["max"]))
        used = row["queue_at_grant_state_used"]
        lines.append("  获准时窗口已用额度: p50 %s max %s" % (used["p50"], used["max"]))
    totals = summary["totals"]
    lines.append("")
    lines.append("== 合计 ==")
    lines.append("  席位 %d  state 查询 %d  决策 %d  单局组 %d" %
                 (totals["slots"], totals["state_requests"], totals["decisions"], totals["game_rounds"]))
    lines.append("  state/决策 %s  state/单局 %s  GET 429 %d" %
                 (totals["state_per_decision"], totals["state_per_round"], totals["http_429"]))
    lines.append("  发前撤销: %s" % (totals["cancelled_before_send"] or "{}"))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="汇总状态查询等待可观测性")
    parser.add_argument("audit_root", help="审计根（含 slot-*/runs/*/participants/*/decisions.jsonl）")
    parser.add_argument("--json-out", default=None, help="可选：机器可读汇总输出路径")
    args = parser.parse_args(argv)
    root = Path(args.audit_root)
    if not root.is_dir():
        raise SystemExit("审计根不存在: " + str(root))
    summary = summarize(root)
    print(render(summary))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
