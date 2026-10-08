"""监督试运行的显式分步入口；不自动重试、不修改模型正文、不绕过生产候选门禁。"""

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
import argparse
import datetime
import hashlib
import json
import sys
import time
HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
PILOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19/pilot')
RUN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19/pilot/run')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
for path in (_project_file(_PROJECT_ROOT, ROUTE/'tools'), _project_file(_PROJECT_ROOT, ADMISSION/'p25-headless'), _project_file(_PROJECT_ROOT, ADMISSION/'p25-dev-cards')):
    sys.path.insert(0,str(path))
import sitin_search as search
import dispatch_headless as dispatch
import criterion

def write(path, obj):
    """原子写监督证据，不修改既有历史目录。"""
    search.av_atomic_write_json(path, obj)

def authorization():
    """采用显式修订授权；旧文件保留，预算未扩大。"""
    path=_project_file(_PROJECT_ROOT, PILOT/'authorization-v2.json')
    return json.loads((path if path.exists() else _project_file(_PROJECT_ROOT, PILOT/'authorization.json')).read_text())

def state():
    """读取在案状态；没有状态不允许发模型调用。"""
    path = search.av_latest_state_path(RUN)
    if not path:
        raise SystemExit('尚未 emit 状态')
    return search.av_state_load(path)

def advance(stop):
    """调用真实编排器；终态必须显式指定 new 才能创建新提案。"""
    auth = authorization()
    result = search.run_av_evolution(RUN, authorization=auth,
        natural_roots=1,natural_seats=4,prefix_source='v2_behavior',
        panel_seed=2026091901,stop_after=stop)
    s=result.get('state') or {}
    print(json.dumps({k:result.get(k) for k in ('status','advanced','refused','terminal','waiting_for_reply')},ensure_ascii=False))
    print(json.dumps({'state':s.get('status'),'run_id':s.get('run_id'),'operator':(s.get('plan') or {}).get('operator')},ensure_ascii=False))

def call(retry=False):
    """单次禁工具 headless 调用；前后留痕，配置/提示/终止/用量均核验后才组装信封。"""
    s=state()
    if s['status']!='RESERVED' or s['generation'].get('phase')!='prompt_emitted':
        raise SystemExit('状态不允许调用')
    idir=Path(s['iter_dir']); call_dir=idir/'author-call'
    if retry:
        # 只恢复有完整终止证据的连接失败；不把不确定状态当作可重试。
        reports=list(idir.glob('author-call/ledger-first-*.json'))
        if len(reports)!=1 or (idir/'reply-envelope.json').exists():
            raise SystemExit('恢复证据不唯一或已有回复，不允许重发')
        old=json.loads(reports[0].read_text())['calls'][0]
        if old.get('exit_code')==0 or old.get('turn_end')!=1 or old.get('protocol_ok') is not True:
            raise SystemExit('非已确认终止的连接失败，需专项对账')
        call_dir=idir/'author-call-02'
    if call_dir.exists(): raise SystemExit('调用目录已存在：先对账，不自动重发')
    auth=authorization()
    prior=list(RUN.glob('iterations/*/author-call*/call-before.json'))
    if len(prior)>=auth['max_model_calls']:raise SystemExit('模型调用数已到上界')
    if prior:
        started=min(json.loads(p.read_text())['started_unix'] for p in prior)
        if time.time()-started>auth['wall_clock_limit_seconds']:raise SystemExit('本批次墙钟上界已到')
    pending=Path(s['generation']['pending_dir']); prompt=(pending/'prompt.txt').read_text()
    if hashlib.sha256(prompt.encode()).hexdigest()!=s['generation']['prompt_sha256']:
        raise SystemExit('提示词摘要不一致')
    limits=auth['generation_call_limits']
    # UTF-8 字节数作为正文 token 的保守估计，另给固定系统层保留空间；实际用量仍取会话。
    if len(prompt.encode())+16384>limits['tokens_input']:
        raise SystemExit('提示词字节上界加系统余量超过预留；不能调用')
    if retry:
        ledger=search._av_ledger_for_run(RUN,auth)
        observed=json.loads((idir/'author-call/usage.json').read_text()).get('usage') or {}
        for account,key,suffix in [('tokens_input','inputTokens','in'),('tokens_output','outputTokens','out')]:
            step='iter'+str(s['iteration_no'])+':gen-tokens-'+suffix
            row=next(r for r in ledger.reservations if r['step_id']==step and r['status']=='reserved')
            actual=observed.get(key)
            known=isinstance(actual,int) and not isinstance(actual,bool) and actual>=0
            ledger.settle(row,actual=actual if known else None,usage_unknown=not known,
                          note='已终止的连接失败；会话观测用量，不冒充供应商最终账单')
            ledger.supersede(step_id=step,account=account,reason='连接失败已对账，授权批次内第二次尝试')
        search._av_reserve_generation_tokens(ledger,iteration_no=s['iteration_no'],
            tokens_input=limits['tokens_input'],tokens_output=limits['tokens_output'])
        search.av_state_history_append(s,'RESERVED','连接失败已对账，显式重试；旧记录保留')
        search.av_state_save(search.av_latest_state_path(RUN),s)
    call_dir.mkdir()
    pdir=call_dir/'dispatch'/'I1'  # 只是调用交付 ID；实际算子由状态记录。
    pdir.mkdir(parents=True); (pdir/'prompt.txt').write_text(prompt)
    expected=json.loads((_project_file(_PROJECT_ROOT, PILOT/'manifest.json')).read_text())['expected_request_config']
    write(call_dir/'call-before.json',{'started_unix':time.time(),'prompt_sha256':s['generation']['prompt_sha256'],
          'expected_request_config':expected,'generation_reservation':s['reservations'],
          'operator':s['plan']['operator'],'route':'supervised_candidate_development'})
    # 只为本进程选择明确冻结的 GLM 身份；仍运行相同的严格单请求断言。
    dispatch._expected_request_config=lambda package:dict(expected)
    try:
        result=dispatch.dispatch(PILOT,['I1'],call_dir/'replies',call_dir/'plan.json',
            model_patch=str(_project_file(_PROJECT_ROOT, PILOT/'route.patch.yml')),prompt_dir=call_dir/'dispatch',timeout_s=900)
    except Exception as exc:
        write(call_dir/'interrupted.json',{'exception':type(exc).__name__,
              'action':'保留预留；从会话对账后再决定，不自动重试'})
        raise
    row=result['calls'][0]
    usage=criterion.usage_of(row.get('run_id'))
    write(call_dir/'usage.json',usage)
    if row.get('exit_code')!=0 or row.get('protocol_ok') is not True:
        raise SystemExit('通道失败：保留调用成本，不摄入，见 author-call')
    u=usage.get('usage') or {}
    if not all(isinstance(u.get(k),int) and not isinstance(u[k],bool) and u[k]>=0
               for k in ('inputTokens','outputTokens')):
        raise SystemExit('用量不完整：先对账，不默认为零')
    reply=(call_dir/'replies/I1.txt').read_text()
    envelope={'schema':'sitin-generation-reply/1','origin':'delegated_model_reply',
        'prompt_sha256':s['generation']['prompt_sha256'],'reply':reply,
        'provider':row['request_config']['provider'],'model':row['request_config']['model'],
        'observed_config':row['request_config'],'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'delegator':'Codex root supervised takeover via no-tool dsh headless',
        'usage':{'input_tokens':u['inputTokens'],'output_tokens':u['outputTokens']},
        'usage_source':'session_log','session_run_id':row['run_id'],
        'evidence':str(call_dir),'info_boundary':'tools_disabled_single_request'}
    write(idir/'reply-envelope.json',envelope)
    write(call_dir/'call-after.json',{'ingestable':True,'reply_sha256':hashlib.sha256(reply.encode()).hexdigest(),
          'usage':envelope['usage'],'limits_exceeded':u['inputTokens']>limits['tokens_input'] or u['outputTokens']>limits['tokens_output']})
    print(json.dumps({'envelope':str(idir/'reply-envelope.json'),'usage':envelope['usage']},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['new','call','retry','ingest','evaluate'])
    a=parser.parse_args()
    if (_project_file(_PROJECT_ROOT, PILOT/'batch-closure.json')).exists():
        raise SystemExit('本批次已封存；不得以剩余 token/桌赛余额继续调用。后续使用新批次。')
    if a.action in ('call','retry'):call(retry=a.action=='retry')
    elif a.action=='new':
        paths=list(RUN.glob('iterations/*/state.json'))
        if len(paths)>=3:raise SystemExit('已到三提案上限')
        if paths and state()['status'] not in search.AV_TERMINAL_STATES and state()['status']!='ITERATION_COMPLETE':
            raise SystemExit('在案提案未终结；不得另开')
        advance('RESERVED')
    else:
        s=state()
        if s['status'] in search.AV_TERMINAL_STATES or s['status']=='ITERATION_COMPLETE':
            raise SystemExit('终态不重复推进；开新提案需显式 new')
        advance('BEHAVIOR_CHECKED' if a.action=='ingest' else None)
