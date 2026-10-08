"""T88／原生计量／原生计量及直接pass三臂回文对照，最多六次。"""

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
import time
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy, SystemClock
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy import route_vip_heuristic as vip

HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')


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
    out = _project_file(_PROJECT_ROOT, HERE / 'response-three-mode')
    out.mkdir(exist_ok=False)
    author = _project_file(_PROJECT_ROOT, EVIDENCE / 't75-net-upgrade-joint-author-1')
    t80 = _project_file(_PROJECT_ROOT, EVIDENCE / 't80-witness-capacity-failure-diagnostic-1')
    t84 = _project_file(_PROJECT_ROOT, EVIDENCE / 't84-public-shape-dispatch-1')
    batch = VipEohBatch.read(author / 'S01-generation.batch.json')
    source = (author / 'S01-model-output/candidate.py').read_text()
    identity = batch.identity(source)
    reference = json.loads((t84 / 'failed-response/CLOSURE.json').read_text())
    assert identity == reference['python_parent_runtime_identity']
    fixture = json.loads((t80 / 'FAILED-PUBLIC-WINDOW.json').read_text())['actual_failed_row']
    sequence = ('t88', 'meter', 'meter-pass', 'meter-pass', 'meter', 't88')
    save(out / 'PLAN.json', dict(schema='t89-response-three-mode/1', modes=sequence,
         max_actual_rules_attempts=6, max_actual_choose_attempts=6,
         candidate_authors_worlds_tables=0, python_parent_runtime_identity=identity,
         script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         build_closure_sha256=hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).read_bytes()).hexdigest(),
         reference_input_sha256=reference['input_sha256'], admission=False,
         scope='同一个公开复杂响应，诊断计时不授线上时限'))
    native = module('t89_fast_overlay', _project_file(_PROJECT_ROOT, HERE / 'fast_overlay.py'))
    baseline = module('t89_t88_overlay', _project_file(_PROJECT_ROOT, EVIDENCE / 't88-native-execution-prototype-1/native_overlay.py'))
    capture_type = module('t88_capture', t80 / 'probe.py').Capture
    rows = []
    original_projection = vip._Projection
    for index, mode in enumerate(sequence):
        directory = out / ('%02d-' % index + mode)
        directory.mkdir()
        context = baseline.installed() if mode == 't88' else native.installed(direct_pass=mode == 'meter-pass')
        with context as execution:
            save(directory / 'START.json', dict(mode=mode, actual_rules_choose_budget=1,
                 execution_identity=execution, python_parent_runtime_identity=identity))
            obs = observation_from_json(fixture['observation'])
            window = window_key_from_json(fixture['window_key'])
            rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
            request = DecisionRequest(obs, CompetitionContext('t89', None, None, None, None, (), 0),
                                      rules, 't89', window.trigger_seq, window, ())
            policy = vip.RouteVipHeuristicPolicy(batch.rule_config, source=source,
                     max_operations=batch.max_operations, projection_limits=batch.projection_limits)
            clock = SystemClock()
            begin = clock.now()
            budget = BudgetPolicy().build(begin, 1.0)
            with gzip.open(directory / 'ACTUAL-INPUTS.jsonl.gz', 'xb') as stream:
                capture = capture_type(policy.executor, stream)
                policy.executor = capture
                plan = await policy.choose(request, budget)
            elapsed = clock.now() - begin
            scores = [dict(key=c.action_key, score=c.total_score, trace=c.score_trace) for c in plan.candidates]
            save(directory / 'ACTUAL-RETURN.json', dict(scores=scores, operations=capture.last_operation_count))
            assert raw(scores) == raw(reference['scores'])
            assert capture.input_sha == reference['input_sha256']
            assert capture.last_operation_count == reference['operations']
            result = dict(status='SCORED', mode=mode, scores=scores,
                    input_sha256=capture.input_sha, operations=capture.last_operation_count,
                    actual_rules_attempts=1, actual_choose_attempts=1, actual_full_inputs=capture.calls,
                    elapsed_seconds=elapsed, capture_seconds=capture.seconds,
                    compute_minus_capture_seconds=elapsed - capture.seconds,
                    original_fallback_budget_seconds=budget.fallback_deadline_monotonic - begin,
                    before_original_fallback=begin + elapsed <= budget.fallback_deadline_monotonic,
                    full_input_scores_traces_order_operations_exact=True,
                    source_stable=batch.identity(source) == identity,
                    native_candidate_type=type(capture.original._fn).__name__,
                    online_admission=False)
            save(directory / 'CLOSURE.json', result)
            rows.append(result)
            print({key: value for key, value in result.items() if key != 'scores'}, flush=True)
        assert vip._Projection is original_projection
    save(out / 'CLOSURE.json', dict(rows=rows, actual_rules_attempts=6, actual_choose_attempts=6,
         actual_full_inputs=6, unique_full_inputs=1, legal_outputs=18,
         candidate_authors_worlds_tables=0, source_restored=True, admission=False))


if __name__ == '__main__':
    asyncio.run(main())
