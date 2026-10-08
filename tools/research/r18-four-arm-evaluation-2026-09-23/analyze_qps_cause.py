"""只读拆解 M=10 测试房每身份的状态查询需求、链式放大和短时拥堵。

输入为完整桌审计根目录。输出仅含聚合量及截断的桌号，不输出报文、手牌或凭据。
时间统一使用本机单调秒；滚动窗口只描述已观察请求，不等于服务端计数器。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

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
from collections import Counter, defaultdict, deque
from pathlib import Path


WINDOW_SEC = 1.05


def read_rows(path: Path):
    with path.open() as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1,
                                     int(len(ordered) * fraction + .999999) - 1))], 3)


def rolling_counts(times: list[float]) -> list[int]:
    pending: deque[float] = deque()
    result = []
    for now in sorted(times):
        while pending and pending[0] <= now - WINDOW_SEC:
            pending.popleft()
        pending.append(now)
        result.append(len(pending))
    return result


def close_increment_to_snapshot_chains(rows: list[dict]) -> dict[str, int]:
    """统计同桌增量之后 500 毫秒内紧接全量的两笔请求链。"""

    by_game: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_game[row["game"]].append(row)
    chains: Counter[str] = Counter()
    for game_rows in by_game.values():
        ordered = sorted(game_rows, key=lambda row: row["queued"])
        for before, after in zip(ordered, ordered[1:]):
            if (not before["seq0"] and after["seq0"]
                    and after["queued"] - before["queued"] < 0.5):
                chains[before["purpose"] + "→" + after["purpose"]] += 1
    return dict(chains)


def summarize_seat(run: Path) -> dict:
    raw_paths = sorted((run / "participants").glob("*/raw/*.jsonl"))
    records = []
    physical_events = set()
    per_game_first_last: dict[str, list[float]] = {}
    reasons = Counter()
    pacing = Counter()
    pacing_wait_sec = []
    for path in sorted((run / "participants").glob("*/games/*.jsonl")):
        for row in read_rows(path):
            payload = row.get("payload") or {}
            reason = payload.get("snapshot_refresh_reason")
            if reason:
                reasons[reason] += 1
            status = payload.get("discard_pacing_status")
            if status in ("completed", "skipped"):
                pacing[(status, payload.get("reason") or "unknown")] += 1
                if status == "completed":
                    pacing_wait_sec.append(float(payload.get("waited_sec") or 0))
    for path in raw_paths:
        for row in read_rows(path):
            payload = row.get("payload") or {}
            endpoint = str(payload.get("endpoint") or "")
            if not endpoint.endswith("/state") or "/games/" not in endpoint:
                continue
            timing = payload.get("request_timing") or {}
            queued = timing.get("queued_at_monotonic")
            started = timing.get("transport_started_at_monotonic")
            completed = timing.get("completed_at_monotonic")
            if not isinstance(queued, (int, float)) or not isinstance(started, (int, float)):
                continue
            game = endpoint.rsplit("/games/", 1)[1].rsplit("/state", 1)[0]
            game_bounds = per_game_first_last.setdefault(game, [started, started])
            game_bounds[0] = min(game_bounds[0], started)
            game_bounds[1] = max(game_bounds[1], completed or started)
            response = {}
            if payload.get("http_status") == 200:
                try:
                    response = json.loads(payload.get("raw") or "{}")
                except (TypeError, json.JSONDecodeError):
                    pass
            events = response.get("events") or []
            for event in events:
                if isinstance(event, dict) and isinstance(event.get("seq"), int):
                    physical_events.add((game, event["seq"], event.get("type")))
            records.append({
                "game": game, "queued": queued, "granted": timing.get("granted_at_monotonic"),
                "started": started, "completed": completed,
                "status": payload.get("http_status"),
                "seq0": payload.get("seq_requested") == 0,
                "purpose": timing.get("query_purpose") or "unknown",
                "priority": timing.get("scheduler_priority") or "unknown",
                "events": [e.get("type") for e in events if isinstance(e, dict)],
                "snapshot_phase": (response.get("snapshot") or {}).get("phase"),
                "pending": bool(response.get("pending")),
            })
    records.sort(key=lambda item: item["queued"])
    if not records:
        return {}
    first = min(item["started"] for item in records)
    last = max(item["completed"] or item["started"] for item in records)
    duration = last - first
    discards = sum(event[2] == "tile_discarded" for event in physical_events)
    event_types = Counter(event[2] for event in physical_events)
    category = Counter()
    queue_ms = []
    short_network_ms = []
    long_network_ms = []
    for item in records:
        if item["seq0"]:
            category["full_snapshot_get"] += 1
        elif item["purpose"] == "response_progress":
            category["response_progress_get"] += 1
        else:
            category["incremental_get"] += 1
        if item["granted"] is not None:
            queue_ms.append(1000 * (item["granted"] - item["queued"]))
        if item["completed"] is not None:
            network = 1000 * (item["completed"] - item["started"])
            (short_network_ms if item["seq0"] else long_network_ms).append(network)
    arrivals = rolling_counts([item["queued"] for item in records])
    sends = rolling_counts([item["started"] for item in records])
    max_arrival = max(arrivals)
    # 同峰值秒按最早请求定位，仅保留业务类别、桌号和相对时间。
    peak_at = records[arrivals.index(max_arrival)]["queued"]
    peak_rows = [r for r in records if peak_at - WINDOW_SEC < r["queued"] <= peak_at]
    peak = {
        "at_sec_from_first": round(peak_at - first, 3),
        "queued_get": len(peak_rows),
        "distinct_games": len({r["game"] for r in peak_rows}),
        "full_snapshot_get": sum(r["seq0"] for r in peak_rows),
        "response_progress_get": sum(r["purpose"] == "response_progress" for r in peak_rows),
        "by_priority": dict(Counter(r["priority"] for r in peak_rows)),
        "by_purpose": dict(Counter(r["purpose"] for r in peak_rows)),
        "same_game_extra_get": len(peak_rows) - len({r["game"] for r in peak_rows}),
        "increment_to_snapshot_under_500ms": close_increment_to_snapshot_chains(peak_rows),
        "frame_get_with_events": sum(r["purpose"] == "sse_frame" and bool(r["events"])
                                     for r in peak_rows),
        "frame_get_without_events": sum(r["purpose"] == "sse_frame" and not r["events"]
                                        for r in peak_rows),
        "frame_get_response_patterns": dict(Counter(
            "+".join(r["events"]) if r["events"] else "empty"
            for r in peak_rows if r["purpose"] == "sse_frame")),
        "snapshot_phases": dict(Counter(
            r["snapshot_phase"] or "unknown"
            for r in peak_rows if r["seq0"])),
        "by_game_get": dict(sorted(Counter(r["game"].rsplit("_", 2)[-2]
                                            for r in peak_rows).items())),
    }
    steady = [(item, count) for item, count in zip(records, arrivals)
              if first + 30 <= item["queued"] <= last - 30]
    steady_peak = max((count for _, count in steady), default=None)
    steady_rows = []
    if steady_peak is not None:
        at = next(item["queued"] for item, count in steady if count == steady_peak)
        steady_rows = [r for r in records if at - WINDOW_SEC < r["queued"] <= at]
    discard_slack = []
    for path in (run / "participants").glob("*/decisions.jsonl"):
        for row in read_rows(path):
            if row.get("kind") != "submission_intent":
                continue
            payload = row.get("payload") or {}
            if not str(payload.get("action_key") or "").startswith("discard:"):
                continue
            latest = payload.get("latest_send_at_monotonic")
            stamp = row.get("monotonic_ns")
            if isinstance(latest, (int, float)) and isinstance(stamp, int):
                discard_slack.append(latest - stamp / 1e9)
    active_table_sec = sum(max(0, bounds[1] - bounds[0])
                           for bounds in per_game_first_last.values())
    return {
        "games": len(per_game_first_last),
        "elapsed_sec": round(duration, 1),
        "active_table_sec": round(active_table_sec, 1),
        "gets": len(records), "gets_per_sec": round(len(records) / duration, 2),
        "gets_per_discard": round(len(records) / discards, 3) if discards else None,
        "observed_discards": discards,
        "discards_per_active_table_min": round(60 * discards / active_table_sec, 2),
        "event_types": dict(event_types),
        "get_categories": dict(category),
        "status": dict(Counter(str(r["status"]) for r in records)),
        "snapshot_reasons": dict(reasons),
        "increment_to_snapshot_under_500ms": close_increment_to_snapshot_chains(records),
        "discard_pacing": {
            "outcomes": {f"{status}:{reason}": count
                         for (status, reason), count in sorted(pacing.items())},
            "completed_wait_sec": round(sum(pacing_wait_sec), 2),
            "completed_wait_p50_sec": quantile(pacing_wait_sec, .5),
        },
        "discard_intent_slack": {
            "count": len(discard_slack), "p10_sec": quantile(discard_slack, .1),
            "p50_sec": quantile(discard_slack, .5),
            "at_least_1_15_sec": sum(value >= 1.15 for value in discard_slack),
        },
        "queue_ms": {"p50": quantile(queue_ms, .5), "p95": quantile(queue_ms, .95),
                     "p99": quantile(queue_ms, .99),
                     "over_500ms": sum(x > 500 for x in queue_ms),
                     "over_1000ms": sum(x > 1000 for x in queue_ms)},
        "short_network_ms": {"p50": quantile(short_network_ms, .5),
                             "p95": quantile(short_network_ms, .95)},
        "incremental_network_ms": {"p50": quantile(long_network_ms, .5),
                                   "p95": quantile(long_network_ms, .95)},
        "queued_in_1_05s": {"p50": quantile(arrivals, .5),
                            "p95": quantile(arrivals, .95),
                            "max": max_arrival,
                            "requests_arriving_above_16": sum(n > 16 for n in arrivals)},
        "sent_in_1_05s": {"p50": quantile(sends, .5),
                          "p95": quantile(sends, .95), "max": max(sends)},
        "peak_arrival": peak,
        "steady_peak_arrival": {
            "queued_get": steady_peak,
            "distinct_games": len({row["game"] for row in steady_rows}),
            "full_snapshot_get": sum(row["seq0"] for row in steady_rows),
            "response_progress_get": sum(row["purpose"] == "response_progress"
                                         for row in steady_rows),
            "at_sec_from_first": round(steady_rows[-1]["queued"] - first, 3)
            if steady_rows else None,
        },
    }


def latest_runs(root: Path) -> dict[str, Path]:
    """每身份按修改时间取最后一次运行，避免旧失败运行的字典键覆盖完整运行。"""
    result = {}
    for slot in sorted(root.glob("slot-*")):
        runs = [run for run in (slot / "runs").glob("run-*") if run.is_dir()]
        if runs:
            result[slot.name] = max(runs, key=lambda run: (run.stat().st_mtime_ns, run.name))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {}
    for root in args.roots:
        report[root.parent.name] = {
            slot: summarize_seat(run) for slot, run in latest_runs(root).items()
        }
    result = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(result)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
