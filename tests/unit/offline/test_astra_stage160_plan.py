"""公开计划接口验证真四席、配对、独立十桌与完整阶段边界。"""
import importlib.util
from pathlib import Path
import pytest


FILE=Path(__file__).resolve().parents[3]/'tools/research/astra-evolution-2026-10-10/stage160.py'
spec=importlib.util.spec_from_file_location('astra_stage160_plan',FILE)
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)


def declaration():
    return {'tables_per_stage':10,'rounds_per_table':16,'seat_variants':[0,1,2,3],
        'stage_roots':['independent-stage-001','independent-stage-002'],
        'opponent_tags':['RF1','P0','P0'],'runtime_root':'/runtime','rules_hash':'rules',
        'candidate':{'kind':'P0_identity'}}


def test_complete_ten_tables_true_relative_dealer_and_paired_walls(tmp_path):
    tasks=stage.build_tasks(declaration(),tmp_path)
    assert len(tasks)==2*10*4*2
    assert len({x['id'] for x in tasks})==len(tasks)
    for root in declaration()['stage_roots']:
        own=[x for x in tasks if x['stage_root']==root]
        assert len({x['table_seed'] for x in own})==10
        for table in range(10):
            rows=[x for x in own if x['table_no']==table]
            assert {x['focal_seat'] for x in rows}=={0,1,2,3}
            assert {x['initial_dealer'] for x in rows}=={0}
            assert len({(x['focal_seat']-x['initial_dealer'])%4 for x in rows})==4
        for variant in range(4):
            rows=[x for x in own if x['seat_variant']==variant]
            assert len(rows)==20
            for slot in range(10):
                a,b=[x for x in rows if x['table_no']==slot]
                for key in ['pair_id','scenario_id','focal_seat','initial_dealer','table_seed','policy_tags_seat_order_0_to_3']:
                    assert a[key]==b[key]


@pytest.mark.parametrize('key,value',[('tables_per_stage',9),('rounds_per_table',8),('seat_variants',[0,1]),
    ('stage_roots',['duplicate','duplicate']),('opponent_tags',['leaderboard_unknown','P0','P0'])])
def test_incomplete_or_mislabelled_stage_is_rejected(tmp_path,key,value):
    d=declaration();d[key]=value
    with pytest.raises(ValueError):stage.build_tasks(d,tmp_path)


@pytest.mark.parametrize('workers',[0,12,14])
def test_worker_cap_is_enforced(workers):
    with pytest.raises(ValueError):stage.verify_declaration({'cpu_cores':14,'workers':workers})
