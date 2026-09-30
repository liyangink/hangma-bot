"""P3 动作后态互斥终局积分探针；开发诊断，不是线上策略。

与旧探针使用相同冻结教师、终局类别和优化参数，只追加已生效或
明确标注“若获裁决”的后态牌形。当前胡始终走规则精确结算。
"""

from __future__ import annotations

import argparse
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

from scripts.vip_p3_afterstate_contract import AfterstateStatus, project_afterstate
from scripts.vip_p3_competing_tail_audit import _label
from scripts.vip_p3_competing_value_probe import _load
from scripts.vip_p3_value_fit_probe import _FEATURE_NAMES as _BASE_NAMES
from scripts.vip_p3_value_fit_probe import _features as _base_features


_CATEGORIES = ("draw", "self_low", "self_high", "other_win")
_LIMITS = ValueAnalysisLimits(max_expansions=8192)
_STEPS = 800
_LEARNING_RATE = 0.5
_RIDGE = 0.1
_POST_NAMES = (
    "post_effective", "post_conditional_award", "post_unresolved_response",
    "post_meld_count", "post_whites", "post_standard_shanten",
    "post_seven_shanten", "post_seven_available", "post_useful_codes",
    "post_support_exact", "post_positive_codes", "post_unseen_capacity",
    "post_baotou", "post_chain_count", "post_piao", "post_piao_known",
)
FEATURE_NAMES = _BASE_NAMES + _POST_NAMES


@dataclass(frozen=True)
class _Arm:
    """同根一条非胡动作；终局类别按 _CATEGORIES 排列。"""

    features: tuple[float, ...]
    fractions: tuple[float, ...]
    net_sums: tuple[float, ...]
    sample_count: int


@dataclass(frozen=True)
class _Root:
    """一个独立行动前玩家观察，内部动作世界相关。"""

    root_id: str
    arms: tuple[_Arm, ...]


def features(candidate, root, observation) -> tuple[tuple[float, ...], float | None]:
    """只用依法可见观察和同次规则事实；未知容量以掩码表示。"""

    base, exact = _base_features(candidate, observation)
    after = project_afterstate(candidate, root, observation.seat)
    if after.status is AfterstateStatus.EXACT_TERMINAL:
        if exact != after.exact_current_hu_net:
            raise ValueError("当前胡两处同源结算不一致")
        return (0.0,) * len(FEATURE_NAMES), exact
    hand = after.own_shape
    effective = after.status is AfterstateStatus.EFFECTIVE_PENDING_EVENT
    conditional = after.status is AfterstateStatus.CONDITIONAL_AWARD
    unresolved = after.status is AfterstateStatus.UNRESOLVED_RESPONSE
    support = hand is not None and hand.useful_unseen_capacity is not None
    appended = (
        float(effective), float(conditional), float(unresolved),
        hand.meld_count / 4.0 if hand else 0.0,
        hand.whites_held / 4.0 if hand else 0.0,
        hand.standard_shanten / 4.0 if hand else 0.0,
        (hand.seven_pairs_shanten / 4.0
         if hand and hand.seven_pairs_shanten is not None else 0.0),
        float(hand is not None and hand.seven_pairs_shanten is not None),
        hand.useful_code_count / 34.0 if hand else 0.0,
        float(support),
        hand.useful_positive_code_count / 34.0 if support else 0.0,
        hand.useful_unseen_capacity / 100.0 if support else 0.0,
        float(hand.baotou) if hand else 0.0,
        hand.chain_count / 4.0 if hand else 0.0,
        hand.chain_piao / 4.0 if hand and hand.chain_piao is not None else 0.0,
        float(hand is not None and hand.chain_piao is not None),
    )
    result = base + appended
    if len(result) != len(FEATURE_NAMES) or not all(math.isfinite(x) for x in result):
        raise ValueError("动作后态特征维度或数值无效")
    return result, None


def probabilities(x: tuple[float, ...], coefficients: tuple[tuple[float, ...], ...]
                  ) -> tuple[float, ...]:
    """四类互斥终局概率；按流局／低番自胡／高番自胡／他座胡排序。"""

    if len(x) != len(FEATURE_NAMES) or len(coefficients) != 3 or any(
        len(row) != len(FEATURE_NAMES) for row in coefficients
    ):
        raise ValueError("动作后态概率模型维度不匹配")
    logits = (0.0,) + tuple(sum(a * b for a, b in zip(row, x)) for row in coefficients)
    peak = max(logits)
    weights = tuple(math.exp(value - peak) for value in logits)
    total = sum(weights)
    result = tuple(value / total for value in weights)
    if not all(math.isfinite(value) and value >= 0 for value in result) or abs(
        sum(result) - 1.0
    ) > 1e-12:
        raise ValueError("互斥终局概率质量不守恒")
    return result


def _read_roots(paths: tuple[Path, ...]) -> tuple[_Root, ...]:
    """重算规则与后态；教师未来只进入标签，不进入特征。"""

    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    seen = set()
    roots = []
    for path in paths:
        report = _load(path)
        if (report.get("scope") != "P3_offline_teacher_labels_only_not_candidate_policy_value"
                or report.get("continuation_reference", "shape") != "shape"
                or report.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}):
            raise ValueError("后态模型只接收目标配置冻结 shape 教师")
        for row in report["rows"]:
            root_id = row["root_id"]
            if root_id in seen:
                raise ValueError("训练观察根重复")
            seen.add(root_id)
            observation = observation_from_json(row["observation"])
            if hashlib.sha256(repr(observation).encode()).hexdigest() != root_id:
                raise ValueError("训练观察根摘要不一致")
            analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
            candidates = analysis.legal_candidates
            route_roots = analysis.conditional_roots
            keys = [candidate.action_key for candidate in candidates]
            if (analysis.completeness is not RuleCompleteness.COMPLETE
                    or route_roots is None
                    or [root.action_key for root in route_roots] != keys
                    or keys != row["legal_action_keys"]
                    or set(row["outcomes_by_action"]) != set(keys)):
                raise ValueError("训练合法动作或同次条件根不完整")
            count = row["sample_count"]
            if type(count) is not int or count < 1:
                raise ValueError("训练相关隐藏世界数无效")
            arms = []
            for candidate, route in zip(candidates, route_roots):
                x, exact = features(candidate, route, observation)
                samples = row["outcomes_by_action"][candidate.action_key]
                if [sample["sample"] for sample in samples] != list(range(count)):
                    raise ValueError("训练相关隐藏世界编号不守恒")
                if isinstance(candidate.action, Hu):
                    if any(sample["terminal"]["score_delta"][observation.seat] != exact
                           for sample in samples):
                        raise ValueError("教师当前胡与规则结算不一致")
                    continue
                cats = [0] * 4
                nets = [0.0] * 4
                for sample in samples:
                    terminal = sample["terminal"]
                    category = _CATEGORIES.index(_label(terminal, observation.seat))
                    cats[category] += 1
                    nets[category] += terminal["score_delta"][observation.seat]
                if sum(cats) != count:
                    raise ValueError("训练互斥终局类别质量不守恒")
                arms.append(_Arm(x, tuple(value / count for value in cats),
                                 tuple(nets), count))
            if arms:
                roots.append(_Root(root_id, tuple(arms)))
    return tuple(roots)


def fit(paths: tuple[Path, ...]) -> dict:
    """每观察根等权拟合 softmax；类别内净分沿用根加权均值。"""

    roots = _read_roots(paths)
    if not roots:
        raise ValueError("无可拟合观察根")
    dimension = len(FEATURE_NAMES)
    mass = [0.0] * 4
    net = [0.0] * 4
    for root in roots:
        weight = 1.0 / len(root.arms)
        for arm in root.arms:
            for category in range(4):
                mass[category] += weight * arm.fractions[category]
                net[category] += weight * arm.net_sums[category] / arm.sample_count
    means = [net[index] / mass[index] if mass[index] else 0.0 for index in range(4)]
    if means[0] != 0 or any(mass[index] <= 0 for index in range(1, 4)):
        raise ValueError("训练缺互斥终局类别或流局非零支付")
    coefficients = [[0.0] * dimension for _ in range(3)]
    for index in range(3):
        coefficients[index][0] = math.log(mass[index + 1] / mass[0])
    for _ in range(_STEPS):
        gradient = [[0.0] * dimension for _ in range(3)]
        frozen = tuple(tuple(row) for row in coefficients)
        for root in roots:
            weight = 1.0 / (len(roots) * len(root.arms))
            for arm in root.arms:
                predicted = probabilities(arm.features, frozen)
                for category in range(3):
                    residual = weight * (predicted[category + 1] -
                                         arm.fractions[category + 1])
                    for feature, value in enumerate(arm.features):
                        gradient[category][feature] += residual * value
        for category in range(3):
            for feature in range(dimension):
                penalty = 0.0 if feature == 0 else _RIDGE * coefficients[category][feature]
                coefficients[category][feature] -= _LEARNING_RATE * (
                    gradient[category][feature] + penalty)
    frozen = tuple(tuple(row) for row in coefficients)
    return {
        "schema": "vip-p3-poststate-terminal-probe/1",
        "scope": "offline_shape_continuation_development_not_C_alg",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "category_order": list(_CATEGORIES), "feature_names": list(FEATURE_NAMES),
        "feature_sources": [
            {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in (
                Path("scripts/vip_p3_afterstate_contract.py"),
                Path("scripts/vip_p3_value_fit_probe.py"),
            )
        ],
        "training_sources": [{"path": str(path),
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                             for path in paths],
        "root_count": len(roots),
        "non_hu_action_count": sum(len(root.arms) for root in roots),
        "root_weighting": "one_per_PlayerObservation; equal_non_hu_arms",
        "steps": _STEPS, "learning_rate": _LEARNING_RATE, "ridge": _RIDGE,
        "coefficients": [list(row) for row in frozen],
        "category_mean_net": means,
        "training_empirical_category_mass": [value / len(roots) for value in mass],
        "immediate_hu_exact": True,
    }


def expected_net(x: tuple[float, ...], model: dict) -> tuple[float, tuple[float, ...]]:
    """四类概率乘根加权条件均分；仍是依赖冻结续打者的离线估值。"""

    if (model.get("schema") != "vip-p3-poststate-terminal-probe/1"
            or tuple(model.get("feature_names", ())) != FEATURE_NAMES
            or tuple(model.get("category_order", ())) != _CATEGORIES):
        raise ValueError("动作后态模型版本或特征顺序不匹配")
    predicted = probabilities(x, tuple(tuple(row) for row in model["coefficients"]))
    means = model["category_mean_net"]
    if len(means) != 4 or means[0] != 0:
        raise ValueError("动作后态模型类别条件积分无效")
    value = sum(p * score for p, score in zip(predicted, means))
    if not math.isfinite(value):
        raise ValueError("动作后态统一积分非有限值")
    return value, predicted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    print(json.dumps(fit(tuple(args.training)), ensure_ascii=False,
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
