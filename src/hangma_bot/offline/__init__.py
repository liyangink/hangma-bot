"""离线整理与转换（不进入线上动作闭环）。

本包只依赖生产核心与适配器，线上运行代码不得反向依赖本包。
统一牌谱读写器在 offline.replay（审计线所有）。
"""

from hangma_bot.offline.replay import (
    CONTRACT_ID,
    REPLAY_SCHEMA_VERSION,
    build_dataset,
    hand_id,
    load_hand_rows,
    split_group_id,
)

__all__ = [
    "CONTRACT_ID",
    "REPLAY_SCHEMA_VERSION",
    "build_dataset",
    "hand_id",
    "load_hand_rows",
    "split_group_id",
]
