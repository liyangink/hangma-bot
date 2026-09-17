"""R6 复审 S1（P1）专属回归：受限执行器的工作量计费边界。

权威材料：
- review/llm-guided-heuristic-route-2026-09-15/R6-IMPLEMENTATION-REVIEW-2026-09-17.md §3 S1；
- review/llm-guided-heuristic-route-2026-09-15/FIX-PLAN-2026-09-17.md 波次 1 工作包 P1。

复审给出两个经公开 ActionValueExecutor.score 正常返回合法弃权的有限纯函数反例
（修复前实测：`count = values.count` 后扫 163,840 项只计 8,357；16 层重复嵌套
元组相等比较访问 65,536 个叶只计 35），本文件把它们固化为正式回归，要求
“提前拒绝或正确耗尽预算”，并补齐：成员查询/递归结构遍历计费、嵌套深度上限、
字符串格式宽度与精度在**分配前**校验、集合迭代确定化与跨 PYTHONHASHSEED 一致。

测试只经公开接口（ActionValueExecutor.score / last_operation_count）验证行为，
不依赖执行器私有实现；反例源码与复审一致，计数数字为实测值。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tracemalloc
from pathlib import Path
from typing import Optional, Tuple

import pytest

from hangma_bot.policy.action_value import ScoreBatch
from hangma_bot.policy.action_value_executor import (
    MAX_COUNTED_OPERATIONS,
    ActionValueExecutor,
    StaticCheckError,
    WorkloadExceeded,
)
from hangma_bot.policy.action_value_seeds import (
    SEED_NAMES,
    build_action_value_policy,
    build_sample_view,
)


# ---------------------------------------------------------------------------
# 复审反例源码（与 R6-IMPLEMENTATION-REVIEW §3 S1 描述一一对应）
# ---------------------------------------------------------------------------

#: 反例 1：先取绑定方法别名 `count = values.count`，再对 4096 项列表查找不存在
#: 元素 40 次（真实扫描 163,840 项）。
ALIAS_COUNT_SOURCE = (
    "def score_actions(view):\n"
    "    values = list(range(4096))\n"
    "    count = values.count\n"
    "    hits = 0\n"
    "    for i in range(40):\n"
    "        hits = hits + count(999999)\n"
    "    return {'status': 'ABSTAIN', 'reason': 'alias-count'}\n"
)

#: 反例 1 变体：成员查询 `in` 走同一条不计费的线性扫描通道。
MEMBERSHIP_SCAN_SOURCE = (
    "def score_actions(view):\n"
    "    values = list(range(4096))\n"
    "    hits = 0\n"
    "    for i in range(40):\n"
    "        if 999999 in values:\n"
    "            hits = hits + 1\n"
    "    return {'status': 'ABSTAIN', 'reason': 'membership-scan'}\n"
)

#: 反例 1 变体：.index 绑定别名。
INDEX_ALIAS_SOURCE = (
    "def score_actions(view):\n"
    "    values = list(range(4096))\n"
    "    lookup = values.index\n"
    "    hits = 0\n"
    "    for i in range(40):\n"
    "        hits = hits + lookup(0)\n"
    "    return {'status': 'ABSTAIN', 'reason': 'alias-index'}\n"
)


def _nested_tuple_source(depth: int) -> str:
    """反例 2：depth 层重复嵌套元组（2**depth 个叶），再整体相等比较。"""
    return (
        "def score_actions(view):\n"
        "    a = (0, 0)\n"
        "    b = (0, 0)\n"
        "    for i in range({0}):\n".format(depth)
        + "        a = (a, a)\n"
        "        b = (b, b)\n"
        "    same = a == b\n"
        "    return {'status': 'ABSTAIN', 'reason': 'nested-eq'}\n"
    )


#: 反例 2 的复审原样版本：16 层 → 65,536 个叶。
NESTED_TUPLE_EQUALITY_SOURCE = _nested_tuple_source(16)


def _score_with_budget(source: str, budget: int) -> Tuple[Optional[ScoreBatch], int]:
    """按给定预算执行候选；返回 (批次或 None, 实测计数)。"""
    executor = ActionValueExecutor(source, max_operations=budget)
    try:
        batch = executor.score(build_sample_view())
    except WorkloadExceeded:
        return None, executor.last_operation_count
    return batch, executor.last_operation_count


# ---------------------------------------------------------------------------
# 反例 1：方法取值/绑定方法别名必须纳入计费
# ---------------------------------------------------------------------------


class TestS1MethodAliasBilling:
    def test_alias_count_scan_rejected_under_default_budget(self) -> None:
        executor = ActionValueExecutor(ALIAS_COUNT_SOURCE, name="p1-alias-count")
        with pytest.raises(WorkloadExceeded):
            executor.score(build_sample_view())
        # 预算被正确耗尽：拒绝不是靠事后检查，而是每一趟扫描都计费。
        assert executor.last_operation_count > MAX_COUNTED_OPERATIONS

    def test_alias_count_scan_billed_when_budget_allows(self) -> None:
        batch, counted = _score_with_budget(ALIAS_COUNT_SOURCE, 10_000_000)
        assert batch is not None and batch.status == "ABSTAIN"
        # 40 趟 × 4096 项：真实扫描量必须进入计数。
        assert counted >= 40 * 4096, "绑定方法别名的线性扫描未按被查序列长度计费"

    def test_membership_scan_rejected_under_default_budget(self) -> None:
        executor = ActionValueExecutor(MEMBERSHIP_SCAN_SOURCE, name="p1-membership")
        with pytest.raises(WorkloadExceeded):
            executor.score(build_sample_view())
        assert executor.last_operation_count > MAX_COUNTED_OPERATIONS

    def test_membership_scan_billed_when_budget_allows(self) -> None:
        batch, counted = _score_with_budget(MEMBERSHIP_SCAN_SOURCE, 10_000_000)
        assert batch is not None and batch.status == "ABSTAIN"
        assert counted >= 40 * 4096, "成员查询未按被查序列长度计费"

    def test_alias_index_scan_billed(self) -> None:
        executor = ActionValueExecutor(INDEX_ALIAS_SOURCE, name="p1-alias-index")
        with pytest.raises(WorkloadExceeded):
            executor.score(build_sample_view())
        assert executor.last_operation_count > MAX_COUNTED_OPERATIONS

    def test_non_whitelisted_method_value_still_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    values = list(range(4))\n"
            "    remover = values.pop\n"
            "    return {'status': 'ABSTAIN', 'reason': 'x'}\n"
        )
        with pytest.raises(StaticCheckError, match="白名单"):
            ActionValueExecutor(source)


# ---------------------------------------------------------------------------
# 反例 2：递归结构遍历（比较/排序/成员查询）必须计费并限深
# ---------------------------------------------------------------------------


class TestS1StructuralTraversalBilling:
    def test_review_nested_tuple_equality_rejected_early(self) -> None:
        """16 层嵌套（65,536 叶）必须在遍历前拒绝，而不是遍历后记账。"""
        executor = ActionValueExecutor(NESTED_TUPLE_EQUALITY_SOURCE, name="p1-nested-eq")
        with pytest.raises(WorkloadExceeded, match="嵌套深度|结构"):
            executor.score(build_sample_view())
        # 提前拒绝：预算远未耗尽，说明没有进入指数遍历。
        assert executor.last_operation_count < MAX_COUNTED_OPERATIONS

    def test_moderate_nested_equality_charged_by_structure(self) -> None:
        """深度在上限内的嵌套比较仍可用，但按结构单元计费。"""
        depth = 10
        batch, counted = _score_with_budget(_nested_tuple_source(depth), 10_000_000)
        assert batch is not None and batch.status == "ABSTAIN"
        assert counted >= 2 * (2**depth), "嵌套结构比较未按叶数计费"

    @pytest.mark.parametrize("expr", ["(a, b)", "(b, a)", "(a, a)"])
    def test_sorted_min_max_over_deep_structures_rejected(self, expr: str) -> None:
        """排序/极值内部比较发生在 C 层：必须在进入前限制结构规模。"""
        for call in ("sorted", "min", "max"):
            source = (
                "def score_actions(view):\n"
                "    a = (0, 0)\n"
                "    b = (0, 0)\n"
                "    for i in range(16):\n"
                "        a = (a, a)\n"
                "        b = (b, b)\n"
                "    rows = {0}\n".format(expr)
                + "    picked = {0}(rows)\n".format(call)
                + "    return {'status': 'ABSTAIN', 'reason': 'nested-sort'}\n"
            )
            executor = ActionValueExecutor(source, name="p1-nested-" + call)
            with pytest.raises(WorkloadExceeded):
                executor.score(build_sample_view())

    def test_deep_membership_item_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    a = (0, 0)\n"
            "    for i in range(16):\n"
            "        a = (a, a)\n"
            "    rows = [a]\n"
            "    hit = a in rows\n"
            "    return {'status': 'ABSTAIN', 'reason': 'nested-in'}\n"
        )
        with pytest.raises(WorkloadExceeded):
            ActionValueExecutor(source, name="p1-nested-in").score(build_sample_view())

    def test_scalar_comparison_still_cheap(self) -> None:
        """标量比较不因结构计费而膨胀：保留既有每运算计费的量级。"""
        source = (
            "def score_actions(view):\n"
            "    hits = 0\n"
            "    for i in range(50):\n"
            "        if i > 10:\n"
            "            hits = hits + 1\n"
            "    return {'status': 'ABSTAIN', 'reason': 'scalar'}\n"
        )
        batch, counted = _score_with_budget(source, MAX_COUNTED_OPERATIONS)
        assert batch is not None and batch.status == "ABSTAIN"
        assert counted < 1_000, "标量比较的计费量级不得因结构检查而爆炸"

    def test_chained_comparison_semantics_preserved(self) -> None:
        """链式比较保持 Python 短路语义（含不触发右侧除零）。"""
        source = (
            "def score_actions(view):\n"
            "    hits = 0\n"
            "    for i in range(10):\n"
            "        if 0 < i < 3 // i:\n"
            "            hits = hits + 1\n"
            "    return {'status': 'ABSTAIN', 'reason': f'chain-{hits}'}\n"
        )
        batch = ActionValueExecutor(source, name="p1-chain").score(build_sample_view())
        assert batch.status == "ABSTAIN"
        assert batch.reason == "chain-1"


# ---------------------------------------------------------------------------
# 字符串宽度/精度必须在分配前校验
# ---------------------------------------------------------------------------


def _peak_bytes_during(source: str) -> Tuple[str, int]:
    """执行候选并返回 (异常类型名, tracemalloc 峰值字节)。"""
    executor = ActionValueExecutor(source, name="p1-format")
    tracemalloc.start()
    try:
        try:
            executor.score(build_sample_view())
            kind = "RETURNED"
        except WorkloadExceeded:
            kind = "WorkloadExceeded"
        except BaseException as exc:  # noqa: BLE001 - 记录实际类型用于判定
            kind = type(exc).__name__
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return kind, peak


class TestS1PreAllocationGuards:
    LIMIT_BYTES = 8 * 1024 * 1024

    def test_fstring_width_rejected_before_allocation(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    text = f'{1:>200000000}'\n"
            "    return {'status': 'ABSTAIN', 'reason': 'format-width'}\n"
        )
        kind, peak = _peak_bytes_during(source)
        assert kind == "WorkloadExceeded"
        assert peak < self.LIMIT_BYTES, "f-string 宽度在分配后才检查：峰值 {0} 字节".format(peak)

    def test_fstring_precision_rejected_before_allocation(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    text = f'{1.5:.200000000f}'\n"
            "    return {'status': 'ABSTAIN', 'reason': 'format-precision'}\n"
        )
        kind, peak = _peak_bytes_during(source)
        assert kind == "WorkloadExceeded"
        assert peak < self.LIMIT_BYTES, "精度在分配后才检查：峰值 {0} 字节".format(peak)

    def test_percent_width_rejected_before_allocation(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    text = '%0199999999d' % 7\n"
            "    return {'status': 'ABSTAIN', 'reason': 'percent-width'}\n"
        )
        kind, peak = _peak_bytes_during(source)
        assert kind == "WorkloadExceeded"
        assert peak < self.LIMIT_BYTES, "% 格式化宽度在分配后才检查：峰值 {0} 字节".format(peak)

    def test_star_width_rejected_before_allocation(self) -> None:
        """'%*d' 的宽度取自实参，分配前无法界定上限：受限子集直接拒绝该形态。"""
        source = (
            "def score_actions(view):\n"
            "    text = '%*d' % (2000000000, 3)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'star'}\n"
        )
        kind, peak = _peak_bytes_during(source)
        assert kind == "WorkloadExceeded"
        assert peak < self.LIMIT_BYTES, "星号宽度未被提前拒绝：峰值 {0} 字节".format(peak)

    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("'%05d' % 7", "00007"),
            ("'%(x)05d' % {'x': 7}", "00007"),
            ("'100%% done %s' % 'x'", "100% done x"),
            ("'%.2f' % 1.5", "1.50"),
            ("'%#010x' % 255", "0x000000ff"),
        ],
    )
    def test_legitimate_percent_formats_still_allowed(
        self, expr: str, expected: str
    ) -> None:
        source = (
            "def score_actions(view):\n"
            "    text = {0}\n".format(expr)
            + "    return {'status': 'ABSTAIN', 'reason': text}\n"
        )
        batch = ActionValueExecutor(source, name="p1-pct").score(build_sample_view())
        assert batch.status == "ABSTAIN"
        assert batch.reason == expected

    def test_legitimate_formatting_still_allowed(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    text = f'{3:>5d}'\n"
            "    other = '%s-%d' % ('x', 2)\n"
            "    return {'status': 'ABSTAIN', 'reason': text + other}\n"
        )
        batch = ActionValueExecutor(source, name="p1-format-ok").score(build_sample_view())
        assert batch.status == "ABSTAIN"
        assert batch.reason == "    3x-2"


# ---------------------------------------------------------------------------
# 集合迭代确定化 + 跨 PYTHONHASHSEED 一致
# ---------------------------------------------------------------------------

SET_ITERATION_SOURCE = (
    "def score_actions(view):\n"
    "    words = set(['delta', 'alpha', 'charlie', 'bravo', 'echo'])\n"
    "    text = ''\n"
    "    for word in words:\n"
    "        text = text + word + '|'\n"
    "    return {'status': 'ABSTAIN', 'reason': text}\n"
)

SET_OPERATION_SOURCE = (
    "def score_actions(view):\n"
    "    left = set(['delta', 'alpha'])\n"
    "    right = set(['charlie', 'alpha'])\n"
    "    merged = left | right\n"
    "    text = ''\n"
    "    for word in merged:\n"
    "        text = text + word + '|'\n"
    "    return {'status': 'ABSTAIN', 'reason': text}\n"
)

FROZENSET_ITERATION_SOURCE = (
    "def score_actions(view):\n"
    "    words = frozenset(['delta', 'alpha', 'charlie'])\n"
    "    text = ''\n"
    "    for word in words:\n"
    "        text = text + word + '|'\n"
    "    return {'status': 'ABSTAIN', 'reason': text}\n"
)

_HASHSEED_SCRIPT = """
import json, sys
sys.path.insert(0, {src!r})
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.action_value_seeds import build_sample_view
SOURCE = {source!r}
executor = ActionValueExecutor(SOURCE, name="p1-hashseed")
batch = executor.score(build_sample_view())
print(json.dumps({{"reason": batch.reason, "ops": executor.last_operation_count}}))
"""


class TestS1DeterministicSetIteration:
    def test_set_iteration_follows_insertion_order(self) -> None:
        batch = ActionValueExecutor(SET_ITERATION_SOURCE, name="p1-set").score(
            build_sample_view()
        )
        assert batch.reason == "delta|alpha|charlie|bravo|echo|"

    def test_frozenset_iteration_follows_insertion_order(self) -> None:
        batch = ActionValueExecutor(FROZENSET_ITERATION_SOURCE, name="p1-fset").score(
            build_sample_view()
        )
        assert batch.reason == "delta|alpha|charlie|"

    def test_set_operation_result_is_deterministic(self) -> None:
        batch = ActionValueExecutor(SET_OPERATION_SOURCE, name="p1-setop").score(
            build_sample_view()
        )
        assert batch.reason == "delta|alpha|charlie|"

    @pytest.mark.parametrize("source", [SET_ITERATION_SOURCE, SET_OPERATION_SOURCE])
    def test_pythonhashseed_consistency_across_processes(self, source: str) -> None:
        """同一程序在三个不同 hash 种子下必须得到相同计费与结果。"""
        root = Path(__file__).resolve().parents[3]
        script = _HASHSEED_SCRIPT.format(src=str(root / "src"), source=source)
        outputs = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = seed
            completed = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                env=env,
                check=False,
                timeout=120,
            )
            assert completed.returncode == 0, completed.stderr
            outputs.append(completed.stdout.strip())
        assert len(set(outputs)) == 1, "跨 PYTHONHASHSEED 结果不一致：{0}".format(outputs)
        payload = json.loads(outputs[0])
        assert payload["ops"] > 0


# ---------------------------------------------------------------------------
# 既有不变量：种子策略仍在预算内、失败语义不变
# ---------------------------------------------------------------------------



class TestS1BoundaryDocumentation:
    """边界值文档化：既不放过超量形态，也不误伤深度内的合法数据。"""

    def test_nesting_depth_boundary_is_twelve_levels(self) -> None:
        # (a, a) 重复 depth 次得到 depth+1 层容器：11 层通过、12 层起拒绝。
        batch, counted = _score_with_budget(_nested_tuple_source(10), 10_000_000)
        assert batch is not None and batch.status == "ABSTAIN"
        assert counted >= 2 * (2**10)
        executor = ActionValueExecutor(_nested_tuple_source(12), name="p1-depth-12")
        with pytest.raises(WorkloadExceeded, match="嵌套深度"):
            executor.score(build_sample_view())

    def test_view_data_comparison_still_allowed(self) -> None:
        """观察数据（容器深度 5）在限深内：比较合法数据不得被误拒。"""
        source = (
            "def score_actions(view):\n"
            "    rows = view['actions']\n"
            "    same = rows[0] == rows[1]\n"
            "    return {'status': 'ABSTAIN', 'reason': 'view-compare'}\n"
        )
        batch, counted = _score_with_budget(source, MAX_COUNTED_OPERATIONS)
        assert batch is not None and batch.status == "ABSTAIN"
        assert counted < 10_000

    def test_string_membership_charged_by_length(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    text = 'a' * 60000\n"
            "    hits = 0\n"
            "    for i in range(4):\n"
            "        if 'q' in text:\n"
            "            hits = hits + 1\n"
            "    return {'status': 'ABSTAIN', 'reason': 'str-in'}\n"
        )
        executor = ActionValueExecutor(source, name="p1-str-in")
        with pytest.raises(WorkloadExceeded):
            executor.score(build_sample_view())
        assert executor.last_operation_count > MAX_COUNTED_OPERATIONS

class TestS1InvariantsPreserved:
    def test_seed_policies_still_within_default_budget(self) -> None:
        for name in SEED_NAMES:
            scorer = build_action_value_policy(name)
            batch = scorer.score(build_sample_view())
            assert batch.status == "SCORED", name
            assert scorer._executor.last_operation_count < MAX_COUNTED_OPERATIONS, name

    def test_workload_exceeded_not_catchable_by_exception(self) -> None:
        assert issubclass(WorkloadExceeded, BaseException)
        assert not issubclass(WorkloadExceeded, Exception)
