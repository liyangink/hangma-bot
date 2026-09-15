"""候选启发式注册表与装载（**静态显式**，不是插件系统）。

**为什么必须静态**：`policy/AGENTS.md` 明确禁止"模型注册表、通用插件系统、
线上 LLM 接缝"。因此这里只做**模块级字面量登记**：
无自动扫描、无 `entry_points`、无动态导入、无网络。
新增候选 = **新增一个模块 + 在 `CANDIDATE_FACTORIES` 加一行 + 过契约测试**。
**这不是给 LLM 的自动上线通道**（README §3.2 B-3）：接缝只负责"能插进来"，
"准不准插"仍由人工审核与门禁决定。

**参数怎么进**：`PolicyDeclaration` 只有 `policy_id / name / weights` 三个字段
（修改它属受控契约变更）。因此候选参数复用 `weights` 映射，但必须带前缀
`adj.`，例如：

```json
{"policy_id": "m4_beta20", "name": "meld_opportunity_cost",
 "weights": {"adj.beta": 20.0, "shanten_step": 100.0}}
```

前缀键由候选消费，**剩余键才是基础评分权重**——这样不会与权重字段重名冲突，
且实验 JSON 里一眼能看出哪些是候选参数。
"""
from __future__ import annotations

from typing import Callable, Mapping, Optional, Tuple

from ..heuristic_adapter import HeuristicAdjustment, HeuristicAdjustmentPolicy
from ..weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1
from . import (
    meld_opportunity_cost,
    meld_waiting_conditional,
    seven_pairs_path_value,
)

# 候选参数的声明前缀。**改这个前缀属接口变更**，需同步实验配置与文档。
ADJUSTMENT_PARAM_PREFIX = "adj."

CandidateFactory = Callable[[Mapping[str, float], str], HeuristicAdjustment]

#: 静态注册表：名称 -> 候选工厂。**新增候选只改这里一行**。
CANDIDATE_FACTORIES: Mapping[str, CandidateFactory] = {
    "meld_opportunity_cost": meld_opportunity_cost.build_adjustment_from_params,
    "meld_waiting_conditional": meld_waiting_conditional.build_adjustment_from_params,
    "seven_pairs_path_value": seven_pairs_path_value.build_adjustment_from_params,
}

#: 名称 -> 模块对象；供**装载方**计算源码指纹（仍是静态字面量，不是自动发现）。
_MODULES = {
    "meld_opportunity_cost": meld_opportunity_cost,
    "meld_waiting_conditional": meld_waiting_conditional,
    "seven_pairs_path_value": seven_pairs_path_value,
}


def candidate_names() -> Tuple[str, ...]:
    """已注册候选名（稳定排序，便于产物与文档引用）。"""

    return tuple(sorted(CANDIDATE_FACTORIES))


def candidate_module(name: str):
    """返回候选模块对象；**装载方**用它读源码算指纹。

    policy 包自身不做任何文件 IO（`tests/unit/policy/test_policy_timeout_and_purity.py`
    静态扫描 `Path(` / `open(` / `read_text`），因此指纹由持有 IO 权限的装载方计算。
    """

    if name not in _MODULES:
        raise KeyError("未注册的候选启发式 {0!r}".format(name))
    return _MODULES[name]


def is_candidate(name: str) -> bool:
    return name in CANDIDATE_FACTORIES


def split_declaration_params(
    weights: Mapping[str, float],
) -> Tuple[dict, dict]:
    """把声明里的 `weights` 拆成 (候选参数, 基础评分权重)。

    带 `adj.` 前缀的键归候选（并**去掉前缀**），其余键归基础评分的
    `HeuristicWeightsV1`。前缀缺失时参数为空——候选走自己的默认值。
    """

    params = {}
    base = {}
    for key, value in weights.items():
        if key.startswith(ADJUSTMENT_PARAM_PREFIX):
            params[key[len(ADJUSTMENT_PARAM_PREFIX):]] = value
        else:
            base[key] = value
    return params, base


def build_candidate(
    name: str,
    *,
    weights: Mapping[str, float] = (),
    monotonic: Optional[Callable[[], float]] = None,
    enabled: bool = True,
    source_fingerprint_value: str = "",
) -> HeuristicAdjustmentPolicy:
    """按名构造候选策略；名称未注册时抛 `KeyError`（不静默回退）。

    `source_fingerprint_value` 由调用方（装载方）提供，因为只有它持有文件 IO 权限。
    """

    if name not in CANDIDATE_FACTORIES:
        raise KeyError(
            "未注册的候选启发式 {0!r}；已注册：{1}".format(name, candidate_names()))
    params, base = split_declaration_params(dict(weights))
    adjustment = CANDIDATE_FACTORIES[name](params, source_fingerprint_value)
    base_weights = HeuristicWeightsV1(**base) if base else DEFAULT_WEIGHTS_V1
    return HeuristicAdjustmentPolicy(
        adjustment, weights=base_weights, monotonic=monotonic, enabled=enabled)


__all__ = [
    "ADJUSTMENT_PARAM_PREFIX",
    "CANDIDATE_FACTORIES",
    "CandidateFactory",
    "build_candidate",
    "candidate_module",
    "candidate_names",
    "is_candidate",
    "split_declaration_params",
]
