"""确认工具的事前算术与坏输入验证；只用明确标为合成的数据，不生成牌局。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import copy
from pathlib import Path

from common import HERE, OLD, pin, save
import t185_prepare_confirmation as prepare
import t185_close_confirmation as reader
from prepare_confirmation_tools import function


def tables_with_delta(value):
    """构造128母来源四桌合成净差；只测试统计分母和门槛，不能作候选成绩。"""
    roots = [{"root_id": f"synthetic-{i}", "seed": i} for i in range(128)]
    plan = {"roots": roots, "rotations": [0, 1, 2, 3], "selected_candidate_id": "synthetic-only",
            "candidates": [{"identity": {"candidate_id": "synthetic-only"}}]}
    tables = {}
    for i, root in enumerate(roots, 1):
        for rotation in plan["rotations"]:
            net = value(i, rotation)
            control = {"net": 0, "ordinary_hu_income": 0, "large_hu_income": 0, "payments": 0,
                "own_hu_ge8_income": 0, "own_hu_ge16_income": 0, "own_hu_ge32_income": 0}
            child = {**control, "net": net, "ordinary_hu_income": max(0, net), "payments": min(0, net)}
            common = {"opponent_policy_ids_physical": [None, "Q1", "Q2", "Q3"],
                      "pairing_proofs": [{"physical_wall_sha256": "synthetic-only"}]}
            tables[(i, rotation, 0)] = {**common, "account": control}
            tables[(i, rotation, 1)] = {**common, "account": child}
    return plan, tables


def rejection(operation):
    """测试必须真实拒绝坏输入；没有抛预期错误则验证失败。"""
    try:
        operation()
    except (ValueError, FileNotFoundError, KeyError, AssertionError):
        return True
    raise AssertionError("预期坏输入未被拒绝")


def main():
    """先核函数来源、再核分母与事前门；排他保存验证，不改变工具或原实验。"""
    derived = (_project_file(_PROJECT_ROOT, HERE / "t185_run_confirmation.py")).read_text()
    expected = function(OLD / "run_confirmation.py", "run_table").replace("t182-confirmation", "t185-confirmation")
    expected = expected.replace("settlement_sink=settlements.append)", "settlement_sink=settlements.append, focal_seat=rotation)")
    actual = function(_project_file(_PROJECT_ROOT, HERE / "t185_run_confirmation.py"), "run_table")
    assert ast.dump(ast.parse(actual)) == ast.dump(ast.parse(expected))
    account = function(_project_file(_PROJECT_ROOT, HERE / "t185_close_confirmation.py"), "account")
    original = function(OLD / "close_confirmation.py", "account").replace("t182-confirmation", "t185-confirmation").replace("t182-development", "t185-development")
    assert ast.dump(ast.parse(account)) == ast.dump(ast.parse(original))
    outcomes = {}
    cases = [("constant_one", lambda i,r: 1, 1.0, True),
             ("at_half_point", lambda i,r: int(r < 2), 0.5, True),
             ("below_half_point", lambda i,r: int(r == 0), 0.25, False),
             ("zero", lambda i,r: 0, 0.0, False),
             ("source_balanced", lambda i,r: 1 if i <= 64 else -1, 0.0, False)]
    for name, value, mean, passes in cases:
        plan, tables = tables_with_delta(value)
        result = reader.summarize(plan, tables)
        assert result["mean_delta"]["net"] == mean and result["independent_strength_evidence_passed"] is passes
        assert result["paired_complete_tables"] == 512 and result["independent_mother_sources"] == 128
        if name != "source_balanced":
            assert result["net_source_bootstrap95"] == [mean, mean]
        outcomes[name] = {"mean": mean, "interval": result["net_source_bootstrap95"], "passed": passes}
    plan, tables = tables_with_delta(lambda i,r: 1)
    bad = copy.deepcopy(tables)
    bad[(1,0,1)]["account"]["net"] = 2
    negative = {"bad_ledger": rejection(lambda: reader.summarize(plan, bad)),
        "missing_mother_sources": rejection(lambda: reader.bootstrap_interval([1] * 127)),
        "boolean_cluster": rejection(lambda: reader.bootstrap_interval([True] * 128)),
        "development_resource_not_closed": rejection(prepare.require_development_dispatch)}
    bad = copy.deepcopy(tables)
    bad[(1,0,1)]["pairing_proofs"] = [{"physical_wall_sha256": "different"}]
    negative["unpaired_wall"] = rejection(lambda: reader.summarize(plan, bad))
    assert not prepare.PLAN.exists() and not (_project_file(_PROJECT_ROOT, HERE / "natural-confirmation")).exists()
    names = ("t185_prepare_confirmation.py", "t185_run_confirmation.py", "t185_close_confirmation.py",
        "run_confirmation_workers.py", "dispatch_confirmation.py", "CONFIRMATION-READOUT-CONTRACT.md",
        "prepare_confirmation_tools.py", "CONFIRMATION-TOOLS-PREPARED.json", "check_confirmation_tools.py", "common.py",
        "t185_run_development.py", "t185_close_development.py")
    files = {str(_project_file(_PROJECT_ROOT, HERE / n)): pin(_project_file(_PROJECT_ROOT, HERE / n)) for n in names}
    for n in names:
        if n.endswith(".py"):
            ast.parse((_project_file(_PROJECT_ROOT, HERE / n)).read_bytes(), filename=n)
    save(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-TOOLS-CHECKED.json"), {"complete": True, "files": files,
        "original_run_table_ast_identical_except_namespace_and_teacher_stratum": True,
        "original_account_ast_identical_except_namespace": True, "synthetic_statistics_checked": True,
        "synthetic_cases": outcomes, "actual_negative_checks": negative, "new_scores_worlds_tables": 0,
        "confirmation_plan_generated": False, "candidate_strength_claim": False})
    print("confirmation_tools_checked_no_new_scores_worlds_tables")


if __name__ == "__main__":
    main()
