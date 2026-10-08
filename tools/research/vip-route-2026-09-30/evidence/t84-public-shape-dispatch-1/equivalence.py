"""当前公式56个冻结公开窗的真实重评；输入、分值、解释和操作计数均须严格不变。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t84-public-shape-dispatch-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE=Path(__file__).resolve().parent
AUTHOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')


def raw(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def save(path,value):
    with path.open('xb') as stream:
        stream.write(raw(value)+b'\n')


def main(compiled_identity):
    out=_project_file(_PROJECT_ROOT, HERE/'equivalence-56');out.mkdir(exist_ok=False)
    spec=importlib.util.spec_from_file_location('t75_public_cases_only',_project_file(_PROJECT_ROOT, AUTHOR/'root_load_and_probe.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.REPO_ROOT=HERE.parents[3]
    cases,files=module.public_cases()
    reference=json.loads((_project_file(_PROJECT_ROOT, HERE.parent/'t80-witness-capacity-failure-diagnostic-1/r3-equivalence-56/CLOSURE.json')).read_text())
    batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, AUTHOR/'S01-generation.batch.json'))
    source=(_project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output/candidate.py')).read_text()
    identity=batch.identity(source)
    assert identity['params']==reference['runtime_identity']['params']
    assert identity['source_sha256']==reference['runtime_identity']['source_sha256']
    save(out/'START.json',{'schema':'t84-public-shape-equivalence-plan/1','python_parent_runtime_identity':identity,'compiled_execution_identity':compiled_identity,
         'reference_identity':reference['runtime_identity'],'actual_rules_projections_scores_budget':56,
         'permitted_input_delta':'none',
         'new_models_worlds_tables':0,'online_admission':False})
    executor=ActionValueExecutor(source,max_operations=batch.max_operations,
                               max_local_collection_size=batch.projection_limits.max_nodes)
    results=[];rules_calls=projections=scores_calls=0
    with gzip.open(out/'ACTUAL-INPUTS.jsonl.gz','xb') as archive, gzip.open(_project_file(_PROJECT_ROOT, HERE.parent/'t80-witness-capacity-failure-diagnostic-1/r3-equivalence-56/ACTUAL-INPUTS.jsonl.gz'),'rt') as old_archive:
        for case,old_result in zip(cases,reference['rows']):
            row={'label':case['label'],'status':'not_scored'}
            begin=time.monotonic()
            try:
                old_capture=json.loads(next(old_archive))
                assert old_capture['label']==case['label']==old_result['label']
                assert hashlib.sha256(raw(old_capture['view'])).hexdigest()==old_result['input_sha256']
                observation=observation_from_json(case['observation']);key=window_key_from_json(case['window_key'])
                rules_calls+=1
                rules=HangmaRules(batch.rule_config).analyze(observation,route_limits=batch.route_limits)
                request=DecisionRequest(observation,CompetitionContext('t80-equivalence',None,None,None,None,(),0),rules,case['label'],key.trigger_seq,key,())
                projections+=1
                view=build_vip_route_scoring_view(request,batch.rule_config,limits=batch.projection_limits)
                dto=view.candidate_view();digest=hashlib.sha256(raw(dto)).hexdigest()
                archive.write(raw({'label':case['label'],'view_sha256':digest,'view':dto})+b'\n');archive.flush()
                old_dto=old_capture['view']
                old_count=old_dto['workload']['waiting_draw_witness_count']
                new_count=dto['workload']['waiting_draw_witness_count']
                assert new_count==old_count and raw(dto)==raw(old_dto),'unexpected input facts changed'
                scores_calls+=1
                scored=executor.score_vip_route(view)
                entries=[{'action_key':e.action_key,'score':e.score,'trace':e.trace} for e in scored.entries]
                assert scored.status=='SCORED'
                assert raw(sorted(entries,key=lambda r:r['action_key']))==raw(sorted(old_result['scores'],key=lambda r:r['action_key']))
                assert executor.last_operation_count==old_result['operations']
                assert {e.action_key for e in scored.entries}=={a.action_key for a in view.actions}
                row.update(status='SCORED',old_queries=old_count,new_queries=new_count,
                           operations=executor.last_operation_count,scores=entries,
                           input_sha256=digest,all_input_facts_exact=True,
                           all_scores_traces_operations_exact=True)
            except Exception as exc:
                row.update(status='FAILED',error=type(exc).__name__+': '+str(exc))
            row['elapsed_seconds']=time.monotonic()-begin;results.append(row)
            print({k:row.get(k) for k in ('label','status','old_queries','new_queries','error')},flush=True)
    inputs={}
    with gzip.open(out/'ACTUAL-INPUTS.jsonl.gz','rt') as archive:
        for line in archive:
            item=json.loads(line)
            assert hashlib.sha256(raw(item['view'])).hexdigest()==item['view_sha256']
            assert item['label'] not in inputs;inputs[item['label']]=item['view_sha256']
    stable=batch.identity(source)==identity
    complete=stable and rules_calls==projections==scores_calls==len(inputs)==len(results)==56 and all(r['status']=='SCORED' for r in results)
    save(out/'CLOSURE.json',{'schema':'t84-public-shape-equivalence/1','complete':complete,
         'python_parent_runtime_identity':identity,'compiled_execution_identity':compiled_identity,'source_stable':stable,'actual_rule_calls':rules_calls,
         'actual_projection_calls':projections,'actual_score_calls':scores_calls,
         'actual_full_inputs_verified':len(inputs),'rows':results,'new_models_worlds_tables':0,
         'full_legal_scores_traces_operations_exact':complete,'online_admission':False})
    print({'complete':complete,'actual_scores':scores_calls,'actual_full_inputs':len(inputs)})
    if not complete: raise SystemExit(1)


if __name__=='__main__':
    from compiled_overlay import installed
    with installed() as compiled_identity:
        main(compiled_identity)
