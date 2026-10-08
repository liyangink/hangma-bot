"""在隔离源码下实际评分214既有窗，精确核冻结同公式参考。

不装载旧包冒称新身份。完整实际输入评分前保存，当前工程身份独立计算。
新代码仅构图复用公开结果；不生成模型、世界或桌赛，不读T52成绩。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t54-public-count-native-cache-1'

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
import time
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
WORKTREE = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t51-t48-same-formula-efficiency-author-1')
PILOT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1/candidate-pilot-1')
T48 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t48-v3-natural-highfan-joint-author-1')


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
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main():
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, AUTHOR / 'S01-generation.batch.json'))
    source_file = _project_file(_PROJECT_ROOT, AUTHOR / 'S01-model-output/candidate.py')
    assert sha(source_file) == '368edebbe1cee32605de6b10f5875bfc556491ed567916548ce5f3803981ab32'
    source = source_file.read_text()
    identity = batch.identity(source)
    prior_public = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / 'PUBLIC-PROBE-CLOSURE.json')).read_text())
    prior_natural = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / 'RECOVERY-NATURAL-EQUIVALENCE-CLOSURE.json')).read_text())
    assert prior_public['complete_all_windows'] and prior_natural['complete']
    reference_identity = prior_natural['candidate_identity']
    assert identity['candidate_id'] != reference_identity['candidate_id']
    assert identity['params'] == reference_identity['params'] and identity['math_backend'] == reference_identity['math_backend']
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')).read_text())
    for name, item in plan['files'].items():
        assert sha(_project_file(_PROJECT_ROOT, WORKTREE / name)) == item['proposed_sha256'] and sha(_project_file(_PROJECT_ROOT, REPO / name)) == item['base_sha256']
    public_cases = json.loads((_project_file(_PROJECT_ROOT, T48 / 'PUBLIC-CASES.json')).read_text())['cases']
    fixture = _project_file(_PROJECT_ROOT, REPO / json.loads((HERE.parent / 't47-integrated-graph-and-preparation-1/PLAN.json').read_text())['fixture_path'])
    for index, old in enumerate(json.loads(fixture.read_text())['rows']):
        row = old['actual_failed_row']
        public_cases.append({'label': 'original-multigang-' + str(index),
                             'observation': row['observation'], 'window_key': row['window_key']})
    natural_expected = {row['decision_id']: row for row in prior_natural['rows']}
    assert len(public_cases) == len(prior_public['rows']) == 22 and len(natural_expected) == 192
    frozen = {str(path): sha(path) for path in (_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'), _project_file(_PROJECT_ROOT, HERE / 'verify_worktree.py'),
        source_file, _project_file(_PROJECT_ROOT, AUTHOR / 'PUBLIC-PROBE-CLOSURE.json'), _project_file(_PROJECT_ROOT, AUTHOR / 'RECOVERY-NATURAL-EQUIVALENCE-CLOSURE.json'),
        _project_file(_PROJECT_ROOT, T48 / 'PUBLIC-CASES.json'), fixture, _project_file(_PROJECT_ROOT, PILOT / 'decisions.jsonl.gz'))}
    save('SCORING-PLAN.json', {'schema': 't54-native-cache-actual-scoring/1',
        'candidate_runtime_identity': identity, 'reference_runtime_identity': reference_identity,
        'same_mathematical_source_sha256': sha(source_file), 'engineering_not_model_generation': True,
        'public_windows': 22, 'natural_windows': 192, 'frozen_files': frozen,
        'main_files_still_base': plan['files'], 'new_models_worlds_tables': 0,
        'no_confirmation_deadline_or_release_credit': True})
    executor = ActionValueExecutor(source, max_operations=batch.max_operations,
                                   max_local_collection_size=batch.projection_limits.max_nodes)
    results = []

    def execute(label, row, expected, archive):
        result = {'label': label, 'status': 'unscored'}
        begin = time.perf_counter()
        try:
            observation = observation_from_json(row['observation'])
            key = window_key_from_json(row['window_key'])
            rules = HangmaRules(batch.rule_config).analyze(observation, route_limits=batch.route_limits)
            request = DecisionRequest(observation,
                CompetitionContext('T54-engineering-equivalence', None, None, None, None, (), 0),
                rules, 'T54:' + str(len(results)), key.trigger_seq, key, ())
            view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
            graph_seconds = time.perf_counter() - begin
            dto = view.candidate_view()
            digest = hashlib.sha256(canonical(dto)).hexdigest()
            archive.write(canonical({'label': label, 'view_sha256': digest, 'candidate_view': dto}) + b'\n')
            archive.flush()
            assert digest == expected['view_sha256'], 'actual input drift'
            scored = executor.score_vip_route(view)
            actual = {entry.action_key: {'score': entry.score, 'trace': entry.trace} for entry in scored.entries}
            old = expected['scores']
            if type(old) is list:
                old = {entry['action_key']: {'score': entry['score'], 'trace': entry['trace']} for entry in old}
            assert canonical(actual) == canonical(old), 'score or trace drift'
            assert executor.last_operation_count == expected['operations'], 'operation drift'
            result.update(status='SCORED', all_actual_input_scores_traces_operations_equal=True,
                view_sha256=digest, scores=actual, operations=executor.last_operation_count,
                whole_graph_seconds=graph_seconds, nodes=len(view.nodes), saved_before_score=True)
        except Exception as exc:
            result.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        result['total_seconds_including_capture'] = time.perf_counter() - begin
        results.append(result)

    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz'), 'xb') as archive:
        for index, row in enumerate(public_cases):
            execute('public:' + str(index), row, prior_public['rows'][index], archive)
        print({'public_completed': 22, 'failures': sum(row['status'] != 'SCORED' for row in results)}, flush=True)
        with gzip.open(_project_file(_PROJECT_ROOT, PILOT / 'decisions.jsonl.gz'), 'rt', encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                expected = natural_expected.get(row['decision_id'])
                if expected is not None:
                    execute('natural:' + row['decision_id'], row, expected, archive)
                    if (len(results) - 22) % 32 == 0:
                        print({'natural_completed': len(results) - 22,
                               'failures': sum(item['status'] != 'SCORED' for item in results)}, flush=True)
    captures = {}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz'), 'rt', encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            assert row['label'] not in captures
            captures[row['label']] = row['view_sha256']
            assert hashlib.sha256(canonical(row['candidate_view'])).hexdigest() == row['view_sha256']
    stable = identity == batch.identity(source) and all(sha(Path(path)) == value for path, value in frozen.items())
    stable = stable and all(sha(_project_file(_PROJECT_ROOT, REPO / name)) == item['base_sha256'] for name, item in plan['files'].items())
    complete = stable and len(results) == len(captures) == 214 and all(row['status'] == 'SCORED' for row in results)
    assert all(captures.get(row['label']) == row.get('view_sha256') for row in results if row['status'] == 'SCORED')
    save('SCORING-CLOSURE.json', {'schema': 't54-native-cache-equivalence/1', 'complete': complete,
        'actual_score_pipelines': len(results), 'actual_full_inputs_readback': len(captures),
        'runtime_identity': identity, 'reference_identity': reference_identity,
        'source_identity_stable': stable, 'full_DTO_scores_traces_operations_equal': complete,
        'rows': results, 'main_source_modified': False, 'new_models_worlds_tables': 0,
        'scope': 'exposed22 public and original result-blind192 development; engineering equivalence only; timing under uncontrolled parallel load'})
    print({'complete': complete, 'actual_score_pipelines': len(results), 'captures': len(captures)}, flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
