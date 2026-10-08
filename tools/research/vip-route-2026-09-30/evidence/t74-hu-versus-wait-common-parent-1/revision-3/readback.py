"""纯文件核验36实际臂、全输入、原尾段及胡／等真实结算，不新增业务。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t74-hu-versus-wait-common-parent-1/revision-3'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
from pathlib import Path
import gzip,hashlib,json,math
from prepare import HERE,canonical,pin,save

def read(path):return json.loads(Path(path).read_text())
def rows(path):
    with gzip.open(path,'rt') as stream:return [json.loads(line) for line in stream]

def main():
    plan,start,closed=(read(_project_file(_PROJECT_ROOT, HERE/name)) for name in ['PREPARED.json','START.json','CLOSURE.json'])
    assert closed['complete'] and closed['source_stable'] and closed['error'] is None and not closed['cleanup_errors']
    assert start['prepared_sha256']==pin(_project_file(_PROJECT_ROOT, HERE/'PREPARED.json'))['sha256'] and start['runner_sha256']==pin(_project_file(_PROJECT_ROOT, HERE/'run.py'))['sha256']
    for name,digest in plan['files'].items():assert pin(name)==digest,name
    for name,digest in closed['files'].items():assert pin(_project_file(_PROJECT_ROOT, HERE/name))==digest
    assert closed['scoring_input_capture']['terminal']['terminal_valid']
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/'SOURCE-MATERIALS.json.gz'),'rt') as stream:material=json.load(stream)['roots']
    decisions,events,views=(rows(_project_file(_PROJECT_ROOT, HERE/name)) for name in ['decisions.jsonl.gz','events.jsonl.gz','views.jsonl.gz'])
    assert len(material)==18 and len({r['mother_root'] for r in material})==16
    assert len(decisions)==closed['actual_explicit_api_counts']['actual_policy_decisions']
    by_sha={}
    for captured in views:
        raw=canonical(captured['view'])
        assert captured['schema']=='vip-scoring-input-view/1' and len(raw)==captured['json_bytes']
        assert hashlib.sha256(raw).hexdigest()==captured['view_sha256']
        assert captured['view_sha256'] not in by_sha;by_sha[captured['view_sha256']]=captured
    assert not any(e['event']=='batch_failed' for e in events)
    event_counts=Counter((e['event'],e.get('status')) for e in events)
    assert event_counts['continuation_start',None]==36
    for prefix in ['continuation','recovery']:
        assert event_counts[prefix+'_advance','pending']==event_counts[prefix+'_advance','advanced']
    calls,used,action_scores=set(),set(),0
    root_results=[];by_category={};by_mother={}
    for root in material:
        directory=_project_file(_PROJECT_ROOT, HERE/root['root_id'].replace(':','-'))
        recovered,result=(read(directory/name) for name in ['RECOVERY.json','ROOT-RESULT.json'])
        assert recovered['status']=='recovered' and recovered['full_target_observations_equal'] and recovered['source_window']==root['source_window']
        assert set(result['results'])=={'P','F'}
        for arm in plan['arm_order']:
            small=read(directory/(arm+'-RESULT.json'));outcome=read(directory/(arm+'-outcome.json'))
            assert small==result['results'][arm] and small['status']=='complete'
            assert outcome['status']=='complete' and outcome['completed_hands']==1 and all(v==0 for v in outcome['runtime_counts'].values())
            settlement=small['settlement']
            assert sum(settlement['score_delta'])==0
            assert [a+d for a,d in zip(settlement['scores_before'],settlement['score_delta'])]==settlement['scores_after']==outcome['final_scores']
            assert small['focal_net_score']==settlement['score_delta'][root['focal_seat']]
            audited=[d for d in decisions if d['root_id']==root['root_id'] and d['arm']==arm]
            assert len(audited)==small['actual_policy_decisions']==len(outcome['decisions'])
            targets=[d for d in audited if d['window_key']==root['source_window']]
            assert len(targets)==1 and targets[0]['observation']==root['focal_observation']
            for audit,actual in zip(audited,outcome['decisions']):
                assert audit['status']=='chosen' and not any('action_value_failed' in x for x in audit['degraded_reasons'])
                assert audit['window_key']==actual['window_key'] and audit['seat']==actual['seat']
                expected=root['forced_first'] if arm=='F' and audit['window_key']==root['source_window'] else audit['selected_action_key']
                assert actual['legal'] and actual['fallback_reason'] is None and actual['action_key']==expected and expected in audit['legal_action_keys']
                if audit.get('focal_vip'):
                    assert audit['c_self_scored'] and len(audit['scoring_calls'])==1
                    call=audit['scoring_calls'][0]
                    assert call['status']=='SCORED' and call['score_completed'] and call['full_legal_keys']
                    assert call['actual_score_calls']==1 and call['cumulative_failed_calls']==0
                    receipt=call['input_capture'];assert receipt['saved_before_score'] and receipt['error'] is None
                    assert receipt['store_call_no'] not in calls;calls.add(receipt['store_call_no'])
                    captured=by_sha[receipt['view_sha256']];assert captured['json_bytes']==receipt['json_bytes'];used.add(receipt['view_sha256'])
                    keys=[a['action_key'] for a in captured['view']['actions']]
                    assert set(keys)==set(call['scored_action_keys'])==set(audit['legal_action_keys'])
                    assert len(keys)==len(call['scored_action_keys'])==len(audit['candidates'])
                    assert all(type(c['score']) in (int,float) and math.isfinite(c['score']) for c in audit['candidates'])
                    action_scores+=len(keys)
                    assert sorted(audit['candidates'],key=lambda c:(-c['score'],c['action_key']))[0]['action_key']==audit['selected_action_key']
                    assert 0<call['candidate_operations']<=plan['parent_identity']['params']['max_operations']
            target=next(d for d in outcome['decisions'] if d['window_key']==root['source_window'])
            assert target['action_key']==small['executed_first'] and small['force_count']==(1 if arm=='F' else 0)
            actual_scores={c['action_key']:{'score':c['score'],'trace':c['trace']['detail']} for c in targets[0]['candidates']}
            assert canonical(actual_scores)==canonical(root['expected_parent_scores'])
            assert targets[0]['scoring_execution']['input_capture']['view_sha256']==root['expected_input_sha256']
            advances=[e for e in events if e['event']=='continuation_advance' and e['root_id']==root['root_id'] and e['arm']==arm and e['status']=='advanced']
            pending=[e for e in events if e['event']=='continuation_advance' and e['root_id']==root['root_id'] and e['arm']==arm and e['status']=='pending']
            assert len(advances)==small['successful_advances'] and [e['revision'] for e in pending]==[e['revision'] for e in advances]
            assert [(c['window_key'],c['action_key']) for e in pending for c in e['choices']]==[(d['window_key'],d['action_key']) for d in outcome['decisions']]
            if arm=='P':
                assert [(d['window_key'],d['selected_action_key'],d['observation']) for d in audited]==[(d['window_key'],d['selected_action_key'],d['observation']) for d in root['original_hand_suffix']]
        hu_arm='P' if root['parent_first']=='hu' else 'F';wait_arm='F' if hu_arm=='P' else 'P'
        assert result['H_alias_actual_arm']==hu_arm and result['W_alias_actual_arm']==wait_arm
        hu,wait=result['results'][hu_arm],result['results'][wait_arm]
        assert hu['executed_first']=='hu' and wait['executed_first']==root['wait_first']
        assert hu['settlement']['winner_seat']==root['focal_seat']
        assert hu['settlement']['fan']==root['public_facts']['current_hu_fan'] and hu['focal_net_score']==root['public_facts']['current_hu_net']
        delta=wait['focal_net_score']-hu['focal_net_score'];assert delta==result['wait_minus_hu']
        kind='draw' if wait['settlement']['is_draw'] else 'own_hu' if wait['settlement']['winner_seat']==root['focal_seat'] else 'opponent_hu'
        record={'root_id':root['root_id'],'mother_root':root['mother_root'],'category':root['category'],
            'wall':root['public_facts']['remaining_tile_count'],'white_count':root['public_facts']['white_count'],
            'original_parent_first':root['parent_first'],'wait_first':root['wait_first'],'hu_net':hu['focal_net_score'],'wait_net':wait['focal_net_score'],
            'wait_minus_hu':delta,'hu_fan':hu['settlement']['fan'],'wait_terminal_kind':kind,'wait_fan':wait['settlement']['fan'],
            'hu_arm':hu_arm,'wait_arm':wait_arm,'original_parent_full_tail_exact':True}
        root_results.append(record)
        by_mother.setdefault(root['mother_root'],[]).append(record)
        by_category.setdefault(root['category'],[]).append(record)
    assert len(root_results)==18 and len(closed['roots'])==18
    assert calls==set(range(1,closed['actual_explicit_api_counts']['actual_vip_score_calls']+1)) and used==set(by_sha)
    assert len(by_sha)==closed['scoring_input_capture']['unique_views_saved']
    def stats(values):return {'windows':len(values),'mothers':len({r['mother_root'] for r in values}),
        'wait_better':sum(r['wait_minus_hu']>0 for r in values),'wait_equal':sum(r['wait_minus_hu']==0 for r in values),'wait_worse':sum(r['wait_minus_hu']<0 for r in values),
        'wait_result_types':dict(Counter(r['wait_terminal_kind'] for r in values)),
        'descriptive_sum_wait_minus_hu':sum(r['wait_minus_hu'] for r in values),'not_natural_frequency_or_table_score_mean':True}
    files={str(p.relative_to(HERE)):pin(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='ROOT-READBACK.json' and '__pycache__' not in p.parts}
    output={'schema':'t74-root-pure-read-closure/1','complete':True,'source_stable':True,'completed_actual_continuations':36,'windows':18,'mothers':16,
        'actual_decision_rows':len(decisions),'actual_candidate_score_calls':len(calls),'actual_action_scores_read':action_scores,'unique_actual_full_inputs_verified':len(by_sha),
        'all_captured_receipts_advances_and_settlements_reconciled':True,'all18_original_parent_full_tails_exact':True,
        'all18_immediate_Hu_equals_original_public_current_payment':True,'roots':root_results,'descriptive_stats':stats(root_results),
        'by_public_category':{k:stats(v) for k,v in by_category.items()},'by_mother':{k:stats(v) for k,v in by_mother.items()},'files':files,
        'new_scores_world_advances_tables_models_in_readback':0,'new_independent_sources_or_natural_complete_tables':0,'normal_r18_fallbacks':0,'strength_or_online_release':False}
    save(_project_file(_PROJECT_ROOT, HERE/'ROOT-READBACK.json'),output)
    print({k:output[k] for k in ['complete','completed_actual_continuations','actual_candidate_score_calls','unique_actual_full_inputs_verified','actual_action_scores_read','descriptive_stats']})

if __name__=='__main__':main()
