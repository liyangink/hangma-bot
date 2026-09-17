"""action_value_v1 候选代码的进程内受限执行器。

权威材料：review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json
的 restricted_subset / limits / whitelist 三节，逐条落实为：

1. 静态子集检查（AST 层）：禁 while/import/递归/动态执行/反射/yield/生成器/
   global/nonlocal/属性白名单外访问/下划线名字/大整数常量/超指数幂；
   只允许白名单 builtins 与只读方法（.append/.add 仅限局部构造期）。
2. 编译产物插桩：候选 AST 重写为受限产物——每个调用点、二元/一元运算、
   推导式元素、f-string 计费；for 迭代经 _av_iter 逐项计费。
3. 计数计费（2026-09-17 R1/S1 收紧）：range 按自身长度计费并禁止超大
   构造；min/max/sum/sorted/all/any/map/filter/enumerate/reversed/zip、
   容器构造与 .count/.index 一律“先限长（≤4096）再按元素计费”，真实
   遍历只发生在计费包装内；len/abs/round/int/float/bool 计 1；总操作 ≤
   MAX_COUNTED_OPERATIONS；局部单集合 ≤ MAX_LOCAL_COLLECTION_SIZE（包装
   list/dict/set，切片同受上限）；字符串长度有界；算术结果整数幅度 ≤
   2^63-1，浮点必须有限；模块级仅允许不可变常量，装载即快照、执行后
   复核，跨调用可变状态被拒绝。
4. WorkloadExceeded 继承 BaseException：受限子集内没有任何可写的 except
   处理器能捕获它（bare except / except BaseException / 任意异常类型名
   均被静态拒绝），保证候选不能捕获工作量耗尽异常继续执行。

本包只做进程内执行器；run_supervised 受监管子进程装载属于 D 包。
执行器自身不读时间/随机/文件/网络；不因任何候选挂死——所有允许计算
路径按计数计费，超限立即抛 WorkloadExceeded 使整批失效。
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import operator
from dataclasses import fields as dataclass_fields
from typing import Any, Callable, Dict, FrozenSet, List, Mapping, Optional, Set, Tuple

from .action_value import (
    CANDIDATE_KIND,
    MAX_TRACE_BYTES,
    STATUS_VALUES,
    SCORING_VIEW_SCHEMA_VERSION,
    ActionScore,
    ActionView,
    AnalysisProfileView,
    CompetitionView,
    ReferenceFeature,
    ScoreBatch,
    ScoringView,
    run_scoring_skeleton,
)

# —— 限额（权威：合同 limits.candidate；合同测试逐条对账，不在两处硬编码）——

MAX_COUNTED_OPERATIONS = 100_000  # 总计数操作上限
MAX_LOCAL_COLLECTION_SIZE = 4_096  # 局部单集合项数上限
MAX_SOURCE_BYTES = 65_536  # 候选源码字节上限
MAX_INT_MAGNITUDE = 2**63 - 1  # 运行时整数幅度界限（拒绝大整数膨胀）
MAX_POWER_EXPONENT = 4  # ** 仅允许 0—4 的整数常量指数
MAX_SHIFT_BITS = 256  # 移位量上限，防止一次性构造超大整数
MAX_STRING_CHARS = 65_536  # 单个字符串长度上限（拼接/重复/格式化后检查）
UNSIZEED_INPUT_COST = 4_096  # 无长度输入的保守计费（正常路径输入均有长度）

# 2026-09-17 R1(S1)：迭代入口全面按元素计费、range 按长度计费、模块级
# 仅不可变常量、跨调用无状态校验——计费语义变更，版本 /1 → /2，旧
# candidate_id 与旧准入记录随之失效（identity.recovery_policy 预期行为）。
EXECUTOR_VERSION = "action-value-executor/2"

# —— 白名单（权威：合同 whitelist；合同测试逐条对账）——

ALLOWED_BUILTINS: FrozenSet[str] = frozenset(
    {
        "len", "min", "max", "abs", "sum", "sorted", "reversed", "enumerate",
        "zip", "range", "round", "int", "float", "bool", "all", "any",
        "tuple", "list", "dict", "set", "frozenset", "map", "filter",
    }
)

ALLOWED_METHODS: FrozenSet[str] = frozenset(
    {
        "get", "items", "keys", "values", "count", "index",
        "append",  # 仅局部构造期（只有受限局部列表实现该方法）
        "add",  # 仅局部集合构造期（只有受限局部集合实现该方法）
    }
)


class WorkloadExceeded(BaseException):
    """候选超过工作量/集合/数值/字符串限额时的执行器终止信号。

    特意继承 BaseException 而非 Exception：受限子集的静态检查拒绝一切
    except 处理器（bare except、except BaseException 以及任何不在白名单
    内的异常类型名都不可写），因此候选无法捕获本异常继续执行；外层
    执行器与骨架按整批失效处理，降级到已备紧急计划。
    """


class StaticCheckError(ValueError):
    """候选源码未通过受限子集静态检查；装载期即失败，不进入执行。"""


def _reject(message: str) -> None:
    raise StaticCheckError(message)


# ---------------------------------------------------------------------------
# 静态子集检查
# ---------------------------------------------------------------------------

_BIN_OPS: Dict[type, str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.Pow: "**",
    ast.LShift: "<<",
    ast.RShift: ">>",
    ast.BitAnd: "&",
    ast.BitOr: "|",
    ast.BitXor: "^",
}

_UNARY_OPS: Dict[type, str] = {
    ast.USub: "-",
    ast.UAdd: "+",
    ast.Not: "not",
    ast.Invert: "~",
}


def _check_constant(node: ast.Constant) -> None:
    value = node.value
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if abs(value) > MAX_INT_MAGNITUDE:
            _reject("整数常量 {0} 超过 63 位界限（拒绝大整数膨胀）".format(value))
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _reject("浮点常量必须有限（1e400 等字面量直接拒绝）")
        return
    _reject("不允许的常量类型 {0}".format(type(value).__name__))


def _check_constant_expr(node: ast.AST) -> None:
    """模块级只允许**不可变**常量：str/int/float/bool/None 与其 tuple 组合。

    S1 修复：list/dict/set 字面量一律拒绝——它们是跨调用可变共享状态
    （CACHE.append 会让同输入连续评分产生不同输出）。可变容器只能在
    函数体内经受限包装构造（局部、随调用丢弃）。
    """
    if isinstance(node, ast.Constant):
        _check_constant(node)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        # 负数字面量（如 -2.0）是 UnaryOp 包 Constant；只放行数值常量。
        if not isinstance(node.operand, ast.Constant) or not isinstance(
            node.operand.value, (int, float)
        ):
            _reject("模块级一元符号只允许作用于数值常量")
        _check_constant(node.operand)
        return
    if isinstance(node, ast.Tuple):
        for item in node.elts:
            _check_constant_expr(item)
        return
    if isinstance(node, (ast.List, ast.Set, ast.Dict)):
        _reject(
            "模块级 {0} 字面量被拒绝：跨调用可变状态；可变容器请在函数内"
            "局部构造（受限包装随调用丢弃）".format(type(node).__name__.lower())
        )
    _reject("模块级只允许不可变常量赋值，得到 {0}".format(type(node).__name__))


def _is_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _valid_name(name: str, what: str) -> None:
    if name.startswith("_"):
        _reject("{0} {1!r} 以下划线开头：禁止触达执行器内部或双下划线名字".format(what, name))


def _resolves(name: str, scope_stack: List[Set[str]], module_names: Set[str], function_names: Set[str]) -> bool:
    if name in ALLOWED_BUILTINS or name in module_names or name in function_names:
        return True
    return any(name in scope for scope in scope_stack)


def _check_target(target: ast.AST, scope: Optional[Set[str]] = None) -> None:
    """赋值/循环目标必须是简单名字或名字元组；下标/属性写入一律拒绝。"""
    if isinstance(target, ast.Name):
        _valid_name(target.id, "目标名")
        if scope is not None:
            scope.add(target.id)
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            _check_target(item, scope)
        return
    _reject("赋值/循环目标必须是简单名字或名字元组，得到 {0}".format(type(target).__name__))


def _check_expr(
    node: ast.AST,
    scope_stack: List[Set[str]],
    module_names: Set[str],
    function_names: Set[str],
) -> None:
    if isinstance(node, ast.Constant):
        _check_constant(node)
        return
    if isinstance(node, ast.Name):
        _valid_name(node.id, "名字")
        if isinstance(node.ctx, ast.Load) and not _resolves(
            node.id, scope_stack, module_names, function_names
        ):
            _reject(
                "名字 {0!r} 不在白名单 builtins、模块常量/函数或任何局部作用域内".format(node.id)
            )
        return
    if isinstance(node, ast.Attribute):
        if not isinstance(node.ctx, ast.Load):
            _reject("禁止属性写入/删除（只读方法白名单之外没有可变通道）")
        if node.attr not in ALLOWED_METHODS:
            _reject(
                "属性 .{0} 不在只读方法白名单 {1}".format(node.attr, sorted(ALLOWED_METHODS))
            )
        _check_expr(node.value, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.Call):
        _check_expr(node.func, scope_stack, module_names, function_names)
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                _reject("禁止 *args 解包")
            _check_expr(arg, scope_stack, module_names, function_names)
        for keyword in node.keywords:
            if keyword.arg is None:
                _reject("禁止 **kwargs 解包")
            _check_expr(keyword.value, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.Subscript):
        if not isinstance(node.ctx, ast.Load):
            _reject("禁止下标写入/删除（输入与局部集合不得经下标变更）")
        _check_expr(node.value, scope_stack, module_names, function_names)
        _check_expr(node.slice, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.Slice):
        for part in (node.lower, node.upper, node.step):
            if part is not None:
                _check_expr(part, scope_stack, module_names, function_names)
        return
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            _check_expr(item, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.Set):
        for item in node.elts:
            _check_expr(item, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.Dict):
        for key in node.keys:
            if key is None:
                _reject("禁止 ** 字典解包")
            _check_expr(key, scope_stack, module_names, function_names)
        for value in node.values:
            _check_expr(value, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BIN_OPS:
            _reject("不允许的二元运算 {0}".format(type(node.op).__name__))
        if isinstance(node.op, ast.Pow):
            right = node.right
            if not (
                isinstance(right, ast.Constant)
                and isinstance(right.value, int)
                and not isinstance(right.value, bool)
                and 0 <= right.value <= MAX_POWER_EXPONENT
            ):
                _reject(
                    "** 仅允许指数为 0—{0} 的整数常量".format(MAX_POWER_EXPONENT)
                )
        _check_expr(node.left, scope_stack, module_names, function_names)
        _check_expr(node.right, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY_OPS:
            _reject("不允许的一元运算 {0}".format(type(node.op).__name__))
        _check_expr(node.operand, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            _check_expr(value, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.Compare):
        _check_expr(node.left, scope_stack, module_names, function_names)
        for comparator in node.comparators:
            _check_expr(comparator, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.IfExp):
        for part in (node.test, node.body, node.orelse):
            _check_expr(part, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.Lambda):
        args = node.args
        if args.vararg or args.kwarg or args.defaults or any(
            item is not None for item in args.kw_defaults
        ):
            _reject("lambda 不允许默认参数、*args 或 **kwargs")
        scope = {item.arg for item in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)}
        for name in scope:
            _valid_name(name, "lambda 参数")
        for item in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
            if item.annotation is not None:
                _reject("不允许 lambda 参数注解")
        _check_expr(node.body, scope_stack + [scope], module_names, function_names)
        return
    if isinstance(node, ast.JoinedStr):
        for value in node.values:
            _check_expr(value, scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.FormattedValue):
        _check_expr(node.value, scope_stack, module_names, function_names)
        if node.format_spec is not None:
            _check_expr(node.format_spec, scope_stack, module_names, function_names)
        return
    if isinstance(node, (ast.ListComp, ast.SetComp)):
        _check_comprehension(node.generators, [node.elt], scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.DictComp):
        _check_comprehension(node.generators, [node.key, node.value], scope_stack, module_names, function_names)
        return
    if isinstance(node, ast.GeneratorExp):
        _reject("禁止生成器表达式（生成器与 yield 一并禁止）")
    if isinstance(node, ast.Starred):
        _reject("禁止星号解包")
    if isinstance(node, ast.NamedExpr):
        _reject("禁止海象表达式")
    if isinstance(node, (ast.Await, ast.Yield, ast.YieldFrom)):
        _reject("禁止 await/yield（异步与生成器不在受限子集内）")
    _reject("不允许的表达式 {0}".format(type(node).__name__))


def _check_comprehension(
    generators: List[ast.comprehension],
    exprs: List[ast.AST],
    scope_stack: List[Set[str]],
    module_names: Set[str],
    function_names: Set[str],
) -> None:
    comp_scope: Set[str] = set()
    inner_stack = scope_stack + [comp_scope]
    for gen in generators:
        if gen.is_async:
            _reject("禁止异步推导式")
        _check_target(gen.target, comp_scope)
        _check_expr(gen.iter, inner_stack, module_names, function_names)
        for cond in gen.ifs:
            _check_expr(cond, inner_stack, module_names, function_names)
    for expr in exprs:
        _check_expr(expr, inner_stack, module_names, function_names)


def _check_stmts(
    body: List[ast.stmt],
    scope_stack: List[Set[str]],
    module_names: Set[str],
    function_names: Set[str],
) -> None:
    for stmt in body:
        if isinstance(stmt, ast.FunctionDef):
            _valid_name(stmt.name, "函数名")
            _check_function(stmt, scope_stack, module_names, function_names)
        elif isinstance(stmt, ast.AsyncFunctionDef):
            _reject("禁止 async 函数")
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                _check_target(target)
            _check_expr(stmt.value, scope_stack, module_names, function_names)
        elif isinstance(stmt, ast.AugAssign):
            if not isinstance(stmt.target, ast.Name):
                _reject("增量赋值目标必须是简单名字")
            if type(stmt.op) not in _BIN_OPS:
                _reject("不允许的增量运算")
            _check_expr(stmt.value, scope_stack, module_names, function_names)
        elif isinstance(stmt, ast.For):
            _check_target(stmt.target)
            _check_expr(stmt.iter, scope_stack, module_names, function_names)
            _check_stmts(stmt.body, scope_stack, module_names, function_names)
            _check_stmts(stmt.orelse, scope_stack, module_names, function_names)
        elif isinstance(stmt, ast.If):
            _check_expr(stmt.test, scope_stack, module_names, function_names)
            _check_stmts(stmt.body, scope_stack, module_names, function_names)
            _check_stmts(stmt.orelse, scope_stack, module_names, function_names)
        elif isinstance(stmt, ast.Return):
            if stmt.value is not None:
                _check_expr(stmt.value, scope_stack, module_names, function_names)
        elif isinstance(stmt, ast.Expr):
            _check_expr(stmt.value, scope_stack, module_names, function_names)
        elif isinstance(stmt, (ast.Pass, ast.Break, ast.Continue)):
            continue
        elif isinstance(stmt, ast.While):
            _reject("禁止 while 循环；只允许对有长度上限的输入做 for 迭代")
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            _reject("禁止 import；首版不开放任何模块（math/第三方库默认关闭）")
        elif isinstance(stmt, (ast.Global, ast.Nonlocal)):
            _reject("禁止 global/nonlocal（全局可变状态不在受限子集内）")
        elif isinstance(stmt, ast.Try):
            _reject(
                "禁止 try/except：bare except 与 except BaseException 一并静态拒绝，"
                "工作量耗尽异常（WorkloadExceeded）不可被候选捕获"
            )
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            _reject("禁止 with 语句")
        elif isinstance(stmt, ast.Raise):
            _reject("候选不得主动抛异常；无法评分时返回 ABSTAIN")
        elif isinstance(stmt, ast.Assert):
            _reject("禁止 assert（优化模式下行为不一致）")
        elif isinstance(stmt, ast.Delete):
            _reject("禁止 del")
        elif isinstance(stmt, ast.AnnAssign):
            _reject("暂不支持带注解赋值")
        elif isinstance(stmt, ast.ClassDef):
            _reject("禁止定义类；受限子集只有纯函数")
        else:
            _reject("不允许的语句 {0}".format(type(stmt).__name__))


def _check_function(
    fn: ast.FunctionDef,
    scope_stack: List[Set[str]],
    module_names: Set[str],
    function_names: Set[str],
) -> None:
    args = fn.args
    if args.vararg or args.kwarg:
        _reject("函数 {0} 不允许 *args/**kwargs".format(fn.name))
    if args.defaults or any(item is not None for item in args.kw_defaults):
        _reject("函数 {0} 不允许默认参数（默认值在模块装载期未插桩求值）".format(fn.name))
    all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    for item in all_args:
        _valid_name(item.arg, "参数名")
        if item.annotation is not None:
            _reject("函数 {0} 不允许参数注解（注解在装载期未插桩求值）".format(fn.name))
    if fn.returns is not None:
        _reject("函数 {0} 不允许返回注解".format(fn.name))
    if fn.decorator_list:
        _reject("函数 {0} 不允许装饰器".format(fn.name))
    scope = {item.arg for item in all_args}
    # 扁平收集本函数（含嵌套函数名、推导式目标）绑定的名字：静态检查是
    # 安全网，漏绑名字在运行期以 NameError 使整批失效，不会扩大权限。
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            scope.add(node.id)
        elif isinstance(node, ast.arg):
            scope.add(node.arg)
        elif isinstance(node, ast.FunctionDef):
            scope.add(node.name)
    _check_stmts(fn.body, scope_stack + [scope], module_names, function_names)


def _check_score_actions_signature(fn: ast.FunctionDef) -> None:
    args = fn.args
    positional = list(args.posonlyargs) + list(args.args)
    if len(positional) != 1 or positional[0].arg != "view":
        _reject("score_actions 必须恰好接受一个名为 view 的位置参数")
    if args.kwonlyargs:
        _reject("score_actions 不允许关键字专属参数")


def _check_recursion(tree: ast.Module, function_names: Set[str]) -> None:
    """拒绝（含相互）递归：函数名引用图出现环即静态拒绝。"""

    edges: Dict[str, Set[str]] = {name: set() for name in function_names}

    def walk(node: ast.AST, owner: str) -> None:
        if isinstance(node, ast.FunctionDef):
            # 嵌套函数体内的引用归嵌套函数自身（同名时按名归并，保守处理）
            collect(node)
            return
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in function_names
        ):
            edges[owner].add(node.id)
        for child in ast.iter_child_nodes(node):
            walk(child, owner)

    def collect(fn: ast.FunctionDef) -> None:
        for child in ast.iter_child_nodes(fn):
            walk(child, fn.name)

    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef):
            collect(stmt)

    visiting: Set[str] = set()
    done: Set[str] = set()

    def visit(name: str, path: List[str]) -> None:
        if name in done:
            return
        if name in visiting:
            cycle = path[path.index(name):] + [name]
            _reject("检测到递归调用：{0}".format(" -> ".join(cycle)))
        visiting.add(name)
        for nxt in sorted(edges[name]):
            visit(nxt, path + [nxt])
        visiting.discard(name)
        done.add(name)

    for name in sorted(edges):
        visit(name, [name])


def static_check(source: str) -> ast.Module:
    """解析并静态检查候选源码；通过时返回模块 AST（未插桩）。"""
    try:
        tree = ast.parse(source, filename="<action_value-candidate>")
    except SyntaxError as exc:
        raise StaticCheckError("候选源码语法错误：{0}".format(exc)) from exc
    if not isinstance(tree, ast.Module):  # pragma: no cover - ast.parse 保证
        _reject("候选必须是模块级源码")
    module_names: Set[str] = set()
    functions: List[ast.FunctionDef] = []
    function_names: Set[str] = set()
    for index, stmt in enumerate(tree.body):
        if index == 0 and _is_docstring(stmt):
            continue
        if isinstance(stmt, ast.FunctionDef):
            _valid_name(stmt.name, "函数名")
            if stmt.name in function_names or stmt.name in module_names:
                _reject("重复定义 {0}".format(stmt.name))
            function_names.add(stmt.name)
            functions.append(stmt)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if not isinstance(target, ast.Name):
                    _reject("模块级赋值目标必须是简单名字")
                _valid_name(target.id, "模块常量名")
                if target.id in function_names or target.id in module_names:
                    _reject("重复绑定 {0}".format(target.id))
                module_names.add(target.id)
            _check_constant_expr(stmt.value)
        else:
            _reject(
                "模块级只允许 docstring、函数定义与常量赋值，得到 {0}".format(
                    type(stmt).__name__
                )
            )
    if "score_actions" not in function_names:
        _reject("缺少模块级导出函数 score_actions(view)")
    _check_score_actions_signature(
        next(fn for fn in functions if fn.name == "score_actions")
    )
    for fn in functions:
        _check_function(fn, [], module_names, function_names)
    _check_recursion(tree, function_names)
    return tree


# ---------------------------------------------------------------------------
# 插桩重写
# ---------------------------------------------------------------------------

_AV_PASS = "_av_pass"
_AV_BIN = "_av_bin"
_AV_UN = "_av_un"
_AV_ITER = "_av_iter"
_AV_SEQ_METHOD = "_av_seq_method"
_AV_WRAP_LIST = "_av_wrap_list"
_AV_WRAP_SET = "_av_wrap_set"
_AV_WRAP_DICT = "_av_wrap_dict"

_INSTRUMENT_NAMES = frozenset(
    {_AV_PASS, _AV_BIN, _AV_UN, _AV_ITER, _AV_WRAP_LIST, _AV_WRAP_SET, _AV_WRAP_DICT}
)


class _Instrumentor(ast.NodeTransformer):
    """把静态检查通过的候选 AST 重写为计数插桩产物。

    插桩点：每个调用点/推导式元素/f-string（_av_pass 计 1）、每个二元与
    一元运算（_av_bin/_av_un 计 1 并做数值守卫）、每个 for 迭代项
    （_av_iter 逐项计费）、每个 list/set/dict 字面量与推导式（包装为受
    限集合并按长度计费）、增量赋值（改写为守卫加法）。执行器侧的这些
    助手属于可信第一方代码，不受受限子集约束。
    """

    def _wrap(self, name: str, node: ast.AST, *extra: ast.AST) -> ast.Call:
        return ast.copy_location(
            ast.Call(
                func=ast.Name(id=name, ctx=ast.Load()),
                args=[node, *extra],
                keywords=[],
            ),
            node,
        )

    def visit_Call(self, node: ast.Call) -> ast.AST:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("count", "index"):
            # S1：.count/.index 在真实对象上线性遍历——改走按长度计费的方法包装。
            self.generic_visit(node)
            return ast.copy_location(
                ast.Call(
                    func=ast.Name(id=_AV_SEQ_METHOD, ctx=ast.Load()),
                    args=[func.value, ast.Constant(func.attr), *node.args],
                    keywords=list(node.keywords),
                ),
                node,
            )
        self.generic_visit(node)
        return self._wrap(_AV_PASS, node)

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        op_name = _BIN_OPS[type(node.op)]
        return self._wrap(_AV_BIN, node.left, ast.Constant(op_name), node.right)

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        # x op= v 重写为 x = _av_bin(x, op, v)；静态检查保证目标是简单名字。
        replacement = ast.Assign(
            targets=[ast.Name(id=node.target.id, ctx=ast.Store())],
            value=ast.BinOp(
                left=ast.Name(id=node.target.id, ctx=ast.Load()),
                op=node.op,
                right=node.value,
            ),
        )
        return self.visit(replacement)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        op_name = _UNARY_OPS[type(node.op)]
        return self._wrap(_AV_UN, ast.Constant(op_name), node.operand)

    def visit_For(self, node: ast.For) -> ast.AST:
        self.generic_visit(node)
        node.iter = self._wrap(_AV_ITER, node.iter)
        return node

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        self.generic_visit(node)
        return self._wrap(_AV_PASS, node)

    def visit_ListComp(self, node: ast.ListComp) -> ast.AST:
        self.generic_visit(node)
        node.elt = self._wrap(_AV_PASS, node.elt)
        return self._wrap(_AV_WRAP_LIST, node)

    def visit_SetComp(self, node: ast.SetComp) -> ast.AST:
        self.generic_visit(node)
        node.elt = self._wrap(_AV_PASS, node.elt)
        return self._wrap(_AV_WRAP_SET, node)

    def visit_DictComp(self, node: ast.DictComp) -> ast.AST:
        self.generic_visit(node)
        node.key = self._wrap(_AV_PASS, node.key)
        node.value = self._wrap(_AV_PASS, node.value)
        return self._wrap(_AV_WRAP_DICT, node)

    def visit_List(self, node: ast.List) -> ast.AST:
        self.generic_visit(node)
        return self._wrap(_AV_WRAP_LIST, node)

    def visit_Set(self, node: ast.Set) -> ast.AST:
        self.generic_visit(node)
        return self._wrap(_AV_WRAP_SET, node)

    def visit_Dict(self, node: ast.Dict) -> ast.AST:
        self.generic_visit(node)
        return self._wrap(_AV_WRAP_DICT, node)


# ---------------------------------------------------------------------------
# 运行时计费与受限容器
# ---------------------------------------------------------------------------


class _Meter:
    """单次执行的操作计数器；超限抛 WorkloadExceeded。"""

    __slots__ = ("used", "limit")

    def __init__(self, limit: int) -> None:
        self.used = 0
        self.limit = limit

    def charge(self, count: int = 1) -> None:
        self.used += count
        if self.used > self.limit:
            raise WorkloadExceeded(
                "计数操作超限：已用 {0}，上限 {1}".format(self.used, self.limit)
            )


class _AvList(list):
    """受限局部列表：append 与切片结果都受集合上限约束（调用点已按次计费）。"""

    __slots__ = ("_cap",)

    def __init__(self, items: Any = (), cap: int = MAX_LOCAL_COLLECTION_SIZE) -> None:
        super().__init__(items)
        self._cap = cap

    def append(self, item: Any) -> None:
        if len(self) >= self._cap:
            raise WorkloadExceeded("局部集合超过 {0} 项上限".format(self._cap))
        super().append(item)

    def __getitem__(self, item: Any) -> Any:
        result = super().__getitem__(item)
        # 切片产生新列表：仍包装为受限列表，防止绕开集合上限继续增长。
        if isinstance(result, list):
            return _AvList(result, self._cap)
        return result


class _AvSet(set):
    """受限局部集合：add 只做集合上限检查。"""

    __slots__ = ("_cap",)

    def __init__(self, items: Any = (), cap: int = MAX_LOCAL_COLLECTION_SIZE) -> None:
        super().__init__(items)
        self._cap = cap

    def add(self, item: Any) -> None:
        if len(self) >= self._cap:
            raise WorkloadExceeded("局部集合超过 {0} 项上限".format(self._cap))
        super().add(item)


class _AvDict(dict):
    """受限局部字典：下标写入做集合上限检查（静态检查已拒绝输入侧写入）。"""

    __slots__ = ("_cap",)

    def __init__(self, items: Any = (), cap: int = MAX_LOCAL_COLLECTION_SIZE) -> None:
        super().__init__(items)
        self._cap = cap

    def __setitem__(self, key: Any, value: Any) -> None:
        if key not in self and len(self) >= self._cap:
            raise WorkloadExceeded("局部集合超过 {0} 项上限".format(self._cap))
        super().__setitem__(key, value)


_RT_OPS: Dict[str, Callable[[Any, Any], Any]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
    "<<": operator.lshift,
    ">>": operator.rshift,
    "&": operator.and_,
    "|": operator.or_,
    "^": operator.xor,
}


def _make_runtime(meter: _Meter) -> Dict[str, Any]:
    """构造受限运行时：插桩助手 + 白名单内建的计费包装。

    计费规范（合同 limits.metering_rules）：每个调用点计 1（_av_pass），
    白名单内建按各自规范再计——len/min/max/abs/round/int/float/bool/range
    计 1；sum/sorted/all/any/map/filter/enumerate/reversed/zip 与容器构造
    按输入长度保守计费；禁止不计费的批量计算。
    """
    cap = MAX_LOCAL_COLLECTION_SIZE

    def seq_len(value: Any) -> Optional[int]:
        try:
            return len(value)
        except TypeError:
            return None

    def input_cost(value: Any) -> int:
        length = seq_len(value)
        return length if length is not None else UNSIZEED_INPUT_COST

    def collection_exceed() -> None:
        raise WorkloadExceeded("局部集合超过 {0} 项上限".format(cap))

    def bounded_items(value: Any, what: str) -> List[Any]:
        """S1 修复：消费可迭代对象的内建统一“先限长（≤cap）再按元素计费”。

        有长度输入：len > cap 即拒绝（最大输入边界），否则按长度计费并
        物化；无长度输入：逐项计费物化（受 cap 约束）。真实遍历只发生在
        本函数内，候选无法再拿到“只计 1 次调用费却遍历百万项”的通道。
        """
        length = seq_len(value)
        if length is None:
            return materialize(value)
        if length > cap:
            raise WorkloadExceeded(
                "{0} 输入长度 {1} 超过 {2} 项上限".format(what, length, cap)
            )
        meter.charge(max(1, length))
        return list(value)

    def num_guard(value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            if value > MAX_INT_MAGNITUDE or value < -MAX_INT_MAGNITUDE:
                raise WorkloadExceeded(
                    "整数结果超过 63 位界限：{0}".format(value)
                )
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise WorkloadExceeded("非有限浮点结果（NaN/Inf）使整批失效")
            return value
        return value

    def materialize(iterable: Any) -> List[Any]:
        out: List[Any] = []
        for item in iterable:
            meter.charge(1)
            if len(out) >= cap:
                collection_exceed()
            out.append(item)
        return out

    def av_pass(value: Any) -> Any:
        meter.charge(1)
        if type(value) is str and len(value) > MAX_STRING_CHARS:
            raise WorkloadExceeded(
                "字符串超过 {0} 字符上限".format(MAX_STRING_CHARS)
            )
        return value

    def repeat_guard(seq: Any, times: int) -> None:
        limit = MAX_STRING_CHARS if isinstance(seq, str) else cap
        if times > 0 and len(seq) * times > limit:
            raise WorkloadExceeded(
                "序列重复将超过 {0} 上限".format(limit)
            )

    def av_bin(a: Any, op_name: str, b: Any) -> Any:
        meter.charge(1)
        if op_name == "**":
            if isinstance(b, bool) or not isinstance(b, int) or b < 0 or b > MAX_POWER_EXPONENT:
                raise WorkloadExceeded("** 只允许 0—{0} 的整数指数".format(MAX_POWER_EXPONENT))
        if op_name in ("<<", ">>"):
            if isinstance(b, bool) or not isinstance(b, int) or b < 0 or b > MAX_SHIFT_BITS:
                raise WorkloadExceeded("移位量超过 {0} 位上限".format(MAX_SHIFT_BITS))
        if op_name == "*":
            if isinstance(a, (list, tuple, str)) and isinstance(b, int) and not isinstance(b, bool):
                repeat_guard(a, b)
            elif isinstance(b, (list, tuple, str)) and isinstance(a, int) and not isinstance(a, bool):
                repeat_guard(b, a)
        result = _RT_OPS[op_name](a, b)
        if isinstance(result, str) and len(result) > MAX_STRING_CHARS:
            raise WorkloadExceeded("字符串超过 {0} 字符上限".format(MAX_STRING_CHARS))
        if isinstance(result, (list, tuple)):
            if len(result) > cap:
                collection_exceed()
            if isinstance(result, list):
                return _AvList(result, cap)
            return result
        return num_guard(result)

    def av_un(op_name: str, value: Any) -> Any:
        meter.charge(1)
        if op_name == "not":
            return not value
        if op_name == "-":
            return num_guard(-value)
        if op_name == "+":
            return num_guard(+value)
        return num_guard(~value)

    def av_iter(iterable: Any) -> Any:
        for item in iterable:
            meter.charge(1)
            yield item

    def av_seq_method(obj: Any, name: str, *args: Any, **kwargs: Any) -> Any:
        """S1：.count/.index 按被查序列长度计费并限长（真实遍历只发生在这里）。"""
        length = seq_len(obj)
        limit = MAX_STRING_CHARS if isinstance(obj, str) else cap
        if length is not None:
            if length > limit:
                raise WorkloadExceeded(
                    ".{0} 输入长度 {1} 超过 {2} 上限".format(name, length, limit)
                )
            meter.charge(max(1, length))
        else:
            meter.charge(1)
        return getattr(obj, name)(*args, **kwargs)

    def wrap_list(value: Any) -> Any:
        length = seq_len(value)
        if length is None:
            items = materialize(value)
        else:
            if length > cap:
                collection_exceed()
            items = list(value)
        meter.charge(max(1, len(items)))
        return _AvList(items, cap)

    def wrap_set(value: Any) -> Any:
        length = seq_len(value)
        if length is None:
            items = materialize(value)
        else:
            if length > cap:
                collection_exceed()
            items = list(value)
        meter.charge(max(1, len(items)))
        return _AvSet(items, cap)

    def wrap_dict(value: Any) -> Any:
        length = seq_len(value)
        if length is None:
            pairs = materialize(value)
            data = dict(pairs)
        else:
            if length > cap:
                collection_exceed()
            data = dict(value)
        meter.charge(max(1, len(data)))
        return _AvDict(data, cap)

    # —— 白名单内建的计费包装 ——

    def b_len(obj: Any) -> int:
        meter.charge(1)
        return len(obj)

    def b_min(*args: Any, **kwargs: Any) -> Any:
        # S1：单参数形式先限长再按元素计费（min(range(N)) 不再免费遍历 N 项）；
        # 多参数形式比较参数本身，按参数个数计费。
        if len(args) == 1:
            items = bounded_items(args[0], "min()")
            return num_guard(min(items, **kwargs))
        meter.charge(max(1, len(args)))
        return num_guard(min(*args, **kwargs))

    def b_max(*args: Any, **kwargs: Any) -> Any:
        if len(args) == 1:
            items = bounded_items(args[0], "max()")
            return num_guard(max(items, **kwargs))
        meter.charge(max(1, len(args)))
        return num_guard(max(*args, **kwargs))

    def b_abs(value: Any) -> Any:
        meter.charge(1)
        return num_guard(abs(value))

    def b_round(*args: Any, **kwargs: Any) -> Any:
        meter.charge(1)
        return num_guard(round(*args, **kwargs))

    def b_int(*args: Any, **kwargs: Any) -> Any:
        meter.charge(1)
        return num_guard(int(*args, **kwargs))

    def b_float(value: Any) -> float:
        meter.charge(1)
        result = float(value)
        if not math.isfinite(result):
            raise WorkloadExceeded("float() 转换结果非有限，整批失效")
        return result

    def b_bool(*args: Any, **kwargs: Any) -> bool:
        meter.charge(1)
        return bool(*args, **kwargs)

    def b_range(*args: Any) -> range:
        # S1：range 本身按长度计费并禁止超大构造——len(range(...)) 即元素数，
        # 构造 range(1000000) 立即计满预算并抛 WorkloadExceeded，后续任何
        # 内建/循环都不可能再从超大 range 获得不计费遍历。
        for item in args:
            if isinstance(item, bool) or not isinstance(item, int):
                raise WorkloadExceeded("range 参数必须是 int")
        result = range(*args)
        meter.charge(max(1, len(result)))
        return result

    def b_sum(iterable: Any, *start: Any) -> Any:
        items = bounded_items(iterable, "sum()")
        return num_guard(sum(items, *start))

    def b_sorted(iterable: Any, **kwargs: Any) -> Any:
        items = bounded_items(iterable, "sorted()")
        return _AvList(sorted(items, **kwargs), cap)

    def b_all(iterable: Any) -> bool:
        return all(bounded_items(iterable, "all()"))

    def b_any(iterable: Any) -> bool:
        return any(bounded_items(iterable, "any()"))

    def b_enumerate(iterable: Any, *start: Any) -> Any:
        # S1：物化为受限列表（不再返回惰性 enumerate），长度受限、按元素计费。
        items = bounded_items(iterable, "enumerate()")
        return _AvList(list(enumerate(items, *start)), cap)

    def b_reversed(seq: Any) -> Any:
        items = bounded_items(seq, "reversed()")
        return _AvList(items[::-1], cap)

    def b_zip(*seqs: Any) -> Any:
        materialized = [bounded_items(seq, "zip()") for seq in seqs]
        items = list(zip(*materialized))
        if len(items) > cap:
            collection_exceed()
        return _AvList(items, cap)

    def b_map(fn: Any, *seqs: Any) -> Any:
        materialized = [bounded_items(seq, "map()") for seq in seqs]
        items = list(map(fn, *materialized))
        if len(items) > cap:
            collection_exceed()
        return _AvList(items, cap)

    def b_filter(fn: Any, seq: Any) -> Any:
        items = bounded_items(seq, "filter()")
        picked = list(filter(fn, items))
        if len(picked) > cap:
            collection_exceed()
        return _AvList(picked, cap)

    def b_tuple(iterable: Any = ()) -> tuple:
        length = seq_len(iterable)
        if length is None:
            items = materialize(iterable)
        else:
            if length > cap:
                collection_exceed()
            items = list(iterable)
        meter.charge(max(1, len(items)))
        return tuple(items)

    def b_list(iterable: Any = ()) -> Any:
        return wrap_list(iterable)

    def b_dict(*args: Any, **kwargs: Any) -> Any:
        source = args[0] if args else ()
        return wrap_dict(dict(source, **kwargs) if args else dict(**kwargs))

    def b_set(iterable: Any = ()) -> Any:
        return wrap_set(iterable)

    def b_frozenset(iterable: Any = ()) -> frozenset:
        length = seq_len(iterable)
        if length is None:
            items = materialize(iterable)
        else:
            if length > cap:
                collection_exceed()
            items = list(iterable)
        meter.charge(max(1, len(items)))
        return frozenset(items)

    runtime: Dict[str, Any] = {
        _AV_PASS: av_pass,
        _AV_BIN: av_bin,
        _AV_UN: av_un,
        _AV_ITER: av_iter,
        _AV_SEQ_METHOD: av_seq_method,
        _AV_WRAP_LIST: wrap_list,
        _AV_WRAP_SET: wrap_set,
        _AV_WRAP_DICT: wrap_dict,
        "len": b_len,
        "min": b_min,
        "max": b_max,
        "abs": b_abs,
        "sum": b_sum,
        "sorted": b_sorted,
        "reversed": b_reversed,
        "enumerate": b_enumerate,
        "zip": b_zip,
        "range": b_range,
        "round": b_round,
        "int": b_int,
        "float": b_float,
        "bool": b_bool,
        "all": b_all,
        "any": b_any,
        "tuple": b_tuple,
        "list": b_list,
        "dict": b_dict,
        "set": b_set,
        "frozenset": b_frozenset,
        "map": b_map,
        "filter": b_filter,
    }
    return runtime


# ---------------------------------------------------------------------------
# 执行器
# ---------------------------------------------------------------------------


class ActionValueExecutor:
    """静态检查、插桩编译与进程内受限执行一个 score_actions 候选。

    用法：executor = ActionValueExecutor(source)；executor.score(view) 返回
    已通过完整性验证的 ScoreBatch，或抛 WorkloadExceeded（限额）/ ValueError
    （输出合同失败），均由调用方整批降级。last_operation_count 记录最近
    一次执行的计数操作数，用于计费测试与审计。
    """

    def __init__(
        self,
        source: str,
        *,
        name: str = "<action_value_candidate>",
        max_operations: int = MAX_COUNTED_OPERATIONS,
    ) -> None:
        if not isinstance(source, str):
            raise StaticCheckError("候选源码必须是字符串")
        self.name = str(name)
        self.source = source
        encoded = source.encode("utf-8")
        if len(encoded) > MAX_SOURCE_BYTES:
            raise StaticCheckError(
                "候选源码 {0} 字节超过 {1} 字节上限".format(len(encoded), MAX_SOURCE_BYTES)
            )
        tree = static_check(source)
        self._meter = _Meter(int(max_operations))
        instrumented = _Instrumentor().visit(tree)
        ast.fix_missing_locations(instrumented)
        self._code = compile(
            instrumented, "<action_value:{0}>".format(self.name), "exec"
        )
        self._runtime = _make_runtime(self._meter)
        namespace: Dict[str, Any] = {"__builtins__": {}}
        namespace.update(self._runtime)
        # 模块级只有常量赋值与函数定义；静态检查已排除任意顶层执行。
        exec(self._code, namespace)
        fn = namespace.get("score_actions")
        if not callable(fn):  # pragma: no cover - 静态检查已保证
            raise StaticCheckError("score_actions 未定义或不可调用")
        self._fn: Callable[[Mapping[str, Any]], Mapping[str, Any]] = fn
        # S1：装载即核验并快照模块级绑定——只允许函数与不可变常量；
        # score() 每次执行后逐项复核，杜绝跨调用可变共享状态。
        self._namespace = namespace
        self._module_snapshot = self._snapshot_module_bindings(namespace)
        self.last_operation_count: Optional[int] = None

    @staticmethod
    def _snapshot_module_bindings(
        namespace: Dict[str, Any]
    ) -> Dict[str, Any]:
        """装载期快照模块级绑定；可变类型直接拒绝（静态检查的双重保险）。"""
        snapshot: Dict[str, Any] = {}
        for name, value in namespace.items():
            if name == "__builtins__" or name.startswith("_av"):
                continue
            if callable(value):
                snapshot[name] = ("fn", value)
                continue
            if value is None or isinstance(value, (str, int, float, bool, tuple, frozenset)):
                snapshot[name] = ("const", value)
                continue
            raise StaticCheckError(
                "模块级绑定 {0!r} 是可变类型 {1}：跨调用状态被拒绝".format(
                    name, type(value).__name__
                )
            )
        return snapshot

    def _verify_no_shared_mutation(self) -> None:
        """执行后复核模块命名空间无残留变更（跨调用状态检测）。"""
        for name, (kind, original) in self._module_snapshot.items():
            current = self._namespace.get(name, None)
            if kind == "fn":
                if current is not original:
                    raise WorkloadExceeded(
                        "模块级函数 {0!r} 被重绑定：跨调用状态被拒绝".format(name)
                    )
            elif current != original or type(current) is not type(original):
                raise WorkloadExceeded(
                    "模块级常量 {0!r} 在执行后发生变化：跨调用状态被拒绝".format(name)
                )

    def score(self, view: ScoringView) -> ScoreBatch:
        """受限执行 score_actions 并验证完整返回；失败整批抛错，不部分补零。"""
        if not isinstance(view, ScoringView):
            raise ValueError("ActionValueExecutor.score 需要 ScoringView 输入")
        self._meter.used = 0
        try:
            # WorkloadExceeded 是 BaseException：骨架内的 except Exception
            # 不会吞掉它，原样上抛给调用方做整批降级。
            return run_scoring_skeleton(view, self._fn)
        finally:
            self.last_operation_count = self._meter.used
            self._verify_no_shared_mutation()


# ---------------------------------------------------------------------------
# 身份
# ---------------------------------------------------------------------------


def _types_digest_material() -> Dict[str, Any]:
    """ScoringView 一族类型的字段摘要；进入第一方传递依赖摘要。"""
    material: Dict[str, Any] = {}
    for cls in (
        ScoringView,
        ActionView,
        CompetitionView,
        AnalysisProfileView,
        ReferenceFeature,
        ActionScore,
        ScoreBatch,
    ):
        material[cls.__name__] = [item.name for item in dataclass_fields(cls)]
    material["schema_version"] = SCORING_VIEW_SCHEMA_VERSION
    material["status_values"] = list(STATUS_VALUES)
    return material


def compute_deps_digest(file_contents: Optional[Mapping[str, str]] = None) -> str:
    """第一方传递依赖摘要：结构摘要（白名单/限额/类型）+ 实际文件内容摘要。

    S4 修复：仅靠字段名/常量摘要无法覆盖“只改方法体”的实现变更。离线
    装配层（sitin_gates）读取 FIRST_PARTY_DIGEST_MODULES 列出的实际第一方
    文件与合同 JSON 内容，经 file_contents 注入本函数——任何实现文件的方法
    体改动都会改变内容摘要，从而使旧 candidate_id 与旧准入记录失效
    （identity.recovery_policy）。本模块保持无文件副作用：读文件在离线层。

    传 None 时摘要仅含结构信息（纯策略层默认路径，用于进程内快速对账）；
    真实准入/评估身份必须由离线层注入内容摘要。
    """
    material = {
        "executor_version": EXECUTOR_VERSION,
        "whitelist_builtins": sorted(ALLOWED_BUILTINS),
        "whitelist_methods": sorted(ALLOWED_METHODS),
        "limits": {
            "max_counted_operations": MAX_COUNTED_OPERATIONS,
            "max_local_collection_size": MAX_LOCAL_COLLECTION_SIZE,
            "max_source_bytes": MAX_SOURCE_BYTES,
            "max_trace_bytes": MAX_TRACE_BYTES,
            "max_int_magnitude": MAX_INT_MAGNITUDE,
            "max_power_exponent": MAX_POWER_EXPONENT,
        },
        "view_types": _types_digest_material(),
    }
    if file_contents is not None:
        if not isinstance(file_contents, Mapping):
            raise ValueError("file_contents 必须是映射（模块名 → 文件文本）")
        material["first_party_contents"] = compute_first_party_digest(file_contents)
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


#: 身份闭包覆盖的第一方模块（S4）：类型/投影/策略接线/种子/规则事实接口。
#: 离线装配层按本清单读取实际文件内容；清单本身变化同样改变身份。
FIRST_PARTY_DIGEST_MODULES: Tuple[str, ...] = (
    "hangma_bot.policy.action_value",
    "hangma_bot.policy.action_value_executor",
    "hangma_bot.policy.action_value_policy",
    "hangma_bot.policy.action_value_seeds",
    "hangma_bot.hangma.interface",
    "hangma_bot.hangma.candidate_facts",
    "hangma_bot.hangma.value_analysis",
    "hangma_bot.hangma.progression_payload",
)


def compute_first_party_digest(file_contents: Mapping[str, str]) -> str:
    """对给定第一方文件内容映射计算确定的内容摘要（sha256）。

    键为模块名/文件标识，值为文件全文文本；键排序后规范化序列化，任何
    文件内容的任何改动（含仅改方法体）都会改变摘要。
    """
    if not isinstance(file_contents, Mapping):
        raise ValueError("file_contents 必须是映射（模块名 → 文件文本）")
    normalized = {str(key): str(value) for key, value in file_contents.items()}
    return hashlib.sha256(
        json.dumps(
            normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _canonical_params(params: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise ValueError("params 必须是映射或空")
    try:
        return json.loads(json.dumps(dict(params), ensure_ascii=False, sort_keys=True))
    except TypeError as exc:
        raise ValueError("params 必须可 JSON 序列化：{0}".format(exc)) from exc


def compute_candidate_identity(
    source: str,
    contract_sha256: str,
    params: Optional[Mapping[str, Any]],
    executor_version: str,
    deps_digest: str,
) -> str:
    """按合同 identity.candidate_id_inputs 计算 candidate_id（sha256）。

    覆盖输入：候选种类 action_value_v1、原始/执行源码、有效参数、输入
    输出合同 sha256（本合同文件哈希）、执行器版本、第一方传递依赖摘要；
    骨架/规则/特征/代理版本经 params 与 deps_digest 进入。生成模型、
    提示词、算子、父代等出处信息不进入身份。
    """
    if not isinstance(source, str):
        raise ValueError("source 必须是字符串")
    if not isinstance(contract_sha256, str) or not contract_sha256:
        raise ValueError("contract_sha256 必须是非空字符串")
    if not isinstance(executor_version, str) or not executor_version:
        raise ValueError("executor_version 必须是非空字符串")
    if not isinstance(deps_digest, str) or not deps_digest:
        raise ValueError("deps_digest 必须是非空字符串")
    payload = {
        "candidate_kind": CANDIDATE_KIND,
        "source": source,
        "params": _canonical_params(params),
        "contract_sha256": contract_sha256,
        "executor_version": executor_version,
        "deps_digest": deps_digest,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
