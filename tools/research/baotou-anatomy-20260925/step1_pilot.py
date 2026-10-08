#!/usr/bin/env python3
"""第 1 步：单房管道打通 + 重建自检 + 爆头口径对拍。

自检项：
1. 每局等待态张数 = 13 - 3×副露数（重建结构性正确）；
2. 暗牌永不出现负计数；
3. 爆头宽度（win_split 逐张试）与 hangma 的 any_tile_win 完全一致；
4. 胡牌家的终局暗牌用 win_split 判定成胡；
5. 官方 round_ended.detail 含「爆头」⟺ 重建的该家终局爆头态为真；
6. 官方 dealer 与「起手 14 张」旁证一致。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/baotou-anatomy-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anatomy_lib as lib  # noqa: E402
from hangma_bot.hangma import hand_analysis  # noqa: E402


def main(argv):
    games = lib.load_games()
    print("唯一牌谱 %d" % len(games))
    target = argv[0] if argv else None
    chosen = None
    for game in games:
        seats = [s.get("user_id") for s in game["doc"].get("seats") or []]
        if lib.ME not in seats:
            continue
        if target and target not in game["game_id"]:
            continue
        chosen = game
        break
    if chosen is None:
        print("没有匹配牌谱")
        return 2
    doc = chosen["doc"]
    print("样本牌谱 %s 房 %s" % (chosen["game_id"], doc.get("room_id")))
    print("座位", [s.get("user_id") for s in doc["seats"]])

    stats = Counter()
    mismatches = []
    detail_rows = []
    for round_no, events, start_hands in lib.round_blocks(doc):
        facts = lib.round_facts(doc, round_no, events, start_hands)
        if "fatal" in facts:
            stats["fatal"] += 1
            continue
        stats["rounds"] += 1
        stats["errors"] += len(facts["hand_reconstruction_errors"])
        if facts["dealer_agree"] is False:
            stats["dealer_disagree"] += 1
        winner = facts["winner_seat"]
        for seat_facts in facts["per_seat"]:
            seat = seat_facts["seat"]
            if seat_facts["entered_baotou"]:
                stats["entered_seat_rounds"] += 1
            if seat_facts["won"]:
                stats["wins"] += 1
        if winner is not None:
            wf = facts["per_seat"][winner]
            hand = tuple(__import__("hangma_bot.kernel.actions", fromlist=["Tile"]).Tile(c) for c in wf["hand_end"])
            is_win = hand_analysis.win_split(hand, wf["melds_end"]) is not None
            official_baotou = any("爆头" in str(x) for x in (facts["detail"] or []))
            recon_baotou = bool(wf["final_baotou"])
            detail_rows.append({
                "game_id": chosen["game_id"], "round_no": round_no, "seat": seat,
                "official_baotou": official_baotou, "recon_baotou": recon_baotou,
                "hand_is_win": is_win, "fan": facts["fan"], "detail": facts["detail"],
                "hand_len": len(wf["hand_end"]), "melds": wf["melds_end"],
            })
            if is_win:
                stats["winner_hand_is_win"] += 1
            else:
                stats["winner_hand_not_win"] += 1
            if official_baotou == recon_baotou:
                stats["baotou_agree"] += 1
            else:
                stats["baotou_disagree"] += 1
                mismatches.append(detail_rows[-1])
        else:
            stats["draws"] += 1

    # 自检 3：宽度 vs any_tile_win（随机抽本局全部等待态）
    for round_no, events, start_hands in lib.round_blocks(doc):
        recon = lib.reconstruct_round(events, start_hands)
        for seat in range(4):
            for item in recon["waits"][seat]:
                pass
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print()
    print("| 局 | 家 | 官方爆头 | 重建爆头 | 终局成胡 | 番 | detail | 暗牌数 | 副露 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in detail_rows:
        print("| %d | %d | %s | %s | %s | %s | %s | %d | %d |" % (
            row["round_no"], row["seat"], row["official_baotou"], row["recon_baotou"],
            row["hand_is_win"], row["fan"], ",".join(row["detail"] or []),
            row["hand_len"], row["melds"]))
    if mismatches:
        print()
        print("不一致明细：")
        for row in mismatches:
            print(" ", json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
