"""签收原答并完整评分56个既知公开窗口；不生成世界或新模型请求。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import json
import time

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_generate import (
    VipEohBatch, build_vip_eoh_prompt, load_vip_parents,
    parse_vip_eoh_reply, run_vip_eoh_generate,
)
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t62-earned-highfan-joint-revision-preparation-1')


def canonical(value):
    """规范JSON统一tuple/list，用精确字节核输入，不使用分数容差。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def public_cases():
    """只装载18个公开因果目标和38个已闭机械控制，不读取教师世界。"""
    public = _project_file(_PROJECT_ROOT, EVIDENCE / 't48-v3-natural-highfan-joint-author-1/PUBLIC-CASES.json')
    cases = json.loads(public.read_text())['cases']
    fixture_plan = _project_file(_PROJECT_ROOT, EVIDENCE / 't47-integrated-graph-and-preparation-1/PLAN.json')
    fixture = _project_file(_PROJECT_ROOT, REPO_ROOT / json.loads(fixture_plan.read_text())['fixture_path'])
    for row in json.loads(fixture.read_text())['rows']:
        failed = row['actual_failed_row']
        cases.append({'observation': failed['observation'], 'window_key': failed['window_key']})
    assert len(cases) == 22
    for index, case in enumerate(cases):
        case['label'] = 'public:' + str(index)
    natural = _project_file(_PROJECT_ROOT, EVIDENCE / 't58-qualifier-result-mechanism-1/NATURAL-PUBLIC-CASES.json')
    for index, row in enumerate(json.loads(natural.read_text())['cases']):
        cases.append({**row, 'label': 'natural:' + format(index, '02')})
    old = json.loads((_project_file(_PROJECT_ROOT, PARENT / 'PUBLIC-PROBE-CLOSURE.json')).read_text())
    assert old['complete_all_windows'] and len(cases) == len(old['rows']) == 38
    for case, reference in zip(cases, old['rows']):
        assert case['label'] == reference['label']
        case['parent_reference'] = {
            'first_action': reference['first_action'], 'scores': reference['scores'],
            'view_sha256': reference['view_sha256'],
        }
    targets = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-CAUSAL-FEEDBACK.json')).read_text())['rows']
    for row in targets:
        result = row['result']
        cases.append({'label': result['root_id'], 'observation': row['public_observation'],
                      'window_key': row['source_window'], 'causal_teacher_result': result,
                      'parent_reference': {'first_action': result['original_parent_first'],
                          'scores': [{'action_key': c['action_key'], 'score': c['score'],
                                      'trace': c['trace']['detail']} for c in row['original_full_scores_and_traces']],
                          'view_sha256': row['original_full_view_sha256']}})
    assert len(cases) == 56 and len({case['label'] for case in cases}) == 56
    return cases, [public, fixture_plan, fixture, natural, _project_file(_PROJECT_ROOT, PARENT / 'PUBLIC-PROBE-CLOSURE.json'),
                   _project_file(_PROJECT_ROOT, HERE / 'PUBLIC-CAUSAL-FEEDBACK.json')]


def main():
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED.json')).read_text())
    for name, digest in preparation['frozen_files'].items():
        assert pin(name) == digest, name
    delivered = {name: pin(_project_file(_PROJECT_ROOT, HERE / name)) for name in
                 ('RAW-REPLY.txt', 'candidate.py', 'STATIC-CHECKS.json', 'AUTHOR-NOTE.md')}
    save('ROOT-AUTHOR-REPLY-FIRST-SEAL.json', {
        'schema': 't75-root-original-delivery/1', 'files': delivered,
        'delivered_at_utc': datetime.now(timezone.utc).isoformat(),
        'actual_author_delegations_this_step': 1, 'proposal_number_in_new_joint_batch': 1,
        'requested_model': 'gpt-6.1-sol', 'requested_effort': 'max',
        'underlying_model_calls_and_tokens': None, 'actual_new_scores_before_seal': 0,
        'strength_or_admission': False,
    })
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'S01-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    parent_path = _project_file(_PROJECT_ROOT, PARENT / 'S02-model-output')
    parents = load_vip_parents([parent_path], batch)
    assert canonical(parents) == canonical(json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENTS-FROZEN.json')).read_text()))
    raw = (_project_file(_PROJECT_ROOT, HERE / 'RAW-REPLY.txt')).read_text()
    parsed = parse_vip_eoh_reply(raw, 'm1', parents)
    assert parsed['source_raw'].encode() == (_project_file(_PROJECT_ROOT, HERE / 'candidate.py')).read_bytes()
    assert len(parsed['source'].encode()) <= 65536
    ActionValueExecutor(parsed['source'], max_operations=batch.max_operations,
                        max_local_collection_size=batch.projection_limits.max_nodes)
    feedback = (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt')).read_text()
    packet, _ = build_vip_eoh_prompt(batch, 'm1', parents, feedback)
    assert packet.sha256 == preparation['prompt_sha256']
    assert packet.sha256 == pin(_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission/prompt.txt'))['sha256']
    save('ROOT-LOAD-PREFLIGHT.json', {'status': 'parser_constructor_pass', 'actual_new_scores': 0,
        'source_raw_byte_identity': True, 'prompt_sha256': packet.sha256,
        'parent_candidate_id': parents[0]['identity']['candidate_id']})
    save('REPLAY-ENVELOPE.json', {
        'schema': 'sitin-generation-reply/1', 'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'origin': 'delegated_model_reply', 'provider': 'codex-collaboration',
        'model': 'unknown', 'finish_reason': 'stop', 'prompt_sha256': packet.sha256,
        'reply': raw, 'delegator': '/root via /root/t75_sol_max_net_upgrade_author',
        'note': 'Original author attestation; underlying usage unknown; replay requests no new model.',
    })
    record = run_vip_eoh_generate(batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S01-model-output'),
        operator='m1', parent_paths=[parent_path], backend='replay', feedback=feedback,
        reply_file=_project_file(_PROJECT_ROOT, HERE / 'REPLAY-ENVELOPE.json'))
    assert record['status'] == 'loaded_not_admitted', record['error']
    child = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / 'S01-model-output')], batch)[0]
    assert child['source'] == parsed['source']
    save('CURRENT-CANDIDATE-PACKAGE.json', {
        'relative_package': 'S01-model-output', 'relative_batch': 'S01-generation.batch.json',
        'candidate_identity': child['identity'], 'true_parent_identity': parents[0]['identity'],
        'probe_closure': 'PUBLIC-PROBE-CLOSURE.json', 'strength_or_release': False,
    })
    cases, source_files = public_cases()
    frozen = {str(path): pin(path) for path in [Path(__file__), *source_files]}
    save('PUBLIC-PROBE-START.json', {
        'schema': 't75-full-public-probe-plan/1', 'candidate_identity': child['identity'],
        'parent_identity': parents[0]['identity'], 'requested_actual_windows': 56,
        'max_actual_score_calls': 56, 'source_files': frozen, 'normal_r18_fallback_allowed': False,
        'scope': '38 old controls and 18 causal public targets; no gold actions or strength credit',
        'new_model_world_table_calls': 0,
    })
    executor = ActionValueExecutor(child['source'], max_operations=batch.max_operations,
                                   max_local_collection_size=batch.projection_limits.max_nodes)
    rows, actual_scores, actual_rules, actual_views = [], 0, 0, 0
    primary = None
    try:
        with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz'), 'xb') as archive:
            for index, case in enumerate(cases):
                reference = case['parent_reference']
                begin = time.perf_counter()
                item = {'case_index': index, 'label': case['label'], 'status': 'unscored',
                        'parent_first_action': reference['first_action']}
                try:
                    obs = observation_from_json(case['observation'])
                    key = window_key_from_json(case['window_key'])
                    actual_rules += 1
                    rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    request = DecisionRequest(obs,
                        CompetitionContext('T75-full-public-probe', None, None, None, None, (), 0),
                        rules, case['label'], key.trigger_seq, key, ())
                    actual_views += 1
                    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    dto = view.candidate_view()
                    digest = hashlib.sha256(canonical(dto)).hexdigest()
                    archive.write(canonical({'label': case['label'], 'view_sha256': digest,
                                             'candidate_view': dto}) + b'\n')
                    archive.flush()
                    item.update(view_sha256=digest, saved_before_score=True, node_count=len(view.nodes))
                    assert digest == reference['view_sha256'], 'public input changed'
                    actual_scores += 1
                    scored = executor.score_vip_route(view)
                    entries = [{'action_key': e.action_key, 'score': e.score, 'trace': e.trace} for e in scored.entries]
                    full = {e.action_key for e in scored.entries} == {a.action_key for a in view.actions}
                    first = sorted(entries, key=lambda e: (-e['score'], e['action_key']))[0]['action_key']
                    item.update(status=scored.status, scores=entries, full_legal_keys=full,
                                first_action=first, behavior_changed=first != reference['first_action'],
                                operations=executor.last_operation_count, parent_scores=reference['scores'])
                    assert full and scored.status == 'SCORED'
                except Exception as exc:
                    item.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
                item['duration_wall_ms'] = 1000 * (time.perf_counter() - begin)
                rows.append(item)
                print({k: item.get(k) for k in ('label', 'status', 'first_action', 'behavior_changed', 'operations', 'error')}, flush=True)
    except BaseException as exc:
        primary = exc
    captures, readback_error = {}, None
    try:
        with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz'), 'rt') as archive:
            for line in archive:
                row = json.loads(line)
                assert row['label'] not in captures
                assert hashlib.sha256(canonical(row['candidate_view'])).hexdigest() == row['view_sha256']
                captures[row['label']] = row['view_sha256']
    except BaseException as exc:
        readback_error = type(exc).__name__ + ': ' + str(exc)
    stable = batch.identity(child['source']) == child['identity']
    stable &= all(pin(_project_file(_PROJECT_ROOT, HERE / name)) == digest for name, digest in delivered.items())
    stable &= all(pin(name) == digest for name, digest in frozen.items())
    stable &= all(pin(name) == digest for name, digest in preparation['frozen_files'].items())
    complete = primary is None and readback_error is None and stable
    complete &= actual_scores == len(rows) == len(captures) == actual_rules == actual_views == 56
    complete &= all(r['status'] == 'SCORED' and r['full_legal_keys'] for r in rows)
    save('PUBLIC-PROBE-CLOSURE.json', {
        'schema': 't75-full-public-probe-closure/1', 'candidate_identity': child['identity'],
        'parent_identity': parents[0]['identity'], 'complete_all_windows': complete,
        'identity_stable': stable, 'actual_score_calls': actual_scores,
        'actual_rule_calls': actual_rules, 'actual_projection_calls': actual_views,
        'actual_full_inputs_readback': len(captures), 'rows': rows,
        'changed_windows': [r['label'] for r in rows if r.get('behavior_changed')],
        'input_archive': pin(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz')),
        'primary_error': None if primary is None else type(primary).__name__ + ': ' + str(primary),
        'readback_error': readback_error, 'normal_r18_fallbacks': 0,
        'new_model_world_table_calls': 0, 'strength_admission_release_claim': False,
        'timing_scope': 'offline, not actual online deadlines',
    })
    if primary is not None:
        raise primary
    print({'complete': complete, 'actual_scores': actual_scores, 'actual_full_inputs': len(captures)}, flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
