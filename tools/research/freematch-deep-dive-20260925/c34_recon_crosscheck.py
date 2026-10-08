#!/usr/bin/env python3
"""C34 附带自检：两条独立重建在**全部弃牌窗**上逐位对拍（预登记 §9.1）。

* A 侧 = review/baotou-anatomy-20260925/anatomy_lib.reconstruct_round
* B 侧 = review/freematch-deep-dive-20260925/c23_claim_opportunity.scan_round
对拍项：每个弃牌窗的 (seq, seat, 弃前暗牌牌码多重集, 弃前副露数, 所打牌)，
以及终局暗牌与副露数。两者历史上都被 C23 §9.2 用于等价性自检，本脚本把它跑成全量。

用法：
    PYTHONPATH=$PWD/src .venv/bin/python review/freematch-deep-dive-20260925/c34_recon_crosscheck.py
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

import collections
import json
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))

import anatomy_lib as AL  # noqa: E402
import c23_claim_opportunity as C23  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c34-followup")


def main():
    started = time.time()
    games = AL.load_games()
    stats = collections.Counter()
    details = []
    for game in games:
        for round_no, events, start_hands in AL.round_blocks(game["doc"]):
            if not start_hands:
                continue
            stats["rounds"] += 1
            recon = AL.reconstruct_round(events, start_hands)
            summary, _audit, _verbose = C23.scan_round(events, start_hands)
            if recon["errors"]:
                stats["recon_errors"] += len(recon["errors"])
            for seat in range(4):
                mine = {code: count for code, count in recon["hands_end"][seat].items() if count}
                theirs = {code: count for code, count in summary["hands_end"][seat].items()
                          if count}
                if mine != theirs:
                    stats["hands_end_mismatch"] += 1
                    if len(details) < 5:
                        details.append(["hands", game["game_id"], round_no, seat])
            if list(recon["melds_end"]) != list(summary["melds_end"]):
                stats["melds_end_mismatch"] += 1
                if len(details) < 5:
                    details.append(["melds", game["game_id"], round_no])
            left = [(item["seq"], item["seat"],
                     tuple(sorted(tile.code for tile in item["hand_before"])),
                     item["meld_count"], item["chosen"])
                    for item in recon["discard_windows"]]
            right = [(item[0], item[1], item[2], item[3], item[4])
                     for item in summary["windows"]]
            stats["windows"] += len(left)
            if left != right:
                stats["windows_mismatch"] += 1
                if len(details) < 5:
                    details.append(["windows", game["game_id"], round_no, len(left), len(right)])
    payload = {"experiment": "C34-RECON-CROSSCHECK", "games": len(games),
               "stats": dict(sorted(stats.items())), "details": details,
               "seconds": round(time.time() - started, 1)}
    OUT.mkdir(parents=True, exist_ok=True)
    (_project_file(_PROJECT_ROOT, OUT / "recon-crosscheck.json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
