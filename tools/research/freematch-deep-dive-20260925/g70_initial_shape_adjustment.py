#!/usr/bin/env python3
"""G70：同房双方起手牌形质量探索性分层，检验 G69 入口差是否只是白板/庄位供给。"""

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
import gzip
import hashlib
import json
from pathlib import Path

from extract_room_scores import load_rooms
import g69_same_room_us_batch as g69
from hangma_bot.hangma.hand_analysis import analyse_hand
from hangma_bot.kernel.actions import Tile


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928')
ROUNDS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/route_rounds.jsonl.gz')
OUT_ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/initial_shape_rounds.jsonl.gz')
OUT_RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/initial_shape_result.json')


def initial_shape(codes: list[str], dealer: bool) -> dict:
    """庄家 14 张按最好合法弃牌归一为 13 张；其他座位直接分析 13 张。"""

    expected = 14 if dealer else 13
    if len(codes) != expected:
        raise ValueError("G70 官方起手张数与庄位不符")
    tiles = tuple(Tile(code) for code in codes)
    hands = (tuple(tile for j, tile in enumerate(tiles) if j != i)
             for i in range(len(tiles))) if dealer else (tiles,)
    summaries = [analyse_hand(hand, 0) for hand in hands]
    return {"initial_standard_best": min(item.standard_shanten for item in summaries),
            "initial_combined_best": min(item.shanten for item in summaries),
            "initial_seven_best": min(item.chiitoi_shanten for item in summaries),
            "initial_white": codes.count("白")}


def start_index(rooms: set[str], wanted_games: set[str]) -> dict[tuple, list[list[str]]]:
    """只读最早官方事件块的真正起手；后续块起手字段是续传快照。"""

    index = {}
    for _, room, _, game_id, doc in load_rooms():
        if room not in rooms or game_id not in wanted_games:
            continue
        blocks = defaultdict(list)
        for block in doc.get("blocks") or []:
            blocks[block["round_no"]].append(block)
        if len(blocks) != 8:
            raise ValueError("G70 官方桌不是八单局")
        for round_no, pieces in blocks.items():
            hands = next((piece["start_hands"] for piece in pieces
                          if isinstance(piece.get("start_hands"), list) and
                          len(piece["start_hands"]) == 4), None)
            if hands is None:
                raise ValueError("G70 官方起手缺失")
            key = (room, game_id, round_no)
            if key in index:
                raise ValueError("G70 官方单局重复")
            index[key] = hands
    return index


def main() -> None:
    if OUT_ROWS.exists() or OUT_RESULT.exists():
        raise SystemExit("G70 起手形状结果已存在，拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["release_package_id"] != json.loads((g69.G60 / "manifest.json").read_text())["release_package_id"]:
        raise ValueError("G70 冻结发布包漂移")
    rounds = [json.loads(line) for line in gzip.open(ROUNDS, "rt", encoding="utf-8")]
    rooms = set(manifest["rooms"])
    games = {row["game_id"] for row in rounds}
    index = start_index(rooms, games)
    if len(index) != 31 * 10 * 8 or len(rounds) != 5120:
        raise ValueError("G70 同房官方起手或双方单局缺失")
    enriched = []
    distribution: dict[str, Counter] = defaultdict(Counter)
    for row in rounds:
        codes = index[row["room"], row["game_id"], row["round_no"]][row["seat"]]
        features = initial_shape(codes, row["dealer"])
        if features["initial_white"] != row["start_white"]:
            raise ValueError("G70 起手白板与 G64 已验终局分层不一致")
        enriched_row = {**row, **features}
        enriched.append(enriched_row)
        dist = distribution[row["peer"] + "/" + row["actor"]]
        dist["starts"] += 1
        for field in ("initial_standard_best", "initial_combined_best", "initial_seven_best"):
            dist[field + "_" + str(features[field])] += 1
    result = {"schema": "g70-initial-shape-adjustment/1", "exploratory": True,
              "source_sha256": {"g69_rounds": hashlib.sha256(ROUNDS.read_bytes()).hexdigest(),
                                "g69_manifest": hashlib.sha256((_project_file(_PROJECT_ROOT, SOURCE / "manifest.json")).read_bytes()).hexdigest(),
                                "script": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "rows": len(enriched),
              "distribution": {key: dict(sorted(value.items())) for key, value in sorted(distribution.items())},
              "boundary": "起手本人可见手牌的生产牌形数学；庄家按起手14张最好弃牌归一；不同起手牌仍非策略因果对照。"}
    with gzip.open(OUT_ROWS, "wt", encoding="utf-8") as stream:
        for row in enriched:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    OUT_RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
