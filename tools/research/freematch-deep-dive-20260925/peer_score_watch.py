#!/usr/bin/env python3
"""用已归档的官方场次复算我方与指定周榜强手的同桌积分。

按 ``game_id`` 去重，按用户 ID 而非座位汇总；逐房读取发布包身份。
只处理含完整八个 ``round_ended`` 的官方场次，不联网、不开房。
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

import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "freematch-deep-dive-20260925")))

from extract_room_scores import load_rooms  # noqa: E402

US = "u_13495c3d79c8"
PEERS = {
    "玄武-2346": "u_380da525337c",
    "Astra-0": "u_a24596248186",
    "腾蛇-0638": "u_b2aa6abe7811",
}


def manifest_identity() -> dict[str, tuple[str, str]]:
    """返回房号到（策略版本、冻结包 ID），冲突身份直接报错。"""

    identities = defaultdict(set)
    for path in glob.glob(str(_project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/*/audit/runs/*/manifest.json"))):
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        room = (doc.get("context") or {}).get("tournament_id")
        payload = doc.get("payload") or {}
        version = payload.get("policy_version")
        package = (payload.get("policy_release") or {}).get("release_package_id")
        if room and version and package:
            identities[room].add((version, package))
    ambiguous = {room: sorted(ids) for room, ids in identities.items() if len(ids) != 1}
    if ambiguous:
        raise ValueError(f"房间发布身份冲突：{ambiguous}")
    return {room: next(iter(ids)) for room, ids in identities.items()}


def main() -> None:
    identities = manifest_identity()
    by_peer = defaultdict(lambda: defaultdict(Counter))
    observed_games = defaultdict(set)
    for _mtime, room, _tag, game_id, doc in load_rooms():
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if len(seats) != 4 or US not in seats:
            continue
        interested = [(name, uid) for name, uid in PEERS.items() if uid in seats]
        if not interested:
            continue
        if room not in identities:
            raise ValueError(f"同桌房缺发布身份：{room}")
        blocks = doc.get("blocks") or []
        terminal = [event for block in blocks for event in block.get("events") or []
                    if event.get("type") == "round_ended"]
        if len(terminal) != 8:
            raise ValueError(f"官方场次非八个完整单局：{game_id}，实际 {len(terminal)}")
        official = doc.get("rounds") or []
        scores = [sum(record["scores"][seat] for record in official) for seat in range(4)]
        # 官方 rounds[] 可能省略零分流局；逐终局事件对账能排除非零遗漏。
        event_scores = [sum(event["data"]["scores"][seat] for event in terminal)
                        for seat in range(4)]
        if scores != event_scores:
            raise ValueError(f"官方摘要与终局积分不一致：{game_id}")
        for name, uid in interested:
            if game_id in observed_games[name]:
                raise ValueError(f"同一对手的官方场次重复：{game_id}")
            observed_games[name].add(game_id)
            row = by_peer[name][room]
            mine, peer = scores[seats.index(US)], scores[seats.index(uid)]
            row["games"] += 1
            row["us_score"] += mine
            row["peer_score"] += peer
            row["us_ahead_games"] += mine > peer
            row["tied_games"] += mine == peer

    result = {}
    for name, rooms in sorted(by_peer.items()):
        grouped = defaultdict(Counter)
        detail = {}
        for room, counts in sorted(rooms.items()):
            if counts["games"] != 10:
                raise ValueError(f"同桌房非十个完整场次：{room}")
            version, package = identities[room]
            row = dict(counts)
            row["peer_minus_us"] = counts["peer_score"] - counts["us_score"]
            row["policy_version"] = version
            row["release_package_id"] = package
            detail[room] = row
            cohort = grouped[version]
            cohort["rooms"] += 1
            cohort.update(counts)
        result[name] = {
            "user_id": PEERS[name],
            "rooms": detail,
            "cohorts": {
                version: {**dict(counts),
                          "peer_minus_us": counts["peer_score"] - counts["us_score"]}
                for version, counts in sorted(grouped.items())
            },
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
