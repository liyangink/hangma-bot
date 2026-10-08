#!/usr/bin/env python3
"""G120：用当前完整自由赛房复核强手同桌的胡牌行动时序。"""

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
import g64_strong_win_timing as g64


HERE = Path(__file__).resolve().parent
CURRENT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g122-current-free-cohort-20260928/result.json')
PRIOR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g64-strong-win-timing-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g120-current-strong-win-timing-20260928/result.json')
PEER_NAMES = {"xuanwu_2346": "玄武-2346", "tengshe_0638": "腾蛇-0638",
              "astra_0": "Astra-0"}


def sha(path: Path) -> str:
    """记录本次只读分析所绑定的输入字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """按 G122 的冻结完整房名单核官方原文，保留房级聚合。"""
    if OUT.exists():
        raise FileExistsError("G120 已有证据，拒绝覆盖")
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    prior = json.loads(PRIOR.read_text(encoding="utf-8"))
    if current["schema"] != "g122-current-free-cohort-snapshot/1":
        raise ValueError("G120 G122 来源 schema 错误")
    source_rooms = {
        peer: {room for room, item in current["included"].items()
               if PEER_NAMES[peer] in item["peer"]}
        for peer in PEER_NAMES
    }
    # G64 原分析只纳入玄武、腾蛇；本次将同一官方时序量具用于 Astra。
    g64.PEERS["astra_0"] = g59.PEERS["astra_0"]
    docs = defaultdict(dict)
    for _mtime, room, _tag, game_id, doc in load_rooms():
        if room in set().union(*source_rooms.values()):
            docs[room][game_id] = doc
    old_index = {
        (row["peer"], row["room"], row["game_id"], row["round_no"]): row
        for row in prior["rows"]
    }
    matched_old = set()
    groups = defaultdict(Counter)
    room_groups = defaultdict(Counter)
    for peer, rooms in source_rooms.items():
        for room in sorted(rooms):
            frozen = current["included"][room]["game_ids"]
            if set(docs[room]) != set(frozen):
                raise ValueError("G120 官方 game_id 与 G122 冻结完整房不一致：" + room)
            for game_id in frozen:
                for row in g64.hand_rows(docs[room][game_id], peer=peer, room=room):
                    old_key = peer, room, game_id, row["round_no"]
                    if old_key in old_index:
                        if row != old_index[old_key]:
                            raise ValueError("G120 与 G64 既有官方单局对账失败")
                        matched_old.add(old_key)
                    for actor_name, actor in row["actors"].items():
                        label = "us" if actor_name == "us" else "peer"
                        g64.add_counts(groups[peer + "/" + label], actor)
                        g64.add_counts(room_groups[peer + "/" + room + "/" + label], actor)
            for label in ("us", "peer"):
                if room_groups[peer + "/" + room + "/" + label]["starts"] != 80:
                    raise ValueError("G120 单房同桌未满 80 单局")
    if matched_old != set(old_index):
        raise ValueError("G120 既有 G64 单局没有全覆盖")
    for peer, rooms in source_rooms.items():
        if len(rooms) != current["by_peer"][PEER_NAMES[peer]]["rooms"]:
            raise ValueError("G120 强手同桌房数漂移")
        if groups[peer + "/us"]["net"] != current["by_peer"][PEER_NAMES[peer]]["our_score"]:
            raise ValueError("G120 我方净分与 G122 不一致")
        if groups[peer + "/peer"]["net"] != current["by_peer"][PEER_NAMES[peer]]["peer_score"]:
            raise ValueError("G120 强手净分与 G122 不一致")
    result = {
        "schema": "g120-current-strong-win-timing/1",
        "input_sha256": {"script": sha(Path(__file__)), "g122": sha(CURRENT),
                         "g64": sha(PRIOR)},
        "rooms": {peer: len(rooms) for peer, rooms in source_rooms.items()},
        "old_g64_round_rows_reconciled": len(matched_old),
        "groups": {key: dict(sorted(value.items())) for key, value in sorted(groups.items())},
        "room_groups": {key: dict(sorted(value.items()))
                        for key, value in sorted(room_groups.items())},
        "boundary": "同房强手为观察性对照，非同手牌随机实验；胜胡序号按本人弃牌数加一，"
                    "后段比例受先胡截尾和庄位反馈共同影响。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"rooms": result["rooms"], "groups": result["groups"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
