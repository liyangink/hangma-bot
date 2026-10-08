"""第二联合提案八个新开发母根，四块每块2根、16实际完整桌。

复用T52全动作评分、完整输入及整桌门；全64桌为开发分母，
各块只输出进度/成本/故障，四块闭合前不读取中途积分。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t64-second-joint-fresh-qualifier-pilot-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
import argparse
import gzip
import hashlib
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.offline.evaluate import MatchExperiment, MatchSeedSpec, run_match_experiment
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_sources import REPO_ROOT, digest_of_file, source_manifest, write_code_snapshot
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from hangma_bot.offline.vip_evaluation import FrozenRoot, audit_vip_batch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditEngine, VipDevelopmentAuditPolicy
from hangma_bot.simulation import MatchSpec, SimulationChoice
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import WORLD_SCHEMA

HERE = Path(__file__).resolve().parent
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t62-earned-highfan-joint-revision-preparation-1')
CAUSAL = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t63-second-joint-same-start-1')
ENGINEERING = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1')
BLOCK = None


def sha(path):
    """流式摘要，避免捕获大文件全部装入内存。"""
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    """小收据先落盘后启动下一组；异常不抹掉费用。"""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'
    temporary = path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


def realized_ledger(rows, challenger_id):
    """只汇总已发生的官方规则积分；高番档位互斥，不给大牌另乘系数。"""
    totals = {arm:{kind:{'hands':0,'focal_score_sum':0} for kind in
                  ('own_lt4','own_4_to7','own_8_to15','own_ge16','opponent_hu','draw','unknown')}
              for arm in ('A','C')}
    for row in rows:
        arm = 'C' if row['match_id'].endswith(':'+challenger_id) else 'A'
        s = row.get('settlement')
        seat = row['focal_physical_seat']
        if row.get('evidence') != 'public_export_hand_settlement' or not s:
            kind, score = 'unknown', None
        else:
            delta = s.get('score_delta')
            score = delta[seat] if isinstance(delta, (list,tuple)) and len(delta)==4 else None
            if s.get('is_draw') is True: kind = 'draw'
            elif s.get('winner_seat') == seat and type(s.get('fan')) is int:
                fan = s['fan']
                kind = 'own_lt4' if fan<4 else 'own_4_to7' if fan<8 else 'own_8_to15' if fan<16 else 'own_ge16'
            elif type(s.get('winner_seat')) is int and s['winner_seat'] in range(4): kind = 'opponent_hu'
            else: kind = 'unknown'
        totals[arm][kind]['hands'] += 1
        if score is None:
            totals[arm][kind]['focal_score_sum'] = None
        elif totals[arm][kind]['focal_score_sum'] is not None:
            totals[arm][kind]['focal_score_sum'] += score
    return {'scope':'actual_completed_hand_settlement_only', 'mutually_exclusive_fan_bands':True,
            'counts_and_actual_net_by_arm':totals, 'unknown_not_zero':True}


async def main():
    plan_path = _project_file(_PROJECT_ROOT, HERE/f'BLOCK-{BLOCK:02d}-PLAN.json')
    plan = json.loads(plan_path.read_text())
    for name, expected in plan['prerequisite_sha256'].items():
        if sha(Path(name)) != expected:
            raise ValueError('确认前置证据漂移:'+name)
    package_pointer=_project_file(_PROJECT_ROOT, AUTHOR/'CURRENT-CANDIDATE-PACKAGE.json')
    package_record=json.loads(package_pointer.read_text())
    generation_file, package = _project_file(_PROJECT_ROOT, AUTHOR/package_record['relative_batch']), _project_file(_PROJECT_ROOT, AUTHOR/package_record['relative_package'])
    generation = VipEohBatch.read(generation_file)
    candidate = load_vip_parents([package],generation)[0]
    probe_file=_project_file(_PROJECT_ROOT, AUTHOR/package_record['probe_closure'])
    probe = json.loads(probe_file.read_text())
    if not probe['complete_all_windows'] or not probe['changed_windows'] or probe['candidate_identity'] != candidate['identity']:
        raise ValueError('先通过完整实际V3评分和行为差异门')
    compositions = json.loads(Path(plan['compositions_file']).read_text())
    by_root = {r['root_id']:r for r in compositions['pilot']['0.6']}
    selected = [by_root[k] for k in plan['root_ids']]
    if len(selected)!=2 or plan['planned_actual_tables'] != 16:
        raise ValueError('每块固定2新开发母根、16实际桌')
    if not json.loads((_project_file(_PROJECT_ROOT, ENGINEERING/'smoke-1/summary.json')).read_text())['engineering_complete']:
        raise ValueError('新对手工具工程门未过')
    if not json.loads((_project_file(_PROJECT_ROOT, ENGINEERING/'PILOT-ROOT-CLOSE-AUDIT.json')).read_text())['complete']:
        raise ValueError('开发批未完整核验')
    if not json.loads((_project_file(_PROJECT_ROOT, CAUSAL/'ROOT-READBACK.json')).read_text())['complete']:
        raise ValueError('第二提案同起点完整核验未过')
    out = _project_file(_PROJECT_ROOT, HERE/f'block-{BLOCK:02d}'); out.mkdir(exist_ok=False)
    frozen_files = {str(path.resolve()):sha(path) for path in (plan_path, Path(plan['compositions_file']),
        generation_file, package_pointer, package/'generation.json',package/'candidate.py',probe_file,
        _project_file(_PROJECT_ROOT, ENGINEERING/'smoke-1/summary.json'), _project_file(_PROJECT_ROOT, ENGINEERING/'PILOT-ROOT-CLOSE-AUDIT.json'),
        _project_file(_PROJECT_ROOT, CAUSAL/'ROOT-READBACK.json'), _project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json'),Path(__file__))}
    manifest = source_manifest(('hangma_bot.offline.qualifier_opponents',))
    manifest.update(candidate['identity']['source_manifest'])
    manifest[str(Path(__file__).relative_to(REPO_ROOT))] = digest_of_file(Path(__file__))
    write_code_snapshot(out,manifest)
    save(out/'START.json',dict(plan,candidate_identity=candidate['identity'],frozen_files=frozen_files,
        source_manifest=manifest,source_kind='simulation',opponent_compositions=selected,
        confirmation_claim=False,published=False,logical_clock_not_deadline_evidence=True))
    started = time.perf_counter()
    charges, root_audits, results, issues, settlements = [],[],[],[],[]
    scoring_audits, decision_count, max_compute_ms = [],0,0.0
    stream = (out/'views.jsonl.gz').open('x+b')
    capture = ScoringInputCapture(stream,limits=ScoringInputCaptureLimits.from_json(plan['scoring_input_capture']))
    capture_result = None
    primary = None
    try:
        with gzip.open(out/'decisions.jsonl.gz','wt',encoding='utf-8') as decision_stream, \
             gzip.open(out/'settlements.jsonl.gz','wt',encoding='utf-8') as settlement_stream:
            def settlement_sink(row):
                settlement_stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
                settlement_stream.flush(); settlements.append(row)
            def sink(row):
                nonlocal decision_count,max_compute_ms
                decision_stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
                decision_stream.flush(); decision_count += 1
                max_compute_ms = max(max_compute_ms,row['policy_compute_ms_observed'])
                if row['status']!='chosen' or ('c_self_scored' in row and row['policy_id'].startswith('vip:') and not row['c_self_scored']):
                    issues.append('失败决策:'+row['decision_id'])
                if any('action_value_failed' in reason for reason in row.get('degraded_reasons',())):
                    issues.append('R18内部评分回退:'+row['decision_id'])
            for root_row in selected:
                runtime = build_qualifier_runtime(generation,candidate['source'],root_row['opponent_types_logical_1_2_3'])
                engine = VipDevelopmentAuditEngine(runtime.engine,settlement_sink=settlement_sink)
                active = [runtime.declarations[k] for k in ('A','C','Q1','Q2','Q3')]
                policies = {d.policy_id:VipDevelopmentAuditPolicy(runtime.policies_by_id[d.policy_id],
                    d.policy_id,lambda:dict(engine.context),sink,
                    challenger=d.policy_id==runtime.challenger_policy_id,capture=capture) for d in active}
                scoring_audits.extend(p.scoring for p in policies.values() if p.scoring is not None)
                root = FrozenRoot(root_row['root_id'],((0,1,2,3),(1,2,3,0),(2,3,0,1),(3,0,1,2)),
                                  ('all_natural',)*4,(0.0,)*4)
                root_results = []
                for permutation in root.permutations:
                    if (_project_file(_PROJECT_ROOT, HERE/'GLOBAL-ENGINEERING-FAILURE.json')).exists():
                        raise RuntimeError('其他分块出现工程故障，不启新桌；保留全分母')
                    if time.perf_counter()-started > plan['wall_clock_limit_seconds']:
                        raise TimeoutError('批次墙钟预算已耗尽，不启新桌')
                    label = ''.join(map(str,permutation))
                    entry = {'root_id':root.root_id,'permutation':list(permutation),
                        'status':'reserved','charged_table_instances':2,'actual_started_table_instances':None}
                    charges.append(entry); save(out/'costs.json',{'entries':charges,'scoring_input_capture':capture.costs})
                    if sum(e['charged_table_instances'] for e in charges)>plan['planned_actual_tables']:
                        raise ValueError('桌实例预留超过冻结预算')
                    engine.context = {'root_id':root.root_id,'permutation':list(permutation),
                        'focal_physical_seat':permutation[0],'opponent_types_logical_1_2_3':root_row['opponent_types_logical_1_2_3']}
                    experiment = MatchExperiment('matches','logical',runtime.declarations['A'],runtime.declarations['C'],
                        tuple(runtime.declarations[f'Q{i}'] for i in range(1,4)),runtime.config,
                        (MatchSeedSpec(root_row['seed'],root.root_id),),(permutation,),permutation.index(0),(0,0,0,0),
                        step_limit=plan['step_limit'],match_id_prefix='t64-second-joint-fresh-qualifier',simulation_version=WORLD_SCHEMA,
                        input_sha256=sha(plan_path),source_namespace='hangma-simulation')
                    before = engine.started_table_instances; group_started = time.perf_counter()
                    try:
                        outcome = await run_match_experiment(experiment,engine=engine,spec_factory=MatchSpec,
                            choice_factory=lambda key,action:SimulationChoice(key,action),policies_by_id=policies,
                            rules=runtime.rules,rules_hash=compute_rules_hash(REPO_ROOT),now_monotonic=lambda:800.,
                            wall_clock=None,budget_policy=BudgetPolicy(),source_kind='simulation',
                            value_limits=generation.route_limits,challenger_route_limits=generation.route_limits,
                            strict_challenger=True)
                        root_results.extend(outcome.results); results.extend(outcome.results)
                        issues.extend(outcome.excluded)
                        with gzip.open(out/f'group-{root.root_id.rsplit(":",1)[-1]}-{label}.json.gz','wt',encoding='utf-8') as gs:
                            json.dump({'experiment':asdict(experiment),'results':[r.to_json() for r in outcome.results],
                                'match_records':[{'match_id':k,'outcome':v.to_json()} for k,v in outcome.match_records]},gs,
                                ensure_ascii=False,sort_keys=True)
                        group_faults = [k for k,v in outcome.match_records if v.status!='complete' or any(
                            getattr(v.runtime_counts,key)!=0 for key in ('timeouts','illegal_choices','fallbacks','auto_actions','audit_missing'))]
                        if group_faults or len(outcome.results)!=2:
                            raise ValueError('桌未完成或运行计数非零:'+str(group_faults))
                        entry['status']='settled'
                    except BaseException as exc:
                        entry.update(status='failed_cost_retained',error=type(exc).__name__+': '+str(exc)); raise
                    finally:
                        entry['actual_started_table_instances']=engine.started_table_instances-before
                        entry['charged_table_instances']=max(2,entry['actual_started_table_instances'])
                        entry['duration_wall_seconds']=time.perf_counter()-group_started
                        save(out/'costs.json',{'entries':charges,'scoring_input_capture':capture.costs})
                    print({'root':root.root_id,'rotation':label,'completed_actual_tables':len(results),'seconds':round(time.perf_counter()-started,2)},flush=True)
                # 旧核验器严格要求固定对手池；每根独立使用，不改变其历史语义。
                audit = audit_vip_batch([root],{'all_natural':1.0},root_results,
                    baseline_policy_id=runtime.baseline_policy_id,challenger_policy_id=runtime.challenger_policy_id)
                if not audit.confirmable: raise ValueError('母根四换座配对核验未过')
                root_audits.append(asdict(audit)); save(out/'root-audits.json',root_audits)
    except BaseException as exc:
        primary=exc; issues.append(type(exc).__name__+': '+str(exc))
        signal_failure(exc)
    finally:
        try:
            capture_result=capture.finish()
        except BaseException as exc:
            issues.append('捕获终态失败:'+type(exc).__name__+': '+str(exc)); capture_result=capture.costs
        try: stream.close()
        except BaseException as exc: issues.append('底层流关闭失败:'+type(exc).__name__)
        save(out/'costs.json',{'entries':charges,'scoring_input_capture':capture_result})
    end_manifest=source_manifest(('hangma_bot.offline.qualifier_opponents',))
    end_manifest.update(generation.identity(candidate['source'])['source_manifest'])
    end_manifest[str(Path(__file__).relative_to(REPO_ROOT))]=digest_of_file(Path(__file__))
    stable=(manifest==end_manifest and all(sha(Path(path))==expected for path,expected in frozen_files.items())
            and generation.identity(candidate['source'])==candidate['identity'])
    if not stable:
        issues.append('冻结文件或依赖闭包漂移'); signal_failure(RuntimeError('source drift'))
    if not capture_result['terminal']['terminal_valid']: issues.append('实际输入捕获终态无效')
    if any(a.failed_calls or a.audit_sink_failed_calls for a in scoring_audits): issues.append('实际评分或审计调用失败')
    if time.perf_counter()-started>plan['wall_clock_limit_seconds']: issues.append('批次墙钟超限')
    challenger_id='vip:'+candidate['identity']['candidate_id']
    ledger=realized_ledger(settlements,challenger_id)
    ledgers=ledger['counts_and_actual_net_by_arm']
    if any(ledgers[arm]['unknown']['hands'] for arm in ('A','C')):
        issues.append('存在未知已发生结算，不能完整解释收益分账')
    for arm in ('A','C'):
        from_tables=sum(r.scores_after[r.seat_permutation[0]]-r.scores_before[r.seat_permutation[0]]
            for r in results if (r.policy_ids_by_seat[r.seat_permutation[0]]==challenger_id)==(arm=='C')
            and r.scores_after is not None and r.scores_before is not None)
        sums=[v['focal_score_sum'] for v in ledgers[arm].values()]
        if any(v is None for v in sums) or sum(sums)!=from_tables:
            issues.append('单局分账与完整桌积分不守恒:'+arm)
    complete=(not issues and len(results)==16 and len(root_audits)==2 and len(settlements)==128)
    root_means=[a['natural_score_delta'] for a in root_audits]
    summary={'schema':'t64-qualifier-development-block-result/1','development_complete':complete,'identity_stable':stable,
        'confirmation_claim':False,'published':False,'candidate_identity':candidate['identity'],
        'planned_actual_tables':16,'observed_result_rows':len(results),'completed_hands':len(settlements),
        'charged_table_instances':sum(e['charged_table_instances'] for e in charges),
        'actual_started_table_instances':sum(e['actual_started_table_instances'] or 0 for e in charges),
        'root_audits':root_audits,'issues':issues,'decision_windows':decision_count,
        'estimated_net_score_delta_per_table':sum(root_means)/2 if complete else None,
        'realized_ledger':ledger,'scoring_input_capture':capture_result,
        'max_choose_ms_with_capture_observed':max_compute_ms,
        'timing_scope':'offline_capture_logical_clock_not_online_deadline_gate',
        'duration_wall_seconds':time.perf_counter()-started}
    save(out/'summary.json',summary)
    save(out/'end-freeze.json',{'source_manifest':end_manifest,'source_stable':stable,'frozen_files':frozen_files})
    with (out/'results.jsonl').open('w') as rs:
        for r in results: rs.write(json.dumps(r.to_json(),ensure_ascii=False,sort_keys=True)+'\n')
    print({k:summary[k] for k in ('development_complete','observed_result_rows','completed_hands','issues')},flush=True)
    if primary is not None: raise primary
    if not complete:
        signal_failure(RuntimeError('block incomplete'))
        raise SystemExit(1)


def signal_failure(exc):
    """工程失败在组边界停止其他块，不杀正在进行的桌；首个故障只写一次。"""
    try:
        with (_project_file(_PROJECT_ROOT, HERE/'GLOBAL-ENGINEERING-FAILURE.json')).open('x') as stream:
            json.dump({'block':BLOCK,'error':type(exc).__name__+': '+str(exc)},stream,ensure_ascii=False)
    except FileExistsError:
        pass


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--block',type=int,required=True,choices=range(1,5))
    BLOCK=parser.parse_args().block
    try:
        asyncio.run(main())
    except BaseException as exc:
        signal_failure(exc)
        raise
