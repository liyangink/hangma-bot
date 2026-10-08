#!/usr/bin/env python3
"""按起手牌形、白板和庄位分层审计我方与玄武同桌的首次入听。

赛后重建他家手牌只用于机制审计，绝不作为线上策略输入或收益标签。
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

from collections import Counter, defaultdict
import json
from pathlib import Path

import independent_xuanwu_four_room_audit as anatomy
from extract_room_scores import load_rooms
from peer_score_watch import manifest_identity
from anatomy_lib import round_blocks, reconstruct_round


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-tenpai-stratified-20260927/result.json')


def _bucket(shanten: int, whites: int, dealer: bool) -> str:
    """结果盲固定粗分层，不为某一强手结果调整切点。"""

    shanten_group = str(shanten) if shanten in (0, 1, 2) else "3plus"
    white_group = "0" if whites == 0 else "1plus"
    return f"start_shanten_{shanten_group}|white_{white_group}|dealer_{int(dealer)}"


def _add(counts: Counter, *, start_shanten: int, whites: int, dealer: bool,
         waits: list[dict], winner: bool, score: int) -> None:
    """以一个已结算单局为观测单位计数。"""

    counts["rounds"] += 1
    counts["initial_shanten_sum"] += start_shanten
    counts["initial_whites_sum"] += whites
    counts["wins"] += int(winner)
    counts["score_sum"] += score
    first = next((item for item in waits if item["shanten"] == 0), None)
    if first is not None:
        counts["reached_tenpai"] += 1
        counts["first_tenpai_turn_sum"] += first["turn"]
        counts["first_tenpai_width_sum"] += first["useful_n"]


def main() -> None:
    """固定当前 R18 v2 同桌房，逐局用唯一规则数学重算起手向听。"""

    identities = manifest_identity()
    by_stratum = defaultdict(lambda: {"us": Counter(), "xuanwu": Counter()})
    by_room = defaultdict(lambda: {"us": Counter(), "xuanwu": Counter()})
    rooms = set()
    tables = set()
    seen_rounds = set()
    for _mtime, room, _tag, game_id, doc in load_rooms():
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if anatomy.US not in seats or anatomy.XUANWU not in seats:
            continue
        if room not in identities or identities[room][0] != "r18_integrated_positive_v2":
            continue
        positions = {"us": seats.index(anatomy.US), "xuanwu": seats.index(anatomy.XUANWU)}
        for number, events, start_hands in round_blocks(doc):
            key = (game_id, number)
            if key in seen_rounds:
                raise ValueError("同一官方单局重复")
            seen_rounds.add(key)
            if start_hands is None:
                raise ValueError("起手暗牌缺失")
            ended = [event for event in events if event.get("type") == "round_ended"]
            if len(ended) != 1:
                raise ValueError("单局终局事件不唯一")
            terminal = ended[0]
            data = terminal.get("data") or {}
            scores = data.get("scores")
            if not isinstance(scores, list) or len(scores) != 4:
                raise ValueError("官方终局分数缺失")
            winner = None if data.get("draw") else terminal.get("seat")
            dealer = data.get("dealer")
            recon = reconstruct_round(events, start_hands)
            if recon["errors"]:
                raise ValueError("赛后重建失败：" + repr(recon["errors"][:2]))
            rooms.add(room)
            tables.add(game_id)
            for label, seat in positions.items():
                hand = start_hands[seat]
                shanten = anatomy.initial_shanten(hand)
                stratum = _bucket(shanten, hand.count("白"), seat == dealer)
                values = {"start_shanten": shanten, "whites": hand.count("白"),
                          "dealer": seat == dealer, "waits": recon["waits"][seat],
                          "winner": winner == seat, "score": scores[seat]}
                _add(by_stratum[stratum][label], **values)
                _add(by_room[room][label], **values)
    if not rooms:
        raise ValueError("没有已冻结 R18 v2 与玄武同桌官方房")
    overlap = 0
    weighted_gap = 0.0
    for actors in by_stratum.values():
        own = actors["us"]
        peer = actors["xuanwu"]
        own_n, peer_n = own["rounds"], peer["rounds"]
        if not own_n or not peer_n:
            continue
        weight = min(own_n, peer_n)
        overlap += weight
        weighted_gap += weight * (
            peer["reached_tenpai"] / peer_n - own["reached_tenpai"] / own_n)
    if not overlap:
        raise ValueError("起手分层没有共同支持")
    room_gap_positive = sum(
        actors["xuanwu"]["reached_tenpai"] > actors["us"]["reached_tenpai"]
        for actors in by_room.values())
    output = {"schema": "g8-tenpai-stratified-audit/1",
              "source_rooms": sorted(rooms), "full_tables": len(tables),
              "rounds": len(seen_rounds),
              "common_stratum_overlap_rounds_per_actor": overlap,
              "common_stratum_weighted_tenpai_rate_gap_xuanwu_minus_us": weighted_gap / overlap,
              "rooms_with_xuanwu_higher_tenpai_count": room_gap_positive,
              "strata": {key: {side: dict(sorted(counter.items())) for side, counter in actors.items()}
                         for key, actors in sorted(by_stratum.items())},
              "by_room": {room: {side: dict(sorted(counter.items())) for side, counter in actors.items()}
                          for room, actors in sorted(by_room.items())},
              "boundary": "不同玩家手牌不配对；起手向听、白板和庄位分层仍不能消除牌山与对手互动混杂；不把本表当候选收益"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    summary = {side: Counter() for side in ("us", "xuanwu")}
    for actors in by_room.values():
        for side in summary:
            summary[side].update(actors[side])
    print(json.dumps({"rooms": len(rooms), "tables": len(tables), "rounds": len(seen_rounds),
                      "summary": {side: dict(row) for side, row in summary.items()}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
