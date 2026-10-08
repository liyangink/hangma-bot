"""能力尺 · 第五阶段（层 2b）：**k 巡精确期望**——让"追大牌"的价值进入同一个精确口径。

关键修正（依 RULES_EVIDENCE §8）：
  - 飘 = 爆头态打出财神；**爆头态随后用"弃后暗牌"重算**（不是自动保持）；
  - 弃非飘非杠的牌 → 链断清零；杠 → 链 +1（本版不建模杠补牌，见局限）；
  - 胡牌番值一律由规则引擎现算，链倍率在"胡的那一刻"按当时链计数生效。

精确性：在声明的世界假设下，k 巡内自摸的期望用**闭式**计算（不是抽样）：
  P(第 j 巡首次命中牌 T) = Π_{i<j}(1 − w/(n−i)) × count_T/(n−j)
  E = Σ_j Σ_T P × fan(T)，另有"现在收胡"= fan(现胡) × 1（确定）。
  继续策略声明为**"摸什么打什么"**（手牌静止、墙递减），因此上式无需自由参数。
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

import sitin_opportunity_positions as opp  # noqa: E402
from hangma_bot.hangma.progression import chain_after_discard, recompute_baotou  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_CODES, Tile  # noqa: E402

WHITE = "白"
ALL_CODES = [str(code) for code in CANONICAL_TILE_CODES]


def world_of(hand):
    counts = Counter(hand)
    return {code: 4 - counts.get(code, 0) for code in ALL_CODES
            if 4 - counts.get(code, 0) > 0}


def fan_of(hand13, drawn, chain, baotou=False, piao=0):
    """规则引擎判定：手牌 + 摸牌 在该链计数与爆头态下成胡的番值；不能胡返回 None。

    爆头（×2）必须与决策窗口同态，否则番值口径与候选看到的 immediate_settlement 不一致。
    """
    try:
        obs = opp._observation(tuple(hand13), draw=drawn, chain=chain, piao=piao, baotou=baotou)
        analysis = opp.RULES.analyze(obs, value_limits=opp.LIMITS)
        request = opp.make_request(obs, analysis)
        view = opp.build_scoring_view(request, value_limits=opp.LIMITS)
    except Exception:
        return None
    for action in view.actions:
        if action.action_type != "hu":
            continue
        settlement = action.immediate_settlement
        fan = getattr(settlement, "fan", None) if settlement is not None else None
        return None if fan is None else int(fan)
    return None


def hit_table(hand13, world, chain, baotou=False, piao=0):
    """动作后手牌的可胡牌表：{code: (fan, 剩余张数)}；番值口径与决策窗口同态。"""
    table = {}
    for code, left in world.items():
        if left <= 0:
            continue
        fan = fan_of(hand13, code, chain, baotou=baotou, piao=piao)
        if fan is not None:
            table[code] = (fan, left)
    return table


def k_turn_expectation(hand13, world, chain, turns, *, with_probability=False,
                       baotou=False, piao=0):
    """k 巡内自摸的精确期望（摸什么打什么）；可选同时返回命中概率。

    baotou/piao 必须传"动作之后"的状态，否则这条路径与 fan_chase 的口径不一致。
    """
    table = hit_table(hand13, world, chain, baotou=baotou, piao=piao)
    total = sum(world.values())
    if not table or total <= 0:
        return (0.0, 0.0) if with_probability else 0.0
    expectation = 0.0
    survival = 1.0
    n = total
    for _step in range(turns):
        if n <= 0:
            break
        wins_now = sum(left for _fan, left in table.values())
        if wins_now > 0:
            for fan, left in table.values():
                expectation += survival * (left / n) * fan
        survival *= max(0.0, 1.0 - wins_now / n)
        n -= 1
    if with_probability:
        return expectation, 1.0 - survival
    return expectation


def chase_versus_take(hand, world, draw, is_baotou, chain, turns):
    """「收」与「追」的精确对照。

    收：立即胡（确定）⇒ 期望 = 当前链下的番值。
    追：打出财神（爆头态即飘，链 +1、爆头按弃后暗牌重算），此后**恢复「能胡就胡」**；
        期望 = P(k 巡内再胡) × 新链下的番值。
    返回 dict（缺项为 None），并给出盈亏平衡所需的命中概率。
    """
    hand14 = tuple(list(hand) + [draw])
    fan_take = fan_of(tuple(hand), draw, chain, baotou=bool(is_baotou)) if is_baotou else None
    result = {"fan_take": fan_take}
    white_key = WHITE
    if white_key not in hand14:
        return result
    post = list(hand14)
    post.remove(white_key)
    post = tuple(post)
    chain_next, piao_next = chain_after_discard(chain, 0, bool(is_baotou), Tile(WHITE))
    baotou_after = recompute_baotou(tuple(Tile(c) for c in post), 0,
                                    sum(1 for c in post if c == WHITE))
    expectation, probability = k_turn_expectation(
        post, world, chain_next, turns, with_probability=True,
        baotou=bool(baotou_after), piao=piao_next)
    fan_chase = 0
    for code, left in world.items():
        if left <= 0:
            continue
        fan = fan_of(post, code, chain_next, baotou=bool(baotou_after), piao=piao_next)
        if fan is not None:
            fan_chase = max(fan_chase, fan)
    result["baotou_after_piao"] = baotou_after
    result.update({"expectation_chase": expectation, "probability_chase": probability,
                   "fan_chase_per_hit": fan_chase, "chain_after_piao": chain_next})
    if fan_take:
        result["breakeven_probability"] = round(fan_take / fan_chase, 4) if fan_chase else None
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--max-rows", type=int, default=60000)
    ap.add_argument("--max-positions", type=int, default=16)
    ap.add_argument("--turns", default="1,4,8,12")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        paths = [entry["path"] for entry in json.load(fh).get("files", ())]
    pool = opp.collect_hands(paths, args.hands, args.max_rows)
    import hangma_bot.hangma.hand_analysis as hand_analysis

    near = [h for h in pool
            if hand_analysis.analyse_hand(tuple(Tile(c) for c in h), 0).shanten <= 1]
    positions = [("A_near", h, False) for h in near[:args.max_positions]]
    positions += [("C_baotou", h, True) for h in opp.baotou_templates()]
    turns_list = [int(x) for x in str(args.turns).split(",") if x.strip()]

    scorers = opp.load_scorers()
    policies = ["V2"] + list(scorers)
    regrets = defaultdict(lambda: defaultdict(list))

    for family, hand, is_baotou in positions:
        world = world_of(hand)
        draw = next((code for code in ALL_CODES if world.get(code, 0) > 0), None)
        if draw is None:
            continue
        obs = opp._observation(hand, draw=draw, chain=0, piao=0, baotou=is_baotou)
        analysis = opp.RULES.analyze(obs, value_limits=opp.LIMITS)
        request = opp.make_request(obs, analysis)
        view = opp.build_scoring_view(request, value_limits=opp.LIMITS)
        hand14 = tuple(list(hand) + [draw])
        value = {}
        for action in view.actions:
            key = action.action_key
            if action.action_type == "hu" and action.immediate_settlement is not None:
                fan = getattr(action.immediate_settlement, "fan", None)
                if fan is not None:
                    value[key] = {t: float(fan) for t in turns_list}
                continue
            if action.action_type != "discard":
                continue
            code = key.split(":", 1)[-1]
            post = list(hand14)
            if code in post:
                post.remove(code)
            else:
                continue
            chain_next, piao_next = chain_after_discard(0, 0, bool(is_baotou), Tile(code))
            baotou_next = recompute_baotou(tuple(Tile(c) for c in post), 0,
                                           sum(1 for c in post if c == WHITE))
            # 后态用于记录；k 巡期望按"弃牌后链计数"结算番值
            value[key] = {t: k_turn_expectation(tuple(post), world, chain_next, t)
                          for t in turns_list}
            value[key]["_baotou_next"] = baotou_next
        if not value:
            continue
        picks = {"V2": opp.first_v2(request)}
        for name, scorer in scorers.items():
            try:
                picks[name] = opp.first_scored(scorer, view)
            except Exception:
                picks[name] = ""
        for name, key in picks.items():
            if key not in value:
                continue
            for t in turns_list:
                best = max(v[t] for k, v in value.items()
                           if k != "_baotou_next" and t in v)
                regrets[family][name].append((t, round(best - value[key][t], 6)))

    summary = {}
    for family, per_policy in regrets.items():
        summary[family] = {}
        for name, rows in per_policy.items():
            by_turn = defaultdict(list)
            for turn, regret in rows:
                by_turn[turn].append(regret)
            summary[family][name] = {str(t): round(sum(v) / len(v), 6)
                                     for t, v in sorted(by_turn.items())}

    chase_rows = []
    for family, hand, is_baotou in positions:
        world = world_of(hand)
        draw = next((code for code in ALL_CODES if world.get(code, 0) > 0), None)
        if draw is None or WHITE not in hand:
            continue
        for chain in (0, 2):
            try:
                row = chase_versus_take(hand, world, draw, is_baotou, chain, 8)
            except Exception:
                continue
            if row.get("fan_take") is None:
                continue
            row["family"] = family
            row["chain"] = chain
            row["hand"] = "".join(hand)
            row["chase_is_better"] = bool(
                row.get("expectation_chase") is not None
                and row["expectation_chase"] > row["fan_take"])
            chase_rows.append(row)

    if chase_rows:
        print()
        print("## 追 vs 收（k=8；追=打白后恢复收胡）")
        print("%-10s %-6s %-10s %-14s %-14s %-12s %-10s" % (
            "family", "chain", "fan(收)", "E(追)", "P(追后8巡胡)", "需要P(平衡)", "追更优?"))
        for row in chase_rows:
            print("%-10s %-6s %-10s %-14s %-14s %-12s %-10s" % (
                row["family"], row["chain"], row["fan_take"],
                None if row.get("expectation_chase") is None else round(row["expectation_chase"], 4),
                None if row.get("probability_chase") is None else round(row["probability_chase"], 4),
                row.get("breakeven_probability"), row["chase_is_better"]))
    os.makedirs(args.out, exist_ok=True)
    report = {"schema": "sitin-k-turn-exact/2",
              "world_assumption": "每种牌 4 张扣本人手持后均匀未知；继续策略=摸什么打什么；"
                                  "只算本人自摸，不建模他家自摸/鸣牌与杠补牌",
              "positions": len(positions), "turns": turns_list, "summary": summary,
              "chase_versus_take": chase_rows}
    with open(os.path.join(args.out, "kturn.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    for family, per_policy in summary.items():
        print()
        print("##", family, "（平均 regret，越小越好；列=剩余巡数）")
        header = "%-16s" % "policy" + "".join("%-12s" % ("k=%d" % t) for t in turns_list)
        print(header)
        for name, stats in per_policy.items():
            print("%-16s" % name + "".join("%-12s" % stats.get(str(t)) for t in turns_list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
