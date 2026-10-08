#!/usr/bin/env python3
"""G64：从冻结官方自由赛事件复核实际胡牌时序与他家先胡截尾。"""

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
import g60_full_free_cohort_audit as g60


HERE = Path(__file__).resolve().parent
G60 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g64-strong-win-timing-20260928')
PEERS = {"xuanwu_2346": g59.PEERS["xuanwu_2346"],
         "tengshe_0638": g59.PEERS["tengshe_0638"]}


def sha(path: Path) -> str:
    """绑定冻结房、代码与执行前方案。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def turn_bucket(index: int) -> str:
    """本人第几次行动，含第十次及以后。"""

    if index <= 0:
        raise ValueError("胡牌行动序号非正")
    return "1-3" if index <= 3 else "4-6" if index <= 6 else "7-9" if index <= 9 else "10plus"


def hand_rows(doc: dict, *, peer: str, room: str) -> list[dict]:
    """每个官方单局同时抽出我方和指定强手，保持同桌关联。"""

    gid = doc["game_id"]
    seats = [item.get("user_id") for item in doc.get("seats") or []]
    if len(seats) != 4 or g59.US not in seats or PEERS[peer] not in seats:
        raise ValueError(f"G64 同桌四座身份缺失：{gid}")
    pair = {"us": seats.index(g59.US), peer: seats.index(PEERS[peer])}
    blocks = defaultdict(list)
    for block in doc.get("blocks") or []:
        blocks[block["round_no"]].append(block)
    if len(blocks) != 8:
        raise ValueError(f"G64 官方桌非八单局：{gid}")
    rows = []
    for round_no, pieces in sorted(blocks.items()):
        starts = [piece["start_hands"] for piece in pieces
                  if isinstance(piece.get("start_hands"), list)
                  and len(piece["start_hands"]) == 4]
        # 官方事件按块续传时，后续块的 start_hands 是续传快照；
        # 只取最早块，与 G59 已对账的起手口径一致。
        if not starts:
            raise ValueError(f"G64 起手牌缺失：{gid} r{round_no}")
        start = starts[0]
        events = [event for piece in pieces for event in piece.get("events") or []]
        endings = [event for event in events if event.get("type") == "round_ended"]
        if len(endings) != 1:
            raise ValueError(f"G64 官方终局不唯一：{gid} r{round_no}")
        end = endings[0]
        data = end.get("data") or {}
        winner = None if data.get("draw") else end.get("seat")
        fan, detail = data.get("fan") or 0, tuple(data.get("detail") or ())
        dealer, scores = data.get("dealer"), data.get("scores")
        if (type(dealer) is not int or dealer not in range(4) or
                not isinstance(scores, list) or len(scores) != 4 or
                sum(scores) != 0 or
                (winner is not None and (type(winner) is not int or winner not in range(4)))):
            raise ValueError(f"G64 权威终局字段非法：{gid} r{round_no}")
        discards = Counter(event["seat"] for event in events
                           if event.get("type") == "tile_discarded"
                           and type(event.get("seat")) is int)
        actors = {}
        for label, seat in pair.items():
            status = "win" if seat == winner else "draw" if winner is None else "other_win"
            start_white = start[seat].count("白")
            if not 0 <= start_white <= 4:
                raise ValueError("G64 起手白板超出物理上限")
            actors[label] = {"seat": seat, "start_white": start_white,
                             "dealer": seat == dealer,
                             "completed_discards": discards[seat],
                             "status": status,
                             "win_turn": discards[seat] + 1 if status == "win" else None,
                             "fan": fan if status == "win" else None,
                             "baotou": bool("爆头" in detail) if status == "win" else None,
                             "score": scores[seat]}
        rows.append({"peer": peer, "room": room, "game_id": gid,
                     "round_no": round_no, "winner_seat": winner,
                     "actors": actors})
    return rows


def add_counts(counter: Counter, actor: dict) -> None:
    """分母始终为单局起手；截尾只记实际发生的其他座位胡。"""

    counter["starts"] += 1
    counter["net"] += actor["score"]
    status = actor["status"]
    counter[status] += 1
    if status == "win":
        counter["plain_win"] += int(actor["fan"] == 1)
        counter["fan2plus_win"] += int(actor["fan"] >= 2)
        counter["baotou_win"] += int(actor["baotou"])
        counter["win_turn_" + turn_bucket(actor["win_turn"])] += 1
        counter[("plain" if actor["fan"] == 1 else "fan2plus") +
                "_turn_" + turn_bucket(actor["win_turn"])] += 1
    elif status == "other_win":
        count = actor["completed_discards"]
        counter["preempted_after_discards_0_3" if count <= 3 else
                "preempted_after_discards_4_6" if count <= 6 else
                "preempted_after_discards_7_9" if count <= 9 else
                "preempted_after_discards_10plus"] += 1


def main() -> None:
    """固定 G60 发布包及强手房，输出逐单局和房级汇总。"""

    if OUT.exists():
        raise SystemExit("G64 结果目录已存在，拒绝覆盖")
    manifest_path, result_path = _project_file(_PROJECT_ROOT, G60 / "manifest.json"), _project_file(_PROJECT_ROOT, G60 / "result.json")
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    g60_result = json.loads(result_path.read_text(encoding="utf-8"))
    if (g60_result["manifest_sha256"] != sha(manifest_path) or
            frozen["release_package_id"] != g60.PACKAGE or
            frozen["complete_rooms"] != 188):
        raise ValueError("G64 G60 冻结发布包漂移")
    units = sorted((peer, key.removesuffix("/" + peer))
                   for peer in PEERS for key in g60_result["room_rows"]
                   if key.endswith("/" + peer))
    if len(units) != 32 or Counter(peer for peer, _ in units) != {
            "xuanwu_2346": 15, "tengshe_0638": 17}:
        raise ValueError("G64 强手同桌房范围漂移")
    required_rooms = {room for _, room in units}
    docs = {room: {} for room in required_rooms}
    for _mtime, room, _tag, gid, doc in load_rooms():
        if room in docs and gid in frozen["included"][room]:
            if gid in docs[room]:
                raise ValueError("G64 官方 game_id 重复")
            docs[room][gid] = doc
    if any(set(by_gid) != set(frozen["included"][room]) for room, by_gid in docs.items()):
        raise ValueError("G64 G60 完整桌来源缺失")
    manifest = {"schema": "g64-strong-win-timing-manifest/1",
                "source_sha256": {"g60_manifest": sha(manifest_path),
                                  "g60_result": sha(result_path),
                                  "g64_prereg": sha(_project_file(_PROJECT_ROOT, HERE / "G64-STRONG-WIN-TIMING-PREREG-2026-09-28.md")),
                                  "g64_script": sha(Path(__file__))},
                "units": [{"peer": peer, "room": room,
                           "game_ids": frozen["included"][room]}
                          for peer, room in units],
                "source": "本地已归档官方 events.json；同一 R18 v2 发布包的 G60 完整房。"}
    rows = []
    groups: dict[str, Counter] = defaultdict(Counter)
    room_groups: dict[str, Counter] = defaultdict(Counter)
    for peer, room in units:
        for gid in frozen["included"][room]:
            for row in hand_rows(docs[room][gid], peer=peer, room=room):
                rows.append(row)
                for actor_name, actor in row["actors"].items():
                    name = "us" if actor_name == "us" else "peer"
                    axes = (("all", "all"),
                            ("start_white", g59.bucket(actor["start_white"])),
                            ("dealer", "yes" if actor["dealer"] else "no"))
                    for axis, value in axes:
                        add_counts(groups[peer + "/" + name + "/" + axis + "/" + value], actor)
                    add_counts(room_groups[peer + "/" + room + "/" + name], actor)
    if len(rows) != 2560:
        raise ValueError("G64 同桌官方单局母体不完整")
    for peer in PEERS:
        count = 1200 if peer == "xuanwu_2346" else 1360
        for name in ("us", "peer"):
            if groups[peer + "/" + name + "/all/all"]["starts"] != count:
                raise ValueError("G64 强手/我方同桌起手分母不一致")
            source_name = "us_vs_" + peer if name == "us" else peer
            for axis, values in (("all", ("all",)),
                                 ("start_white", ("0", "1", "2plus")),
                                 ("dealer", ("yes", "no"))):
                for value in values:
                    actual = groups[peer + "/" + name + "/" + axis + "/" + value]
                    prior = g60_result["groups"].get(source_name + "/" + axis + "/" + value, {})
                    for new_key, old_key in (("starts", "hands"), ("net", "net"),
                                             ("win", "wins"), ("plain_win", "plain_wins"),
                                             ("fan2plus_win", "fan2plus_wins"),
                                             ("baotou_win", "baotou_wins")):
                        if actual[new_key] != prior.get(old_key, 0):
                            raise ValueError("G64 起手/时序账与 G60 权威结算分层不符")
    body = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    result = {"schema": "g64-strong-win-timing-result/1",
              "manifest_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
              "rows": rows,
              "groups": {key: dict(sorted(value.items())) for key, value in sorted(groups.items())},
              "room_groups": {key: dict(sorted(value.items()))
                              for key, value in sorted(room_groups.items())},
              "boundary": "已发生单局的实际行动次序和他家先胡截尾；不是潜在可胡机会或候选因果收益。"}
    g60.write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    g60.write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({peer: {name: result["groups"][peer + "/" + name + "/all/all"]
                             for name in ("us", "peer")} for peer in PEERS},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
