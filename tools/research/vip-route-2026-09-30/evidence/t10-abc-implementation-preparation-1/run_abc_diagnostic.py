"""固定12母根×2世界×5臂开发诊断；prepare纯文件，execute需ROOT START。

自然根取冻结面板前8项，条件根取4个固定模板，均不按终局/候选评分换根。
隐藏样本固定键、不是历史后验；独立统计单位仍为12母根。所有120槽事前
登记，条件资格失败继续其他根；规则/评分/世界/预算实错停止余批。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1'

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
from dataclasses import asdict
import hashlib
from pathlib import Path
import sys
import time
from recover_natural_start import (ROOT, canonical, fingerprint, load_material, read_json,
    require, write_new, recover_natural_start)
from run_abc_pilot import OutputLedger, ORDER, BATCH
from abc_five_arm_core import run_five_arms

HERE = Path(__file__).resolve().parent
CONTROL_SHA = '80c92a8d611e128052abd49ea5f509447d28a9840ff1b8881bea4357435aaa67'
TEMPLATE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1/abc-one-root-preparation-2/PREPARED.json')
VARIANTS = ('original', 'public_consistent_hidden_1')
NAMESPACE = 'vip-t10-abc-diagnostic-12-v1'
BUDGETS = {'wall_clock_seconds': 7200,
    'recovery': {'max_replay_frames': 5000, 'wall_clock_seconds': 600},
    'conditional_script': {'max_advance_calls': 2000},
    'continuation': {'max_instances': 120, 'steps_per_arm': 5000},
    'capture': {'max_unique_views': 12000, 'max_view_json_bytes': 64*1024**2,
                'max_total_json_bytes': 2*1024**3}, 'max_output_bytes': 4*1024**3}


def prepare(panel_file: Path, controls_file: Path, output_dir: Path) -> dict:
    """纯标准库绑定前8自然根和4固定条件源；不导入业务或装载评分器。

    输出一份PREPARED及资格待核事实；新目录独占创建，错误留失败收据。
    后续execute预算固定，不补题、不扩容、不自动START。
    """
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        panel, prototype = read_json(panel_file), read_json(TEMPLATE)
        controls = read_json(controls_file)
        require(fingerprint(controls_file)['sha256'] == CONTROL_SHA
            and controls['schema'] == 't10-abc-conditioned-control-proposals/1'
            and len(controls['proposals']) == 4 and controls['selection_uses_candidate_scores_or_terminal_results'] is False,
            '固定控制来源/槽数/盲选不符')
        roots, root_ids = [], set()
        for item in panel['windows'][:8]:
            recovery, _ = load_material(panel_file, item['input_sha256'], output_dir / ('root-' + str(len(roots)+1).zfill(2)) / 'recovery')
            root_id, pool = recovery['origin']['mother_root'], recovery['origin']['pool']
            require(root_id not in root_ids, '前8项不是8独立自然母根')
            root_ids.add(root_id)
            manifest = read_json(next(Path(r['path']) for r in recovery['source_refs'] if Path(r['path']).name == 'manifest.json'))
            labels = ['A'] + (['H1','H2','H3'] if pool == 'H' else ['M1','M2','M3'])
            metadata = {key: manifest['policy_metadata'][key] for key in labels}
            for meta in metadata.values():
                for name, expected in meta['source_manifest'].items():
                    require(fingerprint(_project_file(_PROJECT_ROOT, ROOT/name)) == expected, '自然策略源码漂移: ' + name)
            require(recovery['value_limits'] == read_json(BATCH)['route_limits'], '自然冻结规则预算不符')
            roots.append({'root_id': root_id, 'source_kind': 'natural', 'profile': 'frozen_panel_first8',
                'recovery': recovery, 'policy_metadata': metadata, 'logical_labels': labels,
                'pool': pool, 'permutation': recovery['origin']['permutation']})
        require(len(roots) == 8, '自然母根数不等于8')
        batch = read_json(BATCH)
        require(controls['value_limits'] == batch['route_limits'] and controls['rule_config'] == batch['rule_config'],
            '控制模板规则/额度与同批候选不符')
        for proposal in controls['proposals']:
            deck = proposal['full_physical_deck']
            require(len(deck) == 136 and len(Counter(deck)) == 34 and set(Counter(deck).values()) == {4}
                and hashlib.sha256(canonical(deck)).hexdigest() == proposal['deck_sha256'], '控制物理牌张/摘要不符')
            hands = [[] for _ in range(4)]
            cursor = 0
            for _ in range(3):
                for seat in range(4):
                    hands[seat].extend(deck[cursor:cursor+4]);cursor += 4
            for seat in range(4): hands[seat].append(deck[cursor]);cursor += 1
            require(hands == proposal['hands13_by_seat'] and deck[52] == proposal['dealer_drawn_tile']
                and deck[53:] == proposal['wall'] and hands[0] == proposal['focal_hand13'], '固定控制物理发牌映射不符')
            require(proposal['root_id'] not in root_ids, '控制母根重复')
            root_ids.add(proposal['root_id'])
            roots.append({'root_id': proposal['root_id'], 'source_kind': 'conditional', 'profile': proposal['profile'],
                'proposal': proposal, 'policy_metadata': prototype['policy_metadata'],
                'logical_labels': prototype['logical_labels'], 'pool': controls['pool'],
                'permutation': controls['permutation']})
        files = {**prototype['files']}
        for name, expected in files.items(): require(fingerprint(Path(name)) == expected, '旧冻结候选/批文件漂移')
        for path in (panel_file, controls_file, TEMPLATE, _project_file(_PROJECT_ROOT, HERE/'run_abc_pilot.py'), _project_file(_PROJECT_ROOT, HERE/'abc_five_arm_core.py'), _project_file(_PROJECT_ROOT, HERE/'recover_natural_start.py')):
            files[str(path.resolve())] = fingerprint(path)
        for package in prototype['packages'].values():
            for name, expected in package['identity']['source_manifest'].items():
                require(fingerprint(_project_file(_PROJECT_ROOT, ROOT/name)) == expected, '冻结候选依赖漂移: ' + name)
        plan = {'schema': 't10-abc-diagnostic-prepared/1', 'tool_file': str(Path(__file__).resolve()),
            'tool_sha256': fingerprint(Path(__file__))['sha256'],
            'recovery_tool_sha256': fingerprint(_project_file(_PROJECT_ROOT, HERE/'recover_natural_start.py'))['sha256'],
            'panel_file': str(panel_file.resolve()), 'controls_file': str(controls_file.resolve()),
            'files': files, 'packages': prototype['packages'], 'batch_file': str(BATCH),
            'roots': roots, 'budgets': BUDGETS, 'python_version': sys.version,
            'runtime_files': roots[0]['recovery']['runtime_files'], 'variant_order': list(VARIANTS),
            'arm_order': list(ORDER), 'hidden_sample_namespace': NAMESPACE, 'planned_mother_roots': 12,
            'planned_worlds': 24, 'planned_continuation_instances': 120, 'endpoint': 'current_single_hand_end',
            'model_api_calls': 0, 'claims': 'development_credit_diagnostic_not_strength_confirmation',
            'qualification_status': 'not_executed', 'selection': 'frozen_panel_first8_then_four_fixed_controls_result_blind'}
        write_new(output_dir/'PREPARED.json', plan)
        return plan
    except BaseException as exc:
        write_new(output_dir/'PREPARE-FAILED.json', {'status': 'failed', 'business_calls': 0,
            'error': type(exc).__name__ + ': ' + str(exc)})
        raise


class ControlIneligible(ValueError):
    """仅固定控制公开资格/预定脚本未达标；保留原槽并继续其他母根。"""


def build_control_start(root, controls, rules, engine, batch, output, directory, event, call, charge):
    """execute内公开导入固定物理单局，规则资格和合法无策略脚本。

    教师可读固定13张验证近完成，但其暗牌不进入策略请求。成功返回当前
    不透明世界、公开目标和摘要；资格/脚本未达标留原分母，不选终局补题。
    """
    from hangma_bot.simulation.engine import WORLD_SCHEMA
    from hangma_bot.simulation.shuffle import DEAL_ALGORITHM
    from hangma_bot.simulation.interface import SimulationChoice
    from hangma_bot.kernel.actions import Tile, action_key
    from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json
    from hangma_bot.hangma.hand_analysis import analyse_hand
    from hangma_bot.offline.evaluate import frame_observation_summary
    proposal = root['proposal']; q = proposal['qualification']; root_id = root['root_id']
    payload = {'deal_algorithm': DEAL_ALGORITHM, 'rule_config': controls['rule_config'],
        'match_id': root_id, 'scenario_id': root_id, 'seed': proposal['seed'], 'round_no': 1,
        'dealer_seat': 0, 'hands': proposal['hands13_by_seat'], 'dealer_drawn_tile': proposal['dealer_drawn_tile'],
        'wall': proposal['wall'], 'wall_front': 0, 'wall_back': len(proposal['wall'])-20,
        'initial_scores': [0,0,0,0], 'timing': controls['timing'], 'rules_hash': engine.rules_hash, 'seq': 0}
    hand = {'replay_schema_version': 1, 'coverage': 'full_world', 'source_kind': 'simulation',
        'initial': {'world_schema': WORLD_SCHEMA, 'world_payload': payload}}
    output.save(directory/'single-hand-teacher-origin.json', {'scope': 'offline_teacher_full_world_only',
        'proposal': proposal, 'hand': hand})
    if root['profile'] == 'opponent_near_completion':
        for seat, codes in proposal['fixed_other_hands'].items():
            summary = call('teacher_structure_analyze_calls', analyse_hand, tuple(Tile(code) for code in codes), 0)
            event({'event': 'teacher_near_completion', 'seat': int(seat), 'standard_shanten': summary.standard_shanten,
                   'scope': 'teacher_only_not_candidate_input'})
            if summary.standard_shanten != 0: raise ControlIneligible('fixed_opponent_standard_shanten_not_zero')
    world = call('world_import_calls', engine.from_replay, hand)
    prefix = output.open(directory/'control-prefix.jsonl', 'xb')
    def record(value): prefix.write(canonical(value)+b'\n');prefix.flush()
    try:
        advances = 0
        while True:
            frame = call('world_frame_calls', engine.frame, world)
            require(frame.blocked_reason is None, '条件来源世界阻塞')
            if frame.final_scores is not None: raise ControlIneligible('script_ended_before_fixed_public_target')
            analyses = []
            for decision in frame.decisions:
                analysis = rules.analyze(decision.observation, route_limits=batch.route_limits)
                require(analysis.completeness.value == 'complete', '控制资格/脚本规则不完整')
                analyses.append(analysis)
            focal_indexes = [i for i,d in enumerate(frame.decisions) if d.window_key.seat == q['focal_seat']]
            facts, eligible = None, False
            if len(focal_indexes) == 1:
                index = focal_indexes[0];decision=frame.decisions[index];obs=decision.observation;analysis=analyses[index]
                whites = sum(t.code == '白' for t in obs.my_hand) + int(obs.drawn_tile is not None and obs.drawn_tile.code == '白')
                hu = [a for a in analysis.legal_candidates if a.action_key == 'hu']
                fan = None
                if hu:
                    require(len(hu) == 1 and hu[0].value_facts is not None and hu[0].value_facts.immediate_settlement is not None,
                        '当前合法胡缺同源即时结算事实')
                    fan = hu[0].value_facts.immediate_settlement.fan
                facts = {'window_key': window_key_to_json(decision.window_key), 'observation': observation_to_json(obs),
                    'legal_action_keys': [a.action_key for a in analysis.legal_candidates],
                    'white_count': whites, 'remaining_tile_count': obs.remaining_tile_count, 'legal_hu_fan': fan,
                    'qualification': q}
                eligible = decision.window_key.phase == q['phase'] and bool(hu) == q['current_legal_hu']
                if 'visible_white_count' in q: eligible &= whites == q['visible_white_count']
                if 'visible_white_count_max' in q: eligible &= whites <= q['visible_white_count_max']
                if 'immediate_fan_lt' in q: eligible &= fan is not None and fan < q['immediate_fan_lt']
                if 'remaining_tile_count_max' in q:
                    eligible &= obs.remaining_tile_count is not None and q['remaining_tile_count_min'] <= obs.remaining_tile_count <= q['remaining_tile_count_max']
            if eligible:
                output.save(directory/'PUBLIC-QUALIFICATION.json', {'status': 'eligible', 'facts': facts,
                    'successful_prefix_frames': advances, 'qualification_uses_candidate_score_or_terminal': False})
                return world, decision.window_key, {'observation_summary': frame_observation_summary(frame),
                    'match_spec': {'match_id': root_id}, 'endpoint': 'current_single_hand_end'}
            if root['profile'] != 'late_wall_low_white_nonhu':
                output.save(directory/'PUBLIC-QUALIFICATION.json', {'status': 'ineligible', 'facts': facts})
                raise ControlIneligible('fixed_initial_public_qualification_failed')
            if advances >= 2000: raise ControlIneligible('fixed_script_2000_advance_limit')
            choices = []
            for decision, analysis in zip(frame.decisions, analyses):
                legal = analysis.legal_candidates
                discard = [a for a in legal if a.action_key.startswith('discard:')]
                drawn = decision.observation.drawn_tile
                exact = [a for a in discard if drawn is not None and a.action_key == 'discard:'+drawn.code]
                selected = exact[0] if exact else (min(discard,key=lambda a:a.action_key) if discard else next((a for a in legal if a.action_key=='pass'),None))
                if selected is None: raise ControlIneligible('fixed_script_no_legal_discard_or_pass')
                choices.append(SimulationChoice(decision.window_key, selected.action))
            row={'ordinal': advances+1, 'revision': frame.revision,
                'choices': [{'window_key': window_key_to_json(c.window_key), 'action_key': action_key(c.action)} for c in choices]}
            record({**row,'status':'advance_pending'})
            world=call('conditional_script_advance_calls',engine.advance,world,frame.revision,tuple(choices));advances+=1
            record({**row,'status':'advanced'})
    finally:
        prefix.close()


async def execute(output_dir: Path, start_path: Path) -> dict:
    """一份ROOT START消费120槽；仅控制资格失败局部继续，其余实错停止。

    总时限7200单调秒包含恢复、脚本、评分和续打，协作检查非抢占。完整
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
        'start_sha256':fingerprint(start_path)['sha256'],'planned_mother_roots':12,'planned_instances':120})
    stream=output.open(output_dir/'calls-and-choices.jsonl','xb')
    counts,root_counts,world_counts=Counter(),{},{};scope={};capture,view_stream,primary=None,None,None
    arms=[{'root_id':r['root_id'],'source_kind':r['source_kind'],'variant':v,'arm':a,'status':'not_started','dispatched':False}
        for r in plan['roots'] for v in VARIANTS for a in ORDER]
    roots=[{'root_id':r['root_id'],'source_kind':r['source_kind'],'profile':r['profile'],'status':'not_started'} for r in plan['roots']]
    result={'status':'unfinished','planned_mother_roots':12,'planned_worlds':24,'planned_continuation_instances':120,
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
        primary=exc;result.update(status='failed_original_120_slots_retained',error=type(exc).__name__+': '+str(exc))
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
        # 120槽终态用窄字段；512KiB费用预留在4GiB内，不另加输出额度。
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
    """prepare只读文件；execute显式消费ROOT START并写完整费用/前缀。"""
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--panel-file',type=Path,required=True)
    p.add_argument('--controls-file',type=Path,default=_project_file(_PROJECT_ROOT, HERE/'CONTROL-TEMPLATES.json'));p.add_argument('--output-dir',type=Path,required=True)
    e=sub.add_parser('execute');e.add_argument('--output-dir',type=Path,required=True);e.add_argument('--start',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare':
        plan=prepare(args.panel_file,args.controls_file,args.output_dir)
        print(canonical({'status':'prepared_no_business_calls','tool_sha256':plan['tool_sha256'],
            'prepared_sha256':fingerprint(args.output_dir/'PREPARED.json')['sha256'],'planned_mother_roots':12,'planned_instances':120}).decode())
    else:
        result=asyncio.run(execute(args.output_dir,args.start));print(canonical({'status':result['status'],'completed_arms':result['completed_arms']}).decode())

if __name__=='__main__': main()
