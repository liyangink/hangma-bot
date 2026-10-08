"""能力题库 v1：把散在 5 个探针里的构造集收成一个可复算的题库，并给策略打轴 2 分。

层的划分按**判据可复算的强度**，不按对局阶段：
  L1 规则约束：抓打圈受限窗口内，策略选的动作是否满足官方硬约束（只能打刚摸牌、禁吃碰明杠）
  L3 支配情形：弃后仍任意听 ⇒ 追（飘）是收的 2 倍；否则应收 —— 答案由规则 + 精确期望确定
  L4 精确期望：k 巡内自摸期望最大的动作（闭式精确计算，含链/爆头/飘白数口径）
  L2 结算：官方金例（1048 例）由 sitin_official_crosscheck.py 记分，属规则层一致性，不在此重复

评分对象：V2 + 6 个 R10 候选 + chase_boundary_v1（各自经原有接缝装载）。
输出：分层的命中率表（每层各报，不混成一个数）。
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

import dataclasses  # noqa: E402

import sitin_k_turn_exact as kt  # noqa: E402
import sitin_opportunity_positions as opp  # noqa: E402
from hangma_bot.hangma.progression import chain_after_discard, recompute_baotou  # noqa: E402
from hangma_bot.hangma.special_rules import catch_play_restriction  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

WHITE = "白"
PIAO_KEY = "discard:" + WHITE
L1 = "L1_rule_constraints"
L3 = "L3_dominance"
L4 = "L4_exact_k_turn"

L1_HANDS = (
    (("1w", "1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", WHITE), "9w"),
    (("1b", "1b", "1b", "1b", "2b", "3b", "4b", "5b", "6b", "7b", "8b", "9b", WHITE), "9b"),
)


def build_l1_cases():
    """抓打圈受限窗口：我不是圈主，合法动作里既有刚摸牌也有别的弃牌。"""
    cases = []
    for index, (hand, draw) in enumerate(L1_HANDS):
        obs = opp._observation(hand, draw=draw, chain=0, piao=0, baotou=False)
        state = dataclasses.replace(obs.rule_state, catch_play=True,
                                    catch_play_owner_seat=1)
        obs = dataclasses.replace(obs, rule_state=state, seat=0)
        analysis = opp.RULES.analyze(obs, value_limits=opp.LIMITS)
        request = opp.make_request(obs, analysis)
        view = opp.build_scoring_view(request, value_limits=opp.LIMITS)
        drawn = Tile(draw)
        allowed = {action.action_key for action in view.actions
                   if catch_play_restriction(action.action, drawn) is None}
        cases.append({"id": "L1-catch-restricted-%d" % index, "layer": L1,
                      "request": request, "view": view, "answer": allowed,
                      "note": "官方指南 1.1 / API §5.4：受限座位只能打刚摸牌，禁吃碰明杠"})
    return cases


def exact_cases(hands, *, layer, label, baotou, chains=(0, 2), turns=(1, 4, 8, 12)):
    """精确期望型题目：答案 = 全部合法动作里 k 巡期望的 argmax 集合。

    答案集用 argmax（不是"只准飘或只准胡"）——否则策略选第三种更优动作会被误判为错。
    """
    cases = []
    for index, hand in enumerate(hands):
        world = kt.world_of(hand)
        draw = next((code for code in kt.ALL_CODES if world.get(code, 0) > 0), None)
        if draw is None:
            continue
        for chain in chains:
            obs = opp._observation(hand, draw=draw, chain=chain, piao=0, baotou=baotou)
            analysis = opp.RULES.analyze(obs, value_limits=opp.LIMITS)
            request = opp.make_request(obs, analysis)
            view = opp.build_scoring_view(request, value_limits=opp.LIMITS)
            hand14 = tuple(list(hand) + [draw])
            values = defaultdict(dict)
            for action in view.actions:
                if action.action_type == "hu" and action.immediate_settlement is not None:
                    fan = getattr(action.immediate_settlement, "fan", None)
                    if fan is not None:
                        for turns_k in turns:
                            values[action.action_key][turns_k] = float(fan)
                elif action.action_type == "discard":
                    code = action.action_key.split(":", 1)[-1]
                    post = list(hand14)
                    if code not in post:
                        continue
                    post.remove(code)
                    chain_next, piao_next = chain_after_discard(chain, 0, baotou, Tile(code))
                    baotou_next = recompute_baotou(tuple(Tile(c) for c in post), 0,
                                                   sum(1 for c in post if c == WHITE))
                    for turns_k in turns:
                        values[action.action_key][turns_k] = kt.k_turn_expectation(
                            tuple(post), world, chain_next, turns_k,
                            baotou=bool(baotou_next), piao=piao_next)
            for turns_k in turns:
                scored = {key: table[turns_k] for key, table in values.items()
                          if turns_k in table}
                if not scored:
                    continue
                best = max(scored.values())
                answer = {key for key, value in scored.items() if value >= best - 1e-9}
                note = "argmax k 巡精确期望 = %.4f" % best
                if baotou and PIAO_KEY in scored:
                    hu_value = scored.get("hu")
                    note += "；E(飘)=%.4f%s" % (
                        scored[PIAO_KEY],
                        "" if hu_value is None else "，fan(收)=%.4f" % hu_value)
                cases.append({"id": "%s-%d-chain%d-k%d" % (label, index, chain, turns_k),
                              "layer": layer, "request": request, "view": view,
                              "answer": answer, "note": note})
    return cases


def build_l3_cases(turns=(1, 4, 8, 12)):
    """支配情形族：爆头 + 手上有白（弃后是否仍任意听决定追还是收）。"""
    return exact_cases(list(opp.baotou_templates()), layer=L3, label="L3-baotou",
                       baotou=True, turns=turns)


def build_l4_cases(positions, turns=(1, 4, 8, 12)):
    """精确期望族：近听手牌（无爆头）。"""
    return exact_cases(positions, layer=L4, label="L4-near", baotou=False, turns=turns)


def score_case(case, policies):
    out = {}
    for name, chooser in policies.items():
        try:
            top = chooser(case["request"], case["view"])
        except Exception as error:
            out[name] = ("ERROR", str(error)[:40])
            continue
        out[name] = ("HIT" if top in case["answer"] else "MISS", top)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--max-rows", type=int, default=60000)
    ap.add_argument("--positions", type=int, default=12)
    args = ap.parse_args()

    import hangma_bot.hangma.hand_analysis as hand_analysis
    with open(args.manifest, encoding="utf-8") as fh:
        paths = [entry["path"] for entry in json.load(fh).get("files", ())]
    pool = opp.collect_hands(paths, args.hands, args.max_rows)
    near = [h for h in pool
            if hand_analysis.analyse_hand(tuple(Tile(c) for c in h), 0).shanten <= 1]

    scorers = opp.load_scorers()
    with open(os.path.join(HERE, "candidates", "chase_boundary_v1.py"), encoding="utf-8") as fh:
        chase_source = fh.read()
    policies = {"V2": lambda request, view: opp.first_v2(request)}
    for name, scorer in scorers.items():
        policies[name] = (lambda s: lambda request, view: opp.first_scored(s, view))(scorer)
    chase_scorer = ActionValueScorer("chase_boundary_v1", chase_source)
    policies["chase_boundary_v1"] = (
        lambda s: lambda request, view: opp.first_scored(s, view))(chase_scorer)

    cases = build_l1_cases() + build_l3_cases() + build_l4_cases(near[:args.positions])  # noqa: E501
    stats = defaultdict(lambda: defaultdict(Counter))
    detail = []
    for case in cases:
        result = score_case(case, policies)
        for name, (verdict, top) in result.items():
            stats[case["layer"]][name][verdict] += 1
        detail.append({"id": case["id"], "layer": case["layer"], "note": case["note"],
                       "answer": sorted(case["answer"]),
                       **{name: list(value) for name, value in result.items()}})

    os.makedirs(args.out, exist_ok=True)
    table = {}
    for layer in (L1, L3, L4):
        table[layer] = {}
        for name in policies:
            counter = stats[layer][name]
            total = sum(counter.values())
            hits = counter.get("HIT", 0)
            table[layer][name] = {"n": total, "hit": hits,
                                  "rate": round(hits / total, 4) if total else None}
    report = {"schema": "sitin-question-bank/1", "cases": len(cases), "table": table,
              "detail": detail}
    with open(os.path.join(args.out, "bank-v1.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    print("题目总数", len(cases),
          {layer: sum(1 for c in cases if c["layer"] == layer) for layer in (L1, L3, L4)})
    print("%-20s" % "layer" + "".join("%-14s" % name[:13] for name in policies))
    for layer in (L1, L3, L4):
        row = "%-20s" % layer
        for name in policies:
            stat = table[layer][name]
            row += "%-14s" % ("%s/%s" % (stat["hit"], stat["n"]))
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
