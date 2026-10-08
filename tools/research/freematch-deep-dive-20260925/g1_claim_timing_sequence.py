#!/usr/bin/env python3
"""按预登记连接已冻结十房的鸣/过审计与官方事件时序。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from g1_claim_timing_exposure import (
    ME, RELEASE_ID, ROOT, VERSION, _shanten, _timing_bucket,
)

ROOM_IDS = (
    "a_1e9a18f1951a", "a_9f5d90ba56ec", "a_51e700c16e9b",
    "a_7293767fe516", "a_7d4b80bb62f4", "a_cf1dac6bbac5",
    "a_8448cc0c89fd", "a_eb4ce48c74aa", "a_b08410b0cae4",
    "a_3c9b8c294df1",
)
LEDGER = _project_file(_PROJECT_ROOT, ROOT / "runs/auto-match-watchdog/auto-match-watchdog-state.json")
OFFICIAL = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/r18-sse-freematch-campaign-20260925b/official")


def _window_key(request: dict) -> tuple:
    window = request.get("window_key") or {}
    result = tuple(window.get(key) for key in
                   ("game_id", "round_no", "trigger_seq", "phase", "seat"))
    if any(value is None for value in result):
        raise ValueError("审计动作窗口键不完整")
    return result


def _audit_rows(audit_dir: Path) -> tuple[list[dict], Counter]:
    manifest = json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8"))
    identity = manifest.get("payload") or {}
    release = (identity.get("policy_release") or {}).get("release_package_id")
    if identity.get("policy_version") != VERSION or release != RELEASE_ID:
        raise ValueError(f"发布身份不符：{audit_dir}")
    records = audit_dir / "participants" / ME / "decisions.jsonl"
    inputs: dict[str, dict] = {}
    plans: dict[str, dict] = {}
    accepted: dict[str, set[str]] = defaultdict(set)
    not_sent: dict[str, set[str]] = defaultdict(set)
    counts = Counter()
    for line in records.open(encoding="utf-8"):
        record = json.loads(line)
        payload = record.get("payload") or {}
        kind = record.get("kind")
        if kind == "decision_input":
            request = payload.get("request") or {}
            decision_id = request.get("decision_id")
            if not decision_id:
                raise ValueError("审计决策输入缺 ID")
            if decision_id in inputs:
                counts["duplicate_input_record"] += 1
            else:
                inputs[decision_id] = request
        elif kind == "decision_planned":
            plan = payload.get("returned_plan") or {}
            decision_id = plan.get("decision_id")
            if not decision_id:
                raise ValueError("审计决策计划缺 ID")
            plans.setdefault(decision_id, plan)
        elif kind == "submission_outcome" and payload.get("outcome_type") == "SubmitAccepted":
            accepted[str(payload.get("decision_id"))].add(str(payload.get("action_key")))
        elif kind == "submission_outcome" and payload.get("outcome_type") == "SubmitNotSent":
            not_sent[str(payload.get("decision_id"))].add(str(payload.get("reason")))
    grouped: dict[tuple, list[tuple[str, dict]]] = defaultdict(list)
    for decision_id, request in inputs.items():
        grouped[_window_key(request)].append((decision_id, request))
    rows = []
    for key, items in grouped.items():
        phase = key[3]
        if phase not in ("response_peng", "response_chi"):
            continue
        if len(items) > 1:
            counts["revised_response_window"] += 1
            continue
        decision_id, request = items[0]
        legal = (request.get("rules") or {}).get("legal_candidates") or []
        kind = "peng" if phase == "response_peng" else "chi"
        claims = [item for item in legal if (item.get("action") or {}).get("kind") == kind]
        if not claims:
            continue
        counts["claim_window"] += 1
        plan = plans.get(decision_id)
        if not plan or not plan.get("candidates"):
            counts["missing_plan"] += 1
            continue
        top = min(plan["candidates"], key=lambda item: item.get("rank", 10**9))
        action_key = top.get("action_key")
        action = next((candidate for candidate in legal
                       if candidate.get("action_key") == action_key), None)
        if action is None:
            counts["top_not_legal"] += 1
            continue
        top_kind = (action.get("action") or {}).get("kind")
        if top_kind not in ("pass", kind):
            counts["other_top_action"] += 1
            continue
        counts[f"plan:{top_kind}"] += 1
        if action_key not in accepted.get(decision_id, set()):
            counts["top_not_accepted"] += 1
            for reason in sorted(not_sent.get(decision_id) or {"unknown"}):
                counts[f"top_not_accepted:{reason}"] += 1
            continue
        if len(accepted[decision_id]) != 1:
            counts["multiple_accepted_keys"] += 1
            continue
        observation = request.get("observation") or {}
        discarder = (observation.get("last_discard") or {}).get("seat")
        discard_seq = (observation.get("last_discard") or {}).get("seq")
        seat = observation.get("seat")
        if (type(discarder) is not int or type(discard_seq) is not int
                or type(seat) is not int or not 0 <= seat < 4
                or not 0 <= discarder < 4
                or observation.get("turn_seat") != discarder):
            counts["bad_observation_anchor"] += 1
            continue
        distance = (seat - discarder) % 4
        if distance not in (1, 2, 3) or (kind == "chi" and distance != 1):
            counts["bad_relative_seat"] += 1
            continue
        pass_candidate = next((item for item in legal
                               if (item.get("action") or {}).get("kind") == "pass"), None)
        if pass_candidate is None:
            counts["missing_pass"] += 1
            continue
        pass_shanten = _shanten(pass_candidate)
        claim_shantens = [_shanten(item) for item in claims]
        if pass_shanten is None or any(value is None for value in claim_shantens):
            counts["missing_shanten_comparison"] += 1
            continue
        bucket = _timing_bucket(pass_shanten, min(claim_shantens))
        shanten_band = "0" if pass_shanten == 0 else "1" if pass_shanten == 1 else "other"
        wall = observation.get("remaining_tile_count")
        if type(wall) is not int:
            counts["missing_wall"] += 1
            continue
        wall_band = "late" if wall <= 40 else "middle" if wall <= 65 else "early"
        rows.append({
            "game_id": key[0], "round_no": key[1], "trigger_seq": key[2],
            "phase": phase, "seat": seat, "discarder": discarder,
            "discard_seq": discard_seq, "distance": distance,
            "choice": top_kind, "pass_shanten_band": shanten_band,
            "opportunity_bucket": bucket,
            "wall_band": wall_band,
        })
    counts["eligible_accepted_rows"] = len(rows)
    return rows, counts


def _official_index() -> dict[str, dict]:
    """仅投影官方事件的序号、类别、座位与流局标志。"""

    index = {}
    digests = {}
    wanted = set(ROOM_IDS)
    for path in OFFICIAL.glob("dl-*/events.json"):
        raw = path.read_bytes()
        document = json.loads(raw)
        if document.get("room_id") not in wanted:
            continue
        game_id = document.get("game_id")
        if game_id in index:
            if hashlib.sha256(raw).hexdigest() != digests[game_id]:
                raise ValueError(f"同一官方场次有内容冲突的重复下载：{game_id}")
            continue
        digests[game_id] = hashlib.sha256(raw).hexdigest()
        by_round: dict[int, list[dict]] = defaultdict(list)
        for block in document.get("blocks") or []:
            round_no = block.get("round_no")
            if type(round_no) is not int:
                raise ValueError(f"官方局号缺失：{game_id}")
            for event in block.get("events") or []:
                by_round[round_no].append({
                    "seq": event.get("seq"), "type": event.get("type"),
                    "seat": event.get("seat"),
                    "draw": ((event.get("data") or {}).get("draw")
                             if event.get("type") == "round_ended" else None),
                })
        normalized = {}
        for round_no, events in by_round.items():
            events.sort(key=lambda item: item["seq"])
            seqs = [event["seq"] for event in events]
            if any(type(seq) is not int for seq in seqs) or len(seqs) != len(set(seqs)):
                raise ValueError(f"官方事件序号重复或缺失：{game_id} 局 {round_no}")
            normalized[round_no] = events
        index[game_id] = {"room_id": document["room_id"], "rounds": normalized}
    return index


def _sequence(row: dict, official: dict[str, dict]) -> tuple[str, dict | None]:
    game = official.get(row["game_id"])
    if game is None:
        return "missing_official_game", None
    events = game["rounds"].get(row["round_no"])
    if events is None:
        return "missing_official_round", None
    if row["trigger_seq"] > row["discard_seq"]:
        return "last_discard_before_trigger", None
    anchors = [index for index, event in enumerate(events)
               if event["seq"] <= row["trigger_seq"]
               and event["type"] == "tile_discarded"]
    if not anchors:
        return "missing_discard_anchor", None
    anchor = anchors[-1]
    if events[anchor]["seat"] != row["discarder"]:
        return "nearest_discard_seat_mismatch", None
    candidates = []
    for index in range(anchor + 1, len(events)):
        event = events[index]
        if event["seq"] <= row["trigger_seq"]:
            continue
        if event["type"] in ("tile_drawn", "tile_discarded", "round_ended"):
            break
        if event["seat"] == row["seat"] and event["type"] == row["choice"]:
            candidates.append(index)
    if not candidates:
        return "missing_action_event", None
    # 碰窗口中的下家可随后再次经过吃窗口；当前窗口只取第一个过牌事件。
    action_index = candidates[0]
    if row["choice"] in ("chi", "peng"):
        following = events[action_index + 1] if action_index + 1 < len(events) else None
        if (following is None or following["type"] != "tile_discarded"
                or following["seat"] != row["seat"]):
            return "claim_not_followed_by_own_discard", None
    others_drawn = 0
    intervening_claims = 0
    for event in events[action_index + 1:]:
        if event["type"] == "tile_drawn":
            if event["seat"] == row["seat"]:
                return "next_self_draw", {
                    "other_draws_before_self": others_drawn,
                    "intervening_claims": intervening_claims,
                }
            others_drawn += 1
        elif event["type"] in ("chi", "peng", "gang"):
            intervening_claims += 1
        elif event["type"] == "round_ended":
            if event["draw"] is True:
                ending = "drawn_round"
            elif event["seat"] == row["seat"]:
                ending = "own_win_before_next_draw"
            else:
                ending = "other_win_before_next_draw"
            return ending, {
                "other_draws_before_self": others_drawn,
                "intervening_claims": intervening_claims,
            }
    return "no_next_draw_or_round_end", None


def main() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    by_id = {room["room_id"]: room for room in ledger.get("rooms") or []}
    if any(room_id not in by_id for room_id in ROOM_IDS):
        raise ValueError("预登记十房未全部结算")
    official = _official_index()
    counts = Counter()
    by_room = {}
    for room_id in ROOM_IDS:
        audit_dir = _project_file(_PROJECT_ROOT, ROOT / by_id[room_id]["audit_dir"])
        rows, audit_counts = _audit_rows(audit_dir)
        local = Counter(audit_counts)
        for row in rows:
            status, sequence = _sequence(row, official)
            local[f"sequence:{status}"] += 1
            if sequence is None:
                continue
            choice = row["choice"]
            phase = row["phase"]
            distance = row["distance"]
            local[f"fate:{choice}:{status}"] += 1
            local[f"fate:{phase}:{choice}:{status}"] += 1
            local[f"fate:d{distance}:{choice}:{status}"] += 1
            local[f"fate:pass_shanten_{row['pass_shanten_band']}:{choice}:{status}"] += 1
            local[f"fate:opportunity_{row['opportunity_bucket']}:{choice}:{status}"] += 1
            local[f"fate:wall_{row['wall_band']}:{choice}:{status}"] += 1
            draws = sequence["other_draws_before_self"]
            local[f"other_draws:{choice}:{min(draws, 5)}{'+' if draws >= 5 else ''}"] += 1
            if status == "next_self_draw":
                expected = distance - 1 if choice == "pass" else 3
                local[f"baseline_draw_count:{choice}:{'equal' if draws == expected else 'different'}"] += 1
            if sequence["intervening_claims"]:
                local[f"intervening_claim:{choice}"] += 1
        counts.update(local)
        by_room[room_id] = dict(sorted(local.items()))
    print(json.dumps({
        "schema": "g1-claim-timing-official-sequence/1",
        "room_ids": list(ROOM_IDS),
        "official_games": sum(game["room_id"] in ROOM_IDS for game in official.values()),
        "total_counts": dict(sorted(counts.items())),
        "by_room": by_room,
        "interpretation": "observational timing labels; no causal action value",
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
