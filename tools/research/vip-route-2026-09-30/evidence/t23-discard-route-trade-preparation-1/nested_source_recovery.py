"""T23 纯读来源适配和已验收嵌套恢复；生产规则/图不变。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t23-discard-route-trade-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import gzip,hashlib,json,sys
HERE=Path(__file__).resolve().parent
E=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
CORE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1')
ORIGINAL=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t21-early-strict-choice-causal-preparation-1')
sys.path.insert(0,str(CORE));sys.path.insert(0,str(ORIGINAL))
from recover_natural_start import ROOT,canonical,fingerprint,read_json,require
from source_recovery import restore as base_restore
CLOSED=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t22-claim-opportunity-same-start-closure-1')
PREVIOUS=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t22-claim-opportunity-same-start-1')
CID='22611fe6943d83ed5448c799cd6fe2cfce032ecf8e90e04bb6a8131082abbd88'


def source_materials(bind):
    """从关闭原件恢复四个登记窗口的全部座位前缀，纯文件业务调用为零。"""
    selection=read_json(_project_file(_PROJECT_ROOT, HERE/'SOURCE-SELECTION.json'));old=read_json(_project_file(_PROJECT_ROOT, PREVIOUS/'PREPARED.json'))
    closed=read_json(_project_file(_PROJECT_ROOT, CLOSED/'ROOT-CLOSED-CHECK.json'));seal=read_json(_project_file(_PROJECT_ROOT, CLOSED/'RAW-FIRST-SEAL.json'))
    require(selection['status']=='pure_read_preparation_no_START' and not selection['selection_uses_terminal_scores'],'来源登记不同')
    require(closed['status']=='accepted_engineering_only' and closed['complete_single_hand_continuations']==80
            and closed['raw_seal_sha256']==fingerprint(_project_file(_PROJECT_ROOT, CLOSED/'RAW-FIRST-SEAL.json'))['sha256'],'T22来源未闭')
    require(old['packages']['Sol']['identity']['candidate_id']==CID,'源候选不是真T22')
    for path,expected in {**old['files'],**old['runtime_files'],**seal['files']}.items():
        require(fingerprint(Path(path))==expected,'闭批依赖/原件漂移: '+path);bind(Path(path))
    for path in (_project_file(_PROJECT_ROOT, HERE/'SOURCE-SELECTION.json'),_project_file(_PROJECT_ROOT, CLOSED/'ROOT-CLOSED-CHECK.json'),_project_file(_PROJECT_ROOT, CLOSED/'RAW-FIRST-SEAL.json')):bind(path)
    wanted={};roots=[]
    for selected in selection['selected']:
        path=Path(selected['file']);require(fingerprint(path)['sha256']==selected['sha256'],'选源文件漂移');bind(path)
        source=read_json(path);require(source['actual_source_candidate_id']==CID,'选源实际候选不同')
        require(hashlib.sha256(canonical(source['full_DTO'])).hexdigest()==source['full_view_sha256'],'完整输入摘要不同')
        key=(source['source_root_id'],source['source_variant']);wanted[key]=source
    advanced={k:[] for k in wanted};chosen={k:{} for k in wanted};scored={k:{} for k in wanted}
    with (_project_file(_PROJECT_ROOT, PREVIOUS/'calls-and-choices.jsonl')).open() as stream:
        for line in stream:
            row=json.loads(line);key=(row['root_id'],row.get('variant'))
            if key not in wanted or row.get('arm')!='Sol-C':continue
            if row['event']=='advance' and row['status']=='advanced':advanced[key].append(row)
            elif row['event']=='policy_choose':
                require(row['status']=='chosen','源动作未成功');w=canonical(row['window_key'])
                require(w not in chosen[key],'源窗口重复');chosen[key][w]=row
            elif row['event']=='score_call' and row['kind']=='C':
                require(row['status']=='SCORED' and row['input_capture']['saved_before_score'],'源评分未完成保存');w=canonical(row['window_key'])
                require(w not in scored[key],'源评分窗口重复');scored[key][w]=row
    for ordinal,selected in enumerate(selection['selected'],1):
        source=read_json(Path(selected['file']));key=(source['source_root_id'],source['source_variant'])
        base=next(r for r in old['roots'] if r['root_id']==source['source_root_id'])
        base_index=next(i for i,r in enumerate(old['roots'],1) if r['root_id']==base['root_id'])
        common_file=_project_file(_PROJECT_ROOT, PREVIOUS/f'root-{base_index:02d}'/source['source_variant']/'COMMON-START.json');common=read_json(common_file);bind(common_file)
        sample=common['sample_key'] if source['source_variant']!='old_original_unused' and source['source_variant']=='public_consistent_hidden_1' else None
        if sample is not None:require(sample==base['hidden_sample_namespace']+':hidden:1:'+base['root_id'],'原隐藏键不等')
        entries=advanced[key];indices=[i for i,row in enumerate(entries) if any(c['window_key']==source['target_window'] for c in row['choices'])]
        require(len(indices)==1,'目标推进帧不唯一');target_index=indices[0]
        def records(entry):
            result=[]
            for choice in entry['choices']:
                row=chosen[key].get(canonical(choice['window_key']))
                require(row is not None and row['selected_action_key']==choice['action_key'] and choice['action_key'] in row['legal_action_keys'],'缺实际合法完整动作收据')
                result.append({'window_key':choice['window_key'],'observation':row['observation'],'legal_action_keys':row['legal_action_keys'],'action_key':choice['action_key']})
            return result
        prefix=[{'revision':r['revision'],'records':records(r),'source_advanced_row':r} for r in entries[:target_index]]
        targets=records(entries[target_index]);target=next(r for r in targets if r['window_key']==source['target_window']);actual=scored[key][canonical(source['target_window'])]
        require(target['observation']==source['complete_actual_observation'] and target['legal_action_keys']==source['legal_action_keys'],'源全观察/合法键不等')
        require(actual['input_capture']['view_sha256']==source['full_view_sha256'] and 'hu' not in target['legal_action_keys'],'目标不是登记的无胡输入')
        require(set(actual['legal_action_keys'])==set(target['legal_action_keys']) and actual['ranking'][0]==target['action_key'],'源评分/选择不等')
        nested={'source_kind':'closed_T22_C_nested_public_start_not_natural_A','base_sample_key':sample,'prefix':prefix,'target_records':targets,
            'target_revision':entries[target_index]['revision'],'target_window':source['target_window'],'focal_observation':target['observation'],
            'nested_request_sha256':hashlib.sha256(canonical({k:target[k] for k in ('observation','window_key','legal_action_keys')})).hexdigest(),
            'source_projected_C_DTO_sha256':source['full_view_sha256'],'source_input_json_bytes':len(canonical(source['full_DTO'])),
            'source_C_cached_scores':{e['action_key']:e['score'] for e in actual['scores']['entries']},'source_C_candidate_id':CID,
            'source_old_closed_outcome_file':str((_project_file(_PROJECT_ROOT, PREVIOUS/f'root-{base_index:02d}'/source['source_variant']/'Sol-C-outcome.json')).resolve()),
            'source_actual_advance_index':target_index,'recovery_only_all_seat_receipts_not_candidate_or_model_inputs':True}
        material={k:base['source'][k] for k in ('match_spec','value_limits','expected_math_backend')}
        material.update(source_kind=nested['source_kind'],source_C_full_DTO_sha256=source['full_view_sha256'],
            source_C_input_json_bytes=nested['source_input_json_bytes'],source_C_cached_scores=nested['source_C_cached_scores'],
            target_window=source['target_window'],target_frame=targets,source_selected_first=target['action_key'])
        roots.append({'root_id':base['root_id']+':T23:'+source['source_stratum']+':'+str(source['target_window']['trigger_seq']),
            'mother_root':base['mother_root'],'source_kind':nested['source_kind'],'profile':source['source_stratum'],
            'base_root':base,'source':material,'nested_start':nested,'pool':base['pool'],'permutation':base['permutation'],
            'policy_metadata':base['policy_metadata'],'logical_labels':base['logical_labels'],
            'hidden_sample_namespace':'vip-t23-discard-route-abc-v1','selection_uses_terminal_score':False,
            'actual_current_white_count':source['focal_actual_white_count'],'original_nested_source_variant':source['source_variant']})
    require(len(roots)==4 and len({r['mother_root'] for r in roots})==3,'嵌套母根数不等')
    return roots,old


def restore_nested_start(*,root,world,old_target,rules,engine,batch,stage_snapshot,focal,event,call,output,directory):
    """START后按公共frame/analyze/advance恢复旧隐藏前缀，返回opaque共同句柄。

    每帧复核版本、全部窗口、完整玩家观察和合法键。动作只匹配唯一规则
    候选，不解析牌码；保留成功推进日志，任何不符立即抛错，不改选来源。
    """
    from hangma_bot.kernel.serialization import observation_to_json,window_key_to_json
    from hangma_bot.simulation.interface import SimulationChoice
    from hangma_bot.offline.evaluate import frame_observation_summary
    nested=root['nested_start']
    old_frame=call('recovery:nested_frame_calls',engine.frame,world)
    before=[observation_to_json(d.observation) for d in old_frame.decisions if d.window_key==old_target]
    require(len(before)==1,'原登记起点完整焦点窗口缺失')
    if nested['base_sample_key'] is not None:
        world=call('recovery:nested_hidden_resample_calls',engine.resample_public_consistent_hidden_world,
            world,focal_seat=focal,sample_key=nested['base_sample_key'])
    initial=call('recovery:nested_frame_calls',engine.frame,world)
    require([observation_to_json(d.observation) for d in initial.decisions if d.window_key==old_target]==before,
        '恢复登记世界改变完整焦点观察')
    def check(frame,revision,records):
        require(frame.blocked_reason is None and frame.final_scores is None and frame.revision==revision,
            '嵌套前缀提前终局/阻塞/版本不同')
        require(canonical([window_key_to_json(d.window_key) for d in frame.decisions])
            ==canonical([r['window_key'] for r in records]),'嵌套前缀完整同期窗口不同')
        analyses=[]
        for decision,old in zip(frame.decisions,records):
            require(canonical(observation_to_json(decision.observation))==canonical(old['observation']),
                '嵌套前缀完整观察canonical字节不同')
            analysis=rules.analyze(decision.observation,route_limits=batch.route_limits)
            require(analysis.completeness.value=='complete'
                and sorted(c.action_key for c in analysis.legal_candidates)==sorted(old['legal_action_keys']),
                '嵌套前缀规则不完整/全合法键不同')
            analyses.append(analysis)
        return analyses
    completed=0
    try:
        for ordinal,entry in enumerate(nested['prefix'],1):
            frame=call('recovery:nested_frame_calls',engine.frame,world)
            analyses=check(frame,entry['revision'],entry['records']);choices=[]
            for decision,old,analysis in zip(frame.decisions,entry['records'],analyses):
                candidates=[c for c in analysis.legal_candidates if c.action_key==old['action_key']]
                require(len(candidates)==1,'旧动作当前不唯一合法')
                choices.append(SimulationChoice(decision.window_key,candidates[0].action))
            receipt={'event':'nested_prefix_advance','ordinal':ordinal,'revision':frame.revision,
                'choices':entry['source_advanced_row']['choices']}
            event({**receipt,'status':'advance_pending'})
            world=call('recovery:nested_world_advance_calls',engine.advance,world,frame.revision,tuple(choices))
            completed=ordinal;event({**receipt,'status':'advanced'})
        frame=call('recovery:nested_frame_calls',engine.frame,world)
        check(frame,nested['target_revision'],nested['target_records'])
        targets=[d for d in frame.decisions if window_key_to_json(d.window_key)==nested['target_window']]
        require(len(targets)==1 and canonical(observation_to_json(targets[0].observation))
            ==canonical(nested['focal_observation']),'嵌套目标完整焦点观察canonical字节不同')
        snapshot=dict(stage_snapshot,observation_summary=frame_observation_summary(frame),
            nested_start_scope=nested['source_kind'])
        output.save(directory/'NESTED-START.json',{'status':'restored_closed_nested_start','successful_prefix_advances':completed,
            'base_sample_key':nested['base_sample_key'],'target_revision':frame.revision,'target_window':nested['target_window'],
            'focal_observation':nested['focal_observation'],'nested_request_sha256':nested['nested_request_sha256'],
            'not_new_natural_A_source':True,'history_posterior':False})
        return world,targets[0].window_key,snapshot
    except BaseException as exc:
        event({'event':'nested_prefix_failed','successful_prefix_advances':completed,
            'error':type(exc).__name__+': '+str(exc)});raise

def restore(*,root,rules,engine,batch,output,directory,event,call):
    """先恢复原C起点，再按记录的世界及真实全座位前缀恢复新边界。"""
    world,old_target,snapshot=base_restore(root=root['base_root'],rules=rules,engine=engine,batch=batch,
        output=output,directory=directory,event=event,call=call)
    return restore_nested_start(root=root,world=world,old_target=old_target,rules=rules,engine=engine,batch=batch,
        stage_snapshot=snapshot,focal=root['source']['target_window']['seat'],event=event,call=call,output=output,directory=directory)
