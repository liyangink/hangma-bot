"""独立确认赛程的纯构造原型：同牌山四换座；不执行或登记正式确认。

候选与V2共用返回计划。完整世界只由模拟器生成，不进入候选评分输入。
尚须持久来源/显著性台账、完整结果核验及发布接线；本模块不授予发布资格。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
from typing import Any, Mapping
import confirmation_draft as draft
import sitin_natural_panel as natural
from hangma_bot.simulation import shuffle

SCHEMA = 'sitin-confirmation-cross-seat-plan-draft/1'


def build_root_plan(*, contract: Mapping[str, Any], registration_seed: int,
                    opponent: str, root_index: int) -> dict:
    """构造一个独立根的四个换座配置，返回严格可序列化的赛程与身份。

    registration_seed为预登记的整数随机来源，不是时间戳；root_index从1开始。
    每桌seed/scenario_id在四换座和双臂之间相同；焦点与三家对手整体轮换。
    返回牌山身份只供离线执行器，禁止放入评分视图。调用方必须另证来源未消费。
    """
    if type(registration_seed) is not int or registration_seed < 0:
        raise ValueError('registration_seed必须是非负整数，布尔不算数')
    if type(root_index) is not int or root_index < 1:
        raise ValueError('root_index必须是正整数')
    if opponent not in ('H', 'M'):
        raise ValueError('只支持冻结H/M情景')
    stage=natural.stage
    tables=contract['group']['tables_per_group']
    if type(tables) is not int or tables < 1:
        raise ValueError('每阶段桌数必须是正整数')
    opponents=contract['panel']['opponent_scenarios'][opponent]['opponent_policies']
    if len(opponents)!=3 or any(not isinstance(x,str) or not x for x in opponents):
        raise ValueError('对手必须是三个非空策略名')
    stage_spec=stage.ladder_stages(contract,4)[0]
    root_seed=stage.derive_seed(registration_seed,SCHEMA,opponent,root_index)
    source_id=f'cf-cross-seat-v1-{opponent}-{registration_seed}-root{root_index}'
    participants=[{'participant_id':natural.FOCAL_PARTICIPANT,'policy_name':'focal-arm'}]
    participants += [{'participant_id':f'opp-{i+1}','policy_name':name} for i,name in enumerate(opponents)]
    rows=[]
    for anchor in range(4):
        plans=[]
        for table_no in range(1,tables+1):
            seed=stage.derive_seed(root_seed,'table',table_no)
            scenario=f'cf-cross-seat-v1:{root_seed}:table{table_no}'
            permutation=stage.rotate_permutation(anchor+table_no-1)
            plan=stage.build_table_plan(stage_no=1,stage_name=str(stage_spec['name']),
                stage_role='qualify',stage_kind='group_round',
                table_id=f'{source_id}-seat{anchor}-tt{table_no}',participants=participants,
                permutation=permutation,seed=seed,tables_in_stage=tables,group_index=1)
            # scenario_id也参与发牌：不能只冻结seed，再把座位或臂名混入scenario。
            plan=replace(plan,scenario_id=scenario,
                pair_id=scenario+':'+''.join(str(x) for x in permutation))
            plans.append(plan.to_json())
        rows.append({'focal_anchor_seat':anchor,'tables':plans})
    body={'schema':SCHEMA,'source_root_id':source_id,'opponent_mix':opponent,
        'independence_id':draft.digest({'schema':SCHEMA,'registration_seed':registration_seed,
            'opponent':opponent,'root_index':root_index,'root_seed':root_seed}),
        'contract_digest':draft.digest(contract),'configurations':rows,
        'runtime_identity':{'deal_algorithm':shuffle.DEAL_ALGORITHM,
            'python_version':sys.version,
            'source_sha256':{name:hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                for name,module in [('shuffle',shuffle),('stage',stage),('plan_builder',sys.modules[__name__])]}},
        'arm_plan_shared':True,'confirmation_registered':False,'release_eligible':False}
    return dict(body,root_content_digest=draft.digest(body))
