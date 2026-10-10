"""从现有公开规则审计聚合首次待胡形状与摸牌次序，不修改策略。"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def waiting_shape(row):
    """仅实际弃牌或过牌后的等待态；未知与已知空集合分别返回。"""
    if not (row['selected'].startswith('discard:') or row['selected']=='pass'):
        return {'status':'not_waiting','codes':[],'capacity':None}
    value=row.get('selected_value_facts')
    if value is None:return {'status':'unknown','codes':[],'capacity':None}
    codes={};payments=defaultdict(list)
    for route in value['routes']:
        if route['followup_discard'] is not None or route['conditions']['draw_kind']!='normal':continue
        for tile in route['useful_tiles']:
            code=tile['code'];capacity=tile['remaining_estimate']
            if code in codes and codes[code]!=capacity:raise ValueError('同一等待态同码容量冲突')
            if capacity>0:
                codes[code]=capacity
                payments[code].append(route['conditional_settlement']['score_delta'][row['seat']])
    complete=value['coverage']=='complete' and not value['issues']
    if not codes:return {'status':'known_empty' if complete else 'unknown','codes':[],'capacity':0 if complete else None}
    return {'status':'known_positive_complete' if complete else 'known_positive_partial',
            'codes':sorted(codes),'code_width':len(codes),'capacity':sum(codes.values()),
            'income_envelopes':{k:[min(v),max(v)] for k,v in sorted(payments.items())}}


def hand_tempo(hand,rows,focal):
    """次序含庄家直抽、普通摸和杠补；吃碰后无摸弃牌不会加一次。"""
    initial_draw=int(hand['initial']['drawn_seat']==focal)
    draw_sequences=[e['seq'] for e in hand['events'] if e['type']=='tile_drawn' and e['seat']==focal]
    structural=None;waiting=None;unknown=0;hu=None
    for row in sorted(rows,key=lambda x:x['seq']):
        if row['round_no']!=hand['round_no'] or row['seat']!=focal:raise ValueError('单局审计身份错误')
        ordinal=initial_draw+sum(seq<=row['seq'] for seq in draw_sequences)
        if row['selected']=='hu':hu={'seq':row['seq'],'own_draw_ordinal':ordinal}
        fact=row.get('selected_rule_facts')
        if (structural is None and row['selected'].startswith('discard:') and fact is not None
                and fact['completeness']=='complete' and fact['shanten_after']==0):
            structural={'seq':row['seq'],'own_draw_ordinal':ordinal}
        shape=waiting_shape(row)
        unknown+=int(shape['status']=='unknown')
        if waiting is None and shape['status'].startswith('known_positive'):
            waiting={'seq':row['seq'],'own_draw_ordinal':ordinal,'shape':shape,
                     'current_white':row['current_white'],'acquired_white':row['acquired_white']}
    own_win=hand['winner_seat']==focal
    if own_win!=(hu is not None):raise ValueError('实际胡牌与公开选择不一致')
    initial_white=sum(t=='白' for t in hand['initial']['hands'][focal])
    acquired_white=initial_white+sum(e['type']=='tile_drawn' and e['seat']==focal and e['tile']=='白' for e in hand['events'])
    return {'round_no':hand['round_no'],'focal_seat':focal,'dealer_seat':hand['initial']['dealer_seat'],
            'initial_white':initial_white,'final_acquired_white':acquired_white,
            'first_structural_zero_after_discard':structural,'first_known_normal_hu_waiting_witness':waiting,
            'waiting_coverage_unknown_windows':unknown,'own_draws_to_hand_end':initial_draw+len(draw_sequences),
            'own_hu':hu,'own_hu_income':hand['score_delta'][focal] if own_win else None,
            'own_hu_fan':hand['fan'] if own_win else None,
            'hu_without_observed_waiting_witness':own_win and waiting is None}


def aggregate(hands):
    """速度均值只描述进入该条件的人群；保留无见证、未胡及未知的分母。"""
    waits=[h['first_known_normal_hu_waiting_witness'] for h in hands if h['first_known_normal_hu_waiting_witness'] is not None]
    zeros=[h['first_structural_zero_after_discard'] for h in hands if h['first_structural_zero_after_discard'] is not None]
    hus=[h['own_hu'] for h in hands if h['own_hu'] is not None]
    return {'hands':len(hands),'structural_zero_hands':len(zeros),'waiting_witness_hands':len(waits),
        'no_observed_waiting_witness_hands':len(hands)-len(waits),'own_hu_hands':len(hus),
        'hu_without_waiting_witness_hands':sum(h['hu_without_observed_waiting_witness'] for h in hands),
        'waiting_coverage_unknown_windows':sum(h['waiting_coverage_unknown_windows'] for h in hands),
        'partial_first_waiting_witness_hands':sum(w['shape']['status']=='known_positive_partial' for w in waits),
        'mean_own_draw_ordinal_to_structural_zero':None if not zeros else sum(z['own_draw_ordinal'] for z in zeros)/len(zeros),
        'mean_own_draw_ordinal_to_waiting_witness':None if not waits else sum(w['own_draw_ordinal'] for w in waits)/len(waits),
        'mean_first_waiting_code_width':None if not waits else sum(w['shape']['code_width'] for w in waits)/len(waits),
        'mean_first_waiting_public_capacity':None if not waits else sum(w['shape']['capacity'] for w in waits)/len(waits),
        'mean_own_draw_ordinal_to_hu':None if not hus else sum(h['own_draw_ordinal'] for h in hus)/len(hus)}


def summarize(directory):
    """先核完整阶段主报告，再按全部十桌生成描述性速度报告。"""
    directory=Path(directory);plan=read(directory/'PLAN.json');end=read(directory/'RUN-CLOSED.json');primary=read(directory/'SUMMARY.json')
    if not end['complete'] or not primary['complete'] or primary['completed_table_instances']!=len(plan['tasks']):
        raise ValueError('缺完整阶段主报告')
    if primary['plan_sha256']!=hashlib.sha256((directory/'PLAN.json').read_bytes()).hexdigest():raise ValueError('主报告来源漂移')
    groups=defaultdict(list);tables={}
    for task in plan['tasks']:
        out=Path(task['out']);hands=read(out/'HANDS.json');rows=read(out/'FOCAL.json')
        if len(hands)!=16 or any('selected_rule_facts' not in r or 'selected_value_facts' not in r for r in rows):
            raise ValueError('未装完整牌效审计，不能猜听牌事实')
        by_round=defaultdict(list)
        for row in rows:by_round[row['round_no']].append(row)
        records=[hand_tempo(h,by_round[h['round_no']],task['focal_seat']) for h in hands]
        key=(task['stage_root'],task['seat_variant'],task['arm']);groups[key].extend(records)
        tables[(task['pair_id'],task['arm'])]=(task,hands,records)
    stages=[]
    for (root,variant,arm),hands in sorted(groups.items()):
        if len(hands)!=160:raise ValueError('不是完整160单局')
        stages.append({'root':root,'variant':variant,'arm':arm,'metrics':aggregate(hands),
            'by_initial_white':{str(b):aggregate([h for h in hands if min(2,h['initial_white'])==b]) for b in range(3)},
            'by_final_acquired_white':{str(b):aggregate([h for h in hands if min(2,h['final_acquired_white'])==b]) for b in range(3)},
            'by_dealer_role':{role:aggregate([h for h in hands if (h['focal_seat']==h['dealer_seat'])==(role=='dealer')]) for role in ('dealer','idle')}})
    paired=[]
    for pair_id in sorted({k[0] for k in tables}):
        p,ph,pr=tables[(pair_id,'P0')];c,ch,cr=tables[(pair_id,'Candidate')];focal=p['focal_seat']
        if c['focal_seat']!=focal:raise ValueError('父子座位不同')
        for a,b,x,y in zip(ph,ch,pr,cr):
            same_deal=(a['initial']['dealer_seat']==b['initial']['dealer_seat'] and a['initial']['hands'][focal]==b['initial']['hands'][focal])
            if same_deal and x['own_hu'] is not None and y['own_hu'] is not None:
                paired.append({'pair_id':pair_id,'round_no':a['round_no'],
                    'own_draw_ordinal_delta':y['own_hu']['own_draw_ordinal']-x['own_hu']['own_draw_ordinal'],
                    'same_fan_and_income':x['own_hu_fan']==y['own_hu_fan'] and x['own_hu_income']==y['own_hu_income']})
    return {'schema':'astra-stage160-tempo/2','complete':True,'stages':stages,'matched_both_hu_same_initial_hand':paired,
        'reporter_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'primary_summary_sha256':hashlib.sha256((directory/'SUMMARY.json').read_bytes()).hexdigest(),
        'shape_scope':'当前等待态的已知普通摸牌条件胡见证；公开容量不是牌墙概率，不保证未来摸到或先于他家胡',
        'speed_scope':'实际本人摸牌次序包含庄家直抽和杠补；未听未胡与未知保留，条件均值不作为因果速度增益',
        'paired_speed_scope':'相同初庄及本家初牌且两臂都胡的描述性子组，不替代全部阶段净积分和收入保护',
        'white_bins_scope':'0/1/2代表0/1/至少2；初白与累计取得白分别保留，累计白分层会随策略终止时点变化',
        'four_variants_are_correlated':True,'strength_claim':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);args=parser.parse_args()
    output=Path(args.run)/'TEMPO-V2.json'
    if output.exists():raise ValueError('不覆盖旧速度报告')
    report=summarize(args.run);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'complete':True,'stage_variants_arms':len(report['stages']),
                      'matched_both_hu':len(report['matched_both_hu_same_initial_hand'])}))


if __name__=='__main__':main()
