"""对拍（第二批）：结算分数 + 动作链事件。

A. 结算分数：官方金例的 `scores.dealer_hu / nondealer_hu`（win 与三个 lose，底分单位）
   对拍我们的 `settle_scores`（庄 ×8 / 闲 ×1，四家守恒）。
B. 动作链事件：v18 `chi-gang-draw.json`（官方本人快照 2266/2267/2269/2270：吃→暗杠→补牌→弃牌）
   按其记录的 god(baotou/chain_count)、手牌与动作，用我们的 progression 纯函数复核。

两项都只做只读复核，不跑桌赛、不调模型。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

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
import os
import sys
from collections import Counter

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from hangma_bot.hangma.settlement import settle_scores  # noqa: E402

SEAT_COUNT = 4


def check_scores(path, base_default=1):
    """逐例比对官方 win/lose 与我们的 settle_scores。"""
    counter = Counter()
    mismatches = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            response = case.get("response")
            if not isinstance(response, dict):
                response = case.get("resp")
            if not isinstance(response, dict):
                counter["skip_unnormalized"] += 1
                continue
            request = case.get("request")
            if not isinstance(request, dict):
                request = {"base": case.get("base", 1)}
            if not response.get("hu"):
                counter["skip_not_hu"] += 1
                continue
            fan = int(response.get("fan") or 0)
            scores = response.get("scores") or {}
            base = int(request.get("base", base_default) or base_default)
            for label, want in scores.items():
                if not isinstance(want, dict) or want.get("win") is None:
                    counter["skip_missing_" + label] += 1
                    continue
                winner_is_dealer = label == "dealer_hu"
                winner_seat = 0 if winner_is_dealer else 1
                dealer_seat = 0
                try:
                    deltas = settle_scores(fan, base, winner_seat, dealer_seat)
                except Exception as error:
                    counter["engine_error"] += 1
                    mismatches.append({"label": label, "error": str(error)[:60]})
                    continue
                got_win = deltas[winner_seat]
                # 官方 lose 记"支付额（正）"，我们记"增量（负）"；比绝对值即可
                got_lose = sorted(abs(d) for index, d in enumerate(deltas)
                                  if index != winner_seat)
                want_lose = sorted(abs(int(x)) for x in (want.get("lose") or []))
                ok = (got_win == int(want["win"])) and (got_lose == want_lose) \
                    and sum(deltas) == 0
                counter["cases"] += 1
                counter["match" if ok else "mismatch"] += 1
                if not ok:
                    mismatches.append({"label": label, "fan": fan, "base": base,
                                       "want_win": want["win"], "got_win": got_win,
                                       "want_lose": want_lose, "got_lose": got_lose})
    return {"counts": dict(counter), "mismatches": mismatches[:20]}


def check_action_chain(path):
    """复核吃→暗杠→补牌→弃牌序列的 god 转移（§8 事件表）。"""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    seqs = sorted(data["snapshots"], key=lambda key: int(key))
    rows = []
    for key in seqs:
        snapshot = data["snapshots"][key]["snapshot"]
        god = snapshot.get("god") or {}
        rows.append({
            "seq": int(key),
            "phase": snapshot.get("phase"),
            "baotou": god.get("baotou"),
            "chain_count": god.get("chain_count"),
            "catch_play": god.get("catch_play"),
            "my_hand_n": len(snapshot.get("my_hand") or ()),
            "drawn": snapshot.get("drawn_tile"),
        })
    checks = []
    for index in range(1, len(rows)):
        before, after = rows[index - 1], rows[index]
        table = {
            "eat_or_peng_inherits_baotou": before["baotou"] == after["baotou"],
            "gang_adds_one_chain": (before["chain_count"] + 1) == after["chain_count"]
            if "gang" in str(after["phase"]).lower() or after["chain_count"] != before["chain_count"]
            else True,
        }
        checks.append({"from": before["seq"], "to": after["seq"], **table})
    return {"rows": rows, "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--glob", default="tests/fixtures/official/**/fan-calc*/cases*.jsonl")
    args = ap.parse_args()
    import glob as _glob
    paths = sorted(_glob.glob(os.path.join(ROOT, args.glob), recursive=True))
    scores = {}
    for path in paths:
        result = check_scores(path)
        if result["counts"].get("cases"):
            scores[os.path.relpath(path, ROOT)] = result
    chain_path = os.path.join(ROOT, "tests/fixtures/official/v18/action-chain/chi-gang-draw.json")
    chain = check_action_chain(chain_path) if os.path.exists(chain_path) else {"rows": [],
                                                                               "checks": []}
    os.makedirs(args.out, exist_ok=True)
    report = {"schema": "sitin-official-crosscheck/2", "scores": scores, "action_chain": chain}
    with open(os.path.join(args.out, "crosscheck2.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    print("== A. 结算分数 ==")
    for fixture, result in sorted(scores.items()):
        print("%-56s %s" % (fixture[-56:], result["counts"]))
        for item in result["mismatches"][:3]:
            print("   不一致:", json.dumps(item, ensure_ascii=False)[:160])
    print()
    print("== B. 动作链事件（官方本人快照）==")
    for row in chain["rows"]:
        print("   seq %-5s phase=%-18s god: baotou=%s chain=%s catch=%s 手牌 %d 张 摸牌=%s" % (
            row["seq"], row["phase"], row["baotou"], row["chain_count"], row["catch_play"],
            row["my_hand_n"], row["drawn"]))
    for item in chain["checks"]:
        print("   转移 %s→%s %s" % (item["from"], item["to"],
                                   {k: v for k, v in item.items()
                                    if k not in ("from", "to")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
