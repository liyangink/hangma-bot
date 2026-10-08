"""按优先级和上一条事件审视长轮询能否暂缓；不作反事实安全推断。"""

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
    """读取已完成审计中的完整 JSONL 行。"""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _previous_kind(request: dict) -> str:
    """以已经收到的事件给上一条 GET 分类，类别互斥。"""
    kinds = request["event_types"]
    if request["seq0"]:
        return "snapshot"
    if not kinds:
        return "empty_or_429"
    if "tile_drawn" in kinds:
        return "tile_drawn"
    if "tile_discarded" in kinds:
        return "tile_discarded"
    if "chi" in kinds or "peng" in kinds:
        return "claim"
    if "timeout" in kinds:
        return "response_timeout"
    if "pass" in kinds:
        return "response_pass_only"
    if "round_ended" in kinds or "game_ended" in kinds:
        return "round_end"
    return "other_events"


def analyze(root: Path) -> dict:
    """聚合四身份最后一次运行；直接碰窗计数可能重复，不代表安全概率。"""
    classes = defaultdict(Counter)
    predecessors = defaultdict(Counter)
    for slot in sorted(root.glob("slot-*")):
        runs = sorted((slot / "runs").glob("run-*"), key=lambda path: path.stat().st_mtime)
        if not runs:
            raise ValueError(f"{slot.name}: 没有审计运行")
        run = runs[-1]
        peng_inputs = set()
        for path in (run / "participants").glob("*/decisions.jsonl"):
            for row in _rows(path):
                if row.get("kind") != "decision_input":
                    continue
                payload = row.get("payload") or {}
                if (payload.get("window") or {}).get("phase") == "response_peng":
                    context = row.get("context") or {}
                    peng_inputs.add((context.get("game_id"), context.get("trigger_seq")))

        by_game = defaultdict(list)
        for path in (run / "participants").glob("*/raw/t_*.jsonl"):
            for row in _rows(path):
                payload = row.get("payload") or {}
                endpoint = str(payload.get("endpoint", ""))
                if not endpoint.endswith("/state") or "/games/" not in endpoint:
                    continue
                timing = payload.get("request_timing") or {}
                queued = timing.get("queued_at_monotonic")
                if queued is None:
                    continue
                game_id = endpoint.split("/games/", 1)[1].rsplit("/state", 1)[0]
                try:
                    body = json.loads(payload.get("raw") or "{}")
                except (TypeError, ValueError):
                    body = {}
                events = body.get("events") or ()
                discard_seqs = {event.get("seq") for event in events
                                if event.get("type") == "tile_discarded"}
                request = {
                    "queued": queued,
                    "seq0": payload.get("seq_requested") == 0,
                    "purpose": timing.get("query_purpose"),
                    "priority": timing.get("scheduler_priority"),
                    "event_types": {event.get("type") for event in events},
                    "has_discard": bool(discard_seqs),
                    "direct_peng_input": any((game_id, seq) in peng_inputs for seq in discard_seqs),
                    "history_backfill": "history_after_seq" in timing,
                }
                by_game[game_id].append(request)
                if not request["seq0"]:
                    label = f"{request['purpose']}/{request['priority']}"
                    counts = classes[label]
                    counts["queries"] += 1
                    counts["returned_discard"] += request["has_discard"]
                    counts["direct_peng_input"] += request["direct_peng_input"]
                    counts["history_backfill"] += request["history_backfill"]

        for requests in by_game.values():
            requests.sort(key=lambda item: item["queued"])
            for previous, current in zip(requests, requests[1:]):
                if (current["purpose"], current["priority"]) != ("discard_watch", "DISCARD_WATCH"):
                    continue
                counts = predecessors[_previous_kind(previous)]
                counts["queries"] += 1
                counts["returned_discard"] += current["has_discard"]
                counts["direct_peng_input"] += current["direct_peng_input"]
    return {
        "scope": "四席最后一次完整运行；seq>0 状态请求；碰窗匹配为查询级次数，非因果延迟实验",
        "longpoll_by_purpose_priority": {key: dict(value) for key, value in sorted(classes.items())},
        "discard_watch_after_previous_response": {
            key: dict(value) for key, value in sorted(predecessors.items())},
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
