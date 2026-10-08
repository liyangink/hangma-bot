"""复用公开窗口，检查当前候选的真实 choose 截止和事件循环响应。

仅作本地工程诊断，不生成世界或桌赛。基线和隔离缓存各最多五次实际
评分；完整输入评分前保存。时间使用本机单调时钟秒，CPU时间另列。
记录开销可单列，但不能据扣记录耗时授真实线上通过。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t80-witness-capacity-failure-diagnostic-1'

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
import gzip
import hashlib
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
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
REPO = _PROJECT_ROOT
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')
CASES = [(20, 'first'), (20, 'repeat'), (18, 'peng-gang'),
         (3, 'chi'), (16, 'ordinary-discard')]


def canonical(value):
    """输入、分值及解释都按规范JSON核字节，不以浮点容差代替等价。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


class CaptureExecutor:
    """包装真实执行器，只额外记录评分实际收到的公开视图。"""

    def __init__(self, original, archive):
        self.original, self.archive = original, archive
        self.label = None
        self.last_digest = None
        self.capture_wall = self.capture_cpu = 0.0

    @property
    def last_operation_count(self):
        return self.original.last_operation_count

    @last_operation_count.setter
    def last_operation_count(self, value):
        self.original.last_operation_count = value

    def score_vip_route(self, view):
        wall, cpu = time.monotonic(), time.process_time()
        dto = view.candidate_view()
        digest = hashlib.sha256(canonical(dto)).hexdigest()
        self.archive.write(canonical({'label': self.label,
                                     'view_sha256': digest,
                                     'candidate_view': dto}) + b'\n')
        self.archive.flush()
        self.last_digest = digest
        self.capture_wall = time.monotonic() - wall
        self.capture_cpu = time.process_time() - cpu
        return self.original.score_vip_route(view)


async def main(mode):
    out = _project_file(_PROJECT_ROOT, HERE / 'r3-timing' / mode)
    out.mkdir(parents=True, exist_ok=False)
    batch_path = _project_file(_PROJECT_ROOT, AUTHOR / 'S01-generation.batch.json')
    batch = VipEohBatch.read(batch_path)
    source_path = _project_file(_PROJECT_ROOT, AUTHOR / 'S01-model-output/candidate.py')
    source = source_path.read_text()
    reference_path = _project_file(_PROJECT_ROOT, HERE / 'TIMING-REFERENCE-R3.json')
    reference = json.loads(reference_path.read_text())
    assert reference['complete_all_windows']
    identity = batch.identity(source)
    assert identity['source_sha256'] == reference['candidate_identity']['source_sha256']
    assert identity['params'] == reference['candidate_identity']['params']
    assert identity['math_backend'] == reference['candidate_identity']['math_backend']
    if mode == 'baseline':
        assert identity == reference['candidate_identity']
    else:
        assert identity['candidate_id'] != reference['candidate_identity']['candidate_id']
    public_path = _project_file(_PROJECT_ROOT, EVIDENCE / 't48-v3-natural-highfan-joint-author-1/PUBLIC-CASES.json')
    cases = json.loads(public_path.read_text())['cases']
    fixture_plan = _project_file(_PROJECT_ROOT, EVIDENCE / 't47-integrated-graph-and-preparation-1/PLAN.json')
    fixture = _project_file(_PROJECT_ROOT, REPO / json.loads(fixture_plan.read_text())['fixture_path'])
    for old in json.loads(fixture.read_text())['rows']:
        row = old['actual_failed_row']
        cases.append({'observation': row['observation'], 'window_key': row['window_key']})
    assert len(cases) == 22
    expected = {r['label']: r for r in reference['rows']}
    files = {str(p.resolve()): sha(p) for p in
             [Path(__file__), batch_path, source_path, reference_path,
              public_path, fixture_plan, fixture,
              _project_file(_PROJECT_ROOT, EVIDENCE / 't78-net-upgrade-fixed-qualifier-confirmation-1/CAMPAIGN-PLAN.json')]}
    policy = RouteVipHeuristicPolicy(batch.rule_config, source=source,
        max_operations=batch.max_operations, projection_limits=batch.projection_limits)
    clock, budgets = SystemClock(), BudgetPolicy()
    save(out / 'START.json', {'schema': 't79-real-current-choose/1',
         'mode': mode, 'runtime_identity': identity,
         'reference_identity': reference['candidate_identity'], 'files': files,
         'actual_score_budget': 5, 'cases': CASES,
         'timer_delay_seconds': 0.01, 'timer_lag_diagnostic_limit_seconds': 0.02,
         'hypothesis_not_official_timing_standard': True,
         'deadline_source': 'production default BudgetPolicy',
         'new_models_worlds_tables': 0, 'published': False,
         'scope': 'five known public requests without T78 or test jobs, OS background uncontrolled; no official SSE/POST'})
    rows, score_attempts, rule_attempts = [], 0, 0
    with gzip.open(out / 'ACTUAL-INPUTS.jsonl.gz', 'xb') as stream:
        capture = CaptureExecutor(policy.executor, stream)
        policy.executor = capture
        loop = asyncio.get_running_loop()
        for index, tag in CASES:
            label = 'public:' + str(index) + ':' + tag
            capture.label, capture.last_digest = label, None
            capture.capture_wall = capture.capture_cpu = 0.0
            raw = cases[index]
            observation = observation_from_json(raw['observation'])
            key = window_key_from_json(raw['window_key'])
            span = 1.0 if observation.phase.startswith('response_') else 3.0
            begin, cpu_begin = clock.now(), time.process_time()
            budget = budgets.build(begin, span)
            fired, fired_at = asyncio.Event(), []

            def timer():
                fired_at.append(clock.now())
                fired.set()

            handle = loop.call_later(0.01, timer)
            row = {'label': label, 'status': 'not_scored', 'phase': observation.phase,
                   'span_seconds': span, 'fallback_deadline_seconds':
                   budget.fallback_deadline_monotonic - begin}
            try:
                rule_attempts += 1
                rules = HangmaRules(batch.rule_config).analyze(observation, route_limits=batch.route_limits)
                rules_wall, rules_cpu = clock.now() - begin, time.process_time() - cpu_begin
                request = DecisionRequest(observation,
                    CompetitionContext('T79-local-deadline-diagnostic', None, None, None, None, (), 0),
                    rules, label, key.trigger_seq, key, ())
                score_attempts += 1
                plan = await policy.choose(request, budget)
                ready, cpu_ready = clock.now(), time.process_time()
                scores = [{'action_key': c.action_key, 'score': c.total_score,
                           'trace': c.score_trace['detail']} for c in plan.candidates]
                old = expected['public:' + str(index)]
                assert not plan.degraded_reasons
                assert set(c.action_key for c in plan.candidates) == {r['action_key'] for r in old['scores']}
                assert canonical(sorted(scores, key=lambda r:r['action_key'])) == canonical(sorted(old['scores'], key=lambda r:r['action_key']))
                assert capture.last_digest == old['view_sha256']
                assert capture.last_operation_count == old['operations']
                row.update(status='SCORED', exact_all_legal_scores_traces_input_operations=True,
                    actual_input_sha256=capture.last_digest, actual_scores=scores,
                    operations=capture.last_operation_count, rules_wall_seconds=rules_wall,
                    rules_cpu_seconds=rules_cpu, elapsed_wall_seconds=ready-begin,
                    elapsed_cpu_seconds=cpu_ready-cpu_begin,
                    capture_wall_seconds=capture.capture_wall,
                    capture_cpu_seconds=capture.capture_cpu,
                    wall_minus_capture_seconds=ready-begin-capture.capture_wall,
                    cpu_minus_capture_seconds=cpu_ready-cpu_begin-capture.capture_cpu,
                    ready_before_fallback=ready <= budget.fallback_deadline_monotonic,
                    compute_minus_capture_before_fallback=
                        ready-begin-capture.capture_wall <= budget.fallback_deadline_monotonic-begin)
            except Exception as exc:
                row.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
            await fired.wait()
            handle.cancel()
            row['event_loop_timer_lag_seconds'] = max(0.0, fired_at[0]-begin-0.01)
            rows.append(row)
            print({k:row.get(k) for k in ['label','status','wall_minus_capture_seconds',
                  'cpu_minus_capture_seconds','compute_minus_capture_before_fallback',
                  'event_loop_timer_lag_seconds','error']}, flush=True)
    inputs = {}
    with gzip.open(out / 'ACTUAL-INPUTS.jsonl.gz', 'rt') as stream:
        for line in stream:
            r = json.loads(line)
            assert r['label'] not in inputs
            assert hashlib.sha256(canonical(r['candidate_view'])).hexdigest() == r['view_sha256']
            inputs[r['label']] = r['view_sha256']
    stable = identity == batch.identity(source) and all(sha(Path(p))==h for p,h in files.items())
    complete = stable and len(inputs)==len(rows)==5 and all(r['status']=='SCORED' for r in rows)
    assert all(inputs.get(r['label'])==r.get('actual_input_sha256') for r in rows if r['status']=='SCORED')
    deadline = complete and all(r['compute_minus_capture_before_fallback'] for r in rows)
    responsive = complete and all(r['event_loop_timer_lag_seconds'] <= 0.02 for r in rows)
    save(out / 'CLOSURE.json', {'schema': 't79-real-current-choose-closure/1',
         'mathematical_complete': complete, 'diagnostic_pass': deadline and responsive,
         'compute_deadline_pass': deadline, 'event_loop_diagnostic_pass': responsive,
         'source_stable': stable, 'actual_rule_attempts': rule_attempts,
         'actual_choose_attempts': score_attempts, 'actual_full_inputs': len(inputs),
         'runtime_identity': identity, 'rows': rows,
         'new_models_worlds_tables': 0, 'online_admission': False})
    print({'mathematical_complete':complete,'compute_deadline_pass':deadline,
           'event_loop_diagnostic_pass':responsive,'diagnostic_pass':deadline and responsive}, flush=True)
    if not complete or not (deadline and responsive):
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['baseline','cache'], required=True)
    asyncio.run(main(parser.parse_args().mode))
