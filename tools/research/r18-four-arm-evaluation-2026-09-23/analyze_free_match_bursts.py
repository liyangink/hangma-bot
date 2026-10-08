"""只读对照旧自由赛与测试房的 M=10 状态查询需求。

原始报文仅在内存中解析；输出是按房聚合的数量和毫秒级等待，不含凭据或牌面。
不同日期的调度器不能用于因果 A/B 对比，详情见同目录报告。
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

import gzip
import json
from collections import Counter, deque
from pathlib import Path


WINDOW_SEC = 1.05


def read_rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_state_requests(run: Path) -> list[dict]:
    requests = []
    for path in sorted((run / "participants").glob("*/raw/*.jsonl*")):
        for row in read_rows(path):
            payload = row.get("payload") or {}
            endpoint = str(payload.get("endpoint") or "")
            if "/games/" not in endpoint or not endpoint.endswith("/state"):
                continue
            timing = payload.get("request_timing") or {}
            queued = timing.get("queued_at_monotonic")
            started = timing.get("transport_started_at_monotonic")
            completed = timing.get("completed_at_monotonic")
            if not all(isinstance(value, (int, float)) for value in (queued, started, completed)):
                continue
            try:
                response = json.loads(payload.get("raw") or "{}")
            except (TypeError, json.JSONDecodeError):
                response = {}
            requests.append({
                "game": endpoint.rsplit("/games/", 1)[1].rsplit("/state", 1)[0],
                "queued": queued,
                "started": started,
                "completed": completed,
                "seq0": payload.get("seq_requested") == 0,
                "purpose": timing.get("query_purpose") or "unknown",
                "status": payload.get("http_status"),
                "events": [(e.get("seq"), e.get("type"), e.get("seat"), e.get("ts"))
                           for e in response.get("events") or [] if isinstance(e, dict)],
            })
    requests.sort(key=lambda item: item["queued"])
    return requests


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values.sort()
    return round(values[min(len(values) - 1, int(q * (len(values) - 1)))], 1)


def official_cadence(session: Path, room: str, participant_id: str) -> dict:
    """按完整官方牌谱中的秒级时间戳统计摸牌后弃牌；分清我方与对手。"""
    games = {}
    for path in sorted((session / "official").glob("dl-*/events.json")):
        data = json.loads(path.read_text())
        if data.get("room_id") != room or data.get("status") != "finished":
            continue
        game = data.get("game_id")
        if game:
            games[game] = data
    gaps = {"own": [], "opponent": []}
    for data in games.values():
        seats = data.get("seats") or []
        own_seat = next((i for i, seat in enumerate(seats)
                         if seat.get("user_id") == participant_id), None)
        events = {}
        for block in data.get("blocks") or []:
            for event in block.get("events") or []:
                seq = event.get("seq")
                if isinstance(seq, int):
                    events.setdefault(seq, event)
        last_draw = {}
        for _, event in sorted(events.items()):
            kind, seat, ts = event.get("type"), event.get("seat"), event.get("ts")
            if kind == "round_ended":
                last_draw.clear()
            if not isinstance(seat, int) or not isinstance(ts, int):
                continue
            if kind == "tile_drawn":
                last_draw[seat] = ts
            elif kind == "tile_discarded" and seat in last_draw:
                gap = ts - last_draw.pop(seat)
                if 0 <= gap <= 10 and own_seat is not None:
                    gaps["own" if seat == own_seat else "opponent"].append(gap)
    return {
        "games": len(games),
        "own": {"matched": len(gaps["own"]),
                "same_second": sum(x == 0 for x in gaps["own"]),
                "le1second": sum(x <= 1 for x in gaps["own"])},
        "opponent": {"matched": len(gaps["opponent"]),
                     "same_second": sum(x == 0 for x in gaps["opponent"]),
                     "le1second": sum(x <= 1 for x in gaps["opponent"])},
    }


def analyze(run: Path) -> dict:
    requests = load_state_requests(run)
    manifest = json.loads((run / "manifest.json").read_text()).get("payload") or {}
    if not requests:
        return {"room": manifest.get("room_id"), "error": "no state requests"}
    first = min(r["started"] for r in requests)
    last = max(r["completed"] for r in requests)
    bounds: dict[str, list[float]] = {}
    physical_events: dict[tuple[str, int], tuple] = {}
    for row in requests:
        bound = bounds.setdefault(row["game"], [row["queued"], row["completed"]])
        bound[0] = min(bound[0], row["queued"])
        bound[1] = max(bound[1], row["completed"])
        for seq, kind, seat, ts in row["events"]:
            if isinstance(seq, int):
                physical_events.setdefault((row["game"], seq), (kind, seat, ts))
    discards = sum(e[0] == "tile_discarded" for e in physical_events.values())
    active_table_sec = sum(max(0, end - begin) for begin, end in bounds.values())
    pending: deque[dict] = deque()
    peaks = []
    for row in requests:
        while pending and pending[0]["queued"] <= row["queued"] - WINDOW_SEC:
            pending.popleft()
        pending.append(row)
        if first + 30 <= row["queued"] <= last - 30:
            peaks.append((len(pending), row["queued"]))
    chosen = []
    for _, end in sorted(peaks, key=lambda x: (-x[0], x[1])):
        if all(abs(end - existing) >= WINDOW_SEC for existing in chosen):
            chosen.append(end)
    selected = []
    for end in chosen:
        rows = [r for r in requests if end - WINDOW_SEC < r["queued"] <= end]
        selected.append({
            "count": len(rows),
            "games": len({r["game"] for r in rows}),
            "active_games": sum(start <= end <= stop for start, stop in bounds.values()),
            "incremental": sum(not r["seq0"] for r in rows),
            "snapshot": sum(r["seq0"] for r in rows),
            "purpose": dict(Counter(r["purpose"] for r in rows)),
            "queue_ms_p50": quantile([1000 * (r["started"] - r["queued"]) for r in rows], .5),
        })
    peak = max(selected, key=lambda x: x["count"])
    incremental_pending: deque[dict] = deque()
    incremental_peak = (0, 0)
    for row in requests:
        if row["seq0"]:
            continue
        while (incremental_pending and
               incremental_pending[0]["queued"] <= row["queued"] - WINDOW_SEC):
            incremental_pending.popleft()
        incremental_pending.append(row)
        if (first + 30 <= row["queued"] <= last - 30 and
                len(incremental_pending) > incremental_peak[0]):
            incremental_peak = (len(incremental_pending),
                                len({r["game"] for r in incremental_pending}))
    busy = [r for r in requests if sum(start <= r["queued"] <= stop
                                       for start, stop in bounds.values()) == 10]
    busy_duration = 0.0
    if busy:
        busy_duration = max(r["queued"] for r in busy) - min(r["queued"] for r in busy)
    # 官方事件时间只有整秒；此分布仅能判断“同一秒”，无法判断 150 毫秒。
    draw_discard_seconds = []
    by_game: dict[str, list[tuple[int, str, int, int]]] = {}
    for (game, seq), (kind, seat, ts) in physical_events.items():
        by_game.setdefault(game, []).append((seq, kind, seat, ts))
    for game, events in by_game.items():
        last_draw: dict[int, int] = {}
        for _, kind, seat, ts in sorted(events):
            if not isinstance(seat, int) or not isinstance(ts, int):
                continue
            if kind == "tile_drawn":
                last_draw[seat] = ts
            elif kind == "tile_discarded" and seat in last_draw:
                gap = ts - last_draw.pop(seat)
                if 0 <= gap <= 10:
                    draw_discard_seconds.append(gap)
    return {
        "room": manifest.get("room_id") or run.parents[3].name,
        "policy": manifest.get("policy_version"),
        "scheduler": manifest.get("state_scheduler_version"),
        "max_games": manifest.get("max_games"),
        "games_seen": len(bounds),
        "elapsed_sec": round(last - first, 1),
        "busy_10_game_sec_approx": round(busy_duration, 1),
        "get": len(requests),
        "get_per_sec": round(len(requests) / (last - first), 2),
        "get_per_discard": round(len(requests) / discards, 2) if discards else None,
        "discard_events": discards,
        "discards_per_active_table_min": round(60 * discards / active_table_sec, 2),
        "http_status": dict(Counter(str(r["status"]) for r in requests)),
        "purposes": dict(Counter(r["purpose"] for r in requests)),
        "seq0": sum(r["seq0"] for r in requests),
        "steady_peak_1p05s": peak,
        "steady_incremental_peak_1p05s": {
            "count": incremental_peak[0], "games": incremental_peak[1]},
        "steady_windows_ge18": sum(p["count"] >= 18 for p in selected),
        "steady_ge18_with_10_active": sum(p["count"] >= 18 and p["active_games"] == 10
                                        for p in selected),
        "draw_discard_matched_coarse": len(draw_discard_seconds),
        "draw_discard_same_second_coarse": sum(x == 0 for x in draw_discard_seconds),
        "draw_discard_le1second_coarse": sum(x <= 1 for x in draw_discard_seconds),
        "queue_wait_p50_ms": quantile([1000 * (r["started"] - r["queued"])
                                       for r in requests], .5),
        "queue_wait_p95_ms": quantile([1000 * (r["started"] - r["queued"])
                                       for r in requests], .95),
        "official_cadence": official_cadence(run.parents[2], manifest.get("room_id"),
                                             manifest.get("participant_id"))
        if manifest.get("mode") == "auto_match" else None,
    }


def main() -> None:
    root = Path("artifacts/sessions")
    manifests = sorted(root.glob("auto-match-a_*/audit/runs/run-*/manifest.json"),
                       key=lambda p: json.loads(p.read_text()).get("wall_time_unix_ms", 0),
                       reverse=True)
    complete_manifests = [p for p in manifests
                          if len(list((p.parents[3] / "official").glob("dl-*/events.json"))) >= 10]
    free = [analyze(p.parent) for p in complete_manifests[:10]]
    test_root = root / "r18-rate-fix-m10-20260923-r3/audit/slot-qinglong/runs"
    test_run = next(test_root.glob("run-*"))
    result = {"free_rooms": free, "test_room_r3_qinglong": analyze(test_run)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
