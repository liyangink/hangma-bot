"""对 M=10 漏响应做“从目标查询入队时起优先服务”的局部容量下界。

这不是整段最优排程：入队前的已发送请求固定，入队后的别桌请求全部暂让，
增量长轮询与必要的 seq=0 快照都计入同一身份的状态额度。事件发生只定位到
别席弃牌 POST 的发送至返回区间；输出时间余量，不将乐观可行当成零漏证明。
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
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from analyze_cross_table_bursts import latest_discard
from analyze_state_runtime import analyze_run, rows


@dataclass(frozen=True)
class Query:
    game: str
    queued: float
    granted: float
    completed: float
    status: int | None
    seq0: bool
    events: tuple[dict, ...]


def selected_run(slot: Path, version: str) -> Path:
    """只接受同一身份中一份指定限频版本的完整运行。"""
    matches = []
    for run in (slot / "runs").glob("run-*"):
        payload = json.loads((run / "manifest.json").read_text()).get("payload") or {}
        if payload.get("state_scheduler_version") == version:
            matches.append(run)
    if len(matches) != 1:
        raise ValueError(f"{slot.name}: expected one {version} run, found {len(matches)}")
    return matches[0]


def load_run(run: Path) -> dict:
    """只保留可核对的状态 GET、动作 POST、公开弃牌和时钟采样。"""
    queries: list[Query] = []
    action_responses: dict[tuple[str, int], dict] = {}
    snapshots: list[dict] = []
    event_types: dict[str, dict[int, str]] = defaultdict(dict)
    first_discards: dict[tuple[str, int], tuple[Query, dict]] = {}
    clock_offsets = []
    for path in sorted((run / "participants").glob("*/raw/*.jsonl")):
        for row in rows(path):
            payload = row.get("payload") or {}
            endpoint = str(payload.get("endpoint", ""))
            timing = payload.get("request_timing") or {}
            sampled_wall = timing.get("started_wall_unix_ms")
            sampled_mono = timing.get("started_clock_sample_end_monotonic")
            if sampled_wall is not None and sampled_mono is not None:
                clock_offsets.append(sampled_wall / 1000 - sampled_mono)
            if endpoint.endswith("/action") and "/games/" in endpoint:
                action_responses[(str(payload.get("decision_id")), int(payload.get("attempt_no") or 0))] = {
                    "start": timing.get("transport_started_at_monotonic"),
                    "end": timing.get("completed_at_monotonic"),
                    "status": payload.get("http_status"),
                }
            if not endpoint.endswith("/state") or "/games/" not in endpoint:
                continue
            queued = timing.get("queued_at_monotonic")
            granted = timing.get("granted_at_monotonic")
            completed = timing.get("completed_at_monotonic")
            if any(value is None for value in (queued, granted, completed)):
                continue
            game = endpoint.split("/games/", 1)[1].rsplit("/state", 1)[0]
            try:
                raw = json.loads(payload.get("raw") or "{}")
            except (TypeError, json.JSONDecodeError):
                raw = {}
            query = Query(game, queued, granted, completed, payload.get("http_status"),
                          payload.get("seq_requested") == 0, tuple(raw.get("events") or ()))
            queries.append(query)
            for event in query.events:
                seq, kind = event.get("seq"), event.get("type")
                if not isinstance(seq, int):
                    continue
                if kind in ("tile_discarded", "round_ended"):
                    event_types[game][seq] = kind
                if kind == "tile_discarded":
                    key = (game, seq)
                    if key not in first_discards or completed < first_discards[key][0].completed:
                        first_discards[key] = (query, event)
            snapshot = raw.get("snapshot") or {}
            deadline_ms = snapshot.get("window_deadline_ms")
            if isinstance(deadline_ms, (int, float)) and deadline_ms > 0:
                snapshots.append({"game": game, "round": snapshot.get("round_no"),
                                  "phase": snapshot.get("phase"), "seq": raw.get("seq"),
                                  "deadline_ms": deadline_ms, "completed": completed})
    intents = {}
    for path in sorted((run / "participants").glob("*/decisions.jsonl")):
        for row in rows(path):
            if row.get("kind") != "submission_intent":
                continue
            payload = row.get("payload") or {}
            body = payload.get("body") or {}
            window = payload.get("window") or {}
            if body.get("action") != "discard":
                continue
            context = row.get("context") or {}
            key = (str(payload.get("decision_id") or context.get("decision_id")),
                   int(payload.get("attempt_no") or context.get("attempt_no") or 0))
            intents[key] = {"game": window.get("game_id"), "round": window.get("round_no"),
                            "seat": window.get("seat"), "tile": body.get("tile")}
    actions = []
    for key, intent in intents.items():
        response = action_responses.get(key)
        if response and response["status"] == 200 and response["start"] is not None:
            actions.append({**intent, **response})
    offsets = sorted(clock_offsets)
    if not offsets:
        raise ValueError(f"{run.name}: no clock alignment samples")
    median_offset = statistics.median(offsets)
    return {"queries": queries, "actions": actions, "snapshots": snapshots,
            "event_types": event_types, "first_discards": first_discards,
            "clock_offset": median_offset,
            "clock_offset_span_ms": round((offsets[-1] - offsets[0]) * 1000, 3)}


def earliest_two_gets(grants: list[float], queued: float, event_earliest: float,
                      *, rate: float = 16.0, burst: float = 4.0,
                      window_sec: float = 1.05, spacing_sec: float = 1 / 14.5) -> tuple[float, float]:
    """固定入队前发送账，乐观地让目标两笔 GET 抢占此后的全部额度。

    event_earliest 是同场弃牌 POST 开始的最早可能时刻；忽略 GET 往返、
    事件发送时间、其他桌硬期限及 429，因此结果只可用作时间下界。
    """
    prior = sorted(sent for sent in grants if sent < queued)
    if not prior:
        return queued, max(queued, event_earliest)
    tokens = burst
    previous = prior[0]
    for sent in prior:
        tokens = min(burst, tokens + max(0.0, sent - previous) * rate) - 1.0
        previous = sent
    history = [sent for sent in prior if sent + window_sec > queued]
    next_paced = prior[-1] + spacing_sec if len(prior) >= 16 else -float("inf")

    def take(ready: float) -> float:
        nonlocal tokens, previous, next_paced
        at = max(queued, ready)
        while True:
            tokens = min(burst, tokens + max(0.0, at - previous) * rate)
            previous = at
            while history and at >= history[0] + window_sec:
                history.pop(0)
            later = at
            if tokens < 1.0:
                later = max(later, at + (1.0 - tokens) / rate)
            if len(history) >= 16:
                later = max(later, history[0] + window_sec)
            if next_paced != -float("inf"):
                later = max(later, next_paced)
            if later <= at + 1e-10:
                break
            at = later
        history.append(at)
        tokens -= 1.0
        if len(prior) >= 16:
            next_paced = at + spacing_sec
        return at

    discovery = take(queued)
    snapshot = take(max(discovery, event_earliest))
    return discovery, snapshot


def inspect(audit_root: Path, version: str) -> dict:
    """逐一匹配合法非过漏窗，保留未匹配和无官方截止的未知样本。"""
    runs = {slot.name: selected_run(slot, version) for slot in sorted(audit_root.glob("slot-*"))}
    data = {name: load_run(run) for name, run in runs.items()}
    actions = [(name, action) for name, item in data.items() for action in item["actions"]]
    report = []
    for name, run in runs.items():
        item = data[name]
        grant_times = sorted(query.granted for query in item["queries"])
        for window in analyze_run(run)["no_input_rule_reconstruction"]["candidate_windows"]:
            game, trigger = window["game_id"], window["trigger_seq"]
            physical = latest_discard(item["event_types"], game, trigger)
            located = item["first_discards"].get((game, physical))
            summary = {"slot": name, "game": game.split("_")[-2],
                       "round": window["round_no"], "trigger_seq": trigger,
                       "phase": window["phase"], "physical_discard_seq": physical}
            if located is None:
                report.append({**summary, "evidence": "unmatched_discard"})
                continue
            target, event = located
            matches = [(source, action) for source, action in actions
                       if source != name and action["game"] == game
                       and action["round"] == window["round_no"]
                       and action["seat"] == event.get("seat")
                       and action["tile"] == event.get("tile")
                       and action["start"] <= target.completed + 0.01
                       and action["end"] >= target.queued - 2.0]
            if len(matches) != 1:
                report.append({**summary, "evidence": "ambiguous_discard_post",
                               "post_matches": len(matches)})
                continue
            source, action = matches[0]
            sender_offset = data[source]["clock_offset"]
            receiver_offset = item["clock_offset"]
            event_start = action["start"] + sender_offset - receiver_offset
            event_end = action["end"] + sender_offset - receiver_offset
            # 同一官方窗口的 deadline 是墙上时钟毫秒；别席若恰好拉到该
            # 弃牌阶段，也可为本席补充同 game/round/seq/phase 的期限证据。
            deadline_rows = [snap for peer in data.values() for snap in peer["snapshots"]
                             if snap["game"] == game and snap["round"] == window["round_no"]
                             and snap["phase"] == window["phase"] and snap["seq"] == trigger]
            deadline_ms = min((snap["deadline_ms"] for snap in deadline_rows), default=None)
            # 吃窗可能以另一事件 seq 投递：只在目标弃牌和下次弃牌之间查找
            # 同阶段快照，且要求其收到时间晚于弃牌 POST、早于下一物理弃牌。
            if deadline_ms is None and window["phase"] == "response_chi":
                later_discards = [seq for g, seq in item["first_discards"]
                                  if g == game and isinstance(physical, int) and seq > physical]
                end_of_cycle = min(later_discards, default=float("inf"))
                fallback = [snap for snap in item["snapshots"]
                            if snap["game"] == game and snap["round"] == window["round_no"]
                            and snap["phase"] == "response_chi"
                            and physical <= snap["seq"] < end_of_cycle
                            and event_start <= snap["completed"]]
                deadline_ms = min((snap["deadline_ms"] for snap in fallback), default=None)
            # 吃窗在碰窗超时后才开启，最早弃牌 GET 不是发现吃窗的查询。
            # 不能把两阶段之间的约 1 秒当作吃窗仍可使用的排队余量。
            next_physical_discard = min((seq for g, seq in item["first_discards"]
                                         if g == game and isinstance(physical, int) and seq > physical),
                                        default=float("inf"))
            phase_snapshot_rows = [snap for snap in item["snapshots"]
                                   if snap["game"] == game
                                   and snap["round"] == window["round_no"]
                                   and snap["phase"] == window["phase"]
                                   and (snap["seq"] == trigger if window["phase"] != "response_chi"
                                        else isinstance(physical, int) and isinstance(snap["seq"], int)
                                        and physical <= snap["seq"] < next_physical_discard)
                                   and snap["completed"] >= event_start]
            discovery, snapshot = earliest_two_gets(grant_times, target.queued, event_start)
            deadline = deadline_ms / 1000 - receiver_offset if deadline_ms is not None else None
            two_get_projection_applies = window["phase"] != "response_chi"
            report.append({**summary, "evidence": "matched",
                           "source_slot": source, "post_interval_ms": round(1000 * (event_end - event_start), 1),
                           "target_queue_ms": round(1000 * (target.granted - target.queued), 1),
                           "observed_event_after_queue_ms": round(1000 * (target.completed - target.queued), 1),
                           "local_earliest_discovery_ms": round(1000 * (discovery - target.queued), 1),
                           "local_earliest_snapshot_ms": round(1000 * (snapshot - target.queued), 1),
                           "official_deadline": deadline is not None,
                           "phase_snapshot_slack_ms": (
                               round(1000 * (deadline - min(snap["completed"] for snap in phase_snapshot_rows)), 1)
                               if deadline is not None and phase_snapshot_rows else None),
                           "observed_event_slack_ms": (
                               round(1000 * (deadline - target.completed), 1)
                               if deadline is not None and two_get_projection_applies else None),
                           "optimistic_snapshot_slack_ms": (
                               round(1000 * (deadline - snapshot), 1)
                               if deadline is not None and two_get_projection_applies else None),
                           "clock_offset_span_ms": max(item["clock_offset_span_ms"],
                                                       data[source]["clock_offset_span_ms"]),
                           "rate429_during_wait": sum(query.status == 429
                                                       and target.queued < query.completed < target.granted
                                                       for query in item["queries"])})
    matched = [row for row in report if row["evidence"] == "matched"]
    with_deadline = [row for row in matched if row["official_deadline"]]
    projected = [row for row in with_deadline if row["optimistic_snapshot_slack_ms"] is not None]
    return {"version": version,
            "method": "碰窗固定入队前本身份发起账，之后让目标增量 GET 与必要的 seq=0 快照抢占别桌；吃窗须先等碰窗结束，只报告实测吃窗快照余量，不套用弃牌时刻的两 GET 预演。忽略网络/策略耗时、其他硬期限和 429，故余量是乐观上界，不是可行性证明。",
            "count": {"candidate": len(report), "post_matched": len(matched),
                      "official_deadline": len(with_deadline),
                      "optimistic_snapshot_assessed": len(projected),
                      "optimistic_snapshot_after_deadline": sum(
                          row["optimistic_snapshot_slack_ms"] <= 0 for row in projected)},
            "rows": report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_root", type=Path)
    parser.add_argument("--version", default="burst4-fair-paced-v1")
    args = parser.parse_args()
    print(json.dumps(inspect(args.audit_root, args.version), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
