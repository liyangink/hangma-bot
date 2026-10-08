"""签收同公式提速原答；真实重建22窗，完整输入先存，再对账全部评分和解释。"""

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
from datetime import datetime, timezone
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_generate import (
    VipEohBatch, build_vip_eoh_prompt, load_vip_parents,
    parse_vip_eoh_reply, run_vip_eoh_generate,
)
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE = Path(__file__).resolve().parent
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t48-v3-natural-highfan-joint-author-1')


def canonical(value):
    """规范JSON只统一运行时tuple和归档list，不作容差比较。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main():
    start = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-START.json')).read_text())
    for name, digest in start['frozen_files'].items():
        assert pin(Path(name))['sha256'] == digest, name
    files = {name: pin(_project_file(_PROJECT_ROOT, HERE / name)) for name in
             ('RAW-REPLY.txt', 'candidate.py', 'STATIC-CHECKS.json', 'AUTHOR-NOTE.md')}
    save('ROOT-AUTHOR-REPLY-FIRST-SEAL.json', {
        'files': files, 'delivered_at_utc': datetime.now(timezone.utc).isoformat(),
        'actual_author_delegations_this_batch': 2,
        'requested_model': 'gpt-6.1-sol', 'requested_effort': 'max',
        'actual_backend_model_and_tokens': 'unknown',
        'business_scores_before_seal': 0, 'new_formula_claim': False,
    })
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'S01-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    parent_path = _project_file(_PROJECT_ROOT, PARENT / 'S01-model-output-2')
    parents = load_vip_parents([parent_path], batch)
    assert parents[0]['identity']['candidate_id'] == start['parent_candidate_id']
    raw = (_project_file(_PROJECT_ROOT, HERE / 'RAW-REPLY.txt')).read_text()
    parsed = parse_vip_eoh_reply(raw, 'm1', parents)
    assert parsed['source_raw'].encode() == (_project_file(_PROJECT_ROOT, HERE / 'candidate.py')).read_bytes()
    assert len(parsed['source'].encode()) <= 65536
    ActionValueExecutor(parsed['source'], max_operations=batch.max_operations,
                        max_local_collection_size=batch.projection_limits.max_nodes)
    feedback = (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt')).read_text()
    packet, _ = build_vip_eoh_prompt(batch, 'm1', parents, feedback)
    assert packet.sha256 == start['prompt_sha256']
    save('ROOT-LOAD-PREFLIGHT.json', {
        'status': 'parser_constructor_pass', 'actual_scores': 0,
        'source_raw_byte_identity': True, 'prompt_sha256': packet.sha256,
        'true_generation_parent': start['parent_candidate_id'],
    })
    save('REPLAY-ENVELOPE.json', {
        'schema': 'sitin-generation-reply/1',
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'origin': 'delegated_model_reply', 'provider': 'codex-collaboration',
        'model': 'unknown', 'finish_reason': 'stop', 'prompt_sha256': packet.sha256,
        'reply': raw, 'delegator': '/root via /root/t48_sol_max_natural_highfan_joint_author',
        'note': 'Root final delivery attestation; vendor identity and usage unknown; replay has zero new model calls.',
    })
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S01-model-output'), operator='m1',
        parent_paths=[parent_path], backend='replay', feedback=feedback,
        reply_file=_project_file(_PROJECT_ROOT, HERE / 'REPLAY-ENVELOPE.json'),
    )
    assert record['status'] == 'loaded_not_admitted', record['error']
    candidate = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / 'S01-model-output')], batch)[0]
    save('CURRENT-CANDIDATE-PACKAGE.json', {
        'relative_package': 'S01-model-output', 'relative_batch': 'S01-generation.batch.json',
        'candidate_identity': candidate['identity'], 'probe_closure': 'PUBLIC-PROBE-CLOSURE.json',
        'same_formula_claim_pending': True, 'admission_release_claim': False,
    })
    cases = json.loads((_project_file(_PROJECT_ROOT, PARENT / 'PUBLIC-CASES.json')).read_text())['cases']
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE.parent / 't47-integrated-graph-and-preparation-1/PLAN.json')).read_text())
    for i, row in enumerate(json.loads((_project_file(_PROJECT_ROOT, REPO_ROOT / plan['fixture_path'])).read_text())['rows']):
        old = row['actual_failed_row']
        cases.append({'label': 'T39-original-multigang-' + str(i),
                      'observation': old['observation'], 'window_key': old['window_key']})
    expected = json.loads((_project_file(_PROJECT_ROOT, PARENT / 'RESEARCH-PUBLIC-PROBE-CLOSURE.json')).read_text())['rows']
    assert len(cases) == len(expected) == 22
    save('PUBLIC-PROBE-START.json', {
        'requested_windows': 22, 'candidate_identity': candidate['identity'],
        'same_source_reference_research_capacity_not_parent_identity':
            json.loads((_project_file(_PROJECT_ROOT, PARENT / 'CURRENT-RESEARCH-CANDIDATE-PACKAGE.json')).read_text())['candidate_identity']['candidate_id'],
        'compare': 'all scores and canonical traces exactly; input SHA equal',
        'scope': 'exposed public development; no strength or online deadline credit',
        'script_digest': pin(Path(__file__)), 'new_worlds_tables': 0,
    })
    executor = ActionValueExecutor(candidate['source'], max_operations=batch.max_operations,
                                   max_local_collection_size=batch.projection_limits.max_nodes)
    rows = []
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz'), 'xb') as archive:
        for i, case in enumerate(cases):
            begin = time.perf_counter()
            item = {'case_index': i, 'label': case['label'], 'status': 'unscored'}
            try:
                obs = observation_from_json(case['observation'])
                key = window_key_from_json(case['window_key'])
                rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                request = DecisionRequest(obs, CompetitionContext('T51-public-probe', None, None, None, None, (), 0),
                                          rules, 'T51-score:' + str(i), key.trigger_seq, key, ())
                view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                dto = view.candidate_view()
                sha = hashlib.sha256(canonical(dto)).hexdigest()
                archive.write(canonical({'case_index': i, 'view_sha256': sha, 'candidate_view': dto}) + b'\n')
                archive.flush()
                assert sha == expected[i]['view_sha256'], 'actual input changed'
                score = executor.score_vip_route(view)
                scores = [{'action_key': e.action_key, 'score': e.score, 'trace': e.trace} for e in score.entries]
                full = {e.action_key for e in score.entries} == {a.action_key for a in view.actions}
                equal = canonical(scores) == canonical(expected[i]['scores'])
                item.update(status=score.status, scores=scores, operations=executor.last_operation_count,
                            parent_operations=expected[i]['operations'], view_sha256=sha,
                            saved_before_score=True, full_legal_keys=full, all_scores_traces_equal=equal,
                            first_action=sorted(scores, key=lambda e: (-e['score'], e['action_key']))[0]['action_key'])
                assert full and equal, 'score or trace differs'
            except (Exception, WorkloadExceeded) as exc:
                item.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
            item['duration_wall_ms'] = (time.perf_counter() - begin) * 1000
            rows.append(item)
            print({k: item.get(k) for k in ('case_index', 'status', 'operations', 'parent_operations', 'all_scores_traces_equal')}, flush=True)
    stable = batch.identity(candidate['source']) == candidate['identity']
    assert all(pin(_project_file(_PROJECT_ROOT, HERE / name)) == digest for name, digest in files.items())
    assert all(pin(Path(name))['sha256'] == digest for name, digest in start['frozen_files'].items())
    complete = len(rows) == 22 and all(r['status'] == 'SCORED' and r['full_legal_keys']
                                      and r['all_scores_traces_equal'] for r in rows) and stable
    save('PUBLIC-PROBE-CLOSURE.json', {
        'candidate_identity': candidate['identity'], 'requested_actual_windows': 22,
        'completed_scores': sum(r['status'] == 'SCORED' for r in rows),
        'complete_all_windows': complete, 'identity_stable': stable,
        'all_scores_and_canonical_traces_equal_to_t48': complete,
        'behavior_changed_against_t48': False,
        'behavior_changed_against_historical_t25': complete,
        'rows': rows, 'actual_input_archive': pin(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz')),
        'strength_admission_release_claim': False, 'new_models_worlds_tables': 0,
        'timing_scope': 'offline observed; not online deadline gate',
    })
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
