"""纯读核验T88实际输入、返回和失败；不重跑规则、图、评分或模型。"""

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
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
REFERENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t84-public-shape-dispatch-1/failed-response')


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def read(path):
    return json.loads(path.read_text())


def rows(path):
    with gzip.open(path, 'rt') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(raw(value) + b'\n')


reference = read(_project_file(_PROJECT_ROOT, REFERENCE / 'CLOSURE.json'))
reference_dto, = rows(_project_file(_PROJECT_ROOT, REFERENCE / 'ACTUAL-INPUTS.jsonl.gz'))
input_files = sorted(HERE.rglob('*ACTUAL-INPUTS.jsonl.gz'))
assert len(input_files) == 12
for path in input_files:
    actual, = rows(path)
    assert raw(actual['view']) == raw(reference_dto['view'])
    assert hashlib.sha256(raw(actual['view'])).hexdigest() == actual['view_sha256'] == reference['input_sha256']
ab = read(_project_file(_PROJECT_ROOT, HERE / 'response-abba/CLOSURE.json'))
completed = []
for directory in ['response-abba/00-t84', 'response-abba/01-t88', 'response-abba/02-t88',
                  'response-abba/03-t84', 'duplicate-choices', 'duplicate-choices-v2', 'canonical-choices']:
    result = read(_project_file(_PROJECT_ROOT, HERE / directory / 'CLOSURE.json'))
    assert raw(result['scores']) == raw(reference['scores'])
    assert result['operations'] == reference['operations'] == 4593210
    assert result['input_sha256'] == reference['input_sha256']
    assert result['actual_rules_attempts'] == result['actual_choose_attempts'] == result['actual_full_inputs'] == 1
    completed.append(directory)
isolation = read(_project_file(_PROJECT_ROOT, HERE / 'factory-isolation-v2/CLOSURE.json'))
expected_detail = [dict(key=item['key'], score=item['score'], trace=item['trace']['detail'])
                   for item in reference['scores']]
for label in ('native-high-1', 'native-high-2'):
    result = read(_project_file(_PROJECT_ROOT, HERE / 'factory-isolation-v2' / (label + '-CLOSURE.json')))
    actual = read(_project_file(_PROJECT_ROOT, HERE / 'factory-isolation-v2' / (label + '-ACTUAL-RETURN.json')))
    assert raw(actual['scores']) == raw(result['scores'])
    assert raw(sorted(result['scores'], key=lambda item: item['key'])) == raw(sorted(expected_detail, key=lambda item: item['key']))
    assert actual['operations'] == result['operations'] == reference['operations']
    completed.append('factory-isolation-v2/' + label)
native_failure = read(_project_file(_PROJECT_ROOT, HERE / 'factory-isolation-v2/native-low-CLOSURE.json'))
python_failure = read(_project_file(_PROJECT_ROOT, HERE / 'factory-isolation-v2/t84-low-CLOSURE.json'))
for key in ('error_type', 'error', 'operations', 'actual_full_inputs', 'input_sha256'):
    assert native_failure[key] == python_failure[key]
assert native_failure['operations'] == 5398
assert native_failure['high_meter_used_after_low'] == reference['operations']
assert isolation['meters_isolated'] and isolation['full_fixed_formula_scores_and_failure_exact']

failure_log = (_project_file(_PROJECT_ROOT, HERE / 'FACTORY-ISOLATION.log')).read_text()
assert 'AssertionError' in failure_log and 'reference[\'scores\']' in failure_log
assert not (_project_file(_PROJECT_ROOT, HERE / 'factory-isolation/CLOSURE.json')).exists()
assert not list((_project_file(_PROJECT_ROOT, HERE / 'factory-isolation')).glob('*ACTUAL-RETURN.json'))
save('FAILED-HELPERS-READBACK.json', dict(
    build_initial_failure=dict(reason='编译工具未加入PYTHONPATH；已有工具目录后成功',
                              actual_rules_choose_scores_worlds_tables=0),
    public_test_initial_failure=dict(reason='收集时tests包不在PYTHONPATH；补工程根后365通过',
                                    passed_test_credit=0),
    factory_v1_failure=dict(reason='把执行器内层trace与choose外层trace比较；工具范围错误',
          actual_rule_analyses=1, actual_graph_builds=1, actual_choose_attempts=0,
          actual_scoring_attempts=1, actual_full_inputs=1,
          completed_score_return_reached=True, raw_return_not_archived=True,
          equality_credit=False, operations=None,
          basis='原脚本和堆栈：score已返回，比较断言失败；不补造未保存返回'),
    admission=False))
plan, closure = read(_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')), read(_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json'))
assert hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_bytes()).hexdigest() == closure['plan']
for spec in plan['specs']:
    assert hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / spec['generated_source'])).read_bytes()).hexdigest() == spec['generated_source_sha256']
for item in closure['binaries'].values():
    path = _project_file(_PROJECT_ROOT, HERE / item['path'])
    assert path.stat().st_size == item['bytes']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
test_log = (_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-TESTS-WITH-ROOT.log')).read_text()
assert '365 passed in ' in test_log and 'failed' not in test_log.lower()
base_median = statistics.median(row['compute_minus_capture_seconds'] for row in ab['rows'] if row['mode'] == 't84')
native_median = statistics.median(row['compute_minus_capture_seconds'] for row in ab['rows'] if row['mode'] == 't88')
canon = read(_project_file(_PROJECT_ROOT, HERE / 'canonical-choices/CLOSURE.json'))
diagnostic = read(_project_file(_PROJECT_ROOT, HERE / 'duplicate-choices-v2/CLOSURE.json'))
assert diagnostic['duplicate_choices'] == 2574 and diagnostic['unique_choices'] == 592
assert diagnostic['analysis_field_diffs'] == {}
artifacts = {}
for path in sorted(HERE.rglob('*')):
    if (not path.is_file() or path.name == 'ROOT-READBACK.json'
            or path.suffix in ('.c', '.o', '.pyc') or '__pycache__' in path.parts):
        continue
    content = path.read_bytes()
    artifacts[str(path.relative_to(HERE))] = dict(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
receipt = dict(schema='t88-root-readback/1',
    actual_rule_analyses=9, actual_choose_attempts=7, extra_graph_builds=2,
    actual_scoring_attempts=12, actual_full_inputs=12, distinct_full_inputs=1,
    archived_completed_score_returns=9, legal_outputs_exact=27,
    completed_but_unarchived_return=1, expected_operation_failures=2,
    completed=completed, public_tests_once_passed=365,
    baseline_compute_minus_capture_median_seconds=base_median,
    native_compute_minus_capture_median_seconds=native_median,
    native_reduction_fraction=1-native_median/base_median,
    canonical_single_compute_minus_capture_seconds=canon['compute_minus_capture_seconds'],
    native_formula_scope='仅固定T75；合成候选公共回归主要覆盖runtime/meter/结构守卫，不授通用AST原生准入',
    canonical_cache_scope='可信项目输入的单一复杂响应；未授生产缓存资格',
    candidate_authors_worlds_tables=0, production_changes=0, admission=False,
    archive_exclusions=['generated .c', 'build/temp .o', '__pycache__'], artifacts=artifacts)
save('ROOT-READBACK.json', receipt)
print(json.dumps({key: value for key, value in receipt.items() if key != 'artifacts'}, ensure_ascii=False))
