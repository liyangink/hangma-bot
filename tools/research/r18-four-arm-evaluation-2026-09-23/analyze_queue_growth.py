"""只读分析一间完整测试房的 state 队列增长与相邻事件请求链。

输出仅含聚合统计和相对运行时间；不输出 Token、手牌或原始报文。
原始审计仅覆盖实际发起的 HTTP 请求，排队中取消的请求不在队列占用计算内。
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
from collections import Counter, defaultdict
from pathlib import Path


def _rows(path: Path):
    with path.open() as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1,
                                    int(len(ordered) * fraction + .999999) - 1))], 1)


def _kind(payload: dict) -> str:
    status = payload.get("http_status")
    if status != 200:
        return "http_" + str(status)
    try:
        raw = json.loads(payload.get("raw") or "{}")
    except (ValueError, TypeError):
        return "unparsed"
    if raw.get("snapshot") is not None:
        return "snapshot"
    if raw.get("pending"):
        return "pending"
    events = raw.get("events") or ()
    if not events:
        return "empty"
    types = {event.get("type") for event in events if isinstance(event, dict)}
    if types <= {"timeout", "pass"}:
        return "marker_only"
    if "tile_discarded" in types:
        return "includes_discard"
    if "tile_drawn" in types:
        return "includes_draw"
    return "other_events"


def _load(run: Path) -> list[dict]:
    result = []
    for path in sorted((run / "participants").glob("*/raw/*.jsonl")):
        for row in _rows(path):
            payload = row.get("payload") or {}
            endpoint = str(payload.get("endpoint") or "")
            if "/games/" not in endpoint or not endpoint.endswith("/state"):
                continue
            timing = payload.get("request_timing") or {}
            queued = timing.get("queued_at_monotonic")
            granted = timing.get("granted_at_monotonic")
            started = timing.get("transport_started_at_monotonic")
            completed = timing.get("completed_at_monotonic")
            if not all(isinstance(x, (int, float)) for x in (queued, granted, started, completed)):
                continue
            try:
                body = json.loads(payload.get("raw") or "{}")
            except (ValueError, TypeError):
                body = {}
            result.append({
                "game": endpoint.split("/games/", 1)[1].rsplit("/state", 1)[0],
                "queued": queued, "granted": granted, "started": started,
                "completed": completed, "kind": _kind(payload),
                "purpose": timing.get("query_purpose") or "unknown",
                "priority": timing.get("scheduler_priority") or "unknown",
                "seq0": payload.get("seq_requested") == 0,
                "contains_marker": any(
                    event.get("type") in {"timeout", "pass"}
                    for event in body.get("events") or ()
                    if isinstance(event, dict)
                ),
            })
    return sorted(result, key=lambda row: (row["queued"], row["started"]))


def _bins(requests: list[dict], first: float, last: float, width: int) -> list[dict]:
    """逐秒取队列存量，并按固定时间桶统计到达与已发请求。"""
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in requests:
        groups[int((row["queued"] - first) // width)].append(row)
    result = []
    for index in range(int((last - first) // width) + 1):
        start = first + index * width
        end = min(last, start + width)
        arrivals = groups[index]
        samples = [sum(row["queued"] <= at < row["granted"] for row in requests)
                   for at in (start + step for step in range(int(end - start) + 1))]
        queue_ms = [(row["granted"] - row["queued"]) * 1000 for row in arrivals]
        result.append({
            "seconds": [round(start - first, 1), round(end - first, 1)],
            "arrived": len(arrivals),
            "granted": sum(start <= row["granted"] < end for row in requests),
            "pending_at_start": samples[0] if samples else 0,
            "pending_at_end": samples[-1] if samples else 0,
            "pending_peak_1s_sample": max(samples, default=0),
            "queue_p50_ms": _percentile(queue_ms, .5),
            "queue_p95_ms": _percentile(queue_ms, .95),
            "kinds": dict(sorted(Counter(row["kind"] for row in arrivals).items())),
        })
    return result


def _chains(requests: list[dict]) -> dict:
    by_game: dict[str, list[dict]] = defaultdict(list)
    for row in requests:
        by_game[row["game"]].append(row)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for game_rows in by_game.values():
        for previous, current in zip(game_rows, game_rows[1:]):
            grouped[previous["kind"]].append({
                "next": current["kind"],
                "gap_ms": 1000 * (current["queued"] - previous["completed"]),
                "queue_ms": 1000 * (current["granted"] - current["queued"]),
                "purpose": current["purpose"], "seq0": current["seq0"],
            })
    output = {}
    for kind, items in sorted(grouped.items()):
        output[kind] = {
            "next_requests": len(items),
            "next_queued_under_20ms": sum(row["gap_ms"] < 20 for row in items),
            "next_queued_under_100ms": sum(row["gap_ms"] < 100 for row in items),
            "next_seq0": sum(row["seq0"] for row in items),
            "next_queue_p50_ms": _percentile([row["queue_ms"] for row in items], .5),
            "next_queue_p95_ms": _percentile([row["queue_ms"] for row in items], .95),
            "next_purpose": dict(sorted(Counter(row["purpose"] for row in items).items())),
            "next_kind": dict(sorted(Counter(row["next"] for row in items).items())),
        }
    return output


def _startup_profile(requests: list[dict], first: float) -> dict:
    """按每身份第 0–10 秒核对标记响应之后是否真的集中拉快照。"""
    boundary = first + 10
    by_game: dict[str, list[dict]] = defaultdict(list)
    for row in requests:
        by_game[row["game"]].append(row)
    next_after_marker = Counter()
    next_after_pure_marker = Counter()
    marker_completions: list[tuple[float, str]] = []
    pending_previous = Counter()
    pending_previous_contains_marker = 0
    for game, items in by_game.items():
        for previous, current in zip(items, items[1:]):
            if previous["contains_marker"] and first <= previous["completed"] < boundary:
                next_after_marker["snapshot" if current["seq0"] else "incremental"] += 1
                marker_completions.append((previous["completed"], game))
                if previous["kind"] == "marker_only":
                    next_after_pure_marker["snapshot" if current["seq0"] else "incremental"] += 1
            if current["queued"] <= boundary < current["granted"]:
                pending_previous[previous["kind"]] += 1
                pending_previous_contains_marker += previous["contains_marker"]
    pending = [row for row in requests if row["queued"] <= boundary < row["granted"]]
    marker_completions.sort()
    rolling_games = [
        len({game for time, game in marker_completions[index:]
             if time - start < 0.1})
        for index, (start, _) in enumerate(marker_completions)
    ]
    return {
        "responses_containing_marker_completed": sum(next_after_marker.values()),
        "next_after_marker": dict(sorted(next_after_marker.items())),
        "pure_marker_completed": sum(next_after_pure_marker.values()),
        "next_after_pure_marker": dict(sorted(next_after_pure_marker.items())),
        "max_distinct_marker_games_in_rolling_100ms": max(rolling_games, default=0),
        "rolling_100ms_start_points_with_four_marker_games": sum(
            count >= 4 for count in rolling_games
        ),
        "pending_at_10s": len(pending),
        "pending_purpose": dict(sorted(Counter(row["purpose"] for row in pending).items())),
        "pending_priority": dict(sorted(Counter(row["priority"] for row in pending).items())),
        "pending_previous_kind": dict(sorted(pending_previous.items())),
        "pending_previous_contains_marker": pending_previous_contains_marker,
        "pending_queued_in_9_to_10s": sum(
            boundary - 1 <= row["queued"] < boundary for row in pending
        ),
    }


def analyze(root: Path) -> dict:
    result = {}
    for slot in sorted(root.glob("slot-*")):
        runs = list((slot / "runs").glob("run-*"))
        if not runs:
            continue
        run = max(runs, key=lambda path: path.stat().st_mtime_ns)
        requests = _load(run)
        if not requests:
            continue
        first = min(row["queued"] for row in requests)
        last = max(row["completed"] for row in requests)
        result[slot.name] = {
            "request_count": len(requests),
            "duration_sec": round(last - first, 1),
            "minute_bins": _bins(requests, first, last, 60),
            "ten_second_bins": _bins(requests, first, last, 10),
            "response_kinds": dict(sorted(Counter(row["kind"] for row in requests).items())),
            "same_game_chains": _chains(requests),
            "startup_profile": _startup_profile(requests, first),
        }
    return result


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
