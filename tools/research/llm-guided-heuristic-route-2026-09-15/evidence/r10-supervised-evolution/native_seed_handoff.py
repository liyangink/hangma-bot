"""原生Terra作者的人工监督交付接缝；不伪造用量或headless隔离证据。"""

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
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(_project_file(_PROJECT_ROOT, HERE.parents[1]/'tools')))
import sitin_search as search

BATCH=_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-seed-terra-01')


def advance(evaluate=False):
    """摄入已完成作者原答，或在root显式裁定后继续评价；失败保持原样。"""
    if (_project_file(_PROJECT_ROOT, BATCH/'batch-closure.json')).exists():
        raise SystemExit('批次已关闭')
    root=_project_file(_PROJECT_ROOT, BATCH/'run');path=search.av_latest_state_path(root)
    state=search.av_state_load(path)
    ok,why,_=search.av_verify_run_identity(state)
    if not ok:raise SystemExit(why)
    envelope=Path(state['iter_dir'])/'reply-envelope.json'
    if not evaluate and not envelope.exists():
        dispatch=json.loads((_project_file(_PROJECT_ROOT, BATCH/'author-dispatch.json')).read_text())
        completion=json.loads((_project_file(_PROJECT_ROOT, BATCH/'author-completion.json')).read_text())
        if completion.get('status')!='COMPLETED' or completion.get('agent_task')!=dispatch['agent_task']:
            raise SystemExit('缺少已完成作者任务证据')
        reply=(_project_file(_PROJECT_ROOT, BATCH/'author-reply.txt')).read_text()
        if hashlib.sha256(reply.encode()).hexdigest()!=completion['reply_sha256']:
            raise SystemExit('作者交付摘要改变')
        if dispatch['prompt_sha256']!=state['generation']['prompt_sha256']:
            raise SystemExit('作者题面身份不一致')
        search.av_atomic_write_json(envelope,{
            'schema':'sitin-generation-reply/1','origin':'delegated_model_reply',
            'prompt_sha256':dispatch['prompt_sha256'],'reply':reply,
            'provider':'codex-native','model':dispatch['requested_model'],
            'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'delegator':'root supervised native subagent',
            'usage':None,'usage_source':'unavailable_native_subagent',
            'evidence':str(_project_file(_PROJECT_ROOT, BATCH/'author-dispatch.json')),
            'info_boundary':dispatch['tool_boundary']})
    if evaluate:
        parity=json.loads((_project_file(_PROJECT_ROOT, BATCH/'parity-accepted.json')).read_text())
        source=(Path(state['iter_dir'])/'generation/candidate.py').read_bytes()
        if (not parity['strict_pass'] or not parity['execution_acceptable']
            or parity['source_sha256']!=hashlib.sha256(source).hexdigest()
            or parity.get('suite_sha256')!=hashlib.sha256((_project_file(_PROJECT_ROOT, HERE/'v2_seed_parity.py')).read_bytes()).hexdigest()):
            raise SystemExit('限定范围差分未通过，不执行效果评价')
    result=search.av_iteration_advance(path,root,
        authorization=json.loads((_project_file(_PROJECT_ROOT, BATCH/'authorization.json')).read_text()),
        stop_after=None if evaluate else 'BEHAVIOR_CHECKED')
    print(json.dumps({k:result.get(k) for k in ('status','advanced','terminal','refused','waiting_for_reply')},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['ingest','evaluate'])
    parser.add_argument('--batch',choices=['v2-seed-terra-01','v2-seed-terra-02'],default='v2-seed-terra-01')
    args=parser.parse_args()
    BATCH=_project_file(_PROJECT_ROOT, HERE/args.batch)
    advance(args.action=='evaluate')
