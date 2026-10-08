"""两张真实完整桌检验新对手；A/C均R18，不能计新VIP强度。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
import gzip
import hashlib
import json
import random
import time
from dataclasses import asdict
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.offline.evaluate import MatchExperiment, MatchSeedSpec, run_match_experiment
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_sources import REPO_ROOT, source_manifest, write_code_snapshot
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditEngine, VipDevelopmentAuditPolicy
from hangma_bot.policy.route_vip_heuristic import VIP_ROUTE_HEURISTIC_SEED_SOURCE
from hangma_bot.simulation import MatchSpec, SimulationChoice
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import WORLD_SCHEMA

HERE = Path(__file__).resolve().parent


def save(path, value):
    """小收据只写新路径；中间进度件原子替换，旧实验不改写。"""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(raw)
    temporary.replace(path)


async def main():
    generation_path = _project_file(_PROJECT_ROOT, HERE.parent / 't48-v3-natural-highfan-joint-author-1/S01-generation.batch.json')
    batch = VipEohBatch.read(generation_path)
    out = _project_file(_PROJECT_ROOT, HERE / 'smoke-1')
    out.mkdir(exist_ok=False)
    manifest = source_manifest(('hangma_bot.offline.qualifier_opponents',))
    manifest[str(Path(__file__).relative_to(REPO_ROOT))] = {
        'bytes': Path(__file__).stat().st_size, 'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    write_code_snapshot(out, manifest)
    seed = random.SystemRandom().randrange(1 << 48, 1 << 63)
    plan = {'schema': 't49-opponent-engineering-smoke/1', 'seed': seed, 'root_id': 't49-proxy-smoke',
        'opponent_types_logical_1_2_3': ['normal_v0', 'r18', 'automatic_like'],
        'permutation': [0, 1, 2, 3], 'rounds': 8, 'initial_dealer_physical': 0,
        'initial_scores_physical': [0, 0, 0, 0], 'reserved_table_instances': 2,
        'step_limit': 10000, 'wall_clock_limit_seconds': 1800,
        'arm_A_and_C_algorithm': 'r18_integrated_positive_v2',
        'VIP_actual_score_calls': 0, 'strength_or_admission_claim': False,
        'source_manifest': manifest, 'generation_batch_sha256': hashlib.sha256(batch.raw).hexdigest()}
    save(out / 'START.json', plan)
    runtime = build_qualifier_runtime(batch, VIP_ROUTE_HEURISTIC_SEED_SOURCE,
                                    plan['opponent_types_logical_1_2_3'])
    # C另用已存在H3独立R18实例；本实验只验新对手机械，不使用VIP。
    challenger = runtime.declarations['H3']
    selected = [runtime.declarations[k] for k in ('A', 'Q1', 'Q2', 'Q3')] + [challenger]
    decisions, rows = [], []
    with gzip.open(out / 'decisions.jsonl.gz', 'wt', encoding='utf-8') as stream:
        def sink(row):
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
            stream.flush()
            decisions.append({k: row.get(k) for k in ('policy_id', 'phase', 'status', 'degraded_reasons', 'selected_action_key')})
        engine = VipDevelopmentAuditEngine(runtime.engine, settlement_sink=rows.append)
        engine.context = {'root_id': plan['root_id'], 'focal_physical_seat': 0, 'permutation': [0,1,2,3]}
        policies = {d.policy_id: VipDevelopmentAuditPolicy(runtime.policies_by_id[d.policy_id],
                    d.policy_id, lambda: dict(engine.context), sink) for d in selected}
        experiment = MatchExperiment('matches', 'logical', runtime.declarations['A'], challenger,
            tuple(runtime.declarations[f'Q{i}'] for i in range(1,4)), runtime.config,
            (MatchSeedSpec(seed, plan['root_id']),), ((0,1,2,3),), 0, (0,0,0,0),
            step_limit=plan['step_limit'], match_id_prefix='t49-opponent-smoke',
            simulation_version=WORLD_SCHEMA, input_sha256=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest(),
            source_namespace='hangma-simulation')
        started = time.perf_counter()
        outcome = await run_match_experiment(experiment, engine=engine, spec_factory=MatchSpec,
            choice_factory=lambda key, action: SimulationChoice(key, action), policies_by_id=policies,
            rules=runtime.rules, rules_hash=compute_rules_hash(REPO_ROOT), now_monotonic=lambda: 800.,
            wall_clock=None, budget_policy=BudgetPolicy(), source_kind='simulation',
            value_limits=batch.route_limits, strict_challenger=True)
    end_manifest = source_manifest(('hangma_bot.offline.qualifier_opponents',))
    end_manifest[str(Path(__file__).relative_to(REPO_ROOT))] = manifest[str(Path(__file__).relative_to(REPO_ROOT))]
    faults = [row for row in decisions if row['status'] != 'chosen' or any(
        'action_value_failed' in reason for reason in row['degraded_reasons'] or ())]
    counters = [asdict(v.runtime_counts) for _,v in outcome.match_records]
    complete = (len(outcome.results) == 2 and len(rows) == 16 and not outcome.excluded and not faults
        and all(v.status == 'complete' for _,v in outcome.match_records)
        and all(all(counts[k] == 0 for k in ('timeouts','illegal_choices','fallbacks','auto_actions','audit_missing')) for counts in counters)
        and manifest == end_manifest and time.perf_counter()-started <= plan['wall_clock_limit_seconds'])
    result = {'schema': 't49-opponent-smoke-result/1', 'engineering_complete': complete,
        'actual_started_table_instances': engine.started_table_instances, 'completed_hands': len(rows),
        'decision_windows': len(decisions), 'runtime_counts': counters, 'faults': faults,
        'excluded': list(outcome.excluded), 'source_stable': manifest == end_manifest,
        'duration_wall_seconds': time.perf_counter()-started, 'VIP_score_calls': 0,
        'strength_or_admission_claim': False, 'results': [r.to_json() for r in outcome.results],
        'policy_metadata': {k:runtime.policy_metadata[k] for k in ('A','H3','Q1','Q2','Q3')}}
    save(out / 'settlements.json', rows)
    save(out / 'match-outcomes.json', [{'match_id':k,'outcome':v.to_json()} for k,v in outcome.match_records])
    save(out / 'summary.json', result)
    print({k:result[k] for k in ('engineering_complete','actual_started_table_instances','completed_hands','decision_windows','runtime_counts','duration_wall_seconds')})
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
