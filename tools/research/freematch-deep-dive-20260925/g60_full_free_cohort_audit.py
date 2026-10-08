#!/usr/bin/env python3
"""同一冻结发布包的全部已归档完整自由赛房，复算白板与胡牌收支。"""

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
from peer_score_watch import manifest_identity


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927')
POLICY = "r18_integrated_positive_v2"
PACKAGE = "e82f904c2c1fb70beea3f195110c8b2db0648971ed3eaa9bfcbed1b6543de486"


def sha(path: Path) -> str:
    """记录本地代码与冻结清单摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, payload: dict) -> None:
    """清单必须在统计结果前落盘；已有内容只能逐字对账。"""

    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != body:
            raise ValueError(f"冻结证据漂移：{path}")
        return
    path.write_text(body, encoding="utf-8")


def main() -> None:
    """仅纳入同一发布包、十张官方桌及每桌八局完整终局的自由赛房。"""

    identities = manifest_identity()
    target_rooms = {room for room, identity in identities.items()
                    if identity == (POLICY, PACKAGE)}
    by_room = defaultdict(list)
    for _mtime, room, _tag, gid, doc in load_rooms():
        if room in target_rooms:
            by_room[room].append((gid, doc))
    included = {room: games for room, games in by_room.items()
                if len(games) == 10 and len({gid for gid, _ in games}) == 10}
    excluded = {room: len(by_room.get(room, [])) for room in target_rooms
                if room not in included}
    manifest = {
        "schema": "g60-full-r18v2-free-manifest/1",
        "policy_version": POLICY,
        "release_package_id": PACKAGE,
        "source": "本地官方 events.json，经 extract_room_scores.load_rooms 按 game_id 去重；逐房 audit manifest 确认发布包。",
        "identity_rooms": len(target_rooms),
        "complete_rooms": len(included),
        "complete_games": sum(map(len, included.values())),
        "included": {room: sorted(gid for gid, _ in games)
                     for room, games in sorted(included.items())},
        "excluded_room_game_counts": dict(sorted(excluded.items())),
        "inputs_sha256": {path.name: sha(path) for path in (
            _project_file(_PROJECT_ROOT, HERE / "g59_freematch_white_value_audit.py"),
            _project_file(_PROJECT_ROOT, HERE / "g60_full_free_cohort_audit.py"),
            _project_file(_PROJECT_ROOT, HERE / "extract_room_scores.py"),
            _project_file(_PROJECT_ROOT, HERE / "peer_score_watch.py"))},
    }
    if len(included) != 188 or manifest["complete_games"] != 1880:
        raise ValueError("G60 当前归档完整房数偏离预期，先核来源")
    write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    rooms = set(included)
    ids = {gid for games in included.values() for gid, _ in games}
    groups: dict[str, Counter] = defaultdict(Counter)
    room_rows: dict[str, Counter] = defaultdict(Counter)
    trace = Counter()
    for room, games in sorted(included.items()):
        for gid, doc in sorted(games):
            if not g59.audit_game(doc, ids, rooms, groups, room_rows, trace):
                raise ValueError(f"冻结官方场次未纳入：{gid}")
    if trace["games"] != 1880 or trace["hands"] != 1880 * 8:
        raise ValueError("G60 全部完整桌／单局没有核齐")
    result = {
        "schema": "g60-full-r18v2-free-cohort/1",
        "manifest_sha256": sha(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "script_sha256": sha(Path(__file__)),
        "boundary": "同一发布包全部已归档完整自由赛房；白板后摸与庄位受赛程/既有行动影响，仅描述，不是同墙候选因果比较。强手同桌的主要聚类单位为房。",
        "rooms": len(included),
        "trace": dict(sorted(trace.items())),
        "groups": {key: dict(sorted(row.items())) for key, row in sorted(groups.items())},
        "room_rows": {key: dict(sorted(row.items())) for key, row in sorted(room_rows.items())},
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"rooms": result["rooms"], "trace": result["trace"],
                      "us": result["groups"]["us/all/all"],
                      "other": result["groups"]["other/all/all"],
                      "excluded": excluded}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
