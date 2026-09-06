"""赛后复核本人实际收到的事件和快照，复用生产投影与规则转移检查。

按 run/participant/game 隔离；只比较已保留的证据，不补造官方未返回历史。
这是赛后集合复核，不证明事件在动作截止时间前已到达。
"""
import json
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path

from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import observation, public_event
from hangma_bot.adapters.recording.reader import read_records
from hangma_bot.hangma.observation_rules import compare_observation_transition, enrich_observation
from hangma_bot.kernel.serialization import public_event_to_json


def audit_observations(run: Path, *, ruleset_version: str, official: list[dict] | None = None) -> dict:
    """返回有文件/行号的快照转移与历史封存核验；缺 raw 明确为未检查。"""
    read = read_records(run)
    groups = defaultdict(lambda: {"events": {}, "raw_events": {}, "seats": set(), "snapshots": [], "closures": [], "issues": []})
    for record in read.records:
        context, payload = record.context or {}, record.payload or {}
        if not context.get("game_id") or not context.get("participant_id"):
            continue
        group = groups[(context["participant_id"], context["game_id"])]
        ref = {"file": record.relative_path, "line": record.line_no}
        if payload.get("history_closure"):
            group["closures"].append((ref, payload))
        if record.kind != "raw_protocol_state" or payload.get("source") != "state_response":
            continue
        try:
            raw = payload.get("raw")
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, dict):
                raise ValueError("raw_missing_or_not_object")
            for raw_event in data.get("events") or []:
                group["raw_events"].setdefault(raw_event["seq"], raw_event)
            response = parse_state_response(data)
            for event in response.events:
                projected = public_event(event)
                if event.seq in group["events"] and group["events"][event.seq] != projected:
                    group["issues"].append({**ref, "issue": "received_seq_conflict", "seq": event.seq})
                else:
                    group["events"][event.seq] = projected
            if response.snapshot is not None:
                group["seats"].add(response.snapshot.seat)
                group["snapshots"].append((data["seq"], ref, response.snapshot))
        except (ValueError, KeyError, TypeError) as exc:
            group["issues"].append({**ref, "issue": "raw_unparseable", "reason": str(exc)})
    reports = []
    for (pid, gid), group in sorted(groups.items()):
        events, outcomes, pairs, failures = group["events"], Counter(), 0, []
        before = None
        for seq, ref, snapshot in sorted(group["snapshots"], key=lambda x: x[0]):
            try:
                start = max((s for s, e in events.items() if s <= seq and e.kind == "round_start"), default=0)
                history = tuple(e for s, e in sorted(events.items()) if start <= s <= seq)
                after = enrich_observation(replace(observation(snapshot, history, ruleset_version), consumed_seq=seq))
                if before is not None and before.round_no == after.round_no and before.consumed_seq < seq:
                    pairs += 1
                    result = compare_observation_transition(before, tuple(e for s, e in sorted(events.items()) if before.consumed_seq < s <= seq), after)
                    outcomes.update(result)
                    for field in ("baotou", "chain_count"):
                        if not any(x.startswith((f"not_checked:{field}:", f"god_mismatch:{field}:")) for x in result):
                            outcomes[field + "_checked_equal"] += 1
                    mismatches = [x for x in result if x.startswith("god_mismatch:")]
                    if mismatches:
                        failures.append({**ref, "before_seq": before.consumed_seq, "after_seq": seq, "issues": mismatches})
                before = after
            except (ValueError, KeyError, TypeError) as exc:
                group["issues"].append({**ref, "issue": "snapshot_unparseable", "reason": str(exc)})
                before = None
        closures = []
        for ref, payload in group["closures"]:
            floor, through = payload.get("history_floor_seq"), payload.get("history_through_seq")
            if not isinstance(floor, int) or not isinstance(through, int):
                closures.append({**ref, "status": "not_checked", "reason": "missing_closure_bounds"})
                continue
            history = {e["seq"]: e for e in payload.get("public_history", [])}
            eligible = {s: public_event_to_json(e) for s, e in events.items() if floor < s <= through}
            missing = sorted(eligible.keys() - history.keys())
            different = sorted(s for s in eligible.keys() & history.keys() if eligible[s] != history[s])
            closures.append({**ref, "round_no": payload.get("round_no"), "floor": floor, "through": through,
                "status": "not_checked" if not eligible else "different" if missing or different else "equal",
                "received_count": len(eligible), "history_count": len(history), "received_missing": missing,
                "field_differences": different, "unreceived_in_history": sorted(history.keys() - events.keys()),
                "history_complete": payload.get("history_complete"), "closure_issues": payload.get("closure_issues", [])})
        comparisons = []
        for source in official or []:
            document = source["document"]
            if document.get("game_id") != gid:
                continue
            truth, conflicts = {}, []
            for block in document.get("blocks", []):
                for event in block.get("events", []):
                    if event["seq"] in truth and truth[event["seq"]] != event:
                        conflicts.append(event["seq"])
                    truth[event["seq"]] = event
            received = group["raw_events"]
            entry = {"source": source["file"], "sha256": source["sha256"], "official_events": len(truth),
                "not_received": sorted(truth.keys() - received.keys()), "not_in_official": sorted(received.keys() - truth.keys()),
                "official_seq_conflicts": sorted(set(conflicts))}
            if len(group["seats"]) != 1 or not received or conflicts:
                entry.update(status="not_checked", reason="missing_received_events_or_unique_seat_or_conflicting_official")
            else:
                seat = next(iter(group["seats"]))
                differences = []
                for seq in sorted(truth.keys() & received.keys()):
                    expected = dict(truth[seq])
                    if expected["type"] == "tile_drawn" and expected["seat"] != seat:
                        # 官方赛后全信息先还原玩家端脱敏形状；绝不把他家暗牌引入观察。
                        expected.update(tile="", data=None)
                    fields = [k for k in ("type", "seat", "tile", "data", "ts") if expected.get(k) != received[seq].get(k)]
                    if fields:
                        differences.append({"seq": seq, "fields": fields})
                entry.update(status="different" if differences or entry["not_received"] or entry["not_in_official"] else "equal",
                    received_field_differences=differences)
            comparisons.append(entry)
        reports.append({"participant_id": pid, "game_id": gid, "received_events": len(events), "snapshot_pairs": pairs,
            "official_comparisons": comparisons,
            "transition_outcomes": dict(outcomes), "transition_mismatches": failures, "closures": closures, "issues": group["issues"]})
    return {"run_id": run.name, "ruleset_version": ruleset_version, "games": reports,
        "reader_issues": [asdict(x) for x in read.issues],
        "limitations": ["赛后集合比较，不证明及时到达；迟到事件可能导致封存差异", "缺原始报文时未检查", "转移仅覆盖生产核验器支持的分支；catch_play 等未检查项保留", "投影复用生产实现，不能替代独立官方规则金例或线上验收"]}
