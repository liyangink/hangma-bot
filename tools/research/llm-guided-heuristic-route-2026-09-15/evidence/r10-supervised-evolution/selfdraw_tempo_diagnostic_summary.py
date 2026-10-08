"""既有112请求的改选来源分类；只解释行为，不增加效果样本。"""

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
import asyncio
from collections import Counter

import selfdraw_tempo_checks as c


def run():
    """重建冻结V2的公开计划分项，区分平分与跨原排序，不读取终局效用。"""
    b=c.b;sub=c.batch.OUT/c.batch.NAME
    output=sub/'diagnostic-mechanisms.json'
    if output.exists():raise ValueError('不覆盖已完成诊断')
    recorded=b.read(sub/'diagnostic-comparison.json')
    assert recorded['panel_sha256']==b.digest(c.PANEL.read_bytes())
    requests={r['name']:r for r in b.read(c.PANEL)['rows']}
    policy=c.ComparableHeuristicPolicyV2(monotonic=lambda:0.0)
    by_origin={}; transitions=Counter(); selected_sources=Counter(); rows=[]
    for row in recorded['rows']:
        request=b.behavior.decision_request_from_json(requests[row['name']]['record']['request'])
        plan=asyncio.run(policy.choose(request,c.DecisionBudget(1.0,2.0,3.0)))
        assert [x.action_key for x in plan.candidates]==row['v2_order']
        totals={x.action_key:x.total_score for x in plan.candidates}
        new=row['candidate']['ordered_actions'][0];old=row['v2_order'][0]
        c_scores=row['candidate']['scores']
        stats=by_origin.setdefault(row['origin'],{'inputs':0,'changed':0,'v2_ties':0,'candidate_ties':0})
        stats['inputs']+=1
        if new==old:continue
        stats['changed']+=1
        v2_tie=abs(totals[new]-totals[old])<1e-9
        candidate_tie=abs(c_scores[new]-c_scores[old])<1e-9
        stats['v2_ties']+=int(v2_tie);stats['candidate_ties']+=int(candidate_tie)
        transitions[old.split(':')[0]+' -> '+new.split(':')[0]]+=1
        selected_sources[row['trace'][new]['source']]+=1
        rows.append({'name':row['name'],'origin':row['origin'],'v2_choice':old,'candidate_choice':new,
            'v2_tie':v2_tie,'candidate_tie':candidate_tie,'v2_scores':{old:totals[old],new:totals[new]},
            'candidate_scores':{old:c_scores[old],new:c_scores[new]},
            'candidate_trace':{old:row['trace'][old],new:row['trace'][new]}})
    report={'schema':'selfdraw-tempo-diagnostic-summary/1','source_sha256':recorded['source_sha256'],
        'panel_sha256':recorded['panel_sha256'],'by_origin':by_origin,'transitions':dict(transitions),
        'selected_sources':dict(selected_sources),'changed_rows':rows,
        'summary':{'inputs':112,'changed':len(rows),'v2_ties':sum(r['v2_tie'] for r in rows),
                   'candidate_ties':sum(r['candidate_tie'] for r in rows)},
        'scope':'固定曝光请求；包含合成和故障输入，分层保留；不读取终局，不能以改选多或跨排序断言提分或因果',
        'new_model_calls':0,'new_effect_tables':0,'release_eligible':False}
    b.write(output,report)
    print(report['summary']);print(report['by_origin']);print(report['transitions'])


if __name__=='__main__':run()
