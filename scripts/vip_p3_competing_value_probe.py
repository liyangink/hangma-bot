"""P3 离线互斥终局概率×条件净分探针；仅供新根全动作检验。

当前胡始终使用同源准确结算。非胡终局类别来自冻结续打者的完整
单局教师，概率只由行动前 PlayerObservation 和规则事实预测；它不
读取未来事件，也不把教师的后续成绩称为新策略成绩。第一版条件净分
在每类内取训练根加权均值，属于待外部校准的末端模型。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Hu
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_competing_tail_audit import _label
from scripts.vip_p3_value_fit_probe import _FEATURE_NAMES, _features


_CATEGORIES = ("draw", "self_low", "self_high", "other_win")
_STEPS = 800
_LEARNING_RATE = 0.5
_RIDGE = 0.1
_LIMITS = ValueAnalysisLimits(max_expansions=8192)


@dataclass(frozen=True)
class _Arm:
    """同一观察根的一条非胡合法动作及互斥教师结局。"""

    features: tuple[float, ...]
    category_fraction: tuple[float, ...]  # 类别顺序为 _CATEGORIES，和为一
    category_net_sum: tuple[float, ...]  # 同顺序，各类本人净分之和
    sample_count: int


@dataclass(frozen=True)
class _Root:
    """一个 PlayerObservation；多个动作和隐藏世界不得当独立根。"""

    root_id: str
    arms: tuple[_Arm, ...]


def _load(path: Path) -> dict:
    """只读教师 JSON 或 gzip JSON；不改动来源证据。"""

    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def _read_roots(paths: tuple[Path, ...]) -> tuple[_Root, ...]:
    """重算规则与合法动作，标签只用于训练目标而不进入特征。"""

    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    seen: set[str] = set()
    roots = []
    for path in paths:
        report = _load(path)
        if (report.get("scope") !=
                "P3_offline_teacher_labels_only_not_candidate_policy_value"
                or report.get("continuation_reference", "shape") != "shape"
                or report.get("rule_config") !=
                {"BaseScore": 1, "YouCaiBiKao": False}):
            raise ValueError("竞争终局探针只接收目标配置的 shape 冻结教师")
        for row in report["rows"]:
            root_id = row["root_id"]
            if root_id in seen:
                raise ValueError("训练来源存在重复观察根")
            seen.add(root_id)
            observation = observation_from_json(row["observation"])
            if hashlib.sha256(repr(observation).encode()).hexdigest() != root_id:
                raise ValueError("教师玩家观察与根摘要不一致")
            analysis = rules.analyze(observation, value_limits=_LIMITS)
            candidates = analysis.legal_candidates
            keys = [candidate.action_key for candidate in candidates]
            if (analysis.completeness is not RuleCompleteness.COMPLETE
                    or keys != row["legal_action_keys"]
                    or set(row["outcomes_by_action"]) != set(keys)):
                raise ValueError("教师合法动作与同源规则分析不一致")
            arms = []
            count = row["sample_count"]
            if type(count) is not int or count < 1:
                raise ValueError("教师同根隐藏世界数无效")
            for candidate in candidates:
                features, exact = _features(candidate, observation)
                samples = row["outcomes_by_action"][candidate.action_key]
                if [item["sample"] for item in samples] != list(range(count)):
                    raise ValueError("教师同根相关世界编号不守恒")
                if isinstance(candidate.action, Hu):
                    if any(item["terminal"]["score_delta"][observation.seat]
                           != exact for item in samples):
                        raise ValueError("教师当前胡与同源规则结算不一致")
                    continue
                counts = [0] * len(_CATEGORIES)
                nets = [0.0] * len(_CATEGORIES)
                for item in samples:
                    category = _label(item["terminal"], observation.seat)
                    index = _CATEGORIES.index(category)
                    counts[index] += 1
                    nets[index] += item["terminal"]["score_delta"][observation.seat]
                if sum(counts) != count or abs(sum(nets) / count - sum(
                        counts[index] / count *
                        (nets[index] / counts[index] if counts[index] else 0)
                        for index in range(len(_CATEGORIES)))) > 1e-9:
                    raise ValueError("互斥类别质量或积分分解不守恒")
                arms.append(_Arm(features, tuple(value / count for value in counts),
                                 tuple(nets), count))
            if arms:
                roots.append(_Root(root_id, tuple(arms)))
    return tuple(roots)


def probabilities(features: tuple[float, ...],
                  coefficients: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    """返回按流局／低番本人胡／高番本人胡／他座胡顺序的非负概率。"""

    if (len(features) != len(_FEATURE_NAMES) or len(coefficients) != 3
            or any(len(row) != len(_FEATURE_NAMES) for row in coefficients)):
        raise ValueError("竞争事件模型维度不匹配")
    logits = (0.0,) + tuple(sum(weight * value for weight, value in
                                zip(row, features)) for row in coefficients)
    peak = max(logits)
    weights = tuple(math.exp(value - peak) for value in logits)
    total = sum(weights)
    result = tuple(value / total for value in weights)
    if (not all(math.isfinite(value) and value >= 0 for value in result)
            or abs(sum(result) - 1.0) > 1e-12):
        raise ValueError("竞争事件概率不守恒")
    return result


def expected_net(features: tuple[float, ...], model: dict) -> tuple[float, tuple[float, ...]]:
    """非胡动作的互斥终局期望净分；此值仍依赖训练续打者。"""

    if (model.get("schema") != "vip-p3-competing-terminal-probe/1"
            or tuple(model.get("feature_names", ())) != _FEATURE_NAMES
            or tuple(model.get("category_order", ())) != _CATEGORIES):
        raise ValueError("竞争终局模型版本或类别顺序不匹配")
    coefficients = tuple(tuple(row) for row in model["coefficients"])
    probability = probabilities(features, coefficients)
    utilities = tuple(model["category_mean_net"])
    if len(utilities) != len(_CATEGORIES) or utilities[0] != 0:
        raise ValueError("竞争终局的流局或条件净分维度无效")
    score = sum(p * value for p, value in zip(probability, utilities))
    if not math.isfinite(score):
        raise ValueError("竞争终局期望净分非有限值")
    return score, probability


def fit(paths: tuple[Path, ...]) -> dict:
    """每根总权重一，拟合互斥概率并保留类别条件净分和训练校准账。"""

    roots = _read_roots(paths)
    if not roots:
        raise ValueError("训练来源没有非胡观察根")
    dimension = len(_FEATURE_NAMES)
    empirical = [0.0] * len(_CATEGORIES)
    net_sum = [0.0] * len(_CATEGORIES)
    for root in roots:
        for arm in root.arms:
            weight = 1 / len(root.arms)
            for index, fraction in enumerate(arm.category_fraction):
                empirical[index] += weight * fraction
                net_sum[index] += weight * arm.category_net_sum[index] / arm.sample_count
    means = [net_sum[index] / empirical[index] if empirical[index] else 0.0
             for index in range(len(_CATEGORIES))]
    if means[0] != 0 or any(empirical[index] <= 0 for index in range(1, 4)):
        raise ValueError("训练类别缺失或流局结算非零，不能拟合首版探针")
    base = empirical[0]
    coefficients = [[0.0] * dimension for _ in range(3)]
    for index in range(3):
        coefficients[index][0] = math.log(empirical[index + 1] / base)
    for _ in range(_STEPS):
        gradient = [[0.0] * dimension for _ in range(3)]
        for root in roots:
            weight = 1.0 / (len(roots) * len(root.arms))
            for arm in root.arms:
                prediction = probabilities(arm.features, tuple(
                    tuple(row) for row in coefficients))
                for category in range(3):
                    residual = weight * (prediction[category + 1] -
                                         arm.category_fraction[category + 1])
                    for feature in range(dimension):
                        gradient[category][feature] += residual * arm.features[feature]
        for category in range(3):
            for feature in range(dimension):
                penalty = 0.0 if feature == 0 else _RIDGE * coefficients[category][feature]
                coefficients[category][feature] -= _LEARNING_RATE * (
                    gradient[category][feature] + penalty)
    frozen = tuple(tuple(row) for row in coefficients)
    predicted = [0.0] * len(_CATEGORIES)
    brier = 0.0
    for root in roots:
        weight = 1.0 / (len(roots) * len(root.arms))
        for arm in root.arms:
            prob = probabilities(arm.features, frozen)
            for index in range(len(_CATEGORIES)):
                predicted[index] += weight * prob[index]
                brier += weight * (prob[index] ** 2 -
                                   2 * prob[index] * arm.category_fraction[index] +
                                   arm.category_fraction[index])
    empirical = [value / len(roots) for value in empirical]
    if abs(sum(empirical) - 1) > 1e-12 or abs(sum(predicted) - 1) > 1e-12:
        raise ValueError("训练类别质量不守恒")
    return {
        "schema": "vip-p3-competing-terminal-probe/1",
        "scope": "offline_shape_continuation_preflight_not_C_alg",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "category_order": list(_CATEGORIES),
        "feature_names": list(_FEATURE_NAMES),
        "feature_source_sha256": hashlib.sha256((Path(__file__).resolve().parent /
            "vip_p3_value_fit_probe.py").read_bytes()).hexdigest(),
        "training_sources": [{"path": str(path),
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                             for path in paths],
        "root_count": len(roots),
        "non_hu_action_count": sum(len(root.arms) for root in roots),
        "root_weighting": "one_per_PlayerObservation; equal_non_hu_arms; correlated_worlds_within_arm",
        "steps": _STEPS, "learning_rate": _LEARNING_RATE, "ridge": _RIDGE,
        "coefficients": [list(row) for row in frozen],
        "category_mean_net": means,
        "training_empirical_category_mass": empirical,
        "training_predicted_category_mass": predicted,
        "training_brier_multiclass": brier,
        "immediate_hu_exact": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    print(json.dumps(fit(tuple(args.training)), ensure_ascii=False,
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
