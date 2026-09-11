"""outcome-v1 的纯 JSON 编解码和观察绑定；训练、审计共用，不读取文件。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from .observation import PlayerObservation
from .config import RuleConfig
from .outcomes import (
    OUTCOME_SCHEMA_VERSION, CandidateOutcome, HandObjectiveKind, HandOutcomeObjective,
    JointOutcome, MeanOutcome, OutcomeAtom, OutcomeBatch, OutcomeDecisionTrace,
    OutcomeModelVersion,
)
from .serialization import observation_to_json


def rules_context_key(config: RuleConfig, source_hash: str) -> str:
    """绑定有效底分/规则开关及规则源码摘要，避免同名规则跨配置误用模型。"""
    if not isinstance(source_hash, str) or not source_hash.strip():
        raise ValueError("规则源码摘要必须非空")
    if not isinstance(config, RuleConfig):
        raise ValueError("config 必须来自有效 RuleConfig")
    config_fields = {"ruleset_version": config.ruleset_version, "base_score": config.base_score,
                     "you_cai_bi_kao": config.you_cai_bi_kao}
    raw = json.dumps({"schema_version": OUTCOME_SCHEMA_VERSION, "config": config_fields, "source_hash": source_hash},
                     sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def observation_key(observation: PlayerObservation) -> str:
    """绑定完整可见观察（含序号/信息质量）；摘要不作为学生特征。"""
    raw = json.dumps(observation_to_json(observation), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _object(value: object) -> Mapping:
    if not isinstance(value, Mapping):
        raise ValueError("结果载荷必须是 JSON 对象")
    return value


def _get(data: Mapping, key: str) -> object:
    if key not in data:
        raise ValueError("结果载荷缺少 " + key)
    return data[key]


def _array(value: object) -> list:
    if not isinstance(value, list):
        raise ValueError("结果载荷必须使用 JSON 数组")
    return value


def _versioned(value: object) -> Mapping:
    data = _object(value)
    version = _get(data, "schema_version")
    if type(version) is not int or version != OUTCOME_SCHEMA_VERSION:
        raise ValueError("不兼容的 outcome schema_version")
    return data


def model_version_to_json(version: OutcomeModelVersion) -> dict:
    """逐字段输出制品适用条件；不是通用 dataclass 序列化协议。"""
    return {name: getattr(version, name) for name in _MODEL_FIELDS}


_MODEL_FIELDS = (
    "model_id", "ruleset_version", "rules_hash", "feature_schema_version",
    "action_schema_version", "training_data_id", "continuation_policy_id",
    "opponent_pool_id", "sampler_version", "calibration_version", "engine_commit",
    "guide_api_version",
)


def model_version_from_json(value: object) -> OutcomeModelVersion:
    """恢复完整版本；缺字段或值错误抛 ValueError，不猜历史默认值。"""
    data = _object(value)
    return OutcomeModelVersion(**{name: _get(data, name) for name in _MODEL_FIELDS})


def outcome_batch_to_json(batch: OutcomeBatch) -> dict:
    """输出均值/联合分布判别联合；单位和终点由版本 1 固定。"""
    candidates = []
    for candidate in batch.candidates:
        estimate = candidate.estimate
        if isinstance(estimate, MeanOutcome):
            result = {"kind": "mean", "score_delta": list(estimate.score_delta)}
        else:
            result = {"kind": "joint", "atoms": [
                {"score_delta": list(a.score_delta), "probability": a.probability}
                for a in estimate.atoms
            ]}
        candidates.append({"action_key": candidate.action_key, "estimate": result})
    return {"schema_version": OUTCOME_SCHEMA_VERSION, "observation_key": batch.observation_key,
            "version": model_version_to_json(batch.version), "candidates": candidates}


def outcome_batch_from_json(value: object) -> OutcomeBatch:
    """严格恢复结果；拒绝未知种类、非有限数、重复键及不守恒的结果。"""
    data = _versioned(value)
    candidates = []
    for item in _array(_get(data, "candidates")):
        item = _object(item)
        result = _object(_get(item, "estimate"))
        kind = _get(result, "kind")
        if kind == "mean":
            estimate = MeanOutcome(tuple(_array(_get(result, "score_delta"))))
        elif kind == "joint":
            atoms = []
            for atom in _array(_get(result, "atoms")):
                atom = _object(atom)
                atoms.append(OutcomeAtom(tuple(_array(_get(atom, "score_delta"))), _get(atom, "probability")))
            estimate = JointOutcome(tuple(atoms))
        else:
            raise ValueError("未知候选结果类型")
        candidates.append(CandidateOutcome(_get(item, "action_key"), estimate))
    return OutcomeBatch(_get(data, "observation_key"), model_version_from_json(_get(data, "version")), tuple(candidates))


def objective_to_json(objective: HandOutcomeObjective) -> dict:
    """保存目标来源及未知原因；目标净增积分不是番数。"""
    return {"schema_version": OUTCOME_SCHEMA_VERSION, "kind": objective.kind.value,
            "seat": objective.seat, "source": objective.source,
            "target_score_delta": objective.target_score_delta, "reason": objective.reason}


def objective_from_json(value: object) -> HandOutcomeObjective:
    """恢复单局目标；不将缺失信息转换成零分门槛。"""
    data = _versioned(value)
    return HandOutcomeObjective(HandObjectiveKind(_get(data, "kind")), _get(data, "seat"),
                                _get(data, "source"), data.get("target_score_delta"), data.get("reason"))


def outcome_trace_to_json(trace: OutcomeDecisionTrace) -> dict:
    """编码可审计的模型适用性、目标与实际结果。"""
    return {"schema_version": OUTCOME_SCHEMA_VERSION, "status": trace.status, "reason": trace.reason,
            "expected_version": model_version_to_json(trace.expected_version),
            "objective": None if trace.objective is None else objective_to_json(trace.objective),
            "batch": None if trace.batch is None else outcome_batch_to_json(trace.batch)}


def outcome_trace_from_json(value: object) -> OutcomeDecisionTrace:
    """恢复增强证据；载荷缺失由上层旧计划兼容路径处理。"""
    data = _versioned(value)
    objective, batch = _get(data, "objective"), _get(data, "batch")
    return OutcomeDecisionTrace(_get(data, "status"), _get(data, "reason"),
                                model_version_from_json(_get(data, "expected_version")),
                                None if objective is None else objective_from_json(objective),
                                None if batch is None else outcome_batch_from_json(batch))
