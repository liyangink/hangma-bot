"""核对官方赛后牌谱中，本人跨局首弃牌是否被超时模切。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import json
from pathlib import Path


def verify(official_root: Path, participant_id: str) -> dict:
    """返回完整桌数及本人跨局首弃牌超时；原文缺失或摘要不符直接失败。"""

    sources = sorted(official_root.rglob("source.json"))
    if not sources:
        raise ValueError("找不到官方赛后原文")
    windows = []
    affected = []
    games: dict[str, str] = {}
    duplicate_downloads = 0
    for source_path in sources:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        events_path = source_path.with_name("events.json")
        digest = hashlib.sha256(events_path.read_bytes()).hexdigest()
        if digest != source["original_sha256"]:
            raise ValueError(f"官方原文摘要不符: {events_path}")
        document = json.loads(events_path.read_text(encoding="utf-8"))
        if document.get("status") != "finished":
            raise ValueError(f"官方完整桌未结束: {events_path}")
        game_id = document["game_id"]
        if game_id in games:
            if games[game_id] != digest:
                raise ValueError(f"同一官方场次有不同原文: {game_id}")
            duplicate_downloads += 1
            continue
        games[game_id] = digest
        seats = [row["user_id"] for row in document["seats"]]
        if seats.count(participant_id) != 1:
            raise ValueError(f"本人座位缺失或重复: {game_id}")
        focal = seats.index(participant_id)
        # 官方 blocks 可在同一局内按事件量拆成多个块，不能把每个块
        # 都误当成新局；先按连续 round_no 拼回完整单局事件。
        rounds = []
        for block in document["blocks"]:
            if rounds and rounds[-1]["round_no"] == block["round_no"]:
                if rounds[-1]["dealer"] != block["dealer"]:
                    raise ValueError(f"同局公开庄家冲突: {game_id} 第 {block['round_no']} 局")
                rounds[-1]["events"].extend(block["events"])
                rounds[-1]["truncated"] |= bool(block.get("truncated"))
            else:
                if rounds and block["round_no"] != rounds[-1]["round_no"] + 1:
                    raise ValueError(f"官方局序不连续: {game_id} 第 {block['round_no']} 局")
                rounds.append({"round_no": block["round_no"],
                               "dealer": block["dealer"],
                               "truncated": bool(block.get("truncated")),
                               "events": list(block["events"])})
        for previous, current in zip(rounds, rounds[1:]):
            if current["dealer"] != focal:
                continue
            if (previous["truncated"] or current["truncated"]
                    or not any(event.get("type") == "round_ended"
                               for event in previous["events"])):
                raise ValueError(f"跨局事件不完整: {game_id} 第 {current['round_no']} 局")
            events = current["events"]
            first_discard = next(
                (event for event in events if event.get("type") == "tile_discarded"), None
            )
            # 庄家若直接胡或杠而未弃牌，则本局没有可核的首弃牌窗。
            if first_discard is None:
                continue
            if first_discard.get("seat") != focal:
                raise ValueError(f"首弃牌座位与公开庄家不符: {game_id} 第 {current['round_no']} 局")
            row = {"game_id": game_id, "round_no": current["round_no"],
                   "discard_seq": first_discard["seq"]}
            windows.append(row)
            next_own_discard = next(
                (event["seq"] for event in events
                 if event.get("type") == "tile_discarded"
                 and event.get("seat") == focal
                 and event["seq"] > first_discard["seq"]), None
            )
            # 官方可能先记录下一家的摸牌，随后才记录本次自动弃牌的
            # timeout；只按“紧邻下一条”判断会产生假阴性。
            timeouts = [event for event in events
                        if event.get("type") == "timeout"
                        and event.get("seat") == focal
                        and (event.get("data") or {}).get("kind") == "discard"
                        and event["seq"] > first_discard["seq"]
                        and (next_own_discard is None
                             or event["seq"] < next_own_discard)]
            if len(timeouts) > 1:
                raise ValueError(f"同一首弃牌窗有多个弃牌超时: {game_id} 第 {current['round_no']} 局")
            if timeouts:
                affected.append({**row, "timeout_seq": timeouts[0]["seq"]})
    return {"schema": "sse-settled-first-discard-check/2",
            "complete_games": len(games), "focal_first_discard_windows": len(windows),
            "focal_first_discard_timeouts": len(affected),
            "duplicate_official_downloads": duplicate_downloads, "affected": affected}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("official_root", type=Path)
    parser.add_argument("participant_id")
    args = parser.parse_args()
    result = verify(args.official_root, args.participant_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["focal_first_discard_timeouts"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
