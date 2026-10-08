"""通过真实发牌器验证确认赛程；全部种子仅用于开发检查，绝不算确认样本。"""

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
from copy import deepcopy
from pathlib import Path
import json
import pytest
import confirmation_pairing as pairing
from hangma_bot.simulation.shuffle import wall_for_round

CONTRACT=_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')


def contract():
    return json.loads(CONTRACT.read_text())


@pytest.mark.parametrize('opponent',['H','M'])
def test_physical_walls_shared_across_four_seats_and_both_arms(opponent):
    cfg=contract()
    root=pairing.build_root_plan(contract=cfg,registration_seed=91237,opponent=opponent,root_index=1)
    rows=root['configurations'];tables=cfg['group']['tables_per_group']
    all_ids=set();root_walls=[]
    for index in range(tables):
        plans=[pairing.natural.stage.TablePlan.from_json(r['tables'][index]) for r in rows]
        assert len({(p.seed,p.scenario_id) for p in plans})==1
        assert {p.permutation[0] for p in plans}=={0,1,2,3}
        for logical in range(4):
            assert {p.permutation[logical] for p in plans}=={0,1,2,3}
        for p in plans:
            assert p.logical_participants[0]==pairing.natural.FOCAL_PARTICIPANT
            assert p.policy_names==plans[0].policy_names
            assert p.initial_dealer==0
            assert p.table_id not in all_ids
            all_ids.add(p.table_id)
        for round_no in range(1,9):
            walls=[wall_for_round(p.scenario_id,p.seed,round_no) for p in plans]
            assert all(w==walls[0] for w in walls)
            root_walls.append(walls[0])
            # 双臂读取同一计划；改变日志match_id不应改变牌山。
            restored=deepcopy(rows[0]['tables'][index]);restored['match_id']='different-log-only'
            assert wall_for_round(restored['scenario_id'],restored['seed'],round_no)==walls[0]
    assert len(set(root_walls))==tables*8
    assert root['release_eligible'] is False and root['confirmation_registered'] is False
    assert pairing.build_root_plan(contract=cfg,registration_seed=91237,opponent=opponent,root_index=1)==root


def test_different_root_and_opponent_do_not_share_draw_identity():
    plans=[pairing.build_root_plan(contract=contract(),registration_seed=91237,opponent=m,root_index=i)
           for m in ('H','M') for i in (1,2)]
    assert len({p['independence_id'] for p in plans})==4
    assert len({p['root_content_digest'] for p in plans})==4
    actual=[]
    for root in plans:
        p=root['configurations'][0]['tables'][0]
        actual.append(wall_for_round(p['scenario_id'],p['seed'],1))
    assert len(set(actual))==4


@pytest.mark.parametrize('change',[{'registration_seed':True},{'registration_seed':-1},{'root_index':True},{'root_index':0},{'opponent':'X'}])
def test_invalid_source_is_rejected_before_any_execution(change):
    args={'contract':contract(),'registration_seed':91237,'opponent':'H','root_index':1,**change}
    with pytest.raises(ValueError):pairing.build_root_plan(**args)
