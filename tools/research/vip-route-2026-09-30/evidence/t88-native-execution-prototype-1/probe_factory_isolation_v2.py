"""固定T75原生工厂的交错执行与精确超限对照；不增加世界或桌赛。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t88-native-execution-prototype-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.action_value_executor import WorkloadExceeded
from hangma_bot.policy import action_value_executor as executor
from hangma_bot.policy import route_vip_heuristic as vip

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


def main():
    out = _project_file(_PROJECT_ROOT, HERE / 'factory-isolation-v2')
    out.mkdir(exist_ok=False)
    evidence = HERE.parent
    author = evidence / 't75-net-upgrade-joint-author-1'
    t80 = evidence / 't80-witness-capacity-failure-diagnostic-1'
    t84 = evidence / 't84-public-shape-dispatch-1'
    batch = VipEohBatch.read(author / 'S01-generation.batch.json')
    source = (author / 'S01-model-output/candidate.py').read_text()
    identity = batch.identity(source)
    reference = json.loads((t84 / 'failed-response/CLOSURE.json').read_text())
    assert identity == reference['python_parent_runtime_identity']
    fixture = json.loads((t80 / 'FAILED-PUBLIC-WINDOW.json').read_text())['actual_failed_row']
    overlay = module('t88_factory_overlay', _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'))
    baseline = module('t88_factory_t84', t84 / 'compiled_overlay.py')
    capture_type = module('t88_factory_capture', t80 / 'probe.py').Capture
    save(out / 'PLAN.json', dict(schema='t88-factory-isolation/1',
         max_actual_rule_analyses=1, max_actual_graph_builds=1, actual_choose_budget=0,
         max_actual_scoring_attempts=4, scoring_order=['native-high','native-low','native-high','t84-low'],
         low_operation_limit=1000, high_operation_limit=4800000,
         script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         build_closure_sha256=hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).read_bytes()).hexdigest(),
         candidate_authors_worlds_tables=0, production_changes=0, admission=False))
    rows = []
    with overlay.installed() as execution:
        obs = observation_from_json(fixture['observation'])
        window = window_key_from_json(fixture['window_key'])
        rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
        request = DecisionRequest(obs, CompetitionContext('t88-isolation', None, None, None, None, (), 0),
                                  rules, 't88-isolation', window.trigger_seq, window, ())
        view = vip.build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
        assert hashlib.sha256(raw(view.candidate_view())).hexdigest() == reference['input_sha256']
        high = executor.ActionValueExecutor(source, max_operations=4800000, max_local_collection_size=8192)
        low = executor.ActionValueExecutor(source, max_operations=1000, max_local_collection_size=8192)
        assert high._meter is not low._meter
        assert high._runtime is not low._runtime and high._namespace is not low._namespace
        assert high._fn is not low._fn
        assert type(high._fn).__name__ == type(low._fn).__name__ == 'cython_function_or_method'
        save(out / 'NATIVE-START.json', dict(execution_identity=execution,
             actual_rule_analyses=1, actual_graph_builds=1,
             meters_runtimes_namespaces_functions_distinct=True))
        for label, actual in [('native-high-1', high), ('native-low', low), ('native-high-2', high)]:
            with gzip.open(out / (label + '-ACTUAL-INPUTS.jsonl.gz'), 'xb') as stream:
                capture = capture_type(actual, stream)
                try:
                    result = capture.score_vip_route(view)
                except WorkloadExceeded as exc:
                    assert label == 'native-low'
                    row = dict(label=label, status='EXPECTED_OPERATION_LIMIT',
                         error_type=type(exc).__name__, error=str(exc), operations=actual.last_operation_count,
                         high_meter_used_after_low=high._meter.used, actual_scoring_attempts=1,
                         actual_full_inputs=capture.calls, input_sha256=capture.input_sha)
                    assert high._meter.used == reference['operations']
                else:
                    assert label.startswith('native-high')
                    scores = [dict(key=item.action_key, score=item.score, trace=item.trace) for item in result.entries]
                    save(out / (label + '-ACTUAL-RETURN.json'), dict(scores=scores, operations=actual.last_operation_count))
                    assert raw(sorted(scores, key=lambda item: item['key'])) == raw(sorted([dict(key=item['key'], score=item['score'], trace=item['trace']['detail']) for item in reference['scores']], key=lambda item: item['key']))
                    assert actual.last_operation_count == reference['operations']
                    row = dict(label=label, status='SCORED', scores=scores,
                         operations=actual.last_operation_count, actual_scoring_attempts=1,
                         actual_full_inputs=capture.calls, input_sha256=capture.input_sha)
            assert capture.input_sha == reference['input_sha256'] and capture.calls == 1
            save(out / (label + '-CLOSURE.json'), row)
            rows.append(row)
    with baseline.installed() as execution:
        low = executor.ActionValueExecutor(source, max_operations=1000, max_local_collection_size=8192)
        save(out / 'T84-START.json', dict(execution_identity=execution, actual_scoring_budget=1))
        with gzip.open(out / 't84-low-ACTUAL-INPUTS.jsonl.gz', 'xb') as stream:
            capture = capture_type(low, stream)
            try:
                capture.score_vip_route(view)
            except WorkloadExceeded as exc:
                row = dict(label='t84-low', status='EXPECTED_OPERATION_LIMIT',
                        error_type=type(exc).__name__, error=str(exc), operations=low.last_operation_count,
                        actual_scoring_attempts=1, actual_full_inputs=capture.calls,
                        input_sha256=capture.input_sha)
            else:
                raise AssertionError('low operation limit unexpectedly passed')
        save(out / 't84-low-CLOSURE.json', row)
        rows.append(row)
    native_failure = rows[1]
    python_failure = rows[3]
    for key in ('error_type', 'error', 'operations', 'input_sha256', 'actual_full_inputs'):
        assert native_failure[key] == python_failure[key]
    closure = dict(schema='t88-factory-isolation-result/1', rows=rows,
          actual_rule_analyses=1, actual_graph_builds=1, actual_choose_attempts=0,
          actual_scoring_attempts=4, completed_scores=2, expected_operation_failures=2,
          actual_full_inputs=4, unique_full_inputs=1, legal_outputs=6,
          full_fixed_formula_scores_and_failure_exact=True, meters_isolated=True,
          candidate_authors_worlds_tables=0, production_changes=0, admission=False)
    save(out / 'CLOSURE.json', closure)
    print({key: value for key, value in closure.items() if key != 'rows'}, flush=True)


if __name__ == '__main__':
    main()
