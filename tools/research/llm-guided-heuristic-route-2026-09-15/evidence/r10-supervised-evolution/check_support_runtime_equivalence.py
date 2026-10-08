"""纯成本修复验收：机械变换范围、三执行参考、真实故障及固定输入计费。"""

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
import builtins
import json
import re
import subprocess
import sys
import strong_seed_batch as b
import support_runtime_repair_batch as repair
import support_competition_batch as original
import support_competition_geometry as geometry
import support_competition_semantics as semantics
import support_competition_boundaries as boundaries
from hangma_bot.policy.action_value_executor import ALLOWED_BUILTINS, ActionValueExecutor, static_check

def sources():
    """旧源码是等价参考，新源码必须已静态准入并由监督审阅。"""
    sub=repair.OUT/repair.NAME
    old=b.Path(b.read(repair.OUT/'manifest.json')['parent'])/'candidate.py'
    new=sub/'run/iterations/iter-01/generation/candidate.py'
    return sub,old,new

def scope(old,new):
    """逆转五种机会的附加质量列表和需求聚合；其余字节应与原实现一致。"""
    text=new.read_text();base=old.read_text()
    text=text.replace(text.splitlines()[0],base.splitlines()[0],1)
    text=text.replace('                            support_quality_terms = []\n                            for natural_position in range(len(natural_codes)):\n                                support_quality_terms.append([])\n','')
    pattern=r'(?m)^([ ]*)opportunity_slots = (.+)\n\1opportunity_quality = (.+)\n\1opportunities.append\(\{"slots": opportunity_slots, "quality": opportunity_quality\}\)\n\1for support_slot in opportunity_slots:\n\1    support_quality_terms\[support_slot\].append\(opportunity_quality\)\n'
    text,count=re.subn(pattern,lambda m:m[1]+'opportunities.append({"slots": '+m[2]+', "quality": '+m[3]+'})\n',text)
    text=text.replace('                                for opportunity_quality in support_quality_terms[natural_position]:\n                                    demand += opportunity_quality\n',
                      '                                for opportunity in opportunities:\n                                    if natural_position in opportunity.get("slots"):\n                                        demand += opportunity.get("quality")\n')
    return count==5 and text==base

def inputs():
    """复用原先冻结142+5+53输入、18几何、11表示、12边界，再加真实失败窗。"""
    cases=[]
    for name in ('diagnostic-panel.json','rule-generated-stress.json','near-limit-rule-inputs.json'):
        panel=b.read(original.OUT/name)
        assert panel['deps_digest']==b.search.av_gates().av_deps_digest()
        for row in panel['rows']:
            request=b.behavior.decision_request_from_json(row['record']['request'])
            cases.append((name+':'+row['name'],b.behavior.build_scoring_view(request)))
    for label,module in [('geometry',geometry),('semantics',semantics),('boundary',boundaries)]:
        saved=b.read(module.PATH)['rows']
        for (name,view,*_),frozen in zip(module.cases(),saved,strict=True):
            assert name==frozen['name'] and b.behavior.digest(view.candidate_view())==b.behavior.digest(frozen['view'])
            cases.append((label+':'+name,view))
    request=b.behavior.decision_request_from_json(b.read(b.HERE/'support-workload-diagnostic-20260920/failing-request.json')['request'])
    cases.append(('actual_workload_failure',b.behavior.build_scoring_view(request)))
    assert len(cases)==242
    return cases

def normalized(value):
    """只统一传输形态，分数与完整trace不得使用近似相等。"""
    return {'status':value['status'],'entries':{e['action_key']:{'score':e['score'],'trace':e['trace']} for e in value.get('entries',[])}}

def worker():
    """白名单标准Python在限时子进程运行，原限额受限执行器仍是修复验收对象。"""
    sub,old,new=sources()
    assert b.read(sub/'source-review.json')['source_sha256']==b.digest(new.read_bytes())
    functions={}
    for name,path in [('old',old),('repair',new)]:
        code=path.read_text();static_check(code)
        namespace={'__builtins__':{k:getattr(builtins,k) for k in ALLOWED_BUILTINS}}
        exec(compile(code,'reviewed-runtime-repair-'+name,'exec'),namespace)
        functions[name]=namespace['score_actions']
    executor=ActionValueExecutor(new.read_text());rows=[]
    for name,view in inputs():
        plain=view.candidate_view()
        left=normalized(functions['old'](plain));middle=normalized(functions['repair'](plain))
        batch=executor.score(view)
        right={'status':batch.status,'entries':{e.action_key:{'score':e.score,'trace':dict(e.trace)} for e in batch.entries}}
        dumps=[json.dumps(v,sort_keys=True,ensure_ascii=False) for v in (left,middle,right)]
        equal=dumps[0]==dumps[1]==dumps[2]
        rows.append({'name':name,'equal':equal,'operations':executor.last_operation_count,
            'status':batch.status,'output_sha256':b.digest(dumps[2].encode()),
            'difference':None if equal else {'old':left,'repair_native':middle,'repair_restricted':right}})
    maximum=max(r['operations'] for r in rows)
    result={'status':'PASS' if all(r['equal'] and r['operations']<=100000 for r in rows) else 'FAIL',
        'cases':len(rows),'maximum_operations':maximum,'rows':rows,'source_sha256':b.digest(new.read_bytes()),
        'parent_sha256':b.digest(old.read_bytes()),'scope':'固定样本三方完整输出精确相等；配合源码变换论证，不是全域成本上界或强度证明。'}
    print(json.dumps(result,ensure_ascii=False))

def main():
    """先源码范围裁定，再限时差分；失败保留产物，不自动给第三次修复。"""
    sub,old,new=sources();output=sub/'runtime-equivalence.json';assert not output.exists()
    static_check(new.read_text());exact=scope(old,new);assert exact
    b.write(sub/'source-review.json',{'source_sha256':b.digest(new.read_bytes()),'reviewed_at_utc':b.search.utc_now(),
        'static_review':'PASS','scope_restores_original_bytes':True,'allow_reference_execution':True,
        'allow_development_evaluation':False,'scope_proof':'每种机会的slots互异；生成机会时按相同全局顺序向其牌位列表追加相同质量值，再按相同顺序累加。每个局部列表独立新建，其余源码机械还原原件。','release_eligible':False})
    done=subprocess.run([sys.executable,__file__,'--worker'],capture_output=True,text=True,timeout=30,check=True)
    result=json.loads(done.stdout);result['runner_sha256']=b.digest(b.Path(__file__).read_bytes());result['scope_restores_original_bytes']=exact
    b.write(output,result);assert result['status']=='PASS'
    failing=next(r for r in result['rows'] if r['name']=='actual_workload_failure')
    print(result['status'],result['cases'],'max operations',result['maximum_operations'],'failing input repaired',failing['operations'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');a=p.parse_args()
    worker() if a.worker else main()
