"""一次作者原答签收、标准包落盘与22个实际V3开发窗评分，不启动世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t48-v3-natural-highfan-joint-author-1'

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
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, parse_vip_eoh_reply, build_vip_eoh_prompt, run_vip_eoh_generate, load_vip_parents
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE=Path(__file__).resolve().parent


def pin(path):
    raw=path.read_bytes()
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def save(name,value):
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False); f.write('\n')


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def main():
    if json.loads((_project_file(_PROJECT_ROOT, HERE/'ROOT-AUTHOR-DELIVERY.json')).read_text())['status']!='FINAL_ANSWER_delivered_one_original':
        raise ValueError('尚未收到作者最终原答')
    batch_path=_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'); batch=VipEohBatch.read(batch_path)
    seal=json.loads((_project_file(_PROJECT_ROOT, HERE/'AUTHOR-ROOT-SEAL.json')).read_text())
    for name,sha in seal['input_files'].items():
        assert pin(_project_file(_PROJECT_ROOT, HERE/name))['sha256']==sha,name
    delivery=json.loads((_project_file(_PROJECT_ROOT, HERE/'ROOT-AUTHOR-DELIVERY.json')).read_text())
    for name,digest in delivery['files'].items(): assert pin(_project_file(_PROJECT_ROOT, HERE/name))==digest,name
    if (_project_file(_PROJECT_ROOT, HERE/'ROOT-AUTHOR-REPLY-FIRST-SEAL.json')).exists():
        first=json.loads((_project_file(_PROJECT_ROOT, HERE/'ROOT-AUTHOR-REPLY-FIRST-SEAL.json')).read_text())
        assert first['files']==delivery['files']
    else:
        save('ROOT-AUTHOR-REPLY-FIRST-SEAL.json',{'files':{name:pin(_project_file(_PROJECT_ROOT, HERE/name)) for name in delivery['files']},
            'captured_at_utc':datetime.now(timezone.utc).isoformat(),'actual_author_delegations':1,
            'requested_model':'gpt-6.1-sol','requested_effort':'max','actual_backend_model_and_tokens':'unknown',
            'business_scores_before_seal':0,'repair_calls':0})
    raw=(_project_file(_PROJECT_ROOT, HERE/'RAW-REPLY.txt')).read_text(); parsed=parse_vip_eoh_reply(raw,'i1',[])
    assert parsed['source_raw'].encode()==(_project_file(_PROJECT_ROOT, HERE/'candidate.py')).read_bytes()
    assert len(parsed['source'].encode())<=65536
    executor=ActionValueExecutor(parsed['source'],max_operations=batch.max_operations,
                                 max_local_collection_size=batch.projection_limits.max_nodes)
    feedback=(_project_file(_PROJECT_ROOT, HERE/'FROZEN-FEEDBACK.txt')).read_text()
    packet,_=build_vip_eoh_prompt(batch,'i1',[],feedback)
    assert packet.sha256==seal['input_files']['S01-prompt-emission/prompt.txt']
    save('ROOT-LOAD-PREFLIGHT.json',{'status':'parser_constructor_pass','actual_scores':0,
        'source_raw_byte_identity':True,'prompt_sha256':packet.sha256,'source_sha256':hashlib.sha256(parsed['source'].encode()).hexdigest()})
    save('REPLAY-ENVELOPE.json',{'schema':'sitin-generation-reply/1','captured_at_utc':datetime.now(timezone.utc).isoformat(),
        'origin':'delegated_model_reply','provider':'codex-collaboration','model':'unknown',
        'finish_reason':'stop','prompt_sha256':packet.sha256,'reply':raw,
        'note':'root final delivery attestation; not vendor finish or token metadata; replay makes zero new model calls'})
    run_vip_eoh_generate(batch_file=batch_path,out_dir=_project_file(_PROJECT_ROOT, HERE/'S01-model-output'),operator='i1',backend='replay',
                         feedback=feedback,reply_file=_project_file(_PROJECT_ROOT, HERE/'REPLAY-ENVELOPE.json'))
    probe_candidate('S01-model-output')


def probe_candidate(package_name, *, batch_name='S01-generation.batch.json', output_prefix=''):
    """标准包已装载后，独立运行真实公开窗；不再调用作者或重复包装。"""
    batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE/batch_name))
    candidate=load_vip_parents([_project_file(_PROJECT_ROOT, HERE/package_name)],batch)[0]
    parsed=parse_vip_eoh_reply((_project_file(_PROJECT_ROOT, HERE/'RAW-REPLY.txt')).read_text(),'i1',[])
    executor=ActionValueExecutor(candidate['source'],max_operations=batch.max_operations,
                                 max_local_collection_size=batch.projection_limits.max_nodes)
    identity=candidate['identity']
    assert candidate['source']==parsed['source']
    cases=json.loads((_project_file(_PROJECT_ROOT, HERE/'PUBLIC-CASES.json')).read_text())['cases']
    reference=json.loads((_project_file(_PROJECT_ROOT, HERE/'AUTHOR-INPUT-SUMMARY.json')).read_text())
    previous_plan=json.loads((_project_file(_PROJECT_ROOT, HERE.parent/'t47-integrated-graph-and-preparation-1/PLAN.json')).read_text())
    previous_fixture=_project_file(_PROJECT_ROOT, REPO_ROOT/previous_plan['fixture_path'])
    for i,item in enumerate(json.loads(previous_fixture.read_text())['rows']):
        failed=item['actual_failed_row']
        cases.append({'label':f'T39-original-multigang-{i}', 'observation':failed['observation'],
            'window_key':failed['window_key'],'expected_legal_action_keys':failed['legal_action_keys'],
            'source_path':str(previous_fixture),'source_sha256':pin(previous_fixture)['sha256']})
    assert len(cases)==22
    save(output_prefix+'PUBLIC-PROBE-START.json',{'schema':'t48-root-public-probe/1','requested_actual_windows':22,
        'candidate_identity':identity,'frozen_files':{str(_project_file(_PROJECT_ROOT, HERE/name)):pin(_project_file(_PROJECT_ROOT, HERE/name)) for name in
            ('PUBLIC-CASES.json','AUTHOR-INPUT-SUMMARY.json','RAW-REPLY.txt','candidate.py','S01-generation.batch.json')},
        'scope':'exposed public development observations, not golden actions or independent strength',
        'model_world_table_calls':0,'script_digest':pin(Path(__file__))})
    rows=[]
    archive_name=output_prefix+'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz'
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/archive_name),'wb') as output:
        for i,row in enumerate(cases):
            begin=time.perf_counter()
            item={'case_index':i,'label':row['label'],'status':'unscored','scores':[]}
            try:
                obs=observation_from_json(row['observation']);key=window_key_from_json(row['window_key'])
                rules=HangmaRules(batch.rule_config).analyze(obs,route_limits=batch.route_limits)
                request=DecisionRequest(obs,CompetitionContext('T48-public-probe',None,None,None,None,(),0),
                    rules,f'T48-score:{i}',key.trigger_seq,key,())
                view=build_vip_route_scoring_view(request,batch.rule_config,limits=batch.projection_limits)
                dto=view.candidate_view();raw_dto=canonical(dto);sha=hashlib.sha256(raw_dto).hexdigest()
                # 同一实际输入先存完整DTO，不能用另一手投影冒充评分输入。
                output.write(canonical({'case_index':i,'view_sha256':sha,'candidate_view':dto})+b'\n');output.flush()
                if i<20: assert sha==reference['cases'][i]['view_sha256']
                else: assert sorted(c.action_key for c in rules.legal_candidates)==sorted(row['expected_legal_action_keys'])
                score=executor.score_vip_route(view)
                item.update(status=score.status,operations=executor.last_operation_count,nodes=len(view.nodes),
                    view_sha256=sha,json_bytes=len(raw_dto),saved_before_score=True,
                    full_legal_keys={e.action_key for e in score.entries}=={a.action_key for a in view.actions},
                    scores=[{'action_key':e.action_key,'score':e.score,'trace':e.trace} for e in score.entries])
                ranked=sorted(score.entries,key=lambda e:(-e.score,e.action_key))
                item['first_action']=ranked[0].action_key if ranked else None
                if i<20:
                    refs=reference['cases'][i]['scores']
                    ref_first=sorted(refs,key=lambda x:(-x['score'],x['action_key']))[0]['action_key']
                    item.update(reference_first_action=ref_first,behavior_changed=item['first_action']!=ref_first)
            except (Exception,WorkloadExceeded) as exc:
                item.update(status='failed',error=type(exc).__name__+': '+str(exc))
            item['duration_wall_ms']=(time.perf_counter()-begin)*1000
            rows.append(item)
            print({'case':i,'status':item['status'],'first':item.get('first_action'),'changed':item.get('behavior_changed'),
                   'ops':item.get('operations')},flush=True)
    stable=batch.identity(parsed['source'])==identity
    complete=len(rows)==22 and all(r['status']=='SCORED' and r['full_legal_keys'] and r['saved_before_score'] for r in rows) and stable
    changed=any(r.get('behavior_changed',False) for r in rows)
    save(output_prefix+'PUBLIC-PROBE-CLOSURE.json',{'schema':'t48-root-public-probe-result/1','candidate_identity':identity,
        'requested_actual_windows':22,'completed_scores':sum(r['status']=='SCORED' for r in rows),
        'complete_all_windows':complete,'identity_stable':stable,'behavior_changed':changed,
        'changed_against_historical_reference_windows':[r['case_index'] for r in rows if r.get('behavior_changed')],
        'rows':rows,'candidate_view_archive':pin(_project_file(_PROJECT_ROOT, HERE/archive_name)),
        'strength_admission_release_claim':False,'new_models_worlds_tables':0})
    if not complete or not changed: raise SystemExit(1)


if __name__=='__main__': main()
