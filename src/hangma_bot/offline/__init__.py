"""离线整理与转换（不进入线上动作闭环）。

本包只依赖生产核心与适配器，线上运行代码不得反向依赖本包。统一牌谱
读写器在 ``offline.replay``。导出保持兼容，但延迟加载回放适配器，避免
只运行纯模拟器或策略评估时因为官方传输的可选依赖而导入失败。
"""

__all__ = [
    "CONTRACT_ID",
    "REPLAY_SCHEMA_VERSION",
    "build_dataset",
    "hand_id",
    "load_hand_rows",
    "split_group_id",
]


def __getattr__(name: str):
    """按需加载牌谱读写器；模拟路径不触发官方 HTTP 适配器。"""

    if name in __all__:
        from hangma_bot.offline import replay

        return getattr(replay, name)
    raise AttributeError(name)
