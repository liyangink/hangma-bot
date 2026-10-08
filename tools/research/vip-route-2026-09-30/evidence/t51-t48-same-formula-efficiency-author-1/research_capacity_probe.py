"""同源码离线研究档重绑定与真实22窗核验；不继承准入或改变线上预算。"""

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
from pathlib import Path
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json,window_key_from_json
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_generate import VipEohBatch,load_vip_parents
from hangma_bot.offline.vip_eoh_rebind import rebind_vip_research_budget
from hangma_bot.policy.action_value_executor import ActionValueExecutor,WorkloadExceeded
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
from root_load_and_probe import HERE,PARENT,save,pin,canonical

def main():
    assert json.loads((_project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-CLOSURE.json')).read_text())['complete_all_windows']
    assert json.loads((_project_file(_PROJECT_ROOT, HERE/'RECOVERY-NATURAL-EQUIVALENCE-CLOSURE.json')).read_text())['complete']
    raw=json.loads((_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json')).read_text())
    raw.update(batch_id='vip-t51-same-source-research-4800000-20261002',max_operations=4800000)
    save('S01-research.batch.json',raw)
    record=rebind_vip_research_budget(source_batch_file=_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'),
        source_package=_project_file(_PROJECT_ROOT, HERE/'S01-model-output'),target_batch_file=_project_file(_PROJECT_ROOT, HERE/'S01-research.batch.json'),
        out_dir=_project_file(_PROJECT_ROOT, HERE/'S01-research-capacity'),execution_evidence_files=[_project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-CLOSURE.json'),
            _project_file(_PROJECT_ROOT, HERE/'RECOVERY-NATURAL-EQUIVALENCE-CLOSURE.json')])
    assert record['status']=='loaded_not_admitted'
    batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE/'S01-research.batch.json'))
    candidate=load_vip_parents([_project_file(_PROJECT_ROOT, HERE/'S01-research-capacity')],batch)[0]
    save('CURRENT-RESEARCH-CANDIDATE-PACKAGE.json',{'relative_package':'S01-research-capacity',
        'relative_batch':'S01-research.batch.json','probe_closure':'RESEARCH-PUBLIC-PROBE-CLOSURE.json',
        'candidate_identity':candidate['identity'],'same_source_as_normal_package':True,'model_calls':0,
        'admission_or_deadline_credit':False,'reason':'Long offline study preserves headroom for unseen expensive windows; online deadline remains separate.'})
    start=json.loads((_project_file(_PROJECT_ROOT, HERE/'AUTHOR-START.json')).read_text())
    files=json.loads((_project_file(_PROJECT_ROOT, HERE/'ROOT-AUTHOR-REPLY-FIRST-SEAL.json')).read_text())['files']
    cases = json.loads((PARENT / 'PUBLIC-CASES.json').read_text())['cases']
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE.parent / 't47-integrated-graph-and-preparation-1/PLAN.json')).read_text())
    for i, row in enumerate(json.loads((_project_file(_PROJECT_ROOT, REPO_ROOT / plan['fixture_path'])).read_text())['rows']):
        old = row['actual_failed_row']
        cases.append({'label': 'T39-original-multigang-' + str(i),
                      'observation': old['observation'], 'window_key': old['window_key']})
    expected = json.loads((_project_file(_PROJECT_ROOT, HERE / 'RESEARCH-PUBLIC-PROBE-CLOSURE.json')).read_text())['rows']
    assert len(cases) == len(expected) == 22
    save('RESEARCH-PUBLIC-PROBE-START.json', {
        'requested_windows': 22, 'candidate_identity': candidate['identity'],
        'same_source_reference_research_capacity_not_parent_identity':
            json.loads((PARENT / 'CURRENT-RESEARCH-CANDIDATE-PACKAGE.json').read_text())['candidate_identity']['candidate_id'],
        'compare': 'all scores and canonical traces exactly; input SHA equal',
        'scope': 'exposed public development; no strength or online deadline credit',
        'script_digest': pin(Path(__file__)), 'new_worlds_tables': 0,
    })
    executor = ActionValueExecutor(candidate['source'], max_operations=batch.max_operations,
                                   max_local_collection_size=batch.projection_limits.max_nodes)
    rows = []
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'RESEARCH-ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz'), 'xb') as archive:
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
    save('RESEARCH-PUBLIC-PROBE-CLOSURE.json', {
        'candidate_identity': candidate['identity'], 'requested_actual_windows': 22,
        'completed_scores': sum(r['status'] == 'SCORED' for r in rows),
        'complete_all_windows': complete, 'identity_stable': stable,
        'all_scores_and_canonical_traces_equal_to_t48': complete,
        'behavior_changed_against_t48': False,
        'behavior_changed_against_historical_t25': complete,
        'rows': rows, 'actual_input_archive': pin(_project_file(_PROJECT_ROOT, HERE / 'RESEARCH-ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz')),
        'strength_admission_release_claim': False, 'new_models_worlds_tables': 0,
        'timing_scope': 'offline observed; not online deadline gate',
    })
    if not complete:
        raise SystemExit(1)


if __name__=='__main__': main()
