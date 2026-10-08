"""纯读回编译原型证据；不重跑规则、候选评分、牌山或模型。

逐份核实际输入、全部分值和操作计量；编译执行身份独立于Python父身份。
归档清单只含重建源码、日志、原始证据及实际二进制，不含编译中间文件。
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
import gzip
import hashlib
import inspect
import json
from pathlib import Path

from compiled_overlay import installed
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy import action_value_executor

HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
T80 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t80-witness-capacity-failure-diagnostic-1')


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def read(path):
    return json.loads(path.read_text())


def inputs(path):
    """核对实际压缩输入的完整字节；返回次序，不把摘要文件当原件。"""
    rows = []
    with gzip.open(path, 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            dto = row.get('view', row.get('candidate_view'))
            assert dto is not None
            assert hashlib.sha256(raw(dto)).hexdigest() == row['view_sha256']
            rows.append(row)
    return rows


def main():
    plan = read(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'))
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, EVIDENCE / 't75-net-upgrade-joint-author-1/S01-generation.batch.json'))
    source = (_project_file(_PROJECT_ROOT, EVIDENCE / 't75-net-upgrade-joint-author-1/S01-model-output/candidate.py')).read_text()
    parent = batch.identity(source)
    assert parent == plan['parent_runtime_identity']
    factory = inspect.getsource(action_value_executor._make_runtime)
    assert hashlib.sha256(factory.encode()).hexdigest() == plan['runtime_factory_sha256']
    assert (_project_file(_PROJECT_ROOT, HERE / '_t82_runtime.pyx')).read_text().endswith(factory)
    with installed() as identity:
        pass
    prechange = read(_project_file(_PROJECT_ROOT, HERE / 'PRECHANGE-PLAN.json'))
    assert '232 passed' in (_project_file(_PROJECT_ROOT, HERE / 'PYTEST.log')).read_text()
    assert hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / 'REFERENCE-public-tile-counts.py')).read_bytes()).hexdigest() == prechange['old_source_sha256']
    assert hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / 'PROPOSED-public-tile-counts.py')).read_bytes()).hexdigest() == prechange['proposed_source_sha256']
    assert hashlib.sha256(Path(prechange['source_path']).read_bytes()).hexdigest() == prechange['proposed_source_sha256']
    assert identity['binary_sha256'] == plan['compiled_binary_sha256']

    panel = read(_project_file(_PROJECT_ROOT, HERE / 'equivalence-56/CLOSURE.json'))
    old_panel = read(_project_file(_PROJECT_ROOT, T80 / 'r3-equivalence-56/CLOSURE.json'))
    panel_inputs = inputs(_project_file(_PROJECT_ROOT, HERE / 'equivalence-56/ACTUAL-INPUTS.jsonl.gz'))
    old_inputs = inputs(_project_file(_PROJECT_ROOT, T80 / 'r3-equivalence-56/ACTUAL-INPUTS.jsonl.gz'))
    assert panel['complete'] and panel['source_stable']
    assert panel['compiled_execution_identity'] == identity
    assert panel['python_parent_runtime_identity'] == parent
    assert len(panel_inputs) == len(panel['rows']) == len(old_inputs) == len(old_panel['rows']) == 56
    assert all(panel[key] == 56 for key in (
        'actual_rule_calls', 'actual_projection_calls', 'actual_score_calls', 'actual_full_inputs_verified'))
    legal_outputs = 0
    for row, previous, capture, old in zip(panel['rows'], old_panel['rows'], panel_inputs, old_inputs):
        assert row['label'] == previous['label'] == capture['label'] == old['label']
        assert row['status'] == 'SCORED'
        assert raw(capture['view']) == raw(old['view'])
        assert row['input_sha256'] == capture['view_sha256'] == previous['input_sha256']
        assert raw(row['scores']) == raw(previous['scores'])
        assert row['operations'] == previous['operations']
        legal_outputs += len(row['scores'])
    assert legal_outputs == 515

    timing = read(_project_file(_PROJECT_ROOT, HERE / 'timing/cache/CLOSURE.json'))
    timing_inputs = inputs(_project_file(_PROJECT_ROOT, HERE / 'timing/cache/ACTUAL-INPUTS.jsonl.gz'))
    old_timing = {row['label']: row for row in read(_project_file(_PROJECT_ROOT, T80 / 'TIMING-REFERENCE-R3.json'))['rows']}
    python_timing = {r['label']:r for r in read(_project_file(_PROJECT_ROOT, EVIDENCE / 't81-executor-numeric-hotpath-1/r2-timing/cache/CLOSURE.json'))['rows']}
    assert timing['mathematical_complete'] and timing['source_stable']
    assert timing['compiled_execution_identity'] == identity
    assert len(timing['rows']) == len(timing_inputs) == timing['actual_choose_attempts'] == 5
    for row, capture in zip(timing['rows'], timing_inputs):
        previous = old_timing[row['label'].rsplit(':', 1)[0]]
        assert row['status'] == 'SCORED' and row['label'] == capture['label']
        assert row['actual_input_sha256'] == capture['view_sha256'] == previous['view_sha256']
        assert raw(sorted(row['actual_scores'], key=lambda e:e['action_key'])) == raw(sorted(previous['scores'], key=lambda e:e['action_key']))
        assert raw(row['actual_scores']) == raw(python_timing[row['label']]['actual_scores'])
        assert row['operations'] == previous['operations']
        legal_outputs += len(row['actual_scores'])

    response = read(_project_file(_PROJECT_ROOT, HERE / 'failed-response/CLOSURE.json'))
    response_inputs = inputs(_project_file(_PROJECT_ROOT, HERE / 'failed-response/ACTUAL-INPUTS.jsonl.gz'))
    previous = read(_project_file(_PROJECT_ROOT, T80 / 'fixed-r3/CLOSURE.json'))
    assert response['status'] == 'SCORED' and response['source_stable']
    assert response['compiled_execution_identity'] == identity
    assert len(response_inputs) == response['actual_full_inputs'] == response['actual_choose_attempts'] == 1
    assert response_inputs[0]['view_sha256'] == response['input_sha256'] == previous['input_sha256']
    assert raw(response['scores']) == raw(previous['scores'])
    assert response['operations'] == previous['operations']
    legal_outputs += len(response['scores'])
    assert legal_outputs == 553

    paths = [p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py', '.pyx', '.json', '.log')]
    paths += [p for folder in ('timing', 'equivalence-56', 'failed-response')
              for p in (_project_file(_PROJECT_ROOT, HERE / folder)).rglob('*') if p.is_file()]
    binary = next((_project_file(_PROJECT_ROOT, HERE / 'build/lib')).glob('_t82_runtime*.so'))
    paths.append(binary)
    files = {str(p.relative_to(HERE)): {'bytes':p.stat().st_size,
             'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)}
    assert files[str(binary.relative_to(HERE))]['sha256'] == identity['binary_sha256']
    assert hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / '_t82_runtime.pyx')).read_bytes()).hexdigest() == plan['generated_source_sha256']
    closure = {'schema':'t84-public-shape-readback/1', 'complete':True,
               'compiled_execution_identity':identity, 'source_stable':True,
               'actual_rules_projection_score_calls':62, 'actual_full_inputs':62,
               'finite_legal_outputs':553, 'full_inputs_scores_traces_operations_exact':True,
               'unique_public_tests_completed':232,
               'unit_scope':'related public rule/cache tests under Python; scoring runs use unchanged compiled T82 callbacks with new exact parent identity',
               'complex_compute_seconds':[r['wall_minus_capture_seconds'] for r in timing['rows'][:2]],
               'complex_actual_elapsed_seconds':[r['elapsed_wall_seconds'] for r in timing['rows'][:2]],
               'response_compute_seconds':response['compute_minus_capture_seconds'],
               'response_actual_elapsed_seconds':response['elapsed_seconds'],
               'compute_deadline_all_windows_pass':False, 'main_loop_isolation_proven':False,
               'new_models_worlds_tables':0, 'production_changes':0, 'online_admission':False,
               'archive_exclusions':['__pycache__'], 'no_new_lru_or_capacity_math':True,
               'files':files}
    with (_project_file(_PROJECT_ROOT, HERE / 'ROOT-READBACK.json')).open('xb') as stream:
        stream.write(raw(closure) + b'\n')
    print({k:closure[k] for k in ('complete','actual_full_inputs','finite_legal_outputs',
                                 'complex_compute_seconds','response_compute_seconds')})


if __name__ == '__main__':
    main()
