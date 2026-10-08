"""T199 P0实际工程证据的小型绑定；不评分，不更改草稿或运行资格包。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime/performance'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from performance_common import HERE,OUT,P0,package,pin,read,root_unchanged,save


def main():
    """核真实成功原件和保留失败，按已裁定的合法及时口径封存有限适用范围。"""
    inputs=read(OUT/'INPUTS.json');reference=read(OUT/'reference-002/CLOSED.json')
    deadline=read(OUT/'deadlines-002/CLOSED.json');legal=read(OUT/'timely-legal-002/CLOSED.json')
    fallback=read(OUT/'corrected-fallback-003/CLOSED.json');payload=package()
    if not (reference['complete'] and legal['complete'] and fallback['complete']):raise ValueError('成功证据未闭')
    identity=payload['candidate_identity']
    if not (identity==inputs['candidate_identity']==reference['P0_identity']==legal['candidate_identity']==fallback['candidate_identity']):
        raise ValueError('实际核心／参数身份不同')
    original=inputs['rows'][:39]
    serial=[row for wave in deadline['waves'] if not wave['concurrent'] for row in wave['rows']]
    original_waves=[wave for wave in legal['waves'] if wave['wave'].startswith('original-ten-')]
    nominal=[wave for wave in legal['waves'] if wave['wave'].startswith('nominal-')]
    faults=[wave for wave in legal['waves'] if wave['fail_rule_analysis']]
    if not (len(original)==len(serial)==39 and all(row['complete'] for row in serial)
            and len(original_waves)==2 and all(wave['complete'] and wave['timely_legal_submissions']==10 for wave in original_waves)
            and sum(wave['complete_scoring'] for wave in original_waves)==14
            and sum(wave['explicit_fallback_or_skip'] for wave in original_waves)==6
            and sum(wave['complete_scoring'] for wave in nominal)==31
            and sum(wave['timely_legal_submissions'] for wave in faults)==2
            and legal['resources_released'] and not legal['remaining_child_pids']):raise ValueError('实际分母／原窗／资源未闭')
    receipts={name:{'path':str(OUT/path),'pin':pin(OUT/path)} for name,path in {
        'inputs':'INPUTS.json','full_plan_equivalence':'reference-002/CLOSED.json',
        'serial_original_and_ten_full_scoring_failure':'deadlines-002/CLOSED.json',
        'production_timely_legal':'timely-legal-002/CLOSED.json',
        'corrected_fallback_logic':'corrected-fallback-003/CLOSED.json',
        'fake_session_first_attempt_failure':'timely-legal-001/CLOSED.json'}.items()}
    original_inputs=[{key:case[key] for key in ('label','decision_id','origin','origin_position','record_sha256','original_monotonic_ns','original_remaining_seconds')}
        for case in original]
    for case in original_inputs:case['origin_pin']=inputs['input_files'][case['origin']]
    compiled=payload['compiled_runtime'];native=compiled['manifest']
    native_file=native['module']+'.cpython-311-darwin.so'
    binary_path=P0/compiled['directory']/native_file
    if pin(binary_path)!=native['files'][native_file]:raise ValueError('实际native字节漂移')
    counts=[]
    # 所有已发生调用均保留，包括工具包装失败；不把失败误记0成本。
    for path in sorted(OUT.glob('*/CLOSED.json')):
        result=read(path)
        row={'path':str(path),'pin':pin(path),'complete':result.get('complete')}
        for key in ('actual_choose_attempts','actual_candidate_score_calls','actual_service_choose',
                    'actual_injected_native_score_calls','local_attempts','audited_full_scoring_count'):
            if key in result:row[key]=result[key]
        if 'waves' in result:
            row['actual_dispatched']=sum(wave.get('resource_terminal',{}).get('dispatched',0) for wave in result['waves']) if 'actual_service_choose' in result else result['resource_terminal']['dispatched']
            row['actual_full_scoring_completed']=sum(wave.get('resource_terminal',{}).get('completed',0) for wave in result['waves']) if 'actual_service_choose' in result else result['resource_terminal']['completed']
        counts.append(row)
    save(OUT/'ENGINEERING-CLOSED.json',{
        'schema':'t199-P0-performance-engineering-close/1','complete':True,
        'runtime_passed_for_covered_legal_deadline_and_fault_recovery':True,'corrected_fallback_passed_for_covered_faults':True,
        'candidate_identity':identity,'core_id':identity['candidate_id'],'params':identity['params'],
        'rules_source_hash':payload['rules_source_hash'],'source_sha256':identity['source_sha256'],
        'native':{'execution_id':legal['execution_id'],'compiled_manifest_sha256':compiled['manifest_sha256'],
            'compiled_manifest_pin':pin(P0/compiled['directory']/'manifest.json'),'actual_binary':{'path':str(binary_path),'pin':pin(binary_path)},
            'shared_original_helpers':native['shared_original_helpers'],'math_backend':identity['math_backend']},
        'draft_package_id':payload['release_package_id'],'draft_offline_validation_only':True,
        'receipts':receipts,'original_requests':39,'original_input_pins':original_inputs,
        'serial_original':{'full_plans_exact':39,'before_original_fallback':39,
            'max_rules_and_IPC_ms':max(row['total_rules_and_IPC_seconds']*1000 for row in serial),
            'minimum_fallback_margin_ms':min((row['relative_budget_seconds'][1]-row['total_rules_and_IPC_seconds'])*1000 for row in serial),
            'minimum_latest_send_margin_ms':min((row['relative_budget_seconds'][2]-row['total_rules_and_IPC_seconds'])*1000 for row in serial)},
        'original_two_ten_bursts':{'actual_local_actions':20,'timely_legal_actions':20,'full_scoring':14,'explicit_budget_fallback':6,
            'minimum_latest_send_margin_ms':min((row['relative_budget_seconds'][2]-row['received_to_submit_seconds'])*1000 for wave in original_waves for row in wave['submissions'])},
        'nominal':{'public_heavy':18,'P0_gold':13,'full_scoring':31,'timely_legal_actions':31,
            'minimum_latest_send_margin_ms':min((row['relative_budget_seconds'][2]-row['received_to_submit_seconds'])*1000 for wave in nominal for row in wave['submissions']),
            'historical_remaining_budget_not_available':True},
        'corrected_faults':{'logic_cases':9,'logic_local_attempts':10,'gold_real_SystemClock_rule_failures':2,
            'gold_tags':['SYN03-six-natural-pairs-white','SYN11-chain-four-white-formula'],
            'explicit_rejection_excludes_attempted_action':True,'ambiguous_no_repeat':True,'original_deadline_not_extended':True,
            'fallback_003_positive_case_label_correction':'其SYN06实际也是负分支；真阳性由timely-legal-002的SYN03补齐，原件未改'},
        'three_degradation_kinds':{
            'isolated_choose_original_ten_deadline':'原deadlines-002完整评分请求10个DEADLINE，0dispatch；原失败保留，不授全评分',
            'production_budget_skip':'生产动作循环两个十桌组各3窗按原增强截止跳过条件事实并及时合法保底',
            'intentional_enhancement_fault':'编译评分/增强规则故障注入独立合法保底；额外真时钟2例policy_failures=2为预期负例'},
        'actual_local_actions_in_final_real_clock_probe':53,'real_clock_full_scoring_completed':45,
        'resource_terminal':legal['resource_terminal'],'resources_released':True,'worker_pids':legal['worker_pids'],
        'all_workers_cpu_nice':0,'root_after':root_unchanged(),'all_attempt_costs':counts,
        'full_ten_scoring_admitted':False,'real_HTTP_submissions_verified':False,'first_real_room_confirmation_pending':True,
        'scope_lifecycle_SSE_409_evidence_reused_same_code':True,'all_rule_trajectories_covered':False,
        'HTTP_Token_tests_rooms':0,'qualification_package_changed':False,
        'source_tool_pin':pin(_project_file(_PROJECT_ROOT, HERE/'close_performance.py'))})
    print({'complete':True,'covered_original_serial':39,'covered_original_burst_legal':20,'nominal_scoring':31,'real_clock_actions':53,
        'receipt':str(OUT/'ENGINEERING-CLOSED.json')})


if __name__=='__main__':main()
