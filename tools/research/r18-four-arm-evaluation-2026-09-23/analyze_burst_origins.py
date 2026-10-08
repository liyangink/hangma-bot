"""逐笔解释稳态状态查询拥堵：前一条同桌结果、请求用途、桌数及事件年龄。

只读完整桌原始审计。选取所有彼此不重叠、1.05 秒内至少 threshold 笔
入队的稳态峰值窗口；同一秒的滑动候选不能重复当独立样本。输出不含牌面。
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

from analyze_qps_cause import WINDOW_SEC, read_rows


def category(request: dict) -> str:
    if request["seq0"]:
        return "full:" + request["purpose"]
    return "incremental:" + request["purpose"]


def predecessor_kind(previous: dict | None) -> str:
    if previous is None:
        return "first_query"
    events = previous["events"]
    if events:
        # 最后一条通常代表本次结果推进后的下一事件需求；保留全部
        # 事件种类以免把“同一次 GET 带回三条 timeout”说成三笔请求。
        return "events:" + "+".join(sorted(set(events)))
    if previous["snapshot_phase"]:
        return "snapshot:" + previous["snapshot_phase"]
    return "status:" + str(previous["status"])


def load_requests(run: Path) -> list[dict]:
    requests = []
    for path in sorted((run / "participants").glob("*/raw/*.jsonl")):
        for row in read_rows(path):
            payload = row.get("payload") or {}
            endpoint = str(payload.get("endpoint") or "")
            if not endpoint.endswith("/state") or "/games/" not in endpoint:
                continue
            timing = payload.get("request_timing") or {}
            queued = timing.get("queued_at_monotonic")
            started = timing.get("transport_started_at_monotonic")
            if not isinstance(queued, (int, float)) or not isinstance(started, (int, float)):
                continue
            try:
                response = json.loads(payload.get("raw") or "{}")
            except (TypeError, json.JSONDecodeError):
                response = {}
            events = response.get("events") or []
            requests.append({
                "game": endpoint.rsplit("/games/", 1)[1].rsplit("/state", 1)[0],
                "queued": queued, "started": started,
                "completed": timing.get("completed_at_monotonic"),
                "started_wall_ms": timing.get("started_wall_unix_ms"),
                "completed_wall_ms": timing.get("completed_wall_unix_ms"),
                "status": payload.get("http_status"),
                "seq_requested": payload.get("seq_requested"),
                "seq0": payload.get("seq_requested") == 0,
                "purpose": timing.get("query_purpose") or "unknown",
                "priority": timing.get("scheduler_priority") or "unknown",
                "events": [e.get("type") for e in events if isinstance(e, dict)],
                "event_ts": [e.get("ts") for e in events if isinstance(e, dict)
                             and isinstance(e.get("ts"), (int, float))],
                "event_seqs": [e.get("seq") for e in events if isinstance(e, dict)
                               and isinstance(e.get("seq"), int)],
                "snapshot_phase": (response.get("snapshot") or {}).get("phase"),
            })
    requests.sort(key=lambda row: row["queued"])
    by_game: dict[str, list[dict]] = defaultdict(list)
    for request in requests:
        by_game[request["game"]].append(request)
    for game_rows in by_game.values():
        for index, request in enumerate(game_rows):
            previous = game_rows[index - 1] if index else None
            request["predecessor"] = predecessor_kind(previous)
            request["since_prev_complete_ms"] = (
                round(1000 * (request["queued"] - previous["completed"]), 1)
                if previous and previous["completed"] is not None else None)
            request["prev_event_age_upper_sec"] = (
                round(previous["completed_wall_ms"] / 1000 - max(previous["event_ts"]), 3)
                if previous and previous["event_ts"] and previous["completed_wall_ms"] is not None
                else None)
            # 官方事件 ts 只有整秒精度：若最新事件的整秒上界仍早于
            # GET 发起时间，才可判作请求发起前已有；反向只能判作待定。
            request["prev_events_certainly_preexisting"] = (
                previous["started_wall_ms"] >= (max(previous["event_ts"]) + 1) * 1000
                if previous and previous["event_ts"] and previous["started_wall_ms"] is not None
                else None)
            request["prev_get_transport_ms"] = (
                round(1000 * (previous["completed"] - previous["started"]), 1)
                if previous and previous["completed"] is not None else None)
    return requests


def select_windows(requests: list[dict], threshold: int) -> list[tuple[float, list[dict]]]:
    first = min(r["started"] for r in requests)
    last = max(r["completed"] or r["started"] for r in requests)
    ordered = sorted(requests, key=lambda row: row["queued"])
    candidates = []
    left = 0
    for right, row in enumerate(ordered):
        end = row["queued"]
        while ordered[left]["queued"] <= end - WINDOW_SEC:
            left += 1
        count = right - left + 1
        if first + 30 <= end <= last - 30 and count >= threshold:
            candidates.append((count, end))
    # 高峰优先；同一波只保留一个峰值，避免滑动窗口逐毫秒重复计数。
    chosen: list[float] = []
    for _, end in sorted(candidates, key=lambda item: (-item[0], item[1])):
        if all(end <= other - WINDOW_SEC or other <= end - WINDOW_SEC
               for other in chosen):
            chosen.append(end)
    result = []
    for end in sorted(chosen):
        result.append((end - first, [r for r in ordered if end - WINDOW_SEC < r["queued"] <= end]))
    return result


def window_summary(offset: float, rows: list[dict], *, detail: bool) -> dict:
    games = Counter(r["game"].rsplit("_", 2)[-2] for r in rows)
    prev_age = [r["prev_event_age_upper_sec"] for r in rows
                if r["prev_event_age_upper_sec"] is not None]
    immediate = sum(r["since_prev_complete_ms"] is not None
                    and -1 <= r["since_prev_complete_ms"] <= 50 for r in rows)
    previous_event_preexisting = sum(r["prev_events_certainly_preexisting"] is True for r in rows)
    previous_event_sample = sum(r["prev_events_certainly_preexisting"] is not None for r in rows)
    result = {
        "at_sec_from_first": round(offset, 3), "queued_get": len(rows),
        "distinct_games": len(games), "max_one_game": max(games.values()),
        "top_two_games": sum(value for _, value in games.most_common(2)),
        "by_game": dict(sorted(games.items())),
        "by_category": dict(Counter(category(r) for r in rows)),
        "by_priority": dict(Counter(r["priority"] for r in rows)),
        "by_predecessor": dict(Counter(r["predecessor"] for r in rows)),
        "immediate_rearm_within_50ms": immediate,
        "prior_event_age_upper_over_2s": sum(age > 2 for age in prev_age),
        "prior_event_age_sample": len(prev_age),
        "prior_events_certainly_preexisting_at_get_start": previous_event_preexisting,
        "prior_events_timestamped": previous_event_sample,
    }
    if detail:
        result["requests"] = [{
            "queued_at_sec_from_first": round(offset - (max(r["queued"] for r in rows) - r["queued"]), 3),
            "game": r["game"].rsplit("_", 2)[-2],
            "category": category(r), "priority": r["priority"],
            "predecessor": r["predecessor"],
            "since_prev_complete_ms": r["since_prev_complete_ms"],
            "previous_event_age_upper_sec": r["prev_event_age_upper_sec"],
            "previous_events_certainly_preexisting_at_get_start": r["prev_events_certainly_preexisting"],
            "previous_get_transport_ms": r["prev_get_transport_ms"],
            "queue_wait_ms": round(1000 * (r["started"] - r["queued"]), 1),
            "returned_events": r["events"],
            "returned_snapshot_phase": r["snapshot_phase"],
            "status": r["status"],
        } for r in rows]
    return result


def analyze(root: Path, threshold: int, detail_per_seat: int) -> dict:
    result = {}
    for run in sorted(root.glob("slot-*/runs/*")):
        if not run.is_dir():
            continue
        requests = load_requests(run)
        windows = select_windows(requests, threshold)
        biggest = sorted(windows, key=lambda item: len(item[1]), reverse=True)
        detailed_offsets = {offset for offset, _ in biggest[:detail_per_seat]}
        summaries = [window_summary(offset, rows, detail=offset in detailed_offsets)
                     for offset, rows in windows]
        result[run.parent.parent.name] = {
            "windows": len(summaries),
            "queued_get": sum(w["queued_get"] for w in summaries),
            "distinct_games_p50": sorted(w["distinct_games"] for w in summaries)[len(summaries) // 2]
            if summaries else None,
            "distinct_games_at_least_8": sum(w["distinct_games"] >= 8 for w in summaries),
            "max_one_game_at_least_5": sum(w["max_one_game"] >= 5 for w in summaries),
            "max_one_game_at_least_8": sum(w["max_one_game"] >= 8 for w in summaries),
            "one_game_majority": sum(w["max_one_game"] * 2 > w["queued_get"] for w in summaries),
            "two_games_majority": sum(w["top_two_games"] * 2 > w["queued_get"] for w in summaries),
            "aggregate_by_category": dict(sum((Counter(w["by_category"]) for w in summaries), Counter())),
            "aggregate_by_predecessor": dict(sum((Counter(w["by_predecessor"]) for w in summaries), Counter())),
            "immediate_rearm_within_50ms": sum(w["immediate_rearm_within_50ms"] for w in summaries),
            "prior_event_age_upper_over_2s": sum(w["prior_event_age_upper_over_2s"] for w in summaries),
            "prior_event_age_sample": sum(w["prior_event_age_sample"] for w in summaries),
            "prior_events_certainly_preexisting_at_get_start": sum(
                w["prior_events_certainly_preexisting_at_get_start"] for w in summaries),
            "prior_events_timestamped": sum(w["prior_events_timestamped"] for w in summaries),
            "top_windows": sorted(summaries, key=lambda item: item["queued_get"], reverse=True)[:detail_per_seat],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--threshold", type=int, default=18)
    parser.add_argument("--detail-per-seat", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = analyze(args.root, args.threshold, args.detail_per_seat)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
