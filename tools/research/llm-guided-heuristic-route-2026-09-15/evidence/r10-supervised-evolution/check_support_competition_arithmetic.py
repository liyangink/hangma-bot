"""显式机会边的有理数手算、单机制消融和生产选择核验；不重写规则。"""

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
from dataclasses import replace
from fractions import Fraction as F
import math
import re
import strong_seed_batch as b
import support_competition_batch as task
from check_discard_arithmetic import action, view
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicMeld
from hangma_bot.hangma.interface import UsefulTileFact
from hangma_bot.policy.action_value_seeds import ActionValueScorer

BASE=b.HERE/'v2-seed-terra-02/run/iterations/iter-01/generation/candidate.py'

def sample(codes, meld_count, live):
    """弃北后留下给定牌位；向听为合同夹具，非这些牌的真实规则裁定。"""
    hand=tuple(codes)+('白',)*(13-3*meld_count-len(codes))+('北',)
    assert len(hand)==14-3*meld_count and max(hand.count(t) for t in hand)<=4
    facts=tuple(UsefulTileFact(t,4-hand.count(t)) for t in live)
    a=replace(action('北',None),fact_kind='hand_progress',shanten_after=1,useful_tiles=facts,
              standard_shanten_after=1,standard_useful_tiles=facts)
    v=view((a,),familiar=())
    melds=tuple(PublicMeld(0,'chi',tuple(Tile(str(n)+s) for n in (7,8,9)),3) for s in 'wbt'[:meld_count])
    return replace(v,visible_state=replace(v.visible_state,my_hand=tuple(Tile(t) for t in hand),
                   drawn_tile=None,melds=(melds,(),(),())))

def rational(n, edges):
    """给定人工列举的牌位机会边，精确计算需求、容量分配、溢出和孤张。"""
    demand=[sum((q for slots,q in edges if i in slots),F(0)) for i in range(n)]
    alloc=[q*min([F(1)]+[1/demand[i] for i in slots]) for slots,q in edges]
    capacity=[sum((a for (slots,_),a in zip(edges,alloc) if i in slots),F(0)) for i in range(n)]
    assert all(F(0)<=c<=1 for c in capacity)
    allocated=sum(capacity,F(0));overflow=sum((max(d-1,0) for d in demand),F(0));orphan=demand.count(0)
    net=allocated-orphan-overflow/4
    return {'allocated_units':float(allocated),'overflow_units':float(overflow),'orphan_slots':orphan,
            'net_units':float(net),'clipped_units':float(max(-10,min(10,net))),
            'part':round(float(max(-10,min(10,net))/5),6),'opportunity_count':len(edges),
            'eligible_slots':n,'exact_capacity':[str(c) for c in capacity]}

def main():
    """产物一次写入；负结果保留，不通过修改候选或夹具隐藏失败。"""
    sub=task.OUT/task.NAME;state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    source=b.Path(state['iter_dir'])/'generation/candidate.py';parent=b.Path(b.read(task.OUT/'manifest.json')['parent'])/'candidate.py'
    scorers={k:ActionValueScorer(k,p.read_text()) for k,p in [('base',BASE),('parent',parent),('candidate',source)]}
    q=F(3,4);half=F(1,2)
    pair=[((0,1),q)];triangle=pair+[((0,2),q),((1,2),q)]
    recombine=[((0,1),q),((2,3),q),((0,2),q),((0,3),q),((1,2),q),((1,3),q),
               ((2,4),q),((3,4),q),((0,4),half),((1,4),half),((0,2,4),F(1))]
    specs=[('shared_556',('5w','5w','6w'),3,('9b',),triangle),
           ('recombined_44556',('4w','4w','5w','5w','6w'),2,('5w',),recombine),
           ('made_123',('1w','2w','3w'),3,('2w',),[((0,1),q),((1,2),q),((0,2),half),((0,1,2),F(1))]),
           ('honor_pair',('东','东'),3,('9b',),pair),
           ('number_pair',('5w','5w'),3,('9b',),pair),
           ('made_triplet',('5w','5w','5w'),3,('9b',),triangle+[((0,1,2),F(1))]),
           ('negative_cap',('1w','5w','9w','1b','5b','9b','1t','5t','9t','东','南','西'),0,('2w',),[])]
    rows=[]
    for name,codes,melds,live,edges in specs:
        v=sample(codes,melds,live);want=rational(len(codes),edges);got=scorers['candidate'].score(v);base=scorers['base'].score(v)
        errors=[]
        if got.status!='SCORED' or base.status!='SCORED':errors.append('status')
        t=dict(got.entries[0].trace['shared_support_competition_v1'])
        if t['active'] is not True:errors.append('activation')
        for key,value in want.items():
            if key!='exact_capacity' and not math.isclose(t[key],value,rel_tol=0,abs_tol=1e-9):errors.append(key)
        if not math.isclose(got.entries[0].score-base.entries[0].score,want['part'],rel_tol=0,abs_tol=1e-9):errors.append('score_delta')
        rows.append({'name':name,'expected':want,'actual':t,'errors':errors,'view':v.candidate_view()})
    code=source.read_text();baseline=BASE.read_text();code=code.replace(code.splitlines()[0],baseline.splitlines()[0],1)
    code=re.sub(r'^        support_[^\n]*\n','',code,flags=re.M)
    start=code.index('            if item.get("basis") == "direct_v2" and action.get("fact_kind") == "hand_progress":')
    end=code.index('            if table_rank == 1 and familiar:',start);code=code[:start]+code[end:]
    code=code.replace('            total += support_part\n            total = round(total, 6)\n','')
    code=re.sub(r'"shared_support_competition_v1": \{[^\n]*?\}, ', '',code)
    exact=code==baseline
    panel=b.read(task.OUT/'diagnostic-panel.json');diag=b.read(sub/'diagnostic-comparison.json');changes=[];active=0;capped=0
    for raw,row in zip(panel['rows'],diag['rows'],strict=True):
        for entry in row['results']['candidate']['entries']:
            t=entry['trace']['shared_support_competition_v1']
            if t['active']:active+=1;capped+=abs(t['net_units'])>=10
        if row['first_changed']:
            request=b.behavior.decision_request_from_json(raw['record']['request'])
            choices={k:b.behavior.evaluate_request(s,row['name'],request) for k,s in scorers.items()}
            changes.append({'name':row['name'],'choices':{k:r['action_key'] for k,r in choices.items()},
                            'all_scored':all(r['status']=='SCORED' for r in choices.values())})
    passed=all(not r['errors'] for r in rows) and exact and bool(changes) and all(r['all_scored'] and r['choices']['parent']!=r['choices']['candidate'] for r in changes)
    report={'status':'PASS' if passed else 'FAIL','source_sha256':b.digest(source.read_bytes()),
            'runner_sha256':b.digest(b.Path(__file__).read_bytes()),'arithmetic':rows,'ablation_restores_baseline_bytes':exact,
            'production_choices':changes,'active_entries':active,'entries_at_or_beyond_cap':capped,
            'scope':'机会边人工列举，不复制作者枚举实现；合成合同和已曝光窗口均不作新强度样本',
            'author_evidence_corrections':['作者两副不同残余手牌的分数对比不是同窗改选；本报告另用生产choose核验。',
                '循环次数不是执行器操作数，另作实际计费压力检查；该式不声称精确分解或概率。']}
    output=sub/'independent-arithmetic-and-scope.json';assert not output.exists();b.write(output,report)
    print(report['status'],[(r['name'],r['errors']) for r in rows],{'ablation_exact':exact,'production_changes':len(changes),'active':active,'capped':capped},flush=True)
    assert passed

if __name__=='__main__':main()
