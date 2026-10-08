"""T13五开发母根50槽；复用T10恢复/五臂合同和按源固定的隐藏采样键。

本工具只接受显式ROOT START。自然恢复仍使用已审核的t10诊断schema，
并非新的规则/世界算法。实际身份和登记未完善时不能启动。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/focused-abc-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse,ast,asyncio,hashlib,sys,time
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
CORE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1')
sys.path.insert(0,str(CORE))
from recover_natural_start import ROOT,canonical,fingerprint,read_json,require,write_new,recover_natural_start
from run_abc_pilot import OutputLedger,ORDER
from abc_five_arm_core import run_five_arms
from run_abc_diagnostic import ControlIneligible,build_control_start
VARIANTS=('original','public_consistent_hidden_1')
BUDGETS={'wall_clock_seconds': 5400, 'recovery': {'max_replay_frames': 5000, 'wall_clock_seconds': 600}, 'conditional_script': {'max_advance_calls': 2000}, 'continuation': {'max_instances': 50, 'steps_per_arm': 5000}, 'capture': {'max_unique_views': 12000, 'max_view_json_bytes': 67108864, 'max_total_json_bytes': 2147483648}, 'max_output_bytes': 4294967296}

async def execute(output_dir: Path, start_path: Path) -> dict:
    """一份ROOT START消费50槽；仅控制资格失败局部继续，其余实错停止。

    总时限5400单调秒包含恢复、脚本、评分和续打，协作检查非抢占。完整
    DTO唯一数量/原始字节与所有实际输出字节分别记账，不按窗口作独立样本。
    """
    output_dir,start_path=output_dir.resolve(),start_path.resolve()
    prepared_path=output_dir/'PREPARED.json';plan,start=read_json(prepared_path),read_json(start_path)
    require(plan['schema']=='t10-abc-diagnostic-prepared/1' and start.get('schema')=='t10-abc-diagnostic-start/1'
        and start.get('status')=='START', '缺诊断批明确ROOT START')
    require(Path(start['prepared_file']).resolve()==prepared_path and start['prepared_sha256']==fingerprint(prepared_path)['sha256']
        and start['tool_sha256']==plan['tool_sha256']==fingerprint(Path(__file__))['sha256']
        and start['budgets']==plan['budgets']==BUDGETS and plan['python_version']==sys.version,'ROOT身份/预算/Python不符')
    output=OutputLedger(output_dir,BUDGETS['max_output_bytes'],reserve=512*1024);begun=time.monotonic()
    output.save(output_dir/'EXECUTION-ENTRY.json',{'status':'entered','start_path':str(start_path),
        'start_sha256':fingerprint(start_path)['sha256'],'planned_mother_roots':len(plan['roots']),'planned_instances':len(plan['roots'])*len(VARIANTS)*len(ORDER)})
    stream=output.open(output_dir/'calls-and-choices.jsonl','xb')
    counts,root_counts,world_counts=Counter(),{},{};scope={};capture,view_stream,primary=None,None,None
    arms=[{'root_id':r['root_id'],'source_kind':r['source_kind'],'variant':v,'arm':a,'status':'not_started','dispatched':False}
        for r in plan['roots'] for v in VARIANTS for a in ORDER]
    roots=[{'root_id':r['root_id'],'source_kind':r['source_kind'],'profile':r['profile'],'status':'not_started'} for r in plan['roots']]
    result={'status':'unfinished','planned_mother_roots':len(plan['roots']),'planned_worlds':len(plan['roots'])*len(VARIANTS),'planned_continuation_instances':len(plan['roots'])*len(VARIANTS)*len(ORDER),
        'model_api_calls':0,'claims':plan['claims'],'hidden_sample_scope':'public_consistency_robustness_not_history_posterior'}
    def charge(name):
        if time.monotonic()-begun>=BUDGETS['wall_clock_seconds']: raise RuntimeError('diagnostic_total_wall_clock_limit')
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
            def analyze(self,*args,**kwargs): return call('rules_analyze_calls',super().analyze,*args,**kwargs)
        rules_hash=call('rules_identity_calls',compute_rules_hash,ROOT)
        controls=read_json(Path(plan['controls_file']))
        for ordinal,(root,root_row) in enumerate(zip(plan['roots'],roots),1):
            scope.clear();scope.update(root_id=root['root_id'],source_kind=root['source_kind'])
            root_row['status']='preparing_start';directory=output_dir/('root-'+str(ordinal).zfill(2));directory.mkdir(exist_ok=False)
            if root['source_kind']=='natural':
                recovery_dir=directory/'recovery';recovery_dir.mkdir(exist_ok=False)
                recovered=recover_natural_start(Path(plan['panel_file']),root['recovery']['input_sha256'],recovery_dir,
                    start_path=start_path,parent_prepared_file=prepared_path,parent_recovery_id=root['root_id'],
                    charge=lambda name:charge('recovery:'+name),save_json=output.save,open_output=output.open)
                original,target,snapshot=recovered.world,recovered.target_window,recovered.stage_snapshot
                match_id=root['recovery']['match_spec']['match_id'];round_no=root['recovery']['target_window']['round_no']
                rules=call('rules_constructors',CountRules,batch.rule_config)
                engine=call('world_engine_constructors',SimulationEngine,rules,rules_hash=rules_hash)
            else:
                rules=call('rules_constructors',CountRules,batch.rule_config)
                engine=call('world_engine_constructors',SimulationEngine,rules,rules_hash=rules_hash)
                try:
                    original,target,snapshot=build_control_start(root,controls,rules,engine,batch,output,directory,event,call,charge)
                except ControlIneligible as exc:
                    root_row.update(status='qualification_failed_original_slots_retained',error=str(exc))
                    for row in arms:
                        if row['root_id']==root['root_id']: row.update(status='not_started_control_ineligible',error=str(exc))
                    output.save(directory/'ROOT-RESULT.json',root_row);continue
                match_id,round_no=root['root_id'],1
            focal=root['permutation'][0]
            original_frame=call('world_frame_calls',engine.frame,original)
            require(frame_observation_summary(original_frame)==snapshot['observation_summary'],'原共同起点摘要不符')
            before=[observation_to_json(d.observation) for d in original_frame.decisions if d.window_key==target]
            require(len(before)==1,'原目标窗口缺失')
            root_row.update(status='qualified',target_window=window_key_to_json(target))
            for variant in VARIANTS:
                scope.update(variant=variant)
                common=original
                sample_key=root['hidden_sample_namespace']+':hidden:1:'+root['root_id']
                if variant!='original': common=call('public_hidden_resample_calls',engine.resample_public_consistent_hidden_world,
                    original,focal_seat=focal,sample_key=sample_key)
                frame=call('world_frame_calls',engine.frame,common)
                selected=[observation_to_json(d.observation) for d in frame.decisions if d.window_key==target]
                require(selected==before,'固定隐藏变体改变完整焦点观察/目标')
                selected_snapshot=dict(snapshot,observation_summary=frame_observation_summary(frame))
                world_dir=directory/variant;world_dir.mkdir(exist_ok=False)
                output.save(world_dir/'COMMON-START.json',{'target_window':window_key_to_json(target),'focal_observation':before[0],
                    'all_responders_summary':selected_snapshot['observation_summary'],'sample_key':sample_key if variant!='original' else None,
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
                    'variant':variant,'clustering_unit':'mother_root','not_independent_root':variant!='original'})
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
    """消费已经绑定实际候选的批次，不准备或自动恢复费用。"""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--start',type=Path,required=True)
    args=parser.parse_args();result=asyncio.run(execute(args.output_dir,args.start))
    print(canonical({'status':result['status'],'completed_arms':result['completed_arms']}).decode())
if __name__=='__main__':main()
