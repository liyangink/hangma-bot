"""分开保留严格评分失败和真实操作可用性；只过例外必须逐窗重算，不豁免选择缺失。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t194-xuanwu-income-gap-1/wiring'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=_PROJECT_ROOT
OUT=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t194-xuanwu-income-gap-1/wiring/necessary-testroom-1')
sys.path[:0]=[str(_project_file(_PROJECT_ROOT, ROOT/'src')),str(ROOT)]


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    """读取自然闭房；3缺评分与零规划各自核合法选择，原严格false永不改写。"""
    from hangma_bot.adapters.official.dto import parse_state_response
    from hangma_bot.adapters.official.projector import observation,public_event
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.config import RuleConfig
    from hangma_bot.kernel.serialization import observation_from_json
    closed=load(_project_file(_PROJECT_ROOT, OUT/'CLOSED.json')); plan=load(_project_file(_PROJECT_ROOT, OUT/'PLAN.json')); session=_project_file(_PROJECT_ROOT, ROOT/plan['session'])
    assert closed['complete'] and closed['postgame_bundle_verified']
    rules=HangmaRules(RuleConfig('hangma-mvp-v10-public-counts',1,False))
    rows=[];pins={};zero_rows=[];unknown=[];game_paths=[]
    for audit in closed['audit']:
        run=session/'audit'/('slot-'+audit['slot'])/'runs'/audit['run_id']
        actual=load(run/'manifest.json')['payload']
        assert actual['base_score']==1 and actual['you_cai_bi_kao'] is False
        pins[str((run/'manifest.json').relative_to(session))]=digest(run/'manifest.json')
        for failed in audit['failed_plans']:
            path=session/failed['input']['source']; number=failed['input']['line']
            with path.open() as stream:
                record=next(json.loads(line) for i,line in enumerate(stream,1) if i==number)
            assert record['kind']=='decision_input' and record['context']==failed['context']
            request=record['payload']['request']; observed=observation_from_json(request['observation'])
            analysis=rules.analyze(observed)
            keys=[c.action_key for c in analysis.legal_candidates]
            rows.append({'context':record['context'],'source':failed['input']['source'],'line':number,
                'request_sha256':hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest(),
                'original_keys':failed['input']['legal'],'recomputed_keys':keys,
                'rules_completeness':analysis.completeness.value,'rules_issues':[i.code for i in analysis.issues]})
            pins[str(path.relative_to(session))]=digest(path)
        game_paths.extend(run.glob('participants/u_*/games/*.jsonl'))
    for path in sorted(game_paths):
        projections={}; selected=[]
        for number,line in enumerate(path.open(),1):
            rec=json.loads(line); payload=rec['payload']
            if rec['kind']=='authoritative_state' and 'seq' in payload and 'window' in payload:
                projections[json.dumps(payload['window'],sort_keys=True)]=(number,rec)
            if rec['kind']=='protocol_recovered' and any('零动作尝试' in reason for reason in payload.get('reasons',[])):
                key=json.dumps(payload['window'],sort_keys=True)
                projection=projections.get(key)
                row={'context':rec['context'],'source':str(path.relative_to(session)),'line':number,
                     'record':rec,'projection':projection,'raw_match':None}
                if projection is None:unknown.append({'source':row['source'],'line':number,'reason':'no exact window projection'})
                else:selected.append(row)
                zero_rows.append(row)
        pins[str(path.relative_to(session))]=digest(path)
        if not selected:continue
        raw_dir=path.parent.parent/'raw'; raw_paths=sorted(raw_dir.glob(path.stem+'.jsonl'))
        assert raw_paths,'缺原始state响应，不能按最近快照豁免零规划'
        for raw_path in raw_paths:
            pins[str(raw_path.relative_to(session))]=digest(raw_path)
            for number,line in enumerate(raw_path.open(),1):
                rec=json.loads(line); payload=rec['payload']
                if payload.get('source')!='state_response' or payload.get('http_status')!=200:continue
                document=json.loads(payload['raw']); snapshot=document.get('snapshot')
                if snapshot is None:continue
                for row in selected:
                    projected=row['projection'][1]; window=row['record']['payload']['window']
                    if (document.get('seq')==projected['payload']['seq'] and snapshot.get('phase')==window['phase']
                        and snapshot.get('round_no')==window['round_no'] and snapshot.get('seat')==window['seat']
                        and rec['monotonic_ns']<=projected['monotonic_ns']
                        and (row['raw_match'] is None or rec['monotonic_ns']>row['raw_match'][2]['monotonic_ns'])):
                        row['raw_match']=(str(raw_path.relative_to(session)),number,rec)
        for row in selected:
            if row['raw_match'] is None:
                unknown.append({'source':row['source'],'line':row['line'],'reason':'no exact consumed seq/phase/round/seat response'})
                continue
            response=parse_state_response(json.loads(row['raw_match'][2]['payload']['raw']))
            obs=observation(response.snapshot,tuple(public_event(e) for e in response.events),row['context']['game_id'])
            analysis=rules.analyze(obs)
            row['recomputed_keys']=[c.action_key for c in analysis.legal_candidates]
            row['rules_completeness']=analysis.completeness.value
            row['rules_issues']=[i.code for i in analysis.issues]
            row['raw_source'],row['raw_line']=row['raw_match'][:2]
    pass_only=all(row['original_keys']==row['recomputed_keys']==['pass'] and row['rules_completeness']=='complete' for row in rows)
    zero_pass_only=not unknown and all(row.get('recomputed_keys')==['pass'] and row.get('rules_completeness')=='complete' for row in zero_rows)
    error_ids={r['context']['decision_id'] for a in closed['audit'] for r in a['policy_errors']}
    warning_ids={r['context']['decision_id'] for r in rows}
    errors_covered=error_ids<=warning_ids and all('DEADLINE' in reason for a in closed['audit'] for r in a['policy_errors'] for reason in r['reasons'])
    audits_complete=all(not a['actual_audit_summary']['audit_degraded'] and a['http_started']==a['http_finished'] for a in closed['audit'])
    no_choice_score_gap=all(not a['inputs_without_plan_count'] and not a['full_plan_legal_key_mismatches'] for a in closed['audit'])
    faults_zero=all(t['decision_compute']['faults']==t['decision_compute']['restarts']==t['decision_compute']['policy_failures']==0 for t in closed['participant_terminals'])
    game_429=sum(a['http_categories'].get(k,{}).get('429',0) for a in closed['audit'] for k in ('state','action'))
    skips=load(_project_file(_PROJECT_ROOT, OUT/'SKIP-SEQUENCES-CLOSED.json'))
    usable=(pass_only and zero_pass_only and errors_covered and audits_complete and no_choice_score_gap and faults_zero
        and closed['postgame_audit_complete'] and not game_429 and not closed['official_discard_timeouts']
        and not closed['rule_origin_conflicts'] and all(closed['official_final_scores_match']) and skips['complete'] and skips['new_skip_count']>0)
    for row in zero_rows:
        row.pop('record');row.pop('projection');row.pop('raw_match')
    result={'complete':True,'operational_engineering_passed':usable,'original_strict_gate_kept':closed['engineering_gate_passed'],
        'strict_full_score_gate_kept':closed['strict_full_score_gate'],'pass_only_missing_full_scores':rows,
        'zero_planning_windows':zero_rows,'unknown_windows':unknown,'only_pass_exceptions_confirmed':pass_only and zero_pass_only,
        'actual_basic_rule_rechecks':len(rows)+len(zero_rows),'new_formula_worlds_tables_HTTP_calls':0,
        'unplanned_choice_or_input_gap':not no_choice_score_gap,'audit_complete':audits_complete,'worker_faults_zero':faults_zero,
        'game_HTTP_429':game_429,'official_discard_timeouts':len(closed['official_discard_timeouts']),
        'new_single_step_skips_officially_verified':skips['new_skip_count'],'pins':pins,
        'acceptance_basis':'T194 PLAN预先允许已证只有Pass的降级告警，不为零告警无限开房；不是修改原全评分false。'}
    with (_project_file(_PROJECT_ROOT, OUT/'OPERABILITY-CLOSED.json')).open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print({'operational_engineering_passed':usable,'missing_scores':len(rows),'zero_planning':len(zero_rows),'unknown':len(unknown),'strict_full_score':closed['strict_full_score_gate']})
    assert usable,'仍有实际选择缺失或原件未知，保留旧自由赛，不接E1'


if __name__=='__main__':main()
