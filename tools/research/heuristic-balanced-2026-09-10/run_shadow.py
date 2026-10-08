#!/usr/bin/env python3
"""影子多路线桌赛运行器（重建版）。

用途：把 `v2_balanced_shadow_v1` 与保底 `v2_hu_upgrade_v1` 放在同一牌山、同一换座
集合下跑完整桌赛。影子层只追加可审计的 Pareto 路线签名理由，不改变候选顺序，
因此本运行的第一个验收项是两支的终局分与动作逐项相等（零行为差异），第二个
验收项是路线签名覆盖率与频率分布。

产物（目录 <phase>/ 或 --out 指定）：
- freeze.json：本批的种子范围、换座集合、规则/策略声明与源码哈希；
- results.jsonl / report.json / report.md：完整桌赛强度统计（summarize_results）；
- hands.jsonl.gz：逐单局结果（用于同牌山对照核查）；
- changes.jsonl.gz：影子路线签名记录（喂给 summarize_shadow_signatures.py）；
- shadow-summary.json：`{roots, tables, changes, errors, shadow_notes}` 聚合；
- completion.json：耗时与运行计数。

边界：研究策略使用逻辑时钟，只验证运行链、事实覆盖与零行为差异；不是收益确认集，
不代表线上计时门禁或可用枚举。
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
from dataclasses import asdict
import gzip
import hashlib
import json
import time
from pathlib import Path

import sys

# 复用既有研究运行器（lab.py / run_tables.py）在同一研究目录内，避免复制第二套装配。
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, Path(__file__).resolve().parent.parent / 'big-hand-paths-2026-09-09')))

from lab import HERE, ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2, ValueAnalysisLimits
from run_tables import RecordingEngine
from hangma_bot.application.audit_codec import decision_request_to_json
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

BASE = 'v2_hu_upgrade_v1'
CAND = V2BalancedShadowPolicy.VERSION
WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')  # 本批产物与计划文档同目录，便于交接
SHADOW_MARK = '影子路线['


def upgrade_policy():  # 必须注入逻辑时钟：驱动以 now_monotonic=lambda:0 构造预算
    """与线上自由赛同一装配的等胡保底；影子层复用同一实例参数。"""
    return V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS, risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN)


class ValuesWhenNeeded:
    """仅在胡存在或已有爆头状态时补生产价值事实；四家采用相同分析装配。

    影子签名只需要普通牌效事实（普通/七对向听与有效牌），因此不因观测本候选
    而扩大价值搜索面；两支分支收到完全相同的规则分析。
    """

    def __init__(self, rules):
        self.rules = rules

    def analyze(self, observation):
        analysis = self.rules.analyze(observation)
        if observation.rule_state.baotou or any(c.action_key == 'hu' for c in analysis.legal_candidates):
            return self.rules.analyze(observation, value_limits=ValueAnalysisLimits())
        return analysis


class ShadowAudit:
    """记录影子层追加的路线签名；未来牌墙与对手暗牌不进入策略输入。"""

    def __init__(self, policy):
        self.policy = policy
        self.changes = []

    async def choose(self, request, budget):
        plan = await self.policy.choose(request, budget)
        note = plan.candidates[0].reasons[-1] if plan.candidates else ''
        if SHADOW_MARK in note:
            obs = request.observation
            self.changes.append(dict(
                game_id=obs.game_id, round_no=obs.round_no, seat=obs.seat,
                trigger_seq=request.trigger_seq,
                hand=[t.code for t in obs.my_hand],
                drawn=None if obs.drawn_tile is None else obs.drawn_tile.code,
                selected=plan.candidates[0].action_key,
                reason=note,
                request=decision_request_to_json(request)))
        return plan


def root_run(item):
    phase, index, seed = item
    raw = HangmaRules(RuleConfig(RULESET, 1, False))
    rules_hash = compute_rules_hash(ROOT)
    config = TournamentConfig(1, 8, raw.config, TimingConfig(1, 1, 3))
    ids = [BASE, CAND, 'opp-v2-1', 'opp-v2-2', 'opp-v2-3']
    policies = {
        BASE: ShadowAudit(upgrade_policy()),
        CAND: ShadowAudit(V2BalancedShadowPolicy(baseline=upgrade_policy(), monotonic=lambda: 0)),
        **{pid: ShadowAudit(ComparableHeuristicPolicyV2(monotonic=lambda: 0)) for pid in ids[2:]},
    }
    experiment = MatchExperiment(
        'matches', 'logical', PolicyDeclaration(BASE, BASE), PolicyDeclaration(CAND, CAND),
        tuple(PolicyDeclaration(pid, 'weighted_heuristic_v2') for pid in ids[2:]), config,
        (MatchSeedSpec(seed, f'shadow-{phase}-{index}'),),
        ((0, 1, 2, 3), (1, 2, 3, 0), (2, 3, 0, 1), (3, 0, 1, 2)), index % 4, (0, 0, 0, 0),
        simulation_version='simulation-v1', match_id_prefix='route-preserve')
    engine = RecordingEngine(SimulationEngine(raw, rules_hash=rules_hash))
    out = asyncio.run(run_match_experiment(
        experiment, engine=engine, spec_factory=MatchSpec, choice_factory=SimulationChoice,
        policies_by_id=policies, rules=ValuesWhenNeeded(raw), rules_hash=rules_hash,
        now_monotonic=lambda: 0, wall_clock=None, budget_policy=BudgetPolicy()))
    changes = [dict(change, policy_id=CAND) for change in policies[CAND].changes]
    return out.results, engine.hands, changes, list(out.excluded)


def verify_zero_difference(results):
    """同牌山对照：基线与影子的终局分必须逐项相等（影子只加观测）。"""
    by_key = {}
    for row in results:
        tested = row.policy_ids_by_seat[0]
        by_key[(row.scenario_id, tuple(row.seat_permutation), tested)] = row
    mismatches = []
    for (scenario, permutation, tested), row in by_key.items():
        if tested != CAND:
            continue
        base = by_key.get((scenario, permutation, BASE))
        if base is None:
            mismatches.append({'scenario_id': scenario, 'seat_permutation': permutation,
                               'issue': 'missing_baseline'})
            continue
        if tuple(row.scores_after or ()) != tuple(base.scores_after or ()):
            mismatches.append({'scenario_id': scenario, 'seat_permutation': permutation,
                               'baseline': list(base.scores_after or ()),
                               'candidate': list(row.scores_after or ())})
    return mismatches


def shadow_integrity(changes_path):
    """内联调用完整性校验；失败不掩盖，直接写进批次产物。"""
    sys.path.insert(0, str(WORK))
    import verify_shadow_integrity as integrity
    return integrity.verify(changes_path)


def run(args):
    directory = Path(args.out) if args.out else _project_file(_PROJECT_ROOT, WORK / f'shadow-{args.phase}')
    count, start = {
        'smoke': (1, 1190000),
        'signature': (8, 1193000),
        'development': (32, 1195000),
        'confirmation': (128, 1197000),
    }[args.phase]
    if args.roots:
        count, start = args.roots, args.seed_start
    directory.mkdir(parents=True, exist_ok=False)

    files = sorted(p for p in (_project_file(_PROJECT_ROOT, ROOT / 'src/hangma_bot')).rglob('*') if p.suffix in ('.py', '.c', '.h', '.so'))
    files += [_project_file(_PROJECT_ROOT, HERE / name) for name in ('lab.py', 'run_tables.py')]
    files += [_project_file(_PROJECT_ROOT, HERE.parent / 'heuristic-balanced-2026-09-10' / 'run_shadow.py')]
    freeze = dict(schema='shadow-tables/1', phase=args.phase, roots=count,
                  seed_range=[start, start + count - 1], hands_per_table=8, seat_rotations=4,
                  initial_dealer='root_index % 4', ruleset=RULESET, you_cai_bi_kao=False,
                  baseline=BASE, candidate=CAND, opponents=['weighted_heuristic_v2'] * 3,
                  value_scope='普通牌效事实；仅在胡存在或已有爆头时补生产价值事实（两支相同）',
                  scope='完整自然桌赛；影子层只追加路线签名理由，不改变候选顺序；逻辑时钟不代表线上计时门禁',
                  acceptance=['同牌山换座两支队终局分逐项相等', '影子签名覆盖率与频率分布入 shadow-summary.json'],
                  gate='本批不产生收益结论；有限多路线候选仍需开发集与独立确认分别通过',
                  source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in files if p.is_file()})
    (directory / 'freeze.json').write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + chr(10))

    results, hands, changes, excluded = [], [], [], []
    errors = []
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index, (rows, hand_rows, change_rows, excluded_rows) in enumerate(
                pool.map(root_run, [(args.phase, i, start + i) for i in range(count)])):
            results.extend(rows)
            hands.extend(hand_rows)
            changes.extend(change_rows)
            excluded.extend(excluded_rows)
            print(args.phase, index + 1, '/', count, 'shadow_notes', len(changes), flush=True)

    write_results_jsonl(directory / 'results.jsonl', results)
    for name, rows in (('hands', hands), ('changes', changes)):
        with gzip.open(directory / f'{name}.jsonl.gz', 'xt', encoding='utf8') as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + chr(10))

    summary = summarize_results(results, baseline_policy_id=BASE, challenger_policy_id=CAND,
                               tie_method='strict', resample_seed=20260910, n_resamples=10000)
    write_report_files(directory, summary)
    mismatches = verify_zero_difference(results)
    integrity_report = shadow_integrity(directory / 'changes.jsonl.gz')
    (directory / 'integrity.json').write_text(
        json.dumps(integrity_report, ensure_ascii=False, indent=2) + chr(10), encoding='utf-8')
    shadow_summary = dict(roots=count, tables=len(results), changes=len(changes), errors=errors,
                          zero_difference_mismatches=mismatches, shadow_notes=len(changes),
                          integrity_passed=integrity_report['passed'],
                          truncated_notes=integrity_report.get('truncated_notes'),
                          seed_range=[start, start + count - 1], phase=args.phase)
    (directory / 'shadow-summary.json').write_text(
        json.dumps(shadow_summary, ensure_ascii=False, indent=2) + chr(10))
    metadata = dict(elapsed_seconds=time.monotonic() - started, tables=len(results), hands=len(hands),
                    changes=len(changes), excluded=excluded, zero_difference_mismatches=len(mismatches),
                    runtime_totals={key: sum(asdict(r.runtime_counts)[key] for r in results)
                                    for key in asdict(results[0].runtime_counts)})
    (directory / 'completion.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + chr(10))
    for name, expected in freeze['source_sha256'].items():
        assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT / name)).read_bytes()).hexdigest() == expected, name
    print(json.dumps(metadata, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['smoke', 'signature', 'development', 'confirmation'], required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--roots', type=int, default=0, help='覆盖根数（配合 --seed-start 使用）')
    parser.add_argument('--seed-start', type=int, default=0)
    parser.add_argument('--out', default='', help='输出目录（默认 review/big-hand-paths-2026-09-09/shadow-<phase>）')
    run(parser.parse_args())
