"""根直接核验T24静态改动范围；不执行候选、规则或模型。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t24-discard-route-portfolio-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import hashlib
import json
from pathlib import Path

B = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t24-discard-route-portfolio-author-1')
P = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t19-maintained-ready-choice-author-1/S01-model-output/candidate.py')


def main():
    parent, child = P.read_text(), (_project_file(_PROJECT_ROOT, B / "candidate.py")).read_text()
    pt, ct = ast.parse(parent), ast.parse(child)
    pf = {node.name: node for node in pt.body if isinstance(node, ast.FunctionDef)}
    cf = {node.name: node for node in ct.body if isinstance(node, ast.FunctionDef)}
    helpers = {}
    for name, node in pf.items():
        if name == "score_actions":
            continue
        old, new = ast.get_source_segment(parent, node), ast.get_source_segment(child, cf[name])
        assert old == new, name
        helpers[name] = hashlib.sha256(old.encode()).hexdigest()
    assert len(helpers) == 8 and set(cf) == set(pf) | {"root_portfolio"}
    assignments = lambda tree: {
        node.targets[0].id: ast.dump(node.value, include_attributes=False)
        for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    pa, ca = assignments(pt), assignments(ct)
    assert all(ca.get(name) == value for name, value in pa.items())
    oldprefix = parent[parent.index("def score_actions(view):"):parent.index("        trace =")]
    newprefix = child[child.index("def score_actions(view):"):child.index("        trace =")]
    begin = newprefix.index("        portfoliofacts = None\n")
    end = newprefix.index("        # 小根表解释", begin)
    block = newprefix[begin:end]
    bt = ast.parse("def block():\n" + block).body[0].body
    assert len(bt) == 2 and isinstance(bt[0], ast.Assign) and isinstance(bt[1], ast.If)
    expected = ast.parse("anchor is None and kind == 'discard' and rootnode['kind'] == 'wait' and drawscale > 0.0", mode="eval").body
    assert ast.dump(bt[1].test, include_attributes=False) == ast.dump(expected, include_attributes=False)
    assert len(bt[1].body) == 2
    before_trace = newprefix[:begin] + newprefix[end:]
    assert ast.dump(ast.parse(before_trace), include_attributes=False) == ast.dump(ast.parse(oldprefix), include_attributes=False)
    calls = [node for node in ast.walk(ct) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "root_portfolio"]
    assert len(calls) == 1
    receipt = {"schema": "t24-root-formula-scope-static/1", "status": "accepted_static_scope_no_scores",
               "original_source_sha256": hashlib.sha256(child.encode()).hexdigest(),
               "eight_helpers_exact_source": helpers, "old_constants_ast_equal": True,
               "new_constants": sorted(set(ca) - set(pa)),
               "score_prefix_ast_identical_after_removing_one_guard": True,
               "guard": "anchor is None and discard and direct wait and drawscale>0",
               "new_helper_call_sites": 1, "trace_changes_separate_from_value_computation": True,
               "protected_runtime_values_still_require_mechanics": True,
               "rules_graph_payment_or_interface_changes": 0, "root_formula_repairs": 0,
               "new_independent_reviews": 0, "new_business_scores": 0}
    with (_project_file(_PROJECT_ROOT, B / "ROOT-FORMULA-SCOPE-CHECK.json")).open("x") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "helpers": len(helpers), "business_calls": 0}))


if __name__ == "__main__":
    main()
