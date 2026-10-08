"""纯文件闭合原失败费用、各修订输入和最终工程身份；不授上线。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t80-witness-capacity-failure-diagnostic-1'

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
import math
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch

HERE=Path(__file__).resolve().parent
AUTHOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')


def raw(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(1<<20),b''):h.update(part)
    return h.hexdigest()


def main():
    final=json.loads((_project_file(_PROJECT_ROOT, HERE/'r3-equivalence-56/CLOSURE.json')).read_text())
    timing=json.loads((_project_file(_PROJECT_ROOT, HERE/'r3-timing/baseline/CLOSURE.json')).read_text())
    failure=json.loads((_project_file(_PROJECT_ROOT, HERE/'T78-FAILURE-COST-CLOSURE.json')).read_text())
    assert final['complete'] and final['source_stable'] and final['actual_score_calls']==56
    assert timing['mathematical_complete'] and not timing['compute_deadline_pass']
    batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, AUTHOR/'S01-generation.batch.json'))
    identity=batch.identity((_project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output/candidate.py')).read_text())
    assert identity==final['runtime_identity']==timing['runtime_identity']
    fixed=json.loads((_project_file(_PROJECT_ROOT, HERE/'fixed-r3/CLOSURE.json')).read_text())
    assert fixed['status']=='SCORED' and fixed['full_legal_outputs'] and not fixed['degraded_reasons']
    reference=json.loads((_project_file(_PROJECT_ROOT, HERE/'reference-unpruned/CLOSURE.json')).read_text())
    assert fixed['scores']==reference['scores'] and fixed['operations']==reference['operations']
    assert '460 passed' in (_project_file(_PROJECT_ROOT, HERE/'PYTEST-R3.log')).read_text()
    archives,inputs={},0
    for path in sorted(HERE.rglob('ACTUAL-INPUTS.jsonl.gz')):
        count=0
        with gzip.open(path,'rt') as stream:
            for line in stream:
                row=json.loads(line);dto=row.get('view',row.get('candidate_view'))
                assert dto is not None and hashlib.sha256(raw(dto)).hexdigest()==row['view_sha256']
                keys=[a['action_key'] for a in dto['actions']]
                assert keys and len(keys)==len(set(keys));count+=1
        archives[str(path.relative_to(HERE))]={'inputs':count,'sha256':sha(path)};inputs+=count
    assert inputs==126
    final_outputs=sum(len(r['scores']) for r in final['rows'])+len(fixed['scores'])
    for row in timing['rows']:
        assert row['status']=='SCORED' and row['exact_all_legal_scores_traces_input_operations']
        final_outputs+=len(row['actual_scores'])
    for rows in ([r['scores'] for r in final['rows']], [fixed['scores']],
                 [r['actual_scores'] for r in timing['rows']]):
        assert all(type(r['score']) in (float,int) and math.isfinite(r['score']) for group in rows for r in group)
    snapshot=_project_file(_PROJECT_ROOT, HERE/'r3-source-snapshot')
    snapshot.mkdir(exist_ok=False)
    from hangma_bot.offline.scoring_sources import REPO_ROOT
    for name,entry in identity['source_manifest'].items():
        source=_project_file(_PROJECT_ROOT, REPO_ROOT/name);assert sha(source)==entry['sha256']
        dest=snapshot/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes())
    source=_project_file(_PROJECT_ROOT, REPO_ROOT/identity['contract_path']);assert sha(source)==identity['contract_sha256']
    dest=snapshot/identity['contract_path'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes())
    files={str(p.relative_to(HERE)):{'bytes':p.stat().st_size,'sha256':sha(p)}
           for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
           and p.name!='ROOT-READBACK.json'}
    result={'schema':'t80-failure-and-pruning-readback/1','complete':True,'runtime_identity':identity,
       'T78_started_complete_partial_tables':[250,249,1],'T78_completed_hands':failure['completed_hands'],
       'T78_confirmation_valid':False,'old_r1_r2_evidence_and_costs_preserved':True,
       'all_revisions_actual_choose_attempts':16,'all_revisions_actual_rules_projection_attempts':128,
       'all_revisions_actual_score_calls_and_input_captures':inputs,
       'final_r3_actual_rules_projection_score_calls':62,'final_r3_actual_full_inputs':62,
       'final_r3_finite_full_legal_outputs':final_outputs,'final_r3_test_count':460,
       'final_r3_reference_scores_traces_operations_exact':True,
       'final_r3_complex_compute_seconds':[r['wall_minus_capture_seconds'] for r in timing['rows'][:2]],
       'final_r3_complex_event_loop_lag_seconds':[r['event_loop_timer_lag_seconds'] for r in timing['rows'][:2]],
       'actual_default_compute_deadline_pass':False,'source_stable':True,'files':files,'archives':archives,
       'new_models_worlds_tables':0,'online_admission':False,
       'scope':'容量修复、公开面板与时限诊断；非自然强度或SSE/并发发布证据'}
    with (_project_file(_PROJECT_ROOT, HERE/'ROOT-READBACK.json')).open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')
    print({k:result[k] for k in ['complete','all_revisions_actual_score_calls_and_input_captures',
          'final_r3_actual_full_inputs','final_r3_finite_full_legal_outputs','actual_default_compute_deadline_pass']})


if __name__=='__main__':main()
