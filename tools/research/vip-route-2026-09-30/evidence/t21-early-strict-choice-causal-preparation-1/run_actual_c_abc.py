"""T21 早期共同公开观察严格偏好诊断：4公开起点、2兼容世界、40五臂续打。

复用已闭五臂公开工具，不扩大规则/策略/来源接口；prepare只读文件，
execute消费根冻结 START。C来源明确，不冒充自然A或新独立母根。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t21-early-strict-choice-causal-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import asyncio
from collections import Counter
import hashlib
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
CORE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1')
T13=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1')
T16=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t16-conservative-lower-support-author-1')
sys.path.insert(0,str(CORE))
from recover_natural_start import ROOT,canonical,fingerprint,read_json,require,write_new
from run_abc_pilot import OutputLedger,ORDER
from abc_five_arm_core import run_five_arms
ORIGINAL=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t21-early-strict-choice-causal-preparation-1')
sys.path.insert(0,str(ORIGINAL))
from source_recovery import source_material,restore,SELECTED,NATURAL
T17=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t17-public-interruption-trade-author-1')
AUTHOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t19-maintained-ready-choice-author-1')
BATCH=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t19-maintained-ready-choice-author-1/S01-generation.batch.json')
PACKAGES={'S02':_project_file(_PROJECT_ROOT, T17/'S01-model-output')}
CIDS={'S02':'b198e694fb46bb95cfac31b0d14a08744e018efb5f0966034b4015a31b05f655',
      'Sol':read_json(_project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output/generation.json'))['identity']['candidate_id']}
VARIANTS=('original_C_start','public_consistent_hidden_1')
NAMESPACE='vip-t21-early-strict-choice-abc-v1'  # 固定相同隐藏世界，不能更换成功样本
BUDGETS={'wall_clock_seconds':3600,'recovery':{'max_replay_frames':5000,'wall_clock_seconds':900},
    'continuation':{'max_instances':40,'steps_per_arm':5000},
    'capture':{'max_unique_views':12000,'max_view_json_bytes':64*1024**2,'max_total_json_bytes':2*1024**3},
    'max_output_bytes':4*1024**3}


def prepare(output_dir:Path,candidate_package:Path,batch_file:Path=BATCH)->dict:
    """纯读四个公开无胡严格偏好起点，绑定实际前缀/包/源码/预算，不导入业务。"""
    output_dir=output_dir.resolve();output_dir.mkdir(parents=True,exist_ok=True)
    require(not (output_dir/'PREPARED.json').exists(),'既有准备不能覆盖')
    began=time.monotonic()
    try:
        batch_file=batch_file.resolve();batch=read_json(batch_file);files={};packages={};roots=[]
        require(batch['max_operations']==2400000,'仅接受冻结240万包')
        def bind(path):
            path=path.resolve();files[str(path)]=fingerprint(path)
        proposal=read_json(candidate_package.resolve()/'generation.json')
        require(proposal['identity']['candidate_id']==CIDS['Sol']
            and [p['identity']['candidate_id'] for p in proposal['parents']]==[CIDS['S02']], 'T19及其生成直接父必须是真实T17')
        for name,path in {**PACKAGES,'Sol':candidate_package.resolve()}.items():
            generation=read_json(path/'generation.json');identity=generation['identity']
            require(generation['status']=='loaded_not_admitted' and generation['load']['ok']
                and generation['identity_stable'] and identity['candidate_id']==CIDS[name], '真实研究包身份不同')
            require(identity['params']=={k:batch[k] for k in ('max_operations','projection_limits','route_limits','rule_config')}, '同批完整配置不等')
            require(fingerprint(path/'candidate.py')['sha256']==identity['source_sha256'], '研究源码漂移')
            for rel,expected in identity['source_manifest'].items():require(fingerprint(_project_file(_PROJECT_ROOT, ROOT/rel))==expected,'依赖漂移: '+rel)
            for path2 in (path/'candidate.py',path/'generation.json',_project_file(_PROJECT_ROOT, ROOT/identity['contract_path'])):bind(path2)
            packages[name]={'path':str(path.resolve()),'identity':identity}
        for pool,sha in SELECTED:
            source=source_material(pool,sha,bind)
            require(source['value_limits']==batch['route_limits'] and source['match_spec']['config']['rules']==batch['rule_config'],'来源规则额度不同')
            for meta in source['policy_metadata'].values():
                for rel,expected in meta['source_manifest'].items():require(fingerprint(_project_file(_PROJECT_ROOT, ROOT/rel))==expected,'基线/对手依赖漂移: '+rel)
            roots.append({'root_id':source['mother_root']+':'+pool+':'+str(source['target_window']['trigger_seq'])+':early-strict-choice',
                'mother_root':source['mother_root'],'source_kind':'actual_C_development',
                'profile':source['profile'],'source':source,'pool':pool,'permutation':source['permutation'],
                'policy_metadata':source['policy_metadata'],'logical_labels':list(source['policy_metadata']),
                'hidden_sample_namespace':NAMESPACE,'selection_uses_terminal_score':False})
        manifest=read_json(NATURAL/'manifest.json')
        for rel,expected in manifest['source_manifest'].items():require(fingerprint(_project_file(_PROJECT_ROOT, ROOT/rel))==expected,'真实自然运行闭包漂移: '+rel)
        runtime={str(p.resolve()):fingerprint(p) for p in sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot')).rglob('*'))
            if p.is_file() and p.suffix in {'.py','.c','.h','.so','.dylib','.pyd'}}
        for path in (batch_file,_project_file(_PROJECT_ROOT, ORIGINAL/'source_recovery.py'),_project_file(_PROJECT_ROOT, HERE/'README.md'),Path(sys.executable).resolve(),
                     *(_project_file(_PROJECT_ROOT, CORE/n) for n in ('recover_natural_start.py','run_abc_pilot.py','abc_five_arm_core.py'))):bind(path)
        require(not any(n=='hangma_bot' or n.startswith('hangma_bot.') for n in sys.modules),'prepare导入了业务')
        plan={'schema':'t10-abc-diagnostic-prepared/1','campaign':'T21 early strict-preference ordinary choices: T19 and true T17 normal C, own first then R18 B, actual shared public prefix; no new author',
            'tool_file':str(Path(__file__).resolve()),'tool_sha256':fingerprint(Path(__file__))['sha256'],
            'source_recovery_sha256':fingerprint(_project_file(_PROJECT_ROOT, ORIGINAL/'source_recovery.py'))['sha256'],
            'files':files,'runtime_files':runtime,'packages':packages,'batch_file':str(batch_file),
            'roots':roots,'budgets':BUDGETS,'python_version':sys.version,'variant_order':list(VARIANTS),
            'arm_order':list(ORDER),'planned_source_roots':4,'planned_mother_roots':4,
            'planned_source_windows':4,'planned_worlds':8,'planned_continuation_instances':40,
            'endpoint':'current_single_hand_end','prepare_business_calls':0,'model_api_calls':0,
            'prepare_elapsed_monotonic_seconds':time.monotonic()-began,
            'claims':'T21_known_early_public_strict_entry_followup_diagnostic_not_strength_confirmation_or_admission',
            'selection':'T21 SOURCE-SELECTION: each motherroot H strict-preference minimum permutation; no outcome criterion; known development',
            'source_kind':'closed_actual_natural_C_window_prefix/2','not_new_unexposed_roots':True,
            'normal_C_first_actions_forced':False,'opponent_near_completion':'unknown_in_both_original_and_public_hidden_worlds','new_independent_reviews':0,'status':'prepared_no_business_calls'}
        write_new(output_dir/'PREPARED.json',plan);return plan
    except BaseException as exc:
        write_new(output_dir/'PREPARE-FAILED.json',{'status':'failed','business_calls':0,'error':type(exc).__name__+': '+str(exc)})
        raise


async def execute(output_dir: Path, start_path: Path) -> dict:
    """一份ROOT START消费本批40槽；仅控制资格失败局部继续，其余实错停止。

    总时限3600单调秒包含恢复、脚本、评分和续打，协作检查非抢占。完整
    DTO唯一数量/原始字节与所有实际输出字节分别记账，不按窗口作独立样本。
    """
    output_dir,start_path=output_dir.resolve(),start_path.resolve()
    prepared_path=output_dir/'PREPARED.json';plan,start=read_json(prepared_path),read_json(start_path)
    require(plan['schema']=='t10-abc-diagnostic-prepared/1' and start.get('schema')=='t10-abc-diagnostic-start/1'
        and start.get('status')=='START', '缺诊断批明确ROOT START')
    require(Path(start['prepared_file']).resolve()==prepared_path and start['prepared_sha256']==fingerprint(prepared_path)['sha256']
        and start['tool_sha256']==plan['tool_sha256']==fingerprint(Path(__file__))['sha256']
        and start['budgets']==plan['budgets']==BUDGETS and plan['python_version']==sys.version and plan['variant_order']==list(VARIANTS),'ROOT身份/预算/Python不符')
    output=OutputLedger(output_dir,BUDGETS['max_output_bytes'],reserve=512*1024);begun=time.monotonic()
    output.save(output_dir/'EXECUTION-ENTRY.json',{'status':'entered','start_path':str(start_path),
        'start_sha256':fingerprint(start_path)['sha256'],'planned_mother_roots':4,'planned_source_windows':len(plan['roots']),'planned_instances':len(plan['roots'])*len(VARIANTS)*len(ORDER)})
    stream=output.open(output_dir/'calls-and-choices.jsonl','xb')
    counts,root_counts,world_counts=Counter(),{},{};scope={};recovery_started=None;capture,view_stream,primary=None,None,None
    arms=[{'root_id':r['root_id'],'source_kind':r['source_kind'],'variant':v,'arm':a,'status':'not_started','dispatched':False}
        for r in plan['roots'] for v in VARIANTS for a in ORDER]
    roots=[{'root_id':r['root_id'],'source_kind':r['source_kind'],'profile':r['profile'],'status':'not_started'} for r in plan['roots']]
    result={'status':'unfinished','planned_mother_roots':4,'planned_source_windows':len(plan['roots']),'planned_worlds':len(plan['roots'])*len(VARIANTS),'planned_continuation_instances':len(plan['roots'])*len(VARIANTS)*len(ORDER),
        'model_api_calls':0,'claims':plan['claims'],'hidden_sample_scope':'public_consistency_robustness_not_history_posterior'}
    def charge(name):
        if time.monotonic()-begun>=BUDGETS['wall_clock_seconds']: raise RuntimeError('diagnostic_total_wall_clock_limit')
        if recovery_started is not None:
            if time.monotonic()-recovery_started>=BUDGETS['recovery']['wall_clock_seconds']: raise RuntimeError('actual_C_recovery_wall_clock_limit')
            if name in ('recovery:world_advance_calls','recovery:nested_world_advance_calls'):
                used=sum(counts[k] for k in ('recovery:world_advance_calls','recovery:nested_world_advance_calls'))
                require(used<BUDGETS['recovery']['max_replay_frames'],'actual_C_recovery_frame_limit')
        counts[name]+=1
        if scope.get('root_id'):
            root_counts.setdefault(scope['root_id'],Counter())[name]+=1
            if scope.get('variant'): world_counts.setdefault(scope['root_id']+':'+scope['variant'],Counter())[name]+=1
    def call(name,fn,*args,**kwargs): charge(name);return fn(*args,**kwargs)
    def event(row): stream.write(canonical({**scope,**row})+b'\n');stream.flush()
    try:
        for name,expected in plan['files'].items(): require(fingerprint(Path(name))==expected,'冻结来源漂移: '+name)
        for name,expected in plan['runtime_files'].items(): require(fingerprint(Path(name))==expected,'业务源码漂移: '+name)
        sys.path.insert(0,str(_project_file(_PROJECT_ROOT, ROOT/'src')))
        from hangma_bot.hangma.engine import HangmaRules
        from hangma_bot.simulation.engine import SimulationEngine
        from hangma_bot.simulation.artifacts import compute_rules_hash
        from hangma_bot.kernel.serialization import observation_to_json,window_key_to_json
        from hangma_bot.offline.evaluate import frame_observation_summary
        from hangma_bot.offline.scoring_input_capture import ScoringInputCapture,ScoringInputCaptureLimits
        from hangma_bot.offline.vip_eoh_generate import VipEohBatch,load_vip_parents
        batch=call('generation_batch_reads',VipEohBatch.read,Path(plan['batch_file']))
        sources={}
        for name,package in plan['packages'].items():
            loaded=call('candidate_package_validation_entries',load_vip_parents,[Path(package['path'])],batch)
            require(len(loaded)==1 and loaded[0]['identity']==package['identity'],'实际候选身份不等')
            sources[name]=loaded[0]['source']
        view_stream=output.open(output_dir/'views.jsonl.gz','x+b')
        capture=ScoringInputCapture(view_stream,limits=ScoringInputCaptureLimits(**BUDGETS['capture']))
        class CountRules(HangmaRules):
            """父批分母计唯一规则实现的实际调用。"""
            def analyze(self,*args,**kwargs): return call('recovery:rules_analyze_calls' if recovery_started is not None else 'rules_analyze_calls',super().analyze,*args,**kwargs)
        rules_hash=call('rules_identity_calls',compute_rules_hash,ROOT)
        for ordinal,(root,root_row) in enumerate(zip(plan['roots'],roots),1):
            scope.clear();scope.update(root_id=root['root_id'],source_kind=root['source_kind'])
            root_row['status']='preparing_start';directory=output_dir/('root-'+str(ordinal).zfill(2));directory.mkdir(exist_ok=False)
            rules=call('rules_constructors',CountRules,batch.rule_config)
            engine=call('world_engine_constructors',SimulationEngine,rules,rules_hash=rules_hash)
            recovery_started=time.monotonic()
            original,target,snapshot=restore(root=root,rules=rules,engine=engine,batch=batch,
                output=output,directory=directory,event=event,call=call)
            recovery_started=None
            match_id=root['source']['match_spec']['match_id'];round_no=root['source']['target_window']['round_no'];focal=root['source']['target_window']['seat']
            frame=call('world_frame_calls',engine.frame,original)
            before=[observation_to_json(d.observation) for d in frame.decisions if d.window_key==target]
            require(len(before)==1,'实际C目标缺失')
            # 使用已验收机械探针同一公开构造器，在任何续打计费前核原 DTO。
            from hangma_bot.kernel.observation import CompetitionContext
            from hangma_bot.policy.interface import DecisionRequest
            from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
            decision=next(d for d in frame.decisions if d.window_key==target)
            analysis=rules.analyze(decision.observation,route_limits=batch.route_limits)
            request=DecisionRequest(decision.observation,CompetitionContext('t20-preflight/1',None,None,None,None,(),0),
                analysis,'t20-preflight:'+root['root_id'],target.trigger_seq,target,())
            typed=call('target_preflight_projection_calls',build_vip_route_scoring_view,request,batch.rule_config,limits=batch.projection_limits)
            actual_dto=call('target_preflight_candidate_view_reads',typed.candidate_view)
            actual_bytes=canonical(actual_dto)
            require(hashlib.sha256(actual_bytes).hexdigest()==root['source']['source_C_full_DTO_sha256']
                and len(actual_bytes)==root['source']['source_C_input_json_bytes'],'首续打前完整原DTO不同')
            require('hu' not in root['source']['source_C_cached_scores'],'目标不是冻结的无胡窗口')
            output.save(directory/'TARGET-INPUT-PREFLIGHT.json',{'status':'exact_actual_DTO_reconstructed_before_any_continuation',
                'view_sha256':hashlib.sha256(actual_bytes).hexdigest(),'json_bytes':len(actual_bytes),'score_calls':0,
                'normal_C_first_unforced':True,'original_C_first':root['source']['source_selected_first']})
            root_row.update(status='qualified',target_window=window_key_to_json(target),
                start_scope='closed_actual_C_single_hand_not_A_or_new_independent_source')
            for variant in VARIANTS:
                scope.update(variant=variant)
                common=original
                sample_key=root['hidden_sample_namespace']+':hidden:1:'+root['root_id']
                if variant!=VARIANTS[0]: common=call('public_hidden_resample_calls',engine.resample_public_consistent_hidden_world,
                    original,focal_seat=focal,sample_key=sample_key)
                frame=call('world_frame_calls',engine.frame,common)
                selected=[observation_to_json(d.observation) for d in frame.decisions if d.window_key==target]
                require(selected==before,'固定隐藏变体改变完整焦点观察/目标')
                selected_snapshot=dict(snapshot,observation_summary=frame_observation_summary(frame))
                world_dir=directory/variant;world_dir.mkdir(exist_ok=False)
                output.save(world_dir/'COMMON-START.json',{'target_window':window_key_to_json(target),'focal_observation':before[0],
                    'all_responders_summary':selected_snapshot['observation_summary'],'sample_key':sample_key if variant!=VARIANTS[0] else 'original_frozen_T17_C_prefix',
                    'base_world_scope':'closed_actual_C_single_hand_prefix',
                    'shared_immutable_handle_across_arms':True,'history_posterior':False})
                group=[r for r in arms if r['root_id']==root['root_id'] and r['variant']==variant]
                local_plan={**plan,**{k:root[k] for k in ('policy_metadata','logical_labels','pool','permutation')}}
                try:
                    world_result=await run_five_arms(plan=local_plan,batch=batch,sources=sources,rules=rules,engine=engine,
                        common=common,stage_snapshot=selected_snapshot,focal=focal,target=target,root_id=root['root_id'],
                        match_id=match_id,round_no=round_no,event=event,call=call,charge=charge,capture=capture,counts=counts,
                        output=output,output_dir=world_dir,arms=group)
                except BaseException as exc:
                    try: output.save(world_dir/'WORLD-FAILED.json',{'error':type(exc).__name__+': '+str(exc),'arms':group})
                    except BaseException as secondary: exc.add_note('原失败臂原件写入失败: '+str(secondary))
                    raise
                output.save(world_dir/'WORLD-RESULT.json',{'deltas':world_result['deltas'],'root_id':root['root_id'],
                    'variant':variant,'clustering_unit':'source mother root; hidden variants not independent','not_independent_root':True})
                for row in group: row.pop('outcome',None)
            root_row['status']='complete';output.save(directory/'ROOT-RESULT.json',root_row)
        scope.clear()
        for name,expected in {**plan['files'],**plan['runtime_files']}.items(): require(fingerprint(Path(name))==expected,'执行后来源漂移: '+name)
        require(fingerprint(prepared_path)['sha256']==start['prepared_sha256'] and fingerprint(Path(__file__))['sha256']==start['tool_sha256'],'执行后父登记漂移')
        result['status']='diagnostic_batch_closed_not_strength_confirmation'
    except BaseException as exc:
        primary=exc;result.update(status='failed_original_registered_slots_retained',error=type(exc).__name__+': '+str(exc))
        for row in arms:
            if row['status']=='not_started': row['status']='not_started_after_first_tool_failure'
            elif row['status'] in ('preparing_arm','dispatched'): row.update(status='failed',error=result['error'])
        for row in roots:
            if row['status']=='not_started': row['status']='not_started_after_first_tool_failure'
            elif row['status'] in ('preparing_start','qualified'): row.update(status='failed',error=result['error'])
        raise
    finally:
        cleanup=[]
        if capture is not None:
            try: capture.finish()
            except BaseException as exc: cleanup.append(type(exc).__name__+': '+str(exc))
            result['input_capture']=capture.costs
            if not capture.costs['terminal']['terminal_valid']: result['status']='failed_input_capture_terminal'
        for handle in (view_stream,stream):
            if handle is not None:
                try: handle.close()
                except BaseException as exc: cleanup.append(type(exc).__name__+': '+str(exc))
        if time.monotonic()-begun >= BUDGETS['wall_clock_seconds']:
            result['status']='failed_total_wall_clock_limit'
        result.update(actual_calls=dict(counts),costs_by_mother_root={k:dict(v) for k,v in root_counts.items()},
            costs_by_world={k:dict(v) for k,v in world_counts.items()},elapsed_monotonic_seconds=time.monotonic()-begun,
            completed_arms=sum(r['status']=='complete' for r in arms),dispatched_arms=sum(r['dispatched'] for r in arms),
            missing_or_failed_arms=sum(r['status']!='complete' for r in arms),roots=roots,cleanup_errors=cleanup,
            output_bytes_before_terminal=output.bytes,output_write_attempts=output.write_attempts,output_write_failures=output.write_failures,
            projection_count_scope='C/R18:scoring_projection_attempts is conservative choose entry; score dispatch separately counted')
        # 登记槽终态用窄字段；512KiB费用预留在4GiB内，不另加输出额度。
        result['arms']=[{k:r[k] for k in ('root_id','source_kind','variant','arm','status','dispatched','focal_net_score','first_action_key','force_count','same_first_action_determinism') if k in r} for r in arms]
        output.terminal=True
        try: output.save(output_dir/'COSTS-AND-RESULT.json',result)
        except BaseException as exc:
            if primary is None: raise
            primary.add_note('诊断费用收口失败: '+type(exc).__name__+': '+str(exc))
        if primary is None and (cleanup or result['status']!='diagnostic_batch_closed_not_strength_confirmation'):
            raise RuntimeError('诊断捕获/输出终态失败')
    return result

def main():
    """prepare只读闭合原件；execute消费根另写的同父接口ROOT START。"""
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--output-dir',type=Path,default=HERE)
    p.add_argument('--candidate-package',type=Path,required=True);p.add_argument('--batch',type=Path,default=BATCH)
    e=sub.add_parser('execute');e.add_argument('--output-dir',type=Path,default=HERE);e.add_argument('--start',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare':
        plan=prepare(args.output_dir,args.candidate_package,args.batch)
        print(canonical({'status':plan['status'],'tool_sha256':plan['tool_sha256'],
            'prepared_sha256':fingerprint(args.output_dir/'PREPARED.json')['sha256'],
            'planned_mother_roots':4,'planned_source_windows':4,'planned_worlds':plan['planned_worlds'],
            'planned_continuation_instances':plan['planned_continuation_instances'],'prepare_business_calls':0}).decode())
    else:
        result=asyncio.run(execute(args.output_dir,args.start));print(canonical({'status':result['status'],
            'completed_arms':result['completed_arms']}).decode())
if __name__=='__main__':main()
