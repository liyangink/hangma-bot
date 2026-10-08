"""由已见高成本牌形确定性邻域生成规则事实，检查是否发生整批超额。"""

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
import strong_seed_batch as b
import support_competition_batch as task
import support_competition_rule_stress as stress
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
from hangma_bot.policy.action_value_seeds import ActionValueScorer

def main():
    """每种牌码替换一次，不按计费结果挑手牌；所有规则事实先冻结，再执行候选。"""
    path=task.OUT/'near-limit-rule-inputs.json';out=task.OUT/task.NAME/'near-limit-check.json'
    assert not path.exists() and not out.exists()
    original=stress.HANDS['dense_recombination'];hands={'fourteen_distinct_control':stress.HANDS['fourteen_distinct']}
    for old in dict.fromkeys(original):
        for new in ('1w','5w','7w','8w','9w','1b','白'):
            if old==new or original.count(new)>=4:continue
            items=list(original);items[items.index(old)]=new
            hands[old+'-to-'+new]=tuple(items)
    stress.HANDS=hands;stress.PATH=path;stress.freeze()
    frozen=b.read(path);frozen['actual_builder_sha256']=b.digest(b.Path(__file__).read_bytes())
    frozen['scope']='高成本牌形的确定性单张替换邻域，规则事实由HangmaRules生成；全体输入先冻结，不作效果样本。'
    b.write(path,frozen)
    source=task.OUT/task.NAME/'run/iterations/iter-01/generation/candidate.py'
    executor=ActionValueExecutor(source.read_text());scorer=ActionValueScorer('near-limit',source.read_text());rows=[]
    for raw in frozen['rows']:
        request=b.behavior.decision_request_from_json(raw['record']['request']);view=b.behavior.build_scoring_view(request)
        error=None;status=None
        try:status=executor.score(view).status
        except WorkloadExceeded as exc:error=type(exc).__name__+': '+str(exc)
        result=scorer.score(view)
        rows.append({'name':raw['name'],'status':status,'operation_count':executor.last_operation_count,
                     'error':error,'scorer_status':result.status,'actions':len(view.actions)})
    exceeded=[r for r in rows if r['error']]
    report={'status':'FAIL' if exceeded else 'PASS','rows':rows,'cases':len(rows),'exceeded':len(exceeded),
            'source_sha256':b.digest(source.read_bytes()),'inputs_sha256':b.digest(path.read_bytes()),
            'maximum_observed':max(r['operation_count'] for r in rows),'scope':frozen['scope']}
    b.write(out,report);print(report['status'],'cases',len(rows),'exceeded',len(exceeded),'max',report['maximum_observed'],flush=True)
    print(exceeded,flush=True)

if __name__=='__main__':main()
