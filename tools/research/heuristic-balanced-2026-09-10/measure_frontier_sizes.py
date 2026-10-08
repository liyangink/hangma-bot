#!/usr/bin/env python3
"""测量影子层口径下的 Pareto 前沿规模（是否触发 8 条截断）。

影子层的 _route_signature 要求普通型与七对向听都存在，因此其前沿是候选集合的
子集；本脚本按同一口径统计前沿规模分布与截断发生率。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
import collections
import sys
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, WORK.parent / 'big-hand-paths-2026-09-09')))

from lab import ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.config import TournamentConfig, TimingConfig
from hangma_bot.policy.balanced_shadow import _pareto
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice
import counterfactual_windows as cf


def main(roots=8, seed_start=1280000):
    rules = HangmaRules(RuleConfig(RULESET, 1, False))
    engine = SimulationEngine(rules, rules_hash=compute_rules_hash(ROOT))
    policy = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    sizes = collections.Counter()
    windows = 0
    for index in range(roots):
        seed = seed_start + index
        spec = MatchSpec(match_id='frontier-{0}'.format(index), scenario_id='frontier-{0}'.format(index),
                         config=TournamentConfig(1, 8, rules.config, TimingConfig(1, 1, 3)),
                         seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0))
        world = engine.start(spec)
        for _ in range(20000):
            frame = engine.frame(world)
            if frame.final_scores is not None:
                break
            for decision in frame.decisions:
                obs = decision.observation
                if obs.seat != 0 or obs.phase != 'draw':
                    continue
                analysis = rules.analyze(obs, value_limits=ValueAnalysisLimits())
                discards = [c for c in analysis.legal_candidates if isinstance(c.action, Discard)]
                frontier = _pareto(discards)
                if frontier:
                    windows += 1
                    sizes[len(frontier)] += 1
            choices = []
            for decision in frame.decisions:
                plan = asyncio.run(policy.choose(cf.request_for(rules, decision, 'frontier'),
                                                 cf.DecisionBudget(10, 11, 12)))
                choices.append(SimulationChoice(decision.window_key, cf.action_of(plan)))
            world = engine.advance(world, frame.revision, tuple(choices))
    over = sum(v for k, v in sizes.items() if k > 8)
    print('窗口', windows, '规模分布', dict(sorted(sizes.items())),
          '超过 8 条', over, '占比 %.2f%%' % (100.0 * over / max(1, windows)))


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8,
         int(sys.argv[2]) if len(sys.argv) > 2 else 1280000)
