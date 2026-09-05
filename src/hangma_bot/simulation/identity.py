"""模拟导出的身份口径（parallel-v1 契约 §4.1）。

集成裁定（2026-09-05）：hand_id / split_group_id 的唯一实现已提升到
kernel.identity，本模块只保留模拟专用包装（固定 source_namespace=
hangma-simulation 的便捷函数）并转导出底层实现，不再维护同义副本。

模拟导出固定 source_namespace=hangma-simulation、tournament_id=
MatchSpec.scenario_id、game_id=MatchSpec.match_id；同牌山候选/换座变体
使用不同 match_id、相同 scenario_id 与 split_group_id（契约 §4.1）。
"""

from __future__ import annotations

from hangma_bot.kernel.identity import hand_id, split_group_id

__all__ = ["hand_id", "simulation_hand_id", "simulation_split_group_id", "split_group_id"]

# 模拟产物的固定来源命名空间（契约 §4.1：不是 Token、主机名或 Git 分支）。
SIMULATION_SOURCE_NAMESPACE = "hangma-simulation"


def simulation_hand_id(scenario_id: str, match_id: str, round_no: int) -> str:
    """模拟导出固定 source_namespace=hangma-simulation、tournament_id=scenario_id。"""
    return hand_id(SIMULATION_SOURCE_NAMESPACE, scenario_id, match_id, round_no)


def simulation_split_group_id(scenario_id: str) -> str:
    """模拟划分组：split 字段 [source_namespace, scenario_id]。"""
    return split_group_id([SIMULATION_SOURCE_NAMESPACE, scenario_id])
