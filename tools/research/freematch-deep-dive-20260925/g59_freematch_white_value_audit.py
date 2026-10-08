#!/usr/bin/env python3
"""冻结 R18 v2 自由赛牌谱的白板供给、庄位与胡牌收支描述审计。"""

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

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import g11_cross_family_action_atlas as atlas
from extract_room_scores import load_rooms


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g59-freematch-white-value-20260927/result.json')
US = "u_13495c3d79c8"
PEERS = {
    "xuanwu_2346": "u_380da525337c",
    "astra_0": "u_a24596248186",
    "tengshe_0638": "u_b2aa6abe7811",
}


def bucket(value: int) -> str:
    """仅为报告分层；2+ 不表示两张白板足以形成任何指定胡型。"""

    return "2plus" if value >= 2 else str(value)


def add(group: Counter, *, score: int, winner: bool, fan: int, detail: tuple[str, ...],
        dealer: bool, first_win_turn: int | None) -> None:
    """积累官方单局账目；`first_win_turn` 是本人本局第几次摸后胡。"""

    group["hands"] += 1
    group["net"] += score
    group["dealer_hands"] += int(dealer)
    if winner:
        group["wins"] += 1
        group["win_points"] += score
        group["plain_wins"] += int(fan == 1)
        group["plain_win_points"] += score if fan == 1 else 0
        group["fan2plus_wins"] += int(fan >= 2)
        group["fan2plus_win_points"] += score if fan >= 2 else 0
        group["fan4plus_wins"] += int(fan >= 4)
        group["baotou_wins"] += int("爆头" in detail)
        group["early_wins_le6"] += int(first_win_turn is not None and first_win_turn <= 6)
    else:
        group["nonwin_points"] += score


def audit_game(doc: dict, complete_ids: set[str], rooms: set[str],
               groups: dict[str, Counter], room_rows: dict[str, Counter],
               trace: Counter) -> bool:
    """以 `round_ended` 为权威，校验八个完整单局和摘要结算。"""

    gid, room = doc.get("game_id"), doc.get("room_id")
    if gid not in complete_ids or room not in rooms:
        return False
    seats = [item.get("user_id") for item in doc.get("seats") or []]
    if len(seats) != 4 or US not in seats:
        raise ValueError(f"冻结官方桌缺我方或四座：{gid}")
    summary = {row["round_no"]: row for row in doc.get("rounds") or []}
    blocks = defaultdict(list)
    for block in doc.get("blocks") or []:
        blocks[block["round_no"]].append(block)
    if len(blocks) != 8:
        raise ValueError(f"冻结官方桌不是八单局：{gid}")
    final = [0, 0, 0, 0]
    for round_no, pieces in blocks.items():
        start = next((block["start_hands"] for block in pieces
                      if isinstance(block.get("start_hands"), list)
                      and len(block["start_hands"]) == 4), None)
        if start is None or any(not isinstance(hand, list) for hand in start):
            raise ValueError(f"缺四座起手牌：{gid} r{round_no}")
        events = [event for block in pieces for event in block.get("events") or []]
        endings = [event for event in events if event.get("type") == "round_ended"]
        if len(endings) != 1:
            raise ValueError(f"单局权威结算不唯一：{gid} r{round_no}")
        end = endings[0]
        data = end.get("data") or {}
        scores = data.get("scores")
        dealer = data.get("dealer")
        winner = None if data.get("draw") else end.get("seat")
        fan = data.get("fan") or 0
        detail = tuple(data.get("detail") or ())
        if (not isinstance(scores, list) or len(scores) != 4 or
                type(dealer) is not int or dealer not in range(4) or
                (winner is not None and (type(winner) is not int or winner not in range(4))) or
                sum(scores) != 0):
            raise ValueError(f"单局结算字段非法：{gid} r{round_no}")
        if round_no in summary:
            row = summary[round_no]
            summary_winner = None if row.get("is_draw") else row.get("winner")
            if (row.get("scores") != scores or row.get("dealer") != dealer or
                    summary_winner != winner or row.get("multiplier") != fan):
                raise ValueError(f"单局摘要与终局事件不一致：{gid} r{round_no}")
        else:
            if not data.get("draw") or any(scores):
                raise ValueError(f"摘要遗漏了非零或非流局结算：{gid} r{round_no}")
            trace["summary_omitted_zero_draw"] += 1
        white_draws = Counter()
        own_discards = Counter()
        for event in events:
            if (type(event.get("seat")) is int and
                    event.get("type") == "tile_drawn" and event.get("tile") == "白"):
                white_draws[event["seat"]] += 1
            if (type(event.get("seat")) is int and
                    event.get("type") == "tile_discarded"):
                own_discards[event["seat"]] += 1
        for seat, uid in enumerate(seats):
            start_white = start[seat].count("白")
            total_white = start_white + white_draws[seat]
            labels = ["us" if uid == US else "other"]
            if uid == US:
                labels.extend("us_vs_" + name for name, peer in PEERS.items()
                              if peer in seats)
            labels.extend(name for name, peer in PEERS.items() if uid == peer)
            first_win_turn = own_discards[seat] + 1 if seat == winner else None
            for label in labels:
                for axis, value in (("all", "all"),
                                    ("start_white", bucket(start_white)),
                                    ("white_supply", bucket(total_white)),
                                    ("dealer", "yes" if seat == dealer else "no")):
                    add(groups[f"{label}/{axis}/{value}"], score=scores[seat],
                        winner=seat == winner, fan=fan, detail=detail,
                        dealer=seat == dealer, first_win_turn=first_win_turn)
            if uid in (US, *PEERS.values()):
                name = "us" if uid == US else next(key for key, peer in PEERS.items()
                                                    if uid == peer)
                add(room_rows[f"{room}/{name}"], score=scores[seat],
                    winner=seat == winner, fan=fan, detail=detail,
                    dealer=seat == dealer, first_win_turn=first_win_turn)
            final[seat] += scores[seat]
            trace["white_start_total"] += start_white
            trace["white_draw_total"] += white_draws[seat]
        trace["hands"] += 1
        trace["round_summary_present"] += int(round_no in summary)
    game_final = next((event.get("data", {}).get("final_scores")
                       for block in doc.get("blocks") or []
                       for event in block.get("events") or []
                       if event.get("type") == "game_ended"), None)
    if game_final is not None and list(game_final) != final:
        raise ValueError(f"完整桌末分与逐局不一致：{gid}")
    trace["games"] += 1
    return True


def main() -> None:
    """冻结房和完整桌身份，只从已下载官方牌谱读事实。"""

    if OUT.exists():
        raise SystemExit("G59 证据已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    rooms = {row["room_id"] for row in frozen["rooms"]}
    complete_ids = atlas._complete_ids()
    groups: dict[str, Counter] = defaultdict(Counter)
    room_rows: dict[str, Counter] = defaultdict(Counter)
    trace = Counter()
    matched = set()
    for _mtime, room, _tag, gid, doc in load_rooms():
        if audit_game(doc, complete_ids, rooms, groups, room_rows, trace):
            matched.add(gid)
    if matched != complete_ids or trace["games"] != 909 or trace["hands"] != 909 * 8:
        raise ValueError("G59 完整桌母体与 91 房已冻结审计不一致")
    result = {
        "schema": "g59-freematch-white-value/1",
        "boundary": "官方自由赛已发生轨迹的观察性拆账；白板后摸数与庄位可受先前行动影响，不能作线上未来输入或策略因果效应。统计比较按房而非单局。",
        "frozen_rooms_sha256": hashlib.sha256(atlas.FROZEN.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "rooms": len(rooms),
        "trace": dict(sorted(trace.items())),
        "groups": {key: dict(sorted(row.items())) for key, row in sorted(groups.items())},
        "room_rows": {key: dict(sorted(row.items())) for key, row in sorted(room_rows.items())},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"rooms": result["rooms"], "trace": result["trace"],
                      "us": result["groups"]["us/all/all"],
                      "other": result["groups"]["other/all/all"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
