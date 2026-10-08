"""固定首8母×四换座自然诊断的文件级封存；0业务导入/规则/评分/World/桌。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = '.private/t199-four-step-execution/natural-development-tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys

from common import HERE,STAGE,ROOT,canonical,pin,save


def main():
    """机械复用32成功原任务，只绑定选定源/比较器，实际pilot须根另批准。"""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',default='A-H0',choices=('A-H0','A-G2-R1','B'))
    parser.add_argument('--comparator',type=Path);args=parser.parse_args()
    joint_path=STAGE/'joint-continuation/common.py'
    loader=importlib.util.spec_from_file_location('t199_natural_composite_reader',joint_path)
    joint=importlib.util.module_from_spec(loader);sys.modules[loader.name]=joint;loader.loader.exec_module(joint)
    origins_path=STAGE/'p0-impact-32-attempt-004/COMPOSITE-ORIGINS.json'
    origins=json.loads(origins_path.read_text());reference_path=Path(origins['reference_plan_path'])
    reference,tables,reference_files,origin_plans=joint.composite_origins(reference_path,origins_path)
    measurement_path=STAGE/'p0-impact-32-attempt-004/PLAN.json';measurement=json.loads(measurement_path.read_text())
    if measurement['candidate_identity']!=reference['candidate_identity'] or measurement['runtime_files']!=reference['runtime_files']:
        raise ValueError('测量helper不是同共同P0来源')
    mechanical_path=STAGE/'strategy-runner/MECHANICAL-PLAN-2.json';mechanical=json.loads(mechanical_path.read_text())
    comparator=(args.comparator or (STAGE/'strategy/A-G2-R1/root_selection.py' if args.variant=='A-G2-R1' else STAGE/'strategy/root_selection_draft.py')).resolve()
    sources={}
    for name,row in mechanical['sources'].items():
        path=Path(row['path']);actual=pin(path)
        declared=row.get('sha256')
        if declared is not None and actual['sha256']!=declared:raise ValueError('冻结公式源码漂移:'+name)
        sources[name]={'path':str(path.resolve()),'pin':actual}
    if set(sources)!={'parent','B','C'}:raise ValueError('缺原parent/B/C固定源，不造新公式')
    native=reference['compiled_runtime'];parent_file=_project_file(_PROJECT_ROOT, ROOT/native['directory']/'source.py')
    if Path(sources['parent']['path']).read_bytes()!=parent_file.read_bytes():raise ValueError('parent源不是P0实际native源')
    if args.variant=='A-H0' and comparator!=STAGE/'strategy/root_selection_draft.py':raise ValueError('根当前A-H0固定预算不可换比较器')
    files={**reference_files,**measurement['files'],str(measurement_path):pin(measurement_path),str(joint_path):pin(joint_path),
        str(mechanical_path):pin(mechanical_path),str(STAGE/'strategy-runner/runtime_policy.py'):pin(STAGE/'strategy-runner/runtime_policy.py'),
        str(STAGE/'strategy-runner/binding.py'):pin(STAGE/'strategy-runner/binding.py'),str(comparator):pin(comparator)}
    files.update({row['path']:row['pin'] for row in sources.values()})
    tool_paths=[_project_file(_PROJECT_ROOT, HERE/name) for name in ('common.py','focal.py','run_table.py','worker.py','controller.py','prepare_plan.py')]
    for path in tool_paths:ast.parse(path.read_text(),filename=str(path));files[str(path)]=pin(path)
    # 下列字段全取已成功原32任务；不创建场景、不抽新墙、不读confirmation。
    plan=copy.deepcopy(reference)
    plan.update(schema='t199-fixed-natural-single-arm-development/1',purpose='A-H0固定首8母32桌完整机制诊断；不是净增强确认',
        output_directory=str(HERE),runtime_root=str(ROOT),reference_plan_path=str(reference_path),reference_plan_pin=pin(reference_path),
        composite_origins_path=str(origins_path),composite_origins_pin=pin(origins_path),composite_references={str(key):value for key,value in tables.items()},
        measurement_plan_path=str(measurement_path),measurement_plan_pin=pin(measurement_path),
        informational_reason_allowlist_by_policy_id=measurement['informational_reason_allowlist_by_policy_id'],
        informational_reason_evidence=measurement['informational_reason_evidence'],files=files,selected_variant=args.variant,
        request_routing_variant='B' if args.variant=='B' else 'A',selected_source=sources['B' if args.variant=='B' else 'parent'],sources=sources,
        comparator={'path':str(comparator),'pin':pin(comparator)},
        parent_execution_id=native['manifest']['original_execution_id'],
        pilot_ordinals=[0],remaining_ordinals=list(range(1,32)),
        planned_table_instances=32,planned_completed_hands=256,actual_new_planned_table_instances=32,
        worker_count=4,requested_nice=19,requested_low_IO=3,logical_now=reference['logical_now'],
        strength_admission=False,original_deadline_admitted=False,main_changed=False,
        parent_tree_choices_and_native_scoring_unchanged=True,natural_choose_each_window=True,forced_first_actions=0,
        single_arm=True,reference_only_no_parent_rescores=True,pilot_reused_never_repeated=True,
        expansion_16_32_or_confirmation_allowed=False,retry_failed_table_allowed=False,
        record_costs_actual=True,prepare_business_import_rule_score_world_table_API_calls=0)
    plan['binding_id']=__import__('hashlib').sha256(canonical(plan)).hexdigest()
    plan['focal_policy_id']='T199:'+args.variant+':'+plan['binding_id']
    # focal标签由完整绑定派生，摘要核验时明确排除派生标签，避免自引用。
    plan['binding_digest_excludes']=['binding_id','focal_policy_id','binding_digest_excludes']
    save(_project_file(_PROJECT_ROOT, HERE/'PLAN.json'),plan)
    loaded={name:str(Path(module.__file__).resolve()) for name,module in tuple(sys.modules.items())
        if name in ('common','t199_natural_measurement','t199_natural_composite_reader')}
    if any(name=='hangma_bot' or name.startswith('hangma_bot.') for name in sys.modules):raise ValueError('文件级准备误导入hangma')
    save(_project_file(_PROJECT_ROOT, HERE/'FILE-ONLY-CLOSED.json'),{'schema':'t199-natural-development-file-preparation/1','complete':True,
        'plan_pin':pin(_project_file(_PROJECT_ROOT, HERE/'PLAN.json')),'binding_id':plan['binding_id'],'selected_variant':args.variant,
        'selected_source':plan['selected_source'],'comparator':plan['comparator'],'tool_pins':{str(path):pin(path) for path in tool_paths},
        'actual_loaded_stdlib_helper_paths':loaded,'actual_hangma_modules':0,'scores_rules_worlds_tables_API':0,
        'reference_complete_tables':32,'source_mothers':8,'Rounds':8,'pilot_table_no':plan['tasks'][0]['table_no'],
        'pilot_new_table_instances':1,'remaining_new_table_instances':31,'execution_approval_missing_expected':True,
        'no_winner_or_strength_claim':True,'four_shared_slot_paths':plan['slot_paths'],'nice':19,'IO':3})
    print({'complete':True,'file_only':True,'variant':args.variant,'pilot':plan['tasks'][0]['table_no'],'planned_natural_tables':32,'actual_scores_worlds':0})


if __name__=='__main__':main()
