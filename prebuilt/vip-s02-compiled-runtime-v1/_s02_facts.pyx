from dataclasses import fields
from typing import Any
def _plain(value: Any) -> Any:
    """复制冻结事实为原始值；候选修改自己的容器不会改变下一次调用。"""

    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    if hasattr(value, "__dataclass_fields__"):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    raise ValueError("VIP 事实含未允许的类型: " + type(value).__name__)
