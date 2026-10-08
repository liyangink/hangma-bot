#!/usr/bin/env python3
"""G85 附录：只读复算同一冻结发布包已完整归档的自由赛房。"""

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
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parents[0] / "baotou-anatomy-20260925")))

import anatomy_lib as anatomy
from extract_room_scores import load_rooms
import g59_freematch_white_value_audit as g59
import g60_full_free_cohort_audit as g60
from peer_score_watch import manifest_identity


OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g85-immediate-post-claim-discard-20260928/free_census.json')
G60 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927/manifest.json')


def sha(path: Path) -> str:
    """将冻结比较集与脚本源码摘要写入证据。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """按发布身份、官方完整桌与八个零和终局筛房；不推断候选效果。"""
    if OUT.exists():
        raise SystemExit("G85 自由赛快照已存在，拒绝覆盖")
    targets = {room for room, identity in manifest_identity().items()
               if identity == (g60.POLICY, g60.PACKAGE)}
    by_room = defaultdict(list)
    for _, room, _, game_id, doc in load_rooms():
        if room in targets:
            by_room[room].append((game_id, doc))
    included = {}
    excluded = {}
    for room in sorted(targets):
        games = by_room.get(room, [])
        if len(games) != 10 or len({game_id for game_id, _ in games}) != 10:
            excluded[room] = "complete_game_count:" + str(len(games))
            continue
        room_score = 0
        room_rounds = 0
        valid = True
        for _, doc in games:
            seats = [item.get("user_id") for item in doc.get("seats") or []]
            if seats.count(g59.US) != 1:
                raise ValueError("同包桌我方座位身份不唯一")
            seat = seats.index(g59.US)
            rounds = list(anatomy.round_blocks(doc))
            if len(rounds) != 8:
                valid = False
                break
            for _, events, _ in rounds:
                ended = [event for event in events if event.get("type") == "round_ended"]
                if len(ended) != 1:
                    valid = False
                    break
                scores = (ended[0].get("data") or {}).get("scores")
                if (not isinstance(scores, list) or len(scores) != 4 or
                        any(type(value) is not int for value in scores) or sum(scores) != 0):
                    raise ValueError("官方终局积分向量非四座零和")
                room_score += scores[seat]
                room_rounds += 1
            if not valid:
                break
        if not valid or room_rounds != 80:
            excluded[room] = "incomplete_rounds"
            continue
        included[room] = {"tables": len(games), "rounds": room_rounds,
                          "our_score": room_score,
                          "game_ids": sorted(game_id for game_id, _ in games)}
    old = json.loads(G60.read_text(encoding="utf-8"))["included"]
    if len(old) != 188 or not set(old).issubset(included):
        raise ValueError("G60 已冻结完整房未被当前归档包含")
    for room, games in old.items():
        if included[room]["game_ids"] != games:
            raise ValueError("G60 已冻结房官方场次身份漂移")
    old_score = sum(included[room]["our_score"] for room in old)
    if old_score != 6014:
        raise ValueError("G60 旧房结算与冻结报告不一致")
    total = sum(row["our_score"] for row in included.values())
    result = {"schema": "g85-free-census/1", "policy": g60.POLICY,
              "package": g60.PACKAGE, "exploratory": True,
              "source_sha256": {"g60_manifest": sha(G60), "script": sha(Path(__file__))},
              "identity_rooms": len(targets), "complete_rooms": len(included),
              "complete_tables": sum(row["tables"] for row in included.values()),
              "complete_rounds": sum(row["rounds"] for row in included.values()),
              "our_score": total, "our_per_table": total / (10 * len(included)),
              "old_188_score": old_score, "new_rooms": len(included) - len(old),
              "new_rooms_score": total - old_score,
              "excluded": excluded, "included": included,
              "boundary": "自由赛房受配桌与牌山选择影响；只为同包累计表现快照。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "identity_rooms", "complete_rooms", "complete_tables", "complete_rounds",
        "our_score", "our_per_table", "new_rooms", "new_rooms_score")},
        ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
