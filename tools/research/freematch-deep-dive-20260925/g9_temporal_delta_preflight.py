#!/usr/bin/env python3
"""结果盲抽取两次本人摸牌间的最小公开差分，验证覆盖与自然变化。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path

import g8_public_response_training_rows as source


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-delta-preflight-20260927/result.json')


def _summary(observation: dict) -> tuple[int, tuple[int, ...], tuple[int, ...], int] | None:
    """只取当前官方观察中公开的墙余及四座弃牌/副露数，保持座位顺序。"""

    seat = observation.get("seat")
    wall = observation.get("remaining_tile_count")
    rivers = observation.get("discards")
    melds = observation.get("melds")
    seq = observation.get("consumed_seq")
    if type(seat) is not int or not 0 <= seat < 4 or type(wall) is not int or type(seq) is not int:
        return None
    if not isinstance(rivers, list) or not isinstance(melds, list) or len(rivers) != 4 or len(melds) != 4:
        return None
    if any(not isinstance(row, list) for row in rivers + melds):
        return None
    return wall, tuple(len(rivers[(seat + delta) % 4]) for delta in range(4)), \
        tuple(len(melds[(seat + delta) % 4]) for delta in range(4)), seq


def main() -> None:
    """逐房统计差分；本程序不读取官方牌谱或训练标签。"""

    if OUT.exists():
        raise SystemExit("时序差分预检已冻结，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    total = Counter()
    by_room = {}
    for room in frozen["rooms"]:
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作审计漂移")
        accepted = source._accepted(decision_file)
        previous = {}
        counts = Counter()
        for context, request, _plan in source.screen._iter_decisions(audit):
            if (request.get("window_key") or {}).get("phase") != "draw":
                continue
            action = accepted.get(context.get("decision_id"))
            if not action or not action.startswith("discard:"):
                continue
            key = (context["game_id"], context["round_no"])
            observation = request["observation"]
            current = _summary(observation)
            counts["accepted_draw_discards"] += 1
            if current is None:
                counts["current_summary_unknown"] += 1
                previous.pop(key, None)
                continue
            prior = previous.get(key)
            if prior is None:
                counts["prior_missing"] += 1
            else:
                old, old_seat = prior
                if old_seat != observation["seat"]:
                    counts["seat_changed_same_round"] += 1
                    previous.pop(key, None)
                    continue
                wall_delta = old[0] - current[0]
                river_delta = tuple(now - before for now, before in zip(current[1], old[1]))
                meld_delta = tuple(now - before for now, before in zip(current[2], old[2]))
                seq_delta = current[3] - old[3]
                if wall_delta < 0 or seq_delta <= 0 or any(delta < 0 for delta in river_delta + meld_delta):
                    counts["nonmonotone_delta"] += 1
                    previous.pop(key, None)
                    continue
                counts["prior_usable"] += 1
                counts[f"seq_gap_{min(seq_delta, 100)}"] += 1
                counts[f"wall_delta_{min(wall_delta, 20)}"] += 1
                counts[f"opponent_river_delta_{','.join(str(min(value, 3)) for value in river_delta[1:])}"] += 1
                counts[f"opponent_meld_delta_{','.join(str(min(value, 2)) for value in meld_delta[1:])}"] += 1
                counts["opponent_extra_river"] += any(value > 1 for value in river_delta[1:])
                counts["opponent_new_meld"] += any(value > 0 for value in meld_delta[1:])
                counts["opponent_no_discard"] += any(value == 0 for value in river_delta[1:])
            previous[key] = (current, observation["seat"])
        by_room[room["room_id"]] = dict(sorted(counts.items()))
        total.update(counts)
    result = {
        "schema": "g9-temporal-delta-preflight/1",
        "source_rooms": len(by_room),
        "source_frozen_rooms_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
        "source_parent_sha256": frozen["parent_source_sha256"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "outcome_blind": True,
        "totals": dict(sorted(total.items())),
        "rooms_with_usable_prior": sum(row.get("prior_usable", 0) > 0 for row in by_room.values()),
        "rooms_with_extra_river": sum(row.get("opponent_extra_river", 0) > 0 for row in by_room.values()),
        "rooms_with_new_meld": sum(row.get("opponent_new_meld", 0) > 0 for row in by_room.values()),
        "by_room": by_room,
        "boundary": "公开前态差分；失忆/重连需弃权；未读取后续比赛结果"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
