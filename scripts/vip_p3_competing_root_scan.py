"""P3 全动作结果盲选根：冻结自然牌山上的行动前观察与合法动作。"""

from __future__ import annotations

import argparse
import hashlib
import json

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.serialization import observation_to_json
from hangma_bot.simulation import MatchSpec, SimulationEngine

from scripts.vip_p3_all_action_teacher import _selected_roots
from scripts.vip_p3_value_fit_probe import _shape_key


def scan(*, start_seed: int, seeds: int) -> dict:
    """只按冻结 shape 路径和当下玩家观察选择根，不查询动作后结局。"""

    if start_seed < 0 or seeds < 1:
        raise ValueError("全动作扫描种子范围无效")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    limits = ValueAnalysisLimits(max_expansions=8192)
    rows = []
    seen: set[str] = set()
    for seed in range(start_seed, start_seed + seeds):
        spec = MatchSpec(
            match_id=f"vip-p3-all-action-{seed}",
            scenario_id=f"vip-p3-all-action-{seed}",
            config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
            seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0),
        )
        for _, _, decision, tags in _selected_roots(
            engine, rules, engine.start(spec)
        ):
            observation = decision.observation
            root_id = hashlib.sha256(repr(observation).encode()).hexdigest()
            if root_id in seen:
                raise ValueError("全动作扫描出现重复玩家观察根")
            seen.add(root_id)
            analysis = rules.analyze(observation, value_limits=limits)
            if analysis.completeness is not RuleCompleteness.COMPLETE:
                raise ValueError("全动作扫描的行动前规则分析不完整")
            keys = [candidate.action_key for candidate in analysis.legal_candidates]
            rows.append({
                "seed": seed, "root_id": root_id, "tags": tags,
                "phase": observation.phase,
                "observation": observation_to_json(observation),
                "legal_action_keys": keys,
                "shape_first_action_key": _shape_key(analysis, observation.phase),
            })
    return {
        "scope": "pre_outcome_all_action_root_scan_not_strategy_value",
        "selection_method": "first_per_tag_under_shape_per_seed",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "reference": "shape", "start_seed": start_seed,
        "requested_seeds": seeds, "root_count": len(rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(scan(start_seed=args.start_seed, seeds=args.seeds),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
