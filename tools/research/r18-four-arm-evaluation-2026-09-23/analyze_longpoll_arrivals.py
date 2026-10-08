"""区分长轮询等新事件与排队后追赶已发生事件；只读完整桌审计。"""

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
from collections import Counter, defaultdict
from pathlib import Path

from analyze_burst_origins import load_requests, select_windows


def _queue_band(wait_seconds: float) -> str:
    if wait_seconds < 0.1:
        return "queue_under_100ms"
    if wait_seconds < 0.5:
        return "queue_100_to_500ms"
    if wait_seconds < 1:
        return "queue_500_to_1000ms"
    return "queue_at_least_1000ms"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    values.sort()
    middle = len(values) // 2
    if len(values) % 2:
        return round(values[middle], 1)
    return round((values[middle - 1] + values[middle]) / 2, 1)


def analyze(audit_root: Path) -> dict:
    seats = {
        slot.name: load_requests(next(slot.glob("runs/*")))
        for slot in sorted(audit_root.glob("slot-*"))
    }
    first_seen: dict[tuple[str, int], float] = {}
    for requests in seats.values():
        for request in requests:
            completed = request["completed"]
            if completed is None:
                continue
            for seq in request["event_seqs"]:
                key = (request["game"], seq)
                first_seen[key] = min(first_seen.get(key, float("inf")), completed)

    groups: dict[str, list[dict]] = defaultdict(list)
    for requests in seats.values():
        for request in requests:
            if (request["purpose"] == "discard_watch" and not request["seq0"]
                    and request["completed"] is not None):
                groups[_queue_band(request["started"] - request["queued"])].append(request)

    watch = {}
    for band in ("queue_under_100ms", "queue_100_to_500ms",
                 "queue_500_to_1000ms", "queue_at_least_1000ms"):
        requests = groups[band]
        transport_ms = [1000 * (r["completed"] - r["started"]) for r in requests]
        event_requests = [r for r in requests if r["event_seqs"]]
        watch[band] = {
            "get": len(requests),
            "transport_under_20ms": sum(ms < 20 for ms in transport_ms),
            "transport_p50_ms": _median(transport_ms),
            "with_event_seq": len(event_requests),
            # 四身份共用一台机器的单调时钟：如果另一 GET 已经看到
            # 同一 (game_id, seq)，该事件在当前 GET 发出前必已存在。
            "at_least_one_event_seen_before_get_start": sum(
                any(first_seen[(r["game"], seq)] <= r["started"]
                    for seq in r["event_seqs"])
                for r in event_requests),
            "all_events_seen_before_get_start": sum(
                all(first_seen[(r["game"], seq)] <= r["started"]
                    for seq in r["event_seqs"])
                for r in event_requests),
        }

    qinglong = seats["slot-qinglong"]
    _, peak = max(select_windows(qinglong, 18), key=lambda item: len(item[1]))
    by_game: dict[str, list[dict]] = defaultdict(list)
    for request in qinglong:
        by_game[request["game"]].append(request)
    previous_by_request = {}
    for game_requests in by_game.values():
        for index, request in enumerate(game_requests):
            previous_by_request[id(request)] = game_requests[index - 1] if index else None
    previous = [previous_by_request[id(request)] for request in peak]
    prior_events = [r for r in previous if r is not None and r["event_seqs"]]
    peak_summary = {
        "queued_get": len(peak),
        "games": len({r["game"] for r in peak}),
        "previous_get_with_events": len(prior_events),
        "previous_event_occurrences": dict(Counter(
            event_type for r in prior_events for event_type in r["events"])),
        "previous_event_batches_all_seen_before_get_start": sum(
            all(first_seen[(r["game"], seq)] <= r["started"]
                for seq in r["event_seqs"])
            for r in prior_events),
        "previous_get_transport_under_20ms": sum(
            r is not None and r["completed"] is not None
            and r["completed"] - r["started"] < 0.02 for r in previous),
    }
    return {"watch_by_queue_band": watch, "qinglong_peak": peak_summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(analyze(args.audit_root), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
