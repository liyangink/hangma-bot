"""必要胡数学剪枝的118个原请求差分；只允许实际资格查询计数减少。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t154-hu-math-pruning-acceptance-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / 'src')))

import asyncio
import gzip
import hashlib
import json
import traceback
from hangma_bot.application.audit_codec import decision_request_from_json, decision_budget_from_json
from hangma_bot.hangma._standard import backend_info
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy, VipRouteProjectionLimits


def canonical(value):
    """有限JSON规范字节，不替换或近似原分数。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    """实际字节摘要；主线旧证据及原请求只读。"""
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1 << 20), b''):
            h.update(data)
    return h.hexdigest()


def save(path, value):
    """新运行自己的费用与终态原子落盘。"""
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def verify(plan):
    """冻结所有当前源和实际原生数学；每个原请求及观察验签。"""
    for relative, item in plan['runtime_source_manifest'].items():
        path = _project_file(_PROJECT_ROOT, ROOT / relative)
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], relative
    assert sha(plan['source_file']) == plan['source_sha256']
    for case in plan['cases']:
        assert sha(case['case_file']) == case['case_sha256']
        assert sha(case['reference_request_file']) == case['reference_request_sha256']
    backend = backend_info()
    assert backend['implementation'] == 'c_grouped' and backend['fallback_reason'] is None
    assert sha(backend['native_path']) == 'c475cfd69a86317a2b42bde8085e9e14aa2a0c456a8dae656935c6ba45a18dd6'
    return backend


def normalize(dto):
    """仅移除已声明的实际查询计数；其余完整字段逐字比较。"""
    return {**dto, 'workload': {k: v for k, v in dto['workload'].items()
        if k != 'waiting_draw_witness_count'}}


async def main():
    """复用原完整规则请求，不重算世界或延长原800单调时钟名义预算。"""
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')).read_text())
    backend = verify(plan)
    out = _project_file(_PROJECT_ROOT, HERE / 'exact-run')
    out.mkdir(exist_ok=False)
    save(out / 'START.json', {'plan_sha256': sha(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')),
        'runner_sha256': sha(Path(__file__)), 'backend': backend,
        'maximum_actual_choose_and_scores': 118, 'rules_worlds_tables_models_HTTP': 0})
    params = plan['params']
    config = RuleConfig(**params['rule_config'])
    projection = VipRouteProjectionLimits(**params['projection_limits'])
    source = Path(plan['source_file']).read_text()
    fees, results, issues = [], [], []
    failure = None
    try:
        for index, case in enumerate(plan['cases'], 1):
            reference = json.loads(Path(case['case_file']).read_text())['item']
            old = reference['original_decision']
            saved = json.loads(Path(case['reference_request_file']).read_text())
            request = decision_request_from_json(saved['request'])
            budget = decision_budget_from_json(saved['budget'])
            assert request.decision_id == case['source_decision_id']
            case_out = out / f'case-{index:03d}'
            case_out.mkdir()
            fee = {'case': index, 'source_decision_id': request.decision_id,
                   'choose_attempted': 0, 'actual_score_calls': 0, 'status': 'reserved'}
            fees.append(fee)
            save(out / 'COSTS.json', fees)
            receipts = []
            def sink(row):
                receipts.append(row)
                save(case_out / 'DECISION.json', row)
            stream = (case_out / 'views.jsonl.gz').open('x+b')
            capture = ScoringInputCapture(stream, limits=ScoringInputCaptureLimits.from_json(plan['capture_limits']))
            inner = RouteVipHeuristicPolicy(config, source=source,
                max_operations=params['max_operations'], projection_limits=projection)
            audited = VipDevelopmentAuditPolicy(inner, 't154:pruning:' + sha(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')),
                lambda: {'source_decision_id': request.decision_id}, sink, challenger=True, capture=capture)
            try:
                fee.update(status='choose_started', choose_attempted=1)
                save(out / 'COSTS.json', fees)
                await audited.choose(request, budget)
                assert len(receipts) == 1
                fee.update(status='choose_complete', actual_score_calls=sum(
                    r['actual_score_calls'] for r in receipts[0]['scoring_calls']))
            finally:
                try:
                    terminal = capture.finish()
                    save(case_out / 'CAPTURE-CLOSURE.json', terminal)
                    if receipts:
                        fee['actual_score_calls'] = sum(r['actual_score_calls'] for r in receipts[-1].get('scoring_calls', []))
                finally:
                    stream.close()
                    save(out / 'COSTS.json', fees)
            assert terminal['terminal']['terminal_valid']
            with gzip.open(case_out / 'views.jsonl.gz', 'rt') as stream:
                new_view = json.loads(next(stream))['view']
                assert next(stream, None) is None
            old_view = reference['original_view']['view']
            assert canonical(normalize(old_view)) == canonical(normalize(new_view)), '数学／规则／条件图不等'
            old_count = old_view['workload']['waiting_draw_witness_count']
            new_count = new_view['workload']['waiting_draw_witness_count']
            assert 0 <= new_count <= old_count
            actual = receipts[0]
            for field in ('legal_action_keys', 'candidates', 'selected_action_key', 'degraded_reasons',
                          'candidate_operations', 'c_self_scored', 'status'):
                assert canonical(old[field]) == canonical(actual[field]), field
            old_call, new_call = old['scoring_calls'][0], actual['scoring_calls'][0]
            for field in ('status', 'actual_score_calls', 'score_completed', 'full_legal_keys',
                          'scored_action_keys', 'candidate_operations', 'unknown_nodes', 'target_distance_evaluation_count'):
                assert canonical(old_call[field]) == canonical(new_call[field]), field
            result = {'case': index, 'source_decision_id': request.decision_id,
                'phase': old['phase'], 'all_mathematical_fields_scores_traces_order_operations_equal': True,
                'old_qualification_queries': old_count, 'new_qualification_queries': new_count,
                'new_policy_choose_with_capture_ms': actual['policy_compute_ms_observed'],
                'old_policy_choose_with_capture_ms': old['policy_compute_ms_observed'],
                'source_root_id': old['root_id'], 'selected_action': actual['selected_action_key']}
            results.append(result)
            save(case_out / 'DIFFERENTIAL-RESULT.json', result)
            if index % 10 == 0:
                print({'complete_cases': index, 'mathematical_score_differences': 0}, flush=True)
    except BaseException as exc:
        failure = exc
        issues.append({'error': type(exc).__name__ + ': ' + str(exc), 'traceback': traceback.format_exc()})
    finally:
        try:
            verify(plan)
        except BaseException as exc:
            issues.append({'source_drift': str(exc)})
        save(out / 'CLOSURE.json', {'schema': 't154-exact-pruning-closure/1',
            'valid': not issues and len(results) == 118, 'complete_cases': len(results),
            'results': results, 'issues': issues, 'fees': fees,
            'old_qualification_queries': sum(r['old_qualification_queries'] for r in results),
            'new_qualification_queries': sum(r['new_qualification_queries'] for r in results),
            'strength_or_online_timing_credit': False, 'rules_worlds_tables_models_HTTP': 0})
    if failure is not None:
        raise failure
    assert not issues


if __name__ == '__main__':
    asyncio.run(main())
