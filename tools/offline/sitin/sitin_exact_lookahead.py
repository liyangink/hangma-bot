"""能力尺 · 第四阶段（层 2）：**精确下一巡期望**，把"敏感度"升级为"判断质量"。

在**声明的世界假设**下精确计算（不是抽样）：
  - 世界：除本人手牌与已见外，其余牌按每种 4 张扣减本人手持，均匀未知（经典牌效口径）；
  - 对每个合法弃牌动作：算出动作后手牌的**自摸成胡牌集合**及其剩余张数 ⇒ 精确自摸概率；
  - 每个成胡牌的**番值**由规则引擎现算（fan-calc 同源）⇒ 动作的精确下一巡期望；
  - 不建模他家自摸与鸣牌（超出下一巡范围），**在报告中显式声明**。

产出：每个构造局点上，各策略所选动作的**精确期望**与"最优动作期望"之差（regret）。
用途：回答"保住路线/追求番值"到底是**更好还是更差**——这是层 1 判据的真值校准。
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
from collections import Counter, defaultdict

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

import sitin_opportunity_positions as opp  # noqa: E402  （复用构造与策略装载）

import hangma_bot.hangma.hand_analysis as hand_analysis  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_CODES, Tile  # noqa: E402

WHITE = "白"
ALL_CODES = [str(code) for code in CANONICAL_TILE_CODES]


def remaining_world(hand):
    """声明世界：每种牌 4 张，扣除本人手持；返回 {code: 剩余张数}。"""
    counts = Counter(hand)
    world = {}
    for code in ALL_CODES:
        left = 4 - counts.get(code, 0)
        if left > 0:
            world[code] = left
    return world


def win_payoffs(hand, world):
    """对 13 张手牌枚举成胡牌：返回 {code: fan}（规则引擎判定，非本脚本重算）。"""
    wins = {}
    for code, left in world.items():
        if left <= 0:
            continue
        try:
            obs = opp._observation(tuple(hand), draw=code, chain=0, piao=0, baotou=False)
            analysis = opp.RULES.analyze(obs, value_limits=opp.LIMITS)
            request = opp.make_request(obs, analysis)
            view = opp.build_scoring_view(request, value_limits=opp.LIMITS)
        except Exception:
            continue
        for action in view.actions:
            if action.action_type != "hu":
                continue
            settlement = action.immediate_settlement
            fan = getattr(settlement, "fan", None) if settlement is not None else None
            if fan is not None:
                wins[code] = int(fan)
            break
    return wins


def action_expectation(post_hand, world, total_unknown):
    """精确下一巡期望 = Σ_T (剩余张数/未知总数) × 番值。"""
    wins = win_payoffs(post_hand, world)
    if not wins:
        return 0.0, 0, 0
    num = sum(world[code] * fan for code, fan in wins.items())
    return (num / total_unknown if total_unknown else 0.0), len(wins), sum(world[c] for c in wins)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--hands", type=int, default=400, help="先收集的手牌池大小")
    ap.add_argument("--max-shanten", type=int, default=1, help="只保留向听 <= 该值的手牌")
    ap.add_argument("--max-rows", type=int, default=60000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    paths = []
    with open(args.manifest, encoding="utf-8") as fh:
        paths = [entry["path"] for entry in json.load(fh).get("files", ())]
    pool = opp.collect_hands(paths, args.hands, args.max_rows)

    def shanten(hand):
        try:
            return hand_analysis.analyse_hand(tuple(Tile(c) for c in hand), 0).shanten
        except Exception:
            return 99

    near = [h for h in pool if shanten(h) <= args.max_shanten]
    quad_hands = [q for q in (opp.force_quad(h) for h in near) if q]
    baotou_hands = opp.baotou_templates()
    print("pool:", len(pool), "| near-tenpai(<=%d):" % args.max_shanten, len(near),
          "| quad:", len(quad_hands), "| baotou:", len(baotou_hands))

    scorers = opp.load_scorers()
    policies = ["V2"] + list(scorers)

    rows = []
    for family, hand_list, baotou in (("A_gang_chain", quad_hands, False),
                                      ("C_piao_chain", baotou_hands, True)):
        for hand in hand_list:
            world = remaining_world(hand)
            total_unknown = sum(world.values())
            for chain in (0, 2):
                # 摸牌窗必须携带刚摸到的第 14 张：取声明世界里第一张仍有剩余的牌（确定性）
                draw = next((code for code in ALL_CODES if world.get(code, 0) > 0), None)
                if draw is None:
                    continue
                obs = opp._observation(hand, draw=draw, chain=chain, piao=0, baotou=baotou)
                analysis = opp.RULES.analyze(obs, value_limits=opp.LIMITS)
                request = opp.make_request(obs, analysis)
                view = opp.build_scoring_view(request, value_limits=opp.LIMITS)
                kinds = {action.action_key: action.action_type for action in view.actions}
                hand14 = tuple(list(hand) + [draw])
                per_action = {}
                for action in view.actions:
                    if action.action_type == "hu" and action.immediate_settlement is not None:
                        fan = getattr(action.immediate_settlement, "fan", None)
                        if fan is not None:
                            per_action[action.action_key] = float(fan)  # 立即胡：确定收益
                        continue
                    if action.action_type != "discard":
                        continue
                    code = action.action_key.split(":", 1)[-1]
                    remaining = list(hand14)
                    if code in remaining:
                        remaining.remove(code)
                    exp, _wins, _tiles = action_expectation(tuple(remaining), world, total_unknown)
                    per_action[action.action_key] = exp
                if not per_action:
                    continue
                best = max(per_action.values())
                picks = {"V2": opp.first_v2(request)}
                for name, scorer in scorers.items():
                    try:
                        picks[name] = opp.first_scored(scorer, view)
                    except Exception:
                        picks[name] = ""
                row = {
                    "family": family, "chain": chain, "hand": "".join(hand),
                    "best_expectation": round(best, 6),
                    "preserve_key": "discard:" + WHITE if ("discard:" + WHITE) in per_action else None,
                    "preserve_expectation": (round(per_action.get("discard:" + WHITE, 0.0), 6)
                                             if ("discard:" + WHITE) in per_action else None),
                    "actions": {k: round(v, 6) for k, v in per_action.items()},
                    "picks": {name: {"key": key,
                                     "expectation": round(per_action.get(key, 0.0), 6),
                                     "regret": round(best - per_action.get(key, 0.0), 6)}
                              for name, key in picks.items()},
                }
                rows.append(row)

    stats = defaultdict(lambda: defaultdict(list))
    for row in rows:
        for name, pick in row["picks"].items():
            stats[row["family"]][name].append(pick["regret"])

    summary = {}
    for family, per_policy in stats.items():
        summary[family] = {}
        for name, regrets in per_policy.items():
            ordered = sorted(regrets)
            summary[family][name] = {
                "n": len(regrets),
                "mean_regret": round(sum(regrets) / len(regrets), 6) if regrets else None,
                "optimal_hits": sum(1 for value in regrets if value == 0),
                "median_regret": round(ordered[len(ordered) // 2], 6) if ordered else None,
            }

    os.makedirs(args.out, exist_ok=True)
    report = {"schema": "sitin-exact-lookahead/1",
              "world_assumption": "每种牌 4 张扣本人手持后均匀未知；只算本人下一巡自摸，不建模他家自摸/鸣牌",
              "scope": {"pool": len(pool), "positions": len(rows),
                        "hands": args.hands, "manifest": args.manifest},
              "summary": summary, "rows": rows[:200]}
    with open(os.path.join(args.out, "lookahead.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    for family, per_policy in summary.items():
        print()
        print("##", family)
        for name, stat in per_policy.items():
            print("   %-16s n=%-4d 平均regret=%-10s 命中最优=%-4d 中位regret=%s" % (
                name, stat["n"], stat["mean_regret"], stat["optimal_hits"],
                stat["median_regret"]))
    if rows:
        sample = rows[0]
        print()
        print("样例位点 chain=%s 最优期望=%s 保白期望=%s" % (
            sample["chain"], sample["best_expectation"], sample["preserve_expectation"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
