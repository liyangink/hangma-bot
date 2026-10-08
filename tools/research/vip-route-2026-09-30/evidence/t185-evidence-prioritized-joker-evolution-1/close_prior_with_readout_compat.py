"""旧批真实失败后的第二次只读闭合；不重开任何原桌，不覆盖任何原件。"""

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
import types
from pathlib import Path

from common import HERE, OLD, pin
from readout_compat import addon_files, copied_readout, prior_modules, CHECKED, FAILURE
import t185_close_development as dev


def main():
    """原wrapper核全部BEFORE/AFTER和512终态；修复仅诊断归类及调用次数记录。"""
    repair, resume, _ = prior_modules()
    files = addon_files()
    context = dict(resume.__dict__)
    context["repair"] = types.SimpleNamespace(**copied_readout(repair))
    context.update(addon_files=lambda: files, checked_pin=pin(CHECKED), prior_failure_pin=pin(FAILURE))
    tree = ast.parse(Path(resume.__file__).read_bytes())
    function = copy.deepcopy(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"))
    class ResourceFact(ast.NodeTransformer):
        changed = 0
        def visit_Dict(self, node):
            for i,key in enumerate(node.keys):
                if isinstance(key, ast.Constant) and key.value == "repaired_dev_readout_called_once_after_all_terminals":
                    dev.require(isinstance(node.values[i], ast.Constant) and node.values[i].value is True, "原一次调用字段已变")
                    node.values[i].value = False
                    self.changed += 1
                    for k,v in (("repaired_dev_readout_successfully_closed_once_after_all_terminals", ast.Constant(True)),
                        ("readout_attempts_after_all_terminals", ast.Constant(2)),
                        ("readout_compatibility_checked_pin", ast.Name("checked_pin", ast.Load())),
                        ("prior_failed_readout_pin", ast.Name("prior_failure_pin", ast.Load()))):
                        node.keys.append(ast.Constant(k));node.values.append(v)
            return self.generic_visit(node)
    transform = ResourceFact()
    function = transform.visit(function)
    dev.require(transform.changed == 1, "资源外壳只准改一次调用事实")
    with_block = next(n for n in function.body if isinstance(n, ast.With))
    at = next(i for i,n in enumerate(with_block.body) if isinstance(n, ast.Assign) and
        any(isinstance(t,ast.Name) and t.id == "files" for t in n.targets)) + 1
    with_block.body[at:at] = ast.parse("files.update(addon_files())").body
    output = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(output)
    exec(compile(output, str(Path(__file__)), "exec"), context)
    context["main"]()


if __name__ == "__main__":
    main()
