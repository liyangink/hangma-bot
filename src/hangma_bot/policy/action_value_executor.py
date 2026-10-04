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
3b. 工作量边界补齐（2026-09-17 R6/S1 第二次收紧）：
   - **方法取值也包装**：属性读取一律改写为 _av_method（绑定本身是 O(1)，
     取值不计费；真实工作发生在调用时），绑定方法别名（count = values.count
     之后再调用）与直接调用走同一计费通道；无白名单方法仍被静态拒绝。
   - **比较/成员查询/递归数据遍历统一计费**：比较按操作数结构规模计费
     （标量 0、长字符串按 64 字符一段、容器 1+子项），in 按被查序列长度加
     元素结构计费，sorted/min/max 按元素结构与 key 结果计费，切片按结果
     长度计费。
   - **嵌套深度与结构规模在建栈时限制**：结构遍历发现容器深度 >
     MAX_DATA_DEPTH 或单元数 > MAX_DATA_CELLS 即提前拒绝，指数结构
     （(a, a) 重复嵌套）不会再让 CPython 递归比较跑满时间或 C 栈。
   - **分配前校验输出规模**：f-string 与 % 格式化的宽度/精度先解析再拒绝
     （动态格式规范同样按运行时取值解析），序列重复、字符串长度同样先
     检查后分配。
   - **集合迭代确定化**：受限集合与冻结集合固定按插入顺序迭代，集合运算
     结果按左→右顺序重建，跨 PYTHONHASHSEED 的计费与结果一致。
3c. 哈希边界与插桩语义补齐（2026-09-17 R8/N1—N3 第三次收紧）：
   - **原生哈希前置守卫**：字典/集合字面量与推导式、set()/frozenset()/
     dict() 构造、.add（含绑定方法别名与经函数间接调用）与 table[深键]
     查询，一律在进入 CPython 的 C 层哈希**之前**做有界结构检查并计费。
     修复前 `x = (x, x)` 嵌套 16 次的元组作 {x: 1} 的键可正常返回且只计
     36，原生哈希完全在保护之外。
   - **字典/集合字面量先求值成元素流再构造**：字面量与集合推导式不再先建
     原生容器（其迭代顺序与哈希种子有关），改由受限容器按源序插入——
     跨 PYTHONHASHSEED 结果逐字节一致。
   - **sum 只保留数值用途**：`sum(rows, ())` 这类序列起始值做 len(rows)
     次拷贝、最终规模不受单集合上限约束（复审反例 64×128 → 8192 项仅计
     138），在拷贝前直接拒绝；`sum(rows)` 与数值起始值仍允许。
   - **链式比较临时名与候选名隔离**：`a < b < c` 的插桩 lambda 参数改为
     `_avc{i}/_avt{i}`。修复前用 `x0/t0` 作参数名，会捕获候选自身的同名
     局部变量（`x0 = 100; 0 < 1 < x0` 原生 True、受限执行器得 False）。

3e. 分派与返回值口径补齐（2026-09-17 R9/S1b 第五次收紧）：
   - **集合式字典视图展开**：dict_keys/dict_items/dict_values 按底层键、或
     键+值逐项展开，计入同一单元上限（修复前它们不是 dict/tuple/list/set/
     frozenset 实例，白名单分派判 0 单元，原生逐项比较完全在保护之外：
     128×4096 的 items 视图比较实测 37,541 ops / 1.672 s 正常返回）。
   - **兜底不再默认放行**：有 len() 按 max(1,len) 计、可调用计 1、其余未知
     类型按 MAX_DATA_CELLS+1 计费（默认预算下计费通道必然拒绝）。
   - **候选返回值计费**：score() 在骨架做任何递归校验/序列化之前，对候选
     返回值按同一套有界结构遍历逐节点计费（共享引用按出现次数展开）；
     trace 通道实测由「24 ops → 201 MB 序列化 / 406 MB 峰值」变为提前拒绝。
   - **字符串产出按 64 字符一段计费**：拼接、重复、f-string 与 % 格式化的
     结果长度计费（短结果 < 64 字符仍为 0，热路径不变）。
   - **ScoreBatch 合同层序列化前预判**（action_value.py）：递归校验与
     json.dumps 之前用有界遍历给出字节下界，超 MAX_TRACE_BYTES 立即拒绝。

3d. 结构单元口径补齐（2026-09-17 R9/S1 第四次收紧）：
   - **结构遍历对每个展开的节点计费**：容器节点与标量叶同口径各计 1 个
     单元（字符串按 64 字符一段、至少 1 段），限额同样按单元数判定。
     修复前只给容器与长字符串计数：`row=(1,)*1024`、`key=(row,)*256`、
     `{key: 1}` 展开 262144 个标量叶、超过 MAX_DATA_CELLS=131072，却只算
     262 operations 正常返回，而 CPython 的元组哈希仍逐项访问这些叶。
   - **共享引用按出现次数累积**：同一对象被引用 n 次就遍历 n 次（原生
     哈希与比较都不去重），不做 id 记忆化。
   - **守卫自身有界**：容器出栈时先按「每个子节点至少 1 单元」预判上限，
     超限立即拒绝，入栈量与遍历量都不超过 MAX_DATA_CELLS。
   - **热路径不变**：顶层标量与短字符串走常数快路径，标量比较、短键
     哈希与字典键查询的计费量级与 /4 一致。

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
import re
from collections.abc import ItemsView, KeysView, ValuesView
from dataclasses import dataclass, fields as dataclass_fields
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
MAX_SUPPORTED_LOCAL_COLLECTION_SIZE = 16_384  # 可信研究配置可声明的单集合硬上限；旧默认不变
MAX_SOURCE_BYTES = 65_536  # 候选源码字节上限
MAX_INT_MAGNITUDE = 2**63 - 1  # 运行时整数幅度界限（拒绝大整数膨胀）
MAX_POWER_EXPONENT = 4  # ** 仅允许 0—4 的整数常量指数
MAX_SHIFT_BITS = 256  # 移位量上限，防止一次性构造超大整数
MAX_STRING_CHARS = 65_536  # 单个字符串长度上限（拼接/重复/格式化前检查）
UNSIZEED_INPUT_COST = 4_096  # 无长度输入的保守计费（正常路径输入均有长度）
MAX_DATA_DEPTH = 12  # 结构嵌套深度上限（比较/成员/格式化/排序前检查）
MAX_DATA_CELLS = 131_072  # 单次结构遍历的单元上限（标量叶与容器节点同口径各计 1）
_STRING_COST_CHUNK = 64  # 长字符串按 64 字符一段进入结构代价（短键增量为 0）
#: 结构代价为 0 的标量类型（快路径；其余非容器类型同样返回 0）。
_SCALAR_COST_TYPES = frozenset({int, float, bool, type(None)})

# 2026-09-17 R1(S1)：迭代入口全面按元素计费、range 按长度计费、模块级
# 仅不可变常量、跨调用无状态校验——计费语义变更，版本 /1 → /2，旧
# candidate_id 与旧准入记录随之失效（identity.recovery_policy 预期行为）。
# 2026-09-17 R6(S1)：方法取值/绑定方法别名、比较与成员查询、递归数据
# 遍历纳入计费，新增嵌套深度与结构规模上限，格式宽度/精度改为分配前
# 校验，集合迭代确定化——计费与语义再次变更，版本 /2 → /3；旧候选
# 在旧计费下的准入结论不再有效（必须按新版本重算身份与准入）。
# 2026-09-17 R8(N1—N3)：原生哈希前置守卫（字典/集合字面量、推导式、
# set/frozenset/dict 构造、.add 与深键查询）、序列起始值求和拒绝、
# 字面量与推导式改为确定元素流构造、链式比较临时名隔离——计费与语义
# 第三次变更，版本 /3 → /4；旧 candidate_id 与旧准入记录随之失效。
# 2026-09-17 R9(S1)：结构遍历改为**每个展开节点（含标量叶）各计 1 个单元**、
# 容器与标量叶同口径限额、共享引用按出现次数累积——宽而浅的共享结构不再
# 只算容器数（反例 row=(1,)*1024、key=(row,)*256 由 262 operations 放行
# 改为哈希前拒绝）；守卫自身入栈/遍历量有界。计费与语义第四次变更，
# 版本 /4 → /5；旧 candidate_id、旧准入记录与旧面板身份随之失效。
# 2026-09-17 R9/S1b（独立对抗性验证收口）：分派不再默认放行——
#   dict_keys/dict_items/dict_values 视图按底层键值展开（第三形状反例：
#   128×4096 的 items 视图比较 37,541 operations / 1.672 s 正常返回）；
#   未知类型改保守兜底（有 len 按长度、可调用计 1、其余按上限+1 → 计费通道
#   必然拒绝）；候选**返回值**按同一结构口径计费（trace 通道修复前 24
#   operations 触发 201 MB 序列化）；字符串产出按 64 字符一段计费（拼接/
#   重复/格式化，修复前 90,005 ops 可搬 983 MB）。计费与语义第五次变更，
#   版本 /5 → /6；旧 candidate_id、旧准入记录与旧面板身份随之失效。
EXECUTOR_VERSION = "action-value-executor/6"

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

#: 比较运算符 → 运行时名（R6/S1：比较一律插桩为 _av_cmp）。
_CMP_NAMES: Dict[type, str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.In: "in",
    ast.NotIn: "not in",
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
_AV_CMP = "_av_cmp"
_AV_METHOD = "_av_method"
_AV_FVALUE = "_av_fvalue"
_AV_SUB = "_av_sub"
_AV_WRAP_LIST = "_av_wrap_list"
_AV_WRAP_DICT = "_av_wrap_dict"
#: R8/N1—N3：字面量/推导式的确定化构造与键守卫（原生哈希之前）。
_AV_SET_LIT = "_av_set_lit"
_AV_DICT_LIT = "_av_dict_lit"
_AV_KEY = "_av_key"

_INSTRUMENT_NAMES = frozenset(
    {
        _AV_PASS,
        _AV_BIN,
        _AV_UN,
        _AV_ITER,
        _AV_CMP,
        _AV_METHOD,
        _AV_FVALUE,
        _AV_SUB,
        _AV_WRAP_LIST,
        _AV_WRAP_DICT,
        _AV_SET_LIT,
        _AV_DICT_LIT,
        _AV_KEY,
    }
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
        # R6/S1：方法取值已在 visit_Attribute 包装为计费可调用对象，调用点
        # 只需按“调用一次”计 1；.count/.index 的线性扫描计费在被包装的
        # 可调用对象里完成，别名与直接调用不再有区别。
        self.generic_visit(node)
        return self._wrap(_AV_PASS, node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        """R6/S1：属性（方法）取值统一包装为计费可调用对象。

        修复前只包装 .count/.index 的**直接调用**形态：候选先写
        `count = values.count` 再调用 `count(x)`，真实线性扫描发生在被绑定的
        C 方法里，计费完全绕过。这里把所有白名单只读方法取值改写成
        `_av_method(obj, name)`，返回的可调用对象在每次调用时按方法规范计费。
        静态检查已保证属性名在 ALLOWED_METHODS 内，因此本改写不放宽权限。
        """
        self.generic_visit(node)
        return ast.copy_location(
            ast.Call(
                func=ast.Name(id=_AV_METHOD, ctx=ast.Load()),
                args=[node.value, ast.Constant(node.attr)],
                keywords=[],
            ),
            node,
        )

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        """R6/S1：切片是批量拷贝——按结果长度计费（下标取值 O(1)，不计）。"""
        self.generic_visit(node)
        return ast.copy_location(
            ast.Call(
                func=ast.Name(id=_AV_SUB, ctx=ast.Load()),
                args=[node.value, node.slice],
                keywords=[],
            ),
            node,
        )

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        """R6/S1：比较运算统一计费，并按操作数结构规模计费。

        修复前 ast.Compare 完全不插桩：`a == b` 的递归结构比较在 C 层执行，
        16 层重复嵌套元组（65,536 个叶）只计 35。链式比较 a < b < c 改写为
        嵌套 lambda：每个操作数只求值一次，且保持 Python 的短路语义（右侧
        操作数在前一次比较为假时不被求值）。

        R8/N2：lambda 参数名必须是候选**写不出来**的名字（静态检查拒绝一切
        下划线开头标识符），否则会捕获候选自身的同名局部变量：修复前用
        `x0/t0`，候选写 `x0 = 100; 0 < 1 < x0` 时第二个比较读到 lambda
        参数 x0(=0)，原生 True 变成受限执行器的 False。
        """
        self.generic_visit(node)
        return self._chain_compare(node.left, list(node.ops), list(node.comparators), 0)

    def _chain_compare(
        self,
        left: ast.AST,
        ops: List[ast.cmpop],
        comparators: List[ast.AST],
        index: int,
    ) -> ast.AST:
        op_name = _CMP_NAMES[type(ops[index])]
        if index == len(ops) - 1:
            return self._wrap(_AV_CMP, left, ast.Constant(op_name), comparators[index])
        # R8/N2：临时名与候选可声明名隔离（下划线开头对候选是保留前缀）。
        slot = "_avc{0}".format(index)
        holder = "_avt{0}".format(index)
        rest = self._chain_compare(
            ast.Name(id=holder, ctx=ast.Load()), ops, comparators, index + 1
        )
        body = ast.BoolOp(
            op=ast.And(),
            values=[
                self._wrap(
                    _AV_CMP,
                    ast.Name(id=slot, ctx=ast.Load()),
                    ast.Constant(op_name),
                    ast.Name(id=holder, ctx=ast.Load()),
                ),
                rest,
            ],
        )
        lam = ast.Lambda(
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg=slot), ast.arg(arg=holder)],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            body=body,
        )
        return ast.copy_location(
            ast.Call(func=lam, args=[left, comparators[index]], keywords=[]), left
        )

    def visit_FormattedValue(self, node: ast.FormattedValue) -> ast.AST:
        """R6/S1：f-string 单值格式化改走 _av_fvalue。

        修复前只在整段 f-string 完成后检查长度：宽度 2×10^8 的结果已经分配
        完毕（实测峰值 200 MB）才抛超限。改写后宽度/精度在 format() 之前校验。
        """
        self.generic_visit(node)
        spec = (
            node.format_spec if node.format_spec is not None else ast.Constant(value=None)
        )
        inner = self._wrap(
            _AV_FVALUE, node.value, spec, ast.Constant(node.conversion)
        )
        return ast.copy_location(
            ast.FormattedValue(value=inner, conversion=-1, format_spec=None), node
        )

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

    def visit_comprehension(self, node: ast.comprehension) -> ast.AST:
        """R6/S1：推导式迭代同样逐项计费。

        修复前只有 for 语句的迭代经 _av_iter 计费：推导式（列表/集合/字典）
        的迭代表达式不受约束，`[x for x in rows if flag]` 这类"被过滤掉的
        元素"完全不计费，可在循环里重复扫描有界集合而绕过计费。
        """
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
        """R8/N3：集合推导式不再先建原生 set（迭代顺序随哈希种子变化）。

        `{e for g}` 改写为 `_av_set_lit([e for g])`：先按源序求值成受限
        列表，再由受限集合按插入顺序去重。元素求值次数、求值顺序与原生
        集合推导式一致（每个元素恰好求值一次）。
        """
        self.generic_visit(node)
        node.elt = self._wrap(_AV_PASS, node.elt)
        listcomp = ast.copy_location(
            ast.ListComp(elt=node.elt, generators=node.generators), node
        )
        return self._wrap(_AV_SET_LIT, listcomp)

    def visit_DictComp(self, node: ast.DictComp) -> ast.AST:
        """R8/N1：字典推导式在 C 层逐项哈希键——键必须先守卫并计费。

        字典本身保持插入序（Python 语义），因此只需在键进入原生哈希之前
        做有界结构检查：深键（如 16 层嵌套元组）改为提前 WorkloadExceeded。
        """
        self.generic_visit(node)
        node.key = self._wrap(_AV_KEY, self._wrap(_AV_PASS, node.key))
        node.value = self._wrap(_AV_PASS, node.value)
        return self._wrap(_AV_WRAP_DICT, node)

    def visit_List(self, node: ast.List) -> ast.AST:
        self.generic_visit(node)
        return self._wrap(_AV_WRAP_LIST, node)

    def visit_Set(self, node: ast.Set) -> ast.AST:
        """R8/N1+N3：集合字面量先求值成元组，再由受限集合按源序构造。

        修复前先建**原生 set**：元素在 C 层被哈希（深键可绕过计费），且
        迭代顺序随进程哈希种子变化。改写后元素求值顺序不变（左→右，
        每个表达式恰好求值一次），构造与计费都发生在守卫之内。
        """
        self.generic_visit(node)
        elements = ast.Tuple(elts=list(node.elts), ctx=ast.Load())
        return self._wrap(_AV_SET_LIT, elements)

    def visit_Dict(self, node: ast.Dict) -> ast.AST:
        """R8/N1+N3：字典字面量先求值成 (键, 值) 对，再逐键守卫后插入。

        键/值的求值顺序与原生字面量一致（键先于值、逐对左→右）；任何键在
        进入原生哈希之前都会被结构检查（超深/超宽即拒绝）并按结构计费。
        """
        self.generic_visit(node)
        if any(key is None for key in node.keys):  # pragma: no cover - 静态检查已拒绝
            _reject("字典字面量不允许 ** 解包")
        pairs = [
            ast.Tuple(elts=[key, value], ctx=ast.Load())
            for key, value in zip(node.keys, node.values)
        ]
        return self._wrap(_AV_DICT_LIT, ast.Tuple(elts=pairs, ctx=ast.Load()))


# ---------------------------------------------------------------------------
# 运行时计费与受限容器
# ---------------------------------------------------------------------------


def _structure_exceeded(what: str) -> WorkloadExceeded:
    """结构单元超限的统一拒绝信号（R9/S1）。"""
    return WorkloadExceeded(
        "{0} 结构超过 {1} 单元上限：拒绝递归数据遍历".format(what, MAX_DATA_CELLS)
    )


def structure_cost(value: Any, what: str) -> int:
    """结构代价（R6/S1；R9/S1 扩到标量叶）：每个展开节点各计 1 个单元。

    计费口径（与复审同口径）：
    - **每个被展开的节点各计 1 个单元**：容器节点与标量叶（int/float/bool/
      None 及其它非容器对象）同口径；字符串按 64 字符一段、至少 1 段
      （CPython 的字符串比较是 memcmp 级、哈希在对象内缓存，短键的额外
      增量本就接近 0，但仍逐项访问一次）；
    - **共享引用按出现次数累积**：同一对象被容器引用 n 次就遍历 n 次。
      CPython 的元组哈希不缓存子对象哈希、容器比较也不去重，所以这里
      **不做 id 记忆化**——去重会让宽而共享的结构少算真实遍历成本；
    - 顶层标量与短字符串走常数快路径（不建栈、不遍历），普通标量比较与
      短键哈希的计费量级与既有实现一致。

    比较/成员查询/格式化/排序，以及 R8/N1 新增的**原生哈希**（字典键、
    集合元素、下标查询）都会递归遍历数据，而 CPython 的比较、repr 与哈希
    在 C 层执行、不受候选语句计费约束。本函数在**真正遍历数据之前**用
    显式栈做有界测量：

    - 容器深度超过 MAX_DATA_DEPTH 即拒绝——(a, a) 重复嵌套会形成深度 d、
      叶数 2^d 的结构，指数比较不再可能跑满时间或 C 栈；
    - 单元数超过 MAX_DATA_CELLS 即拒绝——容器节点与标量叶同口径计入，
      宽而浅（含共享引用）的结构同样有界；
    - 守卫自身有界：容器出栈时先按“每个子节点至少 1 单元”预判上限，
      超限立即拒绝，因此入栈量与遍历量都不超过 MAX_DATA_CELLS。

    修复前（R8/N1—N3）只给容器节点与长字符串计费、标量叶出栈不计数：
    row=(1,)*1024、key=(row,)*256、{key: 1} 的 262144 个展开叶只算 257，
    原生元组哈希仍逐项访问这些叶。

    R9/S1b：分派不再默认放行。dict_keys/dict_items/dict_values 这类集合式
    视图按底层键/键值对展开（同一单元上限）；其余未知类型按
    _unknown_structure_units 的保守兜底处理（有 len 按长度计、可调用计 1、
    其余拒绝），不再有「未知 ⇒ 0」。
    """
    return _walk_structure(value, what, None)


def _structure_children(node: Any) -> Optional[List[Any]]:
    """结构节点的子节点列表；返回 None 表示该节点是 O(1) 叶子。

    R9/S1b：分派不再默认放行——dict_keys/dict_items/dict_values 这类**集合式
    字典视图**必须展开为底层键/键值对：CPython 的 dict_items 相等比较走逐项
    查找并逐值比较（dictview_richcompare），视图本身不是 dict/tuple/list/set/
    frozenset 实例，白名单分派会把它们当成 O(1) 标量（实测量：视图计 0 单元，
    而原生比较每轮访问 524,288 个元素节点）。
    """
    if isinstance(node, dict):
        return [child for pair in node.items() for child in pair]
    if isinstance(node, (tuple, list, set, frozenset)):
        return list(node)
    if isinstance(node, ItemsView):
        # 每项是 (键, 值) 二元组：两项都参与原生比较/序列化。
        return [child for pair in node for child in pair]
    if isinstance(node, KeysView):
        return list(node)
    if isinstance(node, ValuesView):
        return list(node)
    return None


def _unknown_structure_units(node: Any) -> int:
    """未知类型的保守单元数（R9/S1b：不再默认 0）。

    兜底顺序（保守方向 = 宁可多计也不放行）：
    1. 有 len() 的对象（range、视图类、自定义 Sized）：按 max(1, len) 计费
       且**不展开**——元素级遍历由迭代/构造/切片等各自通道计费；
    2. 可调用对象（函数、绑定方法、白名单内建）：身份哈希与比较 O(1)，计 1；
    3. 其余未知类型（分派外的对象）：按 MAX_DATA_CELLS + 1 计费。这个数字
       必然让计费通道触顶——所有调用点都会把结构代价计到计数器上（默认
       预算 100,000 < 131,073）或按单元上限直接拒绝，因此**默认口径下等价于
       拒绝**，同时 structure_cost 保持全函数（不抛异常），直接度量与
       读数仍可观察。
    """
    if node is None or isinstance(node, (bool, int, float, complex)):
        # 标量基类（含 int/float 的子类，如计数叶子这类外部包装）：O(1) 哈希
        # 与比较，计 1——不展开、不按未知形状拒绝。
        return 1
    try:
        length = len(node)
    except TypeError:
        length = None
    if isinstance(length, int) and length >= 0:
        return max(1, length)
    if callable(node):
        return 1
    return MAX_DATA_CELLS + 1  # 未知形状：按上限+1 计费 → 计费通道必然拒绝


def _walk_structure(
    value: Any, what: str, sink: Optional[Callable[[int], None]]
) -> int:
    """同一套有界结构遍历：返回单元数；sink 逐节点计费（None = 只测量）。

    口径（structure_cost 与候选返回值计费共用，避免两份实现分叉）：
    - 每个展开节点各计 1 个单元（容器、视图、标量叶同口径；字符串按 64
      字符一段、至少 1 段）；
    - 共享引用按出现次数累积，不做 id 记忆化；
    - 容器/视图出栈前先按「每个子节点至少 1 单元」预判 MAX_DATA_CELLS，
      超限立即拒绝，因此入栈量与遍历量都有界；
    - 未知类型走保守兜底（见 _unknown_structure_units）。
    """
    kind = type(value)
    if kind is str:
        return len(value) // _STRING_COST_CHUNK
    if kind in _SCALAR_COST_TYPES:
        return 0
    children = _structure_children(value)
    if children is None:
        return _unknown_structure_units(value)
    total = 0
    stack: List[Tuple[Any, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        node_type = type(node)
        if isinstance(node, str):
            units = max(1, len(node) // _STRING_COST_CHUNK)
        elif node is None or isinstance(node, (bool, int, float, complex)):
            units = 1  # 标量叶：与容器节点同口径各计 1 个单元
        else:
            node_children = _structure_children(node)
            if node_children is None:
                units = _unknown_structure_units(node)
            else:
                if depth + 1 > MAX_DATA_DEPTH:
                    raise WorkloadExceeded(
                        "{0} 嵌套深度超过 {1} 层上限：拒绝递归数据遍历".format(
                            what, MAX_DATA_DEPTH
                        )
                    )
                if total + 1 + len(node_children) > MAX_DATA_CELLS:
                    raise _structure_exceeded(what)
                units = 1
                for child in node_children:
                    stack.append((child, depth + 1))
        if sink is not None:
            sink(units)
        total += units
        if total > MAX_DATA_CELLS:
            raise _structure_exceeded(what)
    return total


def charge_structure(value: Any, meter: "_Meter", what: str) -> int:
    """把结构单元逐节点计费到执行器计数器（R9/S1b：候选返回值通道）。

    候选执行期间的一切批量工作都按结构单元计费；候选**返回后**的返回值
    （含 trace）此前完全在计费之外：24 operations 就能让执行器序列化
    201 MB。这里在返回骨架做任何递归校验/序列化之前按出现次数逐节点计费，
    超出计数预算即 WorkloadExceeded（整批失效，不进入序列化）。
    """
    return _walk_structure(value, what, meter.charge)


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
        # 仅切片产生新列表。普通下标必须保留对象引用，否则嵌套累加器
        # 的 append 会写入副本，合法候选将静默丢失计数和加权分数。
        # 切片仍包装为受限列表，防止绕开集合上限继续增长。
        if isinstance(item, slice) and isinstance(result, list):
            return _AvList(result, self._cap)
        return result


class _AvSet(set):
    """受限局部集合：add 做结构守卫与集合上限检查，迭代按插入顺序确定化。

    R6/S1：普通 set 的迭代顺序依赖对象 hash，字符串元素在不同
    PYTHONHASHSEED 下顺序不同（同一候选的计费与结果随之漂移）。受限集合
    因此额外记录首次插入顺序并用它迭代：结果与 hash 种子无关，且真实集合
    语义（成员判定、相等、长度）仍由基类保证。

    R8/N1：原生哈希发生在 C 层，候选若用深键（如 16 层嵌套元组）触发
    指数级哈希/比较，计费完全绕过。add() 因此在**进入原生集合之前**先做
    有界结构检查（structure_cost：超深/超宽即 WorkloadExceeded）并按结构
    单元计费——字面量、推导式、set()/frozenset() 构造、.add（含别名）与
    集合运算全部经此通道。
    """

    __slots__ = ("_cap", "_order", "_meter")

    def __init__(
        self,
        items: Any = (),
        cap: int = MAX_LOCAL_COLLECTION_SIZE,
        meter: Any = None,
    ) -> None:
        super().__init__()
        self._cap = int(cap)
        self._order: List[Any] = []
        self._meter = meter
        for item in items:
            self.add(item)

    def add(self, item: Any) -> None:
        cost = structure_cost(item, "集合元素")  # 原生哈希前的有界结构守卫
        if cost and self._meter is not None:
            self._meter.charge(cost)
        if item in self:
            return
        if len(self._order) >= self._cap:
            raise WorkloadExceeded("局部集合超过 {0} 项上限".format(self._cap))
        super().add(item)
        self._order.append(item)

    def __iter__(self) -> Any:
        # 复制一份顺序表：候选不能在迭代中改变受限集合而影响迭代速度。
        return iter(list(self._order))

    def __len__(self) -> int:
        return len(self._order)


class _AvFrozenSet(frozenset):
    """受限冻结集合：迭代顺序固定为构造时的首次出现顺序（跨 hash 种子一致）。"""

    def __init__(self, items: Any = ()) -> None:
        self._order = tuple(items)

    def __iter__(self) -> Any:
        return iter(self._order)

    def __len__(self) -> int:
        return len(self._order)


class _AvDict(dict):
    """受限局部字典：逐键守卫 + 集合上限检查（静态检查已拒绝输入侧写入）。

    R8/N1：字典键的原生哈希同样在 C 层。候选写不出下标赋值，字典只能经
    字面量、推导式、dict() 构造或 dict | dict 产生，这些入口都经
    __setitem__，因此键的结构检查（超深/超宽即拒绝）与计费只需在这里做
    一次，就覆盖了全部构造通道。
    """

    __slots__ = ("_cap", "_meter")

    def __init__(
        self,
        items: Any = (),
        cap: int = MAX_LOCAL_COLLECTION_SIZE,
        meter: Any = None,
    ) -> None:
        super().__init__()
        self._cap = cap
        self._meter = meter
        source = items.items() if isinstance(items, dict) else items
        for key, value in source:
            self[key] = value

    def __setitem__(self, key: Any, value: Any) -> None:
        cost = structure_cost(key, "字典键")  # 原生哈希前的有界结构守卫
        if cost and self._meter is not None:
            self._meter.charge(cost)
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


_CMP_OPS: Dict[str, Callable[[Any, Any], Any]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "is": operator.is_,
    "is not": operator.is_not,
    "in": lambda item, container: operator.contains(container, item),
    "not in": lambda item, container: not operator.contains(container, item),
}

#: % 格式化规范：%(key)flags width.precision length type（R6/S1 分配前校验）。
#: 宽度/精度允许 \d+ 或 * ；* 形态无法在分配前界定长度上限，单独拒绝。
_PERCENT_SPEC = re.compile(
    r"%(?:\(([^)]*)\))?([-+ #0]*)(\*?\d*|\*)(?:\.(\*?\d*|\*))?[hlL]?([diouxXeEfFgGcrsa%])"
)


def _digits_to_int(digits: str) -> Optional[int]:
    """把数字串转成整数；超过 12 位直接给一个超限值，避免自身大整数膨胀。"""
    if not digits:
        return None
    if len(digits) > 12:
        return MAX_STRING_CHARS + 1
    return int(digits)


def parse_format_spec(spec: str) -> Tuple[Optional[int], Optional[int]]:
    """解析 format mini-language 的宽度与精度（缺失为 None）。

    语法：[[fill]align][sign][z][#][0][width][grouping][.precision][type]。
    fill 可以是任意字符（含数字），所以必须按语法逐段推进，不能用正则
    直接取数字（否则 f-string 里 fill=0 / align=> / width=10 会被误读）。
    """
    index = 0
    size = len(spec)
    if size >= 2 and spec[1] in "<>=^":
        index = 2
    elif size >= 1 and spec[0] in "<>=^":
        index = 1
    if index < size and spec[index] in "+- ":
        index += 1
    for flag in ("z", "#", "0"):
        if index < size and spec[index] == flag:
            index += 1
    digits = ""
    while index < size and spec[index].isdigit() and len(digits) <= 12:
        digits += spec[index]
        index += 1
    width = _digits_to_int(digits)
    if index < size and spec[index] in ",_":
        index += 1
    precision = None
    if index < size and spec[index] == ".":
        index += 1
        digits = ""
        while index < size and spec[index].isdigit() and len(digits) <= 12:
            digits += spec[index]
            index += 1
        precision = _digits_to_int(digits)
    return width, precision


def percent_format_guard(pattern: str, what: str) -> None:
    """按 % 格式化规范在**分配前**检查宽度、精度与最小结果长度。

    修复前百分号格式化先分配 100 MB 结果，再在 av_bin 事后检查长度。
    """
    minimum = 0
    for match in _PERCENT_SPEC.finditer(pattern):
        width_text = match.group(3)
        precision_text = match.group(4)
        conversion = match.group(5)
        if conversion == "%":
            minimum += 1
            continue
        if (width_text and "*" in width_text) or (
            precision_text and "*" in precision_text
        ):
            # '%%*d' % (n, x)：宽度/精度取自实参，分配前无法界定上限。
            raise WorkloadExceeded(
                "{0} 使用 * 宽度/精度：无法在分配前界定长度上限，请改用固定宽度".format(what)
            )
        width = _digits_to_int(width_text)
        if width is not None:
            if width > MAX_STRING_CHARS:
                raise WorkloadExceeded(
                    "{0} 宽度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                        what, width, MAX_STRING_CHARS
                    )
                )
            minimum += width
        else:
            minimum += 1
        precision = _digits_to_int(precision_text)
        if precision is not None:
            if precision > MAX_STRING_CHARS:
                raise WorkloadExceeded(
                    "{0} 精度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                        what, precision, MAX_STRING_CHARS
                    )
                )
            minimum += precision
    if minimum > MAX_STRING_CHARS:
        raise WorkloadExceeded(
            "{0} 结果最小长度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                what, minimum, MAX_STRING_CHARS
            )
        )


def _deterministic_key(value: Any) -> Tuple[int, str]:
    """外部普通集合元素的兜底排序键（与 hash 种子无关）。

    候选只能构造受限集合（插入顺序固定），本函数只服务“非受限集合混入”的
    防御性路径：按类型分层 + repr 排序，repr 深度受结构检查约束。
    """
    if isinstance(value, bool):
        return (0, "1" if value else "0")
    if value is None:
        return (0, "")
    if isinstance(value, (int, float)):
        return (1, repr(value))
    if isinstance(value, str):
        return (2, value)
    try:
        return (3, repr(value))
    except RecursionError:  # pragma: no cover - 结构检查已限制深度
        return (4, type(value).__name__)


def _deterministic_order(value: Any) -> List[Any]:
    """集合迭代顺序：受限集合用插入顺序；其余按确定性键排序兜底。"""
    order = getattr(value, "_order", None)
    if order is not None:
        return list(order)
    try:
        return sorted(value, key=_deterministic_key)
    except TypeError:  # pragma: no cover - 防御性兜底
        return list(value)


def _unique_in_order(items: Any) -> List[Any]:
    """按首次出现顺序去重（受限冻结集合用它固定迭代顺序）。"""
    seen: Set[Any] = set()
    ordered: List[Any] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _make_runtime(meter: _Meter, collection_cap: int = MAX_LOCAL_COLLECTION_SIZE) -> Dict[str, Any]:
    """构造受限运行时：插桩助手 + 白名单内建的计费包装。

    计费规范（合同 limits.metering_rules）：每个调用点计 1（_av_pass），
    白名单内建按各自规范再计——len/min/max/abs/round/int/float/bool/range
    计 1；sum/sorted/all/any/map/filter/enumerate/reversed/zip 与容器构造
    按输入长度保守计费；禁止不计费的批量计算。
    """
    cap = collection_cap

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

    def items_structure_cost(items: Any, what: str) -> int:
        """元素级结构代价：排序/极值的 C 层比较也按元素结构计费。"""
        total = 0
        for item in items:
            total += structure_cost(item, what)
            if total > MAX_DATA_CELLS:
                raise WorkloadExceeded(
                    "{0} 结构超过 {1} 单元上限：拒绝递归数据遍历".format(
                        what, MAX_DATA_CELLS
                    )
                )
        return total

    def scan_cost(value: Any, what: str) -> int:
        """线性扫描计费（in / .count / .index）：按长度 + 元素结构代价。"""
        length = seq_len(value)
        if length is None:
            return UNSIZEED_INPUT_COST
        limit = MAX_STRING_CHARS if isinstance(value, str) else cap
        if length > limit:
            raise WorkloadExceeded(
                "{0} 输入长度 {1} 超过 {2} 上限".format(what, length, limit)
            )
        total = max(1, length)
        if isinstance(value, str) or isinstance(value, dict):
            # 字符串逐字符扫描、字典按哈希查找：不再展开（字典值不参与查找）。
            return total
        for item in value:
            total += structure_cost(item, what)
            if total > MAX_DATA_CELLS:
                raise WorkloadExceeded(
                    "{0} 结构超过 {1} 单元上限：拒绝递归数据遍历".format(
                        what, MAX_DATA_CELLS
                    )
                )
        return total

    def guard_format_spec(spec: str, what: str) -> None:
        """格式规范宽度/精度在**分配前**校验（R6/S1）。"""
        width, precision = parse_format_spec(spec)
        if width is not None and width > MAX_STRING_CHARS:
            raise WorkloadExceeded(
                "{0} 宽度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                    what, width, MAX_STRING_CHARS
                )
            )
        if precision is not None and precision > MAX_STRING_CHARS:
            raise WorkloadExceeded(
                "{0} 精度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                    what, precision, MAX_STRING_CHARS
                )
            )

    def metered_key(key: Any, what: str) -> Any:
        """给 sorted/min/max 的 key 包装：键结果的结构代价进入计费。

        key 结果的比较发生在 C 层（PyObject_RichCompare），不在 _av_cmp 的
        计费路径上；按每个键结果的结构规模计费即把这条通道关掉。
        """
        if key is None or not callable(key):
            return key

        def key_call(item: Any) -> Any:
            result = key(item)
            meter.charge(structure_cost(result, what))
            return result

        return key_call

    def ordered_input(value: Any) -> Any:
        """R8/N3：原生集合输入的迭代顺序确定化（受限集合已按插入序迭代）。

        候选能构造的集合都已是受限集合（插入序）；这里只处理“混入的普通
        set/frozenset”（例如视图数据或旧对象），按确定键排序后再消费，
        保证跨 PYTHONHASHSEED 的计费与结果一致。
        """
        if isinstance(value, (set, frozenset)) and not isinstance(
            value, (_AvSet, _AvFrozenSet)
        ):
            return _deterministic_order(value)
        return value

    def bounded_items(value: Any, what: str) -> List[Any]:
        """S1 修复：消费可迭代对象的内建统一“先限长（≤cap）再按元素计费”。

        有长度输入：len > cap 即拒绝（最大输入边界），否则按长度计费并
        物化；无长度输入：逐项计费物化（受 cap 约束）。真实遍历只发生在
        本函数内，候选无法再拿到“只计 1 次调用费却遍历百万项”的通道。
        """
        value = ordered_input(value)
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
        if op_name == "%" and isinstance(a, str):
            # R6/S1：宽度/精度在分配前校验（修复前先分配 100 MB 再事后检查）。
            percent_format_guard(a, "% 格式化")
            meter.charge(structure_cost(b, "% 格式化右操作数"))
        if op_name in ("|", "-", "&", "^"):
            set_result = combined_set(a, b, op_name)
            if set_result is not None:
                return set_result
            if op_name == "|" and isinstance(a, dict) and isinstance(b, dict):
                return combined_dict(a, b)
        result = _RT_OPS[op_name](a, b)
        if isinstance(result, str) and len(result) > MAX_STRING_CHARS:
            raise WorkloadExceeded("字符串超过 {0} 字符上限".format(MAX_STRING_CHARS))
        if isinstance(result, str):
            # R9/S1b：**字符串产出**按 64 字符一段计费（与字符串哈希/比较同口径）。
            # 修复前拼接与重复只计 1 次运算：`"x"*32768 + "y"*32768` 每次拷贝
            # 64 KiB 却只花 1 个单元，15,000 轮（90,005 ops）能搬 983 MB；
            # 现在的上界是 64 字节/单元（短字符串结果 < 64 字符仍为 0，热路径不变）。
            meter.charge(len(result) // _STRING_COST_CHUNK)
        if isinstance(result, (list, tuple)):
            if len(result) > cap:
                collection_exceed()
            if isinstance(result, list):
                return _AvList(result, cap)
            return result
        if isinstance(result, (set, frozenset)):
            # R6/S1：集合运算结果同样受集合上限约束，并按插入顺序确定化
            # （修复前返回普通 set：长度不受限且迭代顺序随 hash 种子变化）。
            if len(result) > cap:
                collection_exceed()
            meter.charge(max(1, len(result)))
            return _AvSet(_deterministic_order(result), cap, meter)
        return num_guard(result)

    def combined_set(a: Any, b: Any, op_name: str) -> Any:
        """集合运算的确定化重建：顺序 = 左操作数顺序 + 右操作数新增项。"""
        if not isinstance(a, (set, frozenset)) or not isinstance(b, (set, frozenset)):
            return None
        meter.charge(max(1, len(a) + len(b)))
        base = _RT_OPS[op_name](set(a), set(b))
        if len(base) > cap:
            collection_exceed()
        if op_name == "|":
            order = [item for item in _deterministic_order(a)]
            order += [item for item in _deterministic_order(b) if item not in a]
        elif op_name == "&":
            order = [item for item in _deterministic_order(a) if item in b]
        elif op_name == "-":
            order = [item for item in _deterministic_order(a) if item not in b]
        else:  # ^
            order = [item for item in _deterministic_order(a) if item not in b]
            order += [item for item in _deterministic_order(b) if item not in a]
        return _AvSet(order, cap, meter)

    def combined_dict(a: Any, b: Any) -> Any:
        """dict | dict：逐键守卫重建（顺序与 Python 一致：左后右）。

        R8/N1：dict(a)/update(b) 在 C 层哈希全部键，改为经 _AvDict.__setitem__
        重建，键的结构检查与计费与字面量构造走同一通道。
        """
        meter.charge(max(1, len(a) + len(b)))
        merged = _AvDict(cap=cap, meter=meter)
        for key, value in a.items():
            merged[key] = value
        for key, value in b.items():
            merged[key] = value
        return merged

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

    def av_cmp(a: Any, op_name: str, b: Any) -> Any:
        """R6/S1：比较与成员查询统一计费，并按操作数结构规模计费。

        - 相等/排序比较：按两侧结构代价计费（标量 0，故标量比较量级不变）；
        - is / is not：身份比较 O(1)，只计 1；
        - in / not in：按被查序列长度（scan_cost）加被查元素结构计费。

        结构代价由 structure_cost 做**有界**遍历并在超深/超宽时提前拒绝，
        所以 CPython 的递归比较不会在指数结构上跑满时间或 C 栈。
        """
        meter.charge(1)
        if op_name in ("is", "is not"):
            return _CMP_OPS[op_name](a, b)
        if op_name in ("in", "not in"):
            meter.charge(scan_cost(b, "成员查询容器") + structure_cost(a, "成员查询元素"))
            return _CMP_OPS[op_name](a, b)
        cost = structure_cost(a, "比较左操作数") + structure_cost(b, "比较右操作数")
        if cost:
            meter.charge(cost)
        return _CMP_OPS[op_name](a, b)

    def av_fvalue(value: Any, spec: Any, conversion: int) -> str:
        """R6/S1：f-string 单值格式化——宽度/精度在分配前校验。

        修复前 f-string 在整段拼接后才检查长度：宽度 2×10^8 的结果先被分配
        （实测峰值 200 MB）才抛超限。这里先按运行时的格式规范解析宽度与精度
        并拒绝超限值，再做 repr/str/ascii 转换与 format()；容器值先做有界结构
        检查，避免 repr 在指数结构上递归展开。
        """
        meter.charge(1)
        meter.charge(structure_cost(value, "f-string 值"))
        if conversion == 114:  # !r
            value = repr(value)
        elif conversion == 115:  # !s
            value = str(value)
        elif conversion == 97:  # !a
            value = ascii(value)
        if spec is None:
            result = format(value, "")
        else:
            if not isinstance(spec, str):
                raise WorkloadExceeded("f-string 格式规范必须是字符串")
            guard_format_spec(spec, "f-string 格式规范")
            result = format(value, spec)
        if type(result) is str and len(result) > MAX_STRING_CHARS:
            raise WorkloadExceeded("字符串超过 {0} 字符上限".format(MAX_STRING_CHARS))
        if type(result) is str:
            # R9/S1b：格式化产出同样按 64 字符一段计费（宽度 65536 的填充
            # 此前 2 个操作就能产出 128 KiB；短结果仍为 0，热路径不变）。
            meter.charge(len(result) // _STRING_COST_CHUNK)
        return result

    def av_sub(value: Any, index: Any) -> Any:
        """R6/S1：切片是批量拷贝——按结果长度计费；下标取值 O(1) 不计。

        R8/N1：`table[深键]` 的字典查找会在 C 层哈希并比较键，深键的
        指数级代价必须先做有界结构检查并计费。
        """
        if isinstance(value, dict):
            meter.charge(structure_cost(index, "下标键"))
        result = value[index]
        if isinstance(index, slice) and isinstance(result, (str, list, tuple)):
            meter.charge(len(result))
        elif isinstance(result, (set, frozenset, dict)) and len(result) > cap:
            collection_exceed()
        return result

    def av_method(obj: Any, name: str) -> Any:
        """R6/S1：方法取值统一包装为计费可调用对象。

        修复前只包装 .count/.index 的直接调用：`count = values.count` 之后再
        调用就完全绕过计费（4096 项列表扫 40 趟只计 8,357）。现在取方法本身
        计 1，返回的可调用对象在每次调用时按方法规范计费：

        - .count/.index：按被查序列长度 + 参数结构计费（真实线性扫描）；
        - .append/.add：先查集合上限再改（任何底层容器都受上限约束）；
        - .get/.items/.keys/.values：只由调用点计 1（键的哈希成本按结构代价
          计入 .get），因此常见只读方法调用的计费量级与修复前一致。

        取值本身（绑定方法）不计费：绑定是 O(1)，真实工作发生在调用时；
        调用点已经有 _av_pass 计 1。
        """
        bound = getattr(obj, name)  # 无该方法时与原生语义一致：立即 AttributeError

        if name in ("count", "index"):

            def scan(*args: Any, **kwargs: Any) -> Any:
                cost = scan_cost(obj, ".{0} 输入".format(name))
                for arg in args:
                    cost += structure_cost(arg, ".{0} 参数".format(name))
                meter.charge(cost)
                return bound(*args, **kwargs)

            return scan

        if name in ("append", "add"):

            def grow(*args: Any, **kwargs: Any) -> Any:
                if len(obj) >= cap:
                    collection_exceed()
                if name == "add" and not isinstance(obj, _AvSet):
                    # R8/N1：受限集合的 add 自带结构守卫与计费；普通 set
                    # （混入对象）在这里补上，别名调用与直接调用走同一通道。
                    for arg in args:
                        meter.charge(structure_cost(arg, ".add 元素"))
                return bound(*args, **kwargs)

            return grow

        def call(*args: Any, **kwargs: Any) -> Any:
            if name == "get" and args:
                # 键的哈希/比较成本：长键或深键按结构代价计费（短键为 0）。
                meter.charge(structure_cost(args[0], ".get 键"))
            return bound(*args, **kwargs)

        return call

    def wrap_list(value: Any) -> Any:
        value = ordered_input(value)
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
        """集合构造（字面量 / 推导式 / set()）：按源序插入并逐元素守卫。

        R8/N1+N3：元素在进入原生哈希之前做结构检查并按结构计费；原生
        集合输入先确定化排序，避免迭代顺序随哈希种子漂移。
        """
        value = ordered_input(value)
        length = seq_len(value)
        if length is None:
            items = materialize(value)
        else:
            if length > cap:
                collection_exceed()
            items = list(value)
        meter.charge(max(1, len(items)))
        return _AvSet(items, cap, meter)

    def wrap_dict(value: Any) -> Any:
        """字典构造（字面量 / 推导式 / dict()）：逐键守卫（原生哈希前）。

        R8/N1：修复前 dict(mapping) 先在 C 层哈希全部键，深键的指数级
        哈希/比较完全在保护之外；现在键经 _AvDict.__setitem__ 检查与计费。
        """
        if isinstance(value, dict):
            if len(value) > cap:
                collection_exceed()
            pairs = value.items()
        else:
            length = seq_len(value)
            if length is None:
                pairs = materialize(value)
            else:
                if length > cap:
                    collection_exceed()
                pairs = value
        result = _AvDict(pairs, cap, meter)
        meter.charge(max(1, len(result)))
        return result

    def av_key(value: Any) -> Any:
        """R8/N1：推导式键在进入原生哈希前的守卫与计费（标量代价为 0）。"""
        meter.charge(structure_cost(value, "推导式键"))
        return value

    # —— 白名单内建的计费包装 ——

    def b_len(obj: Any) -> int:
        meter.charge(1)
        return len(obj)

    def b_min(*args: Any, **kwargs: Any) -> Any:
        # S1：单参数形式先限长再按元素计费（min(range(N)) 不再免费遍历 N 项）；
        # 多参数形式比较参数本身，按参数个数计费。
        # R6/S1：极值比较发生在 C 层，按元素结构与 key 结果结构计费并限深。
        if len(args) == 1:
            items = bounded_items(args[0], "min()")
            meter.charge(items_structure_cost(items, "min() 元素"))
            if "key" in kwargs:
                kwargs["key"] = metered_key(kwargs["key"], "min() 键")
            return num_guard(min(items, **kwargs))
        meter.charge(max(1, len(args)))
        meter.charge(items_structure_cost(list(args), "min() 参数"))
        if "key" in kwargs:
            kwargs["key"] = metered_key(kwargs["key"], "min() 键")
        return num_guard(min(*args, **kwargs))

    def b_max(*args: Any, **kwargs: Any) -> Any:
        if len(args) == 1:
            items = bounded_items(args[0], "max()")
            meter.charge(items_structure_cost(items, "max() 元素"))
            if "key" in kwargs:
                kwargs["key"] = metered_key(kwargs["key"], "max() 键")
            return num_guard(max(items, **kwargs))
        meter.charge(max(1, len(args)))
        meter.charge(items_structure_cost(list(args), "max() 参数"))
        if "key" in kwargs:
            kwargs["key"] = metered_key(kwargs["key"], "max() 键")
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
        # R6/S1：序列求和（sum(pairs, ())）按元素结构计费——拼接是批量拷贝。
        meter.charge(items_structure_cost(items, "sum() 元素"))
        # R8/N1：序列起始值会做 len(rows) 次拷贝，最终规模 = len(start) +
        # Σlen(item)，不受单集合上限约束（复审反例 [(1,)*128]*64 + () 得到
        # 8192 项、仅计 138）。评分的求和只需要数值用途，因此**在拷贝之前**
        # 拒绝序列起始值；数值起始值（int/float/bool）仍然允许。
        if start and isinstance(start[0], (list, tuple, str, dict, set, frozenset)):
            raise WorkloadExceeded(
                "sum() 不允许序列起始值（如 sum(rows, ())）：重复拷贝的次数与"
                "最终规模不受单集合上限约束；数值求和请用 sum(rows)"
            )
        return num_guard(sum(items, *start))

    def b_sorted(iterable: Any, **kwargs: Any) -> Any:
        items = bounded_items(iterable, "sorted()")
        # R6/S1：排序比较在 C 层执行，按元素结构与 key 结果结构计费并限深。
        meter.charge(items_structure_cost(items, "sorted() 元素"))
        if "key" in kwargs:
            kwargs["key"] = metered_key(kwargs["key"], "sorted() 键")
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
        iterable = ordered_input(iterable)
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
        """dict(...)：与字面量/推导式同一条逐键守卫通道（R8/N1）。"""
        pairs: List[Any] = []
        if args:
            source = args[0]
            if isinstance(source, dict):
                if len(source) > cap:
                    collection_exceed()
                pairs.extend(source.items())
            else:
                pairs.extend(bounded_items(source, "dict()"))
        pairs.extend(kwargs.items())
        if len(pairs) > cap:
            collection_exceed()
        result = _AvDict(pairs, cap, meter)
        meter.charge(max(1, len(result)))
        return result

    def b_set(iterable: Any = ()) -> Any:
        return wrap_set(iterable)

    def b_frozenset(iterable: Any = ()) -> frozenset:
        iterable = ordered_input(iterable)
        length = seq_len(iterable)
        if length is None:
            items = materialize(iterable)
        else:
            if length > cap:
                collection_exceed()
            items = list(iterable)
        meter.charge(max(1, len(items)))
        # R8/N1：冻结集合的构造同样在 C 层哈希元素——逐项结构守卫并计费。
        for item in items:
            meter.charge(structure_cost(item, "frozenset 元素"))
        # R6/S1：冻结集合也按首次出现顺序迭代（跨 hash 种子一致）。
        return _AvFrozenSet(_unique_in_order(items))

    runtime: Dict[str, Any] = {
        _AV_PASS: av_pass,
        _AV_BIN: av_bin,
        _AV_UN: av_un,
        _AV_ITER: av_iter,
        _AV_CMP: av_cmp,
        _AV_METHOD: av_method,
        _AV_FVALUE: av_fvalue,
        _AV_SUB: av_sub,
        _AV_WRAP_LIST: wrap_list,
        _AV_WRAP_DICT: wrap_dict,
        _AV_SET_LIT: wrap_set,
        _AV_DICT_LIT: wrap_dict,
        _AV_KEY: av_key,
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


@dataclass(frozen=True)
class ActionValueCompiledRuntime:
    """组合根验签后注入的专用执行体；纯策略不自行读磁盘或装载扩展。

    每个执行器独占计量器、受限命名空间和候选闭包。源码摘要必须逐字
    匹配；原静态检查、返回合同、操作额度和模块状态复核继续执行。
    编译候选工厂为空时保留原插桩体，只使用原体编译助手。
    """

    source_sha256: str  # 精确UTF-8候选源码摘要，不接受同名或日期替代身份
    execution_id: str  # 组合根核实际源与二进制后给出的身份，不含凭据
    meter_factory: Callable[[int], Any]  # 新建独占计量器；额度与used使用Python整数
    runtime_factory: Callable[[Any, int], Dict[str, Any]]  # 生成原受限助手，第二参为单集合项数
    candidate_factory: Optional[Callable[[Dict[str, Any], Any, int], Dict[str, Any]]]
    # 工厂须返回原函数/不可变常量命名空间；None仅保留原Python插桩候选
    charge_return_value: Callable[[Any, Any, str], int]  # 同原结构逐节点计费，含重复引用
    copy_facts: Callable[[Any], Any]  # 原冻结事实的全新原始值副本，不共享候选容器


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
        max_local_collection_size: int = MAX_LOCAL_COLLECTION_SIZE,
        compiled_runtime: Optional[ActionValueCompiledRuntime] = None,
    ) -> None:
        if (type(max_local_collection_size) is not int
                or not 0 < max_local_collection_size <= MAX_SUPPORTED_LOCAL_COLLECTION_SIZE):
            raise ValueError("局部集合容量必须是1—16384的整数，不能是布尔值")
        self._max_local_collection_size = max_local_collection_size
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
        if compiled_runtime is not None:
            if (type(compiled_runtime) is not ActionValueCompiledRuntime
                    or hashlib.sha256(encoded).hexdigest() != compiled_runtime.source_sha256
                    or not compiled_runtime.execution_id):
                raise ValueError("专用编译执行体与候选源码身份不匹配")
        self._compiled_runtime = compiled_runtime
        self._charge_return_value = (charge_structure if compiled_runtime is None
                                     else compiled_runtime.charge_return_value)
        self._meter = (_Meter(int(max_operations)) if compiled_runtime is None
                       else compiled_runtime.meter_factory(int(max_operations)))
        instrumented = _Instrumentor().visit(tree)
        ast.fix_missing_locations(instrumented)
        self._code = compile(
            instrumented, "<action_value:{0}>".format(self.name), "exec"
        )
        self._runtime = (_make_runtime(self._meter, max_local_collection_size)
                         if compiled_runtime is None else
                         compiled_runtime.runtime_factory(self._meter, max_local_collection_size))
        namespace: Dict[str, Any] = {"__builtins__": {}}
        namespace.update(self._runtime)
        # 模块级只有常量赋值与函数定义；静态检查已排除任意顶层执行。
        if compiled_runtime is None or compiled_runtime.candidate_factory is None:
            exec(self._code, namespace)
        else:
            namespace = compiled_runtime.candidate_factory(
                self._runtime, self._meter, max_local_collection_size)
        fn = namespace.get("score_actions")
        if not callable(fn):  # pragma: no cover - 静态检查已保证
            raise StaticCheckError("score_actions 未定义或不可调用")
        self._fn: Callable[[Mapping[str, Any]], Mapping[str, Any]] = fn
        # S1：装载即核验并快照模块级绑定——只允许函数与不可变常量；
        # score() 每次执行后逐项复核，杜绝跨调用可变共享状态。
        self._namespace = namespace
        self._module_snapshot = self._snapshot_module_bindings(namespace)
        self.last_operation_count: Optional[int] = None

    @property
    def max_local_collection_size(self) -> int:
        """本执行器实际单集合容量；单位项，默认4096，不是操作额度或耗时。"""
        return self._max_local_collection_size

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

    def _guarded_candidate(self, candidate_view: Mapping[str, Any]) -> Any:
        """候选调用 + 返回值结构计费（R9/S1b：返回值不是免费通道）。

        候选**执行期间**的一切批量工作早已计费；但候选**返回后**的返回值
        （尤其 trace）此前完全在计费之外：24 operations 就能让骨架递归校验
        并序列化 201 MB。这里在骨架做任何递归校验/序列化之前，按同一套有界
        结构遍历逐节点计费（共享引用按出现次数展开），超出计数预算即
        WorkloadExceeded 整批失效——正常批的返回值只有几十到几百个单元，
        量级不变。
        """
        raw = self._fn(candidate_view)
        self._charge_return_value(raw, self._meter, "候选返回值")
        return raw

    def score_vip_route(self, view) -> ScoreBatch:
        """受限执行独立 VIP 视图；失败原样交严格研究包装，不补保底。

        只接受新合同的精确视图类型；复用静态检查、工作量计费与跨调用
        状态复核。旧 ScoringView 的版本和执行入口保持原语义。
        """
        from .route_heuristic_view import (
            VipRouteScoringView,
            run_vip_route_scoring_skeleton,
        )

        if not isinstance(view, VipRouteScoringView):
            raise ValueError("ActionValueExecutor.score_vip_route 需要 VipRouteScoringView 输入")
        self._meter.used = 0
        try:
            if self._compiled_runtime is None:
                return run_vip_route_scoring_skeleton(view, self._guarded_candidate)
            return run_vip_route_scoring_skeleton(view, self._guarded_candidate,
                fact_copy=self._compiled_runtime.copy_facts)
        finally:
            self.last_operation_count = self._meter.used
            self._verify_no_shared_mutation()

    def score(self, view: ScoringView) -> ScoreBatch:
        """受限执行 score_actions 并验证完整返回；失败整批抛错，不部分补零。"""
        if not isinstance(view, ScoringView):
            raise ValueError("ActionValueExecutor.score 需要 ScoringView 输入")
        self._meter.used = 0
        try:
            # WorkloadExceeded 是 BaseException：骨架内的 except Exception
            # 不会吞掉它，原样上抛给调用方做整批降级。
            return run_scoring_skeleton(view, self._guarded_candidate)
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
            "max_string_chars": MAX_STRING_CHARS,
            "max_data_depth": MAX_DATA_DEPTH,
            "max_data_cells": MAX_DATA_CELLS,
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
