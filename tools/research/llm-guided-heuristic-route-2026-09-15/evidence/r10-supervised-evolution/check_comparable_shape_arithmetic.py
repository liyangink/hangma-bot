"""按显式残余牌位集合独立手算统一结构分；不复制作者分类循环。"""

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
import math
import re
import strong_seed_batch as b
import comparable_shape_batch as task
from check_discard_arithmetic import action, view
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicMeld
from hangma_bot.hangma.interface import UsefulTileFact
from hangma_bot.policy.action_value_seeds import ActionValueScorer
BASE=b.HERE/'v2-seed-terra-02/run/iterations/iter-01/generation/candidate.py'

def sample(hand,codes,live=('9w',),meld=False):
    """仅合成评分合同，标准向听/有效牌不作为该合成手牌的规则结论。"""
    actions=tuple(replace(action(c,16,1),standard_shanten_after=1,
        standard_useful_tiles=tuple(UsefulTileFact(t,4) for t in live)) for c in codes)
    v=view(actions,familiar=());obs=replace(v.visible_state,my_hand=tuple(Tile(c) for c in hand),drawn_tile=None)
    if meld:obs=replace(obs,melds=((PublicMeld(0,'chi',tuple(Tile(c) for c in ('1b','2b','3b')),3),),(),(),()))
    return replace(v,visible_state=obs)

def main():
    """检查分数与独立数量预期、实际生产改选、单机制机械消融。"""
    sub=task.OUT/task.NAME;state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    source=b.Path(state['iter_dir'])/'generation/candidate.py';parent=b.Path(b.read(task.OUT/'manifest.json')['parent'])/'candidate.py'
    scorers={k:ActionValueScorer(k,p.read_text()) for k,p in [('base',BASE),('parent',parent),('candidate',source)]}
    a=sample(('1w','4w','7w','1b','4b','7b','2t','5t','8t','发','发','东','东','白'),('1w','发','白'))
    z=sample(('2b','6t','6t','1w','1w','3w','3w','5b','5b','7b','7b','发','发','白'),('2b','6t'))
    gaps=sample(('1w','3w','5w','7w','9w','东','东','南','南','白','白'),('1w','东'),('2w','4w','6w','8w'),True)
    isolates=sample(('1w','5w','9w','1b','5b','9b','1t','5t','9t','东','南','西','北','白'),('1w','东'))
    adjacency=sample(('1w','2w','3w','3w','东','东','南','南','西','白','白'),('西','3w'),('9w',),True)
    absent=replace(a,actions=tuple(sorted(a.actions+(replace(action('9b',16,1),standard_shanten_after=1,standard_useful_tiles=a.actions[0].standard_useful_tiles),),key=lambda item:item.action_key)))
    # 每元组为(结构分,连接牌位,孤张牌位,对子牌位,相邻牌位,活隔张牌位)。按具体牌位手工计数。
    specs=[('honor_numeric_common_units',a,{'discard:1w':(-.8,4,8,4,0,0),'discard:发':(-1.6,2,10,2,0,0),'discard:白':(0,None,None,None,None,None)}),
        ('numeric_pair_and_positive_cap',z,{'discard:2b':(2.,12,0,12,0,0),'discard:6t':(1.6,10,2,10,0,0)}),
        ('meld_live_gap_and_honor_pair',gaps,{'discard:1w':(1.6,8,0,4,0,4),'discard:东':(1.2,7,1,2,0,5)}),
        ('negative_cap',isolates,{'discard:1w':(-2.,0,12,0,0,0),'discard:东':(-2.,0,12,0,0,0)}),
        ('pair_priority_no_double_count',adjacency,{'discard:西':(1.6,8,0,6,2,0),'discard:3w':(1.2,7,1,4,3,0)}),
        ('absent_discard_fallback',absent,{'discard:9b':(0,None,None,None,None,None)})]
    rows=[]
    for name,v,expected in specs:
        results={k:s.score(v) for k,s in scorers.items()};base={e.action_key:e.score for e in results['base'].entries};actual={};errors=[]
        if any(r.status!='SCORED' for r in results.values()):errors.append('status')
        for e in results['candidate'].entries:
            if e.action_key not in expected:continue
            t=e.trace['residual_v2'];values=(e.score-base[e.action_key],t['connected_slots'],t['orphan_slots'],t['pair_slots'],t['adjacent_slots'],t['live_gap_slots'])
            actual[e.action_key]=values;want=expected[e.action_key]
            if not math.isclose(values[0],want[0],rel_tol=0,abs_tol=1e-9) or values[1:]!=want[1:]:errors.append('arithmetic:'+e.action_key)
            if t['active']!=(want[1] is not None):errors.append('activation:'+e.action_key)
            if t['active'] and t['eligible_slots']!=t['connected_slots']+t['orphan_slots']:errors.append('partition:'+e.action_key)
        rows.append({'name':name,'expected':expected,'actual':actual,'errors':errors,'view':v.candidate_view()})
    # 删除新增计算块/初始化/一次加分及trace，剩余代码必须逐字节等于无结构基线（只归一模块说明）。
    code=source.read_text();base=BASE.read_text()
    code=code.replace(code.splitlines()[0],base.splitlines()[0],1)
    code=re.sub(r'^        residual_[^\n]*\n','',code,flags=re.M)
    start=code.index('            if item.get("basis") == "direct_v2" and action.get("fact_kind") == "hand_progress":')
    end=code.index('            if table_rank == 1 and familiar:',start)
    code=code[:start]+code[end:]
    code=code.replace('            total += residual_part\n            total = round(total, 6)\n','')
    code=re.sub(r'"residual_v2": \{[^\n]*?\}, ', '',code)
    exact=code==base
    inputs=b.read(task.OUT/'diagnostic-panel.json');diag=b.read(sub/'diagnostic-comparison.json');changes=[];non_discard=[];active=0;saturated=0
    for row,raw in zip(diag['rows'],inputs['rows'],strict=True):
        request=b.behavior.decision_request_from_json(raw['record']['request'])
        for e in row['results']['candidate']['entries']:
            t=e['trace']['residual_v2']
            if t['active']:
                active+=1;saturated+=abs(t['raw_units'])>=10
        if row['first_changed']:
            choices={k:b.behavior.evaluate_request(s,row['name'],request) for k,s in scorers.items()}
            changes.append({'origin':row['origin'],'name':row['name'],'choices':{k:r['action_key'] for k,r in choices.items()},'all_scored':all(r['status']=='SCORED' for r in choices.values())})
        old={e['action_key']:e for e in row['results']['parent']['entries']}
        for e in row['results']['candidate']['entries']:
            if e['action_key'].startswith('discard:') or e['trace'].get('unknown') is True:continue
            if e['score']!=old[e['action_key']]['score']:
                entries=row['results']['candidate']['entries'];best=max(entries,key=lambda x:x['score'])
                non_discard.append({'name':row['name'],'action_key':e['action_key'],'still_hu_first':best['action_key']=='hu'})
    passed=all(not r['errors'] for r in rows) and exact and any(r['choices']['parent']!=r['choices']['candidate'] for r in changes) and all(r['all_scored'] for r in changes) and all(r['action_key']=='hu' and r['still_hu_first'] for r in non_discard)
    report={'status':'PASS' if passed else 'FAIL','source_sha256':b.digest(source.read_bytes()),'runner_sha256':b.digest(b.Path(__file__).read_bytes()),'arithmetic':rows,'ablation_restores_baseline_bytes':exact,'production_choices':changes,'known_non_discard_changes':non_discard,'active_entries':active,'entries_at_or_beyond_cap':saturated,'scope':'合成手算与已曝光真实行为，不是新增强度样本；截顶比例是描述性诊断，不据此调参'}
    out=sub/'independent-arithmetic-and-scope.json';assert not out.exists();b.write(out,report)
    print(report['status'],[(r['name'],r['errors']) for r in rows],{'ablation_exact':exact,'production_change_cases':len(changes),'active_entries':active,'at_or_beyond_cap':saturated})

if __name__=='__main__':main()
