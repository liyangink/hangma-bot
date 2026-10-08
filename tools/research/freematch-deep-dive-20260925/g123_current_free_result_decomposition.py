#!/usr/bin/env python3
"""G123：按 G122 冻结房名单拆近期自由赛胡牌收入和未胡付分。"""

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
PRIOR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g111-current-free-cohort-20260928/result.json')
CURRENT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g122-current-free-cohort-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g123-current-free-result-decomposition-20260928/result.json')


def sha(path: Path) -> str:
    """绑定冻结官方房集合、分类器与本程序。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """三个互斥时期逐桌逐局核对官方零和计分与胡型。"""
    if OUT.exists():
        raise FileExistsError("G123 已有证据，拒绝覆盖")
    old = json.loads(OLD.read_text(encoding="utf-8"))["included"]
    prior = json.loads(PRIOR.read_text(encoding="utf-8"))["included"]
    current = json.loads(CURRENT.read_text(encoding="utf-8"))["included"]
    if (len(old) != 204 or len(prior) != 217 or
            not set(old).issubset(prior) or not set(prior).issubset(current)):
        raise ValueError("G123 冻结房名单不是 204→217→当前的增量")
    periods = (("old_204", set(old)), ("g111_added_13", set(prior) - set(old)),
               ("g122_added", set(current) - set(prior)))
    docs = defaultdict(dict)
    for _mtime, room, _tag, game_id, document in load_rooms():
        if room in current and game_id in current[room]["game_ids"]:
            docs[room][game_id] = document
    if any(set(docs[room]) != set(current[room]["game_ids"]) for room in current):
        raise ValueError("G123 官方原文与 G122 场次身份不一致")
    result_groups = {}
    for label, rooms in periods:
        groups = defaultdict(Counter)
        room_rows = defaultdict(Counter)
        trace = Counter()
        ids = {game_id for room in rooms for game_id in current[room]["game_ids"]}
        for room in sorted(rooms):
            for game_id in current[room]["game_ids"]:
                if not g59.audit_game(docs[room][game_id], ids, rooms,
                                      groups, room_rows, trace):
                    raise ValueError("G123 冻结单局未被官方分类器接收")
        mine = groups["us/all/all"]
        if (trace["games"] != 10 * len(rooms) or trace["hands"] != 80 * len(rooms)
                or mine["net"] != sum(current[room]["our_score"] for room in rooms)):
            raise ValueError("G123 房/桌/单局积分不守恒")
        result_groups[label] = {
            "rooms": len(rooms), "tables": trace["games"], "hands": trace["hands"],
            "our": dict(sorted(mine.items())),
            "our_start_white": {
                white: dict(sorted(groups[f"us/start_white/{white}"].items()))
                for white in ("0", "1", "2plus")},
        }
    if sum(group["our"]["net"] for group in result_groups.values()) != (
            json.loads(CURRENT.read_text(encoding="utf-8"))["our_score"]):
        raise ValueError("G123 时期合计净分不守恒")
    result = {
        "schema": "g123-current-free-result-decomposition/1",
        "input_sha256": {"script": sha(Path(__file__)), "g85": sha(OLD),
                         "g111": sha(PRIOR), "g122": sha(CURRENT),
                         "g59": sha(_project_file(_PROJECT_ROOT, HERE / "g59_freematch_white_value_audit.py"))},
        "groups": result_groups,
        "added_since_g111": sorted(set(current) - set(prior)),
        "boundary": "按归档时期形成的非随机房组；新房小样本不能归因于算法退化、"
                    "白板供给或具体动作。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({label: {"rooms": group["rooms"],
                              "net": group["our"]["net"],
                              "wins": group["our"]["wins"],
                              "plain_wins": group["our"]["plain_wins"],
                              "fan2plus_wins": group["our"]["fan2plus_wins"]}
                      for label, group in result_groups.items()},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
