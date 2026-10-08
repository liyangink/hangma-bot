#!/usr/bin/env python3
"""G71：核对入口差与本人鸣牌、终胡摸牌的关系，仅作赛后机制排查。"""

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


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/initial_shape_rounds.jsonl.gz')
OUT_ROWS = SOURCE.with_name("claim_terminal_rounds.jsonl.gz")
OUT_RESULT = SOURCE.with_name("claim_terminal_result.json")


def official_index(rooms: set[str], games: set[str]) -> dict[tuple, dict]:
    """官方事件用于赛后声明；他家暗手和未来摸牌不进入动作事实。"""

    index = {}
    for _, room, _, game_id, doc in load_rooms():
        if room not in rooms or game_id not in games:
            continue
        blocks = defaultdict(list)
        for block in doc.get("blocks") or []:
            blocks[block["round_no"]].extend(block.get("events") or [])
        if len(blocks) != 8:
            raise ValueError("G71 官方完整桌缺八单局")
        for round_no, events in blocks.items():
            end = [e for e in events if e.get("type") == "round_ended"]
            if len(end) != 1:
                raise ValueError("G71 官方单局终局不唯一")
            key = (room, game_id, round_no)
            if key in index:
                raise ValueError("G71 官方单局重复")
            index[key] = {"events": events, "winner": None if end[0]["data"].get("draw") else end[0]["seat"]}
    return index


def main() -> None:
    if OUT_ROWS.exists() or OUT_RESULT.exists():
        raise SystemExit("G71 赛后诊断结果已存在，拒绝覆盖")
    rows = [json.loads(line) for line in gzip.open(SOURCE, "rt", encoding="utf-8")]
    if len(rows) != 5120:
        raise ValueError("G71 G69/G70 双方单局不完整")
    official = official_index({row["room"] for row in rows}, {row["game_id"] for row in rows})
    if len(official) != 31 * 10 * 8:
        raise ValueError("G71 官方事件对账不完整")
    enriched = []
    groups: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        case = official[row["room"], row["game_id"], row["round_no"]]
        seat = row["seat"]
        own = [event for event in case["events"] if event.get("seat") == seat]
        claims = Counter(event["type"] for event in own if event["type"] in ("chi", "peng", "gang"))
        draws = [event for event in own if event["type"] == "tile_drawn"]
        if row["status"] == "win" and case["winner"] != seat:
            raise ValueError("G71 官方获胜身份与 G64 不同")
        terminal = draws[-1]["tile"] if row["status"] == "win" and draws else None
        if row["status"] == "win" and terminal is None:
            raise ValueError("G71 本人自摸胡缺终胡前摸牌")
        addition = {"own_chi": claims["chi"], "own_peng": claims["peng"],
                    "own_gang": claims["gang"], "own_claims": sum(claims.values()),
                    "own_white_draws": sum(event.get("tile") == "白" for event in draws),
                    "winning_draw_tile": terminal}
        enriched.append({**row, **addition})
        c = groups[row["peer"] + "/" + row["actor"]]
        c["starts"] += 1
        c["claims"] += addition["own_claims"]
        c["claim_rounds"] += addition["own_claims"] > 0
        c["no_claim_rounds"] += addition["own_claims"] == 0
        c["no_claim_ready"] += addition["own_claims"] == 0 and row["first_any_ready"] is not None
        c["no_claim_high_ready"] += addition["own_claims"] == 0 and row["first_high_ready"] is not None
        high_win = row["status"] == "win" and row["fan"] >= 2
        prior_high = row["first_high_ready"] is not None
        c["high_wins"] += high_win
        c["high_win_no_prior_high"] += high_win and not prior_high
        c["high_win_no_prior_high_on_white"] += high_win and not prior_high and terminal == "白"
        c["high_win_no_prior_high_on_nonwhite"] += high_win and not prior_high and terminal != "白"
        c["high_win_with_prior_high"] += high_win and prior_high
        c["win_on_white"] += row["status"] == "win" and terminal == "白"
    result = {"schema": "g71-claim-terminal-diagnostics/1", "exploratory": True,
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "rows": len(enriched),
              "groups": {key: dict(sorted(value.items())) for key, value in sorted(groups.items())},
              "boundary": "本人鸣牌/终胡摸牌是赛后事实；无鸣牌切片和终胡牌切片都受策略与运气影响，不是动作前因果分层。"}
    with gzip.open(OUT_ROWS, "wt", encoding="utf-8") as stream:
        for row in enriched:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    OUT_RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["groups"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
