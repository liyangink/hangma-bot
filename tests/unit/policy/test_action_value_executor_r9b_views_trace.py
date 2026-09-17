"""R9/S1b 定向回归：集合式字典视图通道、候选返回值（trace）通道、字符串产出速率。

权威材料：
- review/llm-guided-heuristic-route-2026-09-15/R9-FIX-PLAN-2026-09-17.md §3（P1 EXEC）；
- 独立对抗性验证 evidence/v4-impl/r9-fixes/P1-exec-verify/VERIFY-REPORT.md：S1 修复的
  第三种绕过形状 dict_keys/dict_items 视图逃逸类型分派，以及同一执行器的
  trace 通道与字符串产出速率两项计费之外的工作。

修复前实测（验证者独立复现；本文件把规模缩小后固化为回归）：
- 128 键 × 每值 (index,)*4096 的两个字典循环比较 left.items() == right.items()：
  37,541 / 100,000 operations **正常返回**、墙钟 1.672 s（超 1 秒动作窗口）；
  同一个 dict 本体会被 131072 单元上限拒绝——逃逸发生在「取视图」之后。
- trace 通道：24 operations → 201,524,908 字节序列化 / 406 MB 峰值。
- 字符串产出：`"x"*32768 + "y"*32768` 每次拷贝 64 KiB 只计 1 个单元。

断言只经公开入口：ActionValueExecutor(source[, max_operations])、score(view)、
last_operation_count、WorkloadExceeded、结构计费函数 structure_cost；trace 通道另
经 ScoreBatch 构造期合同（ValueError）与 tracemalloc 峰值。数字均为实测值。
"""

from __future__ import annotations

import dataclasses
import tracemalloc
from typing import Any, Optional, Tuple

import pytest

from hangma_bot.policy.action_value import ActionScore, ScoreBatch
from hangma_bot.policy.action_value_executor import (
    MAX_COUNTED_OPERATIONS,
    MAX_DATA_CELLS,
    MAX_STRING_CHARS,
    ActionValueExecutor,
    WorkloadExceeded,
    structure_cost,
)
from hangma_bot.policy.action_value_seeds import build_sample_view

_NAME = "r9b-s1b"
#: 视图反例的缩小规模：32 键 × 每值 4096 叶 ≈ 131,136 单元 > 上限（构建只需约 70 个操作）。
VIEW_ENTRIES = 32
VIEW_WIDTH = 4096


class _Opaque:
    """无 len、不可调用的未知类型：候选受限子集内造不出，只能由视图注入。"""

    __slots__ = ()


def _run(source: str, view: Any = None, budget: Optional[int] = None) -> Tuple[str, Any, int]:
    """经公开入口执行候选；返回 (结果种类, 批次或消息, 实测计数)。"""
    executor = (
        ActionValueExecutor(source, name=_NAME)
        if budget is None
        else ActionValueExecutor(source, name=_NAME, max_operations=budget)
    )
    target = build_sample_view() if view is None else view
    try:
        batch = executor.score(target)
    except WorkloadExceeded as exc:
        return "exceeded", str(exc), executor.last_operation_count
    except BaseException as exc:  # noqa: BLE001 - 记录实际类型用于判定
        return type(exc).__name__, str(exc), executor.last_operation_count
    return "returned", batch, executor.last_operation_count


def _peak_bytes_during(source: str) -> Tuple[str, int, int]:
    """执行候选并返回 (结果种类, 峰值字节, 实测计数)。"""
    executor = ActionValueExecutor(source, name=_NAME + "-peak")
    tracemalloc.start()
    try:
        try:
            executor.score(build_sample_view())
            kind = "returned"
        except WorkloadExceeded:
            kind = "exceeded"
        except BaseException as exc:  # noqa: BLE001 - 记录实际类型用于判定
            kind = type(exc).__name__
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return kind, peak, executor.last_operation_count


def _views_source(comparison: str, entries: int = VIEW_ENTRIES, width: int = VIEW_WIDTH,
                  rounds: int = 200) -> str:
    """验证者反例的缩小版：两个等值但不同对象的字典，比较其视图。"""
    if comparison == "items":
        left = "    left = {{index: (index,) * {1} for index in range({0})}}\n"
        right = "    right = {{index: (index,) * {1} for index in range({0})}}\n"
        expr = "left.items() == right.items()"
    else:
        left = "    left = {{(index,) * {1}: 1 for index in range({0})}}\n"
        right = "    right = {{(index,) * {1}: 1 for index in range({0})}}\n"
        expr = "left.keys() == right.keys()"
    return (
        "def score_actions(view):\n"
        + left.format(entries, width)
        + right.format(entries, width)
        + "    hits = 0\n"
        + "    for round_index in range({0}):\n".format(rounds)
        + "        if {0}:\n".format(expr)
        + "            hits = hits + 1\n"
        + "    return {'status': 'ABSTAIN', 'reason': 'view'}\n"
    )


def _patched_view_with_opaque_branch() -> Any:
    """把无 len 的未知对象塞进 dict 型分支的 probe 键（验证者 D9 的同一通道）。"""
    view = build_sample_view()
    patched = []
    for action in view.actions:
        if action.followup_branches:
            branch = dict(action.followup_branches[0])
            branch["probe"] = _Opaque()
            patched.append(dataclasses.replace(action, followup_branches=(branch,)))
        else:
            patched.append(action)
    return dataclasses.replace(view, actions=tuple(patched))


# ===========================================================================
# 一、集合式字典视图：dict_keys / dict_items / dict_values 不再逃逸类型分派
# ===========================================================================


class TestS1bViewChannel:
    """验证者反例（J1/J2/J3）：视图判 0 单元 → 原生逐项比较在计费之外跑满墙钟。"""

    def test_items_view_comparison_rejected_before_native_compare(self) -> None:
        kind, detail, counted = _run(_views_source("items"))
        assert kind == "exceeded", "items 视图比较仍放行：{0!r}".format(detail)
        assert "单元上限" in str(detail) and "比较" in str(detail), str(detail)
        assert counted < MAX_COUNTED_OPERATIONS, counted

    def test_keys_view_comparison_rejected_before_native_compare(self) -> None:
        # 宽元组键在**构建期**就按结构单元计费，默认预算下会先被计数预算拦下；
        # 这里显式提高操作预算，验证拒绝来自结构上限（视图展开）而不是预算。
        kind, detail, counted = _run(_views_source("keys"), budget=1_000_000)
        assert kind == "exceeded", "keys 视图比较仍放行：{0!r}".format(detail)
        assert "单元上限" in str(detail), str(detail)

    def test_view_units_match_element_expansion(self) -> None:
        """视图按底层键/键值对展开：单元数与「每个展开节点各计 1」逐项相等。"""
        small = {index: (index,) * 64 for index in range(8)}
        large = {index: (index,) * 1024 for index in range(8)}
        wide_keys = {(index,) * 64: 1 for index in range(8)}
        # items：1 + Σ(键 1 + 值容器 1 + 叶 64)；keys：1 + Σ 键；values：1 + Σ 值。
        assert structure_cost(small.items(), "视图探针") == 1 + 8 * (1 + 1 + 64)
        assert structure_cost(large.items(), "视图探针") == 1 + 8 * (1 + 1 + 1024)
        assert structure_cost(small.keys(), "视图探针") == 1 + 8 * 1
        assert structure_cost(small.values(), "视图探针") == 1 + 8 * (1 + 64)
        assert structure_cost(wide_keys.keys(), "视图探针") == 1 + 8 * (1 + 64)
        # 三种视图都不再返回 0（修复前 dict_keys/dict_items/dict_values 全部判 0）。
        for view in (small.keys(), small.items(), small.values()):
            assert structure_cost(view, "视图探针") > 0

    def test_below_limit_view_comparison_is_billed_per_element(self) -> None:
        """限额内的视图比较仍可用，但必须按元素规模计费（不是 1 次操作）。"""
        source = _views_source("items", entries=8, width=4096, rounds=1)
        kind, detail, counted = _run(source)
        assert kind == "returned", "限额内视图比较被误拒：{0!r}".format(detail)
        assert counted >= 2 * (1 + 8 * (1 + 1 + 4096)), counted

    def test_view_as_dict_key_guarded_before_native_hash(self) -> None:
        """视图不可哈希：超限时观察到的必须是结构拒绝，而不是原生 TypeError。"""
        source = (
            "def score_actions(view):\n"
            + "    left = {{index: (index,) * {1} for index in range({0})}}\n".format(
                VIEW_ENTRIES, VIEW_WIDTH)
            + "    table = {left.items(): 1}\n"
            "    return {'status': 'ABSTAIN', 'reason': 'view-key'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded", "视图作字典键未先守卫：{0!r}".format(detail)
        assert "字典键" in str(detail), str(detail)

    def test_view_as_set_element_guarded_before_native_hash(self) -> None:
        source = (
            "def score_actions(view):\n"
            + "    left = {{index: (index,) * {1} for index in range({0})}}\n".format(
                VIEW_ENTRIES, VIEW_WIDTH)
            + "    bag = set([left.items()])\n"
            "    return {'status': 'ABSTAIN', 'reason': 'view-set'}\n"
        )
        kind, detail, counted = _run(source)
        assert kind == "exceeded" and "集合元素" in str(detail), str(detail)

    @pytest.mark.parametrize(
        "entry",
        [
            "bag = set([left.items()])",
            "table = dict([(left.items(), 1)])",
            "picked = sorted([left.items(), left.items()])",
            "hit = left.items() in [left.items()]",
            "text = f'{left.items()}'",
            "text = '%s' % (left.items(),)",
            "rows = [left.items()]\n    hit = rows.count(left.items())",
            "rows = [left.items()]\n    hit = rows.index(left.items())",
        ],
    )
    def test_every_downstream_entry_is_guarded_before_native_work(self, entry: str) -> None:
        """构造 / 排序 / 成员 / 格式化 / .count / .index 各入口都必须先守卫。"""
        source = (
            "def score_actions(view):\n"
            + "    left = {{index: (index,) * {1} for index in range({0})}}\n".format(
                VIEW_ENTRIES, VIEW_WIDTH)
            + "    " + entry + "\n"
            + "    return {'status': 'ABSTAIN', 'reason': 'entry'}\n"
        )
        kind, detail, counted = _run(source, budget=1_000_000)
        assert kind == "exceeded", "{0} 未先守卫：{1!r}".format(entry, detail)
        assert "单元上限" in str(detail) or "超限" in str(detail), str(detail)

    def test_list_and_tuple_materialization_billed_by_length(self) -> None:
        """list()/tuple() 物化视图按长度计费（不展开成 131k 单元，也不免费）。"""
        source = (
            "def score_actions(view):\n"
            + "    left = {{index: (index,) * {1} for index in range({0})}}\n".format(
                VIEW_ENTRIES, VIEW_WIDTH)
            + "    rows = list(left.items())\n"
            + "    picked = tuple(left.keys())\n"
            + "    return {'status': 'ABSTAIN', 'reason': f'{len(rows) + len(picked)}'}\n"
        )
        kind, batch, counted = _run(source, budget=1_000_000)
        assert kind == "returned", "{0!r}".format(batch)
        assert batch.reason == str(2 * VIEW_ENTRIES)
        assert counted >= 2 * VIEW_ENTRIES, counted

    def test_hot_path_items_iteration_stays_cheap(self) -> None:
        """只读遍历 table.items() 保持逐项计费的既有量级（修复不打死热路径）。"""
        source = (
            "def score_actions(view):\n"
            "    table = {index: index for index in range(4096)}\n"
            "    total = 0\n"
            "    for key, value in table.items():\n"
            "        total = total + value\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{total}'}\n"
        )
        kind, batch, counted = _run(source)
        assert kind == "returned" and batch.reason == "8386560"
        assert 20_000 <= counted <= 40_000, "热路径迭代计费量级变化：{0}".format(counted)


# ===========================================================================
# 二、兜底分支不再「未知 ⇒ 0」
# ===========================================================================


class TestS1bUnknownTypeFallback:
    def test_unknown_shape_billed_at_the_cell_limit(self) -> None:
        assert structure_cost(_Opaque(), "未知类型探针") == MAX_DATA_CELLS + 1

    def test_sized_and_callable_fallbacks(self) -> None:
        assert structure_cost(range(10), "兜底探针") == 10  # 有 len：按长度，不展开
        assert structure_cost(len, "兜底探针") == 1  # 可调用：身份哈希与比较 O(1)
        assert structure_cost(5, "兜底探针") == 0  # 标量快路径不变
        assert structure_cost("action_key", "兜底探针") == 0

    def test_unknown_shape_in_view_is_rejected_by_metering(self) -> None:
        """执行器通道：未知形状按上限+1 计费 → 默认预算下必然整批拒绝。"""
        source = (
            "def score_actions(view):\n"
            "    seen = set()\n"
            "    for action in view['actions']:\n"
            "        branches = action['followup_branches']\n"
            "        if branches is not None:\n"
            "            for branch in branches:\n"
            "                seen.add(branch['probe'])\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{len(seen)}'}\n"
        )
        kind, detail, counted = _run(source, view=_patched_view_with_opaque_branch())
        assert kind == "exceeded", "未知形状仍放行：{0!r}".format(detail)
        assert counted > MAX_COUNTED_OPERATIONS, counted


# ===========================================================================
# 三、候选返回值（trace）通道：序列化前有界预判 + 计费
# ===========================================================================


#: 样例视图只有 3 个动作：每 entry 约 65,795 单元 × 3 > 100,000（构建仅约 20 个操作）。
def _trace_source(outer: int = 128, inner: int = 128, leaf_chars: int = 256) -> str:
    """共享列表放大的 trace（验证者 I 系列形状的缩小版）。"""
    return (
        "def score_actions(view):\n"
        "    leaf = 'x' * {2}\n"
        "    inner = [leaf] * {1}\n"
        "    outer = [inner] * {0}\n"
        "    trace = {{'a': outer}}\n"
        "    entries = []\n"
        "    for action in view['actions']:\n"
        "        entries.append({{'action_key': action['action_key'],\n"
        "                        'score': 1.0, 'trace': trace}})\n"
        "    return {{'status': 'SCORED', 'entries': entries}}\n"
    ).format(outer, inner, leaf_chars)


class TestS1bTraceChannel:
    def test_oversized_trace_rejected_without_big_serialization(self) -> None:
        """修复前：24 operations → 201 MB 序列化 / 406 MB 峰值；现在必须提前拒绝。"""
        kind, peak, counted = _peak_bytes_during(_trace_source())
        assert kind == "exceeded", "超大 trace 未被拒绝：{0}".format(kind)
        assert counted <= MAX_COUNTED_OPERATIONS + 4096, counted
        assert peak < 8 * 1024 * 1024, "计费之外的序列化峰值 {0} 字节".format(peak)

    def test_trace_nodes_are_charged_to_the_candidate(self) -> None:
        """返回值同样计费：放大 trace 的操作数不再停留在 24。"""
        kind, peak, counted = _peak_bytes_during(_trace_source())
        assert counted >= 1_000, "返回值未按结构计费：{0}".format(counted)

    def test_small_trace_still_accepted(self) -> None:
        kind, batch, counted = _run(_trace_source(outer=2, inner=2, leaf_chars=8))
        assert kind == "returned", "{0!r}".format(batch)
        assert counted < 1_000, counted

    def test_batch_construction_precheck_rejects_before_serialization(self) -> None:
        """不经执行器的构造路径同样受保护（ScoreBatch 合同层的有界预判）。"""
        leaf = "x" * 4096
        inner = [leaf] * 64
        outer = [inner] * 64
        tracemalloc.start()
        try:
            with pytest.raises(ValueError, match="序列化|上限"):
                entry = ActionScore(action_key="a", score=1.0, trace={"a": outer})
                ScoreBatch(status="SCORED", entries=(entry,))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert peak < 4 * 1024 * 1024, "预判前就分配了 {0} 字节".format(peak)


# ===========================================================================
# 四、字符串产出速率：按 64 字符一段计费（拼接 / 重复 / 格式化同口径）
# ===========================================================================


class TestS1bStringProductionRate:
    def test_concat_and_repeat_charged_per_64_chars(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    text = 'x' * 32768 + 'y' * 32768\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{len(text)}'}\n"
        )
        kind, batch, counted = _run(source)
        assert kind == "returned" and batch.reason == "65536"
        # 重复 32768/64 + 32768/64 + 拼接 65536/64 = 512 + 512 + 1024 = 2,048。
        assert counted >= 2_048, "字符串产出未按字节计费：{0}".format(counted)

    def test_concat_loop_cannot_move_hundreds_of_megabytes(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    total = 0\n"
            "    for i in range(15000):\n"
            "        text = 'x' * 32768 + 'y' * 32768\n"
            "        total = total + len(text)\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{total}'}\n"
        )
        kind, peak, counted = _peak_bytes_during(source)
        assert kind == "exceeded", "拼接循环未被拒绝：{0}".format(kind)
        assert peak < 8 * 1024 * 1024, "峰值 {0} 字节".format(peak)

    def test_format_width_charged_per_byte(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    a = f'{1:>65536}'\n"
            "    b = '%65536d' % 1\n"
            "    return {'status': 'ABSTAIN', 'reason': f'{len(a) + len(b)}'}\n"
        )
        kind, batch, counted = _run(source)
        assert kind == "returned" and batch.reason == str(2 * MAX_STRING_CHARS)
        # 宽度填充 65,536 字符 = 1,024 单元/次（修复前每次只计 1）。
        assert counted >= 2 * (MAX_STRING_CHARS // 64), counted

    def test_hot_path_short_string_building_unchanged(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    text = ''\n"
            "    for word in ['delta', 'alpha', 'charlie']:\n"
            "        text = text + word + '|'\n"
            "    return {'status': 'ABSTAIN', 'reason': text}\n"
        )
        kind, batch, counted = _run(source)
        assert kind == "returned" and batch.reason == "delta|alpha|charlie|"
        assert counted < 100, "短字符串热路径计费膨胀：{0}".format(counted)

