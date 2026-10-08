#!/usr/bin/env python3
"""候选门禁：把目标③的验收标准做成可执行脚本。

预登记阈值（运行前固定，不看结果修改；见下方 THRESHOLDS）：

1. 主指标：候选 − 基线 的**完整桌赛**桌内积分差，按同牌山根组（scenario_id）聚类自助 95% 区间；
2. 通过条件：点估计 > 0 且区间下界 > 0；
3. 第一名比例（严格口径）不退化：候选点估计 ≥ 基线 − 0.01；
4. 可靠性：超时 / 非法选择 / 降级 / 排除 全部为 0；
5. 可选 --expect-identical：用于影子类候选，要求两臂终局分逐项相等（零行为差异）。

用法：
  gate_candidate.py --baseline weighted_heuristic_v2 --candidate v2_hu_upgrade_v1 \
      --phase development --roots 32 --seed-start 1290000 --workers 8 \
      --out review/.../gate-hu-vs-v2-dev

本脚本只读模拟公开接口，不改变线上动作、生产枚举与默认配置。
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
import statistics
import gzip
import hashlib
import json
import random
import sys
import time
from dataclasses import asdict
import math
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, WORK.parent / 'big-hand-paths-2026-09-09')))

from lab import ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits
from run_tables import RecordingEngine
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.config import TournamentConfig, TimingConfig
from hangma_bot.offline.evaluate import (MatchExperiment, PolicyDeclaration, MatchSeedSpec,
                                         run_match_experiment, write_report_files)
from hangma_bot.offline.evaluation_results import write_results_jsonl
from hangma_bot.offline.evaluation_statistics import summarize_results
from hangma_bot.policy.balanced_shadow import V2BalancedShadowPolicy
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice

THRESHOLDS = {
    "mean_delta_gt": 0.0,          # 桌内积分差点估计必须为正
    "ci_lower_gt": 0.0,            # 聚类自助 95% 区间下界必须为正
    "first_rate_drop_max": 0.01,   # 第一名比例相对基线的允许退步上限
    "required_zero": ("timeouts", "illegal_choices", "fallbacks"),
    "excluded_max": 0,
    # 稳健性判据（round 15 新增）：均值为正**不足以**认证候选。
    # 重尾候选可以"均值 CI 下界 > 0"却完全无效——实测 v2_value_upgrade_v1 对 Tier-A
    # 的符号检验 p=0.773（正 98 / 负 94，就是掷硬币），但把它外推到 n=2900 时
    # "均值判据通过率"高达 87%，n=10000 时 100%。样本量越大越容易伪证。
    # 因此必须在**有效根**（差值非零）上做符号检验，并要求它显著偏向候选。
    "sign_test_max_p": 0.05,
    "min_informative_roots": 6,    # 精确检验在 n>=6 才可能达到 p<0.05（6:0 -> 0.031）
}
# 四个排列正好是循环群，且 initial_dealer 是**逻辑身份**下标、会被同一个排列映射到物理座位：
# 于是四次换座只是把同一场实验整体重新标号，被测策略与其对手的相对配置完全不变。
# 实测核验（1524 个根，100%）：一个根内 4 次换座的桌内积分差**逐位相同**。
# ⇒ 换座提供**零**额外统计信息，门禁的有效样本量就是根数；跑 4 次等于白烧 4 倍算力。
# 默认只跑 1 次换座，把省下的算力全部换成**更多根**（根数才是自由度）。
# 历史门禁（gate-*）都是 4 次换座跑的，其 freeze.json 的 seat_rotations 记录了这一点。
CYCLIC_ROTATIONS = ((0, 1, 2, 3), (1, 2, 3, 0), (2, 3, 0, 1), (3, 0, 1, 2))
# 真正的座位覆盖：含换位、互不构成循环移位，被测策略因此会落到不同物理座位。
# 用于座位敏感性检验（"换座到底有没有用"），不是默认。
DISTINCT_ROTATIONS = ((0, 1, 2, 3), (1, 0, 2, 3), (2, 3, 0, 1), (3, 2, 1, 0))
ROTATION_SETS = {'cyclic': CYCLIC_ROTATIONS, 'distinct': DISTINCT_ROTATIONS}


class ValuesWhenNeeded:
    """两支使用完全相同的规则分析装配。

    必须**常开**价值事实：按需开启（只在胡或已有爆头时）会让"一摸价值层"这类候选在普通
    听牌窗口拿不到路线事实、静默退化成 V2，从而把真实差异抹成 0——曾导致门禁把
    v2_value_upgrade_v1 误判为与基线完全相同（mean_delta=0、区间 [0,0]）。
    常开对两支一致，不引入比较偏差；代价只是规则分析耗时（策略侧实测 p99 ≈ 25ms）。
    """

    def __init__(self, rules):
        self.rules = rules

    def analyze(self, observation):
        return self.rules.analyze(observation, value_limits=ValueAnalysisLimits())


def build_policy(name):
    """按名称构造策略；离线运行必须注入逻辑时钟（否则增强分支每窗超时降级）。"""
    if name == 'weighted_heuristic_v2':
        return ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    if name == 'v2_hu_upgrade_v1':
        return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                 risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
    if name == 'v2_hu_upgrade_dealer_v2':
        from hangma_bot.policy.v2_hu_upgrade_dealer import (
            DEALER_WEIGHTS_V2, V2HuUpgradeDealerPolicy)
        return V2HuUpgradeDealerPolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                       risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN,
                                       dealer_weights=DEALER_WEIGHTS_V2)
    if name == 'v2_hu_upgrade_risk_v3':
        from hangma_bot.policy.hu_upgrade_calibration import (
            RISK_CELLS_V3, RISK_VERSION_V3, SAFETY_MARGIN_V3)
        return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS_V3,
                                 risk_version=RISK_VERSION_V3, safety_margin=SAFETY_MARGIN_V3)
    if name == 'v2_hu_upgrade_tierb_v3':
        from hangma_bot.policy.hu_upgrade_calibration import (
            RISK_CELLS_V3, RISK_VERSION_V3, SAFETY_MARGIN_V3)
        from hangma_bot.policy.hu_upgrade_tierb import HuUpgradeTierBPolicy
        return HuUpgradeTierBPolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS_V3,
                                    risk_version=RISK_VERSION_V3, safety_margin=SAFETY_MARGIN_V3)
    if name == 'v2_hu_upgrade_tierb_v1':
        from hangma_bot.policy.hu_upgrade_tierb import HuUpgradeTierBPolicy
        return HuUpgradeTierBPolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                    risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
    if name == 'v2_hu_upgrade_dealer_v1':
        from hangma_bot.policy.v2_hu_upgrade_dealer import V2HuUpgradeDealerPolicy
        return V2HuUpgradeDealerPolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                       risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
    if name == 'v2_value_upgrade_v1':
        from hangma_bot.policy.v2_value_upgrade import V2ValueUpgradePolicy
        return V2ValueUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                    risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
    if name == V2BalancedShadowPolicy.VERSION:
        return V2BalancedShadowPolicy(
            baseline=V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                       risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN),
            monotonic=lambda: 0)
    if name == 'weighted_heuristic_v2_white_guard':
        from hangma_bot.policy.white_discard_guard import WhiteDiscardGuardPolicy
        return WhiteDiscardGuardPolicy(ComparableHeuristicPolicyV2(monotonic=lambda: 0))
    if name == 'v2_hu_upgrade_white_guard_v1':
        # 2x2 析因的"等胡 x 护白"格：等胡要靠财神当燃料（爆头/财飘），
        # 因此护白与 Tier-A 在机制上互补——但两者同开从未被测过。
        from hangma_bot.policy.white_discard_guard import WhiteDiscardGuardPolicy
        return WhiteDiscardGuardPolicy(
            V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                              risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN))
    if name.startswith('v2_hu_upgrade_tight_m'):
        # **等胡轴的另一侧**：Tier-A 放宽侧（Tier-B 概率档）已否证为显著负；收紧侧从未测过。
        # 判据 conservative > gain * (1 + safety_margin)：Tier-A 的 floor >= 2 x gain，
        # 而 survival_floor >= 0.83 => 阈值上界约 1.66 x gain > 1.10 x gain，**恒松弛**
        # （这正是方向 B 空操作的原因）。把 margin 提到 ~0.6 以上，这个约束第一次真正咬合。
        margin = int(name.rsplit('m', 1)[1]) / 100.0
        return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                 risk_version=RISK_VERSION, safety_margin=margin)
    if name.startswith('calib-alias-'):
        # **零假设标定专用**（不进入任何候选）。四个不同名字指向行为完全相同的策略：
        # 同台测出的臂间差就只剩座位/分配伪影，用于证明竞技场本身无偏。
        # 若同名则会被聚成一个 stats 条目、净分恒 0——那样的"标定"什么都没检验。
        return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                 risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)
    raise ValueError('门禁未登记的策略：' + name)


def root_run(item):
    baseline, candidate, opponents, rotations, index, seed = item
    raw = HangmaRules(RuleConfig(RULESET, 1, False))
    rules_hash = compute_rules_hash(ROOT)
    config = TournamentConfig(1, 8, raw.config, TimingConfig(1, 1, 3))
    ids = [baseline, candidate, 'opp-1', 'opp-2', 'opp-3']
    policies = {baseline: build_policy(baseline), candidate: build_policy(candidate),
                **{pid: build_policy(name) for pid, name in zip(ids[2:], opponents)}}
    experiment = MatchExperiment(
        'matches', 'logical', PolicyDeclaration(baseline, baseline), PolicyDeclaration(candidate, candidate),
        tuple(PolicyDeclaration(pid, name) for pid, name in zip(ids[2:], opponents)), config,
        (MatchSeedSpec(seed, 'gate-{0}'.format(index)),), rotations, index % 4, (0, 0, 0, 0),
        simulation_version='simulation-v1', match_id_prefix='gate')
    engine = RecordingEngine(SimulationEngine(raw, rules_hash=rules_hash))
    out = asyncio.run(run_match_experiment(
        experiment, engine=engine, spec_factory=MatchSpec, choice_factory=SimulationChoice,
        policies_by_id=policies, rules=ValuesWhenNeeded(raw), rules_hash=rules_hash,
        now_monotonic=lambda: 0, wall_clock=None, budget_policy=BudgetPolicy()))
    return out.results, list(out.excluded)


def tested_seat_score(row, policy_id):
    """返回被测评策略所在实际座位的终局分；找不到返回 None。"""
    for seat, pid in enumerate(row.policy_ids_by_seat):
        if pid == policy_id:
            return None if row.scores_after is None else row.scores_after[seat]
    return None


def first_place(row, policy_id):
    """严格第一名：被测评座位分数严格高于其他三家。"""
    if row.scores_after is None:
        return None
    seat = next((s for s, pid in enumerate(row.policy_ids_by_seat) if pid == policy_id), None)
    if seat is None:
        return None
    mine = row.scores_after[seat]
    return all(mine > other for index, other in enumerate(row.scores_after) if index != seat)


def bootstrap_ci(values_by_root, reps=10000, seed=20260910):
    rng = random.Random(seed)
    roots = list(values_by_root)
    if len(roots) < 2:
        return [None, None]
    samples = []
    for _ in range(reps):
        picked = [rng.choice(roots) for _ in roots]
        flat = [value for root in picked for value in values_by_root[root]]
        samples.append(sum(flat) / len(flat))
    samples.sort()
    return [samples[int(reps * 0.025)], samples[int(reps * 0.975)]]


def sign_test(values):
    """在有效样本（差值非零）上做双侧**精确**符号检验；返回计数、z 与 p。

    只用非零根：候选多数根上根本不改变行为，把零算成"平局"会稀释检验。

    p 用精确二项分布（H0: p=0.5）而不是正态近似——小样本下正态近似不可靠，
    此前只能靠 min_informative_roots 硬性拦下 n<8，代价是把 6:0（精确 p=0.031）
    这种本就显著的结果判成"无法认证"。精确检验对任意 n 都成立，门槛因此可以放松。
    """

    pos = sum(1 for value in values if value > 0)
    neg = sum(1 for value in values if value < 0)
    informative = pos + neg
    if informative == 0:
        return dict(positive=0, negative=0, zero=len(values), zip=None, p=1.0)
    tail = sum(math.comb(informative, k) for k in range(0, min(pos, neg) + 1))
    p = min(1.0, 2.0 * tail * (0.5 ** informative))
    z = (pos - informative / 2) / math.sqrt(informative / 4)
    return dict(positive=pos, negative=neg, zero=len(values) - informative, zip=z, p=p)


def evaluate(results, baseline, candidate, expect_identical):
    pairs = {}
    for row in results:
        key = (row.scenario_id, tuple(row.seat_permutation))
        pairs.setdefault(key, {})[row.policy_ids_by_seat[row.seat_permutation[0]]] = row
    deltas, first_deltas, identical_mismatch = {}, {}, []
    counts = {'timeouts': 0, 'illegal_choices': 0, 'fallbacks': 0}
    baseline_first, candidate_first = [], []
    for (scenario, permutation), arms in pairs.items():
        base_row, cand_row = arms.get(baseline), arms.get(candidate)
        if base_row is None or cand_row is None:
            continue
        base_score = tested_seat_score(base_row, baseline)
        cand_score = tested_seat_score(cand_row, candidate)
        if base_score is None or cand_score is None:
            continue
        deltas.setdefault(scenario, []).append(cand_score - base_score)
        base_first = first_place(base_row, baseline)
        cand_first = first_place(cand_row, candidate)
        if base_first is not None and cand_first is not None:
            baseline_first.append(1 if base_first else 0)
            candidate_first.append(1 if cand_first else 0)
            first_deltas.setdefault(scenario, []).append((1 if cand_first else 0) - (1 if base_first else 0))
        if expect_identical and tuple(base_row.scores_after or ()) != tuple(cand_row.scores_after or ()):
            identical_mismatch.append({'scenario_id': scenario, 'seat_permutation': list(permutation)})
        for row in (base_row, cand_row):
            if row.runtime_counts is not None:
                for name in counts:
                    counts[name] += getattr(row.runtime_counts, name, 0)
    flat = [value for values in deltas.values() for value in values]
    mean_delta = sum(flat) / len(flat) if flat else None
    ci = bootstrap_ci(deltas)
    first_flat = [value for values in first_deltas.values() for value in values]
    first_delta = (sum(first_flat) / len(first_flat)) if first_flat else None
    root_values = [statistics.mean(values) for values in deltas.values()]
    ordered = sorted(root_values)
    trim = int(len(ordered) * 0.05)
    return dict(
        tables=len(flat), roots=len(deltas),
        median_delta=(statistics.median(root_values) if root_values else None),
        trimmed_mean_delta=(statistics.mean(ordered[trim:len(ordered) - trim])
                            if len(ordered) > 2 * trim and trim else
                            (statistics.mean(ordered) if ordered else None)),
        sign_test=sign_test(root_values),
        mean_delta=mean_delta, delta_ci95=ci,
        baseline_first_rate=(sum(baseline_first) / len(baseline_first)) if baseline_first else None,
        candidate_first_rate=(sum(candidate_first) / len(candidate_first)) if candidate_first else None,
        first_rate_delta=first_delta, runtime_counts=counts,
        identical_mismatches=identical_mismatch)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--phase', choices=['development', 'confirmation'], required=True)
    parser.add_argument('--roots', type=int, default=32)
    parser.add_argument('--seed-start', type=int, default=1290000)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--expect-identical', action='store_true')
    parser.add_argument('--rotations', type=int, default=1, choices=[1, 2, 3, 4],
                        help='换座次数；cyclic 集合的 4 个排列互为循环移位，实测与 1 次逐位同结果'
                             '（零信息），默认 1 以把算力换成更多根')
    parser.add_argument('--rotation-set', default='cyclic', choices=sorted(ROTATION_SETS),
                        help='cyclic=历史四换座（零信息）；distinct=含换位的真座位覆盖（座位敏感性检验用）')
    parser.add_argument('--opponents', action='append', default=[],
                        help='三名对手的策略名，可重复三次；缺省 3×weighted_heuristic_v2')
    parser.add_argument('--require-development-pass', default='',
                        help='确认阶段必填：已通过的开发阶段 gate.json；阈值或对照不一致则拒绝运行')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    development_reference = None
    if args.phase == 'confirmation' or args.require_development_pass:
        if not args.require_development_pass:
            raise SystemExit('确认阶段必须用 --require-development-pass 引用已通过的开发阶段门禁')
        reference_path = Path(args.require_development_pass)
        reference = json.loads(reference_path.read_text(encoding='utf-8'))
        reference_freeze = json.loads(
            (reference_path.parent / 'freeze.json').read_text(encoding='utf-8'))
        problems = []
        if not reference.get('passed'):
            problems.append('开发阶段门禁未通过')
        # 阈值经 JSON 往返后元组会变成列表，按同一序列化口径比较，避免假阳性。
        if reference_freeze.get('thresholds') != json.loads(json.dumps(THRESHOLDS)):
            problems.append('开发阶段阈值与当前脚本不一致')
        for key in ('baseline', 'candidate'):
            if reference_freeze.get(key) != getattr(args, key):
                problems.append('开发阶段 {0} 与当前不一致'.format(key))
        if reference_freeze.get('opponents') != (args.opponents or ['weighted_heuristic_v2'] * 3):
            problems.append('开发阶段对手池与当前不一致')
        if problems:
            raise SystemExit('拒绝运行确认阶段：' + '；'.join(problems))
        development_reference = dict(
            path=str(reference_path),
            source_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            seed_range=reference_freeze.get('seed_range'),
            mean_delta=reference.get('mean_delta'), delta_ci95=reference.get('delta_ci95'))
        print('确认阶段守卫通过，引用开发阶段门禁：', json.dumps(development_reference, ensure_ascii=False))
    directory = Path(args.out)
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    opponents = args.opponents or ['weighted_heuristic_v2'] * 3
    if len(opponents) != 3:
        raise ValueError('--opponents 必须给出三名（或省略使用缺省）')
    results, excluded = [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rotations = ROTATION_SETS[args.rotation_set][:args.rotations]
        jobs = [(args.baseline, args.candidate, tuple(opponents), rotations, i, args.seed_start + i)
                for i in range(args.roots)]
        for index, (rows, excluded_rows) in enumerate(pool.map(root_run, jobs)):
            results.extend(rows)
            excluded.extend(excluded_rows)
            if (index + 1) % 8 == 0:
                print('gate', index + 1, '/', args.roots, 'tables', len(results), flush=True)
    freeze = dict(schema='candidate-gate/1', phase=args.phase, baseline=args.baseline,
                  candidate=args.candidate, roots=args.roots,
                  seed_range=[args.seed_start, args.seed_start + args.roots - 1],
                  hands_per_table=8, seat_rotations=args.rotations,
                  seat_rotation_set=args.rotation_set,
                  initial_dealer='root_index % 4', ruleset=RULESET, you_cai_bi_kao=False,
                  opponents=list(opponents), thresholds=THRESHOLDS,
                  expect_identical=args.expect_identical,
                  development_reference=development_reference,
                  source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [_project_file(_PROJECT_ROOT, WORK / 'gate_candidate.py')]})
    (directory / 'freeze.json').write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + chr(10), encoding='utf-8')
    write_results_jsonl(directory / 'results.jsonl', results)
    summary = summarize_results(results, baseline_policy_id=args.baseline,
                                challenger_policy_id=args.candidate, tie_method='strict',
                                resample_seed=20260910, n_resamples=10000)
    write_report_files(directory, summary)
    verdict = evaluate(results, args.baseline, args.candidate, args.expect_identical)
    reliability_checks = {
        'reliability_zero': all(verdict['runtime_counts'][name] == 0 for name in THRESHOLDS['required_zero']),
        'excluded_zero': len(excluded) <= THRESHOLDS['excluded_max'],
    }
    if args.expect_identical:
        # 影子类候选的验收是"零行为差异"，不是"更强"：只查一致性 + 可靠性。
        checks = dict(reliability_checks, identical_arms=not verdict['identical_mismatches'])
    else:
        checks = dict(reliability_checks, **{
            'mean_delta_positive': verdict['mean_delta'] is not None
                                    and verdict['mean_delta'] > THRESHOLDS['mean_delta_gt'],
            'ci_lower_positive': verdict['delta_ci95'][0] is not None
                                 and verdict['delta_ci95'][0] > THRESHOLDS['ci_lower_gt'],
            'first_rate_not_worse': verdict['first_rate_delta'] is not None
                                    and verdict['first_rate_delta'] >= -THRESHOLDS['first_rate_drop_max'],
            'robust_not_heavy_tail': (
                verdict['sign_test']['positive'] + verdict['sign_test']['negative']
                >= THRESHOLDS['min_informative_roots']
                and verdict['sign_test']['positive'] > verdict['sign_test']['negative']
                and verdict['sign_test']['p'] < THRESHOLDS['sign_test_max_p']),
        })
    passed = all(checks.values())
    verdict.update(checks=checks, passed=passed, excluded=excluded[:20],
                   elapsed_seconds=time.monotonic() - started)
    (directory / 'gate.json').write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + chr(10), encoding='utf-8')
    print(json.dumps({key: verdict[key] for key in
                      ('tables', 'roots', 'mean_delta', 'delta_ci95', 'baseline_first_rate',
                       'candidate_first_rate', 'first_rate_delta', 'runtime_counts',
                       'checks', 'passed')}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
