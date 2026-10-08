"""当前main纯Python装配计时，区分研究原生时限与实际集成时限。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

import run_grouped as grouped
base = grouped.base
HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1/actual-main-bounded-1')
ROOT = _PROJECT_ROOT


async def execute():
    plan, helper, cases, freeze, prior = grouped.check()
    labels = plan['modes']['grouped']
    OUT.mkdir(exist_ok=False)
    sys.path[:0] = [str(_project_file(_PROJECT_ROOT, ROOT / 'src'))]
    from hangma_bot.application.deadline import BudgetPolicy, SystemClock
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy, VipRouteProjectionLimits
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.policy import route_vip_heuristic, route_heuristic_view
    assert Path(route_vip_heuristic.__file__).resolve().is_relative_to(_project_file(_PROJECT_ROOT, ROOT / 'src'))
    inputs = {str(p): base.sha(p) for p in (Path(__file__), Path(route_vip_heuristic.__file__),
        Path(route_heuristic_view.__file__), helper.AUTHOR / 'S02-model-output/candidate.py')}
    batch = VipEohBatch.read(helper.AUTHOR / 'AUTHOR-BATCH.json')
    source = (helper.AUTHOR / 'S02-model-output/candidate.py').read_text()
    limits = VipRouteProjectionLimits(**asdict(batch.projection_limits) | {'max_replacement_depth': 1})
    base.save(_project_file(_PROJECT_ROOT, OUT / 'START.json'), {'max_choose': 8, 'frozen_files': inputs,
        'projection_limits': asdict(limits), 'native_research_overlay_used': False,
        'new_authors_worlds_tables': 0, 'online_admission': False})
    costs = dict.fromkeys(helper.COUNTERS, 0)
    rows, issues = [], []
    policy = RouteVipHeuristicPolicy(batch.rule_config, source=source,
        max_operations=batch.max_operations, projection_limits=limits)
    helper.OUT = OUT
    with (_project_file(_PROJECT_ROOT, OUT / 'ACTUAL-INPUTS.jsonl.gz')).open('x+b') as stream:
        capture = ScoringInputCapture(stream, limits=ScoringInputCaptureLimits.from_json(freeze['capture_limits']))
        executor = helper.CaptureExecutor(policy.executor, capture, costs, 'direct')
        policy.executor = executor
        for ordinal, label in enumerate(labels, 1):
            obs = observation_from_json(cases[label]['observation'])
            key = window_key_from_json(cases[label]['window_key'])
            executor.label = label
            begin = time.monotonic()
            budget = BudgetPolicy().build(begin, 1.0 if obs.phase.startswith('response_') else 3.0)
            row = {'label': label, 'status': 'not_scored'}
            try:
                costs['rule_attempts'] += 1
                rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                request = DecisionRequest(obs, CompetitionContext('T132-main-bounded', None, None, None, None, (), 0),
                    rules, label, key.trigger_seq, key, ())
                costs['choose_attempts'] += 1
                chosen = await policy.choose(request, budget)
                ready = time.monotonic()
                assert len(executor.calls)==ordinal and not chosen.degraded_reasons
                assert {c.action_key for c in chosen.candidates} == {c.action_key for c in rules.legal_candidates}
                row.update(status='SCORED', elapsed_seconds=ready-begin,
                    within_return_budget=ready<=budget.fallback_deadline_monotonic,
                    chosen_action_key=chosen.candidates[0].action_key,
                    operations=executor.calls[-1]['operations'], input_sha256=executor.calls[-1]['input_capture']['view_sha256'])
            except BaseException as exc:
                issues.append(type(exc).__name__+': '+str(exc));row.update(status='failed',error=issues[-1])
            rows.append(row);base.save(_project_file(_PROJECT_ROOT, OUT / f'CHOOSE-{ordinal:02d}.json'), row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
            if issues:break
        terminal = capture.finish()
    for p, h in inputs.items():assert base.sha(p)==h, p
    valid = len(rows)==8 and not issues and terminal['terminal']['terminal_valid']
    timely = valid and all(r['within_return_budget'] for r in rows)
    base.save(_project_file(_PROJECT_ROOT, OUT / 'CLOSURE.json'), {'whole_execution_valid':valid, 'timely':timely,
        'rows':rows,'issues':issues,'capture':terminal,'actual_costs':costs,
        'native_research_overlay_used':False,'online_admission':False})
    return 0 if timely else (2 if valid else 1)


if __name__ == '__main__':
    raise SystemExit(asyncio.run(execute()))
