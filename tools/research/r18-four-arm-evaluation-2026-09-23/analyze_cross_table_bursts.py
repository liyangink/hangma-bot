"""按同一身份的十场时间线，核查 M=10 漏响应前后的状态请求。

只输出场次后缀、序号、请求及公开事件类型的聚合；不输出凭据或手牌。
事件没有官方发生时间，因此“事件”只按本地收到响应的时间统计。
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
import bisect
import json
from collections import Counter, defaultdict
from pathlib import Path

from analyze_state_runtime import analyze_run, rows


def percentile(values: list[float], p: float) -> float | None:
    """返回最近秩百分位，空样本返回 None。"""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1, int(len(ordered) * p + .999999) - 1))], 1)


def load_timeline(run: Path) -> tuple[list[dict], dict, dict]:
    """读取单身份全部场次的 GET 时间和可公开辨识的事件序号。"""
    requests = []
    event_types: dict[str, dict[int, str]] = defaultdict(dict)
    discard_first: dict[tuple[str, int], dict] = {}
    for path in sorted((run / "participants").glob("*/raw/*.jsonl")):
        for row in rows(path):
            payload = row.get("payload") or {}
            endpoint = str(payload.get("endpoint", ""))
            if not endpoint.endswith("/state") or "/games/" not in endpoint:
                continue
            timing = payload.get("request_timing") or {}
            queued = timing.get("queued_at_monotonic")
            granted = timing.get("granted_at_monotonic")
            completed = timing.get("completed_at_monotonic")
            if queued is None or granted is None or completed is None:
                continue
            try:
                raw = json.loads(payload.get("raw") or "{}")
            except (TypeError, json.JSONDecodeError):
                raw = {}
            events = [(e.get("seq"), e.get("type")) for e in raw.get("events") or ()]
            game = endpoint.split("/games/", 1)[1].rsplit("/state", 1)[0]
            item = {
                "game": game,
                "q": queued,
                "g": granted,
                "d": completed,
                "purpose": timing.get("query_purpose"),
                "scheduler_priority": timing.get("scheduler_priority"),
                "seq0": payload.get("seq_requested") == 0,
                "status": payload.get("http_status"),
                "events": events,
            }
            requests.append(item)
            for seq, kind in events:
                if not isinstance(seq, int):
                    continue
                if kind in ("tile_discarded", "round_ended"):
                    event_types[game][seq] = kind
                if kind == "tile_discarded":
                    key = (game, seq)
                    prior = discard_first.get(key)
                    if prior is None or item["d"] < prior["d"]:
                        discard_first[key] = item
    requests.sort(key=lambda x: x["q"])
    return requests, event_types, discard_first


def latest_discard(event_types: dict, game: str, seq: int) -> int | None:
    """取同一单局内不晚于响应触发序号的最后一次弃牌。"""
    if not isinstance(seq, int):
        return None
    kinds = event_types.get(game, {})
    ordered = sorted(kinds)
    for index in range(bisect.bisect_right(ordered, seq) - 1, -1, -1):
        event_seq = ordered[index]
        if kinds[event_seq] == "round_ended":
            return None
        return event_seq
    return None


def metrics(target: dict, requests: list[dict]) -> dict:
    """只用同一身份的本地单调时钟，计算目标 GET 前后拥塞。"""
    q, g = target["q"], target["g"]
    before = [r for r in requests if q - 1 <= r["q"] < q]
    recent_events = [r for r in requests if q - 1 <= r["d"] < q and r["events"]]
    after = [r for r in requests if q <= r["q"] < q + 1 and r is not target]
    ahead = [r for r in requests if q < r["g"] < g and r is not target]
    backlog = [r for r in requests if r["q"] < q < r["g"]]
    event_count = Counter(kind for r in recent_events for _, kind in r["events"])
    return {
        "queue_ms": round(1000 * (g - q), 1),
        "network_ms": round(1000 * (target["d"] - g), 1),
        "queued_prev_1s": len(before),
        "queued_next_1s": len(after),
        "tables_prev_1s": len({r["game"] for r in before}),
        "tables_next_1s": len({r["game"] for r in after}),
        "backlog_at_queue": len(backlog),
        "granted_prev_1s": sum(q - 1 <= r["g"] < q for r in requests),
        "other_granted_ahead": len(ahead),
        "other_tables_ahead": len({r["game"] for r in ahead if r["game"] != target["game"]}),
        "event_responses_prev_1s": len(recent_events),
        "event_tables_prev_1s": len({r["game"] for r in recent_events}),
        "event_types_prev_1s": dict(event_count),
        "seq0_prev_1s": sum(r["seq0"] for r in before),
        "rate429_prev_2s": sum(r["status"] == 429 and q - 2 <= r["d"] < q for r in requests),
        "rate429_during_wait": sum(r["status"] == 429 and q < r["d"] < g for r in requests),
        "ahead_no_events": sum(not r["events"] for r in ahead),
        "ahead_only_timeout_pass": sum(
            bool(r["events"]) and {kind for _, kind in r["events"]} <= {"timeout", "pass"}
            for r in ahead
        ),
        "ahead_seq0": sum(r["seq0"] for r in ahead),
        "purpose": target["purpose"],
    }


def inspect_run(run: Path) -> dict:
    """同一运行中对照未交付的可鸣牌窗与成功交付的可鸣牌窗。"""
    analyzed = analyze_run(run)
    requests, event_types, discard_first = load_timeline(run)
    misses = []
    unmatched_misses = []
    chi_not_assessed = []
    for window in analyzed["no_input_rule_reconstruction"]["candidate_windows"]:
        game, seq = window["game_id"], window["trigger_seq"]
        if window["phase"] == "response_chi":
            # 吃窗由碰窗超时后开放，弃牌首笔 GET 的拥堵不是吃窗发现链。
            chi_not_assessed.append({"game": game.split("_")[-2], "seq": seq,
                                     "phase": window["phase"]})
            continue
        physical = latest_discard(event_types, game, seq)
        target = discard_first.get((game, physical))
        if target is None:
            unmatched_misses.append({"game": game.split("_")[-2], "seq": seq})
            continue
        misses.append({
            "game": game.split("_")[-2],
            "round": window["round_no"],
            "seq": seq,
            "discard_seq": physical,
            "phase": window["phase"],
            **metrics(target, requests),
        })
    inputs = []
    for path in sorted((run / "participants").glob("*/decisions.jsonl")):
        for row in rows(path):
            if row.get("kind") != "decision_input":
                continue
            payload = row.get("payload") or {}
            window = payload.get("window") or {}
            if window.get("phase") not in ("response_peng", "response_chi"):
                continue
            if window.get("phase") == "response_chi":
                continue
            legal = ((payload.get("request") or {}).get("rules") or {}).get("legal_candidates") or []
            if not any(c.get("action_key") != "pass" for c in legal):
                continue
            game, seq = window.get("game_id"), window.get("trigger_seq")
            physical = latest_discard(event_types, game, seq)
            target = discard_first.get((game, physical))
            if target is None or target["d"] > (row.get("monotonic_ns") or 0) / 1e9 + .01:
                continue
            inputs.append((game, window.get("round_no"), window.get("phase"), physical, target))
    seen = set()
    successes = []
    for game, round_no, phase, physical, target in inputs:
        key = (game, round_no, phase, physical)
        if key in seen:
            continue
        seen.add(key)
        successes.append(metrics(target, requests))
    return {
        "run": run.name,
        "miss_total": len(analyzed["no_input_rule_reconstruction"]["candidate_windows"]),
        "miss_matched": misses,
        "miss_unmatched": unmatched_misses,
        "miss_chi_not_assessed": chi_not_assessed,
        "success_matched_count": len(successes),
        "success_matched": successes,
    }


def summarize(items: list[dict]) -> dict:
    """给出易核对的中位数、尾部和比例，不作随机实验因果声明。"""
    fields = (
        "queue_ms", "network_ms", "queued_prev_1s", "queued_next_1s",
        "tables_prev_1s", "tables_next_1s", "backlog_at_queue",
        "granted_prev_1s", "other_granted_ahead", "other_tables_ahead",
        "event_responses_prev_1s", "event_tables_prev_1s", "seq0_prev_1s",
        "ahead_no_events", "ahead_only_timeout_pass", "ahead_seq0",
    )
    return {
        "count": len(items),
        "median": {key: percentile([item[key] for item in items], .5) for key in fields},
        "p90": {key: percentile([item[key] for item in items], .9) for key in fields},
        "share": {
            "queue_over_1s": sum(item["queue_ms"] > 1000 for item in items),
            "prev_plus_target_over_16": sum(item["queued_prev_1s"] + 1 > 16 for item in items),
            "prev_tables_at_least_8": sum(item["tables_prev_1s"] >= 8 for item in items),
            "prev_event_tables_at_least_5": sum(item["event_tables_prev_1s"] >= 5 for item in items),
            "backlog_at_least_5": sum(item["backlog_at_queue"] >= 5 for item in items),
            "no_429_prev_2s": sum(item["rate429_prev_2s"] == 0 for item in items),
            "429_during_wait": sum(item["rate429_during_wait"] > 0 for item in items),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_root", type=Path)
    parser.add_argument("--version", default="burst4-fair-paced-v1")
    args = parser.parse_args()
    by_slot = {}
    for slot in sorted(args.audit_root.glob("slot-*")):
        runs = []
        for run in (slot / "runs").glob("run-*"):
            manifest = json.loads((run / "manifest.json").read_text()).get("payload") or {}
            if manifest.get("state_scheduler_version") == args.version:
                runs.append(run)
        if len(runs) != 1:
            raise ValueError(f"{slot.name}: expected one {args.version} run, found {len(runs)}")
        by_slot[slot.name] = inspect_run(runs[0])
    misses = [item for slot in by_slot.values() for item in slot["miss_matched"]]
    successes = [item for slot in by_slot.values() for item in slot["success_matched"]]
    output = {
        "version": args.version,
        "evidence_limit": "事件无官方发生时间；拥堵统计仅对碰窗首个弃牌 GET 计算，吃窗需另按碰窗结束后的阶段转换链分析；不同测试批次牌山不同。",
        "miss_summary": summarize(misses),
        "success_summary": summarize(successes),
        "miss_total": sum(slot["miss_total"] for slot in by_slot.values()),
        "miss_unmatched": [item for slot in by_slot.values() for item in slot["miss_unmatched"]],
        "miss_chi_not_assessed": [item for slot in by_slot.values()
                                   for item in slot["miss_chi_not_assessed"]],
        "miss_details": {name: slot["miss_matched"] for name, slot in by_slot.items()},
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
