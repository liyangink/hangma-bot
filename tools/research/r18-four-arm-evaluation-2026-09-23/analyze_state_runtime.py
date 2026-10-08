"""汇总测试房审计中的状态排队、额度拒绝及未交付的可鸣候选。

输入为四身份审计根目录；仅输出聚合量和场次窗口标识，不输出原始牌谱、手牌或凭据。
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

from hangma_bot.adapters.official.dto import parse_snapshot, parse_state_response
from hangma_bot.adapters.official.projector import observation
from hangma_bot.adapters.official.sync_state import ProtocolSyncState, SyncDecision
from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.config import RuleConfig, TimingConfig


def rows(path: Path):
    """跳过运行中尚未冲刷完整的末尾行；正式结算仍须审计完整性为 complete。"""
    with path.open() as handle:
        for line in handle:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def percentile(values: list[float], percentage: float) -> float | None:
    """返回按排序取最近秩的毫秒分位数；无样本返回空值。"""
    if not values:
        return None
    values = sorted(values)
    index = max(0, min(len(values) - 1, int(len(values) * percentage + .999999) - 1))
    return round(values[index], 1)


def reconstruct_no_input_windows(run: Path, manifest: dict, decisions: dict[str, dict]) -> dict:
    """按真实弃牌周期去重后，重建未进入策略的响应候选；缺证据保持未知。"""
    targets = {}
    for item in decisions.values():
        finish = item.get("ended") or {}
        window = finish.get("window") or {}
        if (finish.get("end_reason") != "deadline" or item.get("input")
                or window.get("phase") not in ("response_peng", "response_chi")):
            continue
        key = (window.get("game_id"), window.get("round_no"),
               window.get("trigger_seq"), window.get("phase"), window.get("seat"))
        targets[key] = None
    if not targets:
        return {"pass_only": 0, "unknown": 0, "candidate_windows": [],
                "unknown_windows": [], "previously_handled": 0,
                "previously_handled_windows": []}
    # 旧同步器在已处理吃窗之后收到本人摸打增量，可能把旧快照以新 seq
    # 再投递一次。这类 decision_ended 没有 input，却不是错失的新响应。
    # 仅当原始连续事件能证明同一弃牌、同一阶段已有策略输入时才排除。
    event_kinds: dict[str, dict[int, str]] = defaultdict(dict)
    for path in sorted((run / "participants").glob("*/raw/*.jsonl")):
        for row in rows(path):
            payload = row.get("payload") or {}
            endpoint = str(payload.get("endpoint", ""))
            if not endpoint.endswith("/state") or "/games/" not in endpoint:
                continue
            game_id = endpoint.split("/games/", 1)[1].rsplit("/state", 1)[0]
            if not any(key[0] == game_id for key in targets):
                continue
            try:
                raw = json.loads(payload.get("raw") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            for event in raw.get("events") or ():
                if event.get("type") in ("tile_discarded", "round_ended") and isinstance(event.get("seq"), int):
                    event_kinds[game_id][event["seq"]] = event["type"]
    event_seqs = {game_id: sorted(kinds) for game_id, kinds in event_kinds.items()}

    def physical_discard_seq(game_id: str, trigger_seq: int) -> int | None:
        """找到当前单局最后一条公开弃牌；跨过终局或缺事件时保持未知。"""
        ordered = event_seqs.get(game_id, ())
        for index in range(bisect.bisect_right(ordered, trigger_seq) - 1, -1, -1):
            seq = ordered[index]
            if event_kinds[game_id][seq] == "round_ended":
                break
            return seq
        return None

    handled = set()
    for item in decisions.values():
        if not item.get("input"):
            continue
        window = item.get("input_window") or (item.get("ended") or {}).get("window") or {}
        game_id, seq = window.get("game_id"), window.get("trigger_seq")
        if game_id and isinstance(seq, int):
            physical = physical_discard_seq(game_id, seq)
            if physical is not None:
                handled.add((game_id, window.get("round_no"), window.get("phase"), physical))
    repeated = []
    for key in tuple(targets):
        physical = physical_discard_seq(key[0], key[2])
        if physical is not None and (key[0], key[1], key[3], physical) in handled:
            repeated.append({"game_id": key[0], "round_no": key[1],
                             "trigger_seq": key[2], "phase": key[3],
                             "physical_discard_seq": physical})
            del targets[key]
    if not targets:
        return {"pass_only": 0, "unknown": 0, "candidate_windows": [],
                "unknown_windows": [], "previously_handled": len(repeated),
                "previously_handled_windows": repeated}
    for path in sorted((run / "participants").glob("*/raw/*.jsonl")):
        for row in rows(path):
            payload = row.get("payload") or {}
            endpoint = str(payload.get("endpoint", ""))
            if not endpoint.endswith("/state") or "/games/" not in endpoint:
                continue
            game_id = endpoint.split("/games/", 1)[1].rsplit("/state", 1)[0]
            if not any(key[0] == game_id for key in targets):
                continue
            try:
                raw = json.loads(payload.get("raw") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            snapshot = raw.get("snapshot") or {}
            key = (game_id, snapshot.get("round_no"), raw.get("seq"),
                   snapshot.get("phase"), snapshot.get("seat"))
            if key in targets and targets[key] is None:
                targets[key] = snapshot
    # 增量窗口没有同序号快照时，只接受生产同步器能从连续公开事件证明的
    # 玩家观察；无法重建、规则降级和缺口均保持未知，不把它们算作安全过牌。
    replayed = {}
    unresolved = {key for key, snapshot in targets.items() if snapshot is None}
    if unresolved:
        raw_by_game: dict[str, list[dict]] = defaultdict(list)
        for path in sorted((run / "participants").glob("*/raw/*.jsonl")):
            for row in rows(path):
                payload = row.get("payload") or {}
                endpoint = str(payload.get("endpoint", ""))
                if not endpoint.endswith("/state") or "/games/" not in endpoint:
                    continue
                game_id = endpoint.split("/games/", 1)[1].rsplit("/state", 1)[0]
                if any(key[0] == game_id for key in unresolved) and payload.get("http_status") == 200:
                    raw_by_game[game_id].append(row)
        for game_id, state_rows in raw_by_game.items():
            sync = ProtocolSyncState(game_id, TimingConfig(1.0, 1.0, 3.0))
            for row in sorted(state_rows, key=lambda item: item.get("monotonic_ns") or 0):
                try:
                    parsed = parse_state_response(json.loads((row.get("payload") or {}).get("raw") or "{}"))
                    if parsed.kind in ("snapshot", "finished"):
                        sync.apply_full_snapshot(parsed.snapshot, finished=parsed.finished,
                                                 events=parsed.events)
                    elif parsed.kind == "events":
                        result = sync.apply_events(parsed.events, gap=parsed.gap)
                        if result.decision is SyncDecision.NEEDS_REBUILD:
                            continue
                    else:
                        continue
                    detected = sync.current_window()
                    if detected is not None:
                        obs = sync.current_observation()
                        key = (game_id, detected.window_key.round_no,
                               detected.window_key.trigger_seq,
                               detected.window_key.phase.value, detected.window_key.seat)
                        if obs is not None and key in unresolved and key not in replayed:
                            replayed[key] = obs
                    obs = sync.incremental_response_observation()
                    if obs is not None and obs.last_discard is not None:
                        key = (game_id, obs.round_no, obs.last_discard.seq, obs.phase, obs.seat)
                        if key in unresolved and key not in replayed:
                            replayed[key] = obs
                except Exception:  # 断链或损坏不补造状态；等下一份权威快照
                    continue
    rules = HangmaRules(RuleConfig(
        manifest.get("ruleset_version") or "offline-snapshot-audit",
        manifest.get("base_score") or 1, bool(manifest.get("you_cai_bi_kao"))))
    pass_only = unknown = 0
    candidates = []
    unknown_windows = []
    for key, raw_snapshot in sorted(targets.items()):
        if raw_snapshot is None and key not in replayed:
            unknown += 1
            unknown_windows.append({"game_id": key[0], "round_no": key[1],
                                    "trigger_seq": key[2], "phase": key[3]})
            continue
        try:
            obs = replayed[key] if raw_snapshot is None else observation(
                parse_snapshot(raw_snapshot, key[2]), (), key[0])
            analysis = rules.analyze(obs)
            if analysis.issues:
                unknown += 1
                unknown_windows.append({"game_id": key[0], "round_no": key[1],
                                        "trigger_seq": key[2], "phase": key[3]})
                continue
            actions = [candidate.action_key for candidate in analysis.legal_candidates
                       if candidate.action_key != "pass"]
        except Exception:  # 异常不当作无候选，保持审计未知
            unknown += 1
            unknown_windows.append({"game_id": key[0], "round_no": key[1],
                                    "trigger_seq": key[2], "phase": key[3]})
            continue
        if actions:
            candidates.append({"game_id": key[0], "round_no": key[1],
                               "trigger_seq": key[2], "phase": key[3],
                               "action_keys": actions})
        else:
            pass_only += 1
    return {"pass_only": pass_only, "unknown": unknown,
            "candidate_windows": candidates, "unknown_windows": unknown_windows,
            "previously_handled": len(repeated), "previously_handled_windows": repeated}


def analyze_run(run: Path) -> dict:
    manifest = json.loads((run / "manifest.json").read_text()).get("payload", {})
    raw_files = sorted((run / "participants").glob("*/raw/*.jsonl"))
    purposes = Counter()
    origins = Counter()
    priorities = Counter()
    queue_ms: dict[str, list[float]] = defaultdict(list)
    priority_queue_ms: dict[str, list[float]] = defaultdict(list)
    network_ms: list[float] = []
    gets = rate_limited = full_snapshots = 0
    for path in raw_files:
        for row in rows(path):
            payload = row.get("payload") or {}
            if not str(payload.get("endpoint", "")).endswith("/state"):
                continue
            gets += 1
            rate_limited += payload.get("http_status") == 429
            full_snapshots += payload.get("seq_requested") == 0
            timing = payload.get("request_timing") or {}
            purpose = timing.get("query_purpose") or "unknown"
            purposes[purpose] += 1
            if timing.get("query_origin"):
                origins[timing["query_origin"]] += 1
            priority = timing.get("scheduler_priority")
            if priority:
                priorities[priority] += 1
            queued, granted = timing.get("queued_at_monotonic"), timing.get("granted_at_monotonic")
            if queued is not None and granted is not None:
                queue_ms[purpose].append(1000 * (granted - queued))
                if priority:
                    priority_queue_ms[priority].append(1000 * (granted - queued))
            started, completed = timing.get("transport_started_at_monotonic"), timing.get("completed_at_monotonic")
            if started is not None and completed is not None:
                network_ms.append(1000 * (completed - started))

    decision_rows = sorted((run / "participants").glob("*/decisions.jsonl"))
    decisions: dict[str, dict] = defaultdict(dict)
    ended = Counter()
    for path in decision_rows:
        for row in rows(path):
            kind = row.get("kind")
            if kind not in ("decision_input", "decision_planned", "candidate_validated",
                            "submission_intent", "decision_ended"):
                continue
            context = row.get("context") or {}
            decision_id = context.get("decision_id")
            if not decision_id:
                continue
            payload = row.get("payload") or {}
            item = decisions[decision_id]
            item.setdefault("context", context)
            if kind == "decision_input":
                item["input"] = True
                item["input_window"] = payload.get("window")
            elif kind == "decision_planned":
                candidates = ((payload.get("returned_plan") or {}).get("candidates") or [])
                item["first"] = candidates[0].get("action_key") if candidates else None
            elif kind == "candidate_validated":
                if payload.get("legal"):
                    item.setdefault("legal", set()).add(payload.get("action_key"))
            elif kind == "submission_intent":
                item["intent"] = True
            elif kind == "decision_ended":
                item["ended"] = payload
                phase = (payload.get("window") or {}).get("phase") or "unknown"
                ended[(phase, payload.get("end_reason"))] += 1

    selected_nonpass_misses = []
    for item in decisions.values():
        finish = item.get("ended") or {}
        phase = (finish.get("window") or {}).get("phase")
        first = item.get("first")
        if (phase in ("response_peng", "response_chi") and first not in (None, "pass")
                and finish.get("sent_attempts") == 0
                and finish.get("end_reason") == "deadline"):
            context = item["context"]
            selected_nonpass_misses.append({
                "game_id": context.get("game_id"), "round_no": context.get("round_no"),
                "trigger_seq": context.get("trigger_seq"), "first_action": first,
                "validated_legal": first in item.get("legal", set()),
                "intent": bool(item.get("intent")),
            })

    games = sum(any(row.get("kind") == "game_finished" for row in rows(path))
                for path in (run / "participants").glob("*/games/*.jsonl"))
    all_queue = [value for values in queue_ms.values() for value in values]
    no_input_response_deadlines = sum(
        1 for item in decisions.values()
        if (item.get("ended") or {}).get("end_reason") == "deadline"
        and ((item.get("ended") or {}).get("window") or {}).get("phase")
        in ("response_peng", "response_chi")
        and not item.get("input"))
    no_input_reconstruction = reconstruct_no_input_windows(run, manifest, decisions)
    # 按原始触发原因而非最终 query_purpose 计数；过期用途可能改查当前快照。
    # sse_idle 为旧版审计名，保留以便历史房间与新版按同口径比较。
    watchdog_origins = (
        "phase_boundary", "sse_boundary", "sse_own_discard_probe", "sse_phase_probe",
        "sse_silence_probe", "sse_state_age_probe", "sse_settled_probe", "sse_idle",
    )
    complete_origins = sum(origins.values()) == gets
    watchdog_by_origin = {origin: origins[origin] for origin in watchdog_origins if origins[origin]}
    watchdog_gets = sum(watchdog_by_origin.values())
    return {
        "run_id": manifest.get("run_id"),
        "max_games": manifest.get("max_games"), "rounds_per_game": manifest.get("rounds_per_game"),
        "sync_mode": manifest.get("official_sync_mode"), "sse_effective": manifest.get("sse_effective"),
        "state_scheduler_version": manifest.get("state_scheduler_version"),
        "completed_games": games, "state_get": gets, "state_429": rate_limited,
        "seq0": full_snapshots, "purpose_counts": dict(purposes),
        # 旧审计缺 query_origin 时为 None，不能拿最终查询用途冒充看门狗总量。
        "query_origin_coverage": sum(origins.values()),
        "watchdog_state_get_by_origin": watchdog_by_origin if complete_origins else None,
        "watchdog_state_get": watchdog_gets if complete_origins else None,
        "watchdog_state_get_pct": (
            round(100 * watchdog_gets / gets, 4)
            if gets and complete_origins else None
        ),
        "priority_counts": dict(priorities),
        "queue_p95_ms": percentile(all_queue, .95),
        "network_p95_ms": percentile(network_ms, .95),
        "purpose_queue_p95_ms": {purpose: percentile(values, .95)
                                 for purpose, values in sorted(queue_ms.items())},
        "priority_queue_p95_ms": {priority: percentile(values, .95)
                                   for priority, values in sorted(priority_queue_ms.items())},
        "response_deadlines": sum(count for (phase, reason), count in ended.items()
                                  if phase in ("response_peng", "response_chi") and reason == "deadline"),
        "response_deadlines_without_input": no_input_response_deadlines,
        "no_input_rule_reconstruction": no_input_reconstruction,
        "selected_nonpass_deadline_misses": selected_nonpass_misses,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_root", type=Path)
    args = parser.parse_args()
    result = {}
    for slot in sorted(args.audit_root.glob("slot-*")):
        runs = sorted((slot / "runs").glob("run-*"), key=lambda path: path.stat().st_mtime)
        if runs:
            result[slot.name] = analyze_run(runs[-1])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
