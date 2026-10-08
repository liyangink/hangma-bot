"""真实故障响应窗口的完整choose复验；保持评分、计费与原截止。

只读既有公开观察，不生成世界／桌赛。不将扣记录后耗时当线上通过。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t84-public-shape-dispatch-1'

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
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy

HERE = Path(__file__).resolve().parent
T80 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t80-witness-capacity-failure-diagnostic-1')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')


def raw(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def save(path, value):
    with path.open('xb') as stream:
        stream.write(raw(value) + b'\n')


async def main(compiled_identity):
    out = _project_file(_PROJECT_ROOT, HERE / 'failed-response')
    out.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location('t80_capture_only', _project_file(_PROJECT_ROOT, T80 / 'probe.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = json.loads((_project_file(_PROJECT_ROOT, T80 / 'FAILED-PUBLIC-WINDOW.json')).read_text())['actual_failed_row']
    reference = json.loads((_project_file(_PROJECT_ROOT, T80 / 'fixed-r3/CLOSURE.json')).read_text())
    assert reference['status'] == 'SCORED'
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, AUTHOR / 'S01-generation.batch.json'))
    source = (_project_file(_PROJECT_ROOT, AUTHOR / 'S01-model-output/candidate.py')).read_text()
    identity = batch.identity(source)
    assert identity == json.loads((_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')).read_text())['parent_runtime_identity']
    save(out / 'START.json', {'python_parent_runtime_identity':identity,'compiled_execution_identity':compiled_identity, 'actual_rules_choose_budget':1,
         'new_models_worlds_tables':0,'online_admission':False,
         'reference':'T80/fixed-r3 full original failed public response'})
    observation = observation_from_json(fixture['observation'])
    key = window_key_from_json(fixture['window_key'])
    policy = RouteVipHeuristicPolicy(batch.rule_config, source=source,
                 max_operations=batch.max_operations, projection_limits=batch.projection_limits)
    clock = SystemClock()
    begin, cpu = clock.now(), time.process_time()
    budget = BudgetPolicy().build(begin, 1.0)
    rules = HangmaRules(batch.rule_config).analyze(observation, route_limits=batch.route_limits)
    assert {c.action_key for c in rules.legal_candidates} == set(fixture['legal_action_keys'])
    request = DecisionRequest(observation, CompetitionContext('t80-public-repro',None,None,None,None,(),0),
                              rules, 't80-repro', key.trigger_seq, key, ())
    result = {'compiled_execution_identity':compiled_identity,'python_parent_runtime_identity':identity,'actual_rules_attempts':1,'actual_choose_attempts':1,
              'status':'not_scored','new_models_worlds_tables':0,'online_admission':False}
    with gzip.open(out / 'ACTUAL-INPUTS.jsonl.gz', 'xb') as stream:
        capture = module.Capture(policy.executor, stream)
        policy.executor = capture
        try:
            plan = await policy.choose(request, budget)
            ready = clock.now()
            scores = [{'key':c.action_key,'score':c.total_score,'trace':c.score_trace} for c in plan.candidates]
            result.update(scores=scores, input_sha256=capture.input_sha, operations=capture.last_operation_count, actual_full_inputs=capture.calls)
            assert not plan.degraded_reasons
            assert raw(scores) == raw(reference['scores']), 'full JSON scores/traces changed'
            assert capture.input_sha == reference['input_sha256']
            assert capture.last_operation_count == reference['operations']
            result.update(status='SCORED',full_scores_traces_input_operations_exact=True,
                          scores=scores,input_sha256=capture.input_sha,operations=capture.last_operation_count,
                          actual_full_inputs=capture.calls,elapsed_seconds=ready-begin,
                          capture_seconds=capture.seconds,compute_minus_capture_seconds=ready-begin-capture.seconds,
                          ready_before_fallback=ready<=budget.fallback_deadline_monotonic,
                          compute_minus_capture_before_fallback=ready-begin-capture.seconds<=budget.fallback_deadline_monotonic-begin,
                          cpu_seconds=time.process_time()-cpu)
        except BaseException as exc:
            result.update(status='FAILED',error=type(exc).__name__+': '+str(exc),actual_full_inputs=capture.calls)
    result['source_stable'] = batch.identity(source) == identity
    save(out / 'CLOSURE.json', result)
    print({k:v for k,v in result.items() if k not in ['scores']},flush=True)
    if result['status'] != 'SCORED':raise SystemExit(1)


if __name__ == '__main__':
    from compiled_overlay import installed
    with installed() as compiled_identity:
        asyncio.run(main(compiled_identity))
