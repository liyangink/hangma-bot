"""仅准备T101真实时限验证的公开输入，确认批运行期间不执行评分。

选择已实际评分的三类最高操作窗口、普通出口及自然结构/当前胡控制，
另加入原工程故障碰响应。公开输入不含未来牌墙或他家暗牌。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t104-current-candidate-deadline-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.offline.scoring_sources import source_manifest
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE=Path(__file__).resolve().parent
E=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
AUTHOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t101-joint-breadth-recovery-author-1')
CONFIRMATION=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t103-joint-breadth-fresh-confirmation-1')
FAILURE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t80-witness-capacity-failure-diagnostic-1/FAILED-PUBLIC-WINDOW.json')


def sha(path):
    """按实际字节冻结公开输入，不靠场景名称猜来源。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name,value):
    """只创建准备材料，不覆盖旧结果，也不启动计时或计算服务。"""
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')


def main():
    """复用公开读取器，冻结八请求计划及原预算，实际业务调用为0。"""
    spec=importlib.util.spec_from_file_location('t104_known_public_reader',_project_file(_PROJECT_ROOT, AUTHOR/'accept_and_probe.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    panel,inputs=module.cases()
    closure=json.loads((_project_file(_PROJECT_ROOT, AUTHOR/'PUBLIC-PROBE-CLOSURE.json')).read_text())
    assert closure['complete'] and closure['primary_failure'] is None
    actual={r['label']:r for r in closure['rows']};by_label={c['label']:c for c in panel}
    batch_file=_project_file(_PROJECT_ROOT, AUTHOR/'S02-generation.batch.json');batch=VipEohBatch.read(batch_file)
    candidate=load_vip_parents([_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output')],batch)[0]
    confirm=json.loads((_project_file(_PROJECT_ROOT, CONFIRMATION/'CAMPAIGN-PLAN.json')).read_text())
    assert candidate['identity']==confirm['candidate_identity']==closure['candidate_identity']
    selected=[]
    for phase in ['draw','response_chi','response_peng']:
        pool=[c for c in panel if c['observation']['phase']==phase]
        case=max(pool,key=lambda c:actual[c['label']]['child_scores']['operations'])
        selected.append((case,'highest_actual_operations_'+phase))
    ordinary=min((c for c in panel if c['observation']['phase']=='draw'),
                 key=lambda c:actual[c['label']]['child_scores']['operations'])
    selected += [(ordinary,'ordinary_outlet'),(by_label['T96:1815'],'natural_set_control'),
                 (by_label['T94:1875'],'current_hu_control')]
    assert len({c['label'] for c,_ in selected})==6
    rows=[]
    for case,reason in selected:
        old=actual[case['label']];assert old['status']=='complete'
        rows.append({'label':case['label'],'selection_reason':reason,'observation':case['observation'],
            'window_key':case['window_key'],'known_complete_view_sha256':old['view_sha256'],
            'known_T101_actual_entries':old['child_scores']['entries'],
            'known_T101_operations':old['child_scores']['operations'],
            'reference':'previous real full scoring; not a new timing or score call'})
    failure=json.loads(FAILURE.read_text())['actual_failed_row']
    rows.append({'label':'original-T80-failed-response','selection_reason':'prior_real_capacity_and_deadline_failure',
        'observation':failure['observation'],'window_key':failure['window_key'],
        'known_complete_view_sha256':None,'known_T101_actual_entries':None,'known_T101_operations':None,
        'reference':'no T101 reference exists; do not transfer T75 scores or fabricate a reference'})
    save('PUBLIC-REQUESTS.json',{'schema':'t104-existing-public-request-selection/1','cases':rows,
        'scope':'seven development engineering inputs only; no independent strength or global deadline coverage'})
    manifest=source_manifest(('hangma_bot.application.deadline','hangma_bot.application.decision_compute',
        'hangma_bot.bootstrap','hangma_bot.policy.route_vip_heuristic'))
    manifest.update(candidate['identity']['source_manifest'])
    save('FROZEN-ENGINEERING-SOURCE-MANIFEST.json',manifest)
    files=[Path(__file__),_project_file(_PROJECT_ROOT, AUTHOR/'accept_and_probe.py'),*inputs,_project_file(_PROJECT_ROOT, AUTHOR/'PUBLIC-PROBE-CLOSURE.json'),
        _project_file(_PROJECT_ROOT, AUTHOR/'ROOT-PUBLIC-PROBE-READBACK.json'),batch_file,_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output/generation.json'),
        _project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output/candidate.py'),FAILURE,_project_file(_PROJECT_ROOT, CONFIRMATION/'CAMPAIGN-PLAN.json'),
        _project_file(_PROJECT_ROOT, HERE/'PUBLIC-REQUESTS.json'),_project_file(_PROJECT_ROOT, HERE/'FROZEN-ENGINEERING-SOURCE-MANIFEST.json')]
    budget=BudgetPolicy()
    spans={str(span):{
        'enhancement_seconds':budget.build(100.,span).enhancement_deadline_monotonic-100.,
        'fallback_seconds':budget.build(100.,span).fallback_deadline_monotonic-100.,
        'latest_send_seconds':budget.build(100.,span).latest_send_at_monotonic-100.}
        for span in [1.,3.]}
    plan={'schema':'t104-current-formula-deadline-preparation/1','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'candidate_identity':candidate['identity'],'frozen_files':{str(p):sha(p) for p in files},
        'unique_public_requests':7,'ordered_direct_choose_requests':[r['label'] for r in rows]+[rows[0]['label']],
        'repeat_last_is_warm_same_input_not_new_source':True,'max_direct_choose_attempts':8,
        'max_new_reference_score_attempts':1,'unreferenced_response_requires_real_complete_reference':True,
        'first_run_source':'unmodified formal T101 source, original rule/route/projection/operation limits',
        'runtime_overlays_or_new_math_backend_in_first_run':False,
        'record_before_scoring_and_exact_legal_scores_trace_input_operations_required':True,
        'budget_seconds_by_original_span':spans,'timer_source':'local monotonic clock; CPU time separately reported',
        'clock_starts_before_rule_analysis':True,'rules_graph_choose_and_return_all_count_toward_original_budget':True,
        'input_capture_and_phase_timing_overheads_reported_not_removed_for_deadline_credit':True,
        'bounded_service_followup_requires_frozen_factory_wire_settings_and_plan_before_launch':True,
        'activation_requires':'T103 complete valid strength signal, original four handles terminal, no parallel table load; root freezes executable runner first',
        'no_automatic_start_or_admission':True,'official_HTTP_SSE_POST_not_covered':True,
        'new_models_rules_scores_choose_worlds_tables_in_preparation':0,'actual_choose_executions':0,'published':False}
    save('PLAN.json',plan)
    print({'prepared':True,'unique_public_requests':7,'planned_direct_choose_attempts':8,
        'actual_rules_scores_choose_worlds_tables':0,'budget_seconds':spans,'source_files_frozen':len(manifest)})


if __name__=='__main__':main()
