"""能力尺 · 第三阶段：同一批构造位点上跑 V2 与 6 个候选，测"机会敏感度"。

方法（同手牌、只改规则状态，每个策略自己当自己的对照）：
  - 族 A（杠·链）：把手牌确定性改成含四张同牌 ⇒ 必有杠候选；链 0 vs 2。
  - 族 C（飘·链）：从语料筛**爆头态且手上有白**的手牌 ⇒ 飘可选；链 0 vs 2。
  - 敏感度 = 同手牌在链 0 与链 2 下**首选是否不同**；另记"选杠率""选飘率"。
  判据只涉及规则事实与行为差异，不声称哪个更优（最优性留给层 2 真值校准）。

边界：构造局面不是自然轨迹，不能作强度证据；候选以 ActionValueScorer 受限执行器装载。
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
import asyncio
import dataclasses
import glob
import json
import os
import sys
import time
from collections import Counter
from dataclasses import replace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from hangma_bot.bootstrap import build_decision_codec  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.hangma.progression import recompute_baotou  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402

from tests.unit.hangma.test_value_analysis import _observation  # noqa: E402
from tests.unit.policy.support import make_request  # noqa: E402

RULES = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
LIMITS = ValueAnalysisLimits()
POLICY = ComparableHeuristicPolicyV2()
DECODE = build_decision_codec()["decode_request"]
WHITE = "白"

CANDIDATES = (
    "hard-astra-high", "hard-sol-high", "hard-sol-max",
    "hard-terra-max", "river-sol-high", "route-terra-max",
)


def first_v2(request):
    now = time.monotonic()
    budget = DecisionBudget(now + 30.0, now + 31.0, now + 32.0)
    plan = asyncio.run(POLICY.choose(request, budget))
    if plan is None or not plan.candidates:
        return ""
    return str(plan.candidates[0].action_key)


def first_scored(scorer, view):
    batch = scorer.score(view)
    if getattr(batch, "status", None) != "SCORED" or not batch.entries:
        return ""
    pairs = []
    for entry in batch.entries:
        key = entry["action_key"] if isinstance(entry, dict) else entry.action_key
        score = entry["score"] if isinstance(entry, dict) else entry.score
        pairs.append((key, float(score)))
    pairs.sort(key=lambda kv: (-kv[1], kv[0]))
    return pairs[0][0]


def collect_hands(paths, want, max_rows):
    hands = {}
    rows = 0
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if rows >= max_rows or (want and len(hands) >= want):
                    return list(hands.values())
                rows += 1
                try:
                    obs = DECODE(json.loads(line)["request"]).observation
                except Exception:
                    continue
                if any(getattr(obs, "melds", ()) or ()):
                    continue
                hand = tuple(getattr(t, "code", str(t)) for t in (obs.my_hand or ()))
                if len(hand) != 13:
                    continue
                key = tuple(sorted(hand))
                if key not in hands:
                    hands[key] = hand
    return list(hands.values())


def force_quad(hand):
    counts = Counter(hand)
    target = None
    for code, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if n < 4:
            target = code
            break
    if target is None:
        return None
    out = list(hand)
    need = 4 - counts[target]
    for index, code in enumerate(out):
        if need == 0:
            break
        if code == target:
            continue
        out[index] = target
        need -= 1
    return tuple(out) if need == 0 else None


def baotou_templates():
    """确定性地造爆头手牌：**四副面子 + 单张白**（13 张）。

    依据：暗牌为 4 面子 + 1 张白时，摸任意牌都能用白与它组成将牌 ⇒ 爆头；
    并因此**手上有白**，飘（爆头态打白）可选。多套模板只换花色与序号，
    避免单点结论。
    """
    templates = []
    suits = ("w", "b", "t", "w", "b")
    for index, suit in enumerate(suits):
        back = suits[(index + 1) % len(suits)]
        if back == suit:
            back = "b" if suit != "b" else "w"
        # 顺子面子：按 index 轮转起点，避免所有模板同形
        start = 1 + (index % 3)
        run_a = [str(start + offset) + suit for offset in range(3)]
        run_b = [str(start + offset) + back for offset in range(3)]
        run_c = [str(start + offset + 3) + suit for offset in range(3)]
        triplet = [str(start) + suit] * 3
        melds = run_a + run_b + run_c + triplet
        templates.append(tuple(melds + [WHITE]))
    # 双白版本：手上两张财神，飘与保白的取舍更尖锐
    templates.append(tuple(["1w", "2w", "3w", "4w", "5w", "6w",
                            "7w", "8w", "9w", WHITE, WHITE, WHITE, WHITE]))
    return templates


def is_baotou_hand(hand) -> bool:
    """规则判定：摸前暗牌接任意可得牌均成胡（爆头）。"""
    try:
        return bool(recompute_baotou(tuple(Tile(code) for code in hand), 0, 0))
    except Exception:
        return False


def build(hand, chain, *, baotou=False, piao=0):
    obs = _observation(hand, chain=chain, piao=piao, baotou=baotou)
    analysis = RULES.analyze(obs, value_limits=LIMITS)
    request = make_request(obs, analysis)
    view = build_scoring_view(request, value_limits=LIMITS)
    kinds = {action.action_key: action.action_type for action in view.actions}
    return request, view, kinds


def load_scorers():
    """按固定清单装载 6 个候选（受限执行器），供其他探针复用。"""
    loaded = {}
    base = os.path.join(ROOT, "review/llm-guided-heuristic-route-2026-09-15",
                        "evidence/r10-supervised-evolution/strong-seeds-20260920")
    for name in CANDIDATES:
        found = sorted(glob.glob(os.path.join(base, name, "run/iterations/*/generation/candidate.py")))
        if not found:
            continue
        with open(found[0], encoding="utf-8") as fh:
            loaded[name] = ActionValueScorer(name, fh.read())
    return loaded


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--corpus")
    ap.add_argument("--hands", type=int, default=150, help="基座手牌上限（0=不限）")
    ap.add_argument("--max-rows", type=int, default=60000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    paths = []
    if args.manifest:
        with open(args.manifest, encoding="utf-8") as fh:
            paths = [entry["path"] for entry in json.load(fh).get("files", ())]
    if args.corpus:
        paths = sorted(set(paths) | set(glob.glob(args.corpus)))
    paths = sorted(paths)
    if not paths:
        print("no corpus matched")
        return 2

    hands = collect_hands(paths, args.hands, args.max_rows)
    quad_hands = [q for q in (force_quad(h) for h in hands) if q]
    baotou_hands = [h for h in hands if WHITE in h and is_baotou_hand(h)]
    print("base hands:", len(hands), "| quad:", len(quad_hands), "| baotou+white:", len(baotou_hands))

    scorers = {}
    base = os.path.join(ROOT, "review/llm-guided-heuristic-route-2026-09-15",
                        "evidence/r10-supervised-evolution/strong-seeds-20260920")
    for name in CANDIDATES:
        found = sorted(glob.glob(os.path.join(base, name, "run/iterations/*/generation/candidate.py")))
        if not found:
            print("missing candidate:", name)
            continue
        with open(found[0], encoding="utf-8") as fh:
            scorers[name] = ActionValueScorer(name, fh.read())

    policies = ["V2"] + list(scorers)
    stats = {name: Counter() for name in policies}

    baotou_synth = baotou_templates()
    baotou_chain = []
    for hand in baotou_synth:
        try:
            obs = _observation(hand, chain=0, piao=0, baotou=True)
            if bool(obs.rule_state.baotou):
                baotou_chain.append(hand)
        except Exception:
            continue
    print("synthetic baotou hands:", len(baotou_chain))
    for family, hand_list in (("A_gang_chain", quad_hands),
                              ("C_piao_chain", baotou_chain)):
        for hand in hand_list:
            variants = {}
            for chain in (0, 2):
                try:
                    request, view, kinds = build(hand, chain,
                                                 baotou=(family == "C_piao_chain"))
                except Exception:
                    variants = {}
                    break
                picks = {"V2": first_v2(request)}
                for name, scorer in scorers.items():
                    try:
                        picks[name] = first_scored(scorer, view)
                    except Exception:
                        picks[name] = ""
                variants[chain] = {"kinds": kinds, "picks": picks}
            if len(variants) != 2:
                continue
            for name in policies:
                stat = stats[name]
                stat[family + "_hands"] += 1
                a = variants[0]["picks"].get(name, "")
                b = variants[2]["picks"].get(name, "")
                if not a or not b:
                    stat[family + "_unscored"] += 1
                    continue
                if a != b:
                    stat[family + "_changed"] += 1
                kinds0 = variants[0]["kinds"]
                if kinds0.get(a) == "gang":
                    stat[family + "_gang_at_0"] += 1
                if variants[2]["kinds"].get(b) == "gang":
                    stat[family + "_gang_at_2"] += 1
                if kinds0.get(a) == "discard" and str(a).endswith(":" + WHITE):
                    stat[family + "_piao_at_0"] += 1
                if str(b).endswith(":" + WHITE):
                    stat[family + "_piao_at_2"] += 1
                if family == "C_piao_chain":
                    stat[family + "_kind_" + (kinds0.get(a) or "?")] += 1

    os.makedirs(args.out, exist_ok=True)
    report = {"schema": "sitin-opportunity-positions/3",
              "scope": {"base_hands": len(hands), "quad_hands": len(quad_hands),
                        "baotou_hands": len(baotou_hands), "manifest": args.manifest},
              "stats": {name: dict(counter) for name, counter in stats.items()}}
    with open(os.path.join(args.out, "positions.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    print()
    print("%-16s %-14s %s" % ("policy", "family", "hands / changed / gang@0 / gang@2 / piao@0 / piao@2"))
    for name in policies:
        stat = stats[name]
        for family in ("A_gang_chain", "C_piao_chain"):
            n = stat.get(family + "_hands", 0)
            print("%-16s %-14s n=%-4d changed=%-4d gang0=%-3d gang2=%-3d piao0=%-3d piao2=%-3d" % (
                name, family, n, stat.get(family + "_changed", 0),
                stat.get(family + "_gang_at_0", 0), stat.get(family + "_gang_at_2", 0),
                stat.get(family + "_piao_at_0", 0), stat.get(family + "_piao_at_2", 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
