"""读回兼容附加工具：接受R18成功说明，原统计函数及原冻结文件不改。

原DecisionPlan把成功说明放在degraded_reasons；这里只给精确R18成功
字符串单列信息计数。实际原件不改写，未知说明、真实降级和身份缺失仍拒绝。
"""

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
import sys
import types
from pathlib import Path

from common import HERE, OLD, pin
import t185_close_development as dev

CONTRACT = _project_file(_PROJECT_ROOT, HERE / "READOUT-COMPATIBILITY-CONTRACT.md")
CHECKED = _project_file(_PROJECT_ROOT, HERE / "READOUT-COMPATIBILITY-CHECKED.json")
FAILURE = _project_file(_PROJECT_ROOT, HERE / "PRIOR-READOUT-FAILED-007.json")
R18_DONE = "action_value: r18_integrated_positive_v2 评分完成"


def addon_files():
    """额外执行代码事前验签；不替换旧计划里的原文件摘要。"""
    checked, checked_pin = dev.read(CHECKED)
    dev.require(checked["complete"] and checked["actual_metadata_tables"] == 512 and
        checked["all_negative_checks_passed"] and checked["statistics_and_selection_unchanged"] and
        checked["new_scores_worlds_tables"] == 0, "兼容附加工具未经真实全批元数据及负例检查")
    dev.require(all(pin(Path(p)) == h for p,h in checked["files"].items()), "兼容附加工具验证后漂移")
    return {**checked["files"], str(CHECKED): checked_pin}


def metadata_adapter(original):
    """保留原校验，仅把确切R18成功信息从降级判定分离；原审计仍计数保存。"""
    def compatible(table, closure, plan):
        seat = table.rotation
        kinds = plan["roots"][table.index - 1]["opponent_types_logical_1_2_3"]
        decisions, completed = [], 0
        for row in closure["outcome"]["decisions"]:
            other = row.get("seat")
            changed = row
            if type(other) is int and 0 <= other < 4 and other != seat:
                kind = kinds[(other - seat) % 4 - 1]
                if kind == "r18" and row.get("degraded_reasons") == [R18_DONE]:
                    changed = {**row, "degraded_reasons": []}
                    completed += 1
            decisions.append(changed)
        # 只是校验用浅副本；原文件和原决策对象均不改写。
        checked = {**closure, "outcome": {**closure["outcome"], "decisions": decisions}}
        focal, identities, audit = original(table, checked, plan)
        audit["opponent_compatibility_diagnostic_decisions_by_type"]["r18"] += completed
        notes = audit["opponent_compatibility_diagnostic_counts_by_type"]["r18"]
        if completed:
            notes[R18_DONE] = notes.get(R18_DONE, 0) + completed
        audit["r18_success_information_count"] = completed
        audit["readout_compatibility_addon"] = "r18_success_information_v2"
        return focal, identities, audit
    return compatible


def function_copy(function, context):
    """复用原函数字节码但独占globals；不修改旧模块的全局对象。"""
    result = types.FunctionType(function.__code__, context, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def copied_readout(module, *, confirmation=False, unchecked=False):
    """构造独立读回上下文；只换元数据校验并追加执行身份，不改变统计与选择。"""
    context = dict(module.__dict__)
    if confirmation:
        # 确认借同型开发receipt校验；独占命名空间替换，旧模块不受影响。
        reader = types.SimpleNamespace(**copied_readout(dev, unchecked=unchecked))
        context["dev"] = reader
    else:
        context["decision_metadata"] = metadata_adapter(module.decision_metadata)
        context["score_receipts"] = function_copy(module.score_receipts, context)
    frozen_original = module.frozen if hasattr(module, "frozen") else dev.frozen
    def frozen_with_addon(plan):
        frozen_original(plan)
        if not unchecked:
            addon_files()
    context["frozen"] = frozen_with_addon
    if hasattr(module, "frozen_repair"):
        original = module.frozen_repair
        context["frozen_repair"] = lambda: {**original(), **({} if unchecked else addon_files())}
    tree = ast.parse(Path(module.__file__).read_bytes())
    function = copy.deepcopy(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_readout"))
    additions = ast.parse("""
files.update(addon_files())
result['readout_compatibility_addon'] = 'r18_success_information_v2'
result['readout_compatibility_checked_pin'] = pin(CHECKED)
result['original_readout_and_statistics_files_unchanged'] = True
""").body
    # 插入在result构造后、序列化前；不接触eligible/selected和其余原函数语句。
    at = next(i for i,n in enumerate(function.body) if isinstance(n, ast.Assign) and
        any(isinstance(t, ast.Name) and t.id == "result" for t in n.targets)) + 1
    function.body[at:at] = additions
    context.update(addon_files=addon_files, CHECKED=CHECKED, pin=pin)
    transformed = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(transformed)
    exec(compile(transformed, str(Path(__file__)), "exec"), context)
    # confirmation没有自身main；入口复用开发的nice/IO/锁壳。
    if hasattr(module, "main"):
        context["main"] = function_copy(module.main, context)
    else:
        def confirmation_main(preflight_only=False):
            module.background_priority()
            with module.postprocess_lock("confirmation_readout_with_r18_success_compatibility"):
                return context["_readout"](preflight_only)
        context["main"] = confirmation_main
    return context


def prior_modules():
    """旧批固定模块通过实际路径装载，不引用别的仓库或旧快照。"""
    if str(OLD) not in sys.path:
        sys.path.append(str(OLD))
    import close_development_readout_repair as repair
    import close_development_resume as resume
    import confirmation_resources as resources
    return repair, resume, resources


def prior_resource_evidence(development_pin, development_plan_pin, *, verify=False):
    """复用原全资源核验，仅精确纠正失败后第二次调用的事实；不读中途积分。"""
    _, _, original = prior_modules()
    closure, closure_pin = dev.read(OLD / "RESOURCE-SCHEDULING-CLOSED.json")
    dev.require(closure.get("readout_attempts_after_all_terminals") == 2 and
        closure.get("repaired_dev_readout_called_once_after_all_terminals") is False and
        closure.get("repaired_dev_readout_successfully_closed_once_after_all_terminals") is True and
        closure.get("readout_compatibility_checked_pin") == pin(CHECKED) and
        closure.get("prior_failed_readout_pin") == pin(FAILURE), "旧资源附加事实未知")
    addon_files()
    tree = ast.parse(Path(original.__file__).read_bytes())
    function = copy.deepcopy(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "development_resource_evidence"))
    class ActualAttempts(ast.NodeTransformer):
        count = 0
        def visit_Compare(self, node):
            if (isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Attribute) and
                node.left.func.attr == "get" and node.left.args and isinstance(node.left.args[0], ast.Constant) and
                node.left.args[0].value == "repaired_dev_readout_called_once_after_all_terminals"):
                dev.require(len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant) and
                    node.comparators[0].value is True, "原资源一次调用谓词变了")
                node.comparators[0].value = False
                self.count += 1
            return self.generic_visit(node)
    transform = ActualAttempts()
    function = transform.visit(function)
    dev.require(transform.count == 1, "只准改变一次调用的真实事实判据")
    body = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(body)
    context = dict(original.__dict__)
    exec(compile(body, str(Path(__file__)), "exec"), context)
    actual, actual_pin = context["development_resource_evidence"](development_pin, development_plan_pin, verify=verify)
    dev.require(actual == closure and actual_pin == closure_pin, "资源原件被修改或返回别的副本")
    return actual, actual_pin
