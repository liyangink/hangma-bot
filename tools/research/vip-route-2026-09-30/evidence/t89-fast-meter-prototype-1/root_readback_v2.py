"""纯读封存T89已发生的执行和原件；不重跑任何规则、评分或牌局。"""

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
import gzip
import hashlib
import json
from pathlib import Path
import re
import statistics

HERE = Path(__file__).resolve().parent


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


reference = read(_project_file(_PROJECT_ROOT, HERE.parent / 't84-public-shape-dispatch-1/failed-response/CLOSURE.json'))
native_parent = read(_project_file(_PROJECT_ROOT, HERE.parent / 't88-native-execution-prototype-1/BUILD-PLAN.json'))
plan = read(_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json'))
closure = read(_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json'))
assert closure['plan_sha256'] == sha((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_bytes())
assert plan['instrumented_ast_sha256'] == native_parent['specs'][-1]['instrumented_ast_sha256']
assert plan['candidate_source_sha256'] == native_parent['specs'][-1]['candidate_source_sha256']
assert plan['generator_sha256'] == sha((_project_file(_PROJECT_ROOT, HERE / 'build_fast.py')).read_bytes())
assert plan['meter_source_sha256'] == sha((_project_file(_PROJECT_ROOT, HERE / 'fast_meter_source.py')).read_bytes())
for name, digest in plan['generated_sources'].items():
    assert sha((_project_file(_PROJECT_ROOT, HERE / name)).read_bytes()) == digest
for binding in closure['binaries'].values():
    data = (_project_file(_PROJECT_ROOT, HERE / binding['path'])).read_bytes()
    assert len(data) == binding['bytes'] and sha(data) == binding['sha256']

rows = []
root_outputs = 0
direct_outputs = 0
input_digests = []
for directory in sorted((_project_file(_PROJECT_ROOT, HERE / 'response-three-mode')).glob('[0-9][0-9]-*')):
    row = read(directory / 'CLOSURE.json')
    returned = read(directory / 'ACTUAL-RETURN.json')
    assert raw(returned['scores']) == raw(reference['scores']) == raw(row['scores'])
    assert returned['operations'] == row['operations'] == reference['operations']
    rows.append(row)
    root_outputs += len(row['scores'])
for directory in sorted((_project_file(_PROJECT_ROOT, HERE / 'stage-costs')).glob('[0-9][0-9]-*')):
    row = read(directory / 'CLOSURE.json')
    returned = read(directory / 'ACTUAL-RETURN.json')
    assert raw(returned['scores']) == raw(reference['scores']) == raw(row['scores'])
    assert returned['operations'] == row['operations'] == reference['operations']
    assert len(row['candidate_view_seconds']) == 2
    assert row['graph_seconds'] + row['guarded_candidate_seconds'] < row['compute_minus_capture_seconds']
    rows.append(row)
    root_outputs += len(row['scores'])
isolation = read(_project_file(_PROJECT_ROOT, HERE / 'factory-isolation/CLOSURE.json'))
expected_inner = sorted([dict(key=item['key'], score=item['score'], trace=item['trace']['detail'])
                         for item in reference['scores']], key=lambda row: row['key'])
for label in ('native-high-1', 'native-high-2'):
    returned = read(_project_file(_PROJECT_ROOT, HERE / 'factory-isolation' / (label + '-ACTUAL-RETURN.json')))
    assert raw(sorted(returned['scores'], key=lambda row: row['key'])) == raw(expected_inner)
    assert returned['operations'] == reference['operations']
    direct_outputs += len(returned['scores'])
for row in isolation['rows']:
    rows.append(row)
failures = [row for row in isolation['rows'] if row['status'] == 'EXPECTED_OPERATION_LIMIT']
assert len(failures) == 2
for key in ('error_type', 'error', 'operations', 'input_sha256'):
    assert failures[0][key] == failures[1][key]
assert failures[0]['operations'] == 5398
assert failures[0]['high_meter_used_after_low'] == reference['operations']

for path in HERE.rglob('*ACTUAL-INPUTS.jsonl.gz'):
    with gzip.open(path, 'rt') as stream:
        actual = [json.loads(line) for line in stream if line.strip()]
    assert len(actual) == 1
    digest = sha(raw(actual[0]['view']))
    assert digest == actual[0]['view_sha256'] == reference['input_sha256']
    input_digests.append(digest)
assert len(input_digests) == 12 and len(set(input_digests)) == 1
assert len(rows) == 12 and all(row['actual_full_inputs'] == 1 for row in rows)
assert sum(row['status'] == 'SCORED' for row in rows) == 10
assert root_outputs == 24 and direct_outputs == 6

semantics = read(_project_file(_PROJECT_ROOT, HERE / 'meter-semantics/ACTUAL-RETURNS.json'))
assert raw(semantics['reference']) == raw(semantics['native'])
assert len(semantics['reference']) == 400
semantics_closure = read(_project_file(_PROJECT_ROOT, HERE / 'meter-semantics/CLOSURE.json'))
assert semantics_closure['charges'] == 1700
reset = read(_project_file(_PROJECT_ROOT, HERE / 'meter-semantics/RESET-RETURNS.json'))
assert len(reset) == 6 and all(raw(row['rows'][0]) == raw(row['rows'][1]) for row in reset)
dynamic = read(_project_file(_PROJECT_ROOT, HERE / 'dynamic-runtime/CLOSURE.json'))
assert len(dynamic['rows']) == 3
for row in dynamic['rows']:
    returns = read(_project_file(_PROJECT_ROOT, HERE / 'dynamic-runtime' / (row['label'] + '-ACTUAL-RETURN.json')))
    assert raw(returns['reference']) == raw(returns['native'])
    assert len(returns['reference']) == 10
public_log = (_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-TESTS.log')).read_text()
assert re.search(r'\b365 passed\b', public_log) and 'FAILED' not in public_log

response_rows = read(_project_file(_PROJECT_ROOT, HERE / 'response-three-mode/CLOSURE.json'))['rows']
medians = {mode: statistics.median([row['compute_minus_capture_seconds'] for row in response_rows
                                   if row['mode'] == mode]) for mode in ('t88', 'meter', 'meter-pass')}
stages = read(_project_file(_PROJECT_ROOT, HERE / 'stage-costs/CLOSURE.json'))['rows']
cache = stages[1]
assert cache['cache']['hits'] == 2015 and cache['cache']['calls'] == 3166
assert cache['cache']['canonicalized_suffixes'] == 0
assert cache['cache']['expanded_nodes'] == 5163
assert cache['cache']['branches'] == 5692
assert cache['cache']['witnesses'] == 1628
assert cache['cache']['target_distances'] == 314364

# 只保存少量实际生成C的直接调用原件及摘要；不归档可再生成的整份C和目标文件。
bindings = {}
for name in ('_t89_runtime.c', '_t89_candidate.c'):
    content = (_project_file(_PROJECT_ROOT, HERE / name)).read_bytes()
    lines = content.decode().splitlines()
    direct = [(index + 1, line) for index, line in enumerate(lines)
              if ('__pyx_vtab)->_charge_one(' in line or '__pyx_vtab)->_charge_zero(' in line)
              or (not line.lstrip().startswith(('*', 'static')) and '__pyx_f_14_t89_candidate__direct_pass(' in line)]
    assert direct
    bindings[name] = dict(generated_c_sha256=sha(content), direct_call_sites=len(direct),
                          first_actual_lines=[dict(line=index, code=line.strip()) for index, line in direct[:3]])

result = dict(schema='t89-root-readback/2',
    actual_rule_analyses=9, actual_choose_attempts=8, extra_graph_builds=1,
    actual_scoring_attempts=12, actual_full_inputs=12, distinct_full_inputs=1,
    archived_completed_score_returns=10, legal_outputs_exact=30,
    expected_operation_failures=2, first_expected_overflow_used=5398,
    public_tests_once_passed=365,
    meter_boundary_pairs=400, meter_charges_per_backend=1700, reset_pairs=6,
    dynamic_runtime_pairs=3, dynamic_helper_calls_per_side_per_pair=10,
    response_compute_minus_capture_medians_seconds=medians,
    meter_reduction_fraction=1-medians['meter']/medians['t88'],
    direct_pass_additional_reduction_fraction=1-medians['meter-pass']/medians['meter'],
    combined_cache_diagnostic_compute_seconds=cache['compute_minus_capture_seconds'],
    combined_cache_diagnostic_graph_seconds=cache['graph_seconds'],
    combined_cache_diagnostic_guarded_candidate_seconds=cache['guarded_candidate_seconds'],
    native_binding_evidence=bindings,
    candidate_authors_worlds_tables=0, production_changes=0, admission=False,
    scope='同一复杂公开响应；公共回归不授通用候选原生AST或生产缓存准入',
    archive_exclusions=['generated .c', 'build/temp .o', '__pycache__'])
artifacts = {}
for path in sorted(HERE.rglob('*')):
    if (not path.is_file() or path.suffix in ('.c', '.o', '.pyc')
            or '__pycache__' in path.parts or path.name in ('ROOT-READBACK-V2.json', 'ROOT-READBACK-V2.log')):
        continue
    data = path.read_bytes()
    artifacts[str(path.relative_to(HERE))] = dict(bytes=len(data), sha256=sha(data))
result['artifacts'] = artifacts
with (_project_file(_PROJECT_ROOT, HERE / 'ROOT-READBACK-V2.json')).open('xb') as stream:
    stream.write(raw(result) + b'\n')
print({key: value for key, value in result.items() if key not in ('artifacts', 'native_binding_evidence')}, flush=True)
