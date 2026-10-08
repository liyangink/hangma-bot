#!/usr/bin/env python3
"""G111：只读冻结当前同发布包自由赛完整房、对手同桌账。"""

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

from collections import defaultdict
import hashlib
import json
from pathlib import Path

from extract_room_scores import load_rooms
from peer_score_watch import manifest_identity, PEERS, US
import g60_full_free_cohort_audit as g60


HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g85-immediate-post-claim-discard-20260928/free_census.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g111-current-free-cohort-20260928/result.json')


def sha(path: Path) -> str:
    """记录脚本与旧房快照的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """从官方已归档事件逐单局核对零和、完整度及发布身份。"""
    if OUT.exists():
        raise FileExistsError("G111 快照已存在，拒绝覆盖")
    identities = manifest_identity()
    target = {room for room, identity in identities.items()
              if identity == (g60.POLICY, g60.PACKAGE)}
    by_room: dict[str, dict[str, dict]] = defaultdict(dict)
    for _, room, _, game_id, document in load_rooms():
        if room in target:
            by_room[room][game_id] = document
    old = json.loads(OLD.read_text(encoding="utf-8"))["included"]
    included = {}
    excluded = {}
    for room in sorted(target):
        games = by_room.get(room, {})
        if len(games) != 10:
            excluded[room] = "complete_game_count:" + str(len(games))
            continue
        score = 0
        peers = {name: {"tables": 0, "our_score": 0, "peer_score": 0}
                 for name in PEERS}
        invalid = None
        for game_id, doc in games.items():
            seats = [seat.get("user_id") for seat in doc.get("seats") or []]
            if len(seats) != 4 or seats.count(US) != 1:
                invalid = "seat_identity:" + game_id
                break
            ended = [event for block in doc.get("blocks") or []
                     for event in block.get("events") or []
                     if event.get("type") == "round_ended"]
            if len(ended) != 8:
                invalid = "round_count:" + game_id
                break
            vectors = [(event.get("data") or {}).get("scores") for event in ended]
            if any(not isinstance(vector, list) or len(vector) != 4
                   or any(type(value) is not int for value in vector)
                   or sum(vector) != 0 for vector in vectors):
                invalid = "score_vector:" + game_id
                break
            mine = seats.index(US)
            game_score = sum(vector[mine] for vector in vectors)
            score += game_score
            for name, user_id in PEERS.items():
                if user_id in seats:
                    entry = peers[name]
                    entry["tables"] += 1
                    entry["our_score"] += game_score
                    entry["peer_score"] += sum(vector[seats.index(user_id)] for vector in vectors)
        if invalid:
            excluded[room] = invalid
            continue
        if room in old and sorted(games) != old[room]["game_ids"]:
            raise ValueError("G111 旧房官方 game_id 集合漂移：" + room)
        if room in old and score != old[room]["our_score"]:
            raise ValueError("G111 旧房积分漂移：" + room)
        included[room] = {"game_ids": sorted(games), "our_score": score,
                          "peer": {name: value for name, value in peers.items()
                                   if value["tables"]}}
    if set(old) - set(included):
        raise ValueError("G111 旧完整房没有全部进入新快照")
    score = sum(item["our_score"] for item in included.values())
    by_peer = {}
    for name in PEERS:
        rows = [row["peer"][name] for row in included.values() if name in row["peer"]]
        by_peer[name] = {
            "rooms": len(rows), "tables": sum(row["tables"] for row in rows),
            "our_score": sum(row["our_score"] for row in rows),
            "peer_score": sum(row["peer_score"] for row in rows),
        }
        by_peer[name]["peer_minus_our_per_table"] = (
            (by_peer[name]["peer_score"] - by_peer[name]["our_score"])
            / by_peer[name]["tables"] if by_peer[name]["tables"] else None)
    result = {
        "schema": "g111-current-free-cohort-snapshot/1",
        "policy": g60.POLICY, "package": g60.PACKAGE,
        "source_sha256": {"script": sha(Path(__file__)), "g85_snapshot": sha(OLD),
                          "extract_room_scores": sha(_project_file(_PROJECT_ROOT, HERE / "extract_room_scores.py")),
                          "peer_score_watch": sha(_project_file(_PROJECT_ROOT, HERE / "peer_score_watch.py"))},
        "identity_rooms": len(target), "complete_rooms": len(included),
        "complete_tables": len(included) * 10,
        "complete_rounds": len(included) * 80,
        "our_score": score, "our_per_table": score / (len(included) * 10),
        "new_complete_rooms": len(set(included) - set(old)),
        "new_complete_room_score": sum(included[room]["our_score"]
                                       for room in set(included) - set(old)),
        "by_peer": by_peer, "included": included, "excluded": excluded,
        "boundary": "官方已归档完整房的观察性快照；房/座位/牌山非策略随机配对。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "identity_rooms", "complete_rooms", "complete_tables", "our_score",
        "our_per_table", "new_complete_rooms", "new_complete_room_score", "by_peer")},
        ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
