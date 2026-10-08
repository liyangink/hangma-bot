"""一次性对账：恢复被生成摄入错误覆盖的已终结失败尝试费用，保留更正凭证。"""

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
from pathlib import Path
import json
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import pilot

def main():
    """仅按本次第一条连接失败会话的显式用量校正 superseded 行，不更改状态或候选。"""
    s=pilot.state(); idir=Path(s['iter_dir']); receipt=idir/'transport-settlement-correction.json'
    if receipt.exists():raise SystemExit('已对账，不重复更正')
    old=json.loads((idir/'author-call/usage.json').read_text())
    auth=json.loads((pilot.PILOT/'authorization.json').read_text())
    ledger=pilot.search._av_ledger_for_run(pilot.RUN,auth)
    changes=[]
    for account,key,suffix in [('tokens_input','inputTokens','in'),('tokens_output','outputTokens','out')]:
        step='iter'+str(s['iteration_no'])+':gen-tokens-'+suffix
        rows=[r for r in ledger.reservations if r['step_id']==step and r.get('superseded')]
        if len(rows)!=1:raise SystemExit('旧尝试不唯一')
        row=rows[0]; actual=old['usage'][key]
        if actual!=0:raise SystemExit('本对账只处理已核验的零用量连接失败')
        changes.append({'reservation_id':row['reservation_id'],'before':row['charged'],'after':actual})
        ledger.settle(row,actual=actual,note='独立对账更正：superseded 连接失败不属于本次成功调用；来源 author-call/usage.json')
    pilot.write(receipt,{'reason':'_step_generate 以 step_id 结算时误包含 superseded 历史行',
        'source_session_sha256':old['session_sha256'],'changes':changes,
        'spent_after':ledger.account_summary(),'scope':'只纠正费用，不改候选、状态或门禁'})
    print(json.dumps({'changes':changes,'spent':ledger.account_summary()},ensure_ascii=False))
if __name__=='__main__':main()
