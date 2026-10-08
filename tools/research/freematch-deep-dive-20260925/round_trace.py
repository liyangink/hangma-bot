#!/usr/bin/env python3
"""打印指定 game_id / 单局的官方事件流轨迹（只读，用于报告中的具体例证）。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/round_trace.py <game_id> <round_no> [<game_id> <round_no> ...]

输出：座位表、起始手牌、该局全部事件（摸/弃/吃/碰/杠/结算），
以及每位座位在结算时的手上财神数与出牌次数。
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

W = "白"


def load(game_id: str):
    for path in glob.glob("artifacts/sessions/*/official/dl-*/events.json"):
        try:
            doc = json.load(open(path))
        except (OSError, ValueError):
            continue
        if doc.get("game_id") == game_id:
            return doc, path
    return None, None


def trace(game_id: str, round_no: int) -> None:
    doc, path = load(game_id)
    if doc is None:
        print("未找到", game_id)
        return
    print("=" * 78)
    print(f"game_id={game_id} room={doc.get('room_id')} file={path}")
    for i, s in enumerate(doc.get("seats") or []):
        print(f"  座位{i}  {s.get('name')}  {s.get('user_id')}")
    summary = next((r for r in doc.get("rounds") or [] if r.get("round_no") == round_no), {})
    print(f"摘要 round{round_no}: dealer={summary.get('dealer')} winner={summary.get('winner')} "
          f"fan={summary.get('multiplier')} scores={summary.get('scores')} is_draw={summary.get('is_draw')}")
    white = {i: None for i in range(4)}
    drawn = {i: 0 for i in range(4)}
    disc = {i: 0 for i in range(4)}
    for block in doc.get("blocks") or []:
        if block.get("round_no") != round_no:
            continue
        starts = block.get("start_hands") or []
        if any(isinstance(h, list) and h for h in starts):
            for i in range(4):
                if white[i] is None and isinstance(starts[i], list):
                    white[i] = sum(1 for t in starts[i] if t == W)
            print("起始手牌:", json.dumps(starts, ensure_ascii=False))
        for e in block.get("events") or []:
            t = e.get("type")
            if t in ("timeout", "pass"):
                continue
            data = e.get("data") or {}
            extra = ""
            if t == "round_ended":
                extra = "  " + json.dumps({k: data.get(k) for k in ("draw", "fan", "detail", "scores")},
                                          ensure_ascii=False)
            elif t == "chi":
                extra = "  tiles=" + str(data.get("tiles"))
            elif t == "tile_discarded":
                extra = "  catch_play=" + str(data.get("catch_play"))
            print(f"  seq{e.get('seq'):>5} {t:<14} seat{e.get('seat')} {e.get('tile') or '':<3}{extra}")
            s = e.get("seat")
            if isinstance(s, int) and 0 <= s < 4:
                if t == "tile_drawn" and e.get("tile") == W:
                    drawn[s] += 1
                if t == "tile_discarded" and e.get("tile") == W:
                    disc[s] += 1
    print("结算时手上财神（白板）数:", {i: (None if white[i] is None else white[i] + drawn[i] - disc[i])
                                        for i in range(4)})


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) % 2:
        raise SystemExit("用法: round_trace.py <game_id> <round_no> ...")
    for i in range(0, len(args), 2):
        trace(args[i], int(args[i + 1]))
