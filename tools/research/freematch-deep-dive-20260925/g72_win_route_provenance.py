#!/usr/bin/env python3
"""G72：用官方事件对账终胡前一次本人弃牌的来源，补 G69 正常摸打盲区。"""

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
import gzip
import hashlib
import json
from pathlib import Path

from extract_room_scores import load_rooms


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/claim_terminal_rounds.jsonl.gz')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g72-win-route-provenance-20260928/result.json')
ACQUISITION = frozenset(("tile_drawn", "chi", "peng", "gang"))


def origin_before_terminal_draw(events: list[dict], seat: int) -> tuple[str, int | None, int]:
    """回看本座终胡摸牌前最后一次弃牌，不读取别家暗手或未来墙。"""

    own = [event for event in events if event.get("seat") == seat]
    draws = [i for i, event in enumerate(own) if event.get("type") == "tile_drawn"]
    if not draws:
        raise ValueError("获胜座缺本人摸牌事件")
    terminal_index = draws[-1]
    terminal_seq = own[terminal_index]["seq"]
    prior_discards = [i for i, event in enumerate(own[:terminal_index])
                      if event.get("type") == "tile_discarded"]
    if not prior_discards:
        return "no_prior_discard", None, terminal_seq
    discard_index = prior_discards[-1]
    discard = own[discard_index]
    acquisition = [event for event in own[:discard_index]
                   if event.get("type") in ACQUISITION]
    origin = acquisition[-1]["type"] if acquisition else "opening_dealer_discard"
    if discard["seq"] >= terminal_seq:
        raise ValueError("终胡前弃牌时序错误")
    return origin, discard["seq"], terminal_seq


def main() -> None:
    if OUT.exists():
        raise SystemExit("G72 证据已存在，拒绝覆盖")
    source = [json.loads(line) for line in gzip.open(SOURCE, "rt", encoding="utf-8")]
    if len(source) != 5120:
        raise ValueError("G69/G71 同房单双方单局样本漂移")
    by_game_round: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for row in source:
        by_game_round[(row["room"], row["game_id"], row["round_no"])].append(row)
    rooms = {row["room"] for row in source}
    games = {row["game_id"] for row in source}
    found_rounds: set[tuple[str, str, int]] = set()
    rows = []
    official_sources = []
    for _, room, _, game_id, doc in load_rooms():
        if room not in rooms or game_id not in games:
            continue
        blocks: dict[int, list[dict]] = defaultdict(list)
        for block in doc.get("blocks") or []:
            blocks[block["round_no"]].extend(block.get("events") or [])
        if len(blocks) != 8:
            raise ValueError("官方完整桌不含八单局")
        official_sources.append((game_id, hashlib.sha256(
            json.dumps(doc, ensure_ascii=False, sort_keys=True).encode()).hexdigest()))
        for round_no, events in blocks.items():
            key = (room, game_id, round_no)
            if key not in by_game_round:
                raise ValueError("官方单局超出 G69 冻结集合")
            if key in found_rounds:
                raise ValueError("官方单局重复")
            found_rounds.add(key)
            ends = [event for event in events if event.get("type") == "round_ended"]
            if len(ends) != 1:
                raise ValueError("单局终局事件不唯一")
            winner = None if ends[0]["data"].get("draw") else ends[0].get("seat")
            for row in by_game_round[key]:
                if row["status"] != "win":
                    continue
                if winner != row["seat"] or type(row["fan"]) is not int:
                    raise ValueError("官方赢家或番数与 G69 不符")
                origin, discard_seq, draw_seq = origin_before_terminal_draw(events, row["seat"])
                rows.append({"peer": row["peer"], "actor": row["actor"],
                             "room": room, "game_id": game_id, "round_no": round_no,
                             "seat": row["seat"], "fan": row["fan"],
                             "origin": origin, "last_discard_seq": discard_seq,
                             "terminal_draw_seq": draw_seq,
                             "prior_any_ready": row["first_any_ready"] is not None,
                             "prior_high_ready": row["first_high_ready"] is not None,
                             "claims_in_round": row["own_claims"]})
    if found_rounds != set(by_game_round):
        raise ValueError("官方单局覆盖不完整")
    counts: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        c = counts[row["peer"] + "/" + row["actor"]]
        fan = "high" if row["fan"] >= 2 else "plain"
        c[fan + "_wins"] += 1
        c[fan + "_origin_" + row["origin"]] += 1
        if fan == "high" and not row["prior_high_ready"]:
            c["high_no_prior_ready"] += 1
            c["high_no_prior_origin_" + row["origin"]] += 1
            c["high_no_prior_with_claim"] += row["claims_in_round"] > 0
            c["high_no_prior_with_plain_ready"] += row["prior_any_ready"]
    expected = {"xuanwu_2346/peer": (237, 108), "xuanwu_2346/us": (211, 73),
                "tengshe_0638/peer": (238, 140), "tengshe_0638/us": (258, 96)}
    for name, (plain, high) in expected.items():
        if counts[name]["plain_wins"] != plain or counts[name]["high_wins"] != high:
            raise ValueError("G60/G64 胡牌分层对账失败")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    result = {"schema": "g72-win-route-provenance/1", "exploratory": True,
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "official_game_digests": sorted(official_sources),
              "rounds": len(found_rounds), "winning_rows": len(rows),
              "counts": {name: dict(sorted(value.items())) for name, value in sorted(counts.items())},
              "rows": sorted(rows, key=lambda row: (row["peer"], row["room"], row["game_id"],
                                                    row["round_no"], row["actor"])),
              "boundary": "赛后终胡前最后弃牌来源只是事件归因；不同起手和策略选择、先胡截尾未控制，不能当作鸣牌因果收益。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rounds": result["rounds"], "winning_rows": len(rows),
                      "counts": result["counts"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
