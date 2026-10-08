"""实际choose的构图、输入转换与评分分段诊断；同一输入，不授线上耗时。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t89-fast-meter-prototype-1'

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
import importlib.util
import json
from pathlib import Path
import time

from hangma_bot.application.deadline import BudgetPolicy, SystemClock
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy import route_vip_heuristic as vip
from hangma_bot.policy.route_heuristic_view import VipRouteScoringView

from fast_overlay import installed

HERE = Path(__file__).resolve().parent


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def save(path, value):
    with path.open('xb') as stream:
        stream.write(raw(value) + b'\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


async def main():
    out = _project_file(_PROJECT_ROOT, HERE / 'stage-costs')
    out.mkdir(exist_ok=False)
    evidence = HERE.parent
    author = evidence / 't75-net-upgrade-joint-author-1'
    t80 = evidence / 't80-witness-capacity-failure-diagnostic-1'
    t84 = evidence / 't84-public-shape-dispatch-1'
    batch = VipEohBatch.read(author / 'S01-generation.batch.json')
    source = (author / 'S01-model-output/candidate.py').read_text()
    parent = batch.identity(source)
    reference = json.loads((t84 / 'failed-response/CLOSURE.json').read_text())
    assert parent == reference['python_parent_runtime_identity']
    fixture = json.loads((t80 / 'FAILED-PUBLIC-WINDOW.json').read_text())['actual_failed_row']
    capture_type = module('t89_stage_capture', t80 / 'probe.py').Capture
    prototype_module = module('t89_t88_choices', evidence / 't88-native-execution-prototype-1/probe_canonical_choices.py')
    save(out / 'PLAN.json', dict(schema='t89-stage-cost-diagnostic/1',
         modes=['native-meter', 'native-meter-canonical-prototype'],
         max_actual_rules_choose_scoring=2,
         script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         borrowed_cache_source_sha256=hashlib.sha256(Path(prototype_module.__file__).read_bytes()).hexdigest(),
         build_closure_sha256=hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).read_bytes()).hexdigest(),
         python_parent_runtime_identity=parent, scope='same complex response; timings with stage hooks',
         candidate_authors_worlds_tables=0, production_changes=0, admission=False))
    rows = []
    original_projection = vip._Projection
    original_view = VipRouteScoringView.candidate_view
    original_build = vip.build_vip_route_scoring_view
    for index, cache in enumerate((False, True)):
        directory = out / ('%02d-' % index + ('cache' if cache else 'no-cache'))
        directory.mkdir()
        with installed(direct_pass=False) as execution:
            obs = observation_from_json(fixture['observation'])
            window = window_key_from_json(fixture['window_key'])
            begin = time.monotonic()
            rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
            rule_seconds = time.monotonic() - begin
            request = DecisionRequest(obs, CompetitionContext('t89-stage', None, None, None, None, (), 0),
                rules, 't89-stage', window.trigger_seq, window, ())
            policy = vip.RouteVipHeuristicPolicy(batch.rule_config, source=source,
                max_operations=batch.max_operations, projection_limits=batch.projection_limits)
            base = vip._Projection
            prototype = prototype_module.make_projection(base) if cache else None
            if prototype:
                vip._Projection = prototype
            durations = dict(graph=0.0, views=[], guarded_candidate=0.0)

            def timed_build(*args, **kwargs):
                begin = time.monotonic()
                try:
                    return original_build(*args, **kwargs)
                finally:
                    durations['graph'] += time.monotonic() - begin

            def timed_view(self):
                begin = time.monotonic()
                try:
                    return original_view(self)
                finally:
                    durations['views'].append(time.monotonic() - begin)

            guarded = policy.executor._guarded_candidate

            def timed_guarded(candidate_view):
                begin = time.monotonic()
                try:
                    return guarded(candidate_view)
                finally:
                    durations['guarded_candidate'] += time.monotonic() - begin

            policy.executor._guarded_candidate = timed_guarded
            vip.build_vip_route_scoring_view = timed_build
            VipRouteScoringView.candidate_view = timed_view
            save(directory / 'START.json', dict(execution_identity=execution,
                cache_prototype=cache, actual_rules_attempts=1, actual_choose_budget=1))
            try:
                clock = SystemClock()
                begin = clock.now()
                budget = BudgetPolicy().build(begin, 1.0)
                with gzip.open(directory / 'ACTUAL-INPUTS.jsonl.gz', 'xb') as stream:
                    capture = capture_type(policy.executor, stream)
                    policy.executor = capture
                    plan = await policy.choose(request, budget)
                elapsed = clock.now() - begin
            finally:
                vip._Projection = base
                vip.build_vip_route_scoring_view = original_build
                VipRouteScoringView.candidate_view = original_view
            scores = [dict(key=c.action_key, score=c.total_score, trace=c.score_trace) for c in plan.candidates]
            save(directory / 'ACTUAL-RETURN.json', dict(scores=scores, operations=capture.last_operation_count))
            assert raw(scores) == raw(reference['scores'])
            assert capture.input_sha == reference['input_sha256']
            assert capture.last_operation_count == reference['operations']
            assert len(durations['views']) == 2
            row = dict(status='SCORED', cache_prototype=cache,
                actual_rules_attempts=1, actual_choose_attempts=1, actual_full_inputs=capture.calls,
                input_sha256=capture.input_sha, operations=capture.last_operation_count,
                scores=scores, rules_seconds=rule_seconds, elapsed_seconds=elapsed,
                capture_seconds=capture.seconds, compute_minus_capture_seconds=elapsed - capture.seconds,
                graph_seconds=durations['graph'], candidate_view_seconds=durations['views'],
                guarded_candidate_seconds=durations['guarded_candidate'],
                residual_compute_seconds=elapsed - capture.seconds - durations['graph']
                    - durations['views'][1] - durations['guarded_candidate'],
                original_fallback_budget_seconds=budget.fallback_deadline_monotonic - begin,
                before_original_fallback=begin + elapsed <= budget.fallback_deadline_monotonic,
                full_input_scores_traces_order_operations_exact=True,
                source_stable=batch.identity(source) == parent, admission=False)
            if prototype:
                item, = prototype.instances
                row['cache'] = dict(calls=item.calls, hits=item.hits, misses=item.misses,
                    bypasses=item.bypasses, canonicalized_suffixes=item.canonicalized_suffixes,
                    key_seconds=item.key_seconds, entries=len(item.completed_choices),
                    expanded_nodes=len(item.nodes), branches=item.branch_count,
                    witnesses=item.witness_count, target_distances=item.target_distance_count)
            save(directory / 'CLOSURE.json', row)
            rows.append(row)
            print({key: value for key, value in row.items() if key != 'scores'}, flush=True)
        assert vip._Projection is original_projection
    save(out / 'CLOSURE.json', dict(rows=rows, actual_rules_choose_scoring=2,
        actual_full_inputs=2, unique_full_inputs=1, legal_outputs=6,
        hooks_restored=True, candidate_authors_worlds_tables=0,
        scope='stage-hook diagnostic; no broad performance/production cache admission', admission=False))


if __name__ == '__main__':
    asyncio.run(main())
