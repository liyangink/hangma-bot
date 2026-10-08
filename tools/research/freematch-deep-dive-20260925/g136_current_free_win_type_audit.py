#!/usr/bin/env python3
"""G136：只读核对 G122 冻结完整官方自由赛的本人胡型收入。"""

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

from extract_room_scores import load_rooms
import g59_freematch_white_value_audit as g59


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g122-current-free-cohort-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g136-current-free-win-type-20260928/result.json')
PEERS = {"玄武-2346": g59.PEERS["xuanwu_2346"],
         "腾蛇-0638": g59.PEERS["tengshe_0638"],
         "Astra-0": g59.PEERS["astra_0"]}


def kind(details: list[str], fan: int) -> str:
    """赛后按官方胡牌明细互斥分类；未知明细保留独立类。"""
    if details == ["平胡"] and fan == 1:
        return "plain"
    if not details or fan <= 0:
        raise ValueError("G136 胡牌番数或明细缺失")
    if details[0] == "七对" or details[0].startswith("豪华七对×"):
        return "seven_pairs_baotou" if "爆头" in details else "seven_pairs_other"
    if details[0] == "平胡" and "爆头" in details:
        return "plain_baotou"
    return "other_special"


def add(counter: Counter, *, amount: int, win_kind: str | None,
        start_white: int, win_turn: int | None) -> None:
    """按单局累加本人积分、胡牌数和胡型收入；不把单局当独立样本。"""
    counter["hands"] += 1
    counter["net"] += amount
    counter["start_white_" + ("2plus" if start_white >= 2 else str(start_white))] += 1
    if win_kind is None:
        counter["nonwin_income"] += amount
        return
    counter["wins"] += 1
    counter["win_income"] += amount
    counter["wins_" + win_kind] += 1
    counter["income_" + win_kind] += amount
    counter["wins_" + win_kind + ("_le6" if win_turn <= 6 else "_ge7")] += 1


def main() -> None:
    """按 G122 冻结房号和 game_id 逐手核官方事件与积分。"""
    if OUT.exists():
        raise FileExistsError("G136 已有证据，拒绝覆盖")
    frozen = json.loads(SOURCE.read_text(encoding="utf-8"))
    if (frozen["schema"] != "g122-current-free-cohort-snapshot/1"
            or frozen["complete_rooms"] != 220
            or frozen["complete_tables"] != 2200):
        raise ValueError("G136 冻结母体不符")
    included = frozen["included"]
    docs: dict[str, dict[str, dict]] = defaultdict(dict)
    for _mtime, room, _tag, game_id, doc in load_rooms():
        if room in included and game_id in included[room]["game_ids"]:
            if game_id in docs[room]:
                raise ValueError("G136 game_id 去重后仍重复")
            docs[room][game_id] = doc
    if set(docs) != set(included):
        raise ValueError("G136 官方房集合不符")
    groups: dict[str, Counter] = defaultdict(Counter)
    room_groups: dict[str, Counter] = defaultdict(Counter)
    details: Counter = Counter()
    hand_count = 0
    for room, entry in sorted(included.items()):
        if set(docs[room]) != set(entry["game_ids"]) or len(docs[room]) != 10:
            raise ValueError("G136 房内十桌身份不符：" + room)
        for game_id in entry["game_ids"]:
            doc = docs[room][game_id]
            seats = [s.get("user_id") for s in doc.get("seats") or []]
            if len(seats) != 4 or g59.US not in seats:
                raise ValueError("G136 官方四座或我方身份缺失")
            labels = {"us": seats.index(g59.US)}
            for name, uid in PEERS.items():
                if uid in seats:
                    labels[name] = seats.index(uid)
                    labels["us_vs_" + name] = seats.index(g59.US)
            blocks = defaultdict(list)
            for block in doc.get("blocks") or []:
                blocks[block["round_no"]].append(block)
            if set(blocks) != set(range(1, 9)):
                raise ValueError("G136 官方八局不完整：" + game_id)
            summary = {row["round_no"]: row for row in doc.get("rounds") or []}
            totals = [0, 0, 0, 0]
            for round_no, pieces in sorted(blocks.items()):
                starts = [piece["start_hands"] for piece in pieces
                          if isinstance(piece.get("start_hands"), list)
                          and len(piece["start_hands"]) == 4]
                if not starts:
                    raise ValueError("G136 单局起手牌缺失")
                events = [event for piece in pieces for event in piece.get("events") or []]
                endings = [event for event in events if event.get("type") == "round_ended"]
                if len(endings) != 1:
                    raise ValueError("G136 官方权威结算不唯一")
                ending = endings[0]
                data = ending.get("data") or {}
                score = data.get("scores")
                if (not isinstance(score, list) or len(score) != 4
                        or any(type(x) is not int for x in score) or sum(score) != 0):
                    raise ValueError("G136 四座积分不守恒")
                winner = None if data.get("draw") else ending.get("seat")
                fan = data.get("fan") or 0
                detail = list(data.get("detail") or [])
                if winner is not None:
                    if type(winner) is not int or winner not in range(4):
                        raise ValueError("G136 胡牌座位非法")
                    win_kind = kind(detail, fan)
                    details[tuple(detail)] += 1
                else:
                    if fan or any(score):
                        raise ValueError("G136 流局积分或番数不符")
                    win_kind = None
                if round_no in summary:
                    item = summary[round_no]
                    summary_winner = None if item.get("is_draw") else item.get("winner")
                    if (item.get("scores") != score or summary_winner != winner
                            or item.get("multiplier") != fan):
                        raise ValueError("G136 事件积分与官方摘要不符")
                elif winner is not None or any(score):
                    raise ValueError("G136 官方摘要遗漏非零结算")
                discards = Counter(event["seat"] for event in events
                                   if event.get("type") == "tile_discarded"
                                   and type(event.get("seat")) is int)
                for label, seat in labels.items():
                    who_won = winner == seat
                    add(groups[label], amount=score[seat],
                        win_kind=win_kind if who_won else None,
                        start_white=starts[0][seat].count("白"),
                        win_turn=discards[seat] + 1 if who_won else None)
                    add(room_groups[room + "/" + label], amount=score[seat],
                        win_kind=win_kind if who_won else None,
                        start_white=starts[0][seat].count("白"),
                        win_turn=discards[seat] + 1 if who_won else None)
                totals = [a + b for a, b in zip(totals, score)]
                hand_count += 1
            final = next((event.get("data", {}).get("final_scores")
                          for block in doc.get("blocks") or []
                          for event in block.get("events") or []
                          if event.get("type") == "game_ended"), None)
            if final is not None and totals != final:
                raise ValueError("G136 八局合计与官方终分不符")
        if room_groups[room + "/us"]["hands"] != 80:
            raise ValueError("G136 房内本人八十局不完整")
        if room_groups[room + "/us"]["net"] != entry["our_score"]:
            raise ValueError("G136 房内本人积分与 G122 不符")
    if (hand_count != 17600 or groups["us"]["hands"] != 17600
            or groups["us"]["net"] != frozen["our_score"]):
        raise ValueError("G136 累计官方母体不守恒")
    for name, frozen_peer in frozen["by_peer"].items():
        if (groups[name]["hands"] != frozen_peer["rooms"] * 80
                or groups[name]["net"] != frozen_peer["peer_score"]
                or groups["us_vs_" + name]["net"] != frozen_peer["our_score"]):
            raise ValueError("G136 强手同桌口径与 G122 不符：" + name)
    output = {"schema": "g136-current-free-win-type/1",
              "input_sha256": {"g122": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                               "script": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "complete_rooms": len(included), "complete_tables": len(included) * 10,
              "complete_hands": hand_count,
              "groups": {k: dict(sorted(v.items())) for k, v in sorted(groups.items())},
              "room_groups": {k: dict(sorted(v.items())) for k, v in sorted(room_groups.items())},
              "win_details": {"|".join(k): v for k, v in sorted(details.items())},
              "boundary": "官方自由赛真实轨迹的观察性胡型拆分；同房配桌非随机，"
                          "不能当作弃牌反事实或新候选确认。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rooms": len(included), "tables": len(included) * 10,
                      "groups": output["groups"]}, ensure_ascii=False,
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
