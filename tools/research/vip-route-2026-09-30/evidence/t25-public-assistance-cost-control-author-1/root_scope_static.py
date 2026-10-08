"""根核T25原答只改费用返还一赋值；不执行候选、规则或模型。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t25-public-assistance-cost-control-author-1'

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
import hashlib
import json
from pathlib import Path

B = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t25-public-assistance-cost-control-author-1')
P = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t24-discard-route-portfolio-author-1/S01-model-output/candidate.py')


def strip_doc(node):
    node = copy.deepcopy(node)
    if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
        node.body.pop(0)
    return node


class FormulaLabel(ast.NodeTransformer):
    """仅统一trace公式版本字符串，所有运算和字段仍逐项比较。"""
    def visit_Constant(self, node):
        if isinstance(node.value, str) and node.value.startswith("vip_") and node.value.endswith("m1/1"):
            return ast.copy_location(ast.Constant(value="formula_label_only"), node)
        return node


def main():
    parent, child = P.read_text(), (_project_file(_PROJECT_ROOT, B / "candidate.py")).read_text()
    pt, ct = ast.parse(parent), ast.parse(child)
    pf = {node.name: node for node in pt.body if isinstance(node, ast.FunctionDef)}
    cf = {node.name: node for node in ct.body if isinstance(node, ast.FunctionDef)}
    assert set(pf) == set(cf)
    helpers = {}
    for name, node in pf.items():
        if name in ("score_actions", "root_portfolio"):
            continue
        old, new = ast.get_source_segment(parent, node), ast.get_source_segment(child, cf[name])
        assert old == new, name
        helpers[name] = hashlib.sha256(old.encode()).hexdigest()
    assert len(helpers) == 8
    assignments = lambda tree: {
        node.targets[0].id: ast.dump(node.value, include_attributes=False)
        for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    assert assignments(pt) == assignments(ct)
    old = strip_doc(pf["root_portfolio"])
    new = strip_doc(cf["root_portfolio"])
    expected_old = ast.parse("publicfacts[0] * ROOTHELP_BLEND * credit / (ROOTPORT_CAP + credit)", mode="eval").body
    expected_new = ast.parse("publicfacts[0]", mode="eval").body
    matches = [node for node in ast.walk(new) if isinstance(node, ast.Assign)
               and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
               and node.targets[0].id == "refund"
               and ast.dump(node.value, include_attributes=False) == ast.dump(expected_new, include_attributes=False)]
    assert len(matches) == 1
    matches[0].value = copy.deepcopy(expected_old)
    assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)
    old_score = FormulaLabel().visit(strip_doc(pf["score_actions"]))
    new_score = FormulaLabel().visit(strip_doc(cf["score_actions"]))
    assert ast.dump(old_score, include_attributes=False) == ast.dump(new_score, include_attributes=False)
    receipt = {"schema": "t25-root-isolated-fee-scope-static/1", "status": "accepted_static_scope_no_scores",
               "true_parent_candidate_id": "edda117c2593f75e1098e280546187084655f35f540642fc081842cf484e43a1",
               "original_source_sha256": hashlib.sha256(child.encode()).hexdigest(),
               "eight_helpers_exact_source": helpers, "all_constants_ast_identical": True,
               "root_portfolio_one_refund_assignment_only": True,
               "score_actions_ast_identical_except_formula_label": True,
               "original_guard_and_full_graph_computation_unchanged": True,
               "new_functions": 0, "root_formula_repairs": 0, "new_independent_reviews": 0,
               "new_business_scores": 0, "runtime_protection_still_required": True}
    with (_project_file(_PROJECT_ROOT, B / "ROOT-FORMULA-SCOPE-CHECK.json")).open("x") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "helpers": len(helpers), "business_calls": 0}))


if __name__ == "__main__":
    main()
