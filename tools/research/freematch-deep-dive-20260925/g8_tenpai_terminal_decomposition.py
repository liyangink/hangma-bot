#!/usr/bin/env python3
"""把同桌强手与我方未入听单局按局终事实分解，限作观察性诊断。"""

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
import json
from pathlib import Path

import independent_xuanwu_four_room_audit as anatomy
from extract_room_scores import load_rooms
from peer_score_watch import manifest_identity
from anatomy_lib import round_blocks, reconstruct_round


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-tenpai-terminal-20260927/result.json')
BASELINE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-tenpai-stratified-20260927/result.json')


def _terminal_bucket(*, waits: list[dict], winner: int | None,
                     actor: int, peer: int) -> str:
    """按赛后事实互斥分组；末次等待态不是未摸取牌墙的反事实。"""

    if any(row["shanten"] == 0 for row in waits):
        return "reached_tenpai"
    if not waits:
        return "no_wait_snapshot"
    end_shanten = waits[-1]["shanten"]
    distance = "one_shanten" if end_shanten == 1 else "two_plus"
    ending = "draw" if winner is None else "peer_hu" if winner == peer else "other_hu"
    if winner == actor:
        raise ValueError("本人胡却从未出现听牌等待态，请核对重建口径")
    return f"not_tenpai|{distance}|{ending}"


def main() -> None:
    """固定已用于选题的九间官方房，仅做逐房描述，不作为候选确认。"""

    identities = manifest_identity()
    source_rooms = set(json.loads(BASELINE.read_text(encoding="utf-8"))["source_rooms"])
    if len(source_rooms) != 9:
        raise ValueError("冻结同桌房数不符")
    by_room = defaultdict(lambda: {"us": Counter(), "xuanwu": Counter()})
    paired = Counter()
    seen = set()
    games = set()
    for _mtime, room, _tag, game_id, doc in load_rooms():
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if anatomy.US not in seats or anatomy.XUANWU not in seats:
            continue
        if room not in source_rooms:
            continue
        if room not in identities or identities[room][0] != "r18_integrated_positive_v2":
            continue
        positions = {"us": seats.index(anatomy.US), "xuanwu": seats.index(anatomy.XUANWU)}
        games.add(game_id)
        for round_no, events, start_hands in round_blocks(doc):
            key = (game_id, round_no)
            if key in seen:
                raise ValueError("同一单局重复")
            seen.add(key)
            if start_hands is None:
                raise ValueError("起手暗牌缺失")
            terminal = [event for event in events if event.get("type") == "round_ended"]
            if len(terminal) != 1:
                raise ValueError("终局事件不唯一")
            event = terminal[0]
            winner = None if (event.get("data") or {}).get("draw") else event.get("seat")
            recon = reconstruct_round(events, start_hands)
            if recon["errors"]:
                raise ValueError("赛后重建失败：" + repr(recon["errors"][:2]))
            reached = {label: any(row["shanten"] == 0 for row in recon["waits"][actor])
                       for label, actor in positions.items()}
            winner_group = ("us" if winner == positions["us"] else
                            "xuanwu" if winner == positions["xuanwu"] else
                            "draw" if winner is None else "other")
            paired[f"us_{int(reached['us'])}|xuanwu_{int(reached['xuanwu'])}"] += 1
            paired[f"winner_{winner_group}|us_{int(reached['us'])}|xuanwu_{int(reached['xuanwu'])}"] += 1
            for label, actor in positions.items():
                peer = positions["xuanwu" if label == "us" else "us"]
                waits = recon["waits"][actor]
                bucket = _terminal_bucket(waits=waits, winner=winner, actor=actor, peer=peer)
                counts = by_room[room][label]
                counts["rounds"] += 1
                counts[bucket] += 1
                if bucket != "reached_tenpai":
                    counts["non_tenpai_last_wait_shanten_sum"] += waits[-1]["shanten"] if waits else 0
                    counts["non_tenpai_last_wait_count"] += int(bool(waits))
                    counts["non_tenpai_last_wait_turn_sum"] += waits[-1]["turn"] if waits else 0
                    counts["non_tenpai_last_wait_turn_count"] += int(bool(waits))
    if set(by_room) != source_rooms or len(games) != 90 or len(seen) != 720:
        raise ValueError(f"同桌来源变更：{len(by_room)} 房、{len(games)} 桌、{len(seen)} 局")
    total = {side: Counter() for side in ("us", "xuanwu")}
    for actors in by_room.values():
        for side, counts in actors.items():
            total[side].update(counts)
    for side, counts in total.items():
        if counts["rounds"] != 720:
            raise ValueError(f"{side} 逐局口径不全")
        classified = sum(value for key, value in counts.items()
                         if key == "reached_tenpai" or key == "no_wait_snapshot"
                         or key.startswith("not_tenpai|"))
        if classified != 720:
            raise ValueError(f"{side} 互斥局终分类不守恒")
    result = {"schema": "g8-tenpai-terminal-decomposition/1",
              "source_rooms": sorted(by_room), "full_tables": len(games), "rounds": len(seen),
              "same_round_tenpai_pair_counts": dict(sorted(paired.items())),
              "total": {side: dict(sorted(counts.items())) for side, counts in total.items()},
              "by_room": {room: {side: dict(sorted(counts.items())) for side, counts in actors.items()}
                          for room, actors in sorted(by_room.items())},
              "boundary": "赛后重建和局终结果，仅作观察性分解；本人与对手暗手不配对，末次等待态不代表本可摸到的反事实牌"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"total": result["total"], "same_round_tenpai_pair_counts":
                      result["same_round_tenpai_pair_counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
