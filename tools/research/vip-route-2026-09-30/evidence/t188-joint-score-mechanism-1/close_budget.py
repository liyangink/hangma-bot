"""按读分前冻结的条件费用门决定是否买64桌，不将筛选当作增强证明。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import pin, save


def main():
    """仅读取已闭原件和机械检查，不补抽、不发起模型或牌桌。"""
    resultpath, planpath = _project_file(_PROJECT_ROOT, HERE / "CONDITION-CLOSED.json"), _project_file(_PROJECT_ROOT, HERE / "CONDITION-PLAN.json")
    result, plan = [json.loads(p.read_text()) for p in (resultpath, planpath)]
    gatepath = _project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")
    gate = json.loads(gatepath.read_text())
    assert result["complete"] and result["source_stable"] and result["resources_released"]
    assert result["plan_pin"] == pin(planpath) and gate["complete"] and gate["mechanical_passed"]
    assert result["counts"]["single_hand_dispatched"] == plan["planned_single_hand_continuations"] == 84
    sampled = result["public_compatible_uniform"]
    rule = plan["fee_rule_for_64_table_pilot"]
    positive = [r["root_id"] for r in sampled["source_groups"] if r["sum_C_minus_A"]["net"] > 0]
    criteria = {
        "conditional_net_positive": sampled["sum_C_minus_A"]["net"] > 0,
        "conditional_large_income_nonnegative": sampled["sum_C_minus_A"]["large_hu_income"] >= 0,
        "minimum_distinct_positive_source_groups": len(positive) >= rule["minimum_distinct_positive_source_groups"],
        "mechanical_complete_required": gate["complete"] and gate["mechanical_passed"],
    }
    eligible = all(criteria.values())
    next_action = (
        "仅允许另行冻结64自然桌小试；不自动派发，不读取独立确认来源。"
        if eligible else
        "停止c70同版完整桌费用；保留局部正例，先查后继双白提前小胡与继续失胡的联合取舍，不机械追加样本。"
    )
    save(_project_file(_PROJECT_ROOT, HERE / "PILOT-BUDGET-DECISION.json"), {
        "complete": True, "candidate_identity": gate["identity"], "criteria": criteria,
        "64_table_pilot_budget_eligible": eligible,
        "independent_confirmation_budget_eligible": False,
        "natural_strength_or_online_admission": False,
        "historical_sum_C_minus_A": result["historical_exposed"]["sum_C_minus_A"],
        "conditional_sum_C_minus_A": sampled["sum_C_minus_A"],
        "positive_source_groups": positive, "counts": result["counts"],
        "files": {str(p): pin(p) for p in (Path(__file__), resultpath, planpath, gatepath)},
        "new_scores_worlds_tables_models_HTTP": 0,
        "proposal_proven_globally_worse": False, "next_action": next_action,
    })
    print(json.dumps({"complete": True, "criteria": criteria,
        "64_table_pilot_budget_eligible": eligible, "actual_new_tables_models_HTTP": 0}))


if __name__ == "__main__":
    main()
