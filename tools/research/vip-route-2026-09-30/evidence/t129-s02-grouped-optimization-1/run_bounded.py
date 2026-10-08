"""T130：原样优化未达标后的有限杠链实验；另身份、另输出、不授旧成绩。"""

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
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import textwrap
import time

import run_grouped as group
base = group.base
HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1/actual-bounded-depth1')


@contextmanager
def installed(helper):
    """全部同源优化加一层补牌限制，缓存键保留深度；退出恢复。"""
    native = group.load('t130_native', _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'))
    math = group.load('t130_math', _project_file(_PROJECT_ROOT, HERE / 'math_batch.py'))
    graph = group.load('t130_graph', _project_file(_PROJECT_ROOT, HERE / 'graph_batch.py'))
    chain = group.load('t130_chain', _project_file(_PROJECT_ROOT, HERE / 'bounded_chain.py'))
    single = group.load('t130_single', _project_file(_PROJECT_ROOT, HERE / 'single_conversion.py'))
    from hangma_bot.policy.route_heuristic_view import VipRouteScoringView
    with native.installed() as parent, math.installed() as (mi, ms), graph.installed() as (gi, gs):
        with chain.installed(1) as (ci, cs), single.installed(VipRouteScoringView) as (scope, ss):
            identity = {'schema': 't130-bounded-chain-execution/1', 'parent': parent,
                'math': mi, 'graph': gi, 'chain': ci,
                'single_conversion_sha256': base.sha(_project_file(_PROJECT_ROOT, HERE / 'single_conversion.py')),
                'runner_sha256': base.sha(Path(__file__)), 'admission': False,
                'new_formula': False, 'unchanged_strength_claim': False}
            identity['execution_id'] = hashlib.sha256(base.canonical(identity)).hexdigest()
            original = helper.CaptureExecutor.score_vip_route
            source = textwrap.dedent(inspect.getsource(original))
            source = source.replace('receipt = self.capture.store(view.candidate_view())',
                'dto = view.candidate_view()\n    receipt = self.capture.store(dto)')
            source = source.replace('result = self.original.score_vip_route(view)',
                'with __scope(view, dto):\n            result = self.original.score_vip_route(view)')
            namespace = dict(helper.__dict__, __scope=scope)
            exec(compile(source, str(Path(__file__)), 'exec'), namespace)
            helper.CaptureExecutor.score_vip_route = namespace['score_vip_route']
            try:
                yield identity
            finally:
                helper.CaptureExecutor.score_vip_route = original
    base.save(_project_file(_PROJECT_ROOT, OUT / 'OPTIMIZATION-STATS.json'), {'math': ms, 'graph': gs, 'chain': cs, 'single': ss})


async def execute():
    """固定八选择；完整评分、原时限与旧打法变化分别记账，不伪称全等。"""
    parent, helper, cases, freeze, prior = group.check()
    result = base.read(_project_file(_PROJECT_ROOT, HERE / 'TIMING-RESULT.json'))
    if not result['full_math_exact'] or result['timely'] == result['requests']:
        raise ValueError('仅原样优化正确但仍超时才启用后备有限展开')
    OUT.mkdir(exist_ok=False)
    helper.OUT = OUT
    labels = parent['modes']['grouped']
    paths = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'bounded_chain.py'), _project_file(_PROJECT_ROOT, HERE / 'PLAN.json'), _project_file(_PROJECT_ROOT, HERE / 'TIMING-RESULT.json')]
    base.save(_project_file(_PROJECT_ROOT, OUT / 'PLAN.json'), {'labels': labels, 'max_choose': 8, 'max_replacement_depth': 1,
        'frozen_files': {str(p): base.sha(p) for p in paths},
        'new_authors_worlds_tables': 0, 'old_strength_not_inherited': True,
        'must_revalidate_changed_graph_and_strength_before_online': True})
    sys.path[:0] = [str(base.RUNTIME), str(base.RUNTIME / 'src')]
    from hangma_bot.application.deadline import BudgetPolicy, SystemClock
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    costs = dict.fromkeys(helper.COUNTERS, 0)
    rows, issues = [], []
    batch = VipEohBatch.read(helper.AUTHOR / 'AUTHOR-BATCH.json')
    source = (helper.AUTHOR / 'S02-model-output/candidate.py').read_text()
    base.save(_project_file(_PROJECT_ROOT, OUT / 'START.json'), {'pid': os.getpid(), 'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'planned_choose': 8, 'new_authors_worlds_tables': 0})
    with installed(helper) as identity:
        policy = RouteVipHeuristicPolicy(batch.rule_config, source=source,
            max_operations=batch.max_operations, projection_limits=batch.projection_limits)
        with (_project_file(_PROJECT_ROOT, OUT / 'ACTUAL-INPUTS.jsonl.gz')).open('x+b') as stream:
            capture = ScoringInputCapture(stream, limits=ScoringInputCaptureLimits.from_json(freeze['capture_limits']))
            executor = helper.CaptureExecutor(policy.executor, capture, costs, 'direct')
            policy.executor = executor
            for ordinal, label in enumerate(labels, 1):
                obs = observation_from_json(cases[label]['observation'])
                key = window_key_from_json(cases[label]['window_key'])
                expected = next(row for row in prior['rows'] if row['label'] == label)
                executor.label = label
                clock, budgets = SystemClock(), BudgetPolicy()
                begin = clock.now()
                budget = budgets.build(begin, 1.0 if obs.phase.startswith('response_') else 3.0)
                row = {'label': label, 'status': 'not_scored'}
                try:
                    costs['rule_attempts'] += 1
                    rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    request = DecisionRequest(obs, CompetitionContext('T130-bounded', None, None, None, None, (), 0),
                        rules, label, key.trigger_seq, key, ())
                    costs['choose_attempts'] += 1
                    chosen = await policy.choose(request, budget)
                    ready = clock.now()
                    assert len(executor.calls) == ordinal and not chosen.degraded_reasons
                    call = executor.calls[-1]
                    scores = [{'action_key': c.action_key, 'score': c.total_score,
                               'trace': c.score_trace['detail']} for c in chosen.candidates]
                    assert set(c['action_key'] for c in scores) == {c.action_key for c in rules.legal_candidates}
                    order = lambda xs: sorted(xs, key=lambda x: x['action_key'])
                    same = (call['input_capture']['view_sha256'] == expected['actual_input_sha256']
                        and call['operations'] == expected['operations']
                        and base.canonical(order(scores)) == base.canonical(order(expected['actual_scores'])))
                    row.update(status='SCORED', elapsed_seconds=ready-begin,
                        within_return_budget=ready<=budget.fallback_deadline_monotonic,
                        return_budget_seconds=budget.fallback_deadline_monotonic-begin,
                        unchanged_complete_input_scores_operations=same,
                        chosen_action_key=chosen.candidates[0].action_key,
                        old_chosen_action_key=expected['actual_scores'][0]['action_key'],
                        input_sha256=call['input_capture']['view_sha256'],
                        operations=call['operations'], complete_scores=scores)
                except BaseException as exc:
                    issues.append(type(exc).__name__ + ': ' + str(exc))
                    row.update(status='failed', error=issues[-1])
                base.save(_project_file(_PROJECT_ROOT, OUT / f'CHOOSE-{ordinal:02d}.json'), row)
                rows.append(row)
                print(json.dumps({k:v for k,v in row.items() if k!='complete_scores'},ensure_ascii=False),flush=True)
                if issues: break
            terminal = capture.finish()
    group.check()
    valid = len(rows)==8 and not issues and terminal['terminal']['terminal_valid']
    timely = valid and all(row['within_return_budget'] for row in rows)
    base.save(_project_file(_PROJECT_ROOT, OUT / 'CLOSURE.json'), {'execution_identity': identity, 'rows': rows, 'issues': issues,
        'whole_execution_valid': valid, 'all_original_return_budgets_passed': timely,
        'actual_costs': costs, 'capture': terminal, 'online_admission': False,
        'strength_not_evaluated': True, 'mathematical_equivalence_claim': False})
    return 0 if timely else (2 if valid else 1)


if __name__ == '__main__':
    raise SystemExit(asyncio.run(execute()))
