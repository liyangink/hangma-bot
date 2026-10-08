"""核旧日志解释包装，补五次尚未执行的候选评分；旧评分只读复用。

首次失败原件不改。此补批无模型、世界或桌赛；只建同身份公开视图。
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
from dataclasses import asdict
import gzip
import hashlib
import json
import math
import time

import accept_and_probe as base

HERE = base.HERE


def main():
    """先纯读验证117次原评分，再补五焦点评分并登记完整分母。"""
    prior = json.loads((_project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-CLOSURE.json')).read_text())
    feedback = json.loads((_project_file(_PROJECT_ROOT, HERE/'PUBLIC-CAUSAL-FEEDBACK.json')).read_text())
    targets = {r['label']:r for r in feedback['targets']}
    rows = {r['label']:r for r in prior['rows']}
    assert len(rows) == 61 and prior['source_stable'] and not prior['cleanup_errors']
    assert prior['costs']['actual_score_calls'] == 117
    assert prior['scoring_input_capture']['terminal']['terminal_valid']
    # 日志包装来自生产策略。只去已验证的这一层，不容忍任何分值或detail变化。
    envelope = {'candidate_kind':'vip_route_heuristic_v1',
        'trace_schema':'vip-route-score-trace/1','view_schema_version':'vip-route-scoring-view/3',
        'natural_preparation_semantics_version':'vip-natural-set-preparation/1',
        'normal_draw_hu_payment_semantics_version':'vip-normal-draw-hu-payment/1'}
    cached_views = {}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-VIEWS.jsonl.gz'),'rt') as stream:
        for line in stream:
            item = json.loads(line)
            raw = base.canonical(item['view'])
            assert len(raw) == item['json_bytes']
            assert hashlib.sha256(raw).hexdigest() == item['view_sha256']
            assert item['view_sha256'] not in cached_views
            cached_views[item['view_sha256']] = item['view']
    checked = 0
    for label, target in targets.items():
        row = rows[label]
        assert row['status'] == 'failed' and row['error'] == 'AssertionError: reference score or trace drift'
        assert set(row['scores']) == {'reference'}
        assert row['view_sha256'] == target['view_sha256']
        actual = {e['action_key']:e for e in row['scores']['reference']['entries']}
        expected = {e['action_key']:e for e in target['original_full_scores']}
        assert set(actual) == set(expected)
        for key, entry in actual.items():
            old = expected[key]
            assert {k:v for k,v in old['trace'].items() if k != 'detail'} == envelope
            assert base.canonical((entry['score'],entry['trace'])) == base.canonical((old['score'],old['trace']['detail']))
            checked += 1
        assert row['view_sha256'] in cached_views
    assert all(r['status'] == 'complete' for label,r in rows.items() if label not in targets)
    originals = [_project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-CLOSURE.json'),_project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-ROWS.jsonl'),
        _project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-VIEWS.jsonl.gz'),_project_file(_PROJECT_ROOT, HERE/'PUBLIC-CAUSAL-FEEDBACK.json'),
        _project_file(_PROJECT_ROOT, HERE/'ROOT-AUTHOR-REPLY-FIRST-SEAL.json'),_project_file(_PROJECT_ROOT, HERE/'candidate.py'),
        _project_file(_PROJECT_ROOT, HERE/'S01-model-output/generation.json'),_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'),
        _project_file(_PROJECT_ROOT, HERE/'accept_and_probe.py'),_project_file(_PROJECT_ROOT, HERE/'complete_missing_focus_probe.py')]
    pins = {str(p):base.pin(p) for p in originals}
    base.save('FOCUS-PROBE-CORRECTION-START.json',{'schema':'t97-focus-logging-envelope-correction/1',
        'cause':'production wraps executor trace in detail; first script compared different layers',
        'reference_score_and_detail_entries_exact':checked,'reference_scores_reused':5,
        'prior_actual_calls':117,'requested_new_candidate_calls':5,
        'requested_new_rules_and_views':5,'models_worlds_tables':0,'frozen_files':pins,
        'failure_originals_preserved':True,'reference_repeated_calls':0})
    batch = base.VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'))
    candidate = base.load_vip_parents([_project_file(_PROJECT_ROOT, HERE/'S01-model-output')],batch)[0]
    assert candidate['identity'] == prior['candidate_identity']
    executor = base.ActionValueExecutor(candidate['source'],max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes)
    source_manifest = candidate['identity']['source_manifest']
    costs = {'rules_analyze_attempts':0,'view_build_attempts':0,'actual_score_calls':0}
    output, failure, capture_costs = [], None, None
    start = time.monotonic()
    stream = (_project_file(_PROJECT_ROOT, HERE/'FOCUS-PROBE-VIEWS.jsonl.gz')).open('x+b')
    capture = base.ScoringInputCapture(stream,limits=base.ScoringInputCaptureLimits(67108864,2147483648,8))
    result_stream = (_project_file(_PROJECT_ROOT, HERE/'FOCUS-PROBE-ROWS.jsonl')).open('x')
    try:
        for label, target in targets.items():
            assert time.monotonic()-start < 180
            obs = base.observation_from_json(target['observation'])
            key = base.window_key_from_json(target['window_key'])
            costs['rules_analyze_attempts'] += 1
            analysis = base.HangmaRules(batch.rule_config).analyze(obs,route_limits=batch.route_limits)
            assert analysis.completeness.value == 'complete'
            request = base.DecisionRequest(obs,base.CompetitionContext('T97-public-probe',None,None,None,None,(),0),
                analysis,label,key.trigger_seq,key,())
            costs['view_build_attempts'] += 1
            view = base.build_vip_route_scoring_view(request,batch.rule_config,limits=batch.projection_limits)
            dto = view.candidate_view()
            assert base.canonical(dto) == base.canonical(cached_views[target['view_sha256']])
            legal = {a.action_key for a in view.actions}
            assert legal == {a.action_key for a in analysis.legal_candidates}
            receipt = capture.store(dto)
            assert receipt.saved_before_score and receipt.error is None
            costs['actual_score_calls'] += 1
            scored = executor.score_vip_route(view)
            entries = [{'action_key':e.action_key,'score':e.score,'trace':e.trace} for e in scored.entries]
            assert scored.status == 'SCORED'
            assert len(entries) == len(legal) and {e['action_key'] for e in entries} == legal
            assert all(type(e['score']) in (int,float) and math.isfinite(e['score']) for e in entries)
            assert base.canonical(view.candidate_view()) == base.canonical(dto)
            first = sorted(entries,key=lambda e:(-e['score'],e['action_key']))[0]['action_key']
            row = {'label':label,'status':'complete','view_sha256':target['view_sha256'],
                'scores':{'reference':rows[label]['scores']['reference'],
                    'candidate':{'first':first,'entries':entries,'operations':executor.last_operation_count,
                        'capture_receipt':asdict(receipt)}},
                'reference_source':'original first probe; validated exact score and production trace detail',
                'behavior_changed':first != rows[label]['scores']['reference']['first']}
            output.append(row)
            result_stream.write(base.canonical(row).decode()+'\n')
            result_stream.flush()
            print({'label':label,'reference':row['scores']['reference']['first'],'candidate':first,
                'behavior_changed':row['behavior_changed']},flush=True)
    except BaseException as exc:
        failure = type(exc).__name__+': '+str(exc)
        raise
    finally:
        result_stream.close()
        try:
            capture_costs = capture.finish()
        finally:
            stream.close()
        stable = all(base.pin(n) == h for n,h in pins.items()) and all(base.pin(base.REPO_ROOT/n) == h for n,h in source_manifest.items())
        complete = failure is None and len(output) == 5 and costs['actual_score_calls'] == 5 and stable and capture_costs['terminal']['terminal_valid']
        merged = [r for r in prior['rows'] if r['label'] not in targets]+output
        base.save('FOCUS-PROBE-CLOSURE.json',{'complete':complete,'source_stable':stable,'costs':costs,
            'scoring_input_capture':capture_costs,'error':failure,'rows':output,'models_worlds_tables':0,
            'elapsed_monotonic_seconds':time.monotonic()-start})
        base.save('PUBLIC-PROBE-COMBINED-CLOSURE.json',{'complete':complete and len(merged) == 61,
            'first_probe_failed_original_preserved':True,'first_actual_score_calls':117,
            'supplement_actual_candidate_calls':5,'total_actual_score_calls':122,
            'reference_actual_calls':61,'candidate_actual_calls':61,'reference_reused_not_repeated':5,
            'windows':61,'rows':merged,'changed_windows':sum(r.get('behavior_changed',False) for r in merged),
            'source_stable':stable,'candidate_identity':prior['candidate_identity'],
            'reference_raw_identity':prior['reference_raw_identity'],'normal_R18_fallbacks':0 if complete else None,
            'scope':'known public development windows; no independent strength or admission',
            'total_rule_analysis_calls':prior['costs']['rules_analyze_attempts']+costs['rules_analyze_attempts'],
            'total_view_build_calls':prior['costs']['view_build_attempts']+costs['view_build_attempts'],
            'new_models_worlds_tables':0})
        if not complete:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
