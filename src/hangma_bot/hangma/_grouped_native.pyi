"""可选 C 扩展的内部类型契约；运行时由同名平台扩展提供实现。"""

SEMANTICS_VERSION: str

def need(
    counts33: tuple[int, ...], whites: int, sets_left: int, pair_needed: bool
) -> int:
    """返回最少自然进张数；类型错误抛 TypeError，范围错误抛 ValueError。"""
    ...

def cache_clear() -> None:
    """清空所属解释器中该模块实例的有界缓存。"""
    ...

def cache_info() -> dict[str, object]:
    """返回缓存容量和使用情况；字节数仅含原生缓存。"""
    ...
