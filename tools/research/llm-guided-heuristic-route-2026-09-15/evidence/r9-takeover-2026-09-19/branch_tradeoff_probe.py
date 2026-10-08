"""M1 机制事后诊断：合成向听/支持权衡输入，不是正式准入题或真实可达牌局证明。"""

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
import sys,json
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(_project_file(_PROJECT_ROOT, HERE.parents[1]/'tools')))
import sitin_model_admission as a

def main():
    """保持输入合同，检验更改分支刻度能否改变排序；不修改冻结面板或原准入成绩。"""
    view=a._view([
        a._action_view(a.actions_mod.Discard(a.actions_mod.Tile('1w')),
                       branches=a._known_branches(0,0),progress='SAME'),
        a._action_view(a.actions_mod.Discard(a.actions_mod.Tile('2b')),
                       branches=a._known_branches(1,12),progress='SAME')])
    rows={}
    for label,it in [('parent','iter-02'),('child','iter-03')]:
        code=(_project_file(_PROJECT_ROOT, HERE/'pilot/run/iterations'/it/'generation/candidate.py')).read_text()
        batch=a.av_exec.ActionValueExecutor(code).score(view)
        scores={e.action_key:e.score for e in batch.entries}
        rows[label]={'status':batch.status,'scores':scores,'preferred':max(scores,key=scores.get)}
    out={'schema':'sitin-posthoc-mechanism-probe/1','source':'synthetic_contract_fixture',
        'real_world_reachability_verified':False,'usable_for_selection':False,
        'purpose':'冻结面板等行为不等于全域等价；只证明分支刻度有数学区分能力',
        'inputs':{'discard:1w':{'shanten':0,'support':0},'discard:2b':{'shanten':1,'support':12}},
        'results':rows,'preference_changed':rows['parent']['preferred']!=rows['child']['preferred']}
    (_project_file(_PROJECT_ROOT, HERE/'branch-tradeoff-probe.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
