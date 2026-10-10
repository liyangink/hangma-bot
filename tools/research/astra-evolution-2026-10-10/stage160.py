"""独立十桌、每桌十六单局的配对驱动；固定初庄，真实四席换座。

只编排生产规则、模拟器和策略，不生成第二套规则。相同根的四次换座
作为相关变体整体保留，不当作四个独立阶段。完整产物写私有运行目录。
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
from dataclasses import asdict
import gzip
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time


def canonical(body):
    """固定字节编码，不允许NaN；仅用于研究身份与私有结果。"""
    return json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def save(path,body):
    """原子保存本次产物，不覆盖旧运行目录。"""
    path=Path(path);temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(canonical(body)+b'\n');temp.replace(path)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_tasks(declaration,output):
    """父子同墙同座，对照四个真实相对庄位；十桌种子互异。"""
    if declaration['tables_per_stage']!=10 or declaration['rounds_per_table']!=16:
        raise ValueError('效果阶段必须完整十桌各十六单局')
    if declaration['seat_variants']!=[0,1,2,3]:
        raise ValueError('本驱动要求四个真实换座变体')
    roots=declaration['stage_roots']
    if not roots or len(set(roots))!=len(roots):raise ValueError('阶段根必须非空且唯一')
    opponents=declaration['opponent_tags']
    if len(opponents)!=3 or any(x not in ('P0','RF1') for x in opponents):
        raise ValueError('当前只装验签P0/RF1实验参照，不冒充排行榜对手')
    tasks=[]
    for root in roots:
        for slot in range(10):
            seed=int.from_bytes(hashlib.sha256(f'{root}:table:{slot}'.encode()).digest()[:8],'big')
            for variant in range(4):
                focal=(slot+variant)%4
                tags=[None]*4;tags[focal]='FOCAL'
                for i,tag in enumerate(opponents,1):tags[(focal+i)%4]=tag
                for arm in ('P0','Candidate'):
                    ident=f'{root}:v{variant}:t{slot:02d}:{arm}'
                    tasks.append({'id':ident,'pair_id':f'{root}:v{variant}:t{slot:02d}',
                        'scenario_id':f'{root}:t{slot:02d}','stage_root':root,'table_no':slot,
                        'table_seed':seed,'seat_variant':variant,'focal_seat':focal,'initial_dealer':0,
                        'policy_tags_seat_order_0_to_3':tags,'arm':arm,
                        'out':str(Path(output)/root/f'v{variant}-t{slot:02d}-{arm}'),
                        'runtime_root':declaration['runtime_root'],'rules_hash':declaration['rules_hash'],
                        'candidate':declaration['candidate']})
    return tasks


def verify_declaration(declaration):
    """派发前核冻结文件和资源限额；不替代收益、时限或发布验收。"""
    cap=declaration['cpu_cores']*80//100
    if not 1<=declaration['workers']<=cap:raise ValueError('工作进程超过80%核心上限')
    for path,digest in declaration['frozen_files'].items():
        if file_sha(path)!=digest:raise ValueError('冻结来源漂移: '+path)
    c=declaration['candidate']
    if c['kind'] not in ('P0_identity','factory'):raise ValueError('候选类型不支持')
    if c['kind']=='factory' and file_sha(c['factory_path'])!=c['factory_sha256']:
        raise ValueError('候选工厂原文漂移')


_RUNTIME=None


def runtime(root):
    """一个进程只装一个冻结环境，避免父子模块覆盖或跨根复用。"""
    global _RUNTIME
    root=Path(root).resolve()
    if _RUNTIME is not None:
        if _RUNTIME['root']!=root:raise RuntimeError('禁止同进程混用冻结运行根')
        return _RUNTIME
    sys.path.insert(0,str(root/'src'))
    from hangma_bot import bootstrap
    from hangma_bot.application.deadline import BudgetPolicy
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.kernel.config import RuleConfig,TimingConfig,TournamentConfig
    from hangma_bot.kernel.serialization import observation_to_json
    from hangma_bot.offline.evaluate import drive_match,MatchDriverConfig
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy,VipRouteProjectionLimits
    from hangma_bot.policy.vip_g37_rf1_identity import VIP_G37_RF1_IDENTITY
    from hangma_bot.policy import vip_g37_rf1_release
    from hangma_bot.simulation import SimulationEngine,SimulationChoice,MatchSpec,compute_rules_hash
    metadata,_=bootstrap._verify_vip_s03_runtime()
    p0=bootstrap._load_vip_s03_runtime(metadata['manifest_sha256'])
    base,_=bootstrap._verify_vip_s02_runtime()
    rfmeta,_=vip_g37_rf1_release.verify_compiled_runtime(root,base)
    rf1=vip_g37_rf1_release.load_compiled_runtime(root,rfmeta,bootstrap._load_vip_s02_runtime(base['manifest_sha256']))
    _RUNTIME=locals().copy()
    return _RUNTIME


def candidate_policy(parent,candidate):
    """只加载已冻结可信离线工厂；它仅得到父策略和原单调时钟。"""
    if candidate['kind']=='P0_identity':return parent
    path=Path(candidate['factory_path'])
    if file_sha(path)!=candidate['factory_sha256']:raise RuntimeError('候选源码漂移')
    name='_astra_candidate_'+candidate['factory_sha256'][:16]
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
        sys.modules[name]=module;spec.loader.exec_module(module)
    return sys.modules[name].build_policy(parent,clock=lambda:800.0,params=candidate.get('params'))


class FocalAudit:
    """只记录本家可见事实和实际选择，不向策略提供完整世界。"""
    def __init__(self,inner,sink,rows):self.inner=inner;self.sink=sink;self.rows=rows
    async def choose(self,request,budget):
        began=time.monotonic();plan=await self.inner.choose(request,budget);obs=request.observation
        size=13-3*len(obs.melds[obs.seat]);held=sum(t.code=='白' for t in obs.my_hand)
        if len(obs.my_hand)==size:held+=int(obs.drawn_tile is not None and obs.drawn_tile.code=='白')
        elif len(obs.my_hand)!=size+1 or obs.drawn_tile not in obs.my_hand:held=None
        details=getattr(self.inner,'last_details',None)
        changed=(isinstance(details,dict) and details.get('child_first')==plan.candidates[0].action_key
                 and details.get('parent_first') is not None and details['parent_first']!=details['child_first'])
        row={'round_no':obs.round_no,'seq':request.trigger_seq,'phase':obs.phase,'seat':obs.seat,
            'dealer':obs.dealer_seat,'selected':plan.candidates[0].action_key,
            'current_white':held,'acquired_white':None if held is None else held+sum(t.code=='白' for t in obs.discards[obs.seat]),
            'wall_remaining':obs.remaining_tile_count,'chain_count':obs.rule_state.chain_count,
            'choose_seconds':time.monotonic()-began,'details':details,'changed':changed}
        self.rows.append(row)
        if self.sink is not None:
            # 全量公开输入只收末墙，供后续原点复原；其余轨迹可按全座决策复原。
            if obs.remaining_tile_count is not None and obs.remaining_tile_count<=28:
                from hangma_bot.kernel.serialization import observation_to_json,window_key_to_json
                self.sink.write(canonical({'row':row,'observation':observation_to_json(obs),
                    'window_key':window_key_to_json(request.window_key)})+b'\n')
        return plan


class ExportAudit:
    """透传公开模拟接缝并检查自然结算；完整导出仅给离线评估。"""
    def __init__(self,engine,out):self.engine=engine;self.out=out;self.hands=[]
    def start(self,spec):return self.engine.start(spec)
    def frame(self,world):return self.engine.frame(world)
    def advance(self,world,revision,choices):
        before=self.engine.frame(world).completed_hands;after=self.engine.advance(world,revision,choices)
        completed=self.engine.frame(after).completed_hands
        for n in range(before+1,completed+1):
            self.hands.append(self.engine.export_hand(after,n))
            save(self.out/'RUNNING.json',{'completed_hands':n,'updated_at_unix_seconds':time.time()})
        return after


async def run_table(task):
    """同一规则完整R16；计时为逻辑预算，实际秒数另列，不能授线上准入。"""
    r=runtime(task['runtime_root']);out=Path(task['out']);out.mkdir(parents=True,exist_ok=False)
    save(out/'START.json',task);params=r['VIP_G37_RF1_IDENTITY']['params']
    config=r['TournamentConfig'](10,16,r['RuleConfig'](**params['rule_config']),r['TimingConfig'](1,1,3))
    rules=r['HangmaRules'](config.rules);assert r['compute_rules_hash'](r['root'])==task['rules_hash']
    rows=[];policies=[]
    with gzip.open(out/'TAIL-PUBLIC-INPUTS.jsonl.gz','wb') as sink:
        for seat,tag in enumerate(task['policy_tags_seat_order_0_to_3']):
            tag='P0' if tag=='FOCAL' else tag
            source=r['bootstrap'].VIP_S03_SOURCE if tag=='P0' else r['vip_g37_rf1_release'].source_body(r['root'])
            p=r['RouteVipHeuristicPolicy'](config.rules,source=source,max_operations=params['max_operations'],
                projection_limits=r['VipRouteProjectionLimits'](**params['projection_limits']),
                compiled_runtime=r['p0'] if tag=='P0' else r['rf1'])
            if seat==task['focal_seat']:
                if task['arm']=='Candidate':p=candidate_policy(p,task['candidate'])
                p=FocalAudit(p,sink,rows)
            policies.append(p)
        engine=ExportAudit(r['SimulationEngine'](rules,rules_hash=task['rules_hash']),out)
        spec=r['MatchSpec'](task['id'],task['scenario_id'],config,task['table_seed'],0,(0,0,0,0))
        began=time.monotonic()
        result=await r['drive_match'](engine=engine,spec=spec,policies_by_seat=tuple(policies),rules=rules,
            choice_factory=r['SimulationChoice'],
            config=r['MatchDriverConfig']('logical',100_000,r['BudgetPolicy'](),task['stage_root'],
                strict_policy=True,route_limits=r['ValueAnalysisLimits'](**params['route_limits'])),
            now_monotonic=lambda:800.0,wall_clock=time.monotonic)
    assert result.status=='complete' and result.completed_hands==len(engine.hands)==16
    assert all(v==0 for v in asdict(result.runtime_counts).values())
    assert all(sum(h['score_delta'])==0 for h in engine.hands)
    assert tuple(sum(h['score_delta'][s] for h in engine.hands) for s in range(4))==tuple(result.final_scores)
    closed={'task':task,'status':result.status,'completed_hands':16,'runtime_counts':asdict(result.runtime_counts),
        'final_scores_seat_order_0_to_3':result.final_scores,'focal_score':result.final_scores[task['focal_seat']],
        'elapsed_seconds':time.monotonic()-began,'maximum_focal_choose_seconds':max(x['choose_seconds'] for x in rows),
        'focal_windows':len(rows),'actual_changed_windows':sum(x['changed'] for x in rows)}
    save(out/'FOCAL.json',rows);save(out/'HANDS.json',engine.hands)
    save(out/'DECISIONS.json',[x.to_json() for x in result.decisions]);save(out/'CLOSED.json',closed)
    return closed


def worker(task):
    """失败保留原任务，不补种子，不将失败写成流局。"""
    try:
        os.nice(15)
        return asyncio.run(run_table(task))
    except BaseException as error:
        out=Path(task['out']);out.mkdir(parents=True,exist_ok=True)
        result={'task':task,'status':'worker_failed','error_type':type(error).__name__,'error':str(error)}
        save(out/'FAILED.json',result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--declaration',required=True);p.add_argument('--out',required=True)
    p.add_argument('--plan-only',action='store_true');args=p.parse_args()
    declaration=json.loads(Path(args.declaration).read_text());verify_declaration(declaration)
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=False);tasks=build_tasks(declaration,out)
    save(out/'PLAN.json',{'declaration':declaration,'declaration_sha256':file_sha(args.declaration),
        'driver_sha256':file_sha(__file__),'tasks':tasks,'logical_budget_not_live_admission':True})
    if args.plan_only:return
    pending={};iterator=iter(tasks);results=[];stopped=False
    with concurrent.futures.ProcessPoolExecutor(max_workers=declaration['workers'],
            mp_context=multiprocessing.get_context('spawn')) as pool:
        for _ in range(declaration['workers']):
            task=next(iterator,None)
            if task:pending[pool.submit(worker,task)]=task
        while pending:
            done,_=concurrent.futures.wait(pending,timeout=30,return_when=concurrent.futures.FIRST_COMPLETED)
            if not done:
                print(json.dumps({'heartbeat':True,'closed':len(results),'planned':len(tasks)}),flush=True);continue
            for future in done:
                pending.pop(future);row=future.result();results.append(row)
                save(out/'PROGRESS.json',{'closed':len(results),'planned':len(tasks),'results':results})
                print(json.dumps({'closed':len(results),'planned':len(tasks),'stage':row['task']['stage_root'],
                    'arm':row['task']['arm'],'status':row['status'],'score':row.get('focal_score'),
                    'changed':row.get('actual_changed_windows'),'error':row.get('error')}),flush=True)
                if row['status']!='complete':stopped=True
            if not stopped:
                for _ in done:
                    task=next(iterator,None)
                    if task:pending[pool.submit(worker,task)]=task
    save(out/'RUN-CLOSED.json',{'complete':len(results)==len(tasks) and not stopped,
        'closed':len(results),'planned':len(tasks),'results':results})


if __name__=='__main__':main()
