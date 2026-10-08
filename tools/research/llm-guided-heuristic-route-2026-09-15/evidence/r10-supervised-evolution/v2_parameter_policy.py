"""可信 V2 的离线联合参数研究包装；不修改生产默认权重或合法动作来源。"""

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

import hashlib
import json
from dataclasses import asdict
from typing import Any, Mapping

from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.weights_v1 import HeuristicWeightsV1


SCHEMA = "offline-v2-joint-parameter-policy/1"
PREFIX = "offline-v2-joint-v1:"
WEIGHT_FIELDS = tuple(HeuristicWeightsV1.__dataclass_fields__)


def _canonical(value: Any) -> bytes:
    """生成严格 JSON 字节；NaN/Infinity 不得进入研究身份。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def weights_digest(weights: HeuristicWeightsV1) -> str:
    """把完整权重向量折成研究策略身份，不只绑定六个正在搜索的字段。"""
    return hashlib.sha256(_canonical(asdict(weights))).hexdigest()


def weights_from_record(record: Mapping[str, Any]) -> HeuristicWeightsV1:
    """严格装配完整权重记录；缺字段、额外字段及非数值均失败关闭。"""
    if not isinstance(record, Mapping) or set(record) != set(WEIGHT_FIELDS):
        raise ValueError("联合参数记录必须且只能包含完整 HeuristicWeightsV1 字段")
    return HeuristicWeightsV1(**{field: record[field] for field in WEIGHT_FIELDS})


class ResearchWeightedV2(ComparableHeuristicPolicyV2):
    """仅增加不可变研究身份和可见决策轨迹，排序仍完全复用生产 V2。"""

    def __init__(self, weights: HeuristicWeightsV1, monotonic: Any) -> None:
        super().__init__(weights=weights, monotonic=monotonic)
        self.weights_sha256 = weights_digest(weights)
        self.policy_id = PREFIX + self.weights_sha256
        self.decision_trace: list[dict[str, Any]] = []

    async def choose(self, request: Any, budget: Any) -> Any:
        """记录可见请求的最终排序；轨迹只用于离线验收，不读取完整世界。"""
        plan = await super().choose(request, budget)
        self.decision_trace.append({
            "decision_id": request.decision_id,
            "window_key": str(request.window_key),
            "ordered_action_keys": [candidate.action_key for candidate in plan.candidates],
        })
        return plan
