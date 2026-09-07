"""选择同语义的标准型数学实现；只加载已安装模块，不编译或读取配置。

原生库不可用、ABI 不兼容或语义标签不符时，改用修正后的 Python
分组算法。选择在模块导入时固定，计算失败仍由 HangmaRules 隔离。
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from ._standard_python import SEMANTICS_VERSION, build_solver

IMPLEMENTATION = "python_grouped"
FALLBACK_REASON: str | None = None
NATIVE_MODULE = None
cache_info: Callable[[], Mapping[str, object]]

try:
    from . import _grouped_native

    if _grouped_native.SEMANTICS_VERSION != SEMANTICS_VERSION:
        raise ImportError("规则 C 扩展与 Python 数学语义版本不一致")
    need = _grouped_native.need
    cache_clear = _grouped_native.cache_clear
    cache_info = _grouped_native.cache_info
    NATIVE_MODULE = _grouped_native
    IMPLEMENTATION = "c_grouped"
except (ImportError, OSError, AttributeError, RuntimeError, MemoryError) as exc:
    FALLBACK_REASON = type(exc).__name__ + ": " + str(exc)
    need = build_solver()
    cache_clear = need.cache_clear
    cache_info = need.cache_info


def backend_info() -> dict[str, str | None]:
    """返回已选实现的诊断事实；路径仅取已加载模块属性，不访问文件。"""
    return {
        "implementation": IMPLEMENTATION,
        "semantics_version": SEMANTICS_VERSION,
        "fallback_reason": FALLBACK_REASON,
        "native_path": getattr(NATIVE_MODULE, "__file__", None),
    }
