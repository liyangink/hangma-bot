"""只接收完整配对阶段；按独立根统计，四个换座变体保持相关。"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import statistics


def read(path):
    return json.loads(Path(path).read_text())


def signature(decisions):
    """忽略臂内游戏标识和耗时，保留所有座位的真实行动轨迹。"""
    return [(r['window_key']['round_no'],r['window_key']['trigger_seq'],r['window_key']['phase'],
             r['seat'],r['action_key']) for r in decisions]


def root_statistics(values, *, bootstrap_seed=20261010, resamples=10000):
    """每个输入值必须是完整独立根的四席均值；单根不授区间。"""
    values=list(values)
    if not values:raise ValueError('没有完整独立阶段')
    result={'independent_roots':len(values),'values':values,'mean':statistics.mean(values),
            'minimum':min(values),'maximum':max(values),'positive_roots':sum(v>0 for v in values),
            'zero_roots':sum(v==0 for v in values),'negative_roots':sum(v<0 for v in values)}
    if len(values)<2:return {**result,'root_bootstrap_95_percent_interval':None}
    rng=random.Random(bootstrap_seed);n=len(values)
    samples=sorted(sum(rng.choice(values) for _ in range(n))/n for _ in range(resamples))
    return {**result,'root_bootstrap_95_percent_interval':[samples[int(.025*resamples)],samples[int(.975*resamples)-1]],
            'bootstrap_seed':bootstrap_seed,'resamples':resamples}


def hand_facts(hand,focal):
    """白数为该单局配牌加实际摸入；支付按庄闲分账，不猜听牌状态。"""
    initial=hand['initial'];dealer=initial['dealer_seat'];winner=hand['winner_seat'];delta=hand['score_delta']
    white=[sum(t=='白' for t in h) for h in initial['hands']]
    draws=[int(initial['drawn_seat']==s) for s in range(4)]
    for e in hand['events']:
        if e['type']=='tile_drawn':
            draws[e['seat']]+=1;white[e['seat']]+=int(e['tile']=='白')
    own_win=winner==focal;fan=hand['fan'];bin_=str(min(2,white[focal]))
    fact={'white_bin':bin_,'white_by_seat':white,'draws_by_seat':draws,
          'net':delta[focal],'hands':1,'own_hu':int(own_win),'draw_hand':int(hand['is_draw']),
          'ordinary_hu':int(own_win and fan<4),'ordinary_income':delta[focal] if own_win and fan<4 else 0,
          'highfan_hu':int(own_win and fan>=4),'highfan_income':delta[focal] if own_win and fan>=4 else 0,
          'multiwhite_income':delta[focal] if own_win and white[focal]>=2 else 0,
          'dealer_hands':int(dealer==focal),'dealer_hu':int(own_win and dealer==focal),
          'idle_hu':int(own_win and dealer!=focal),'other_dealer_hu':int(winner==dealer and dealer!=focal),
          'dealer_to_idle_payment':0,'idle_to_dealer_payment':0,'idle_to_idle_payment':0,
          'own_draws_to_hu':draws[focal] if own_win else 0}
    if winner is not None and not own_win:
        key='dealer_to_idle_payment' if focal==dealer else ('idle_to_dealer_payment' if winner==dealer else 'idle_to_idle_payment')
        fact[key]=-delta[focal]
    return fact


METRICS=('net','hands','own_hu','draw_hand','ordinary_hu','ordinary_income','highfan_hu',
         'highfan_income','multiwhite_income','dealer_hands','dealer_hu','idle_hu','other_dealer_hu',
         'dealer_to_idle_payment','idle_to_dealer_payment','idle_to_idle_payment','own_draws_to_hu')


def analyze_table(task,closed,hands,decisions,focal_rows,place_points):
    """拒绝缺局、非守恒、运行故障及错误任务身份；未知不填零。"""
    if closed['task']!=task:raise ValueError('闭合任务身份漂移')
    if closed['status']!='complete' or closed['completed_hands']!=16 or len(hands)!=16:
        raise ValueError('不完整十六单局桌赛')
    if any(closed['runtime_counts'].values()):raise ValueError('存在运行故障')
    if [h['round_no'] for h in hands]!=list(range(1,17)):raise ValueError('单局缺失或重复')
    # 强制唯一过牌也标记is_emergency；它不是故障降级，运行计数与原因另核。
    if not all(d['legal'] and d['fallback_reason'] is None and not d['degraded_reasons'] for d in decisions):
        raise ValueError('行动存在降级或合法性问题')
    focal=task['focal_seat'];total={k:0 for k in METRICS};bins={b:{k:0 for k in METRICS} for b in ('0','1','2')}
    white_by_seat=[0]*4;score=[0]*4;held_dealer=stolen_dealer=draw_held=0
    for i,h in enumerate(hands):
        if h['coverage']!='full_world' or h['attempt_status']!='valid' or not h['result_confirmed'] or h['missing_fields']:
            raise ValueError('完整导出证据不足')
        if h['rules_hash']!=task['rules_hash'] or sum(h['score_delta'])!=0:raise ValueError('规则或积分守恒失败')
        if h['scores_before']!=score:raise ValueError('单局积分前后不连续')
        score=[score[s]+h['score_delta'][s] for s in range(4)]
        if h['scores_after']!=score:raise ValueError('单局终分不匹配')
        payload=h['initial']['world_payload']
        if payload['seed']!=task['table_seed'] or payload['scenario_id']!=task['scenario_id']:
            raise ValueError('牌山来源漂移')
        f=hand_facts(h,focal)
        for k in METRICS:total[k]+=f[k];bins[f['white_bin']][k]+=f[k]
        for s in range(4):white_by_seat[s]+=f['white_by_seat'][s]
        if i<15:
            if hands[i+1]['initial']['dealer_seat']==focal:
                if h['winner_seat']==focal:
                    held_dealer+=int(h['initial']['dealer_seat']==focal)
                    stolen_dealer+=int(h['initial']['dealer_seat']!=focal)
                elif h['is_draw'] and h['initial']['dealer_seat']==focal:draw_held+=1
    if score!=closed['final_scores_seat_order_0_to_3'] or score[focal]!=closed['focal_score']:
        raise ValueError('桌赛终分不匹配')
    total.update({'place_points':place_points(score)[focal],'god_count':white_by_seat[focal],
                  'hu_held_dealer_with_next_hand':held_dealer,'hu_stolen_dealer_with_next_hand':stolen_dealer,
                  'draw_held_dealer_with_next_hand':draw_held,'changed_windows':sum(bool(x['changed']) for x in focal_rows)})
    if total['changed_windows']!=closed['actual_changed_windows']:raise ValueError('改选计数不匹配')
    return {'metrics':total,'white_bins':bins,'score_by_seat':score,'white_by_seat':white_by_seat,
            'points_by_seat':place_points(score),'action_signature':signature(decisions),
            'first_deal':{'hands':hands[0]['initial']['hands'],'wall':hands[0]['initial']['wall'],
                          'dealer':hands[0]['initial']['dealer_seat']},
            'walls_by_hand':[h['initial']['wall'] for h in hands],
            'maximum_focal_choose_seconds':closed['maximum_focal_choose_seconds']}


def rank_intervals(ledger):
    """三键按字典序；完全并列给区间，四实验角色的名次不是官方晋级率。"""
    keys=[(r['total_score'],r['place_points'],r['god_count']) for r in ledger]
    return [[1+sum(x>k for x in keys),sum(x>=k for x in keys)] for k in keys]


def summarize(directory,place_points):
    """全计划无缺漏才汇总；保留所有零活动根和换座变体。"""
    directory=Path(directory);plan=read(directory/'PLAN.json');end=read(directory/'RUN-CLOSED.json');declaration=plan['declaration']
    if not end['complete'] or end['closed']!=end['planned'] or end['planned']!=len(plan['tasks']):raise ValueError('运行计划未全部闭合')
    if declaration['tables_per_stage']!=10 or declaration['rounds_per_table']!=16 or declaration['seat_variants']!=[0,1,2,3]:raise ValueError('不是160单局真四席计划')
    expected={(r,v,s,a) for r in declaration['stage_roots'] for v in range(4) for s in range(10) for a in ('P0','Candidate')}
    actual={(t['stage_root'],t['seat_variant'],t['table_no'],t['arm']) for t in plan['tasks']}
    if actual!=expected or len(plan['tasks'])!=len(expected):raise ValueError('任务矩阵缺漏或混入未声明根')
    if {x['task']['id'] for x in end['results']}!={x['id'] for x in plan['tasks']}:
        raise ValueError('最终派发账本与计划不同')
    matrix=defaultdict(dict);tables={};index=set()
    for t in plan['tasks']:
        key=(t['stage_root'],t['seat_variant'],t['table_no'],t['arm'])
        if key in index:raise ValueError('重复任务')
        index.add(key);out=Path(t['out'])
        tables[key]=analyze_table(t,read(out/'CLOSED.json'),read(out/'HANDS.json'),read(out/'DECISIONS.json'),read(out/'FOCAL.json'),place_points)
        matrix[(t['stage_root'],t['seat_variant'],t['table_no'])][t['arm']]=t
    pairs=[]
    for key,arms in matrix.items():
        if set(arms)!={'P0','Candidate'}:raise ValueError('配对缺臂')
        a=arms['P0'];b=arms['Candidate']
        for k in ('table_seed','scenario_id','focal_seat','initial_dealer','policy_tags_seat_order_0_to_3','rules_hash'):
            if a[k]!=b[k]:raise ValueError('配对初始条件不同')
        parent=tables[(*key,'P0')];child=tables[(*key,'Candidate')]
        if parent['first_deal']!=child['first_deal'] or parent['walls_by_hand']!=child['walls_by_hand']:
            raise ValueError('父子不在同牌山')
        same=parent['action_signature']==child['action_signature']
        if declaration['candidate']['kind']=='P0_identity' and (not same or parent['score_by_seat']!=child['score_by_seat']):
            raise ValueError('同算法对照轨迹分歧')
        pairs.append({'stage_root':key[0],'variant':key[1],'table':key[2],
                      'net_delta':child['metrics']['net']-parent['metrics']['net'],'same_action_trajectory':same})
    roots=[];allkeys=tuple(next(iter(tables.values()))['metrics'])
    for root in declaration['stage_roots']:
        variants=[]
        for slot in range(10):
            ts=[matrix[(root,v,slot)]['P0'] for v in range(4)]
            if {t['focal_seat'] for t in ts}!={0,1,2,3} or {t['initial_dealer'] for t in ts}!={0}:
                raise ValueError('换座只是同构平移')
            if len({t['table_seed'] for t in ts})!=1:raise ValueError('换座种子漂移')
        if len({matrix[(root,0,s)]['P0']['table_seed'] for s in range(10)})!=10:raise ValueError('十桌种子不独立')
        for variant in range(4):
            arms={};ledgers={}
            for arm in ('P0','Candidate'):
                own=[tables[(root,variant,s,arm)] for s in range(10)]
                if len(own)!=10 or sum(x['metrics']['hands'] for x in own)!=160:raise ValueError('不是完整160单局阶段')
                arms[arm]={'metrics':{k:sum(x['metrics'][k] for x in own) for k in allkeys},
                    'white_bins':{b:{k:sum(x['white_bins'][b][k] for x in own) for k in METRICS} for b in ('0','1','2')}}
                ledger=[{'role':i,'total_score':0,'place_points':0,'god_count':0} for i in range(4)]
                for s,x in enumerate(own):
                    focal=matrix[(root,variant,s)][arm]['focal_seat']
                    for relative in range(4):
                        physical=(focal+relative)%4
                        ledger[relative]['total_score']+=x['score_by_seat'][physical]
                        ledger[relative]['place_points']+=x['points_by_seat'][physical]
                        ledger[relative]['god_count']+=x['white_by_seat'][physical]
                intervals=rank_intervals(ledger)
                ledgers[arm]={'roles_relative_to_focal_0_to_3':ledger,'focal_rank_interval':intervals[0],
                              'scope':'四个实验策略槽位的阶段三键对比，不是官方排行榜晋级率'}
            variants.append({'variant':variant,'arms':arms,'ledger':ledgers,
                'delta':{k:arms['Candidate']['metrics'][k]-arms['P0']['metrics'][k] for k in allkeys},
                'white_bin_delta':{b:{k:arms['Candidate']['white_bins'][b][k]-arms['P0']['white_bins'][b][k] for k in METRICS} for b in ('0','1','2')}})
        roots.append({'root':root,'variants':variants,
                      'mean_delta_four_correlated_variants':{k:statistics.mean(v['delta'][k] for v in variants) for k in allkeys}})
    return {'schema':'astra-stage160-summary/1','complete':True,'independent_roots':len(roots),
        'completed_table_instances':len(tables),'paired_tables':len(pairs),'stage_hands_per_arm_per_variant':160,
        'root_statistics':{k:root_statistics([r['mean_delta_four_correlated_variants'][k] for r in roots]) for k in allkeys},
        'roots':roots,'pairs':pairs,'all_zero_activity_roots_retained':True,
        'maximum_observed_choose_seconds':max(x['maximum_focal_choose_seconds'] for x in tables.values()),
        'timing_is_logical_not_online_admission':True,
        'white_bin_scope':'按实际累计取白分层，策略影响终止时点；分布描述而非固定白条件因果效应',
        'ting_speed_and_shape_not_in_driver_v1':True,
        'plan_sha256':hashlib.sha256((directory/'PLAN.json').read_bytes()).hexdigest(),
        'strength_claim':False,'opponent_pool':'当前冻结P0/RF1实验参照，不冒充排行榜强手'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[3];path=root/'tools/offline/sitin/sitin_stage.py'
    spec=importlib.util.spec_from_file_location('astra_sitin_points',path);module=importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name]=module;spec.loader.exec_module(module)
    report=summarize(args.run,module.place_points_for_table)
    target=Path(args.run)/'SUMMARY.json'
    if target.exists():raise ValueError('不覆盖旧汇总')
    target.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'complete':True,'instances':report['completed_table_instances'],'roots':report['independent_roots'],
        'net':report['root_statistics']['net'],'changed':report['root_statistics']['changed_windows']},ensure_ascii=False))


if __name__=='__main__':main()
