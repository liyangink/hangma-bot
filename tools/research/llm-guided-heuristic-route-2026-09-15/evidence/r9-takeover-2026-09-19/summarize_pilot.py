"""从在案状态、真实会话和共享账本生成简要摘要；复用答卷不算独立模型样本。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
RUN=_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19/pilot/run')

def main():
    """只读运行证据，输出调用分母、执行结果和成本；不推测未完成结果。"""
    states=[];calls=[]
    for path in sorted(RUN.glob('iterations/*/state.json')):
        d=json.loads(path.read_text()); idir=path.parent
        record={'attempt':idir.name,'run_id':d['run_id'],'status':d['status'],
            'operator':d['plan']['operator'],'candidate_id':d['identity'].get('candidate_id'),
            'reused_capture':(idir/'capture-reuse.json').exists(),
            'admission':d.get('admission'),'rejection':d.get('rejection'),
            'stop_reason':d.get('stop_reason')}
        statistics=idir/'summary/statistics.json'
        if statistics.exists():
            stats=json.loads(statistics.read_text()); panels={}
            for candidate in stats.get('by_candidate',{}).values():
                for name,block in candidate.get('panels',{}).items():
                    panels[name]={'mix':block.get('declared_mix'),
                        'by_opponent':{k:{f:v.get(f) for f in ('n_roots','mean_delta','interval_95','status')}
                            for k,v in block.get('panels',{}).items()}}
            record['panels']=panels
        states.append(record)
        for call_dir in sorted(idir.glob('author-call*')):
            reports=list(call_dir.glob('ledger-first-*.json'))
            for report in reports:
                data=json.loads(report.read_text())
                u=json.loads((call_dir/'usage.json').read_text()) if (call_dir/'usage.json').exists() else {}
                for row in data.get('calls',[]):
                    calls.append({k:row.get(k) for k in ('run_id','exit_code','elapsed_s','answer_chars','request_config','protocol_ok')} |
                                 {'operator':d['plan']['operator'],'usage':u.get('usage'),'evidence':str(call_dir)})
    ledger=json.loads((_project_file(_PROJECT_ROOT, RUN/'av-ledger.json')).read_text())
    out={'schema':'sitin-supervised-pilot-summary/1','states':states,'calls':calls,
        'calls_attempted':len(calls),'successful_author_calls':sum(c.get('exit_code')==0 for c in calls),
        'spent_including_active_reservations':ledger['spent'],
        'pending_reservations':[r for r in ledger['reservations'] if r['status']=='reserved'],
        'claim':'有监督研发试运行；非模型自主准入；非独立确认；复用答卷不计新增独立提案'}
    (_project_file(_PROJECT_ROOT, HERE/'pilot-summary.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'calls':out['calls_attempted'],'successful':out['successful_author_calls'],
        'states':[(s['attempt'],s['operator'],s['status']) for s in states],
        'spent':ledger['spent'],'pending':len(out['pending_reservations'])},ensure_ascii=False))
if __name__=='__main__':main()
