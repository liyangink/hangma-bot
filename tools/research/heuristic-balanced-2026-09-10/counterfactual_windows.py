#!/usr/bin/env python3
"""自然窗口的反事实筛选链：捕获（capture）→ 分支续打（branch）→ 分层汇总（summarize）。

背景：`export_hand` 导出的是**单局起点**牌山（payload.seq = 本局起始 seq）加上本局事件
历史，不是中期世界快照；因此本链在捕获阶段同时记录**动作前缀**（自本局开始到目标窗口
的全部四家动作），分支阶段从同一份单局起点重放前缀，再在目标窗口落下不同动作。

三个子命令：

- capture：跑自然桌赛（我方座位用 v2_balanced_shadow_v1，其余三家 V2），在**每局至多一个**
  满足条件的摸牌窗口上记录案例：单局起点 world 行、动作前缀、目标窗口键、保底动作、
  候选动作、路线签名与类别。每局只取一个窗口，保证前缀语义唯一。
- branch：对每个案例从同一单局起点重建两个世界，重放同一前缀后在目标窗口分别落下
  保底/候选动作，其后四家全部由 V2 续打到单局终局。世界完全确定（牌山在起点行内），
  因此每案例一对分支即为一个确定样本，不需要重复抽样。
- summarize：按类别聚合差值（候选 − 保底），按根聚类自助给出区间。

边界：本链只用于离线筛选有限多路线候选；不改变线上动作、生产枚举与默认配置。
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
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
import random
import sys
import time
from dataclasses import replace
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, WORK.parent / 'big-hand-paths-2026-09-09')))

from lab import ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.hand_analysis import any_tile_win  # noqa: E402
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness, ValueCoverage
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.serialization import (action_from_json, action_to_json,
                                             window_key_from_json, window_key_to_json)
from hangma_bot.kernel.config import TournamentConfig, TimingConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.balanced_shadow import V2BalancedShadowPolicy, _pareto, _route_signature
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN
from hangma_bot.policy.interface import DecisionBudget, DecisionRequest
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice

# 诊断计数：仅在核对分类口径时使用，正常路径不读取。
_CAPTURE_COUNTS = {}


def _bump(name):
    _CAPTURE_COUNTS[name] = _CAPTURE_COUNTS.get(name, 0) + 1


TEST_SEAT = 0
BASE = 'v2_hu_upgrade_v1'
WHITE_DISCARD_KEY = 'discard:白'  # 财神（白）弃牌动作键；由规则字段传递而非硬编码规则
CAND = V2BalancedShadowPolicy.VERSION


def upgrade_policy():
    """逻辑时钟必须注入：驱动与分支续打都以逻辑预算比较策略截止。"""
    return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                             risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)


def request_for(rules, decision, game_id):
    """只交付可见观察与规则事实；分析开启生产价值事实以便等胡保底正常工作。"""
    obs = decision.observation
    analysis = rules.analyze(obs, value_limits=ValueAnalysisLimits())
    return DecisionRequest(
        observation=obs,
        competition=CompetitionContext(game_id, None, None, None, None, (), 0),
        rules=analysis, decision_id=game_id, trigger_seq=obs.snapshot_seq,
        window_key=decision.window_key, rejected_attempts=())


def claim_candidates(analysis):
    """响应窗口里可比较的候选：吃/碰/杠 与 过；都要求带完整手牌进度事实。"""
    out = []
    for candidate in analysis.legal_candidates:
        head = candidate.action_key.split(':')[0]
        if head not in ('chi', 'peng', 'gang', 'pass'):
            continue
        facts = route_facts(candidate)
        if facts is None:
            continue
        out.append((candidate, facts, head))
    return out


def classify_claim(candidates):
    """按鸣牌相对过牌的最优向听关系分类。

    - 鸣牌更快：存在鸣牌候选的普通型向听严格小于过牌；
    - 鸣牌听牌：存在鸣牌候选直接达到向听 0；
    - 同向听：最优向听相同；
    - 过更快：所有鸣牌候选都比过牌更远。
    """
    pass_sig = next((sig for _, sig, head in candidates if head == 'pass'), None)
    claims = [(sig, head) for _, sig, head in candidates if head != 'pass']
    if pass_sig is None or not claims:
        return None
    best_claim = min(sig[0] for sig, _ in claims)
    if best_claim == 0 and pass_sig[0] > 0:
        return '鸣牌听牌'
    if best_claim < pass_sig[0]:
        return '鸣牌更快'
    if best_claim == pass_sig[0]:
        return '同向听'
    return '过更快'


def classify(frontier):
    """按七对相对普通型向听的关系给窗口分类（与签名分层工具同口径）。

    七对事实缺失（中局有副露）时返回 '无七对事实'，仍保留案例供只用普通型
    向听与有效牌的规则评估；完全没有路线事实时返回 None。
    """
    signatures = [route_facts(c) for c in frontier]
    signatures = [s for s in signatures if s is not None]
    if not signatures:
        return None
    if all(signature[1] is None for signature in signatures):
        return '无七对事实'
    near = any(pairs < standard for standard, pairs, _ in signatures)
    far = any(pairs > standard for standard, pairs, _ in signatures)
    same = any(pairs == standard for standard, pairs, _ in signatures)
    if near:
        return '七对更近' if not (same or far) else '七对更近(混合)'
    if far and same:
        return '混合'
    if far:
        return '普通更近'
    return '同距离'


def action_of(plan):
    return plan.candidates[0].action


def _signature(candidate):
    return _route_signature(candidate)


def route_facts(candidate):
    """返回 (普通型向听, 七对向听或 None, 未见有效牌估计)；事实不足返回 None。

    中局有副露时七对向听为 None（七对仅门清有效），此时仍可用普通型路线做
    标准向听与有效牌的比较；不能用综合向听反推。
    """
    facts = candidate.facts
    if facts is None or facts.fact_kind is not CandidateFactKind.HAND_PROGRESS:
        return None
    if facts.completeness is not RuleCompleteness.COMPLETE:
        return None
    if facts.replacement_draw_unknown:
        return None
    standard = getattr(facts, 'standard_shanten_after', None)
    if standard is None:
        return None
    pairs = getattr(facts, 'seven_pairs_shanten_after', None)
    outs = sum(tile.remaining_estimate for tile in facts.useful_tiles)
    return standard, pairs, outs


def frontier_of(candidates):
    """保留不被支配的弃牌候选：普通向听不更差、有效牌不更少、七对不更远。

    七对事实缺失时按 (普通向听, 有效牌) 两维比较，不把缺失当成更远。
    """
    known = []
    for candidate in candidates:
        facts = route_facts(candidate)
        if facts is not None:
            known.append((candidate, facts))
    result = []
    for candidate, sig in known:
        dominated = False
        for other_candidate, other in known:
            if other_candidate is candidate:
                continue
            if other[0] > sig[0] or other[2] < sig[2]:
                continue
            if sig[1] is not None and other[1] is not None and other[1] > sig[1]:
                continue
            if sig[1] is None or other[1] is None:
                if other == sig:
                    continue
            dominated = True
            break
        if not dominated:
            result.append(candidate)
    return tuple(result)


def feed_risk(table, tile, remaining):
    """查表估计该弃牌被鸣的概率：类别×墙余带优先，退化为类别，再退化为总体。"""
    if not table:
        return None
    honors = ('东', '南', '西', '北', '中', '发', '白')
    category = 'honor' if tile in honors else ('terminal' if len(tile) == 2 and tile[0] in '19' else 'middle')
    bands = ((80, 'opening'), (64, '64_79'), (40, '40_63'), (0, 'le39'))
    band = next(name for threshold, name in bands if remaining >= threshold)
    cell = (table.get('cells') or {}).get(category + '|' + band)
    if cell and cell.get('n', 0) >= 30:
        return cell['rate']
    category_row = (table.get('category_rates') or {}).get(category)
    if category_row and category_row.get('n', 0) >= 30:
        return category_row['rate']
    return table.get('claim_rate')


def baotou_ready_map(obs, candidates):
    """每个弃牌候选扣除该张后，暗牌是否"摸任意一张种类即胡"（爆头就绪）。

    判定用规则侧唯一来源 hand_analysis.any_tile_win：摸前 13−3×副露 张暗牌 + 任意一张都成胡。
    摸牌相位的 my_hand 不含当前摸牌，必须并入池子（否则"弃刚摸的牌"会 remove 失败）。
    事实不足的候选不进入结果；本函数只看决策时可见事实。
    """

    hand = list(obs.my_hand)
    if obs.drawn_tile is not None:
        hand.append(obs.drawn_tile)
    meld_count = len(obs.melds[obs.seat])
    out = {}
    for candidate in candidates:
        if not isinstance(candidate.action, Discard):
            continue
        after = list(hand)
        try:
            after.remove(candidate.action.tile)
        except ValueError:
            continue
        if len(after) != 13 - 3 * meld_count:
            continue
        out[candidate.action_key] = any_tile_win(tuple(sorted(after)), meld_count)
    return out


def select_by_rule(rule, frontier, all_candidates, baseline_key, context=None):
    """按规则选一个替代动作；规则只看决策时可见事实。

    白板族规则用**全量合法弃牌集**：支配过滤会把"弃白"隐藏（弃白通常减少有效牌），
    而白板决策要比较的正是这笔代价是否值得。其余规则用 Pareto 前沿。
    所有规则都不选基线动作本身；返回 (候选动作键, 说明) 或 (None, 原因)。
    """
    context = context or {}
    pass_seat = context.get('seat', TEST_SEAT)
    if rule.startswith('dealer_') and not context.get('is_dealer'):
        return None, 'not_dealer_window'
    if rule.startswith('nondealer_') and context.get('is_dealer'):
        return None, 'not_nondealer_window'
    source = all_candidates if (rule.startswith('white_') or rule.startswith('spend_white')
                               or rule == 'always_spend_white') else frontier
    baseline = next((c for c in source if c.action_key == baseline_key), None)
    if baseline is None:
        return None, 'baseline_not_in_frontier'
    base_sig = route_facts(baseline)
    if base_sig is None:
        return None, 'baseline_signature_unknown'
    pool = []
    for candidate in source:
        if candidate.action_key == baseline_key:
            continue
        sig = route_facts(candidate)
        if sig is None:
            continue
        pool.append((candidate, sig))
    base_standard, base_pairs, base_outs = base_sig

    def route_nearer(sig):
        return sig[1] is not None and sig[1] < sig[0]

    def keeps_outs(sig, ratio=0.95):
        return base_outs and sig[2] >= base_outs * ratio

    pass_candidate = next((item for item in pool if item[0].action_key == 'pass'), None)
    claim_pool = [(candidate, sig) for candidate, sig in pool if candidate.action_key.split(':')[0] in ('chi', 'peng', 'gang')]
    if rule == 'always_pass':
        if pass_candidate is None:
            return None, 'no_pass_candidate'
        return pass_candidate[0].action_key, rule
    if rule.startswith('claim_'):
        if pass_candidate is None or not claim_pool:
            return None, 'no_claim_alternative'
        pass_sig = pass_candidate[1]
        if rule in ('claim_by_value', 'claim_by_shanten'):
            # 多鸣牌候选选择：现有价值层只覆盖弃牌，本规则把同一"一摸价值质量"口径
            # 用到吃/碰/杠之间的取舍上；只在不损进度的候选里挑。
            eligible = [(candidate, sig) for candidate, sig in claim_pool if sig[0] <= pass_sig[0]]
            if not eligible:
                return None, 'no_claim_without_progress_loss'
            if rule == 'claim_by_shanten':
                eligible.sort(key=lambda item: (item[1][0], -item[1][2], item[0].action_key))
                return eligible[0][0].action_key, rule
            scored = []
            for candidate, sig in eligible:
                mass = 0.0
                facts = getattr(candidate, 'value_facts', None)
                if facts is not None and facts.coverage is ValueCoverage.COMPLETE:
                    for route in facts.routes:
                        if route.support != 'conditional_witness' or route.shanten != 0:
                            continue
                        score = route.conditional_settlement.score_delta[pass_seat]
                        if not isinstance(score, (int, float)) or score <= 0:
                            continue
                        mass += sum(tile.remaining_estimate * float(score) for tile in route.useful_tiles
                                    if tile.remaining_estimate > 0)
                scored.append((mass, sig, candidate))
            if not scored or max(item[0] for item in scored) <= 0:
                return None, 'no_value_witness'
            scored.sort(key=lambda item: (-item[0], item[1][0], -item[1][2], item[2].action_key))
            return scored[0][2].action_key, rule
        if rule == 'claim_if_standard_improves':
            picked = [item for item in claim_pool if item[1][0] < pass_sig[0]]
        elif rule == 'claim_if_tenpai':
            picked = [item for item in claim_pool if item[1][0] == 0]
        elif rule == 'claim_if_no_outs_loss':
            picked = [item for item in claim_pool
                      if item[1][0] <= pass_sig[0] and pass_sig[2] and item[1][2] >= pass_sig[2] * 0.95]
        else:
            raise ValueError('未知规则 ' + rule)
        if not picked:
            return None, 'no_rule_match'
        picked.sort(key=lambda item: (item[1][0], -item[1][2], item[0].action_key))
        return picked[0][0].action_key, rule

    if rule.startswith('white_') or rule.startswith('spend_white') or rule == 'always_spend_white':
        white_entries = [item for item in pool if item[0].action_key == WHITE_DISCARD_KEY]
        others = [item for item in pool if item[0].action_key != WHITE_DISCARD_KEY]
        baseline_is_white = baseline_key == WHITE_DISCARD_KEY
        if rule == 'always_spend_white':
            picked = list(white_entries)
        elif rule == 'spend_white_if_faster':
            picked = [item for item in white_entries if item[1][0] < base_standard]
        elif rule == 'spend_white_if_tenpai':
            picked = [item for item in white_entries if item[1][0] == 0 and base_standard > 0]
        elif rule == 'white_spend_no_standard_cost':
            picked = [item for item in white_entries if item[1][0] <= base_standard]
        elif rule == 'white_keep_unless_faster':
            # 只在保底弃白时检验"护白"：取不损向听的非白弃牌。
            if not baseline_is_white:
                return None, 'baseline_not_white_discard'
            picked = [item for item in others if item[1][0] <= base_standard]
        elif rule == 'white_keep_no_outs_loss':
            if not baseline_is_white:
                return None, 'baseline_not_white_discard'
            picked = [item for item in others
                      if item[1][0] <= base_standard and base_outs and item[1][2] >= base_outs * 0.95]
        else:
            raise ValueError('未知规则 ' + rule)
        if not picked:
            return None, 'no_rule_match'
        picked.sort(key=lambda item: (item[1][0], -item[1][2], item[0].action_key))
        return picked[0][0].action_key, rule

    if rule in ('min_feed_risk', 'max_feed_risk'):
        table = context.get('feed_table')
        if not table:
            return None, 'feed_table_missing'
        candidates = [item for item in pool
                      if item[1][0] <= base_standard and keeps_outs(item[1])]
        if not candidates:
            return None, 'no_rule_match'
        ranked = []
        for candidate, sig in candidates:
            head, _, tile = candidate.action_key.partition(':')
            if head != 'discard':
                continue
            risk = feed_risk(table, tile, context.get('remaining'))
            if risk is None:
                continue
            ranked.append((risk, sig, candidate))
        if not ranked:
            return None, 'no_discard_alternative'
        ranked.sort(key=lambda item: (item[0] if rule == 'min_feed_risk' else -item[0],
                                      item[1][0], -item[1][2], item[2].action_key))
        return ranked[0][2].action_key, rule

    if rule == 'frontier_second':
        chosen = pool[0] if pool else None
        return (chosen[0].action_key, 'frontier_second') if chosen else (None, 'no_alternative')
    if rule == 'route_nearer_any':
        picked = [item for item in pool if route_nearer(item[1])]
    elif rule == 'route_nearer_keeps_outs':
        picked = [item for item in pool if route_nearer(item[1]) and keeps_outs(item[1])]
    elif rule == 'pairs_nearer_keeps_outs':
        picked = [item for item in pool if item[1][1] is not None and base_pairs is not None
                  and item[1][1] < base_pairs and keeps_outs(item[1])]
    elif rule in ('standard_keeps_outs_only', 'dealer_standard_keeps_outs',
                  'nondealer_standard_keeps_outs'):
        picked = [item for item in pool if item[1][0] <= base_standard and keeps_outs(item[1])]
    elif rule == 'standard_no_worse_keeps_outs':
        picked = [item for item in pool if item[1][0] <= base_standard and keeps_outs(item[1])]
    elif rule == 'baotou_ready_keeps_outs':
        ready = context.get("baotou_ready") or {}
        picked = [item for item in pool
                  if ready.get(item[0].action_key)
                  and item[1][0] <= base_standard and keeps_outs(item[1])]
    elif rule == 'pairs_nearer_no_standard_cost':
        picked = [item for item in pool if item[1][1] is not None and base_pairs is not None
                  and item[1][1] < base_pairs and item[1][0] <= base_standard]
    else:
        raise ValueError('未知规则 ' + rule)
    if not picked:
        return None, 'no_rule_match'
    # 同规则内取七对向听最小、其次未见有效牌最多；确定性排序。
    picked.sort(key=lambda item: (item[1][1] if item[1][1] is not None else 9, -item[1][2], item[0].action_key))
    return picked[0][0].action_key, rule


def capture_root(item):
    """跑一根自然桌赛并收集可反事实的案例；每局至多一个窗口。"""
    index, seed, max_cases, windows, per_hand = item
    rules = HangmaRules(RuleConfig(RULESET, 1, False))
    rules_hash = compute_rules_hash(ROOT)
    engine = SimulationEngine(rules, rules_hash=rules_hash)
    shadow = V2BalancedShadowPolicy(baseline=upgrade_policy(), monotonic=lambda: 0)
    opponent = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    config = TournamentConfig(1, 8, rules.config, TimingConfig(1, 1, 3))
    game_id = 'cf-root-{0}'.format(index)
    spec = MatchSpec(match_id=game_id, scenario_id=game_id, config=config, seed=seed,
                     initial_dealer=index % 4, initial_scores=(0, 0, 0, 0))
    world = engine.start(spec)
    cases = []
    feed_samples = []
    pending_discards = []
    hand_payloads = {}
    prefix = []
    case_counts = {}
    last_wall = {}
    steps = 0
    while steps < 20000:
        steps += 1
        frame = engine.frame(world)
        if frame.blocked_reason:
            raise RuntimeError(frame.blocked_reason)
        if frame.final_scores is not None:
            break
        choices = []
        for decision in frame.decisions:
            obs = decision.observation
            if obs.round_no not in hand_payloads:
                row = engine.export_hand(world, obs.round_no)
                hand_payloads[obs.round_no] = row
                prefix = []  # 新的一局：动作前缀从空开始
            if obs.seat == TEST_SEAT:
                plan = asyncio.run(shadow.choose(request_for(rules, decision, game_id), DecisionBudget(10, 11, 12)))
            else:
                plan = asyncio.run(opponent.choose(request_for(rules, decision, game_id), DecisionBudget(10, 11, 12)))
            action = action_of(plan)
            kind = None
            whites_in_hand = sum(1 for tile in obs.my_hand if tile.code == "白")
            # F-1：爆头就绪窗口必须**先分类后接受**，因此这一支要提前做规则分析
            # （合法弃牌集只能由 RuleAnalysis 给出，不能自行拼）。
            early_analysis = None
            if obs.phase == "draw" and "baotou_ready" in windows:
                early_analysis = rules.analyze(obs, value_limits=ValueAnalysisLimits())
            if obs.phase == "draw":
                _bump("draw")
                _bump("draw_seat0" if obs.seat == TEST_SEAT else "draw_other")
                if "baotou_ready" in windows:
                    ready = baotou_ready_map(obs, early_analysis.legal_candidates)
                    if any(ready.values()):
                        _bump("ready_true")
                        if obs.seat == TEST_SEAT:
                            _bump("ready_true_seat0")
                    kind = "draw" if any(ready.values()) else None
                elif "white" in windows:
                    # 白板族只收本人手上持白的摸牌窗口：决策点就是"护白还是用白"。
                    kind = 'draw' if whites_in_hand >= 1 else None
                elif 'draw' in windows:
                    kind = 'draw'
            elif obs.phase in ('response_peng', 'response_chi') and 'claim' in windows:
                kind = 'claim'
            spread_ok = (obs.round_no not in last_wall
                         or last_wall[obs.round_no] - obs.remaining_tile_count >= 8)
            if (obs.seat == TEST_SEAT and kind is not None and spread_ok
                    and case_counts.get(obs.round_no, 0) < per_hand
                    and len(cases) < max_cases):
                analysis = early_analysis or rules.analyze(obs, value_limits=ValueAnalysisLimits())
                if kind == "draw":
                    frontier = frontier_of([c for c in analysis.legal_candidates
                                            if isinstance(c.action, Discard)])
                    label = classify(frontier)
                    pool = list(frontier)
                else:
                    claim_pool = claim_candidates(analysis)
                    label = classify_claim(claim_pool)
                    pool = [candidate for candidate, _, _ in claim_pool]
                chosen_rule = next((c for c in analysis.legal_candidates
                                    if c.action_key == plan.candidates[0].action_key), None)
                projected_followup = (chosen_rule.facts.best_followup_discard
                                      if chosen_rule is not None and chosen_rule.facts is not None
                                      else None)
                # baotou_ready 族的接受条件与其它族不同：它关心的是"有就绪候选可选"，
                # 而"前沿 >=2"与"有分层标签"是为路线族设的，对本族无意义——曾因此把
                # 捕获密度从 0.70 例/根压到 0.09，导致误判方向不值得做。
                if kind == "baotou_ready":
                    pool = [c for c in analysis.legal_candidates if isinstance(c.action, Discard)]
                    accept = len(pool) >= 2
                else:
                    accept = label is not None and len(pool) >= 2
                if accept:
                    alternatives = [c for c in pool if c.action_key != plan.candidates[0].action_key]
                    if alternatives:
                        case_counts[obs.round_no] = case_counts.get(obs.round_no, 0) + 1
                        last_wall[obs.round_no] = obs.remaining_tile_count
                        cases.append(dict(
                            window_kind=kind,
                            case_id='{0}-r{1}-s{2}'.format(game_id, obs.round_no, obs.snapshot_seq),
                            root=game_id, seed=seed, round_no=obs.round_no,
                            window_key=window_key_to_json(decision.window_key),
                            my_hand=[t.code for t in obs.my_hand],
                            drawn=None if obs.drawn_tile is None else obs.drawn_tile.code,
                            remaining=obs.remaining_tile_count,
                            whites_in_hand=whites_in_hand,
                            baotou=bool(obs.rule_state.baotou),
                            chain_count=int(obs.rule_state.chain_count),
                            label=label,
                            projected_followup=projected_followup,
                            baseline_action_key=plan.candidates[0].action_key,
                            baseline_action=action_to_json(plan.candidates[0].action),
                            candidate_action_key=alternatives[0].action_key,
                            candidate_action=action_to_json(alternatives[0].action),
                            frontier=[dict(action_key=c.action_key, signature=list(route_facts(c)))
                                      for c in pool],
                            prefix=[dict(window_key=window_key_to_json(k), action=action_to_json(a))
                                    for k, a in prefix],
                            hand_row=hand_payloads[obs.round_no],
                        ))
            chosen_key = plan.candidates[0].action_key
            head, _, tile = chosen_key.partition(':')
            if head == 'discard':
                # 上一条弃牌的响应窗口已经过去：未匹配到鸣牌即记为未被鸣。
                for item in pending_discards:
                    if item['seat'] == TEST_SEAT:
                        feed_samples.append(dict(item, claimed=item.get('claimed', False),
                                                 claim_kind=item.get('claim_kind')))
                pending_discards = [dict(seat=obs.seat, tile=tile,
                                         wall=obs.remaining_tile_count,
                                         hand_row=obs.round_no)]
            elif head in ('chi', 'peng', 'gang') and tile:
                # 吃牌动作键形如 chi:7t,8t,9t，被吃的牌是其中一张；碰/杠为单张。
                wanted = set(tile.split(','))
                for item in reversed(pending_discards):
                    if item['tile'] in wanted and item['seat'] != obs.seat:
                        item['claimed'] = True
                        item['claim_kind'] = head
                        item['claimer'] = obs.seat
                        break
            choices.append(SimulationChoice(decision.window_key, action))
            prefix.append((decision.window_key, action))
        world = engine.advance(world, frame.revision, tuple(choices))
    for item in pending_discards:
        if item['seat'] == TEST_SEAT:
            feed_samples.append(dict(item, claimed=item.get('claimed', False),
                                     claim_kind=item.get('claim_kind')))
    return cases, steps, feed_samples


def _window_key(payload):
    return window_key_from_json(payload)


def _action(payload):
    return action_from_json(payload)


def branch_case(case, engine, policy, rule, feed_table=None):
    """从同一单局起点重放前缀，再在目标窗口按规则选路，其后全部由 V2 续打。

    基线臂 = 影子保底策略当时的实际选择；规则臂 = 在同一观察上按规则重新选出的动作。
    规则未命中时本案例记为 no_rule_match，不产生差值。
    """
    rules = engine.rules
    results = {}
    target = _window_key(case['window_key'])
    replay = {_window_key(item['window_key']): _action(item['action']) for item in case['prefix']}
    arms = {'baseline': _action(case['baseline_action']), 'candidate': None}
    rule_key, rule_note = None, None
    for arm in ('baseline', 'candidate'):
        world = engine.from_replay(case['hand_row'])
        target_action = arms[arm]
        # 一帧可能同时包含多个待决窗口，必须整帧推进；目标窗口出现的那一帧才替换动作。
        for _ in range(20000):
            frame = engine.frame(world)
            if frame.blocked_reason:
                raise RuntimeError(frame.blocked_reason)
            at_target = any(d.window_key == target for d in frame.decisions)
            if at_target and arm == 'candidate' and target_action is None:
                obs = next(d.observation for d in frame.decisions if d.window_key == target)
                analysis = rules.analyze(obs, value_limits=ValueAnalysisLimits())
                if case.get('window_kind', 'draw') == 'claim':
                    frontier = tuple(candidate for candidate, _, _ in claim_candidates(analysis))
                    all_candidates = frontier
                else:
                    discards = tuple(c for c in analysis.legal_candidates
                                     if isinstance(c.action, Discard) and route_facts(c) is not None)
                    frontier = frontier_of(discards)
                    all_candidates = discards
                dealer_seat = (case.get('hand_row') or {}).get('initial', {}).get('dealer_seat')
                context = {"seat": obs.seat,
                           "is_dealer": dealer_seat is not None and obs.seat == dealer_seat,
                           "remaining": obs.remaining_tile_count,
                           "feed_table": feed_table,
                           # F-1：爆头就绪按候选预先算好，规则只消费事实。
                           "baotou_ready": baotou_ready_map(obs, all_candidates)}
                rule_key, rule_note = select_by_rule(rule, frontier, all_candidates,
                                                     case['baseline_action_key'], context)
                if rule_key is None:
                    return dict(baseline=results.get('baseline'), candidate=None,
                                rule_key=None, rule_note=rule_note)
                target_action = next(c.action for c in all_candidates if c.action_key == rule_key)
            choices = []
            for decision in frame.decisions:
                if decision.window_key == target:
                    choices.append(SimulationChoice(decision.window_key, target_action))
                elif not at_target:
                    if decision.window_key not in replay:
                        raise RuntimeError('前缀缺少窗口 ' + str(decision.window_key))
                    choices.append(SimulationChoice(decision.window_key, replay[decision.window_key]))
                else:
                    plan = asyncio.run(policy.choose(
                        request_for(rules, decision, case['root']), DecisionBudget(10, 11, 12)))
                    choices.append(SimulationChoice(decision.window_key, action_of(plan)))
            world = engine.advance(world, frame.revision, tuple(choices))
            if at_target:
                break
        else:
            raise RuntimeError('重放前缀未到达目标窗口')
        if arm == 'candidate':
            results['rule_key'] = rule_key
            results['rule_note'] = rule_note
        for _ in range(20000):
            frame = engine.frame(world)
            if frame.blocked_reason:
                raise RuntimeError(frame.blocked_reason)
            if frame.final_scores is not None:
                row = engine.export_hand(world, case['round_no'])
                results[arm] = dict(score=frame.final_scores[TEST_SEAT], winner=row['winner_seat'],
                                    fan=row['fan'], details=list(row['details']))
                break
            choices = []
            for decision in frame.decisions:
                plan = asyncio.run(policy.choose(request_for(rules, decision, case['root']), DecisionBudget(10, 11, 12)))
                choices.append(SimulationChoice(decision.window_key, action_of(plan)))
            world = engine.advance(world, frame.revision, tuple(choices))
        else:
            raise RuntimeError('分支续打超过步数上限')
    return results


def branch_root(item):
    rule, payload, cases, feed_table = item
    engine = SimulationEngine(HangmaRules(RuleConfig(RULESET, 1, False)))
    policy = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    rows = []
    for case in cases:
        outcome = branch_case(case, engine, policy, rule, feed_table)
        row = dict(case_id=case['case_id'], root=case['root'], label=case['label'], rule=rule,
                   window_kind=case.get('window_kind', 'draw'),
                   round_no=case['round_no'], remaining=case['remaining'],
                   baseline_action=case['baseline_action_key'],
                   action_differs=outcome.get('rule_key') not in (None, case['baseline_action_key']),
                   frontier=case['frontier'],
                   rule_key=outcome.get('rule_key'), rule_note=outcome.get('rule_note'),
                   baseline=outcome.get('baseline'), candidate=outcome.get('candidate'))
        if outcome.get('candidate') is not None and outcome.get('baseline') is not None:
            row['delta'] = outcome['candidate']['score'] - outcome['baseline']['score']
        rows.append(row)
    return rows


def cmd_capture(args):
    directory = Path(args.out) if args.out else _project_file(_PROJECT_ROOT, WORK / 'counterfactual-cases')
    directory.mkdir(parents=True, exist_ok=False)
    windows = args.windows if args.windows else ['draw']
    started = time.monotonic()
    all_cases = []
    all_feed = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index, (cases, steps, feed) in enumerate(pool.map(
                capture_root, [(i, args.seed_start + i, args.max_cases, windows, args.per_hand)
                               for i in range(args.roots)])):
            all_cases.extend(cases)
            all_feed.extend(feed)
            print('capture', index + 1, '/', args.roots, 'cases', len(all_cases),
                  'feed', len(all_feed), flush=True)
    freeze = dict(schema='counterfactual-cases/1', roots=args.roots,
                  seed_range=[args.seed_start, args.seed_start + args.roots - 1],
                  hands_per_table=8, test_seat=TEST_SEAT, baseline=BASE, candidate=CAND,
                  windows=windows,
                  opponents=['weighted_heuristic_v2'] * 3,
                  scope='自然窗口案例；每局至多一个；不含未来牌墙信息进入策略',
                  source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [_project_file(_PROJECT_ROOT, WORK / 'counterfactual_windows.py')]})
    (directory / 'freeze.json').write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + chr(10), encoding='utf-8')
    with gzip.open(directory / 'cases.jsonl.gz', 'xt', encoding='utf-8') as stream:
        for case in all_cases:
            stream.write(json.dumps(case, ensure_ascii=False) + chr(10))
    with gzip.open(directory / 'feed-samples.jsonl.gz', 'xt', encoding='utf-8') as stream:
        for item in all_feed:
            stream.write(json.dumps(item, ensure_ascii=False) + chr(10))
    summary = dict(cases=len(all_cases), feed_samples=len(all_feed),
                   elapsed_seconds=time.monotonic() - started,
                   labels=dict(_count(case['label'] for case in all_cases)),
                   roots=args.roots, seed_range=freeze['seed_range'])
    (directory / 'capture.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + chr(10), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def _count(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def cmd_branch(args):
    cases = [json.loads(line) for line in gzip.open(args.cases, 'rt', encoding='utf-8')]
    by_root = {}
    for case in cases:
        by_root.setdefault(case['root'], []).append(case)
    rules = args.rule if args.rule else ['frontier_second']
    out = Path(args.out) if args.out else _project_file(_PROJECT_ROOT, WORK / ('counterfactual-branches-' + '-'.join(rules) + '.jsonl.gz'))
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        feed_table = json.loads(Path(args.feed_table).read_text(encoding='utf-8')) if args.feed_table else None
        jobs = [(rule, index, group, feed_table) for rule in rules
                for index, group in sorted(by_root.items())]
        for index, result in enumerate(pool.map(branch_root, jobs)):
            rows.extend(result)
            print('branch', index + 1, '/', len(jobs), 'rows', len(rows), flush=True)
    with gzip.open(out, 'xt', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + chr(10))
    matched = sum(1 for row in rows if row.get('candidate') is not None)
    print(json.dumps(dict(cases=len(cases), rules=rules, rows=len(rows), matched=matched,
                          output=str(out)), ensure_ascii=False), flush=True)


def cmd_summarize(args):
    rows = [json.loads(line) for line in gzip.open(args.branches, 'rt', encoding='utf-8')]
    rows = [row for row in rows if row.get('delta') is not None]
    if args.differing_only:
        rows = [row for row in rows if row.get('action_differs')]
    by_label = {}
    for row in rows:
        by_label.setdefault(row['rule'] + '/' + row['label'], []).append(row)
    summary = {}
    for label, items in sorted(by_label.items()):
        deltas = [item['delta'] for item in items]
        by_root = {}
        for item in items:
            by_root.setdefault(item['root'], []).append(item['delta'])
        rng = random.Random(20260910)
        roots = list(by_root)
        boot = []
        for _ in range(10000):
            picked = [rng.choice(roots) for _ in roots]
            flat = [value for root in picked for value in by_root[root]]
            boot.append(sum(flat) / len(flat))
        boot.sort()
        summary[label] = dict(
            cases=len(items), mean=sum(deltas) / len(deltas),
            ci95=[boot[250], boot[9749]],
            positive=sum(1 for value in deltas if value > 0),
            zero=sum(1 for value in deltas if value == 0),
            negative=sum(1 for value in deltas if value < 0),
            roots=len(by_root))
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('capture')
    capture.add_argument('--roots', type=int, default=32)
    capture.add_argument('--seed-start', type=int, default=1200000)
    capture.add_argument('--max-cases', type=int, default=4)
    capture.add_argument('--per-hand', type=int, default=1,
                         help='每局最多取几个窗口（相邻窗口墙余至少差 8，避免全挤在开局）')
    capture.add_argument('--workers', type=int, default=4)
    capture.add_argument('--out', default='')
    capture.add_argument('--windows', action='append', default=[], choices=['draw', 'claim', 'white', 'baotou_ready'],
                         help='捕获窗口种类，可重复；缺省 draw')
    capture.set_defaults(func=cmd_capture)
    branch = sub.add_parser('branch')
    branch.add_argument('--cases', required=True)
    branch.add_argument('--workers', type=int, default=4)
    branch.add_argument('--rule', action='append', default=[],
                        help='规则名，可重复；缺省只用 frontier_second')
    branch.add_argument('--feed-table', default='', help='喂牌风险表 JSON（min_feed_risk/max_feed_risk 规则使用）')
    branch.add_argument('--out', default='')
    branch.set_defaults(func=cmd_branch)
    summarize = sub.add_parser('summarize')
    summarize.add_argument('--branches', required=True)
    summarize.add_argument('--differing-only', action='store_true',
                           help='只统计规则动作与保底不同的样本（真实改选）')
    summarize.set_defaults(func=cmd_summarize)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
