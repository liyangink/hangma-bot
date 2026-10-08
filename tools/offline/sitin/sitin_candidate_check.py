"""候选校验：chase_boundary_v1 是否按「追 vs 收」的精确判据做选择。

对每个构造位点（爆头手牌 × 链深 × 剩余巡数 k）：
  - 精确真值来自 sitin_k_turn_exact（规则引擎现算，零随机）；
  - 候选经 ActionValueScorer（受限执行器）装载，取最高分动作；
  - 两件事：① 候选是否与"精确最优"一致；② 选择带来的精确 regret。
同时测两种装法：候选内部 K_TURNS 与当前 k 一致（对齐）与固定 12（不对齐）。
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

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

import sitin_k_turn_exact as kt  # noqa: E402
import sitin_opportunity_positions as opp  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

CANDIDATE = os.path.join(HERE, "candidates", "chase_boundary_v1.py")
WHITE_KEY = "discard:" + kt.WHITE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", default="4,8,12")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    turns_list = [int(x) for x in args.turns.split(",") if x.strip()]

    with open(CANDIDATE, encoding="utf-8") as fh:
        base_source = fh.read()

    rows = []
    for index, hand in enumerate(opp.baotou_templates()):
        world = kt.world_of(hand)
        draw = next((code for code in kt.ALL_CODES if world.get(code, 0) > 0), None)
        if draw is None or kt.WHITE not in hand:
            continue
        for chain in (0, 2):
            obs = opp._observation(hand, draw=draw, chain=chain, piao=0, baotou=True)
            analysis = opp.RULES.analyze(obs, value_limits=opp.LIMITS)
            request = opp.make_request(obs, analysis)
            view = opp.build_scoring_view(request, value_limits=opp.LIMITS)
            for turns in turns_list:
                exact = kt.chase_versus_take(hand, world, draw, True, chain, turns)
                fan_take = exact.get("fan_take")
                e_chase = exact.get("expectation_chase")
                if fan_take is None or e_chase is None:
                    continue
                best_is_chase = e_chase > fan_take
                record = {"hand": index, "chain": chain, "k": turns,
                          "fan_take": fan_take, "E_chase": round(e_chase, 4),
                          "exact_best": "chase" if best_is_chase else "take"}
                for label, source in (("aligned", base_source.replace("K_TURNS = 12", "K_TURNS = %d" % turns)),
                                      ("fixed12", base_source)):
                    scorer = ActionValueScorer("chase_boundary_v1_" + label, source)
                    try:
                        top = opp.first_scored(scorer, view)
                    except Exception as error:
                        record[label] = {"error": str(error)[:80]}
                        continue
                    chose_chase = top == WHITE_KEY
                    picked_value = e_chase if chose_chase else (
                        fan_take if top.startswith("hu") else None)
                    best_value = e_chase if best_is_chase else fan_take
                    record[label] = {
                        "top": top,
                        "choice": "chase" if chose_chase else ("take" if top.startswith("hu") else "other"),
                        "matches_exact": bool(chose_chase == best_is_chase),
                        "regret": None if picked_value is None else round(best_value - picked_value, 4),
                    }
                rows.append(record)

    summary = {}
    for label in ("aligned", "fixed12"):
        cells = [r[label] for r in rows if isinstance(r.get(label), dict) and "error" not in r[label]]
        matches = [c for c in cells if c.get("matches_exact")]
        regrets = [c["regret"] for c in cells if c.get("regret") is not None]
        summary[label] = {
            "n": len(cells),
            "matches": len(matches),
            "mean_regret": round(sum(regrets) / len(regrets), 4) if regrets else None,
            "errors": sum(1 for r in rows if isinstance(r.get(label), dict) and "error" in r[label]),
        }
    per_k = {}
    for label in ("aligned", "fixed12"):
        per_k[label] = {}
        for turns in turns_list:
            cells = [r[label] for r in rows if r["k"] == turns
                     and isinstance(r.get(label), dict) and "error" not in r[label]]
            per_k[label][str(turns)] = {
                "n": len(cells),
                "matches": sum(1 for c in cells if c.get("matches_exact")),
            }

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "candidate-check.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": "sitin-candidate-check/1", "summary": summary,
                   "per_k": per_k, "rows": rows}, fh, ensure_ascii=False, indent=1)

    print(json.dumps(summary, ensure_ascii=False))
    print(json.dumps(per_k, ensure_ascii=False))
    for row in rows:
        aligned = row.get("aligned", {})
        if isinstance(aligned, dict) and aligned.get("matches_exact") is False:
            print("MISS k=%s chain=%s hand=%s exact=%s chose=%s regret=%s" % (
                row["k"], row["chain"], row["hand"], row["exact_best"],
                aligned.get("choice"), aligned.get("regret")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
