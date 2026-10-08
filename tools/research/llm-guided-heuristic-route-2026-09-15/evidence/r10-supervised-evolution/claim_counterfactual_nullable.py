"""反事实样本兼容层：保留可空晋级中点，并以识别区间上下界为主事实。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import builtins
from typing import Any

import claim_counterfactual_pilot as core


class _NullableFloatMeta(type):
    """让原生 float 在临时类型检查中仍被识别。"""

    def __instancecheck__(cls, instance: Any) -> bool:
        return isinstance(instance, builtins.float)


class _NullableFloat(float, metaclass=_NullableFloatMeta):
    """调用时允许 None，同时仍是可供 isinstance 使用的 float 类型。"""

    def __new__(cls, value: Any = 0.0):
        return super().__new__(cls, 0.0 if value is None else value)


def one_sample_nullable(**kwargs: Any) -> dict:
    """复用冻结 CF1 执行链，并修正仅位于结果序列化处的可空中点缺陷。

    CF1 的 ``one_sample`` 在完整续打后无条件 ``float(arm['u'])``；当缺失
    `god_count` 使晋级结果为识别区间时，底层正确返回 ``u=None`` 与非空
    ``u_low/u_high``，旧序列化会抛错。兼容层只在调用期间让该转换可完成，
    随后从原始双臂记录重建标签：中点任一为空则 ``u_delta=None``，上下界
    差和阶段积分差始终按原始事实计算。执行、规则、快照和强制动作逻辑不变。
    """

    sentinel = object()
    previous = getattr(core, "float", sentinel)
    core.float = _NullableFloat
    try:
        sample = core.one_sample(**kwargs)
    finally:
        if previous is sentinel:
            delattr(core, "float")
        else:
            core.float = previous
    if not sample.get("status", "").startswith("HIT"):
        return sample
    baseline = sample["double_arm"]["arms"]["baseline"]
    candidate = sample["double_arm"]["arms"]["candidate"]
    baseline_u = baseline.get("u")
    candidate_u = candidate.get("u")
    sample["label"] = {
        "u_delta": (
            None if baseline_u is None or candidate_u is None
            else builtins.float(candidate_u) - builtins.float(baseline_u)
        ),
        "u_low_delta": (
            builtins.float(candidate["u_low"]) - builtins.float(baseline["u_low"])
        ),
        "u_high_delta": (
            builtins.float(candidate["u_high"]) - builtins.float(baseline["u_high"])
        ),
        "baseline_u_interval": [
            builtins.float(baseline["u_low"]), builtins.float(baseline["u_high"])
        ],
        "candidate_u_interval": [
            builtins.float(candidate["u_low"]), builtins.float(candidate["u_high"])
        ],
        "focal_stage_score_delta": (
            int(candidate["focal_stage_score"]) - int(baseline["focal_stage_score"])
        ),
    }
    return sample


__all__ = ["one_sample_nullable"]
