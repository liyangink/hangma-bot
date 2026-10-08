"""通过公开策略入口比较V2种子；真实开发窗与工程夹具分列，不产生效果样本。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

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
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROUTE=_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO=_PROJECT_ROOT
sys.path.insert(0,str(REPO))
sys.path.insert(0,str(_project_file(_PROJECT_ROOT, ROUTE/'tools')))
import sitin_real_behavior as behavior
from hangma_bot.hangma.interface import CandidateFactKind as Kind, RuleCompleteness, UsefulTileFact
from hangma_bot.kernel.actions import Discard, Hu, Pass, Peng, Chi, Gang, GangKind, Tile
from hangma_bot.kernel.observation import PublicMeld
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.evaluation_v2 import has_waiting_baseline
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from tests.unit.policy.support import make_observation,make_request,make_rules,make_budget,rejected
from tests.unit.policy.test_heuristic_v2 import progress,candidate


def scope(request):
    """按输入冻结严格比较范围；排除原因独立于被测候选输出，防止选择性删错。"""
    cs=request.rules.legal_candidates
    reasons=[]
    if request.rejected_attempts:
        reasons.append('rejected_actions_not_visible')
    if any(isinstance(c.action,Pass) for c in cs) and not any(has_waiting_baseline(c) for c in cs):
        reasons.append('missing_waiting_baseline_contract_difference')
    if any(c.facts and c.facts.completeness!=RuleCompleteness.COMPLETE for c in cs):
        reasons.append('fact_completeness_not_visible')
    trusted=any(isinstance(c.action,Hu) or (c.facts is not None
        and c.facts.completeness==RuleCompleteness.COMPLETE
        and c.facts.fact_kind==Kind.HAND_PROGRESS
        and type(c.facts.shanten_after) is int and c.facts.shanten_after>=0) for c in cs)
    if not trusted:
        reasons.append('all_unknown_emergency_identity_not_visible')
    return reasons


def fixtures():
    """工程夹具只控制策略输入事实；不声称牌型合法性或自然分布覆盖。"""
    cases=[]
    def add(name,cs,obs=None,emergency=None,rejections=()):
        request=make_request(obs or make_observation(),make_rules(cs,emergency),rejected=rejections)
        cases.append((name,request))
    def d(code,s,u=0):
        return candidate(Discard(Tile(code)),progress(s,u))
    add('shanten_priority',[d('1w',1,0),d('2w',2,40)])
    add('support_not_clipped',[d('1w',2,20),d('2w',2,40)])
    add('tie_action_key',[d('2w',2,20),d('1w',2,20)])
    add('hu_priority',[candidate(Hu()),d('1w',0,80)])
    extreme=replace(progress(0),useful_tiles=(UsefulTileFact('1w',4),)*300)
    add('hu_priority_extreme_contract_fixture',[candidate(Hu()),candidate(Discard(Tile('2w')),extreme)])
    add('unknown_below_negative',[candidate(Discard(Tile('1w'))),d('2w',4,0)])
    for kind in (GangKind.CONCEALED,GangKind.ADDED,GangKind.EXPOSED):
        add('gang_'+kind.value,[candidate(Gang(Tile('1w'),kind),progress(1,0,replacement_draw_unknown=True)),d('2w',1,30)])
    for action in (Peng(Tile('5w')),Chi(tuple(Tile(c) for c in ('1w','2w','3w')))):
        for no,(w,c) in enumerate((((2,20),(1,15)),((1,15),(1,15)),((1,10),(1,25)),((0,0),(0,0)),((1,20),(2,30)))):
            add(type(action).__name__+str(no),[candidate(Pass(),progress(*w)),candidate(action,progress(*c,best_followup_discard='9t'))])
    hand=tuple(Tile(c) for c in '1w 1w 2w 3w 4w 5w 6w 7w 8w 9w 1t 2t 3t'.split())
    for included in (False,True):
        obs=make_observation(my_hand=hand+( (Tile('白'),) if included else ()),drawn_tile=Tile('白'))
        add('wealth_draw_included_'+str(included),[d('白',1,60),d('1w',1,0)],obs)
    rivers=((),(Tile('3w'),),(),())
    add('own_river_is_not_opponent_safe',[d('3w',1,0),d('1w',1,5)],make_observation(discards=((Tile('3w'),),(),(),())))
    for scores,label in (((0,0,0,0),'tied_first'),((-1,1,2,3),'last'),((1,2,0,-1),'middle')):
        add('style_'+label,[d('3w',1,0),d('1w',1,5)],make_observation(scores=scores,discards=rivers))
    add('style_best_shanten_excludes_pass',[candidate(Pass(),progress(0,0)),d('1w',1,4),d('2w',1,3)],make_observation(scores=(-3,0,1,2)))
    meld=PublicMeld(1,'peng',(Tile('4w'),)*3,2)
    add('next_seat_also_dealer_risk',[d('3w',1,12),d('9t',1,0)],make_observation(dealer_seat=1,melds=((),(meld,),(),())))
    add('familiar_skips_feed_risk',[d('3w',1,0),d('9t',1,0)],make_observation(dealer_seat=1,melds=((),(meld,),(),()),discards=rivers))
    unknown=candidate(Discard(Tile('2w')))
    add('boundary_all_unknown',[candidate(Discard(Tile('1w'))),unknown],emergency=unknown)
    add('boundary_missing_pass',[candidate(Pass()),candidate(Peng(Tile('5w')),progress(0,20))])
    add('boundary_rejected',[d('1w',1,0),d('2w',1,1)],rejections=(rejected('discard:1w'),))
    return cases


def run(source):
    """比较完整动作序列并保留范围外结果；失败不能算等价。"""
    scorer=ActionValueScorer('v2-seed-parity',source)
    panel_digest,real=behavior.load_panel(_project_file(_PROJECT_ROOT, HERE/'batch03-known-root-diagnostic/panel.json'))
    rows=[]
    for origin,items in [('real_development',real),('controlled_fixture',fixtures())]:
        for name,request in items:
            baseline=asyncio.run(ComparableHeuristicPolicyV2(monotonic=lambda:0).choose(request,make_budget()))
            observed=behavior.evaluate_request(scorer,name,request)
            expected=[c.action_key for c in baseline.candidates]
            outside=scope(request)
            rows.append({'name':name,'origin':origin,'excluded_reasons':outside,'strict_scope':not outside,
                'status':observed['status'],'v2_order':expected,'candidate_order':observed['ordered_actions'],
                'full_order_equal':observed['status']=='SCORED' and expected==observed['ordered_actions'],
                'v2_scores':{c.action_key:c.total_score for c in baseline.candidates},
                'candidate_scores':observed['scores'],'input_digest':behavior.digest(behavior.capture_request(request))})
    strict=[r for r in rows if r['strict_scope']]
    execution_acceptable=all(r['status']=='SCORED' or (r['status']=='ABSTAIN'
        and 'all_unknown_emergency_identity_not_visible' in r['excluded_reasons']) for r in rows)
    return {'schema':'v2-seed-parity/2','source_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'suite_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'panel_digest':panel_digest,'strict_count':len(strict),'strict_mismatches':sum(not r['full_order_equal'] for r in strict),
        'total_count':len(rows),'all_scored':all(r['status']=='SCORED' for r in rows),
        'execution_acceptable':execution_acceptable,
        'strict_pass':bool(strict) and all(r['full_order_equal'] for r in strict),
        'rows':rows,'selection_eligible':False,'release_eligible':False,
        'scope':'仅本开发清单与工程夹具；不是全域V2等价、规则验证或强度样本'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args()
    if a.output.exists():raise SystemExit('输出已存在，不覆盖历史验收')
    result=run(a.candidate.read_text())
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('strict_count','strict_mismatches','total_count','all_scored','execution_acceptable','strict_pass')}))
    raise SystemExit(0 if result['strict_pass'] and result['execution_acceptable'] else 1)
