"""固定已有公开窗口，实测独立 VIP choose 的总耗时和事件循环响应。

这是接入前诊断，不是官方完整动作窗口或发布门。使用系统单调时钟与
应用层默认预算；完整实际 DTO 评分前持久化。只调用已有同公式，不生成
模型、世界或桌赛，不读取正在 T52 运行的任何成绩。失败不重试或补分。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t55-real-choose-deadline-diagnostic-1'

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
import time
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy, SystemClock
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
from hangma_bot.policy.safe_fallback import SafeFallbackPolicy

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
WORKTREE = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t51-t48-same-formula-efficiency-author-1')
T48 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t48-v3-natural-highfan-joint-author-1')
T54 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t54-public-count-native-cache-1')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / ('V2-' + name))).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


class CaptureExecutor:
    """仅在评分入口记录收到的真实视图，计时单列；评分仍由原执行器完成。"""

    def __init__(self, original, archive):
        self.original, self.archive = original, archive
        self.label = None
        self.last_capture = None
        self.capture_seconds = 0.0

    @property
    def last_operation_count(self):
        return self.original.last_operation_count

    @last_operation_count.setter
    def last_operation_count(self, value):
        self.original.last_operation_count = value

    def score_vip_route(self, view):
        begin = time.monotonic()
        dto = view.candidate_view()
        digest = hashlib.sha256(canonical(dto)).hexdigest()
        self.archive.write(canonical({'label': self.label, 'candidate_view': dto,
                                      'view_sha256': digest}) + b'\n')
        self.archive.flush()
        self.last_capture = digest
        self.capture_seconds = time.monotonic() - begin
        return self.original.score_vip_route(view)


async def main():
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, AUTHOR / 'S01-generation.batch.json'))
    source_path = _project_file(_PROJECT_ROOT, AUTHOR / 'S01-model-output/candidate.py')
    source = source_path.read_text()
    identity = batch.identity(source)
    expected_closure = json.loads((_project_file(_PROJECT_ROOT, T54 / 'SCORING-CLOSURE.json')).read_text())
    assert expected_closure['complete'] and identity == expected_closure['runtime_identity']
    expected = {row['label']: row for row in expected_closure['rows']}
    public = json.loads((_project_file(_PROJECT_ROOT, T48 / 'PUBLIC-CASES.json')).read_text())['cases']
    fixture = _project_file(_PROJECT_ROOT, REPO / json.loads((HERE.parent / 't47-integrated-graph-and-preparation-1/PLAN.json').read_text())['fixture_path'])
    for index, old in enumerate(json.loads(fixture.read_text())['rows']):
        row = old['actual_failed_row']
        public.append({'label': 'original-multigang-' + str(index),
                       'observation': row['observation'], 'window_key': row['window_key']})
    # 已知复杂窗首次及同窗热态，再含真实碰杠、吃和普通弃牌；不按成绩选样。
    cases = [(20, 'fresh-process-first'), (20, 'same-process-repeat'),
             (18, 'response-peng-gang'), (3, 'response-chi'), (16, 'ordinary-draw')]
    budget_policy, clock = BudgetPolicy(), SystemClock()
    assert budget_policy.post_reserve_seconds == 0.10
    frozen = {str(path): sha(path) for path in (_project_file(_PROJECT_ROOT, HERE / 'probe_v2.py'), source_path,
        _project_file(_PROJECT_ROOT, T54 / 'SCORING-CLOSURE.json'), _project_file(_PROJECT_ROOT, T48 / 'PUBLIC-CASES.json'), fixture)}
    save('PLAN.json', {'schema': 't55-real-choose-diagnostic/1', 'candidate_identity': identity,
        'public_cases': cases, 'candidate_score_call_limit': 5,
        'budget': {'post_reserve_seconds': budget_policy.post_reserve_seconds,
                   'enhancement_fraction': budget_policy.enhancement_fraction,
                   'fallback_fraction': budget_policy.fallback_fraction},
        'timer_delay_seconds': 0.01, 'new_models_worlds_tables': 0,
        'frozen_files': frozen,
        'timing_scope': 'real monotonic time under uncontrolled concurrent T52 CPU load; no online admission'})
    rows, control = [], None
    init_started = time.monotonic()
    policy = RouteVipHeuristicPolicy(batch.rule_config, source=source,
        max_operations=batch.max_operations, projection_limits=batch.projection_limits)
    init_seconds = time.monotonic() - init_started
    loop = asyncio.get_running_loop()
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'V2-ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz'), 'xb') as archive:
        capture = CaptureExecutor(policy.executor, archive)
        policy.executor = capture
        for case_index, mode in cases:
            raw = public[case_index]
            observation = observation_from_json(raw['observation'])
            key = window_key_from_json(raw['window_key'])
            label = 'public:' + str(case_index) + ':' + mode
            capture.label, capture.last_capture, capture.capture_seconds = label, None, 0.0
            span = 1.0 if observation.phase.startswith('response_') else 3.0
            begin = clock.now()
            budget = budget_policy.build(begin, span)
            timer_fired = asyncio.Event()
            fired_at = []

            def timer():
                fired_at.append(clock.now())
                timer_fired.set()

            handle = loop.call_later(0.01, timer)
            result = {'label': label, 'phase': observation.phase,
                'configured_span_seconds': span, 'status': 'unscored',
                'fallback_budget_seconds': budget.fallback_deadline_monotonic - begin,
                'latest_send_budget_seconds': budget.latest_send_at_monotonic - begin}
            try:
                rules = HangmaRules(batch.rule_config).analyze(observation, route_limits=batch.route_limits)
                rules_seconds = clock.now() - begin
                request = DecisionRequest(observation,
                    CompetitionContext('T55-predeployment-diagnostic', None, None, None, None, (), 0),
                    rules, label, key.trigger_seq, key, ())
                plan = await policy.choose(request, budget)
                ready_at = clock.now()
                actual = {entry.action_key: {'score': entry.total_score,
                          'trace': entry.score_trace['detail']} for entry in plan.candidates}
                old = expected['public:' + str(case_index)]
                assert canonical(actual) == canonical(old['scores'])
                assert capture.last_capture == old['view_sha256']
                assert capture.last_operation_count == old['operations']
                result.update(status='SCORED', all_legal_scores_traces_operations_equal=True,
                    actual_input_sha256=capture.last_capture, actual_full_scores=actual,
                    operations=capture.last_operation_count, rules_seconds=rules_seconds,
                    elapsed_including_capture_seconds=ready_at - begin,
                    capture_seconds=capture.capture_seconds,
                    elapsed_minus_capture_seconds=ready_at - begin - capture.capture_seconds,
                    ready_before_fallback=ready_at <= budget.fallback_deadline_monotonic,
                    ready_before_latest_send=ready_at <= budget.latest_send_at_monotonic)
            except Exception as exc:
                result.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
            await timer_fired.wait()
            handle.cancel()
            result['event_loop_timer_lag_seconds'] = max(0.0, fired_at[0] - begin - 0.01)
            rows.append(result)
            print({k: result.get(k) for k in ('label','status','elapsed_minus_capture_seconds',
                  'ready_before_fallback','event_loop_timer_lag_seconds')}, flush=True)
            if control is None and result['status'] == 'SCORED':
                control_begin = clock.now()
                control_event = asyncio.Event()
                control_fired = []

                def control_timer():
                    control_fired.append(clock.now())
                    control_event.set()

                loop.call_later(0.01, control_timer)
                await SafeFallbackPolicy().choose(request, budget_policy.build(control_begin, span))
                control_ready = clock.now()
                await control_event.wait()
                control = {'same_prepared_request': label,
                    'fallback_only_choose_seconds': control_ready - control_begin,
                    'event_loop_timer_lag_seconds': max(0.0, control_fired[0] - control_begin - 0.01),
                    'candidate_score_calls': 0}
    captures = {}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'V2-ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz'), 'rt', encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            assert row['label'] not in captures
            assert hashlib.sha256(canonical(row['candidate_view'])).hexdigest() == row['view_sha256']
            captures[row['label']] = row['view_sha256']
    stable = identity == batch.identity(source) and all(sha(Path(path)) == digest for path,digest in frozen.items())
    complete = stable and len(rows) == len(captures) == 5 and all(row['status'] == 'SCORED' for row in rows)
    save('CLOSURE.json', {'schema': 't55-real-choose-diagnostic-closure/1', 'complete': complete,
        'source_identity_stable': stable, 'actual_choose_and_score_calls': len(rows),
        'actual_full_inputs_readback': len(captures), 'policy_initialization_seconds': init_seconds,
        'rows': rows, 'fallback_only_timer_control': control, 'candidate_identity': identity,
        'new_models_worlds_tables': 0, 'normal_r18_fallbacks': 0, 'online_admission': False,
        'scope': 'public policy choose only; default budget and event loop response under live CPU load; no actual POST/SSE'})
    print({'complete': complete, 'actual_scores': len(rows)}, flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
