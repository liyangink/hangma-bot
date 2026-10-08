"""从四席审计核对同桌连续弃牌 POST 的实际时间间隔。"""

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
import statistics
from collections import defaultdict
from pathlib import Path

from analyze_burst_origins import load_requests, select_windows
from analyze_qps_cause import read_rows


def accepted_discards(audit_root: Path) -> tuple[dict[str, list[dict]], list[float]]:
    by_game: dict[str, list[dict]] = defaultdict(list)
    draw_to_discard_ms = []
    for slot in sorted(audit_root.glob("slot-*")):
        run = next(slot.glob("runs/*"))
        intents = {}
        draw_seen: dict[tuple[str, int], float] = {}
        for path in (run / "participants").glob("*/decisions.jsonl"):
            for row in read_rows(path):
                if row.get("kind") != "submission_intent":
                    continue
                payload = row.get("payload") or {}
                body = payload.get("body") or {}
                if body.get("action") != "discard":
                    continue
                context = row.get("context") or {}
                window = payload.get("window") or {}
                key = (str(payload.get("decision_id") or context.get("decision_id")),
                       int(payload.get("attempt_no") or context.get("attempt_no") or 0))
                intents[key] = (window.get("game_id"), window.get("seat"),
                                window.get("phase"), window.get("trigger_seq"))
        for path in (run / "participants").glob("*/raw/*.jsonl"):
            for row in read_rows(path):
                payload = row.get("payload") or {}
                endpoint = str(payload.get("endpoint") or "")
                timing = payload.get("request_timing") or {}
                if endpoint.endswith("/state") and "/games/" in endpoint:
                    completed = timing.get("completed_at_monotonic")
                    if isinstance(completed, (int, float)):
                        game = endpoint.rsplit("/games/", 1)[1].rsplit("/state", 1)[0]
                        try:
                            response = json.loads(payload.get("raw") or "{}")
                        except (TypeError, json.JSONDecodeError):
                            response = {}
                        for event in response.get("events") or []:
                            if (event.get("type") == "tile_drawn"
                                    and isinstance(event.get("seq"), int)):
                                event_key = (game, event["seq"])
                                draw_seen[event_key] = min(
                                    draw_seen.get(event_key, float("inf")), completed)
                if (payload.get("http_status") != 200
                        or not endpoint.endswith("/action")):
                    continue
                key = (str(payload.get("decision_id")), int(payload.get("attempt_no") or 0))
                if key not in intents:
                    continue
                game, seat, phase, trigger_seq = intents[key]
                completed = timing.get("completed_at_monotonic")
                if game and isinstance(completed, (int, float)):
                    by_game[game].append({"seat": seat, "completed": completed})
                    if phase == "draw":
                        seen = draw_seen.get((game, trigger_seq))
                        if seen is not None and completed >= seen:
                            draw_to_discard_ms.append(1000 * (completed - seen))
    for actions in by_game.values():
        actions.sort(key=lambda action: action["completed"])
    return by_game, draw_to_discard_ms


def analyze(audit_root: Path) -> dict:
    by_game, draw_to_discard_ms = accepted_discards(audit_root)
    pair_gaps = []
    triple_gaps = []
    distinct_triples_under_1s = []
    for game, actions in by_game.items():
        pair_gaps.extend(b["completed"] - a["completed"]
                         for a, b in zip(actions, actions[1:]))
        for a, b, c in zip(actions, actions[1:], actions[2:]):
            gap = c["completed"] - a["completed"]
            triple_gaps.append(gap)
            if gap <= 1 and len({a["seat"], b["seat"], c["seat"]}) == 3:
                distinct_triples_under_1s.append((game, c["completed"]))

    windows = []
    for slot in sorted(audit_root.glob("slot-*")):
        requests = load_requests(next(slot.glob("runs/*")))
        for _, rows in select_windows(requests, 18):
            windows.append((max(row["queued"] for row in rows),
                            {row["game"] for row in rows}))
    window_near_fast_triple = sum(
        any(game in games and end - 3 <= finished <= end
            for game, finished in distinct_triples_under_1s)
        for end, games in windows)
    return {
        "accepted_bot_discard_posts": sum(map(len, by_game.values())),
        "draw_to_discard_matched": len(draw_to_discard_ms),
        "draw_to_discard_under_50ms": sum(ms < 50 for ms in draw_to_discard_ms),
        "draw_to_discard_under_150ms": sum(ms < 150 for ms in draw_to_discard_ms),
        "draw_to_discard_p50_ms": round(statistics.median(draw_to_discard_ms), 1)
        if draw_to_discard_ms else None,
        "games": len(by_game),
        "consecutive_pair_count": len(pair_gaps),
        "consecutive_pair_at_most_150ms": sum(gap <= .15 for gap in pair_gaps),
        "consecutive_triple_count": len(triple_gaps),
        "consecutive_triple_at_most_150ms": sum(gap <= .15 for gap in triple_gaps),
        "consecutive_triple_at_most_500ms": sum(gap <= .5 for gap in triple_gaps),
        "consecutive_triple_at_most_1s": sum(gap <= 1 for gap in triple_gaps),
        "fastest_triple_ms": round(1000 * min(triple_gaps), 1) if triple_gaps else None,
        "distinct_seat_triples_at_most_1s": len(distinct_triples_under_1s),
        "congestion_identity_windows": len(windows),
        "congestion_windows_with_distinct_triple_within_previous_3s": window_near_fast_triple,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(analyze(args.audit_root), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
