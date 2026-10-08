"""复核同场重挂底档对拥堵窗口的实际覆盖面，不读取凭证。"""

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
from collections import Counter
from pathlib import Path


WINDOW_SEC = 1.05
SPACING_SEC = .05


def _rows(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def _ordinary(item: dict) -> bool:
    """审计代理条件：真实调用仍须由会话自身判定是否为长轮询。"""
    return (isinstance(item["seq"], int) and item["seq"] > 0
            and item["priority"] == "DISCARD_WATCH"
            and item["purpose"] == "discard_watch")


def _previous_kind(item: dict) -> str:
    """按上一响应的可见事件分类；互斥顺序与长轮询延期复算一致。"""
    event_types = set(item["event_types"])
    for name, types in (
        ("draw", {"tile_drawn"}), ("discard", {"tile_discarded"}),
        ("claim", {"chi", "peng", "gang"}), ("timeout", {"timeout"}),
        ("pass", {"pass"}), ("round_end", {"round_ended", "game_ended"}),
    ):
        if event_types & types:
            return name
    return "empty" if not event_types else "other"


def analyze_slot(run: Path, spacing_sec: float = SPACING_SEC) -> dict:
    """按每场原始请求次序找直接可整形的连续普通增量长轮询。"""
    counts = Counter()
    shifted_by_previous_kind = Counter()
    requests = []
    for path in (run / "participants").glob("*/raw/t_*.jsonl"):
        previous = None
        post_between = False
        for row in _rows(path):
            payload = row.get("payload") or {}
            endpoint = str(payload.get("endpoint", ""))
            if endpoint.startswith("POST ") and endpoint.endswith("/action"):
                post_between = True
                continue
            if not endpoint.endswith("/state"):
                continue
            timing = payload.get("request_timing") or {}
            try:
                body = json.loads(payload.get("raw") or "{}")
            except (TypeError, ValueError):
                body = {}
            events = body.get("events") or []
            queued = timing.get("queued_at_monotonic")
            if not isinstance(queued, (float, int)):
                continue
            item = {
                "game": path.stem,
                "queued": queued,
                "start": timing.get("transport_started_at_monotonic"),
                "completed": timing.get("completed_at_monotonic"),
                "seq": payload.get("seq_requested"),
                "priority": timing.get("scheduler_priority"),
                "purpose": timing.get("query_purpose"),
                "status": payload.get("http_status"),
                "event_types": [event.get("type") for event in events],
            }
            item["ordinary"] = _ordinary(item)
            item["short_requeue"] = bool(
                item["ordinary"] and previous and previous["ordinary"]
                and previous["status"] == 200 and not post_between
                and isinstance(previous["completed"], (int, float))
                and 0 <= queued - previous["completed"] < spacing_sec)
            item["would_directly_move_start"] = bool(
                item["short_requeue"] and isinstance(item["start"], (int, float))
                and item["start"] < previous["completed"] + spacing_sec)
            counts["state_get"] += 1
            counts["seq0"] += item["seq"] == 0
            counts["ordinary"] += item["ordinary"]
            counts["short_ordinary_requeue"] += item["short_requeue"]
            counts["observed_start_within_spacing"] += item["would_directly_move_start"]
            if item["would_directly_move_start"]:
                shifted_by_previous_kind[_previous_kind(previous)] += 1
                if item["start"] - queued >= .2:
                    counts["shifted_after_200ms_queue"] += 1
                if any(event.get("type") == "tile_discarded" for event in events):
                    counts["shifted_response_has_discard"] += 1
            if isinstance(item["start"], (int, float)) and item["start"] - queued > 1:
                counts["queue_over_1s"] += 1
                counts["short_requeue_in_queue_over_1s"] += item["short_requeue"]
            requests.append(item)
            previous = item
            post_between = False

    requests.sort(key=lambda item: item["queued"])
    if not requests:
        return {**counts, "spacing_ms": round(spacing_sec * 1000),
                "shifted_by_previous_kind": dict(shifted_by_previous_kind),
                "steady_peak": None}
    first, last = requests[0]["queued"], requests[-1]["queued"]
    left = 0
    peak = None
    for right, request in enumerate(requests):
        while requests[left]["queued"] < request["queued"] - WINDOW_SEC:
            left += 1
        if not first + 30 <= request["queued"] <= last - 30:
            continue
        window = requests[left:right + 1]
        if peak is None or len(window) > peak["state_get"]:
            peak = {
                "state_get": len(window),
                "distinct_games": len({item["game"] for item in window}),
                "seq0": sum(item["seq"] == 0 for item in window),
                "ordinary": sum(item["ordinary"] for item in window),
                "short_ordinary_requeue": sum(item["short_requeue"] for item in window),
                "observed_start_within_spacing": sum(
                    item["would_directly_move_start"] for item in window),
            }
    return {**counts, "spacing_ms": round(spacing_sec * 1000),
            "shifted_by_previous_kind": dict(shifted_by_previous_kind),
            "steady_peak": peak}


def analyze(root: Path, spacing_sec: float = SPACING_SEC) -> dict:
    result = {}
    for slot in sorted(root.glob("slot-*")):
        runs = list((slot / "runs").glob("run-*"))
        if runs:
            run = max(runs, key=lambda item: (item.stat().st_mtime_ns, item.name))
            result[slot.name] = analyze_slot(run, spacing_sec=spacing_sec)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--spacing-ms", type=int, default=50)
    args = parser.parse_args()
    if not 0 < args.spacing_ms <= 1000:
        parser.error("--spacing-ms 必须在 1..1000 之间")
    result = {root.parent.name: analyze(root, spacing_sec=args.spacing_ms / 1000)
              for root in args.roots}
    document = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(document, encoding="utf-8")
    else:
        print(document, end="")


if __name__ == "__main__":
    main()
