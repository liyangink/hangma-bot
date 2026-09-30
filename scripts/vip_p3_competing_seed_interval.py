"""新根逐种子成组重抽样；仅描述条件动作差的不确定性。"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def summarize(report: dict, *, repeats: int = 30_000,
              random_seed: int = 20260930) -> dict:
    """保留同自然牌山种子的多个观察根关联，重抽样不是赛事强度检验。"""

    if (report.get("scope") != "prelocked_competing_terminal_action_once_not_C_alg"
            or repeats < 100):
        raise ValueError("输入不是事前动作一次评价或重抽样次数不足")
    all_rows = report["rows"]
    seeds = sorted({row["seed"] for row in all_rows})
    if len(seeds) != report["seed_frame"][1] - report["seed_frame"][0] + 1:
        raise ValueError("新根自然牌山种子不连续或缺失")
    groups = {
        "all": all_rows,
        "response": [row for row in all_rows if row["phase"].startswith("response_")],
        "draw": [row for row in all_rows if row["phase"] == "draw"],
    }
    output = {}
    for name, rows in groups.items():
        by_seed: dict[int, list[dict]] = defaultdict(list)
        for row in rows:
            by_seed[row["seed"]].append(row)
        results = {"root_count": len(rows)}
        for ref in ("shape", "r18_frozen"):
            rng = random.Random(random_seed)
            means = []
            for _ in range(repeats):
                selected = rng.choices(seeds, k=len(seeds))
                gains = [row["paired_net_minus_shape_first"][ref]
                         for seed in selected for row in by_seed[seed]]
                if gains:
                    means.append(sum(gains) / len(gains))
            means.sort()
            results[ref] = {
                "lower_2_5_percent": means[int(0.025 * len(means))],
                "upper_97_5_percent": means[int(0.975 * len(means))],
            }
        output[name] = results
    return {
        "scope": "descriptive_seed_cluster_interval_not_natural_table_claim",
        "repeats": repeats, "random_seed": random_seed,
        "source_root_count": len(all_rows), "seed_count": len(seeds),
        "groups": output,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.evaluation.read_text(encoding="utf-8"))
    print(json.dumps(summarize(report), ensure_ascii=False,
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
