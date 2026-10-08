"""签收一份联合原答并完整评分38个已曝光公开窗口。

模型原答先验字节，标准包只重放装载，不新增模型请求。实际完整DTO在
评分前保存；父参考仅比较行为，不是金标。失败全保留，不推进任何世界。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t62-earned-highfan-joint-revision-preparation-1'

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
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t59-qualifier-highfan-credit-author-1')
PUBLIC = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t48-v3-natural-highfan-joint-author-1')
NATURAL = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t58-qualifier-result-mechanism-1')


def canonical(value):
    """规范JSON统一tuple/list，拒绝非有限数，不作分数容差替换。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main():
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED.json')).read_text())
    for name, digest in preparation['frozen_files'].items():
        assert pin(Path(name)) == digest, name
    delivered = {name: pin(_project_file(_PROJECT_ROOT, HERE / name)) for name in
                 ('RAW-REPLY.txt', 'candidate.py', 'STATIC-CHECKS.json', 'AUTHOR-NOTE.md')}
    save('ROOT-AUTHOR-REPLY-FIRST-SEAL.json', {
        'schema': 't59-root-original-delivery/1', 'files': delivered,
        'delivered_at_utc': datetime.now(timezone.utc).isoformat(),
        'actual_author_delegations_this_step': 1, 'actual_author_delegations_in_joint_batch': 2, 'requested_model': 'gpt-6.1-sol',
        'requested_effort': 'max', 'underlying_model_calls_and_tokens': None,
        'actual_new_scores_before_seal': 0, 'strength_or_admission': False,
    })
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'S02-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    parent_path = _project_file(_PROJECT_ROOT, PARENT / 'S01-model-output')
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
    assert packet.sha256 == pin(_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission/prompt.txt'))['sha256']
    save('ROOT-LOAD-PREFLIGHT.json', {
        'status': 'parser_constructor_pass', 'actual_new_scores': 0,
        'source_raw_byte_identity': True, 'prompt_sha256': packet.sha256,
        'parent_candidate_id': parents[0]['identity']['candidate_id'],
    })
    save('REPLAY-ENVELOPE.json', {
        'schema': 'sitin-generation-reply/1',
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'origin': 'delegated_model_reply', 'provider': 'codex-collaboration',
        'model': 'unknown', 'finish_reason': 'stop', 'prompt_sha256': packet.sha256,
        'reply': raw, 'delegator': '/root via /root/t59_sol_max_joint_highfan_credit_author',
        'note': 'Root final delivery attestation; underlying usage unknown; replay makes zero new model calls.',
    })
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S02-model-output'), operator='m1',
        parent_paths=[parent_path], backend='replay', feedback=feedback,
        reply_file=_project_file(_PROJECT_ROOT, HERE / 'REPLAY-ENVELOPE.json'),
    )
    assert record['status'] == 'loaded_not_admitted', record['error']
    child = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / 'S02-model-output')], batch)[0]
    assert child['source'] == parsed['source']
    save('CURRENT-CANDIDATE-PACKAGE.json', {
        'relative_package': 'S02-model-output', 'relative_batch': 'S02-generation.batch.json',
        'candidate_identity': child['identity'], 'true_parent_identity': parents[0]['identity'],
        'probe_closure': 'PUBLIC-PROBE-CLOSURE.json', 'strength_or_release': False,
    })
    cases = json.loads((_project_file(_PROJECT_ROOT, PUBLIC / 'PUBLIC-CASES.json')).read_text())['cases']
    fixture_plan = _project_file(_PROJECT_ROOT, HERE.parent / 't47-integrated-graph-and-preparation-1/PLAN.json')
    fixture = _project_file(_PROJECT_ROOT, REPO_ROOT / json.loads(fixture_plan.read_text())['fixture_path'])
    for i, row in enumerate(json.loads(fixture.read_text())['rows']):
        failed = row['actual_failed_row']
        cases.append({'label': 'original-multigang-' + str(i),
                      'observation': failed['observation'], 'window_key': failed['window_key']})
    assert len(cases) == 22
    for i, case in enumerate(cases):
        case['label'] = 'public:' + str(i)
    natural = json.loads((_project_file(_PROJECT_ROOT, NATURAL / 'NATURAL-PUBLIC-CASES.json')).read_text())['cases']
    assert len(natural) == 16
    for i, case in enumerate(natural):
        case['label'] = 'natural:' + format(i, '02')
        cases.append(case)
    parent_closed = json.loads((_project_file(_PROJECT_ROOT, PARENT / 'PUBLIC-PROBE-CLOSURE.json')).read_text())
    assert parent_closed['complete_all_windows']
    assert parent_closed['candidate_identity'] == parents[0]['identity']
    old_rows = parent_closed['rows']
    assert [r['label'] for r in old_rows] == [r['label'] for r in cases]
    references = [{'view_sha256': r['view_sha256'], 'first_action': r['first_action'],
                   'scores': r['scores']} for r in old_rows]
    frozen = {str(path): pin(path) for path in
              (Path(__file__), _project_file(_PROJECT_ROOT, PUBLIC / 'PUBLIC-CASES.json'), fixture_plan, fixture,
               _project_file(_PROJECT_ROOT, PARENT / 'PUBLIC-PROBE-CLOSURE.json'),
               _project_file(_PROJECT_ROOT, NATURAL / 'NATURAL-PUBLIC-CASES.json'), _project_file(_PROJECT_ROOT, NATURAL / 'PARENT-REPLAY-CLOSURE.json'))}
    save('PUBLIC-PROBE-START.json', {
        'schema': 't62-full-public-probe-plan/1', 'candidate_identity': child['identity'],
        'parent_identity': parents[0]['identity'], 'requested_actual_windows': 38,
        'max_actual_score_calls': 38, 'source_files': frozen, 'normal_r18_fallback_allowed': False,
        'scope': 'known public cases and real full inputs, no gold action or strength/deadline credit',
        'new_model_world_table_calls': 0,
    })
    executor = ActionValueExecutor(child['source'], max_operations=batch.max_operations,
                                   max_local_collection_size=batch.projection_limits.max_nodes)
    rows, actual_scores = [], 0
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz'), 'xb') as archive:
        for i, (case, old) in enumerate(zip(cases, references)):
            begin = time.perf_counter()
            item = {'case_index': i, 'label': case['label'], 'status': 'unscored',
                    'parent_first_action': old['first_action']}
            try:
                obs = observation_from_json(case['observation'])
                key = window_key_from_json(case['window_key'])
                rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                request = DecisionRequest(obs,
                    CompetitionContext('T62-full-public-probe', None, None, None, None, (), 0),
                    rules, case['label'], key.trigger_seq, key, ())
                view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                dto = view.candidate_view()
                digest = hashlib.sha256(canonical(dto)).hexdigest()
                archive.write(canonical({'label': case['label'], 'view_sha256': digest,
                                         'candidate_view': dto}) + b'\n')
                archive.flush()
                item.update(view_sha256=digest, saved_before_score=True, node_count=len(view.nodes))
                assert digest == old['view_sha256'], 'public input changed'
                actual_scores += 1
                scored = executor.score_vip_route(view)
                entries = [{'action_key': e.action_key, 'score': e.score, 'trace': e.trace} for e in scored.entries]
                full = {e.action_key for e in scored.entries} == {a.action_key for a in view.actions}
                first = sorted(entries, key=lambda e: (-e['score'], e['action_key']))[0]['action_key']
                item.update(status=scored.status, scores=entries, full_legal_keys=full,
                            first_action=first, behavior_changed=first != old['first_action'],
                            operations=executor.last_operation_count, parent_scores=old['scores'])
                assert full and scored.status == 'SCORED'
            except Exception as exc:
                item.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
            item['duration_wall_ms'] = 1000 * (time.perf_counter() - begin)
            rows.append(item)
            print({k: item.get(k) for k in ('label', 'status', 'first_action', 'behavior_changed', 'operations', 'error')}, flush=True)
    captures = {}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz'), 'rt') as archive:
        for line in archive:
            row = json.loads(line)
            assert row['label'] not in captures
            assert hashlib.sha256(canonical(row['candidate_view'])).hexdigest() == row['view_sha256']
            captures[row['label']] = row['view_sha256']
    stable = batch.identity(child['source']) == child['identity']
    stable &= all(pin(_project_file(_PROJECT_ROOT, HERE / name)) == digest for name, digest in delivered.items())
    stable &= all(pin(Path(name)) == digest for name, digest in frozen.items())
    stable &= all(pin(Path(name)) == digest for name, digest in preparation['frozen_files'].items())
    complete = stable and actual_scores == len(rows) == len(captures) == 38
    complete &= all(r['status'] == 'SCORED' and r['full_legal_keys'] for r in rows)
    save('PUBLIC-PROBE-CLOSURE.json', {
        'schema': 't62-full-public-probe-closure/1', 'candidate_identity': child['identity'],
        'parent_identity': parents[0]['identity'], 'complete_all_windows': complete,
        'identity_stable': stable, 'actual_score_calls': actual_scores, 'actual_full_inputs_readback': len(captures),
        'rows': rows, 'changed_windows': [r['label'] for r in rows if r.get('behavior_changed')],
        'input_archive': pin(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz')),
        'normal_r18_fallbacks': 0, 'new_model_world_table_calls': 0,
        'strength_admission_release_claim': False, 'timing_scope': 'offline, not actual online deadlines',
    })
    print({'complete': complete, 'actual_scores': actual_scores, 'actual_full_inputs': len(captures)}, flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
