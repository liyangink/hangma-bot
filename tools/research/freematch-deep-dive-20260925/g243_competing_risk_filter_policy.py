"""G243：以可见三摸前本人胡增量过滤 G237 数牌宽面反转。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import time

import numpy as np

import g237_numeric_inversion_policy as base
import g242_competing_risk_calibration as model
from hangma_bot.hangma.engine import _build_context


HERE = Path(__file__).resolve().parent
MODEL_PATH = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g242-competing-risk-calibration-20260929/result.json')
MODEL_SHA256 = "f3eb4e7eed1ed1ef388e7afeda0fbad8e3eb7df9899650bfc447922cded55ccf"
POLICY_ID = "action_value_v1:research:g243-competing-risk-filter-v1"
EPS = 1e-8


def _load_weights() -> np.ndarray:
    """只接受事前冻结的 G242 权重及类别/特征顺序。"""
    if sha256(MODEL_PATH.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError("G243 冻结 G242 结果摘要漂移")
    result = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    if (result["class_order"] != list(model.CLASSES)
            or result["full_feature_order"] != list(model.FULL_FEATURES)
            or result["evaluation"]["predeclared_incremental_signal_gate_pass"] is not True):
        raise ValueError("G243 冻结 G242 模型合同不符")
    weights = np.asarray(result["full_coefficients"], dtype=np.float64)
    if weights.shape != (len(model.FULL_FEATURES), len(model.CLASSES)):
        raise ValueError("G243 模型权重维度不符")
    return weights


WEIGHTS = _load_weights()


def _arm_features(request, key: str, legal: dict, white_before: int) -> list[float]:
    """该合法弃牌只用玩家可见状态与生产弃后规则事实。"""
    item = legal.get(key)
    fact = None if item is None else item.facts
    if fact is None:
        raise ValueError("G243 合法弃牌事实缺失")
    width = base.g232.width(fact.standard_useful_tiles)
    if width is None:
        raise ValueError("G243 普通有效牌公开容量未知")
    observation = request.observation
    row = {
        "remaining_tile_count": observation.remaining_tile_count,
        "standard_shanten_after": fact.standard_shanten_after,
        "seven_pairs_shanten_after": fact.seven_pairs_shanten_after,
        "white_before": white_before,
        "meld_count": len(observation.melds[observation.seat]),
        "standard_useful_type_count": width[0],
        "standard_useful_public_capacity": width[1],
        "chosen_action": key,
    }
    return model.features(row, full=True)


def select(request, plan) -> tuple[str | None, dict]:
    """G237 先保近端合法性；仅以冻结正向竞争结局差作过滤。"""
    key, evidence = base.select(request, plan)
    if key is None:
        return None, evidence
    parent_key = plan.candidates[0].action_key
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if len(legal) != len(request.rules.legal_candidates):
        raise ValueError("G243 生产合法动作键重复")
    observation = request.observation
    white_code = observation.rule_state.wealth_god.code
    white_before = sum(tile.code == white_code
                       for tile in _build_context(observation).full_hand())
    matrix = np.asarray([
        _arm_features(request, parent_key, legal, white_before),
        _arm_features(request, key, legal, white_before),
    ], dtype=np.float64)
    forecast = model.probabilities(matrix, WEIGHTS)
    parent_value, alternate_value = float(forecast[0, 1]), float(forecast[1, 1])
    delta = alternate_value - parent_value
    report = {**evidence, "parent_ownwin_before_third": round(parent_value, 9),
              "alternate_ownwin_before_third": round(alternate_value, 9),
              "predicted_ownwin_gain": round(delta, 9)}
    if delta <= EPS:
        return None, {**report, "reason": "competing_risk_filter_rejected"}
    return key, {**report, "reason": "competing_risk_filter_adopted"}


class CompetingRiskFilterPolicy(base.NumericInversionPolicy):
    """研究候选仅重排父代已合法计划，所有缺证直接返回父代。"""

    policy_id = POLICY_ID

    async def choose(self, request, budget):
        """父代先生成保底；过滤失败或异常不改变任何线上动作。"""
        plan = await self.baseline.choose(request, budget)
        started = time.perf_counter()
        try:
            key, evidence = select(request, plan)
        except Exception as exc:
            key = None
            evidence = {"reason": "selector_exception", "error_type": type(exc).__name__}
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if key is None:
            if evidence["reason"] in ("competing_risk_filter_rejected", "selector_exception"):
                self.metrics.append({"decision_id": request.decision_id,
                                     "status": "filtered" if evidence["reason"]
                                     == "competing_risk_filter_rejected" else "fallback",
                                     **evidence, "elapsed_ms": round(elapsed_ms, 3)})
            return plan
        selected = next((item for item in plan.candidates
                         if item.action_key == key), None)
        if selected is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "fallback", "reason": "selected_not_in_plan"})
            return plan
        ordered = (selected,) + tuple(item for item in plan.candidates
                                     if item.action_key != key)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G243 竞争结局过滤数牌反转",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id,
                             "status": "adopted", **evidence,
                             "elapsed_ms": round(elapsed_ms, 3)})
        return replace(plan, candidates=ranked)


research_parent_factory = base.research_parent_factory


def policy_factory(metrics: list[dict]):
    """每张完整桌独立装配研究过滤器和只读指标接收器。"""
    def build(monotonic):
        return CompetingRiskFilterPolicy(research_parent_factory(monotonic), metrics)
    return build
