#!/usr/bin/env python3
"""G117：对照 G111 新增 13 房与先前 204 房的官方胡型收支。"""

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
OLD = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g85-immediate-post-claim-discard-20260928/free_census.json')
CURRENT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g111-current-free-cohort-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g117-recent-free-result-decomposition-20260928/result.json')


def sha(path: Path) -> str:
    """将已冻结的房间集合、分类程序和本脚本绑定。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """逐桌逐局用官方终局事件复核胡型、白板供给和收支。"""
    if OUT.exists():
        raise FileExistsError("G117 对比结果已存在，拒绝覆盖")
    old = json.loads(OLD.read_text(encoding="utf-8"))["included"]
    current_doc = json.loads(CURRENT.read_text(encoding="utf-8"))
    current = current_doc["included"]
    if len(old) != 204 or len(current) != 217 or not set(old).issubset(current):
        raise ValueError("G117 冻结 204/217 房关系不成立")
    new_rooms = set(current) - set(old)
    by_room: dict[str, dict[str, dict]] = defaultdict(dict)
    for _, room, _, game_id, document in load_rooms():
        if room in current:
            by_room[room][game_id] = document
    if any(set(games) != set(current[room]["game_ids"])
           for room, games in by_room.items()):
        raise ValueError("G117 官方 game_id 集合与 G111 不一致")
    result_groups = {}
    for label, rooms in (("previous_204", set(old)), ("added_13", new_rooms)):
        groups: dict[str, Counter] = defaultdict(Counter)
        room_rows: dict[str, Counter] = defaultdict(Counter)
        trace = Counter()
        ids = {game_id for room in rooms for game_id in current[room]["game_ids"]}
        for room in sorted(rooms):
            for game_id in current[room]["game_ids"]:
                doc = by_room[room][game_id]
                if not g59.audit_game(doc, ids, rooms, groups, room_rows, trace):
                    raise ValueError("G117 冻结场次未纳入分解")
        if trace["games"] != len(rooms) * 10 or trace["hands"] != len(rooms) * 80:
            raise ValueError("G117 桌/单局计数不守恒")
        us = groups["us/all/all"]
        if us["net"] != sum(current[room]["our_score"] for room in rooms):
            raise ValueError("G117 本人净分与 G111 冻结快照不一致")
        result_groups[label] = {
            "rooms": len(rooms), "tables": trace["games"],
            "hands": trace["hands"],
            "our": dict(sorted(us.items())),
            "other": dict(sorted(groups["other/all/all"].items())),
            "our_start_white": {
                white: dict(sorted(groups[f"us/start_white/{white}"].items()))
                for white in ("0", "1", "2plus")},
        }
    result = {
        "schema": "g117-recent-free-result-decomposition/1",
        "source_sha256": {
            "script": sha(Path(__file__)), "g85": sha(OLD),
            "g111": sha(CURRENT),
            "g59": sha(_project_file(_PROJECT_ROOT, HERE / "g59_freematch_white_value_audit.py")),
        },
        "new_room_ids": sorted(new_rooms),
        "groups": result_groups,
        "boundary": "两期房间由归档时间/可用性形成，非随机分配；只能描述近期波动。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({label: {"rooms": item["rooms"], "tables": item["tables"],
                              "our": item["our"]}
                      for label, item in result_groups.items()},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
