"""签收真实作者原答，再用共用公开输入核新根和固定T75；不生成世界。

原T75只通过当前批次的原码研究构造，不伪装兼容父代。新根按已有
i1/replay签收入口建立当前正式包；模型费用与本次读回装载分别记录。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t97-natural-preparation-joint-root-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict
import gzip
import hashlib
import importlib.util
import json
import math
import time

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_generate import (
    VipEohBatch, build_vip_eoh_prompt, load_vip_parents, parse_vip_eoh_reply, run_vip_eoh_generate,
)
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')


def canonical(value):
    """规范有限JSON用于同窗实际输入身份，不改评分或未知含义。"""
    return json.dumps(value,ensure_ascii=False,sort_keys=True,
                      separators=(',', ':'),allow_nan=False).encode()


def pin(path):
    """流式核验字节数及摘要，避免仅信旧文件名。"""
    h, size = hashlib.sha256(), 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1 << 20),b''):
            h.update(block)
            size += len(block)
    return {'sha256':h.hexdigest(),'bytes':size}


def save(name, value):
    """只创建新结果；失败原答和首次运行不会被后续覆盖。"""
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('xb') as stream:
        stream.write(canonical(value)+b'\n')


def public_cases():
    """仅调用旧公开材料读取函数，五个新目标仍只含焦点观察。"""
    path = _project_file(_PROJECT_ROOT, OLD/'root_load_and_probe.py')
    spec = importlib.util.spec_from_file_location('t75_public_material_reader',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old, inputs = module.public_cases()
    cases = [{'label':'old:'+r['label'],'observation':r['observation'],
              'window_key':r['window_key'],'scope':'historical public mechanical control, not strength'} for r in old]
    feedback = json.loads((_project_file(_PROJECT_ROOT, HERE/'PUBLIC-CAUSAL-FEEDBACK.json')).read_text())
    for row in feedback['targets']:
        cases.append({'label':row['label'],'observation':row['observation'],
                      'window_key':row['window_key'],'expected_current_reference_view_sha256':row['view_sha256'],
                      'expected_current_reference_scores':row['original_full_scores'],
                      'scope':'one exposed root044 causal target, not independent source'})
    assert len(cases) == 61 and len({r['label'] for r in cases}) == 61
    return cases, [path,*inputs,_project_file(_PROJECT_ROOT, HERE/'PUBLIC-CAUSAL-FEEDBACK.json')]


def main():
    prep = json.loads((_project_file(_PROJECT_ROOT, HERE/'AUTHOR-PREPARATION-CLOSED.json')).read_text())
    assert all(pin(n) == h for n,h in prep['frozen_files'].items())
    batch_file = _project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    delivered = {n:pin(_project_file(_PROJECT_ROOT, HERE/n)) for n in ('RAW-REPLY.txt','candidate.py','STATIC-CHECKS.json','AUTHOR-NOTE.md')}
    save('ROOT-AUTHOR-REPLY-FIRST-SEAL.json',{'schema':'t97-real-author-first-seal/1',
        'files':delivered,'requested_model':'gpt-6.1-sol','requested_effort':'max',
        'actual_author_delegations':1,'underlying_api_calls_and_tokens':None,
        'operator':'i1','formal_parents':[],'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'new_models_scores_rules_worlds_tables_in_seal':0,'admitted':False})
    raw = (_project_file(_PROJECT_ROOT, HERE/'RAW-REPLY.txt')).read_text()
    parsed = parse_vip_eoh_reply(raw,'i1',[])
    assert parsed['source_raw'].encode() == (_project_file(_PROJECT_ROOT, HERE/'candidate.py')).read_bytes()
    assert len(parsed['source'].encode()) <= 65536
    ActionValueExecutor(parsed['source'],max_operations=batch.max_operations,
                        max_local_collection_size=batch.projection_limits.max_nodes)
    packet, _ = build_vip_eoh_prompt(batch,'i1',[],(_project_file(_PROJECT_ROOT, HERE/'FROZEN-FEEDBACK.txt')).read_text())
    assert packet.sha256 == prep['prompt_sha256'] == pin(_project_file(_PROJECT_ROOT, HERE/'S01-prompt-emission/prompt.txt'))['sha256']
    save('REPLAY-ENVELOPE.json',{'schema':'sitin-generation-reply/1',
        'captured_at_utc':datetime.now(timezone.utc).isoformat(),'origin':'delegated_model_reply',
        'provider':'codex-collaboration','model':'unknown','finish_reason':'stop',
        'prompt_sha256':packet.sha256,'reply':raw,
        'delegator':'/root via /root/t97_sol_max_natural_joint_author',
        'note':'actual agent delivery; replay is zero new model calls; underlying usage unknown'})
    generated = run_vip_eoh_generate(batch_file=batch_file,out_dir=_project_file(_PROJECT_ROOT, HERE/'S01-model-output'),
        operator='i1',parent_paths=(),backend='replay',feedback=(_project_file(_PROJECT_ROOT, HERE/'FROZEN-FEEDBACK.txt')).read_text(),
        reply_file=_project_file(_PROJECT_ROOT, HERE/'REPLAY-ENVELOPE.json'))
    assert generated['status'] == 'loaded_not_admitted', generated['error']
    candidate = load_vip_parents([_project_file(_PROJECT_ROOT, HERE/'S01-model-output')],batch)[0]
    reference = (_project_file(_PROJECT_ROOT, HERE/'T75-REFERENCE-SOURCE.py')).read_text()
    ref_identity = batch.identity(reference)
    assert ref_identity == json.loads((_project_file(_PROJECT_ROOT, HERE/'REFERENCE-IDENTITY.json')).read_text())['current_research_raw_source_identity']
    cases, inputs = public_cases()
    source_manifest = generated['framework']['generation_source_manifest']
    frozen = {str(p):pin(p) for p in [Path(__file__),*inputs,_project_file(_PROJECT_ROOT, HERE/'FROZEN-FEEDBACK.txt'),
              _project_file(_PROJECT_ROOT, HERE/'S01-model-output/generation.json'),_project_file(_PROJECT_ROOT, HERE/'S01-model-output/candidate.py'),
              _project_file(_PROJECT_ROOT, HERE/'T75-REFERENCE-SOURCE.py'),batch_file]}
    save('PUBLIC-PROBE-START.json',{'schema':'t97-current-reference-paired-probe/1',
        'candidate_identity':candidate['identity'],'reference_raw_identity':ref_identity,
        'requested_windows':61,'max_actual_score_calls':122,'wall_seconds':1200,
        'capture':{'max_view_json_bytes':67108864,'max_total_json_bytes':2147483648,'max_unique_views':128},
        'source_files':frozen,'source_manifest':source_manifest,'cases':cases,
        'new_models_or_worlds_or_tables':0,'normal_r18_fallback_allowed':False,
        'old_absolute_scores_not_used_as_current_reference':True,
        'scope':'all exposed development, mechanical and behavior only; no strength or probability'})
    executors = {'reference':ActionValueExecutor(reference,max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes),
        'candidate':ActionValueExecutor(candidate['source'],max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes)}
    begun = time.monotonic()
    costs = {'rules_analyze_attempts':0,'view_build_attempts':0,'actual_score_calls':0}
    rows, primary, cleanup = [], None, []
    stream = (_project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-VIEWS.jsonl.gz')).open('x+b')
    capture = ScoringInputCapture(stream,limits=ScoringInputCaptureLimits(67108864,2147483648,128))
    results = (_project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-ROWS.jsonl')).open('x')
    capture_costs = None
    try:
        for case in cases:
            assert time.monotonic()-begun <= 1200, 'monotonic wall budget exceeded'
            row = {'label':case['label'],'status':'unscored','scores':{}}
            try:
                obs = observation_from_json(case['observation'])
                key = window_key_from_json(case['window_key'])
                costs['rules_analyze_attempts'] += 1
                analysis = HangmaRules(batch.rule_config).analyze(obs,route_limits=batch.route_limits)
                assert analysis.completeness.value == 'complete'
                request = DecisionRequest(obs,CompetitionContext('T97-public-probe',None,None,None,None,(),0),
                    analysis,case['label'],key.trigger_seq,key,())
                costs['view_build_attempts'] += 1
                view = build_vip_route_scoring_view(request,batch.rule_config,limits=batch.projection_limits)
                dto = view.candidate_view()
                digest = hashlib.sha256(canonical(dto)).hexdigest()
                row['view_sha256'] = digest
                legal = {a.action_key for a in view.actions}
                assert legal == {a.action_key for a in analysis.legal_candidates}
                if 'expected_current_reference_view_sha256' in case:
                    assert digest == case['expected_current_reference_view_sha256']
                for name, executor in executors.items():
                    receipt = capture.store(dto)
                    assert receipt.saved_before_score and receipt.error is None
                    costs['actual_score_calls'] += 1
                    scored = executor.score_vip_route(view)
                    entries = [{'action_key':e.action_key,'score':e.score,'trace':e.trace} for e in scored.entries]
                    assert scored.status == 'SCORED'
                    assert len(entries) == len(legal) and {e['action_key'] for e in entries} == legal
                    assert all(type(e['score']) in (int,float) and math.isfinite(e['score']) for e in entries)
                    assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                    first = sorted(entries,key=lambda e:(-e['score'],e['action_key']))[0]['action_key']
                    row['scores'][name] = {'first':first,'entries':entries,
                        'operations':executor.last_operation_count,'capture_receipt':asdict(receipt)}
                    if name == 'reference' and 'expected_current_reference_scores' in case:
                        expected = {e['action_key']:(e['score'],e['trace']) for e in case['expected_current_reference_scores']}
                        actual = {e['action_key']:(e['score'],e['trace']) for e in entries}
                        assert canonical(actual) == canonical(expected), 'reference score or trace drift'
                row['status'] = 'complete'
                row['behavior_changed'] = row['scores']['candidate']['first'] != row['scores']['reference']['first']
            except Exception as exc:
                row.update(status='failed',error=type(exc).__name__+': '+str(exc))
            rows.append(row)
            results.write(canonical(row).decode()+'\n')
            results.flush()
            print({'label':row['label'],'status':row['status'],
                   'reference':row['scores'].get('reference',{}).get('first'),
                   'candidate':row['scores'].get('candidate',{}).get('first'),
                   'changed':row.get('behavior_changed'),'error':row.get('error')},flush=True)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            results.close()
            capture_costs = capture.finish()
        except BaseException as exc:
            cleanup.append(type(exc).__name__+': '+str(exc))
        finally:
            stream.close()
        stable = (all(pin(n) == h for n,h in frozen.items()) and
                  all(pin(n) == h for n,h in prep['frozen_files'].items()) and
                  all(pin(_project_file(_PROJECT_ROOT, HERE/n)) == h for n,h in delivered.items()) and
                  all(pin(_project_file(_PROJECT_ROOT, REPO_ROOT/n)) == h for n,h in source_manifest.items()) and
                  batch.identity(candidate['source']) == candidate['identity'] and
                  batch.identity(reference) == ref_identity)
        complete = (primary is None and not cleanup and stable and len(rows) == 61 and
            costs['actual_score_calls'] == 122 and all(r['status'] == 'complete' for r in rows) and
            capture_costs is not None and capture_costs['terminal']['terminal_valid'])
        save('PUBLIC-PROBE-CLOSURE.json',{'schema':'t97-paired-full-public-probe-closure/1',
            'complete':complete,'source_stable':stable,'costs':costs,'rows':rows,
            'scoring_input_capture':capture_costs,'cleanup_errors':cleanup,
            'error':None if primary is None else type(primary).__name__+': '+str(primary),
            'changed_windows':sum(r.get('behavior_changed',False) for r in rows),
            'candidate_identity':candidate['identity'],'reference_raw_identity':ref_identity,
            'new_model_world_table_calls':0,'normal_R18_fallbacks':0 if complete else None,
            'scope':'exposed development behavior only, no strength admission',
            'elapsed_monotonic_seconds':time.monotonic()-begun})
        if primary is None and not complete:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
