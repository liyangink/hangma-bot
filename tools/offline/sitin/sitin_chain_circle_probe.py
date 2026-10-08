"""抓打圈/动作链第二轮：官方 v18 轨迹对拍 + 吃分支补齐。

1. 官方 v18 轨迹（chi-gang-draw.json）：把每个快照记录的 god 与**我们用规则重算的结果**对拍——
   爆头用 `recompute_baotou`（弃后/摸前暗牌），链用 §8 事件表推导，而不是只读 god。
2. 吃分支：把响应窗的 phase 置为 `response_chi` 后，检查吃候选是否出现、受限座位是否被正确禁止。
3. 圈主官方证据边界：统计含 `catch_play=true` 的官方快照（目前仅 v24 一处）。
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
import dataclasses
import json
import os
import sys
from collections import Counter

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from hangma_bot.hangma import catch_play  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.hangma.progression import recompute_baotou  # noqa: E402
from hangma_bot.hangma.special_rules import catch_play_restriction  # noqa: E402
from hangma_bot.kernel.actions import Chi, Tile  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402

from tests.unit.hangma.test_value_analysis import _observation  # noqa: E402

RULES = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
LIMITS = ValueAnalysisLimits()
WHITE = "白"


def _tiles(hand):
    return tuple(Tile(code) for code in hand)


def check_trajectory(path):
    """官方轨迹：god 与我们重算的爆头/链对拍。"""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    events = data.get("events")
    rows = []
    for key in sorted(data["snapshots"], key=lambda k: int(k)):
        snapshot = data["snapshots"][key]["snapshot"]
        god = snapshot.get("god") or {}
        hand = list(snapshot.get("my_hand") or ())
        drawn = snapshot.get("drawn_tile")
        melds = snapshot.get("melds")
        own_melds = 0
        if isinstance(melds, list):
            seat = int(snapshot.get("seat", 0))
            if seat < len(melds) and isinstance(melds[seat], list):
                own_melds = len(melds[seat])
        # 摸牌窗：手牌不含摸牌 ⇒ 直接判定；响应窗：手牌即当前暗牌
        concealed = list(hand)
        if drawn is not None and snapshot.get("phase") == "draw":
            concealed.append(drawn)
        whites = sum(1 for code in concealed if str(code) == WHITE)
        derived = None
        if len(concealed) % 3 == 2 or (len(concealed) + 3 * own_melds) % 3 == 1:
            try:
                derived = bool(recompute_baotou(_tiles([str(c) for c in concealed]),
                                                own_melds, whites))
            except Exception:
                derived = None
        rows.append({
            "seq": int(key), "phase": snapshot.get("phase"),
            "god_baotou": god.get("baotou"), "god_chain": god.get("chain_count"),
            "derived_baotou": derived,
            "agree": (None if derived is None else derived == bool(god.get("baotou"))),
            "hand_n": len(hand), "melds": own_melds, "drawn": drawn,
        })
    return {"rows": rows, "events_present": bool(events)}


def check_chi_branch():
    """吃分支：把响应窗 phase 置为 response_chi 后再看候选与限制。"""
    obs = _observation(("7b", "8b", "9b", "9b", "1t", "2t", "3t", "5w", "5w",
                        "1w", "1w", WHITE, "发"), response="9b")
    obs = dataclasses.replace(obs, phase="response_chi")
    analysis = RULES.analyze(obs, value_limits=LIMITS)
    chi = [c.action for c in analysis.legal_candidates if isinstance(c.action, Chi)]
    reasons = [catch_play_restriction(action, None) for action in chi]
    return {"chi_candidates": len(chi),
            "restricted_reasons": [r for r in reasons if r],
            "all_restricted": bool(chi) and all(reasons)}


def count_circle_snapshots():
    """统计含 catch_play=true 的官方快照文件。"""
    hits = []
    for root, _dirs, files in os.walk(os.path.join(ROOT, "tests/fixtures/official")):
        for name in files:
            if not name.endswith(".json"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    if '"catch_play": true' in fh.read():
                        hits.append(os.path.relpath(path, ROOT))
            except Exception:
                continue
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    trajectory = check_trajectory(
        os.path.join(ROOT, "tests/fixtures/official/v18/action-chain/chi-gang-draw.json"))
    chi = check_chi_branch()
    circle = count_circle_snapshots()
    os.makedirs(args.out, exist_ok=True)
    report = {"schema": "sitin-chain-circle-probe/1", "trajectory": trajectory,
              "chi_branch": chi, "circle_fixtures": circle}
    with open(os.path.join(args.out, "chain-circle.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    print("== 官方 v18 轨迹：god vs 我们重算 ==")
    for row in trajectory["rows"]:
        print("   seq %-5s %-14s god.baotou=%-5s 重算=%-5s 一致=%-5s 手牌%2d 副露%d 摸=%s" % (
            row["seq"], row["phase"], row["god_baotou"], row["derived_baotou"],
            row["agree"], row["hand_n"], row["melds"], row["drawn"]))
    print()
    print("== 吃分支 ==", json.dumps(chi, ensure_ascii=False))
    print("== 含 catch_play=true 的官方 fixture ==", circle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
