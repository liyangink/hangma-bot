#!/usr/bin/env python3
"""第 2 步：全量重建，产出 rounds.jsonl（每局一条，含四家事实）与 selfcheck.json。

用法：
    .venv/bin/python step2_reconstruct.py [--limit N] [--workers K] [--out NAME]
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
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anatomy_lib as lib  # noqa: E402


def dump_wait(item):
    """等待态压缩成定长数组，降低中间产物体积。"""

    return [item["kind"], item["turn"], item["baotou"], item["whites"],
            item["shanten"], item["standard_shanten"], item["chiitoi_shanten"],
            item["useful_n"], item["seq"], item["draws_so_far"], item["discards_so_far"]]


def process_game(game):
    rows = []
    checks = Counter()
    mismatches = []
    doc = game["doc"]
    room_id = doc.get("room_id")
    for round_no, events, start_hands in lib.round_blocks(doc):
        facts = lib.round_facts(doc, round_no, events, start_hands)
        if "fatal" in facts:
            checks["fatal_rounds"] += 1
            continue
        checks["rounds"] += 1
        checks["recon_errors"] += len(facts["hand_reconstruction_errors"])
        if facts["dealer_agree"] is False:
            checks["dealer_disagree"] += 1
        if facts["dealer_agree"] is True:
            checks["dealer_agree"] += 1
        status = facts["fan_check"]["status"]
        checks["fan_" + status] += 1
        if status == "ok":
            if facts["fan_check"].get("detail_match"):
                checks["fan_detail_match"] += 1
            else:
                checks["fan_detail_diff"] += 1
        if status == "fan_mismatch":
            checks["fan_mismatch_rows"] += 0
            mismatches.append({
                "game_id": game["game_id"], "round_no": round_no,
                "official": facts["fan_check"]["official_fan"],
                "recomputed": facts["fan_check"]["recomputed_fan"],
                "official_detail": facts["fan_check"]["official_details"],
                "recomputed_detail": facts["fan_check"]["recomputed_details"],
                "branch": facts["fan_check"]["branch"],
                "chain": facts["fan_check"]["chain"], "piao": facts["fan_check"]["piao"],
            })
        if facts["chain_unknown"]:
            checks["chain_unknown_rounds"] += 1
        winner = facts["winner_seat"]
        seats_out = []
        for seat_facts in facts["per_seat"]:
            item = dict(seat_facts)
            item["waits"] = [dump_wait(w) for w in seat_facts["waits"]]
            seats_out.append(item)
        rows.append({
            "game_id": game["game_id"],
            "room_id": room_id,
            "session": game.get("session"),
            "round_no": round_no,
            "winner_seat": winner,
            "is_draw": facts["is_draw"],
            "fan": facts["fan"],
            "detail": facts["detail"],
            "scores": facts["scores"],
            "dealer": facts["dealer"],
            "seats": seats_out,
            "my_discard_windows": [
                {"seq": w["seq"], "turn": w["turn"], "hand": [t.code for t in w["hand_before"]],
                 "melds": w["meld_count"], "chosen": w["chosen"], "whites": w["whites_held"]}
                for w in facts["discard_windows"] if w["seat"] == next(
                    (s["seat"] for s in facts["per_seat"] if s["is_me"]), -1)
            ],
            "error_msgs": facts["hand_reconstruction_errors"][:4],
        })
    return rows, checks, game["game_id"], mismatches


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", default="rounds.jsonl")
    parser.add_argument("--only-me", action="store_true", default=True)
    args = parser.parse_args(argv)

    out_dir = Path(__file__).resolve().parent
    started = time.time()
    games = lib.load_games()
    if args.only_me:
        games = [g for g in games if lib.ME in [s.get("user_id") for s in g["doc"].get("seats") or []]]
    if args.limit:
        games = games[: args.limit]
    print("待处理唯一牌谱 %d（含我方）" % len(games))

    checks = Counter()
    written = 0
    errors = Counter()
    fan_mismatches = []
    with open(out_dir / args.out, "w", encoding="utf-8") as handle:
        if args.workers > 1:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=min(4, args.workers)) as pool:
                for rows, sub_checks, game_id, sub_mismatch in pool.map(process_game, games, chunksize=4):
                    checks.update(sub_checks)
                    fan_mismatches.extend(sub_mismatch)
                    for row in rows:
                        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                        written += 1
                        for msg in row["error_msgs"]:
                            errors[msg.split(" ")[0]] += 1
        else:
            for game in games:
                rows, sub_checks, game_id, sub_mismatch = process_game(game)
                checks.update(sub_checks)
                fan_mismatches.extend(sub_mismatch)
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                    written += 1
                    for msg in row["error_msgs"]:
                        errors[msg.split(" ")[0]] += 1

    summary = {
        "unique_games": len(games),
        "rounds_written": written,
        "checks": dict(checks),
        "error_kinds": dict(errors),
        "seconds": round(time.time() - started, 1),
        "out": str(out_dir / args.out),
    }
    (out_dir / "fan_mismatches.json").write_text(
        json.dumps(fan_mismatches[:200], ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "selfcheck.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
