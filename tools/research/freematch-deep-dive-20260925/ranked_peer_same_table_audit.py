#!/usr/bin/env python3
"""Astra-0 与腾蛇-0638：同桌官方牌谱的版本分层复核（只读）。

积分/胡家/庄家/番数取官方 rounds[] 与 round_ended；零分流局若被
rounds[] 省略，按 round_ended 补回。起手和逐巡派生量复用 hangma 与
anatomy_lib，不另写规则。
"""

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
import sys
from collections import Counter, defaultdict
from pathlib import Path
from glob import glob

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))

from anatomy_lib import round_blocks, reconstruct_round
from extract_room_scores import load_rooms
from independent_xuanwu_four_room_audit import initial_shanten

US = "u_13495c3d79c8"
TARGETS = {"Astra-0": "u_a24596248186", "腾蛇-0638": "u_b2aa6abe7811"}
VERSION_HASH = {
    "R18 v1": "0d3c094d9ee5f5fd0316d0c3db7563523ce1d8d2fafb0e64d3d9b93817909b2d",
    "R18 v2": "a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618",
}
ROOM_VERSIONS = {
    "Astra-0": {
        "a_00a841afe1a6": "R18 v1",
        "a_5a2d078cfa69": "R18 v1",
        "a_5b9dda845c67": "R18 v1",
        "a_b0d2cf5da218": "R18 v2",
        "a_c0739f8cabc3": "R18 v1",
        "a_d71ee9ea6643": "R18 v1",
        "a_d7c3190a1422": "R18 v2",
    },
    "腾蛇-0638": {
        "a_53f4861835b9": "R18 v2",
        "a_5e16dfc1305b": "R18 v2",
        "a_d773a8e428a0": "R18 v2",
        "a_d8e15fe8bc96": "R18 v2",
    },
}


def combine(items: list[Counter]) -> Counter:
    """保留负积分；Counter 的相加运算会丢弃非正项。"""

    out = Counter()
    for item in items:
        for key, value in item.items():
            out[key] += value
    return out


def main() -> None:
    by_target_room = defaultdict(lambda: defaultdict(lambda: {"us": Counter(), "peer": Counter()}))
    game_ids = defaultdict(lambda: defaultdict(set))
    audit = Counter()
    observed = defaultdict(set)
    manifest_versions = defaultdict(set)
    for path in glob(str(_project_file(_PROJECT_ROOT, ROOT / "artifacts" / "sessions" / "*" / "audit" / "runs" / "*" / "manifest.json"))):
        try:
            manifest = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        room_id = (manifest.get("context") or {}).get("tournament_id")
        payload = manifest.get("payload") or {}
        version = payload.get("policy_version")
        source_hash = (payload.get("policy_release") or {}).get("candidate_source_sha256")
        if room_id and version:
            manifest_versions[room_id].add((version, source_hash))
    for _mtime, room, tag, gid, doc in load_rooms():
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if US not in seats:
            continue
        for name, uid in TARGETS.items():
            if uid not in seats:
                continue
            observed[name].add(room)
            if room not in ROOM_VERSIONS[name]:
                continue
            game_ids[name][room].add(gid)
            positions = {"us": seats.index(US), "peer": seats.index(uid)}
            blocks = {no: (events, hands) for no, events, hands in round_blocks(doc)}
            official = doc.get("rounds") or []
            results = {
                r["round_no"]: ({**r, "winner": None} if r.get("is_draw") else r)
                for r in official
            }
            if len(results) != len(official):
                raise AssertionError((name, room, gid, "duplicate round number"))
            audit[f"{name}:official_rounds"] += len(official)
            for no, (events, _hands) in blocks.items():
                if no in results:
                    continue
                terminal = [event for event in events if event.get("type") == "round_ended"]
                if len(terminal) != 1 or not terminal[0].get("data", {}).get("draw"):
                    raise AssertionError((name, room, gid, no, "missing non-draw result"))
                data = terminal[0]["data"]
                if data.get("scores") != [0, 0, 0, 0]:
                    raise AssertionError((name, room, gid, no, "nonzero omitted draw"))
                results[no] = {
                    "round_no": no, "scores": data["scores"], "winner": None,
                    "dealer": data["dealer"], "multiplier": 0,
                }
                audit[f"{name}:recovered_draws"] += 1

            totals = {label: 0 for label in positions}
            for no, result in results.items():
                events, hands = blocks[no]
                if hands is None:
                    raise AssertionError((name, room, gid, no, "missing start hands"))
                terminal = [event for event in events if event.get("type") == "round_ended"]
                if len(terminal) != 1:
                    raise AssertionError((name, room, gid, no, "terminal event count", len(terminal)))
                event = terminal[0]
                data = event.get("data") or {}
                if (data.get("scores") != result["scores"]
                        or data.get("dealer") != result["dealer"]
                        or (None if data.get("draw") else event.get("seat")) != result["winner"]
                        or (0 if data.get("draw") else data.get("fan")) != result["multiplier"]):
                    raise AssertionError((name, room, gid, no, "summary vs event mismatch"))
                recon = reconstruct_round(events, hands)
                if recon["errors"]:
                    raise AssertionError((name, room, gid, no, recon["errors"][:2]))
                audit[f"{name}:round_event_agreements"] += 1
                for label, seat in positions.items():
                    c = by_target_room[name][room][label]
                    score = result["scores"][seat]
                    dealer = result["dealer"]
                    c["rounds"] += 1
                    c["score"] += score
                    totals[label] += score
                    initial_whites = hands[seat].count("白")
                    c["initial_whites"] += initial_whites
                    initial_white_class = "0" if initial_whites == 0 else ("1" if initial_whites == 1 else "2plus")
                    c[f"initial_white_{initial_white_class}_rounds"] += 1
                    drawn_whites = recon["draws"][seat].count("白")
                    c["drawn_whites"] += drawn_whites
                    c["white_discards"] += recon["discards"][seat].count("白")
                    start_shanten = initial_shanten(hands[seat])
                    if seat == dealer:
                        c["dealer_rounds"] += 1
                        c["dealer_start_shanten_sum"] += start_shanten
                        c["dealer_initial_whites"] += initial_whites
                        c["dealer_drawn_whites"] += drawn_whites
                    else:
                        c["nondealer_start_shanten_sum"] += start_shanten
                    if seat == result["winner"]:
                        c["wins"] += 1
                        c[f"initial_white_{initial_white_class}_wins"] += 1
                        c["winning_score"] += score
                        c["fan_sum"] += result["multiplier"]
                        c[f"fan_{result['multiplier']}"] += 1
                        for feature in data.get("detail") or []:
                            c[f"win_detail:{feature}"] += 1
                        if seat == dealer:
                            c["dealer_wins"] += 1
                            c["dealer_winning_score"] += score
                        else:
                            c["nondealer_winning_score"] += score
                    elif score < 0:
                        c["paid_score"] += score
                    waits = recon["waits"][seat]
                    tenpai_waits = [w for w in waits if w["shanten"] == 0]
                    if tenpai_waits:
                        tenpai = tenpai_waits[0]
                        last_tenpai = tenpai_waits[-1]
                        widest = max(w["useful_n"] for w in tenpai_waits)
                        c["reached_tenpai"] += 1
                        c["first_tenpai_turn_sum"] += tenpai["turn"]
                        c["first_tenpai_width_sum"] += tenpai["useful_n"]
                        c["last_tenpai_width_sum"] += last_tenpai["useful_n"]
                        c["max_tenpai_width_sum"] += widest
                        c["max_minus_first_width_sum"] += widest - tenpai["useful_n"]
                        c["widened_after_first_tenpai"] += widest > tenpai["useful_n"]
                    entered_baotou = any(w["state_known"] and w["baotou"] for w in waits)
                    if tenpai_waits and not entered_baotou:
                        c["tenpai_without_baotou_rounds"] += 1
                        c["nonbaotou_first_tenpai_width_sum"] += tenpai_waits[0]["useful_n"]
                        c["nonbaotou_last_tenpai_width_sum"] += tenpai_waits[-1]["useful_n"]
                        c["nonbaotou_widened_after_first_tenpai"] += (
                            max(w["useful_n"] for w in tenpai_waits) > tenpai_waits[0]["useful_n"]
                        )
                    if entered_baotou:
                        c["reached_baotou"] += 1
                        c[f"initial_white_{initial_white_class}_baotou_entry"] += 1
                        if seat == dealer:
                            c["dealer_reached_baotou"] += 1
                    for kind in ("peng", "chi", "gang"):
                        c[f"{kind}_events"] += sum(e.get("type") == kind and e.get("seat") == seat for e in events)
                audit[f"{name}:rounds"] += 1

            ordered = sorted(results.values(), key=lambda r: r["round_no"])
            for label, seat in positions.items():
                c = by_target_room[name][room][label]
                if ordered and ordered[0]["dealer"] == seat:
                    c["initial_dealer_tables"] += 1
                    c["initial_dealer_wins"] += ordered[0]["winner"] == seat
                for current, following in zip(ordered, ordered[1:]):
                    if (current["winner"] == seat and current["dealer"] != seat
                            and following["round_no"] == current["round_no"] + 1):
                        if following["dealer"] != seat:
                            raise AssertionError((name, room, gid, "winner did not become dealer"))
                        c["next_dealer_after_nondealer_win"] += 1
                        c["next_dealer_wins"] += following["winner"] == seat
            if totals["us"] > totals["peer"]:
                by_target_room[name][room]["us"]["tables_ahead_peer"] += 1
            if totals["us"] == totals["peer"]:
                by_target_room[name][room]["us"]["tables_tied_peer"] += 1
            audit[f"{name}:tables"] += 1

    for name, expected_rooms in ROOM_VERSIONS.items():
        if observed[name] != set(expected_rooms):
            raise AssertionError((name, "shared-room set changed", sorted(observed[name])))
        if any(len(game_ids[name][room]) != 10 for room in expected_rooms):
            raise AssertionError((name, {room: len(ids) for room, ids in game_ids[name].items()}))
        for room, version in expected_rooms.items():
            expected = "r18_integrated_positive_" + version.split()[-1]
            if manifest_versions[room] != {(expected, VERSION_HASH[version])}:
                raise AssertionError((name, room, "manifest identity mismatch", manifest_versions[room], expected))
            audit[f"{name}:manifest_identity_checks"] += 1
    cohorts = {}
    for name, rooms in ROOM_VERSIONS.items():
        cohorts[name] = {}
        for version in sorted(set(rooms.values())):
            chosen = [room for room, label in rooms.items() if label == version]
            cohorts[name][version] = {
                label: dict(sorted(combine([by_target_room[name][room][label] for room in chosen]).items()))
                for label in ("us", "peer")
            }
    print(json.dumps({
        "source": "deduplicated official events.json",
        "target_user_ids": TARGETS,
        "room_versions": ROOM_VERSIONS,
        "audit": dict(audit),
        "cohorts": cohorts,
        "rooms": {name: {room: {label: dict(sorted(c.items())) for label, c in pair.items()}
                          for room, pair in rooms.items()}
                  for name, rooms in by_target_room.items()},
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
