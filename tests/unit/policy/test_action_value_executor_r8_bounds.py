"""R8 复审 N1/N2/N3 专属回归：受限执行器的哈希边界、插桩语义与集合确定化。

权威材料：
- review/llm-guided-heuristic-route-2026-09-15/R7-REPAIR-REREVIEW-2026-09-17.md §3：
  N1（P1）深键哈希与序列求和仍能绕过计算边界；
  N2（P2）链式比较插桩改变合法代码语义；
  N3（P2）集合字面量仍随进程哈希种子变化；
- 同目录 R8-FIX-PLAN-2026-09-17.md 波次 E1。

所有断言只经公开入口：ActionValueExecutor(source[, max_operations])、
score(view)、last_operation_count、WorkloadExceeded。期望值不来自实现，
而来自**原生 Python 语义**（N2 插桩前后差分）与**跨进程逐字节一致**
（N3 子进程 PYTHONHASHSEED 1/2/123，与复审实测同口径）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import pytest

from hangma_bot.policy.action_value_executor import (
    MAX_COUNTED_OPERATIONS,
    ActionValueExecutor,
    WorkloadExceeded,
)
from hangma_bot.policy.action_value_seeds import build_sample_view

_NAME = "r8-e1"
#: 复审反例规模：元组按 x = (x, x) 嵌套 16 次（深度 17、2**16 个叶）。
DEEP_DEPTH = 16


def _run(source: str, budget: Optional[int] = None) -> Tuple[str, Any, int]:
    """经公开入口执行候选；返回 (结果种类, 批次或消息, 实测计数)。"""
    executor = (
        ActionValueExecutor(source, name=_NAME)
        if budget is None
        else ActionValueExecutor(source, name=_NAME, max_operations=budget)
    )
    try:
        batch = executor.score(build_sample_view())
    except WorkloadExceeded as exc:
        return "exceeded", str(exc), executor.last_operation_count
    return "returned", batch, executor.last_operation_count


def _deep_tuple_block(depth: int = DEEP_DEPTH, indent: str = "    ") -> str:
    """生成 depth 层重复嵌套元组 x（复审反例的紧凑形式）。"""
    return (
        indent + "x = (1, 1)\n"
        + indent + "for i in range({0}):\n".format(depth)
        + indent + "    x = (x, x)\n"
    )


# ===========================================================================
# N1 · 深键哈希 / 集合构造 / 深键查询必须在原生 C 层工作之前守卫并计费
# ===========================================================================


class TestN1DeepKeyGuards:
    """复审反例：{x: 1} 深键只计 36 且不触发深度上限——每个入口单独回归。"""

    def test_dict_literal_deep_key_rejected_before_hashing(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    table = {x: 1}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-dict-literal'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "深键字典字面量仍合法返回：{0!r}".format(detail)
        assert "深度" in str(detail) or "结构" in str(detail), str(detail)
        # 提前拒绝（而非耗尽预算）：说明守卫发生在原生哈希之前。
        assert counted < MAX_COUNTED_OPERATIONS

    def test_set_literal_deep_element_rejected_before_hashing(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    bag = {x}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-set-literal'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "深元素集合字面量仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_dict_comprehension_deep_key_rejected_before_hashing(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    table = {x: i for i in range(1)}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-dict-comp'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "深键字典推导式仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_set_comprehension_deep_element_rejected_before_hashing(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    bag = {x for i in range(1)}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-set-comp'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "深元素集合推导式仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_set_constructor_deep_element_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    bag = set([x])\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-set-ctor'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "set([深元素]) 仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_frozenset_constructor_deep_element_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    frozen = frozenset([x])\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-frozenset'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "frozenset([深元素]) 仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_dict_constructor_deep_key_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    table = dict([(x, 1)])\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-dict-ctor'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "dict([(深键, 1)]) 仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_set_add_deep_element_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    bag = set()\n"
            "    bag.add(x)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-add'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", ".add(深元素) 仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_set_add_alias_deep_element_rejected(self) -> None:
        """间接调用：先取绑定方法别名，再调用。"""
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    bag = set()\n"
            "    grow = bag.add\n"
            "    grow(x)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-add-alias'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "别名 .add(深元素) 仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_indirect_guard_through_helper_function(self) -> None:
        """间接调用：深元素经候选自定义函数传入集合构造。"""
        source = (
            "def put(bag, item):\n"
            "    bag.add(item)\n"
            "    return bag\n"
            "\n"
            "\n"
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    bag = set()\n"
            "    filled = put(bag, x)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-indirect'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "间接 .add(深元素) 仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_subscript_deep_key_rejected(self) -> None:
        """深键查询：table[深键] 的哈希发生在 C 层，必须先守卫。"""
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    table = {'a': 1}\n"
            "    hit = table[x]\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-subscript'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "table[深键] 未被守卫：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS

    def test_get_deep_key_rejected(self) -> None:
        """既有守卫不回退：.get(深键) 在 R6/S1 已纳入结构检查。"""
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    table = {'a': 1}\n"
            "    hit = table.get(x)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-get'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", ".get(深键) 未被守卫：{0!r}".format(detail)

    def test_membership_deep_element_rejected(self) -> None:
        """既有守卫不回退：in 的深元素在 C 层比较前已被结构检查。"""
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    bag = set(['a'])\n"
            "    hit = x in bag\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-in'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "in 深元素未被守卫：{0!r}".format(detail)

    def test_legal_nested_key_is_billed_not_just_rejected(self) -> None:
        """正向对照：限深内的嵌套键合法，且按结构单元计费（不是一概拒绝）。"""
        source = (
            "def score_actions(view):\n"
            "    key = (1, 2, 3, 4)\n"
            "    total = 0\n"
            "    for i in range(100):\n"
            "        table = {key: i}\n"
            "        total = total + len(table)\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{total}'}\n"
        )
        kind, batch, counted = _run(source, budget=1_000_000)
        assert kind == "returned", "限深内嵌套键被误拒：{0!r}".format(batch)
        assert batch.reason == "100"
        # 每个字典字面量至少按 4 个结构单元计费（100 次 ≥ 400）。
        assert counted >= 400, "嵌套键未按结构计费：{0}".format(counted)

    def test_flat_key_dict_literal_keeps_previous_billing_scale(self) -> None:
        """标量键字典字面量不因守卫而改变计费量级（结构代价为 0）。"""
        source = (
            "def score_actions(view):\n"
            "    table = {'a': 1, 'b': 2}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'flat'}\n"
        )
        kind, batch, counted = _run(source)
        assert kind == "returned" and batch.reason == "flat"
        assert counted <= 8, "标量键字典计费膨胀：{0}".format(counted)


class TestN1SequenceSumBounds:
    """复审反例：sum([(1,)*128]*64, ()) 产生 8192 项（超 4096）仅计 138。"""

    def test_sequence_start_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    rows = [(1,) * 128] * 64\n"
            "    total = sum(rows, ())\n"
            "    size = len(total)\n"
            "    return {'status': 'ABSTAIN', 'reason': f'size-{size}'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "序列起始值求和仍合法返回：{0!r}".format(detail)
        assert counted < MAX_COUNTED_OPERATIONS, "未在拷贝前拒绝：{0}".format(counted)

    def test_sequence_start_list_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    rows = [[1] * 128] * 64\n"
            "    total = sum(rows, [])\n"
            "    size = len(total)\n"
            "    return {'status': 'ABSTAIN', 'reason': f'size-{size}'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "列表起始值求和仍合法返回：{0!r}".format(detail)

    def test_sequence_start_through_variable_rejected(self) -> None:
        """间接调用：起始值经变量/函数传入也必须被守卫。"""
        source = (
            "def total_of(rows, start):\n"
            "    return sum(rows, start)\n"
            "\n"
            "\n"
            "def score_actions(view):\n"
            "    rows = [(1,) * 128] * 64\n"
            "    start = ()\n"
            "    total = total_of(rows, start)\n"
            "    size = len(total)\n"
            "    return {'status': 'ABSTAIN', 'reason': f'size-{size}'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "间接序列起始值求和仍合法返回：{0!r}".format(detail)

    def test_numeric_sum_still_allowed(self) -> None:
        """数值用途仍可用：sum(items) 与 sum(items, 数值起始值)。"""
        source = (
            "def score_actions(view):\n"
            "    base = sum([1, 2, 3])\n"
            "    offset = sum([1, 2, 3], 10)\n"
            "    total = base + offset\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{total}'}\n"
        )
        kind, batch, counted = _run(source)
        # sum([1,2,3]) = 6；sum([1,2,3], 10) = 16；两者相加 = 22。
        assert kind == "returned" and batch.reason == "22", "{0!r}".format(batch)


#: 每一种允许的聚合入口：逐一前置规模守卫（超单集合上限即拒绝）。
_OVERSIZED_AGGREGATION = {
    "sum": "sum(range(4097))",
    "sorted": "sorted(range(4097))",
    "min": "min(range(4097))",
    "max": "max(range(4097))",
    "all": "all(range(4097))",
    "any": "any(range(4097))",
    "list": "list(range(4097))",
    "tuple": "tuple(range(4097))",
    "set": "set(range(4097))",
    "frozenset": "frozenset(range(4097))",
    "enumerate": "enumerate(range(4097))",
    "reversed": "reversed(range(4097))",
    "zip": "zip(range(4097), range(4097))",
    "map": "map(abs, range(4097))",
    "filter": "filter(bool, range(4097))",
    "dict-zip": "dict(zip(range(4097), range(4097)))",
    "list-comp": "[i for i in range(4097)]",
    "set-comp": "{i for i in range(4097)}",
    "dict-comp": "{i: i for i in range(4097)}",
}


class TestN1AggregationEntryGuards:
    @pytest.mark.parametrize("entry", sorted(_OVERSIZED_AGGREGATION))
    def test_every_allowed_aggregation_entry_has_size_guard(self, entry: str) -> None:
        expr = _OVERSIZED_AGGREGATION[entry]
        source = (
            "def score_actions(view):\n"
            "    result = {0}\n".format(expr)
            + "    return {'status': 'ABSTAIN', 'reason': 'oversized'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "{0} 缺少前置规模守卫：{1!r}".format(entry, detail)


# ===========================================================================
# N2 · 链式比较插桩必须与原生 Python 语义一致（差分）
# ===========================================================================


def _restricted_source(
    setup: Sequence[Tuple[int, str]],
    expr: str,
    tail: Sequence[Tuple[int, str]] = (),
    reason_expr: str = "f'{value}'",
) -> str:
    """按同一份用例文本生成受限候选源码（setup/tail 缩进 +1 层）。"""
    lines = ["def score_actions(view):"]
    for level, text in list(setup) + [(0, "value = " + expr)] + list(tail):
        lines.append("    " * (level + 1) + text)
    lines.append("    return {'status': 'ABSTAIN', 'reason': " + reason_expr + "}")
    return "\n".join(lines) + "\n"


def _native_reason(
    setup: Sequence[Tuple[int, str]],
    expr: str,
    tail: Sequence[Tuple[int, str]] = (),
    reason_expr: str = "f'{value}'",
) -> str:
    """原生 Python 基准：同一份用例文本直接执行（无插桩）。"""
    lines = []
    for level, text in list(setup) + [(0, "value = " + expr)] + list(tail):
        lines.append("    " * level + text)
    lines.append("reason = " + reason_expr)
    namespace: dict = {}
    exec(compile("\n".join(lines), "<native-baseline>", "exec"), namespace)  # noqa: S102
    return namespace["reason"]


_BUMP_SETUP: List[Tuple[int, str]] = [
    (0, "def bump(box, value):"),
    (1, "box.append(value)"),
    (1, "return value"),
    (0, "box = []"),
]

#: (用例名, setup, 表达式, tail, reason 表达式)
_CHAIN_CASES: List[Tuple[str, List[Tuple[int, str]], str, List[Tuple[int, str]], str]] = [
    ("same-name-x0", [(0, "x0 = 100")], "0 < 1 < x0", [], "f'{value}'"),
    ("same-name-t0", [(0, "t0 = 100")], "0 < 1 < t0", [], "f'{value}'"),
    ("same-name-both", [(0, "x0 = 100"), (0, "t0 = 0")], "t0 < 1 < x0", [], "f'{value}'"),
    ("false-first-branch", [(0, "x0 = 100")], "5 < 1 < x0", [], "f'{value}'"),
    ("mixed-branches", [(0, "x0 = 10")], "0 < 5 < 9 < x0", [], "f'{value}'"),
    ("nested-chain", [(0, "x0 = 4")], "(1 < 2 < x0) and (x0 < 10 < 20)", [], "f'{value}'"),
    ("chain-in-ifexp", [(0, "x0 = 100")], "'yes' if 0 < 1 < x0 else 'no'", [], "value"),
    ("chain-with-is", [(0, "x0 = None")], "x0 is None is True", [], "f'{value}'"),
    ("chain-over-arithmetic", [(0, "x0 = 12")], "0 + 1 < 2 * 2 < x0 - 1", [], "f'{value}'"),
    (
        "same-name-function-param",
        [(0, "def probe(x0):"), (1, "return 0 < 1 < x0")],
        "probe(100)",
        [],
        "f'{value}'",
    ),
    (
        "evaluate-once-and-short-circuit",
        _BUMP_SETUP,
        "bump(box, 0) < bump(box, 1) < bump(box, 2)",
        [
            (0, "visited = len(box)"),
            (0, "second = bump(box, 5) < bump(box, 1) < bump(box, 9)"),
            (0, "visited2 = len(box)"),
        ],
        "f'{value}-{visited}-{second}-{visited2}'",
    ),
]


class TestN2ChainedCompareSemantics:
    def test_review_counterexample_x0_capture(self) -> None:
        """复审反例：x0=100; 0<1<x0 原生 True，修复前受限执行器得 False。"""
        source = (
            "def score_actions(view):\n"
            "    x0 = 100\n"
            "    result = 0 < 1 < x0\n"
            "    return {'status': 'ABSTAIN', 'reason': 'chain-true' if result else 'chain-false'}\n"
        )
        kind, batch, counted = _run(source)
        assert kind == "returned"
        assert batch.reason == "chain-true", "链式比较捕获候选同名局部变量：{0!r}".format(
            batch.reason
        )

    @pytest.mark.parametrize("case", _CHAIN_CASES, ids=[case[0] for case in _CHAIN_CASES])
    def test_differential_against_native_python(
        self, case: Tuple[str, List[Tuple[int, str]], str, List[Tuple[int, str]], str]
    ) -> None:
        name, setup, expr, tail, reason_expr = case
        expected = _native_reason(setup, expr, tail, reason_expr)
        source = _restricted_source(setup, expr, tail, reason_expr)
        kind, batch, counted = _run(source, budget=1_000_000)
        assert kind == "returned", "{0}: 受限执行器异常 {1!r}".format(name, batch)
        assert batch.reason == expected, "{0}: 受限 {1!r} ≠ 原生 {2!r}".format(
            name, batch.reason, expected
        )

    def test_native_baseline_values_are_as_expected(self) -> None:
        """差分基准自检：原生结果就是复审给出的语义（True/False 等）。"""
        assert _native_reason([(0, "x0 = 100")], "0 < 1 < x0") == "True"
        assert _native_reason([(0, "x0 = 100")], "5 < 1 < x0") == "False"
        assert (
            _native_reason(_BUMP_SETUP, "bump(box, 0) < bump(box, 1) < bump(box, 2)",
                           [(0, "visited = len(box)")], "f'{value}-{visited}'")
            == "True-3"
        )


# ===========================================================================
# N3 · 集合字面量/推导式/构造器/集合运算的迭代顺序必须与 hash 种子无关
# ===========================================================================

WORDS = ["delta", "alpha", "charlie", "bravo", "echo"]


def _words_source(expr: str, name: str = "words") -> str:
    return (
        "def score_actions(view):\n"
        "    {0} = {1}\n".format(name, expr)
        + "    text = ''\n"
        "    for word in {0}:\n".format(name)
        + "        text = text + word + '|'\n"
        "    return {'status': 'ABSTAIN', 'reason': text}\n"
    )


SET_LITERAL_SOURCE = _words_source("{'delta', 'alpha', 'charlie', 'bravo', 'echo'}")
SET_COMPREHENSION_SOURCE = _words_source(
    "{word for word in ['delta', 'alpha', 'charlie', 'bravo', 'echo']}"
)
SET_CONSTRUCTOR_SOURCE = _words_source(
    "set(['delta', 'alpha', 'charlie', 'bravo', 'echo'])"
)
FROZENSET_SOURCE = _words_source("frozenset(['delta', 'alpha', 'charlie'])")
SET_UNION_SOURCE = _words_source("{'delta', 'alpha'} | {'charlie', 'alpha'}")
SET_INTERSECTION_SOURCE = _words_source("{'delta', 'alpha'} & {'alpha', 'charlie'}")
SET_DIFFERENCE_SOURCE = _words_source("{'delta', 'alpha', 'charlie'} - {'alpha'}")
SET_XOR_SOURCE = _words_source("{'delta', 'alpha'} ^ {'alpha', 'charlie'}")
SET_INPLACE_UNION_SOURCE = (
    "def score_actions(view):\n"
    "    words = {'delta', 'alpha'}\n"
    "    words = words | {'charlie'}\n"
    "    text = ''\n"
    "    for word in words:\n"
    "        text = text + word + '|'\n"
    "    return {'status': 'ABSTAIN', 'reason': text}\n"
)
SET_ADD_SOURCE = (
    "def score_actions(view):\n"
    "    words = set(['delta', 'alpha'])\n"
    "    words.add('charlie')\n"
    "    text = ''\n"
    "    for word in words:\n"
    "        text = text + word + '|'\n"
    "    return {'status': 'ABSTAIN', 'reason': text}\n"
)
SET_LITERAL_ADD_SOURCE = (
    "def score_actions(view):\n"
    "    words = {'delta', 'alpha'}\n"
    "    words.add('charlie')\n"
    "    text = ''\n"
    "    for word in words:\n"
    "        text = text + word + '|'\n"
    "    return {'status': 'ABSTAIN', 'reason': text}\n"
)
SET_MEMBERSHIP_SOURCE = (
    "def score_actions(view):\n"
    "    words = {'delta', 'alpha', 'charlie'}\n"
    "    hits = 0\n"
    "    if 'delta' in words:\n"
    "        hits = hits + 1\n"
    "    size = len(words)\n"
    "    same = words == {'charlie', 'delta', 'alpha'}\n"
    "    return {'status': 'ABSTAIN', 'reason': f'{hits}-{size}-{same}'}\n"
)
DICT_LITERAL_SOURCE = (
    "def score_actions(view):\n"
    "    table = {'delta': 1, 'alpha': 2, 'charlie': 3}\n"
    "    text = ''\n"
    "    for key in table:\n"
    "        text = text + key + '|'\n"
    "    return {'status': 'ABSTAIN', 'reason': text}\n"
)
DICT_COMPREHENSION_SOURCE = (
    "def score_actions(view):\n"
    "    table = {key: 1 for key in ['delta', 'alpha', 'charlie']}\n"
    "    text = ''\n"
    "    for key in table:\n"
    "        text = text + key + '|'\n"
    "    return {'status': 'ABSTAIN', 'reason': text}\n"
)
SORTED_SET_SOURCE = (
    "def score_actions(view):\n"
    "    words = {'delta', 'alpha', 'charlie'}\n"
    "    picked = sorted(words)\n"
    "    text = ''\n"
    "    for word in picked:\n"
    "        text = text + word + '|'\n"
    "    return {'status': 'ABSTAIN', 'reason': text}\n"
)

#: 入口 → （候选源码, 期望顺序：插入/源序，或字典的插入序）
_ORDER_EXPECTATIONS: List[Tuple[str, str, str]] = [
    ("literal", SET_LITERAL_SOURCE, "delta|alpha|charlie|bravo|echo|"),
    ("comprehension", SET_COMPREHENSION_SOURCE, "delta|alpha|charlie|bravo|echo|"),
    ("constructor", SET_CONSTRUCTOR_SOURCE, "delta|alpha|charlie|bravo|echo|"),
    ("frozenset", FROZENSET_SOURCE, "delta|alpha|charlie|"),
    ("union", SET_UNION_SOURCE, "delta|alpha|charlie|"),
    ("intersection", SET_INTERSECTION_SOURCE, "alpha|"),
    ("difference", SET_DIFFERENCE_SOURCE, "delta|charlie|"),
    ("xor", SET_XOR_SOURCE, "delta|charlie|"),
    ("inplace-union", SET_INPLACE_UNION_SOURCE, "delta|alpha|charlie|"),
    ("add", SET_ADD_SOURCE, "delta|alpha|charlie|"),
    ("literal-add", SET_LITERAL_ADD_SOURCE, "delta|alpha|charlie|"),
    ("dict-literal", DICT_LITERAL_SOURCE, "delta|alpha|charlie|"),
    ("dict-comprehension", DICT_COMPREHENSION_SOURCE, "delta|alpha|charlie|"),
    ("sorted-set", SORTED_SET_SOURCE, "alpha|charlie|delta|"),
]

_HASHSEED_SCRIPT = """
import json, sys
sys.path.insert(0, {src!r})
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.action_value_seeds import build_sample_view
SOURCES = {sources!r}
view = build_sample_view()
result = {{}}
for name, source in sorted(SOURCES.items()):
    executor = ActionValueExecutor(source, name="r8-hashseed")
    batch = executor.score(view)
    result[name] = [batch.reason, executor.last_operation_count]
print(json.dumps(result, sort_keys=True))
"""


class TestN3DeterministicSetIteration:
    @pytest.mark.parametrize("entry", [case[0] for case in _ORDER_EXPECTATIONS])
    def test_iteration_order_is_source_order(self, entry: str) -> None:
        source, expected = next(
            (case[1], case[2]) for case in _ORDER_EXPECTATIONS if case[0] == entry
        )
        kind, batch, counted = _run(source, budget=1_000_000)
        assert kind == "returned", "{0}: {1!r}".format(entry, batch)
        assert batch.reason == expected, "{0}: {1!r} ≠ 源序 {2!r}".format(
            entry, batch.reason, expected
        )

    def test_set_semantics_preserved_after_determinization(self) -> None:
        kind, batch, counted = _run(SET_MEMBERSHIP_SOURCE)
        assert kind == "returned"
        assert batch.reason == "1-3-True"

    def test_hashseed_consistency_across_processes(self) -> None:
        """复审同口径：PYTHONHASHSEED 1/2/123 下逐字节一致。"""
        outputs = {}
        for value in ("1", "2", "123"):
            outputs[value] = _run_hashseed_subprocess(value)
        assert len(set(outputs.values())) == 1, "跨 PYTHONHASHSEED 结果不一致：{0}".format(
            json.dumps(outputs, ensure_ascii=False, sort_keys=True)
        )
        payload = json.loads(outputs["1"])
        assert set(payload) == {case[0] for case in _ORDER_EXPECTATIONS}
        for name, (reason, ops) in payload.items():
            assert ops > 0, name


def _run_hashseed_subprocess(seed: str) -> str:
    root = Path(__file__).resolve().parents[3]
    sources = {case[0]: case[1] for case in _ORDER_EXPECTATIONS}
    script = _HASHSEED_SCRIPT.format(src=str(root / "src"), sources=sources)
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()
