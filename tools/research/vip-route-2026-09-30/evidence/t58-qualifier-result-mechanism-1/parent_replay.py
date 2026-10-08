"""十六个已抽真实窗口复现固定父代，保存实际输入后完整评分。

旧记录只作同源码全动作分数／解释的对账，不当最佳动作标签。只调用
原合法规则和公开策略，不读取完整世界、不推进桌赛、不调用模型。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t58-qualifier-result-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from hangma_bot.application.deadline import BudgetPolicy, SystemClock
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy

HERE = Path(__file__).resolve().parent
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t51-t48-same-formula-efficiency-author-1')
T52 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t52-fixed-qualifier-unexposed-long-1')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


async def main():
    case_path = _project_file(_PROJECT_ROOT, HERE / 'NATURAL-PUBLIC-CASES.json')
    cases = json.loads(case_path.read_text())['cases']
    batch_path = _project_file(_PROJECT_ROOT, PARENT / 'S01-research.batch.json')
    batch = VipEohBatch.read(batch_path)
    source_path = _project_file(_PROJECT_ROOT, PARENT / 'S01-research-capacity/candidate.py')
    source = source_path.read_text()
    identity = batch.identity(source)
    campaign = json.loads((_project_file(_PROJECT_ROOT, T52 / 'CAMPAIGN-CLOSURE.json')).read_text())
    assert campaign['whole_batch_valid'] and identity == campaign['candidate_identity']
    capture_path = _project_file(_PROJECT_ROOT, HERE.parent / 't55-real-choose-deadline-diagnostic-1/probe_v2.py')
    spec = importlib.util.spec_from_file_location('t55_capture_for_t58', capture_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    frozen = {str(path):sha(path) for path in [Path(__file__), case_path, batch_path,
        source_path, capture_path, _project_file(_PROJECT_ROOT, T52 / 'CAMPAIGN-CLOSURE.json')]}
    save('PARENT-REPLAY-PLAN.json', {'schema':'t58-fixed-parent-natural-replay/1',
        'candidate_identity':identity,'frozen_files':frozen,'actual_candidate_score_limit':16,
        'cases': [{'label':f'natural:{i:02}', 'root_id':r['root_id'], 'category':r['category']} for i,r in enumerate(cases)],
        'new_model_world_table_calls':0,'scope':'same known public states and parent, full scores/traces; no capability or release gold label'})
    policy = RouteVipHeuristicPolicy(batch.rule_config, source=source,
        max_operations=batch.max_operations, projection_limits=batch.projection_limits)
    clock, budgets = SystemClock(), BudgetPolicy()
    rows = []
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'PARENT-ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz'),'xb') as archive:
        capture = module.CaptureExecutor(policy.executor,archive)
        policy.executor = capture
        for index,raw in enumerate(cases):
            label = f'natural:{index:02}'
            capture.label,capture.last_capture,capture.capture_seconds = label,None,0.0
            row = {'label':label,'root_id':raw['root_id'],'category':raw['category'],'status':'unscored'}
            try:
                observation = observation_from_json(raw['observation'])
                key = window_key_from_json(raw['window_key'])
                begin = clock.now()
                span = 1.0 if observation.phase.startswith('response_') else 3.0
                rules = HangmaRules(batch.rule_config).analyze(observation,route_limits=batch.route_limits)
                request = DecisionRequest(observation,
                    CompetitionContext('T58-parent-same-public-diagnostic',None,None,None,None,(),0),
                    rules,raw['decision_id'],key.trigger_seq,key,())
                result = await policy.choose(request,budgets.build(begin,span))
                elapsed = clock.now()-begin
                actual = {c.action_key:{'score':c.total_score,'trace':c.score_trace['detail']} for c in result.candidates}
                expected = {c['action_key']:{'score':c['score'],'trace':c['trace']['detail']} for c in raw['actual_recorded_candidates']}
                assert canonical(actual) == canonical(expected)
                assert result.candidates[0].action_key == raw['selected_action_key']
                row.update(status='SCORED',all_legal_scores_traces_and_choice_equal=True,
                    full_scores=actual,actual_input_sha256=capture.last_capture,
                    operations=capture.last_operation_count,selected_action_key=result.candidates[0].action_key,
                    elapsed_including_capture_seconds=elapsed,capture_seconds=capture.capture_seconds)
            except Exception as exc:
                row.update(status='failed',error=type(exc).__name__+': '+str(exc))
            rows.append(row)
            print({'label':label,'status':row['status'],'error':row.get('error')},flush=True)
    seen = set()
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'PARENT-ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz'),'rt') as stream:
        for line in stream:
            item = json.loads(line)
            assert item['label'] not in seen
            seen.add(item['label'])
            assert hashlib.sha256(canonical(item['candidate_view'])).hexdigest() == item['view_sha256']
    stable = identity == batch.identity(source) and all(sha(Path(p))==digest for p,digest in frozen.items())
    complete = stable and len(rows)==len(seen)==16 and all(r['status']=='SCORED' for r in rows)
    save('PARENT-REPLAY-CLOSURE.json',{'schema':'t58-fixed-parent-natural-replay-closure/1',
        'complete':complete,'source_stable':stable,'candidate_identity':identity,
        'actual_score_calls':len(rows),'actual_full_inputs_readback':len(seen),
        'rows':rows,'normal_r18_fallbacks':0,'new_model_world_table_calls':0,
        'strength_or_online_admission':False})
    print({'complete':complete,'actual_score_calls':len(rows),'actual_full_inputs':len(seen)},flush=True)
    if not complete:
        raise SystemExit(1)


if __name__=='__main__':
    asyncio.run(main())
