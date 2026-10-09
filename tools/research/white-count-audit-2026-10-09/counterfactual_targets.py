#!/usr/bin/env python3
"""反事实重放的分叉目标计算：从已捕获面板标出售核窗与其替代弃牌。

口径：资格窗=实持≤1白、phase=draw、全合法根为弃牌、墙余>20（与探针一致）。
替代动作=同最小综合向听距离候选中支持核（speedof，生产口径 standard_useful）
最大者；若已等于父版首选则该窗不是卖核窗。对照组=父版首选已是最优支持核的
资格窗，强制父版自己的第二名。只读面板，输出分叉目标清单 JSON。
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

SPEEDCAP, SPEEDREF, VARREF, LINKCAP = 4.8, 12.0, 4.0, 2.0


def stockof(slot, waiting):
    cap = waiting["unseen_capacities"][slot]
    ev = waiting["unseen_evidence"][slot]
    if ev == "exact" and cap is not None:
        return float(cap)
    if ev == "conservative" and cap is not None and cap > 0:
        return float(cap)
    return 0.75


def summaryof(codes, codeindex, stock):
    mass, width, seen = 0.0, 0, set()
    for code in codes:
        if code in seen:
            continue
        seen.add(code)
        cell = stock[codeindex[code]]
        if cell > 0:
            mass += min(cell, LINKCAP)
            width += 1
    return mass, width


def speedof(mass, width):
    return SPEEDCAP * mass / (SPEEDREF + mass) * width / (VARREF + width) if width else 0.0


def candidate_facts(view):
    codeindex = {c: i for i, c in enumerate(view["tile_order"])}
    nodes = {n["node_key"]: n for n in view["nodes"]}
    facts = {}
    for action in view["actions"]:
        node = nodes[action["node_key"]]
        waiting = node.get("waiting")
        if not waiting:
            continue
        structure = waiting["structure"]
        std, sev = structure["standard_shanten"], structure["seven_pairs_shanten"]
        if std is None and sev is None:
            continue
        combined = min(x for x in (std, sev) if x is not None)
        stock = [stockof(i, waiting) for i in range(len(waiting["unseen_capacities"]))]
        codes = waiting.get("standard_useful_codes")
        core = None if codes is None else speedof(*summaryof(codes, codeindex, stock))
        facts[action["action_key"]] = (combined, core, std, sev)
    return facts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default="artifacts/white-gap-step0/panel-rf1-001")
    parser.add_argument("--out", required=True)
    parser.add_argument("--per-seed", type=int, default=10, help="每种子最多抽多少分叉")
    args = parser.parse_args()

    views = {}
    for line in gzip.open(Path(args.panel) / "views.jsonl.gz", "rt"):
        rec = json.loads(line)
        views[rec["view_sha256"]] = rec["view"]
    rows = [json.loads(line) for line in gzip.open(Path(args.panel) / "decisions.jsonl.gz", "rt")]
    rows = [r for r in rows if "decision_id" in r]

    targets = {"core_selling": [], "control": []}
    counts = {"eligible": 0, "core_selling": 0, "control_pool": 0, "skipped_no_view": 0}
    per_seed = {}
    for occurrence, row in enumerate(rows):
        legal = row.get("legal_action_keys") or []
        if (row.get("phase") != "draw" or row.get("white_count", 9) > 1
                or not legal or any(not k.startswith("discard:") for k in legal)):
            continue
        wall = (row.get("observation") or {}).get("remaining_tile_count")
        if wall is None or wall <= 20:
            continue
        counts["eligible"] += 1
        capture = ((row.get("scoring_execution") or {}).get("input_capture") or {})
        view = views.get(capture.get("view_sha256"))
        if view is None:
            counts["skipped_no_view"] += 1
            continue
        facts = candidate_facts(view)
        if not facts or any(v[1] is None for v in facts.values()):
            continue
        best_combined = min(v[0] for v in facts.values())
        tied = {k: v for k, v in facts.items() if v[0] == best_combined}
        alt = max(tied, key=lambda k: tied[k][1])
        selected = row.get("selected_action_key")
        seed = int(row["match_id"].rsplit("-", 1)[1])
        entry = {"occurrence": occurrence, "seed": seed, "decision_id": row["decision_id"],
                 "selected": selected, "forced": alt,
                 "whites": row.get("white_count"),
                 "core_selected": round(facts[selected][1], 4) if selected in facts else None,
                 "core_forced": round(tied[alt][1], 4),
                 "std_selected": facts.get(selected, (None,))[0] if selected in facts else None,
                 "std_forced": tied[alt][2]}
        if alt != selected and (selected not in facts or tied[alt][1] > facts[selected][1] + 1e-9):
            counts["core_selling"] += 1
            targets["core_selling"].append(entry)
        else:
            counts["control_pool"] += 1
            ranked = row.get("candidates") or []
            if len(ranked) >= 2 and ranked[1].get("action_key") != selected:
                targets["control"].append({**entry, "forced": ranked[1]["action_key"],
                                           "control_kind": "runner_up"})

    # 分层抽样：每种子按类别均匀取，控制重放成本。
    picked = {"core_selling": [], "control": []}
    per_seed_counts = {}
    for kind in ("core_selling", "control"):
        for entry in targets[kind]:
            key = (entry["seed"], kind)
            if per_seed_counts.get(key, 0) >= args.per_seed:
                continue
            per_seed_counts[key] = per_seed_counts.get(key, 0) + 1
            picked[kind].append(entry)

    output = {"counts": counts, "per_seed_cap": args.per_seed,
              "total_forks": sum(len(v) for v in picked.values()), "targets": picked}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=1))
    print(json.dumps({"counts": counts, "forks": {k: len(v) for k, v in picked.items()},
                      "by_seed_whites": {f'{e["seed"]}/{e["whites"]}w': 1 for e in picked["core_selling"]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
