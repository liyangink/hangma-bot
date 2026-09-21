"""R17 单叶程序的受限执行适配器。

复用 ``action_value_executor`` 已经过对抗性验证的静态子集、AST 插桩、
有限数守卫、结构计费和跨调用状态检查；不另写一套沙箱。叶程序仍定义
单参数 ``score_actions(view)``，其中 view 是一个叶映射，返回值是
[-1, 1] 的一个数。每叶与每窗
都有独立操作上限；任一失败由固定归约器整窗回退 V2。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional, Tuple

from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER

from .action_value_executor import ActionValueExecutor, WorkloadExceeded
from .public_successor_search import LEAF_VIEW_SCHEMA_VERSION, LeafView


LEAF_EXECUTOR_VERSION = "r17-leaf-executor/1"
MAX_OPERATIONS_PER_LEAF = 2048
MAX_OPERATIONS_PER_WINDOW = 500_000

LEAF_FIRST_PARTY_DIGEST_MODULES: Tuple[str, ...] = (
    "hangma_bot.hangma.interface",
    "hangma_bot.hangma.public_successor",
    "hangma_bot.policy.public_successor_search",
    "hangma_bot.policy.public_successor_leaf_executor",
    "hangma_bot.policy.action_value_executor",
    "hangma_bot.policy.action_value",
    "hangma_bot.policy.action_value_policy",
    "hangma_bot.policy.evaluation_v1",
)


def _useful_tiles(mask: int, packed: int) -> Tuple[Tuple[str, int], ...]:
    return tuple(
        (code, (packed >> (index * 3)) & 0b111)
        for index, code in enumerate(CANONICAL_TILE_ORDER)
        if mask & (1 << index)
    )


def leaf_view_mapping(view: LeafView) -> Mapping[str, Any]:
    """把内部紧凑叶投影为候选只读原始值；完整保留有效牌身份。"""

    if not isinstance(view, LeafView):
        raise TypeError("leaf_view_mapping 需要 LeafView")
    competition = view.window.competition
    return {
        "schema_version": LEAF_VIEW_SCHEMA_VERSION,
        "window": {
            "seat": view.window.seat,
            "dealer_seat": view.window.dealer_seat,
            "round_no": view.window.round_no,
            "table_scores": view.window.table_scores,
            "table_rank": view.window.table_rank,
            "stage_scores": competition.stage_scores,
            "current_stage_scores": competition.current_stage_scores,
            "freshness_masks": competition.freshness_masks,
            "chain_count": view.window.chain_count,
            "baotou": view.window.baotou,
            "wealth_count": view.window.wealth_count,
            "chain_piao": view.window.chain_piao,
            "remaining_tile_count": view.window.remaining_tile_count,
            "catch_play": view.window.catch_play,
            "catch_play_owner_seat": view.window.catch_play_owner_seat,
        },
        "root": {
            "action_key": view.root.action_key,
            "discard_code": view.root.discard_code,
            "shanten_after": view.root.shanten_after,
            "standard_shanten_after": view.root.standard_shanten_after,
            "seven_pairs_shanten_after": view.root.seven_pairs_shanten_after,
            "useful_tiles": _useful_tiles(
                view.root.useful_mask, view.root.useful_remaining_packed
            ),
            "useful_tile_count": view.root.useful_tile_count,
            "support_remaining": view.root.support_remaining,
            "family_progress": tuple(
                {
                    "family": item.family,
                    "progress": item.progress,
                    "route_status": item.route_status,
                }
                for item in view.root.family_progress
            ),
            "value_coverage": view.root.value_coverage,
        },
        "draw": {
            "code": view.draw_code,
            "capacity": view.draw_capacity,
            "is_currently_useful": view.draw_is_currently_useful,
            "envelope_kind": view.envelope_kind,
        },
        "next": {
            "action_key": view.next_action_key,
            "action_type": view.next_action_type,
            "shanten_after": view.shanten_after,
            "standard_shanten_after": view.standard_shanten_after,
            "seven_pairs_shanten_after": view.seven_pairs_shanten_after,
            "useful_tiles": _useful_tiles(
                view.useful_mask, view.useful_remaining_packed
            ),
            "useful_tile_count": view.useful_tile_count,
            "support_remaining": view.support_remaining,
            "replacement_draw_unknown": view.replacement_draw_unknown,
            "requires_future_wall_gt20": view.requires_future_wall_gt20,
        },
    }


class _RawLeafExecutor(ActionValueExecutor):
    """只复用父类硬化编译器；不进入 ActionValue 的 ScoreBatch 骨架。"""

    def call_raw(self, leaf: Mapping[str, Any]) -> Tuple[Any, int]:
        self._meter.used = 0
        try:
            raw = self._guarded_candidate(leaf)
            return raw, self._meter.used
        finally:
            self.last_operation_count = self._meter.used
            self._verify_no_shared_mutation()


class LeafProgramExecutor:
    """已静态核验的单叶程序；每个窗口通过 ``window_scorer`` 独立计费。"""

    def __init__(
        self,
        source: str,
        *,
        name: str = "<r17_leaf_candidate>",
        max_operations_per_leaf: int = MAX_OPERATIONS_PER_LEAF,
        max_operations_per_window: int = MAX_OPERATIONS_PER_WINDOW,
    ) -> None:
        for field_name, value in (
            ("max_operations_per_leaf", max_operations_per_leaf),
            ("max_operations_per_window", max_operations_per_window),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(field_name + " 必须是正整数")
        self.name = str(name)
        self.max_operations_per_leaf = max_operations_per_leaf
        self.max_operations_per_window = max_operations_per_window
        self._inner = _RawLeafExecutor(
            source,
            name=self.name,
            max_operations=max_operations_per_leaf,
        )

    def window_scorer(self) -> "WindowLeafScorer":
        """返回一窗一次的新计费器；不得跨窗口复用累计数。"""

        return WindowLeafScorer(self)

    def _score(self, view: LeafView) -> Tuple[float, int]:
        try:
            raw, operations = self._inner.call_raw(leaf_view_mapping(view))
        except WorkloadExceeded as exc:
            raise ValueError("叶程序超过受限执行工作量") from exc
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError("叶程序必须返回一个数值")
        value = float(raw)
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("叶程序返回非有限数")
        if not -1.0 <= value <= 1.0:
            raise ValueError("叶程序分数必须在 [-1, 1] 内")
        return value, operations


class WindowLeafScorer:
    """一窗的候选计费状态；状态在候选命名空间之外，不参与评分。"""

    def __init__(self, executor: LeafProgramExecutor) -> None:
        self._executor = executor
        self.operation_count = 0
        self.leaf_count = 0

    def __call__(self, view: LeafView) -> float:
        value, operations = self._executor._score(view)
        self.operation_count += operations
        self.leaf_count += 1
        if self.operation_count > self._executor.max_operations_per_window:
            raise ValueError(
                "叶程序整窗操作数超过固定上限 {0}".format(
                    self._executor.max_operations_per_window
                )
            )
        return value


def compute_leaf_deps_digest(file_contents: Mapping[str, str]) -> str:
    """计算候选第一方语义闭包摘要；文件读取由离线装配层完成。"""

    if not isinstance(file_contents, Mapping):
        raise ValueError("file_contents 必须是模块名到文件文本的映射")
    missing = set(LEAF_FIRST_PARTY_DIGEST_MODULES) - set(file_contents)
    extra = set(file_contents) - set(LEAF_FIRST_PARTY_DIGEST_MODULES)
    if missing or extra:
        raise ValueError(
            "第一方依赖集合不一致: missing={0}, extra={1}".format(
                sorted(missing), sorted(extra)
            )
        )
    payload = {
        "executor_version": LEAF_EXECUTOR_VERSION,
        "leaf_schema": LEAF_VIEW_SCHEMA_VERSION,
        "limits": {
            "per_leaf": MAX_OPERATIONS_PER_LEAF,
            "per_window": MAX_OPERATIONS_PER_WINDOW,
        },
        "files": {key: str(file_contents[key]) for key in sorted(file_contents)},
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def compute_leaf_candidate_identity(
    source: str,
    contract_sha256: str,
    deps_digest: str,
    params: Optional[Mapping[str, Any]] = None,
) -> str:
    """按冻结合同计算叶候选身份；作者／模型出处另记溯源，不改身份。"""

    for name, value in (
        ("source", source),
        ("contract_sha256", contract_sha256),
        ("deps_digest", deps_digest),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(name + " 必须是非空字符串")
    try:
        normalized_params = json.loads(
            json.dumps(
                {} if params is None else dict(params),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("params 必须可 JSON 序列化") from exc
    payload = {
        "candidate_kind": "r17_public_successor_leaf",
        "source": source,
        "contract_sha256": contract_sha256,
        "executor_version": LEAF_EXECUTOR_VERSION,
        "deps_digest": deps_digest,
        "params": normalized_params,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "LEAF_EXECUTOR_VERSION",
    "MAX_OPERATIONS_PER_LEAF",
    "MAX_OPERATIONS_PER_WINDOW",
    "LEAF_FIRST_PARTY_DIGEST_MODULES",
    "LeafProgramExecutor",
    "WindowLeafScorer",
    "compute_leaf_candidate_identity",
    "compute_leaf_deps_digest",
    "leaf_view_mapping",
]
