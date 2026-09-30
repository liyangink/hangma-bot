"""在新模拟单局的每个动作窗口核对 VIP 全部合法根的机械投影。

运行：.venv/bin/python scripts/vip_p2_root_canary.py --start-seed 41 --seeds 30
完整世界仅供模拟器推进；根投影只接收当前座位的 PlayerObservation。
这是根单步与同次结算的覆盖审计，不证明未来事件模型或独立策略强度。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Chi, Discard, Gang, Hu, Pass, Peng
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine


_ORDER = (Hu, Gang, Peng, Chi, Discard, Pass)


def audit(*, start_seed: int, seeds: int, max_steps: int = 500) -> dict:
    """逐窗登记合法根与故障，并用确定性的合法动作推进整单局。"""

    if start_seed < 0 or seeds < 1 or max_steps < 1:
        raise ValueError("种子和步数范围无效")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    limits = ValueAnalysisLimits(max_expansions=8192)
    counts: Counter[str] = Counter()
    failures: list[dict] = []
    for seed in range(start_seed, start_seed + seeds):
        spec = MatchSpec(
            match_id=f"vip-p2-root-{seed}",
            scenario_id=f"vip-p2-root-{seed}",
            config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
            seed=seed,
            initial_dealer=0,
            initial_scores=(0, 0, 0, 0),
        )
        world = engine.start(spec)
        for step in range(max_steps):
            frame = engine.frame(world)
            if frame.blocked_reason is not None:
                failures.append({"seed": seed, "step": step, "kind": "simulator_blocked",
                                 "reason": frame.blocked_reason})
                break
            if frame.final_scores is not None:
                counts["completed_hands"] += frame.completed_hands
                break
            choices = []
            for decision in frame.decisions:
                observation = decision.observation
                # 由公开规则分析入口同时附同源结算和条件根，复核策略实际接线。
                analysis = rules.analyze(observation, route_limits=limits)
                roots = analysis.conditional_roots
                if roots is None:
                    raise ValueError("显式请求条件根后规则分析仍返回未请求状态")
                counts["windows"] += 1
                counts[f"window_{observation.phase}"] += 1
                counts["legal_roots"] += len(roots)
                if (analysis.completeness.value != "complete"
                        or tuple(root.action_key for root in roots)
                        != tuple(item.action_key for item in analysis.legal_candidates)):
                    failures.append({"seed": seed, "step": step,
                                     "seat": observation.seat,
                                     "kind": "analysis_or_root_identity"})
                for root in roots:
                    if root.gap_kind is not None:
                        counts[f"gap_{root.gap_kind.value}"] += 1
                        failures.append({
                            "seed": seed, "step": step, "seat": observation.seat,
                            "phase": observation.phase, "action_key": root.action_key,
                            "kind": root.gap_kind.value,
                            "issues": [issue.reason for issue in root.issues],
                        })
                candidate = min(
                    analysis.legal_candidates,
                    key=lambda item: (
                        next(index for index, kind in enumerate(_ORDER)
                             if isinstance(item.action, kind)),
                        item.action_key,
                    ),
                )
                counts[f"chosen_{type(candidate.action).__name__}"] += 1
                choices.append(SimulationChoice(decision.window_key, candidate.action))
            world = engine.advance(world, frame.revision, tuple(choices))
        else:
            failures.append({"seed": seed, "kind": "step_limit", "limit": max_steps})
    return {
        "scope": "P2_root_projection_only_not_conditional_chain_or_strength",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "start_seed": start_seed,
        "seeds": seeds,
        "counts": dict(sorted(counts.items())),
        "failure_count": len(failures),
        "failure_examples": failures[:20],
    }


def main() -> None:
    """输出确定性 JSON，存在根/模拟故障时以非零状态退出。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=41)
    parser.add_argument("--seeds", type=int, default=30)
    args = parser.parse_args()
    report = audit(start_seed=args.start_seed, seeds=args.seeds)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["failure_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
