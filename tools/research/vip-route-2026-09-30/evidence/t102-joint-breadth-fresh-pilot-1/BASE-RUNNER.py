"""八个新母牌山、两个R18配对、共128桌的八块固定公式开发。

工具复用已过16桌工程预检的构造、评分输入和结算链，保持公式／规则／预算。
每块2母根16桌；四进程分两波，全终态前只看进度／费用／故障。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t102-joint-breadth-fresh-pilot-1'

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
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.offline.vip_evaluation import FrozenRoot, audit_vip_batch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditEngine, VipDevelopmentAuditPolicy
from hangma_bot.simulation import MatchSpec, SimulationChoice
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import WORLD_SCHEMA

HERE = Path(__file__).resolve().parent
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
    generation_file = Path(plan['generation_file'])
    source_file = Path(plan['raw_source_file'])
    generation = VipEohBatch.read(generation_file)
    source = source_file.read_text(encoding='utf-8')
    candidate = {'source': source, 'identity': generation.identity(source)}
    if candidate['identity'] != plan['candidate_identity']:
        raise ValueError('冻结后的执行身份漂移')
    compositions = json.loads(Path(plan['compositions_file']).read_text())
    by_root = {r['root_id']: r for r in compositions['roots']}
    selected = [by_root[k] for k in plan['root_ids']]
    if len(selected) != 2 or plan['planned_actual_tables'] != 16 or plan['planned_hands'] != 128:
        raise ValueError('每块固定2母根、16完整桌、128单局')
    if plan['confirmation_claim'] or plan['published'] or plan['old_admission_or_results_transferred']:
        raise ValueError('本批不准入、不发布、不转移旧成绩')
    out = _project_file(_PROJECT_ROOT, HERE/f'block-{BLOCK:02d}'); out.mkdir(exist_ok=False)
    frozen_files = {str(plan_path.resolve()): sha(plan_path), **plan['prerequisite_sha256']}
    manifest = source_manifest(tuple(plan['source_roots']))
    manifest.update(candidate['identity']['source_manifest'])
    contract = _project_file(_PROJECT_ROOT, REPO_ROOT/candidate['identity']['contract_path'])
    manifest[candidate['identity']['contract_path']] = digest_of_file(contract)
    if manifest != json.loads((_project_file(_PROJECT_ROOT, HERE/'FROZEN-SOURCE-MANIFEST.json')).read_text()):
        raise ValueError('准备与启动源码闭包不一致')
    write_code_snapshot(out,manifest)
    for relative, digest in manifest.items():
        copied = out/'code_snapshot'/relative
        if copied.stat().st_size != digest['bytes'] or sha(copied) != digest['sha256']:
            raise ValueError('实际执行快照不完整:'+relative)
    # 运行脚本在main证据目录；生产源码来自隔离工作树，不能伪造相对路径。
    (out/'RUNNER.py').write_bytes(Path(__file__).read_bytes())
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
                        raise RuntimeError('其他分块出现工程故障，不启新配对；保留128分母')
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
                        step_limit=plan['step_limit'],match_id_prefix='t99-fixed-formula-fresh-pilot',simulation_version=WORLD_SCHEMA,
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
    end_manifest = source_manifest(tuple(plan['source_roots']))
    end_manifest.update(generation.identity(candidate['source'])['source_manifest'])
    end_manifest[candidate['identity']['contract_path']] = digest_of_file(contract)
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
    summary={'schema':'t99-fresh-natural-pilot-block-result/1','block_complete':complete,'identity_stable':stable,
        'confirmation_claim':False,'published':False,'candidate_identity':candidate['identity'],
        'planned_actual_tables':16,'observed_result_rows':len(results),'completed_hands':len(settlements),
        'charged_table_instances':sum(e['charged_table_instances'] for e in charges),
        'actual_started_table_instances':sum(e['actual_started_table_instances'] or 0 for e in charges),
        'root_audits':root_audits,'issues':issues,'decision_windows':decision_count,
        'descriptive_net_score_delta_per_table':sum(root_means)/2 if complete else None,
        'realized_ledger':ledger,'scoring_input_capture':capture_result,
        'max_choose_ms_with_capture_observed':max_compute_ms,
        'timing_scope':'offline_capture_logical_clock_not_online_deadline_gate',
        'strength_confirmation':False,'new_author_calls':0,'new_formula':plan['variant']=='T97',
        'variant':plan['variant'],'comparison_scope':'development raw formula versus registered R18',
        'old_admission_or_results_transferred':False,
        'research_native_graph_meter_or_payload_overlays_used':False,
        'duration_wall_seconds':time.perf_counter()-started}
    save(out/'summary.json',summary)
    save(out/'end-freeze.json',{'source_manifest':end_manifest,'source_stable':stable,'frozen_files':frozen_files})
    with (out/'results.jsonl').open('w') as rs:
        for r in results: rs.write(json.dumps(r.to_json(),ensure_ascii=False,sort_keys=True)+'\n')
    print({k:summary[k] for k in ('block_complete','observed_result_rows','completed_hands','issues')},flush=True)
    if primary is not None: raise primary
    if not complete:
        signal_failure(RuntimeError('block incomplete'))
        raise SystemExit(1)


def signal_failure(exc):
    """首个故障全局停止新配对；不主动杀其他正在执行的配对，失败费用保留。"""
    try:
        with (_project_file(_PROJECT_ROOT, HERE/'GLOBAL-ENGINEERING-FAILURE.json')).open('x') as stream:
            json.dump({'scope':'eight_block128table_pilot','block':BLOCK,'error':type(exc).__name__+': '+str(exc)},stream,ensure_ascii=False)
    except FileExistsError:
        pass


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--block',type=int,required=True,choices=range(1,9))
    BLOCK=parser.parse_args().block
    try:
        asyncio.run(main())
    except BaseException as exc:
        signal_failure(exc)
        raise
