"""T32: eight frozen physical conditions, unchanged T24/T25, two worlds, five arms.
Prepare is pure; only ROOT START can execute existing rule and simulation cores.
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t32-new-multiwhite-source-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import ast
import asyncio
from collections import Counter
import hashlib
from pathlib import Path
import random
import sys
import time

HERE = Path(__file__).resolve().parent
T10 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1')
sys.path.insert(0, str(T10))
from recover_natural_start import (ROOT, canonical, fingerprint, read_json, require,
    write_new, recover_natural_start)
from run_abc_pilot import OutputLedger, ORDER
from abc_five_arm_core import run_five_arms
from run_abc_diagnostic import ControlIneligible, build_control_start

PROTOTYPE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1/abc-diagnostic-12-preparation-1/PREPARED.json')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t25-public-assistance-cost-control-author-1')
BATCH = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t25-public-assistance-cost-control-author-1/S01-generation.batch.json')
PACKAGES = {'Sol': _project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output'), 'S02': _project_file(_PROJECT_ROOT, HERE.parent/'t24-discard-route-portfolio-author-1/S01-model-output')}
EXPECTED_IDS = {'Sol': 'efe05edd6c93b58c24526313ea1ca0fc5e60970bb100ab18734fbab053264164',
    'S02': 'edda117c2593f75e1098e280546187084655f35f540642fc081842cf484e43a1'}
VARIANTS = ('original', 'public_consistent_hidden_1')
NAMESPACE = 'vip-t32-new-multiwhite-abc-v1'
# seeds是opaque身份；手牌/当前摸牌事前固定，未指定未来进张、赢家或终局。
CONDITIONS = read_json(_project_file(_PROJECT_ROOT, HERE/'SOURCE-CONDITIONS.json'))
DESIGNS = tuple((p['seed'], p['profile'], p['focal_hand13'], p['dealer_drawn_tile'],
    p['qualification']['current_legal_hu'], p['fixed_other_hands']) for p in CONDITIONS['proposals'])
ROOT_IDS = tuple('vip-t32-new-multiwhite-'+str(d[0]) for d in DESIGNS)
BUDGETS = {'wall_clock_seconds': 3600,
    'recovery': {'max_replay_frames': 5000, 'wall_clock_seconds': 600},
    'conditional_script': {'max_advance_calls': 2000},
    'continuation': {'max_instances': len(ROOT_IDS)*len(VARIANTS)*len(ORDER), 'steps_per_arm': 5000},
    'capture': {'max_unique_views': 12000, 'max_view_json_bytes': 64*1024**2,
                'max_total_json_bytes': 2*1024**3}, 'max_output_bytes': 4*1024**3}


def make_controls(batch):
    """标准库固定四源；输出34码各4张与三轮四张/尾张/庄摸发牌映射。

    只检查牌张物理容量（张），不分析胡牌/向听。余牌只按seed均匀打乱
    一次；有资格失败亦不得替换seed、摸牌或余墙。规则资格待execute。
    """
    module = ast.parse((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot/kernel/actions.py')).read_text())
    codes = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name) and n.target.id == 'CANONICAL_TILE_ORDER')
    require(len(codes)==34 and len(set(codes))==34, '规范牌码不是34类')
    proposals=[]
    for seed,profile,focal,drawn,current_hu,others in DESIGNS:
        require(len(focal)==13 and all(len(h)==13 for h in others.values()), '固定手牌不等于13张')
        reserved=Counter(focal+[drawn]+[t for h in others.values() for t in h])
        require(set(reserved)<=set(codes) and max(reserved.values())<=4, '固定物理牌容量超限')
        residual=[code for code in codes for _ in range(4-reserved[code])]
        random.Random(seed).shuffle(residual)
        hands=[list(focal),[],[],[]];cursor=0
        for seat in range(1,4):
            if str(seat) in others: hands[seat]=list(others[str(seat)])
            else: hands[seat]=residual[cursor:cursor+13];cursor+=13
        wall=residual[cursor:]
        deck=[]
        for block in range(3):
            for seat in range(4): deck.extend(hands[seat][block*4:block*4+4])
        for seat in range(4): deck.append(hands[seat][12])
        deck.append(drawn);deck.extend(wall)
        require(len(deck)==136 and Counter(deck)==Counter({t:4 for t in codes}) and len(wall)==83,
            '136张物理守恒/83张牌墙失败')
        replayed=[[] for _ in range(4)];offset=0
        for _ in range(3):
            for seat in range(4): replayed[seat].extend(deck[offset:offset+4]);offset+=4
        for seat in range(4): replayed[seat].append(deck[offset]);offset+=1
        require(replayed==hands and deck[52]==drawn and deck[53:]==wall, '固定发牌映射失败')
        proposals.append({'root_id':'vip-t32-new-multiwhite-'+str(seed),'seed':seed,'profile':profile,
            'focal_hand13':focal,'dealer_drawn_tile':drawn,'fixed_other_hands':others,
            'hands13_by_seat':hands,'wall':wall,'full_physical_deck':deck,
            'deck_sha256':hashlib.sha256(canonical(deck)).hexdigest(),
            'qualification':{'focal_seat':0,'phase':'draw','visible_white_count':sum(t=='白' for t in focal+[drawn]),
                'current_legal_hu':current_hu},
            'original_teacher_standard_shanten_zero_required': bool(others),
            'hidden_teacher_near_completion_qualification':'unknown_not_retested',
            'rules_qualification_status':'not_executed',
            'physical_precheck':{'tile_count':136,'tile_classes':34,'copies_per_class':4,
                'hands13_count':4,'current_dealer_tiles':14,'wall_tiles':83,'deal_mapping_equal':True}})
    return {'schema':'t32-rare-conditioned-control-proposals/1','compatible_import_fields':'T10 build_control_start',
        'pool':'M','permutation':[0,1,2,3],'rule_config':batch['rule_config'],'value_limits':batch['route_limits'],
        'timing':{'chi_timeout_sec':1,'discard_timeout_sec':3,'peng_timeout_sec':1},'proposals':proposals,
        'sampling':'固定焦点13张/当前摸牌/可选教师13张后，规范34码物理余牌Random(seed).shuffle一次；不搜索未来',
        'selection_uses_candidate_scores_or_terminal_results':False,'rules_precheck_status':'not_started',
        'business_calls':0,'candidate_or_r18_score_calls':0,'model_api_calls':0,
        'source_kind':'conditional_physical_teacher_origin_not_natural_panel',
        'failure_policy':'资格失败保留该母根两世界十槽；不补题、不换seed，其他登记根继续',
        'development_only':True,'confirmation':False,'strength_claim':False,'complete_table_claim':False}


def prepare(output_dir: Path):
    """纯文件生成CONTROL-TEMPLATES/PREPARED，绑定原件和运行闭包；禁止START。

    允许目录已含本工具/README；输出使用独占写，已有准备原件不覆盖。
    失败保留PREPARE-FAILED；时间预算为execute的单调秒，不消耗作者账本。
    """
    output_dir=output_dir.resolve();output_dir.mkdir(parents=True,exist_ok=True)
    require(not (output_dir/'PREPARED.json').exists(), '既有PREPARED不得覆盖')
    try:
        prototype,batch=read_json(PROTOTYPE),read_json(BATCH)
        controls=make_controls(batch)
        require(len(controls['proposals'])==8, 'Expected eight fixed physical roots')
        for actual, original in zip(controls['proposals'], CONDITIONS['proposals']):
            require(all(actual[k]==original[k] for k in ('root_id','full_physical_deck','deck_sha256','qualification','profile')), 'Original condition changed')
        controls_file=output_dir/'CONTROL-TEMPLATES.json'
        write_new(controls_file,controls)
        require(controls['pool']=='M' and controls['permutation']==[0,1,2,3], '固定M池或座位不符')
        metadata=prototype['roots'][8]['policy_metadata'];labels=prototype['roots'][8]['logical_labels']
        require(labels==['A','M1','M2','M3'], '旧M实际对手装配不符')
        files={}
        def bind(path): files[str(path.resolve())]=fingerprint(path)
        for path in (controls_file,PROTOTYPE,BATCH,_project_file(_PROJECT_ROOT, HERE/'SOURCE-CONDITIONS.json'),_project_file(_PROJECT_ROOT, HERE/'prepare_sources.py'),_project_file(_PROJECT_ROOT, HERE/'README.md'),_project_file(_PROJECT_ROOT, ROOT/'doc/references/official-guide-v34-content.txt'),
            _project_file(_PROJECT_ROOT, ROOT/'doc/references/official-guide-version-v34.json'),_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot/hangma/RULES_EVIDENCE.md'),
            _project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot/kernel/actions.py'),Path(sys.executable).resolve(),
            *(_project_file(_PROJECT_ROOT, T10/name) for name in ('run_abc_diagnostic.py','abc_five_arm_core.py','run_abc_pilot.py','recover_natural_start.py'))): bind(path)
        packages={}
        for name,path in PACKAGES.items():
            generation=read_json(path/'generation.json');identity=generation['identity']
            require(generation['status']=='loaded_not_admitted' and identity['candidate_id']==EXPECTED_IDS[name], '固定候选身份不符')
            require(identity['params']=={k:batch[k] for k in ('max_operations','projection_limits','route_limits','rule_config')},
                '候选操作/投影/规则/配置不等')
            require(hashlib.sha256((path/'candidate.py').read_bytes()).hexdigest()==identity['source_sha256'], '候选源码与generation摘要不等')
            for relative,expected in identity['source_manifest'].items():
                require(fingerprint(_project_file(_PROJECT_ROOT, ROOT/relative))==expected, '候选运行源码漂移: '+relative)
            for original in (path/'candidate.py',path/'generation.json',_project_file(_PROJECT_ROOT, ROOT/identity['contract_path'])): bind(original)
            packages[name]={'path':str(path.resolve()),'identity':identity}
        new_generation=read_json(PACKAGES['Sol']/'generation.json')
        require(len(new_generation['parents'])==1 and new_generation['parents'][0]['identity']==packages['S02']['identity'],
            'T25 true direct parent must be T24')
        for meta in metadata.values():
            for relative,expected in meta['source_manifest'].items():
                require(fingerprint(_project_file(_PROJECT_ROOT, ROOT/relative))==expected, '原M/R18策略源码漂移: '+relative)
        runtime={str(p.resolve()):fingerprint(p) for p in sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot')).rglob('*'))
            if p.is_file() and p.suffix in ('.py','.c','.h','.so','.dylib','.pyd')}
        for path,expected in prototype['runtime_files'].items(): require(runtime.get(path)==expected, 'T10运行源码漂移: '+path)
        roots=[{'root_id':p['root_id'],'source_kind':'conditional','profile':p['profile'],'proposal':p,
            'policy_metadata':metadata,'logical_labels':labels,'pool':'M','permutation':[0,1,2,3]} for p in controls['proposals']]
        require(tuple(r['root_id'] for r in roots)==ROOT_IDS, '四个事前母根不符')
        plan={'schema':'t32-rare-conditional-prepared/1','tool_file':str(Path(__file__).resolve()),
            'tool_sha256':fingerprint(Path(__file__))['sha256'],'recovery_tool_sha256':fingerprint(_project_file(_PROJECT_ROOT, T10/'recover_natural_start.py'))['sha256'],
            'controls_file':str(controls_file),'files':files,'packages':packages,'batch_file':str(BATCH.resolve()),
            'roots':roots,'budgets':BUDGETS,'python_version':sys.version,'python_executable':sys.executable,
            'runtime_files':runtime,'variant_order':list(VARIANTS),'arm_order':list(ORDER),'hidden_sample_namespace':NAMESPACE,
            'planned_mother_roots':len(roots),'planned_worlds':len(roots)*len(VARIANTS),
            'planned_continuation_instances':len(roots)*len(VARIANTS)*len(ORDER),'endpoint':'current_single_hand_end',
            'model_api_calls':0,'prepare_business_calls':0,'claims':'conditional_development_credit_diagnostic_not_strength_confirmation',
            'qualification_status':'not_executed','selection':'eight_pre_frozen_physical_roots_four_public_shapes_paired_competition_controls_no_replacement',
            'candidate_aliases':{'Sol':'T25 unchanged','S02':'T24 true parent'},
            'reused_core':{'conditional_start':'T10 build_control_start unchanged','five_arms':'T10 abc_five_arm_core unchanged'},
            'source_kind':'conditional_physical_teacher_origin_not_natural_panel','formal_panel_claim':False,
            'hidden_teacher_qualification':'unknown; only full focal observation is required equal'}
        write_new(output_dir/'PREPARED.json',plan)
        return plan
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
    require(plan['schema']=='t32-rare-conditional-prepared/1' and start.get('schema')=='t32-rare-conditional-start/1'
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
                sample_key=NAMESPACE+':hidden:1:'+root['root_id']
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
    """prepare只处理本目录文件；execute必须显式给根写的ROOT START路径。"""
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--output-dir',type=Path,default=HERE)
    e=sub.add_parser('execute');e.add_argument('--output-dir',type=Path,default=HERE);e.add_argument('--start',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare':
        plan=prepare(args.output_dir)
        print(canonical({'status':'prepared_no_business_calls','tool_sha256':plan['tool_sha256'],
            'prepared_sha256':fingerprint(args.output_dir/'PREPARED.json')['sha256'],
            'planned_mother_roots':plan['planned_mother_roots'],'planned_worlds':plan['planned_worlds'],
            'planned_instances':plan['planned_continuation_instances']}).decode())
    else:
        result=asyncio.run(execute(args.output_dir,args.start));print(canonical({'status':result['status'],'completed_arms':result['completed_arms']}).decode())

if __name__=='__main__': main()
