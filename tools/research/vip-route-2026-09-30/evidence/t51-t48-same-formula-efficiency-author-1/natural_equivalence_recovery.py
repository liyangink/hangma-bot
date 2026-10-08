"""按公开输入分层盲选192个自然开发窗，重建实际视图并对账真父归档评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t51-t48-same-formula-efficiency-author-1'

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
from collections import defaultdict
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
from hangma_bot.policy.route_heuristic_view import VIP_ROUTE_TRACE_SCHEMA_VERSION

HERE = Path(__file__).resolve().parent
PILOT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1/candidate-pilot-1')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def rows():
    with gzip.open(_project_file(_PROJECT_ROOT, PILOT / 'decisions.jsonl.gz'), 'rt', encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['c_self_scored']:
                yield row


def main():
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / 'S01-generation.batch.json'))
    candidate = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / 'S01-model-output')], batch)[0]
    assert json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PROBE-CLOSURE.json')).read_text())['complete_all_windows']
    buckets = defaultdict(list)
    for row in rows():
        # 只读窗口、白库存、合法动作族及ID；不按得分、终局或选中动作入样。
        label = (row['phase'], min(3, row['white_count']), tuple(sorted(row['action_families'])))
        rank = hashlib.sha256(('T51-result-blind:' + row['decision_id']).encode()).hexdigest()
        buckets[label].append((rank, row['decision_id']))
    for group in buckets.values():
        group.sort()
    selected, depth = [], 0
    while len(selected) < 192:
        previous = len(selected)
        for label in sorted(buckets):
            if depth < len(buckets[label]) and len(selected) < 192:
                selected.append(buckets[label][depth][1])
        assert len(selected) > previous
        depth += 1
    assert selected == json.loads((_project_file(_PROJECT_ROOT, HERE / 'NATURAL-EQUIVALENCE-START.json')).read_text())['selected_decision_ids']
    selected_set = set(selected)
    frozen = {str(_project_file(_PROJECT_ROOT, PILOT / name)): sha(_project_file(_PROJECT_ROOT, PILOT / name)) for name in ('decisions.jsonl.gz','views.jsonl.gz','summary.json')}
    plan = {'requested_windows': 192, 'selection': 'public phase, white inventory and legal action family strata; round-robin SHA-ID order',
            'selected_decision_ids': selected, 'frozen_files': frozen, 'candidate_identity': candidate['identity'],
            'scope': 'previously exposed natural development; equivalence only, not strength/confirmation/deadline',
            'bucket_counts': [{'phase': k[0], 'white_bin': k[1], 'families': k[2], 'available': len(v)} for k,v in sorted(buckets.items())],
            'new_models_worlds_tables': 0}
    with (_project_file(_PROJECT_ROOT, HERE / 'RECOVERY-NATURAL-EQUIVALENCE-START.json')).open('xb') as f:
        f.write(canonical(plan) + b'\n')
    actual_rows = []
    executor = ActionValueExecutor(candidate['source'], max_operations=batch.max_operations,
                                   max_local_collection_size=batch.projection_limits.max_nodes)
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'RECOVERY-NATURAL-EQUIVALENCE-ACTUAL-INPUTS.jsonl.gz'), 'xb') as archive:
        for row in rows():
            if row['decision_id'] not in selected_set:
                continue
            record = {'decision_id': row['decision_id'], 'status': 'unscored'}
            begin = time.perf_counter()
            try:
                obs = observation_from_json(row['observation'])
                key = window_key_from_json(row['window_key'])
                rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                request = DecisionRequest(obs, CompetitionContext('T51-equivalence',None,None,None,None,(),0),
                                          rules, 'T51-natural:' + str(len(actual_rows)), key.trigger_seq, key, ())
                view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                dto = view.candidate_view()
                digest = hashlib.sha256(canonical(dto)).hexdigest()
                archive.write(canonical({'decision_id': row['decision_id'], 'view_sha256': digest, 'candidate_view': dto}) + b'\n')
                archive.flush()
                assert digest == row['scoring_execution']['input_capture']['view_sha256'], 'input drift'
                score = executor.score_vip_route(view)
                actual = {e.action_key: {'score': e.score, 'trace': e.trace} for e in score.entries}
                metadata = {'trace_schema': VIP_ROUTE_TRACE_SCHEMA_VERSION,
                            'candidate_kind': dto['candidate_kind'], 'view_schema_version': view.schema_version,
                            'normal_draw_hu_payment_semantics_version': view.normal_draw_hu_payment_semantics_version,
                            'natural_preparation_semantics_version': view.natural_preparation_semantics_version}
                assert all({k:v for k,v in e['trace'].items() if k != 'detail'} == metadata for e in row['candidates']), 'production trace metadata drift'
                expected = {e['action_key']: {'score': e['score'], 'trace': e['trace']['detail']} for e in row['candidates']}
                assert canonical(actual) == canonical(expected), 'score or trace drift'
                assert set(actual) == set(row['legal_action_keys']), 'missing legal root'
                record.update(status='SCORED', all_scores_traces_equal=True, saved_before_score=True,
                              view_sha256=digest, operations=executor.last_operation_count,
                              old_operations=row['candidate_operations'], scores=actual,
                              white_count=row['white_count'], action_families=row['action_families'],
                              current_legal_hu=row['current_opportunity']['legal_hu'])
            except (Exception, WorkloadExceeded) as exc:
                record.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
            record['duration_wall_ms'] = (time.perf_counter() - begin) * 1000
            actual_rows.append(record)
    stable = batch.identity(candidate['source']) == candidate['identity'] and all(sha(Path(n)) == v for n,v in frozen.items())
    complete = len(actual_rows) == 192 and all(r['status'] == 'SCORED' for r in actual_rows) and stable
    result = {'schema': 't51-natural-equivalence/1', 'complete': complete, 'requested_windows': 192,
              'completed_scores': sum(r['status'] == 'SCORED' for r in actual_rows), 'identity_stable': stable,
              'candidate_identity': candidate['identity'], 'rows': actual_rows, 'new_models_worlds_tables': 0,
              'strength_confirmation_admission_claim': False}
    with (_project_file(_PROJECT_ROOT, HERE / 'RECOVERY-NATURAL-EQUIVALENCE-CLOSURE.json')).open('xb') as f:
        f.write(canonical(result) + b'\n')
    print({k: result[k] for k in ('complete','requested_windows','completed_scores','identity_stable')}, flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
