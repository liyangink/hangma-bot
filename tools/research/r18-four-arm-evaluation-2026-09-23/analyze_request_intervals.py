"""比较测试房状态查询的发送耗时、同场重入队间隔与跨场突发。"""

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
from statistics import mean


def _quantile(values: list[float], fraction: float) -> float | None:
    """用最近秩定义分位数，单位保持输入单位。"""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction + .999999) - 1))], 1)


def _distribution(values: list[float]) -> dict:
    """统一输出毫秒分布，避免不同类别采用不同口径。"""
    return {
        "count": len(values),
        "mean_ms": round(mean(values), 1) if values else None,
        "p50_ms": _quantile(values, .5),
        "p95_ms": _quantile(values, .95),
        "max_ms": round(max(values), 1) if values else None,
    }


def _rows(path: Path):
    """只读取完整 JSONL 行；正式报告仅对 complete 审计运行。"""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def analyze(root: Path) -> dict:
    """对四身份完整运行求原始观察量，不模拟人为缓发的因果效果。"""
    purposes = defaultdict(lambda: {
        "status": Counter(), "queue": [], "network": [], "total": [], "event_count": []})
    all_queue = []
    all_gaps = []
    response_slack = []
    peaks = {}
    for slot in sorted(root.glob("slot-*")):
        runs = sorted((slot / "runs").glob("run-*"), key=lambda path: path.stat().st_mtime)
        if not runs:
            raise ValueError(f"{slot.name}: 没有审计运行")
        run = runs[-1]
        by_game = defaultdict(list)
        by_slot = []
        for path in (run / "participants").glob("*/raw/t_*.jsonl"):
            for row in _rows(path):
                payload = row.get("payload") or {}
                endpoint = str(payload.get("endpoint", ""))
                if not endpoint.endswith("/state") or "/games/" not in endpoint:
                    continue
                timing = payload.get("request_timing") or {}
                queued = timing.get("queued_at_monotonic")
                granted = timing.get("granted_at_monotonic")
                started = timing.get("transport_started_at_monotonic")
                completed = timing.get("completed_at_monotonic")
                purpose = str(timing.get("query_purpose") or "unknown")
                item = purposes[purpose]
                status = payload.get("http_status")
                item["status"][str(status)] += 1
                if queued is not None and granted is not None:
                    delay = 1000 * (granted - queued)
                    item["queue"].append(delay)
                    all_queue.append(delay)
                if status == 200 and started is not None and completed is not None:
                    item["network"].append(1000 * (completed - started))
                    if queued is not None:
                        item["total"].append(1000 * (completed - queued))
                    try:
                        body = json.loads(payload.get("raw") or "{}")
                    except (TypeError, ValueError):
                        body = {}
                    item["event_count"].append(len(body.get("events") or ()))
                if queued is None or completed is None:
                    continue
                game_id = endpoint.split("/games/", 1)[1].rsplit("/state", 1)[0]
                request = (queued, completed, game_id)
                by_game[game_id].append(request)
                by_slot.append(request)
        for requests in by_game.values():
            requests.sort()
            all_gaps.extend(1000 * (current[0] - previous[1])
                            for previous, current in zip(requests, requests[1:]))
        by_slot.sort()
        left = 0
        peak_count = 0
        peak_games = 0
        for right, request in enumerate(by_slot):
            while request[0] - by_slot[left][0] > 1.05:
                left += 1
            count = right - left + 1
            if count > peak_count:
                peak_count = count
                peak_games = len({row[2] for row in by_slot[left:right + 1]})
        peaks[slot.name] = {
            "queued_in_1_05s": peak_count,
            "distinct_games": peak_games,
            "same_game_repeats": peak_count - peak_games,
        }
        for path in (run / "participants").glob("*/decisions.jsonl"):
            for row in _rows(path):
                if row.get("kind") != "decision_input":
                    continue
                payload = row.get("payload") or {}
                phase = (payload.get("window") or {}).get("phase")
                if phase not in ("response_peng", "response_chi"):
                    continue
                origin = payload.get("budget_origin_monotonic")
                latest = (payload.get("budget") or {}).get("latest_send_at_monotonic")
                if origin is not None and latest is not None:
                    response_slack.append(1000 * (latest - origin))
    return {
        "room": root.parent.name,
        "scope": "四席最后一次完整测试房运行；网络耗时仅 HTTP 200；GET /state；单调时钟毫秒",
        "state_get": sum(sum(entry["status"].values()) for entry in purposes.values()),
        "state_429": sum(entry["status"]["429"] for entry in purposes.values()),
        "queue_ms": _distribution(all_queue),
        "same_game_completion_to_next_queue_ms": {
            **_distribution(all_gaps),
            "p10_ms": _quantile(all_gaps, .1),
            "p90_ms": _quantile(all_gaps, .9),
            "under_50ms": sum(0 <= value < 50 for value in all_gaps),
            "under_100ms": sum(0 <= value < 100 for value in all_gaps),
        },
        "response_input_to_latest_send_ms": {
            **_distribution(response_slack),
            "p01_ms": _quantile(response_slack, .01),
            "under_100ms": sum(value < 100 for value in response_slack),
        },
        "peak_arrivals_by_slot": peaks,
        "by_purpose": {
            purpose: {
                "status": dict(entry["status"]),
                "queue_ms": _distribution(entry["queue"]),
                "network_ms": _distribution(entry["network"]),
                "queue_to_response_ms": _distribution(entry["total"]),
                "mean_events_per_200": round(mean(entry["event_count"]), 2)
                if entry["event_count"] else None,
            }
            for purpose, entry in sorted(purposes.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {root.parent.name: analyze(root) for root in args.roots}
    document = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(document, encoding="utf-8")
    else:
        print(document, end="")


if __name__ == "__main__":
    main()
