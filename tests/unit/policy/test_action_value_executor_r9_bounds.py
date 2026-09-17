"""R9 复审 S1（P1）专属回归：结构工作量守卫的单元口径（含标量叶）与宽浅结构上限。

权威材料：
- review/llm-guided-heuristic-route-2026-09-15/R8-REPAIR-REREVIEW-2026-09-17.md §3 S1；
- 同目录 R9-FIX-PLAN-2026-09-17.md §3（P1 EXEC 执行器）。

复审原样反例（固定版本 3dc7489a 实测）：依次执行 row=(1,)*1024、key=(row,)*256、
lookup={key: 1} 正常返回、只计 262 operations；展开标量叶 262144 个，超过声明的
MAX_DATA_CELLS=131072，但 structure_cost(key) 只返回 257——只有容器节点与长字符串
计费，整数等标量叶出栈不计数，而 CPython 的原生元组哈希仍逐项访问这些叶。

本文件把该反例与四条修复要求固化为回归：
1) 结构遍历对每次展开的节点（含标量叶）计数、限额、计费，容器与标量叶同口径；
2) 共享引用按出现次数累积（原生哈希/比较不去重，所以不做 id 记忆化）；
3) 守卫自身有界，并在原生哈希/比较之前拒绝超额数据；
4) 热路径（普通标量、短字符串）保持常数成本。

断言只经公开入口：ActionValueExecutor(source[, max_operations])、score(view)、
last_operation_count、WorkloadExceeded，以及执行器公开的计费函数 structure_cost
（与复审探针同口径）。期望值来自规格（单元数 = 展开节点数、上限 MAX_DATA_CELLS）
与原生语义（原生哈希逐项访问共享引用），不来自实现内部状态；数字均为实测值。
"""

from __future__ import annotations

from typing import Optional, Tuple

import pytest

from hangma_bot.policy.action_value_executor import (
    MAX_COUNTED_OPERATIONS,
    MAX_DATA_CELLS,
    ActionValueExecutor,
    WorkloadExceeded,
    structure_cost,
)
from hangma_bot.policy.action_value_seeds import build_sample_view

_NAME = "r9-s1"
#: 深度上限内允许的最大容器层数：x=(1,1) 后重复 16 次得到 17 层，超出 12 层上限。
DEEP_DEPTH = 16


def _run(source: str, budget: Optional[int] = None) -> Tuple[str, object, int]:
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
    except BaseException as exc:  # noqa: BLE001 - 记录实际类型用于判定
        return type(exc).__name__, str(exc), executor.last_operation_count
    return "returned", batch, executor.last_operation_count


def _shared_key_source(row_len: int, occurrences: int) -> str:
    """row=(1,)*row_len 复用 occurrences 次作为字典键（宽而浅、共享引用）。

    该键的结构单元数 = 1（外层元组） + occurrences（内层元组引用）
    + row_len*occurrences（标量叶）。
    """
    return (
        "def score_actions(view):\n"
        + "    row = (1,) * {0}\n".format(row_len)
        + "    key = (row,) * {0}\n".format(occurrences)
        + "    table = {key: 1}\n"
        + "    return {'status': 'ABSTAIN', 'reason': 'wide-key'}\n"
    )


def _key_cells(row_len: int, occurrences: int) -> int:
    """规格口径的键单元数：容器节点与标量叶同口径各计 1。"""
    return 1 + occurrences + row_len * occurrences


def _deep_tuple_block(depth: int = DEEP_DEPTH) -> str:
    """depth 层重复嵌套元组 x（既有反例的紧凑形式）。"""
    return (
        "    x = (1, 1)\n"
        + "    for i in range({0}):\n".format(depth)
        + "        x = (x, x)\n"
    )


# ===========================================================================
# 复审原反例：宽而浅的共享结构必须在原生哈希之前被拒绝
# ===========================================================================


class TestS1ReviewCounterexample:
    """复审反例原文：262144 个展开叶只算 262 operations 并正常返回。"""

    WIDE_SHARED_SOURCE = (
        "def score_actions(view):\n"
        "    row = (1,) * 1024\n"
        "    key = (row,) * 256\n"
        "    lookup = {key: 1}\n"
        "    return {'status': 'ABSTAIN', 'reason': 'wide hash completed'}\n"
    )

    def test_review_counterexample_rejected_before_hashing(self) -> None:
        kind, detail, counted = _run(self.WIDE_SHARED_SOURCE)
        assert kind == "exceeded", "宽共享结构仍合法返回：{0!r}".format(detail)
        # 拒绝类型与位置：字典键的结构单元守卫，报出单元上限数值。
        assert "字典键" in str(detail), str(detail)
        assert str(MAX_DATA_CELLS) in str(detail), str(detail)
        assert "单元上限" in str(detail), str(detail)
        # 提前拒绝（而非耗尽预算）：说明守卫发生在原生哈希之前。
        assert counted < MAX_COUNTED_OPERATIONS, counted

    def test_rejection_precedes_native_hash_unhashable_key(self) -> None:
        """位置证据：键含列表（原生哈希必然 TypeError）时仍须先报结构超限。

        若守卫被放到原生哈希之后，CPython 会先抛 TypeError（经骨架转为
        ValueError），观察到的拒绝类型就不再是结构超限。
        """
        source = (
            "def score_actions(view):\n"
            "    row = [1] * 4096\n"
            "    key = (row,) * 64\n"
            "    table = {key: 1}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'unhashable-key'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "键含列表时未先报结构超限：{0!r}".format(detail)
        assert "单元上限" in str(detail), str(detail)
        assert counted < MAX_COUNTED_OPERATIONS, counted

    def test_boundary_is_exactly_the_declared_cell_limit(self) -> None:
        """限额外 1 个单元即拒绝：m=30/n=4096 得 126,977 放行，m=31 得 131,073 拒绝。"""
        allowed_cells = _key_cells(30, 4096)
        rejected_cells = _key_cells(31, 4096)
        assert allowed_cells == 126_977 and rejected_cells == MAX_DATA_CELLS + 1
        kind, batch, counted = _run(_shared_key_source(30, 4096), budget=1_000_000)
        assert kind == "returned", "限内结构被误拒：{0!r}".format(batch)
        assert batch.reason == "wide-key"
        assert counted >= allowed_cells, "限内结构未按单元计费：{0}".format(counted)
        kind, detail, counted = _run(_shared_key_source(31, 4096))
        assert kind == "exceeded", "超出 1 个单元仍放行：{0!r}".format(detail)
        assert "单元上限" in str(detail), str(detail)
        assert counted < MAX_COUNTED_OPERATIONS, counted


# ===========================================================================
# 标量叶与共享引用：单元口径一致、按出现次数累积
# ===========================================================================


class TestS1ScalarLeafCells:
    def test_shared_references_accumulate_by_occurrence(self) -> None:
        """同一元组被引用 8 次：按 8 次真实遍历计费（去重实现只算 1 次）。"""
        cells = _key_cells(4096, 8)
        assert cells == 32_777
        kind, batch, counted = _run(_shared_key_source(4096, 8))
        assert kind == "returned", "{0!r}".format(batch)
        assert counted >= cells, "共享引用被去重少算：{0} < {1}".format(counted, cells)

    @pytest.mark.parametrize("row_len,occurrences", [(8, 64), (8, 256), (8, 1024)])
    def test_units_scale_with_leaf_count(self, row_len: int, occurrences: int) -> None:
        cells = _key_cells(row_len, occurrences)
        kind, batch, counted = _run(_shared_key_source(row_len, occurrences))
        assert kind == "returned", "{0!r}".format(batch)
        # 计费 = 结构单元 + 固定的构造/返回开销（实测 +5）。
        assert cells <= counted <= cells + 64, (cells, counted)

    def test_flat_wide_key_counted_by_leaf_units(self) -> None:
        """平坦宽结构（无共享）同样按叶计单元：4096 项元组 = 1 + 4096。"""
        value = tuple(range(4096))
        assert structure_cost(value, "平坦宽键探针") == 4097
        assert structure_cost((), "空元组探针") == 1

    def test_wide_flat_key_billed_in_execution(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    key = tuple(range(4096))\n"
            "    table = {key: 1}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'flat-wide'}\n"
        )
        kind, batch, counted = _run(source)
        assert kind == "returned", "{0!r}".format(batch)
        # range(4096) 4096 + tuple() 4096 + 字典键结构 4097 ≈ 12,289（实测 12,294）。
        assert counted >= 12_000, counted


# ===========================================================================
# 热路径：普通标量与短字符串保持常数成本
# ===========================================================================


class TestS1HotPathCost:
    def test_top_level_scalars_and_short_strings_are_free(self) -> None:
        for value in (5, -3, 0, 2.5, True, False, None, "action_key", "a"):
            assert structure_cost(value, "热路径探针") == 0, repr(value)
        # 长字符串仍按 64 字符一段（顶层）。
        assert structure_cost("a" * 64, "热路径探针") == 1
        assert structure_cost("a" * 63, "热路径探针") == 0

    def test_nested_nodes_each_count_one_unit(self) -> None:
        assert structure_cost([1, 2, 3], "探针") == 4
        assert structure_cost(("a", "b"), "探针") == 3
        assert structure_cost((("x",),), "探针") == 3
        assert structure_cost(("a" * 100,), "探针") == 2

    def test_scalar_comparison_and_short_key_lookup_stay_cheap(self) -> None:
        scalar_source = (
            "def score_actions(view):\n"
            "    hits = 0\n"
            "    for i in range(50):\n"
            "        if i > 10:\n"
            "            hits = hits + 1\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{hits}'}\n"
        )
        kind, batch, counted = _run(scalar_source)
        assert kind == "returned" and batch.reason == "39"
        assert counted < 1_000, "标量比较计费膨胀：{0}".format(counted)
        lookup_source = (
            "def score_actions(view):\n"
            "    table = {'a': 1, 'b': 2}\n"
            "    total = 0\n"
            "    for i in range(100):\n"
            "        total = total + table.get('a')\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{total}'}\n"
        )
        kind, batch, counted = _run(lookup_source)
        assert kind == "returned" and batch.reason == "100"
        assert counted < 1_000, "短键查询计费膨胀：{0}".format(counted)


# ===========================================================================
# 既有反例全部保留（深键 / 序列求和 / 方法别名 / 格式宽度 / 原生哈希守卫）
# ===========================================================================


class TestS1ExistingCounterexamplesPreserved:
    def test_deep_key_dict_literal_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    table = {x: 1}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-dict'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded" and "深度" in str(detail), str(detail)
        assert counted < MAX_COUNTED_OPERATIONS, counted

    def test_deep_element_set_literal_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    bag = {x}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-set'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", str(detail)
        assert counted < MAX_COUNTED_OPERATIONS, counted

    def test_deep_subscript_key_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    table = {'a': 1}\n"
            "    hit = table[x]\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-sub'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", str(detail)
        assert counted < MAX_COUNTED_OPERATIONS, counted

    def test_deep_membership_element_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            + _deep_tuple_block()
            + "    bag = set(['a'])\n"
            "    hit = x in bag\n"
            "    return {'status': 'ABSTAIN', 'reason': 'deep-in'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", str(detail)

    def test_sequence_start_sum_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    rows = [(1,) * 128] * 64\n"
            "    total = sum(rows, ())\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{len(total)}'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded" and "序列起始值" in str(detail), str(detail)
        assert counted < MAX_COUNTED_OPERATIONS, counted

    def test_bound_method_alias_scan_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    values = list(range(4096))\n"
            "    count = values.count\n"
            "    hits = 0\n"
            "    for i in range(40):\n"
            "        hits = hits + count(999999)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'alias-count'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", str(detail)
        assert counted > MAX_COUNTED_OPERATIONS, counted

    def test_format_width_rejected_before_allocation(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    text = f'{1:>200000000}'\n"
            "    return {'status': 'ABSTAIN', 'reason': 'width'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", str(detail)
        assert counted < MAX_COUNTED_OPERATIONS, counted

    def test_nested_tuple_equality_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    a = (0, 0)\n"
            "    b = (0, 0)\n"
            + "    for i in range({0}):\n".format(DEEP_DEPTH)
            + "        a = (a, a)\n"
            "        b = (b, b)\n"
            "    same = a == b\n"
            "    return {'status': 'ABSTAIN', 'reason': 'nested-eq'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", str(detail)
        assert counted < MAX_COUNTED_OPERATIONS, counted

    def test_sample_view_comparison_still_allowed(self) -> None:
        """限深内的观察数据不受新增叶计费误伤（真实输入的回归护栏）。"""
        source = (
            "def score_actions(view):\n"
            "    rows = view['actions']\n"
            "    same = rows[0] == rows[1]\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{same}'}\n"
        )
        kind, batch, counted = _run(source)
        assert kind == "returned", str(batch)
        assert counted < 10_000, counted

