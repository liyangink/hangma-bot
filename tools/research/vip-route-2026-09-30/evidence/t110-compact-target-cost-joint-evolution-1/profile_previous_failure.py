"""对T109原完整失败窗口做一次实际剖析；不改源码、图、操作上限或结论。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from dataclasses import asdict
import cProfile
import hashlib
import json
from pathlib import Path
import time

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t109-target-specific-joint-evolution-1')


def canonical(value):
    """输入按原有限JSON摘要核对，剖析不增加或删减事实。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """只绑定公开证据和实际执行源码，不访问认证配置。"""
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, value):
    """只新建诊断收据，原失败与费用保持原样。"""
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main():
    """固定原public:20及480万上限，一次score，要求重现原操作超限。"""
    package = _project_file(_PROJECT_ROOT, OLD / 'S01-model-output')
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, OLD / 'AUTHOR-BATCH.json'))
    child = load_vip_parents([package], batch)[0]
    original = json.loads((_project_file(_PROJECT_ROOT, OLD / 'S01-public-probe/FAILED-MECHANICAL-READBACK.json')).read_text())
    failure = original['failures'][0]
    assert failure['label'] == 'old:public:20'
    case = next(row for row in json.loads((_project_file(_PROJECT_ROOT, OLD / 'PUBLIC-PANEL.json')).read_text())['cases']
                if row['label'] == failure['label'])
    out = _project_file(_PROJECT_ROOT, HERE / 'T109-original-failure-profile')
    out.mkdir(exist_ok=False)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, OLD / 'AUTHOR-BATCH.json'), _project_file(_PROJECT_ROOT, OLD / 'PUBLIC-PANEL.json'),
        _project_file(_PROJECT_ROOT, OLD / 'S01-public-probe/FAILED-MECHANICAL-READBACK.json'),
        package / 'candidate.py', package / 'generation.json']
    pins = {str(p): pin(p) for p in files}
    assert all(pin(_project_file(_PROJECT_ROOT, REPO_ROOT / name)) == h for name, h in child['identity']['source_manifest'].items())
    save(out / 'START.json', {'candidate_identity': child['identity'], 'frozen_files': pins,
        'case_label': case['label'], 'expected_input_sha256': case['view_sha256'],
        'max_operations': batch.max_operations, 'max_actual_score_attempts': 1,
        'new_model_world_table_calls': 0,
        'hypotheses': ['repeated support computation', 'per-target container construction/sorting',
                       'graph aggregation', 'explanation generation'],
        'full_input_retained_no_minimization': 'remove nodes would change the complete mechanical requirement',
        'timing_scope': 'profiled execution only, includes profiler overhead; no real deadline credit'})
    observation = observation_from_json(case['observation'])
    key = window_key_from_json(case['window_key'])
    analysis = HangmaRules(batch.rule_config).analyze(observation, route_limits=batch.route_limits)
    assert analysis.completeness.value == 'complete'
    request = DecisionRequest(observation, CompetitionContext('T109-profile-only', None, None,
        None, None, (), 0), analysis, case['label'], key.trigger_seq, key, ())
    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
    dto = view.candidate_view()
    assert hashlib.sha256(canonical(dto)).hexdigest() == case['view_sha256'] == failure['input_sha256']
    executor = ActionValueExecutor(child['source'], name='T109-original-failure-profile',
        max_operations=batch.max_operations, max_local_collection_size=batch.projection_limits.max_nodes)
    raw = (out / 'VIEWS.jsonl.gz').open('x+b')
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 67108864, 1))
    receipt = capture.store(dto)
    assert receipt.saved_before_score and receipt.error is None
    profile = cProfile.Profile()
    error = None
    started = time.monotonic()
    profile.enable()
    try:
        executor.score_vip_route(view)
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'reason': str(exc)}
    finally:
        profile.disable()
        elapsed = time.monotonic() - started
        costs = capture.finish()
        raw.close()
    profile.dump_stats(str(out / 'candidate-profile.pstats'))
    candidate_rows, runtime_rows = [], []
    for row in profile.getstats():
        code = row.code
        if isinstance(code, str):
            continue
        entry = {'function': code.co_name, 'filename': code.co_filename,
            'first_line': code.co_firstlineno, 'calls': row.callcount,
            'recursive_calls': row.reccallcount,
            'exclusive_seconds_with_profiler': row.inlinetime,
            'inclusive_seconds_with_profiler': row.totaltime}
        if code.co_filename.startswith('<action_value:'):
            candidate_rows.append(entry)
        elif code.co_filename.endswith('action_value_executor.py'):
            runtime_rows.append(entry)
    candidate_rows.sort(key=lambda row: -row['exclusive_seconds_with_profiler'])
    runtime_rows.sort(key=lambda row: -row['exclusive_seconds_with_profiler'])
    source_stable = all(pin(n) == h for n, h in pins.items()) and all(
        pin(_project_file(_PROJECT_ROOT, REPO_ROOT / n)) == h for n, h in child['identity']['source_manifest'].items())
    complete = (source_stable and error is not None and error['type'] == 'WorkloadExceeded'
        and executor.last_operation_count == 4800006 and costs['terminal']['terminal_valid'])
    save(out / 'CLOSURE.json', {'complete': complete, 'original_failure_reproduced': complete,
        'error': error, 'input_sha256': case['view_sha256'], 'source_stable': source_stable,
        'actual_rule_analyze_calls': 1, 'actual_view_build_calls': 1, 'actual_score_attempts': 1,
        'actual_completed_scores': 0, 'actual_operations': executor.last_operation_count,
        'input_capture': costs, 'capture_receipt': asdict(receipt),
        'profiled_score_elapsed_seconds': elapsed,
        'candidate_function_profile': candidate_rows, 'runtime_function_profile': runtime_rows,
        'profiled_seconds_not_real_deadline_evidence': True,
        'all_candidate_cost_after_failure_unknown': True,
        'new_models_worlds_tables': 0, 'budget_or_candidate_changed': False})
    print({'complete': complete, 'actual_operations': executor.last_operation_count,
        'top_candidate_functions': candidate_rows[:8], 'top_runtime_functions': runtime_rows[:6]}, flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
