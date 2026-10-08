#!/usr/bin/env python3
"""复核我方与玄武-2346同桌牌谱；只读官方赛后归档。

分数、庄位、胡牌与番数直接取官方 rounds；起手与逐巡派生量只经
hangma 规则模块和已有 anatomy_lib 重建。未结算的事件局不计入分母。
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

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))

from anatomy_lib import round_blocks, reconstruct_round  # noqa: E402
from extract_room_scores import load_rooms  # noqa: E402
from hangma_bot.hangma.hand_analysis import analyse_hand_progress  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

US = "u_13495c3d79c8"
XUANWU = "u_380da525337c"
ROOM_VERSION = {
    "a_8f73d9fe25c5": "R18 v1",
    "a_f8ddc4c3bd9b": "R18 v2",
    "a_d773a8e428a0": "R18 v2",
    "a_852fb97c102e": "R18 v2",
}


def initial_shanten(codes: list[str]) -> int:
    """起手向听：闲家13张；庄家14张取最优合法弃牌后的13张。"""

    hand = tuple(Tile(code) for code in codes)
    if len(hand) == 13:
        return analyse_hand_progress(hand, 0).shanten
    if len(hand) == 14:
        return min(
            analyse_hand_progress(tuple(tile for i, tile in enumerate(hand) if i != j), 0).shanten
            for j in range(14)
        )
    raise ValueError(f"unexpected initial hand length {len(hand)}")


def summarize(counters: dict) -> dict:
    """只输出可审计的计数和整数和；比率由报告明确给出分母。"""

    return {side: dict(sorted(counts.items())) for side, counts in counters.items()}


def main() -> None:
    by_room = defaultdict(lambda: {"us": Counter(), "xuanwu": Counter()})
    games = defaultdict(set)
    audit = Counter()
    shared_room_ids = set()
    for _mtime, room, _tag, game_id, doc in load_rooms():
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if US in seats and XUANWU in seats:
            shared_room_ids.add(room)
        if room not in ROOM_VERSION:
            continue
        if US not in seats or XUANWU not in seats:
            raise AssertionError((room, game_id, seats))
        games[room].add(game_id)
        positions = {"us": seats.index(US), "xuanwu": seats.index(XUANWU)}
        blocks = {number: (events, hands) for number, events, hands in round_blocks(doc)}
        official = doc.get("rounds") or []
        result_by_no = {r["round_no"]: r for r in official}
        if len(result_by_no) != len(official):
            raise AssertionError((room, game_id, "duplicate round_no in rounds[]"))
        audit["official_result_rounds"] += len(official)
        # 官方 rounds[] 在这些牌谱中省略零分流局；权威事件仍给出庄位与四家分数。
        for number, (events, _hands) in blocks.items():
            if number in result_by_no:
                continue
            ended = [event for event in events if event.get("type") == "round_ended"]
            if len(ended) != 1 or not ended[0].get("data", {}).get("draw"):
                raise AssertionError((room, game_id, number, "missing non-draw result"))
            data = ended[0]["data"]
            if data.get("scores") != [0, 0, 0, 0]:
                raise AssertionError((room, game_id, number, "nonzero omitted draw"))
            result_by_no[number] = {
                "round_no": number,
                "scores": data["scores"],
                "winner": None,
                "dealer": data["dealer"],
                "multiplier": 0,
            }
            audit["zero_score_draw_rounds_recovered"] += 1

        table_total = {name: 0 for name in positions}
        for rnd in result_by_no.values():
            number = rnd["round_no"]
            events, start_hands = blocks[number]
            if start_hands is None:
                raise AssertionError((room, game_id, number, "missing start hands"))
            ended = [e for e in events if e.get("type") == "round_ended"]
            if len(ended) != 1:
                raise AssertionError((room, game_id, number, "round_ended count", len(ended)))
            terminal = ended[0]
            terminal_data = terminal.get("data") or {}
            if (terminal_data.get("scores") != rnd["scores"]
                    or terminal_data.get("dealer") != rnd["dealer"]
                    or (None if terminal_data.get("draw") else terminal.get("seat")) != rnd["winner"]
                    or (0 if terminal_data.get("draw") else terminal_data.get("fan")) != rnd["multiplier"]):
                raise AssertionError((room, game_id, number, "rounds[] disagrees with round_ended"))
            audit["official_result_event_agreements"] += 1
            recon = reconstruct_round(events, start_hands)
            if recon["errors"]:
                raise AssertionError((room, game_id, number, recon["errors"][:3]))
            scores = rnd["scores"]
            winner = rnd["winner"]
            dealer = rnd["dealer"]
            fan = rnd["multiplier"]
            for name, seat in positions.items():
                c = by_room[room][name]
                c["rounds"] += 1
                c["score"] += scores[seat]
                table_total[name] += scores[seat]
                if seat == dealer:
                    c["dealer_rounds"] += 1
                if seat == winner:
                    c["wins"] += 1
                    c["winning_score"] += scores[seat]
                    c["fan_sum"] += fan
                    c[f"fan_{fan}"] += 1
                    if seat == dealer:
                        c["dealer_wins"] += 1
                        c["dealer_winning_score"] += scores[seat]
                        c["dealer_winning_fan_sum"] += fan
                    else:
                        c["nondealer_winning_score"] += scores[seat]
                        c["nondealer_winning_fan_sum"] += fan
                    if fan >= 4:
                        c["high_fan_wins"] += 1
                elif scores[seat] < 0:
                    c["paid_score"] += scores[seat]
                c["initial_whites"] += start_hands[seat].count("白")
                rec_whites = recon["draws"][seat].count("白")
                c["drawn_whites"] += rec_whites
                if seat == dealer:
                    c["dealer_initial_whites"] += start_hands[seat].count("白")
                    c["dealer_drawn_whites"] += rec_whites
                c["discarded_whites"] += recon["discards"][seat].count("白")
                shanten = initial_shanten(start_hands[seat])
                c["start_shanten_sum"] += shanten
                c["start_shanten_count"] += 1
                if seat == dealer:
                    c["dealer_start_shanten_sum"] += shanten
                else:
                    c["nondealer_start_shanten_sum"] += shanten
                waits = recon["waits"][seat]
                first_tenpai = next((w for w in waits if w["shanten"] == 0), None)
                if first_tenpai is not None:
                    c["reached_tenpai"] += 1
                    c["first_tenpai_turn_sum"] += first_tenpai["turn"]
                    c["first_tenpai_width_sum"] += first_tenpai["useful_n"]
                if any(w["state_known"] and w["baotou"] for w in waits):
                    c["reached_baotou"] += 1
                    if seat == dealer:
                        c["dealer_reached_baotou"] += 1
                if any(e.get("type") == "peng" and e.get("seat") == seat for e in events):
                    c["rounds_with_peng"] += 1
                c["peng_events"] += sum(e.get("type") == "peng" and e.get("seat") == seat for e in events)
                c["chi_events"] += sum(e.get("type") == "chi" and e.get("seat") == seat for e in events)
                c["gang_events"] += sum(e.get("type") == "gang" and e.get("seat") == seat for e in events)
                c["draw_events"] += len(recon["draws"][seat])
                audit["white_draw_events"] += rec_whites
            audit["settled_rounds"] += 1
        ordered = sorted(result_by_no.values(), key=lambda r: r["round_no"])
        if ordered:
            for name, seat in positions.items():
                if ordered[0]["dealer"] == seat:
                    by_room[room][name]["initial_dealer_tables"] += 1
                    by_room[room][name]["initial_dealer_wins"] += ordered[0]["winner"] == seat
                for current, following in zip(ordered, ordered[1:]):
                    if current["winner"] != seat or current["dealer"] == seat:
                        continue
                    if following["round_no"] != current["round_no"] + 1:
                        continue
                    if following["dealer"] != seat:
                        raise AssertionError((room, game_id, "nondealer winner did not become dealer"))
                    by_room[room][name]["next_dealer_after_nondealer_win"] += 1
                    by_room[room][name]["next_dealer_wins"] += following["winner"] == seat
        if table_total["us"] > table_total["xuanwu"]:
            by_room[room]["us"]["table_wins_over_xuanwu"] += 1
        if table_total["us"] == table_total["xuanwu"]:
            by_room[room]["us"]["table_ties_with_xuanwu"] += 1
        audit["table_matches"] += 1

    if shared_room_ids != set(ROOM_VERSION):
        raise AssertionError(("shared rooms changed; review new games before extending comparison", sorted(shared_room_ids)))
    if set(games) != set(ROOM_VERSION) or any(len(games[room]) != 10 for room in ROOM_VERSION):
        raise AssertionError({room: len(ids) for room, ids in games.items()})
    def combine(rooms: list[str], name: str) -> Counter:
        out = Counter()
        for room in rooms:
            for key, value in by_room[room][name].items():
                out[key] += value  # 保留负的分数和付分；Counter.__add__ 会丢弃负数。
        return out

    v2_rooms = [room for room, version in ROOM_VERSION.items() if version == "R18 v2"]
    v2 = {name: combine(v2_rooms, name) for name in ("us", "xuanwu")}
    all_rooms = {name: combine(list(ROOM_VERSION), name) for name in ("us", "xuanwu")}
    print(json.dumps({
        "source": "official events.json, latest file per game_id",
        "user_ids": {"us": US, "xuanwu": XUANWU},
        "room_version": ROOM_VERSION,
        "audit": dict(audit),
        "room_game_counts": {room: len(ids) for room, ids in games.items()},
        "rooms": {room: summarize(c) for room, c in by_room.items()},
        "r18_v2": summarize(v2),
        "all_four_rooms": summarize(all_rooms),
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
