"""用官方赛后事件逐帧核对 SSE 甄别跳过，不读取测试身份凭据。

用法：python verify_sse_live.py AUDIT_ROOT OFFICIAL_EVENTS_ROOT
OFFICIAL_EVENTS_ROOT 下可按任意层级保存 events.json；每份文档须含 game_id。
"""

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
import json
from collections import Counter
from pathlib import Path


def rows(path: Path):
    """读取一份完整 JSONL；损坏行直接报错，避免把证据缺口误报为零差异。"""

    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def official_events(root: Path) -> dict[str, dict]:
    """按官方 game_id 建立事件和参赛座位索引；重复文档拒绝覆盖。"""

    result = {}
    for path in sorted(root.rglob("events.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        game_id = document["game_id"]
        if game_id in result:
            raise ValueError(f"重复官方 game_id: {game_id}")
        events = {}
        for block in document["blocks"]:
            for event in block["events"]:
                seq = event["seq"]
                if seq in events and events[seq] != event:
                    raise ValueError(f"官方事件冲突: {game_id} seq={seq}")
                events[seq] = event
        result[game_id] = {
            "events": events,
            "seats": {item["user_id"]: seat for seat, item in enumerate(document["seats"])},
        }
    if not result:
        raise ValueError("找不到官方 events.json")
    return result


def matches(reason: str, seq: int, seat: int, events: dict[int, dict]) -> bool:
    """只验证本次跳过所需的类型、阶段及座位事实。"""

    def event(at: int) -> dict:
        return events.get(at, {})

    def timeout(at: int, window: str) -> bool:
        item = event(at)
        return item.get("type") == "timeout" and (item.get("data") or {}).get("window") == window

    if reason == "accepted_own_discard_echo":
        return event(seq).get("type") == "tile_discarded" and event(seq).get("seat") == seat
    if reason == "plain_peng_timeout_group":
        return all(timeout(at, "peng") for at in range(seq - 2, seq + 1))
    if reason == "chi_timeout_opponent_draw":
        return (timeout(seq - 1, "chi") and event(seq).get("type") == "tile_drawn"
                and event(seq).get("seat") != seat)
    if reason == "opponent_draw_after_chi_timeout":
        return event(seq).get("type") == "tile_drawn" and event(seq).get("seat") != seat
    return False


def verify(audit_root: Path, official_root: Path) -> dict:
    """输出每身份跳过数、官方不符清单与 SSE 帧步长文法计数。"""

    truth = official_events(official_root)
    result = {"official_games": len(truth), "slots": {}, "frame_patterns": {}}
    for slot_dir in sorted(audit_root.glob("slot-*")):
        counts = Counter()
        mismatches = []
        game_files = sorted(slot_dir.glob("runs/*/participants/*/games/*.jsonl"))
        for path in game_files:
            game_id = path.stem
            participant_id = path.parents[1].name
            source = truth.get(game_id)
            if source is None or participant_id not in source["seats"]:
                raise ValueError(f"缺官方游戏或参赛座位: {game_id}")
            for row in rows(path):
                payload = row.get("payload") or {}
                reason = payload.get("sse_skip_reason")
                if reason is None:
                    continue
                counts[reason] += 1
                seq = payload["observed_seq"]
                if not matches(reason, seq, source["seats"][participant_id], source["events"]):
                    mismatches.append({"game_id": game_id, "seq": seq, "reason": reason})
        result["slots"][slot_dir.name] = {
            "games": len(game_files), "skips": dict(counts), "official_mismatches": mismatches,
        }
    # 四席观察同一批物理事件，只取一席统计帧文法，避免伪造四倍样本量。
    first_slot = next(iter(sorted(audit_root.glob("slot-*"))), None)
    if first_slot is not None:
        patterns = Counter()
        for path in sorted(first_slot.glob("runs/*/participants/*/raw/t_*.jsonl")):
            source = truth.get(path.stem)
            if source is None:
                raise ValueError(f"缺官方游戏: {path.stem}")
            previous = 0
            for row in rows(path):
                payload = row.get("payload") or {}
                if payload.get("source") != "sse_frame" or payload.get("closed"):
                    continue
                seq = payload["seq"]
                if seq <= previous:
                    continue
                events = source["events"]
                pattern = "+".join(
                    str((events.get(at) or {}).get("type", "missing"))
                    + (":" + str(((events.get(at) or {}).get("data") or {}).get("window"))
                       if (events.get(at) or {}).get("type") == "timeout" else "")
                    for at in range(previous + 1, seq + 1)
                )
                patterns[pattern] += 1
                previous = seq
        result["frame_patterns"] = dict(patterns)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_root", type=Path)
    parser.add_argument("official_events_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.audit_root, args.official_events_root), ensure_ascii=False, indent=2))
