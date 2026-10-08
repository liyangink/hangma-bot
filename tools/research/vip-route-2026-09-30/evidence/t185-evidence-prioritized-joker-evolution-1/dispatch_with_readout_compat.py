"""已失败且零桌的开发派发显式恢复，或确认首派发；兼容R18正常评分说明。

原派发器与原计划字节保留；只有只读资源附加证据、读回入口和尝试文件名
发生列明变化，两个槽、原run_table、512/1024桌和统计选择均不变。
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
import argparse
import ast
import asyncio
import copy
import types
from pathlib import Path

from common import HERE, pin
import t185_close_development as dev
from readout_compat import addon_files, prior_resource_evidence


def require_zero_table_recovery():
    """仅允许旧派发自然失败、实际零桌时新建一次恢复；不覆盖原失败或任何桌。"""
    directory = _project_file(_PROJECT_ROOT, HERE / "development-dispatch")
    failure, _ = dev.read(directory / "FAILED.json")
    start, _ = dev.read(directory / "START.json")
    dev.require(failure["failure"]["message"] == "旧进程已消失但资源终态缺失，保留未知不接管" and
        failure["child_pids"] == [] and failure["returncodes_observed"] == [] and
        start["new_table_calls_at_start"] == 0 and failure["plan_pin"] == start["plan_pin"] == pin(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json")),
        "原派发不是已失败的零桌等待，禁止恢复")
    dev.require(not any((directory / n).exists() for n in ("RESOURCE-READY.json", "CLOSED.json", "RECOVERY-1-START.json")) and
        not (_project_file(_PROJECT_ROOT, HERE / "natural-development")).exists() and not (_project_file(_PROJECT_ROOT, HERE / "development-workers")).exists(),
        "原派发已启动或恢复已存在，禁止重复")


def dispatch_context(phase):
    """在独占globals中作三项源码转换；不修改原模块或工作进程的实现。"""
    if phase == "development":
        import dispatch_development as original
    else:
        import dispatch_confirmation as original
    context = dict(original.__dict__)
    context.update(__file__=__file__, require_zero_table_recovery=require_zero_table_recovery,
        compatibility_prior=types.SimpleNamespace(development_resource_evidence=prior_resource_evidence))
    tree = ast.parse(Path(original.__file__).read_bytes())
    function = copy.deepcopy(next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "main"))
    class DeclaredChanges(ast.NodeTransformer):
        changed = {"prior": 0, "directory": 0, "readout": 0, "start": 0, "failure": 0}
        def visit_Import(self, node):
            if phase == "development" and len(node.names) == 1 and node.names[0].name == "confirmation_resources":
                self.changed["prior"] += 1
                return ast.Assign(targets=[ast.Name("prior",ast.Store())], value=ast.Name("compatibility_prior",ast.Load()))
            return node
        def visit_Expr(self, node):
            if (phase == "development" and isinstance(node.value, ast.Call) and
                isinstance(node.value.func,ast.Attribute) and isinstance(node.value.func.value,ast.Name) and
                node.value.func.value.id == "directory" and node.value.func.attr == "mkdir"):
                self.changed["directory"] += 1
                return ast.Expr(ast.Call(ast.Name("require_zero_table_recovery",ast.Load()), [], []))
            return self.generic_visit(node)
        def visit_Constant(self, node):
            replacements = {"t185_close_development.py": "close_with_readout_compat.py",
                "t185_close_confirmation.py": "close_with_readout_compat.py"}
            if isinstance(node.value, str) and node.value in replacements:
                self.changed["readout"] += 1
                return ast.Constant(replacements[node.value])
            if phase == "development" and node.value in ("START.json", "FAILED.json"):
                # START只有一次，失败路径也只有一次；worker的START路径表达式不改。
                return node
            return node
        def visit_Call(self, node):
            # 只改顶层派发记录，worker START和其他证据仍是原名称。
            if phase == "development" and isinstance(node.func,ast.Name) and node.func.id == "save" and node.args:
                path = node.args[0]
                if (isinstance(path,ast.BinOp) and isinstance(path.left,ast.Name) and path.left.id == "directory" and
                    isinstance(path.right,ast.Constant) and path.right.value in ("START.json","FAILED.json")):
                    key = "start" if path.right.value == "START.json" else "failure"
                    self.changed[key] += 1
                    path.right.value = "RECOVERY-1-" + path.right.value
            return self.generic_visit(node)
    transform = DeclaredChanges()
    function = transform.visit(function)
    expected = {"prior": 1, "directory": 1, "readout": 1, "start": 1, "failure": 1} if phase == "development" else {
        "prior": 0,"directory": 0,"readout": 1,"start": 0,"failure": 0}
    dev.require(transform.changed == expected, "派发源码转换超出列明修改:" + str(transform.changed))
    # 真实子进程命令明确指定对应读回阶段，不依赖进程继承globals。
    count = 0
    for node in ast.walk(function):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id == "readout_command" for t in node.targets):
            dev.require(isinstance(node.value,ast.List), "原读回命令不是列表")
            node.value.elts.extend([ast.Constant("--phase"),ast.Constant(phase)])
            count += 1
    dev.require(count == 1, "读回子进程入口不唯一")
    compiled = ast.Module(body=[function],type_ignores=[])
    ast.fix_missing_locations(compiled)
    exec(compile(compiled, str(Path(__file__)), "exec"),context)
    context["compatibility_transform_counts"] = transform.changed
    return context


async def main(phase):
    """事前验签兼容工具；原owner锁、自然结束和资源归零流程仍由原外壳执行。"""
    files = addon_files()
    context = dispatch_context(phase)
    await context["main"]()
    dev.require(all(pin(Path(p)) == h for p,h in files.items()), "派发期间兼容工具漂移")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase",choices=("development","confirmation"),required=True)
    asyncio.run(main(parser.parse_args().phase))
