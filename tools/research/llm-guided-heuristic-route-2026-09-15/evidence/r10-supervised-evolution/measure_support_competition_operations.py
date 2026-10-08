"""以公开计费接口检查真实与规则生成输入的操作额度，不把循环数当操作数。"""

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
import strong_seed_batch as b
import support_competition_batch as task
from hangma_bot.policy.action_value_executor import ActionValueExecutor, MAX_COUNTED_OPERATIONS

def main():
    """固定147输入一次评分，记录计数与任何降级；不产生桌赛或模型费用。"""
    sub=task.OUT/task.NAME;source=sub/'run/iterations/iter-01/generation/candidate.py'
    assert b.read(sub/'source-review.json')['source_sha256']==b.digest(source.read_bytes())
    executor=ActionValueExecutor(source.read_text());rows=[];inputs=[]
    for filename in ('diagnostic-panel.json','rule-generated-stress.json'):
        panel=b.read(task.OUT/filename);assert panel['deps_digest']==b.search.av_gates().av_deps_digest()
        for row in panel['rows']:
            request=b.behavior.decision_request_from_json(row['record']['request'])
            inputs.append((filename,row['name'],b.behavior.build_scoring_view(request)))
    for origin,name,view in inputs:
        error=None;status=None
        try:status=executor.score(view).status
        except (ValueError,RuntimeError) as exc:error=type(exc).__name__+': '+str(exc)
        rows.append({'origin':origin,'name':name,'actions':len(view.actions),'status':status,
                     'operation_count':executor.last_operation_count,'error':error})
    passed=all(r['status']=='SCORED' and r['error'] is None and r['operation_count']<=MAX_COUNTED_OPERATIONS for r in rows)
    result={'status':'PASS' if passed else 'FAIL','source_sha256':b.digest(source.read_bytes()),
            'runner_sha256':b.digest(b.Path(__file__).read_bytes()),'rows':rows,'limit':MAX_COUNTED_OPERATIONS,
            'maximum_observed':max(r['operation_count'] for r in rows),'cases':len(rows),
            'scope':'固定样本的实测操作计数，不是全域最坏上界；超额仍由生产评分器整批降级。独立运行成本和真实截止时间待发布门禁。',
            'release_eligible':False}
    out=sub/'operation-meter-check.json';assert not out.exists();b.write(out,result)
    print(result['status'],result['cases'],'max',result['maximum_observed'],'limit',MAX_COUNTED_OPERATIONS,flush=True)
    assert passed

if __name__=='__main__':main()
