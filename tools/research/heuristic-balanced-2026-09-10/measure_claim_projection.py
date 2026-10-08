#!/usr/bin/env python3
"""方向 1 前置证明：吃碰候选压缩是否丢掉高价值后续弃牌。

机制：`candidate_facts._best_followup` 按 (向听, -有效牌, 牌序) 从全部合法后续弃牌中
选**唯一**一条并据此组装吃碰候选事实，不比较番值与一摸价值。本脚本在同一天然窗口上
比较：投影后续弃牌（吃碰候选所见）与**一摸价值最优**后续弃牌（按 Σ 未见×条件结算）。

不改规则层：只在吃碰窗口记录投影值，落子后再读该窗口的全部合法弃牌与价值事实。
判据（P3 前置条件）：若投影与价值最优不同、且投影被价值最优在 (向听, 有效牌) 上支配，
说明压缩确实丢掉了高价值且可识别的分支。
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

import argparse
import asyncio
import collections
import gzip
import json
import sys
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, WORK.parent / 'big-hand-paths-2026-09-09')))

from lab import RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.serialization import action_from_json, window_key_from_json
from hangma_bot.policy.interface import DecisionBudget
import counterfactual_windows as cf


def value_mass(candidate, seat):
    """一摸价值质量：Σ(未见张数 × 条件结算中本人的净得分)；无见证返回 None。"""
    facts = candidate.value_facts
    if facts is None or not facts.routes:
        return None
    total = 0.0
    seen = False
    for route in facts.routes:
        delta = route.conditional_settlement.score_delta[seat]
        for tile in route.useful_tiles:
            total += tile.remaining_estimate * delta
            seen = True
    return total if seen else None


def measure_case(case, engine, policy):
    """重放前缀 → 落子吃碰 → 在本人下一个窗口比较投影弃牌与价值最优弃牌。"""
    rules = engine.rules
    target = cf._window_key(case['window_key'])
    replay = {cf._window_key(item['window_key']): cf._action(item['action']) for item in case['prefix']}
    world = engine.from_replay(case['hand_row'])
    action = cf._action(case['baseline_action'])
    for _ in range(20000):
        frame = engine.frame(world)
        if frame.blocked_reason:
            raise RuntimeError(frame.blocked_reason)
        at_target = any(d.window_key == target for d in frame.decisions)
        choices = []
        for decision in frame.decisions:
            if decision.window_key == target:
                choices.append(cf.SimulationChoice(decision.window_key, action))
            elif not at_target:
                if decision.window_key not in replay:
                    raise RuntimeError('前缀缺少窗口')
                choices.append(cf.SimulationChoice(decision.window_key, replay[decision.window_key]))
            else:
                plan = asyncio.run(policy.choose(
                    cf.request_for(rules, decision, case['root']), DecisionBudget(10, 11, 12)))
                choices.append(cf.SimulationChoice(decision.window_key, cf.action_of(plan)))
        world = engine.advance(world, frame.revision, tuple(choices))
        if at_target:
            break
    # 落子吃碰后，本人下一个决策窗口（出牌）
    for _ in range(20000):
        frame = engine.frame(world)
        if frame.blocked_reason or frame.final_scores is not None:
            return None
        mine = [d for d in frame.decisions if d.observation.seat == cf.TEST_SEAT]
        if mine:
            decision = mine[0]
            obs = decision.observation
            analysis = rules.analyze(obs, value_limits=ValueAnalysisLimits())
            cands = [c for c in analysis.legal_candidates if isinstance(c.action, Discard)]
            plan = asyncio.run(policy.choose(
                cf.request_for(rules, decision, case['root']), DecisionBudget(10, 11, 12)))
            chosen = cf.action_of(plan)
            chosen_key = chosen.code if hasattr(chosen, 'code') else None
            rows = []
            for candidate in cands:
                sig = cf.route_facts(candidate)
                mass = value_mass(candidate, obs.seat)
                rows.append(dict(action_key=candidate.action_key,
                                 tile=candidate.action_key.split(':', 1)[-1],
                                 standard=None if sig is None else sig[0],
                                 pairs=None if sig is None else sig[1],
                                 outs=None if sig is None else sig[2],
                                 mass=mass))
            return dict(round_no=obs.round_no, remaining=obs.remaining_tile_count,
                        projected=case.get('projected_followup'),
                        chosen=candidate_key_of(chosen), rows=rows)
        choices = []
        for decision in frame.decisions:
            plan = asyncio.run(policy.choose(
                cf.request_for(rules, decision, case['root']), DecisionBudget(10, 11, 12)))
            choices.append(cf.SimulationChoice(decision.window_key, cf.action_of(plan)))
        world = engine.advance(world, frame.revision, tuple(choices))
    return None


def candidate_key_of(action):
    head = type(action).__name__.lower()
    if head == 'discard':
        return 'discard:' + action.tile.code
    return head


def main(path, output):
    rules = HangmaRules(RuleConfig(RULESET, 1, False))
    engine = cf.SimulationEngine(rules)
    policy = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        cases = [json.loads(line) for line in handle if line.strip()]
    stats = collections.Counter()
    gaps = []
    details = []
    for case in cases:
        if case.get('window_kind') != 'claim' or not case.get('projected_followup'):
            continue
        row = measure_case(case, engine, policy)
        if row is None:
            stats['窗口不可用'] += 1
            continue
        stats['已测量'] += 1
        with_mass = [item for item in row['rows'] if item['mass'] is not None]
        if not with_mass:
            stats['无一摸价值见证'] += 1
            continue
        stats['有一摸价值见证'] += 1
        best_mass = max(item['mass'] for item in with_mass)
        argmax = [item for item in with_mass if item['mass'] == best_mass]
        projected = [item for item in row['rows'] if item['tile'] == row['projected']]
        stats['投影不在合法集'] += 0 if projected else 1
        stats['投影恰为价值最优'] += 1 if any(item in argmax for item in projected) else 0
        if projected and not any(item in argmax for item in projected):
            stats['投影非价值最优'] += 1
            mass_proj = projected[0]['mass']
            if mass_proj is not None and best_mass > 0:
                gaps.append((best_mass - mass_proj) / best_mass)
            best = argmax[0]
            dominated = (projected[0]['standard'] is not None and best['standard'] is not None
                         and best['standard'] <= projected[0]['standard']
                         and best['outs'] is not None and projected[0]['outs'] is not None
                         and best['outs'] >= projected[0]['outs'])
            stats['其中被价值最优支配(向听不更差/有效牌不更少)'] += 1 if dominated else 0
            details.append(dict(case_id=case['case_id'], round_no=row['round_no'],
                                remaining=row['remaining'], projected=row['projected'],
                                projected_mass=mass_proj, best=best['action_key'],
                                best_mass=best_mass, dominated=bool(dominated)))
        stats['策略实际选择=投影'] += 1 if row['chosen'] == 'discard:' + str(row['projected']) else 0
        stats['策略实际选择≠投影'] += 1 if row['chosen'] != 'discard:' + str(row['projected']) else 0
    summary = dict(cases=len(cases), stats=dict(stats),
                   mean_relative_gap=(sum(gaps) / len(gaps)) if gaps else None,
                   gap_samples=len(gaps), samples=details[:200])
    rendered = json.dumps(summary, ensure_ascii=False, indent=2) + chr(10)
    if output:
        Path(output).write_text(rendered, encoding='utf-8')
    print(rendered[:4000])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cases', type=Path)
    parser.add_argument('--output')
    args = parser.parse_args()
    main(args.cases, args.output)
