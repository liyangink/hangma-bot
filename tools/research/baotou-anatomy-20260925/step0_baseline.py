#!/usr/bin/env python3
"""第 0 步：基线盘面（与重建同一份去重牌谱），供报告直接引用。

用法：.venv/bin/python step0_baseline.py [--out baseline.json]
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

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import anatomy_lib as lib  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="baseline.json")
    args = parser.parse_args(argv)

    games = [g for g in lib.load_games()
             if lib.ME in [s.get("user_id") for s in g["doc"].get("seats") or []]]
    rooms = {g["doc"].get("room_id") for g in games}
    me_wins = me_baotou = opp_wins = opp_baotou = draws = 0
    rounds = 0
    me_fan = []
    opp_fan = []
    me_points = []
    opp_points = []
    uca_off_rounds = 0
    uca_off_games = set()
    me_selfdraw = 0
    for game in games:
        doc = game["doc"]
        seats = [s.get("user_id") for s in doc.get("seats") or []]
        me = seats.index(lib.ME)
        for round_no, events, start_hands in lib.round_blocks(doc):
            ended = next((e for e in events if e["type"] == "round_ended"), None)
            if ended is None:
                continue
            rounds += 1
            row = lib.round_facts(doc, round_no, events, start_hands)
            if "fatal" in row:
                continue
            data = ended.get("data") or {}
            winner = ended.get("seat")
            if not (type(winner) is int and 0 <= winner < 4):
                draws += 1
                continue
            detail = data.get("detail") or []
            baotou = any("爆头" in str(x) for x in detail)
            # 有财必拷响开关的数据推断：若出现「非爆头胡 且 胡牌暗牌里有财神」，
            # 则该牌谱的 you_cai_bi_kao 必为 False（开关为 True 时
            # special_rules.you_cai_bi_kao_block 会拦掉这种胡）。
            facts = None
            for item in row["per_seat"]:
                if item["seat"] == winner:
                    facts = item
            if facts is not None and not baotou and facts["whites_end"] >= 1:
                uca_off_rounds += 1
                uca_off_games.add(game["game_id"])
            scores = data.get("scores") or []
            points = scores[winner] if winner < len(scores) else None
            if winner == me:
                me_wins += 1
                me_baotou += baotou
                me_fan.append(data.get("fan"))
                if points is not None:
                    me_points.append(points)
            else:
                opp_wins += 1
                opp_baotou += baotou
                opp_fan.append(data.get("fan"))
                if points is not None:
                    opp_points.append(points)

    def fmean(values):
        values = [v for v in values if isinstance(v, int)]
        return sum(values) / len(values) if values else float("nan")

    payload = {
        "unique_games": len(games), "rooms": len(rooms), "rounds": rounds,
        "me_wins": me_wins, "me_baotou": me_baotou,
        "opp_wins": opp_wins, "opp_baotou": opp_baotou, "draws": draws,
        "me_baotou_share": me_baotou / max(1, me_wins),
        "opp_baotou_share": opp_baotou / max(1, opp_wins),
        "me_fan": fmean(me_fan), "opp_fan": fmean(opp_fan),
        "me_points_per_win": fmean(me_points), "opp_points_per_win": fmean(opp_points),
        "me_points_per_round": sum(me_points) / max(1, rounds),
        "opp_points_per_round": sum(opp_points) / max(1, 3 * rounds),
        "uca_off_evidence_rounds": uca_off_rounds,
        "uca_off_evidence_games": len(uca_off_games),
        "me_win_share": me_wins / max(1, rounds),
        "opp_win_share": opp_wins / max(1, 3 * rounds),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    (_project_file(_PROJECT_ROOT, HERE / args.out)).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
