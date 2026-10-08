"""累计读取器真实旧账复核及费用门边界检查，不生成候选成绩。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import copy
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save


def source(i, net=10, big=3, payment=2):
    """构造合成四座账本，仅测试门槛与坏输入，不能当自然策略收益。"""
    delta = {"net":net,"ordinary_hu_income":net-big-payment,"large_hu_income":big,"payments":payment}
    return {"root":i,"root_id":f"synthetic-{i}","paired_tables":[{"rotation":r,"delta":dict(delta)} for r in range(4)],
        "four_seat_delta_sums":{k:v*4 for k,v in delta.items()}}


def main():
    """新计算核原16来源均差与区间逐值一致，再检查淘汰条件独立生效。"""
    path = _project_file(_PROJECT_ROOT, HERE/"read_natural_cumulative-v2.py")
    spec = importlib.util.spec_from_file_location("t186_cumulative_v2_check",path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    oldpath = _project_file(_PROJECT_ROOT, HERE/"natural-stage-002-dispatch/CUMULATIVE-SUMMARY.json")
    old = json.loads(oldpath.read_text())
    planpath = _project_file(_PROJECT_ROOT, HERE/"NATURAL-STAGE-002-PLAN.json")
    plan = json.loads(planpath.read_text())
    real = module.summarize(old["sources"],old["blocks"],plan["bootstrap"])
    for key in ("independent_roots","mean_delta_per_complete_table","net_exploratory_source_bootstrap95",
        "exploratory_next_stage_budget_eligible","new_block_net_direction"):
        assert real[key] == old[key]
    assert real["net_mean_excluding_maximum_positive_source"] == 3.4
    small = {"seed":1861005,"replicates":1000}
    block = [{"mean_delta_per_complete_table":{"net":10}}]
    good = [source(i) for i in range(1,33)]
    result = module.summarize(good,block,small)
    assert result["independent_confirmation_budget_eligible"] and all(result["stronger_development_budget_criteria"].values())
    cases = []
    tests = [
        ("below_practical_net",[source(i,net=4,big=1,payment=0) for i in range(1,33)],block,"mean_net_at_least_5"),
        ("negative_large_income",[source(i,big=-2,payment=0) for i in range(1,33)],block,"cumulative_large_income_nonnegative"),
        ("only_one_large_positive_source",[source(i,big=3 if i==1 else 0,payment=0) for i in range(1,33)],block,"two_distinct_large_income_positive_sources"),
        ("latest_block_negative",good,[{"mean_delta_per_complete_table":{"net":-1}}],"latest_block_net_positive"),
        ("one_extreme_source",[source(i,net=250 if i==1 else -1,big=0,payment=0) for i in range(1,33)],block,"excluding_maximum_net_source_still_positive")]
    for label,sources,blocks,key in tests:
        checked = module.summarize(sources,blocks,small)
        assert not checked["independent_confirmation_budget_eligible"] and not checked["stronger_development_budget_criteria"][key]
        cases.append({"label":label,"specified_criterion_rejected":key,"synthetic_not_candidate_score":True})
    bad = []
    for label in ("duplicate_root_id","missing_rotation","inconsistent_account","source_order_gap"):
        rows = copy.deepcopy(good)
        if label=="duplicate_root_id": rows[1]["root_id"]=rows[0]["root_id"]
        elif label=="missing_rotation": rows[0]["paired_tables"].pop()
        elif label=="inconsistent_account": rows[0]["paired_tables"][0]["delta"]["net"]+=1
        else: rows[1]["root"]=3
        try:
            module.summarize(rows,block,small)
        except AssertionError:
            bad.append(label)
        else:
            raise AssertionError("坏输入未拒绝："+label)
    target=_project_file(_PROJECT_ROOT, HERE/"CUMULATIVE-READER-PREFLIGHT.json")
    assert not target.exists()
    save(target,{"complete":True,"files":{str(p):pin(p) for p in (Path(__file__),path,oldpath,planpath)},
        "real_16_source_statistics_exact_match":True,"real_max_source_exclusion_mean":3.4,
        "synthetic_all_criteria_pass":True,"synthetic_failed_criteria":cases,"bad_inputs_rejected":bad,
        "new_scores_worlds_tables_models_HTTP":0,"stronger_candidate_or_online_admission":False})
    print(json.dumps({"complete":True,"real_16_source_statistics_exact_match":True,"independent_gate_failures_checked":len(cases),
        "bad_inputs_rejected":len(bad),"new_scores_worlds_tables_models_HTTP":0}))


if __name__=="__main__":
    main()
