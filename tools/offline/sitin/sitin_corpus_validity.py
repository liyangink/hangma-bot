"""A- 语料级效度检验：把机会窗口按「是否保住机会」分组，比该局真实结果。

数据：canonical 面板 decisions.jsonl（判据）+ 同目录 hands.jsonl（真实结果）。
判据（规则确定，不猜）：爆头窗/链窗下，策略选的动作**是否保住状态**——
  - 选胡：收胡（状态让位给胜利）；
  - 过：状态不变 ⇒ 保住；
  - 杠：链 +1、爆头继承 ⇒ 保住；
  - 弃牌：按弃后暗牌重算（爆头）与断链规则（链）判定。
结果：该局本人 score_delta 与是否胡（winner_seat == seat）。

**已知混淆（必须与结论一起读）**：窗口类型在两组间不均衡（响应窗多为"过"），
而且单局结果由牌运主导。因此这只是弱证据；干净的做法是配对反事实（强制动作后重放同一局）。
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
import glob
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from hangma_bot.bootstrap import build_decision_codec  # noqa: E402
from hangma_bot.hangma.progression import recompute_baotou  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

WHITE = "白"
DECODE = build_decision_codec()["decode_request"]


def hand_outcomes(hands_path):
    """round 键 → {seat: score_delta}，以及是否本人胡。"""
    table = {}
    with open(hands_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except Exception:
                continue
            key = (row["game_key"]["game_id"], int(row["round_no"]))
            delta = row.get("score_delta")
            winner = row.get("winner_seat")
            table[key] = {"delta": delta, "winner": winner, "draw": row.get("is_draw")}
    return table


def verdict_of(obs, chosen_kind, chosen_key):
    """保住/未保住：按规则确定性判定。"""
    baotou = bool(getattr(obs.rule_state, "baotou", False))
    chain = int(getattr(obs.rule_state, "chain_count", 0) or 0)
    if not baotou and chain == 0:
        return None
    if chosen_kind == "hu":
        return "traded_for_win"
    if chosen_kind == "pass":
        return "kept"
    if chosen_kind == "gang":
        return "kept"
    if chosen_kind != "discard":
        return "kept"
    code = str(chosen_key).split(":", 1)[-1]
    hand = [str(getattr(t, "code", t)) for t in (obs.my_hand or ())]
    drawn = getattr(obs, "drawn_tile", None)
    if drawn is not None:
        hand.append(str(getattr(drawn, "code", drawn)))
    if code in hand:
        hand.remove(code)
    melds = getattr(obs, "melds", ()) or ()
    seat = int(getattr(obs, "seat", 0))
    own = len(melds[seat]) if 0 <= seat < len(melds) else 0
    if baotou:
        whites = sum(1 for c in hand if c == WHITE)
        try:
            kept = bool(recompute_baotou(tuple(Tile(c) for c in hand), own, whites))
        except Exception:
            return None
        return "kept" if kept else "not_kept"
    return "not_kept"  # 链：弃非飘非杠 ⇒ 断链


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--max-files", type=int, default=25)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        files = [entry["path"] for entry in json.load(fh).get("files", ())]
    files = sorted(files)[: args.max_files]

    groups = defaultdict(lambda: {"n": 0, "delta_sum": 0.0, "win": 0, "delta": []})
    seen_hands = Counter()
    for path in files:
        hands_path = os.path.join(os.path.dirname(path), "hands.jsonl")
        outcomes = hand_outcomes(hands_path) if os.path.exists(hands_path) else {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    request = row["request"]
                    obs = DECODE(request).observation
                except Exception:
                    continue
                plan = row.get("returned_plan") or {}
                candidates = plan.get("candidates") or []
                if not candidates:
                    continue
                top = min(candidates, key=lambda c: c.get("rank", 99))
                kind = str((top.get("action") or {}).get("kind", ""))
                verdict = verdict_of(obs, kind, top.get("action_key", ""))
                if verdict is None:
                    continue
                wk = request["window_key"]
                outcome = outcomes.get((wk["game_id"], int(wk["round_no"])))
                if outcome is None or not isinstance(outcome["delta"], list):
                    continue
                seat = int(obs.seat)
                delta = outcome["delta"][seat]
                bucket = groups[verdict]
                bucket["n"] += 1
                bucket["delta_sum"] += delta
                bucket["delta"].append(delta)
                if outcome["winner"] == seat:
                    bucket["win"] += 1
                seen_hands[(wk["game_id"], int(wk["round_no"]))] += 1

    report = {}
    for verdict, bucket in groups.items():
        values = sorted(bucket["delta"])
        n = bucket["n"]
        report[verdict] = {
            "n": n,
            "mean_delta": round(bucket["delta_sum"] / n, 3) if n else None,
            "median_delta": values[n // 2] if n else None,
            "win_rate": round(bucket["win"] / n, 4) if n else None,
        }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "validity-corpus.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": "sitin-corpus-validity/1", "files": len(files),
                   "hands_joined": len(seen_hands), "groups": report}, fh,
                  ensure_ascii=False, indent=1)
    print("文件", len(files), "| 关联到的单局", len(seen_hands))
    print("%-16s %-8s %-12s %-12s %-10s" % ("判定", "n", "均值分", "中位分", "胡率"))
    for verdict, stat in sorted(report.items(), key=lambda kv: -kv[1]["n"]):
        print("%-16s %-8d %-12s %-12s %-10s" % (verdict, stat["n"], stat["mean_delta"],
                                                stat["median_delta"], stat["win_rate"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
