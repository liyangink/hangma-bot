"""从已保存两桌请求核对未修复故障；不重跑模拟、不改变生产额度。"""

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
import gzip
import json
import strong_seed_batch as b
import support_runtime_repair_batch as repair
import verify_remaining_support_workload as original
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded

def main():
    """默认额度失败和扩额度公式参考分别记账，未修复窗口不能从故障计数消失。"""
    out=original.OUT;assert not (out/'summary.json').exists()
    frozen=b.read(out/'manifest.json')
    old=b.Path(b.read(repair.OUT/'manifest.json')['parent'])/'candidate.py'
    new=repair.OUT/repair.NAME/'run/iterations/iter-01/generation/candidate.py'
    assert b.digest(old.read_bytes())==frozen['old_sha256'] and b.digest(new.read_bytes())==frozen['new_sha256']
    reports=[]
    for mix,root,seat in frozen['cases']:
        label=f'{mix}-root{root}-seat{seat}'
        with gzip.open(out/(label+'-requests.json.gz'),'rt',encoding='utf-8') as handle:requests=json.load(handle)
        old_limit=ActionValueExecutor(old.read_text());old_ref=ActionValueExecutor(old.read_text(),max_operations=1000000)
        new_limit=ActionValueExecutor(new.read_text());new_ref=ActionValueExecutor(new.read_text(),max_operations=1000000)
        failures=[];mismatches=[];new_failures=0;max_new=0
        for i,record in enumerate(requests):
            view=b.behavior.build_scoring_view(b.behavior.decision_request_from_json(record['request']))
            old_error=new_error=None
            try:left=old_limit.score(view);old_count=old_limit.last_operation_count
            except WorkloadExceeded as exc:
                old_error=str(exc);left=old_ref.score(view);old_count=old_ref.last_operation_count
            try:right=new_limit.score(view);new_count=new_limit.last_operation_count
            except WorkloadExceeded as exc:
                new_error=str(exc);new_failures+=1;right=new_ref.score(view);new_count=new_ref.last_operation_count
            max_new=max(max_new,new_count)
            def plain(batch):return {'status':batch.status,'entries':{e.action_key:{'score':e.score,'trace':dict(e.trace)} for e in batch.entries}}
            equal=json.dumps(plain(left),sort_keys=True)==json.dumps(plain(right),sort_keys=True)
            if not equal:mismatches.append(i)
            if old_error or new_error:
                failures.append({'request_index':i,'old_default_error':old_error,'new_default_error':new_error,
                    'old_complete_operations':old_count,'new_complete_operations':new_count,'unlimited_outputs_equal':equal})
                b.write(out/(label+'-failure-'+str(i)+'.json'),record)
        report={'label':label,'requests':len(requests),'terminal_reproduced':b.read(out/(label+'-verification.json'))['terminal_reproduced'],
            'failures':failures,'remaining_repair_failures':new_failures,'output_mismatches':mismatches,
            'maximum_complete_repaired_operations':max_new}
        b.write(out/(label+'-verification-v2.json'),report);reports.append(report)
    assert sum(sum(r['old_default_error'] is not None for r in report['failures']) for report in reports)==3
    remaining=sum(r['remaining_repair_failures'] for r in reports)
    status='PASS' if remaining==0 and all(not r['output_mismatches'] for r in reports) else 'FAIL_RUNTIME_REPAIR_INCOMPLETE'
    summary={'status':status,'reports':reports,'full_tables':2,'additional_tables_this_analysis':0,'model_calls':0,
        'remaining_repair_failures':remaining,'source_sha256':frozen['new_sha256'],
        'supervisor_check_correction':'v1只在新源码成功后记录旧失败，遇到未修复窗口时误触故障总数断言；原产物保留，本次从gzip重判，不再次模拟。',
        'scope':'完整公式输出相同与默认额度可执行性分开；1000000仅离线参考，不准用于生产或效果评价。'}
    b.write(out/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
