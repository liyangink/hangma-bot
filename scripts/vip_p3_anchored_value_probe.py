"""P3 规则支付锚定的离线积分探针；失败时不得接入 VIP 策略。

仅普通弃牌的一次本人普通摸牌有精确逐码支付与公开容量。把这一项
显式计入积分，再从冻结续打教师拟合其余完整单局净分。首事件频率
是教师路径的观察量，不是官方牌墙概率；本模型仍须新根否证。
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
from hangma_bot.kernel.actions import Discard, Hu
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_competing_value_probe import _load
from scripts.vip_p3_payoff_frontier import (
    extract_payoff_frontier, ordinary_discard_one_draw_component,
)
from scripts.vip_p3_poststate_value_probe import FEATURE_NAMES, features
from scripts.vip_p3_value_fit_probe import _solve


_LIMITS = ValueAnalysisLimits(max_expansions=8192)
_RIDGE = 10.0  # 预先固定，不按开发结果调参
_FEATURE_INDEXES = tuple(i for i, name in enumerate(FEATURE_NAMES)
                         if not name.startswith("one_draw_"))
_FEATURE_NAMES = tuple(FEATURE_NAMES[i] for i in _FEATURE_INDEXES)


@dataclass(frozen=True)
class _Arm:
    """一个合法动作的公开特征及冻结续打者完整单局标签。"""

    action_key: str
    features: tuple[float, ...]
    exact_current_hu: float | None
    direct_component: float  # 仅普通弃牌有值；条件下一本人普通摸牌
    observed_mean_net: float


@dataclass(frozen=True)
class _Root:
    """同一玩家观察下相关隐藏世界的全部合法臂；根等权。"""

    root_id: str
    arms: tuple[_Arm, ...]
    normal_draw_fraction: float | None  # 仅本根普通弃牌臂的首事件频率


def _project(x: tuple[float, ...]) -> tuple[float, ...]:
    """排除旧静态支付特征，避免规则精确支付被线性项重复学习。"""

    if len(x) != len(FEATURE_NAMES):
        raise ValueError("后态特征维度漂移")
    return tuple(x[i] for i in _FEATURE_INDEXES)


def _roots(paths: tuple[Path, ...]) -> tuple[tuple[_Root, ...], dict[str, int]]:
    """重算全部合法根，并核行动前逐码支付与教师下一摸实际结算。"""

    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    roots = []
    counters = {"discard_worlds": 0, "first_normal_draws": 0,
                "direct_hu_worlds": 0, "matched_draw_payoffs": 0,
                "other_first_events": 0}
    seen = set()
    for path in paths:
        report = _load(path)
        if (report.get("scope") !=
                "P3_offline_teacher_labels_only_not_candidate_policy_value"
                or report.get("continuation_reference", "shape") != "shape"
                or report.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}):
            raise ValueError("支付探针只接受目标配置的冻结 shape 续打教师")
        for row in report["rows"]:
            root_id = row["root_id"]
            if root_id in seen:
                raise ValueError("训练观察根重复")
            seen.add(root_id)
            observation = observation_from_json(row["observation"])
            if hashlib.sha256(repr(observation).encode()).hexdigest() != root_id:
                raise ValueError("教师玩家观察摘要不一致")
            analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
            candidates = analysis.legal_candidates
            route_roots = analysis.conditional_roots
            keys = [candidate.action_key for candidate in candidates]
            if (analysis.completeness is not RuleCompleteness.COMPLETE
                    or route_roots is None or any(root.gap_kind is not None for root in route_roots)
                    or [root.action_key for root in route_roots] != keys
                    or keys != row["legal_action_keys"]
                    or set(row["outcomes_by_action"]) != set(keys)):
                raise ValueError("教师同源合法动作或条件根不完整")
            count = row["sample_count"]
            if type(count) is not int or count < 1:
                raise ValueError("教师相关隐藏世界数量无效")
            arms = []
            root_discard_worlds = 0
            root_normal = 0
            for candidate, root in zip(candidates, route_roots):
                key = candidate.action_key
                x, exact = features(candidate, root, observation)
                frontier = extract_payoff_frontier(candidate, root, observation.seat)
                samples = row["outcomes_by_action"][key]
                if [sample["sample"] for sample in samples] != list(range(count)):
                    raise ValueError("教师相关隐藏世界编号不守恒")
                component = 0.0
                cells = {}
                if isinstance(candidate.action, Discard):
                    component = ordinary_discard_one_draw_component(
                        candidate, root, observation.seat
                    ).conditional_exchangeable_direct_hu_net
                    cells = {cell.draw_code: cell for path in frontier.paths
                             if path.conditions.draw_kind == "normal" for cell in path.cells}
                    root_discard_worlds += count
                    counters["discard_worlds"] += count
                nets = []
                for sample in samples:
                    event = sample["first_event"]
                    terminal = sample["terminal"]
                    delta = terminal["score_delta"]
                    if (len(delta) != 4 or any(type(value) is not int for value in delta)
                            or sum(delta) != 0):
                        raise ValueError("教师终局四座整数积分不守恒")
                    net = delta[observation.seat]
                    nets.append(net)
                    if isinstance(candidate.action, Hu):
                        if net != exact or frontier.immediate_hu_net != exact:
                            raise ValueError("当前胡教师结局与规则即时结算不符")
                    if not isinstance(candidate.action, Discard):
                        continue
                    if event["kind"] != "self_normal_draw":
                        counters["other_first_events"] += 1
                        continue
                    counters["first_normal_draws"] += 1
                    root_normal += 1
                    cell = cells.get(event["tile"])
                    actual = event["immediate_hu"]
                    if (cell is None) != (actual is None):
                        raise ValueError("行动前规则支付与下一本人普通摸牌胡资格不符")
                    if cell is not None:
                        if (cell.fan != actual["fan"]
                                or list(cell.score_delta) != actual["score_delta"]
                                or net != cell.own_net or terminal["fan"] != cell.fan):
                            raise ValueError("逐码规则支付或 shape 立即胡与教师结算不符")
                        counters["direct_hu_worlds"] += 1
                        counters["matched_draw_payoffs"] += 1
                arms.append(_Arm(key, _project(x), exact, component,
                                 sum(nets) / count))
            roots.append(_Root(root_id, tuple(arms),
                               root_normal / root_discard_worlds
                               if root_discard_worlds else None))
    return tuple(roots), counters


def _score(arm: _Arm, beta: tuple[float, ...], p_normal: float) -> float:
    """同一积分轴：当前胡准确结算；其余为直接支付加剩余项。"""

    if arm.exact_current_hu is not None:
        return arm.exact_current_hu
    return p_normal * arm.direct_component + sum(
        weight * value for weight, value in zip(beta, arm.features)
    )


def fit(paths: tuple[Path, ...]) -> dict:
    """按观察根等权估首事件频率，并用根内中心化岭回归拟合余项。"""

    roots, counters = _roots(paths)
    normal = [root.normal_draw_fraction for root in roots
              if root.normal_draw_fraction is not None]
    if not roots or not normal:
        raise ValueError("训练来源缺普通弃牌根")
    p_normal = sum(normal) / len(normal)
    if not 0 < p_normal <= 1:
        raise ValueError("训练首次本人普通摸牌频率无效")
    dimension = len(_FEATURE_NAMES)
    gram = [[_RIDGE if i == j else 0.0 for j in range(dimension)]
            for i in range(dimension)]
    rhs = [0.0] * dimension
    for root in roots:
        n = len(root.arms)
        mean_x = [sum(arm.features[i] for arm in root.arms) / n
                  for i in range(dimension)]
        residual = [arm.observed_mean_net - (arm.exact_current_hu or 0.0)
                    - p_normal * arm.direct_component for arm in root.arms]
        mean_y = sum(residual) / n
        for arm, y in zip(root.arms, residual):
            x = [arm.features[i] - mean_x[i] for i in range(dimension)]
            for i in range(dimension):
                rhs[i] += x[i] * (y - mean_y) / n
                for j in range(dimension):
                    gram[i][j] += x[i] * x[j] / n
    beta = _solve(gram, rhs)
    if len(beta) != dimension or not all(math.isfinite(value) for value in beta):
        raise ValueError("剩余积分模型系数无效")
    return {
        "schema": "vip-p3-anchored-payoff-probe/1",
        "scope": "offline_shape_teacher_development_not_C_alg",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "feature_names": list(_FEATURE_NAMES), "ridge": _RIDGE,
        "first_event_normal_draw_root_mean": p_normal,
        "direct_payoff_condition": "first_self_normal_draw_and_exchangeable_public_unseen",
        "residual_label": "complete_hand_own_net_minus_exact_hu_minus_predicted_direct_payoff",
        "root_count": len(roots), "discard_root_count": len(normal),
        "counters": counters,
        "coefficients": list(beta),
        "training_sources": [{"path": str(path),
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                             for path in paths],
        "feature_source_sha256": hashlib.sha256(Path(
            "scripts/vip_p3_poststate_value_probe.py").read_bytes()).hexdigest(),
    }


def predict_observation(observation, model: dict) -> list[dict]:
    """只用当前玩家观察与同次规则事实给全部合法动作记分。"""

    if (model.get("schema") != "vip-p3-anchored-payoff-probe/1"
            or model.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}
            or model.get("feature_names") != list(_FEATURE_NAMES)):
        raise ValueError("支付模型版本、规则配置或特征顺序不符")
    beta = tuple(model["coefficients"])
    p_normal = model["first_event_normal_draw_root_mean"]
    if (len(beta) != len(_FEATURE_NAMES) or not all(math.isfinite(x) for x in beta)
            or not isinstance(p_normal, (float, int)) or not 0 <= p_normal <= 1):
        raise ValueError("支付模型概率或剩余项系数无效")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
    if (analysis.completeness is not RuleCompleteness.COMPLETE
            or analysis.conditional_roots is None
            or any(root.gap_kind is not None for root in analysis.conditional_roots)
            or len(analysis.legal_candidates) != len(analysis.conditional_roots)):
        raise ValueError("预测窗口规则事实或条件根不完整")
    rows = []
    for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots):
        x, exact = features(candidate, root, observation)
        direct = (ordinary_discard_one_draw_component(
            candidate, root, observation.seat
        ).conditional_exchangeable_direct_hu_net
                  if isinstance(candidate.action, Discard) else 0.0)
        arm = _Arm(candidate.action_key, _project(x), exact, direct, 0.0)
        rows.append({"action_key": arm.action_key,
                     "exact_current_hu_net": exact,
                     "first_normal_draw_direct_payoff": p_normal * direct,
                     "residual_tail_estimate": 0.0 if exact is not None else sum(
                         weight * value for weight, value in zip(beta, arm.features)),
                     "predicted_own_net": _score(arm, beta, p_normal)})
    return sorted(rows, key=lambda row: (-round(row["predicted_own_net"], 8),
                                         row["action_key"] != "hu", row["action_key"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", nargs="+", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(fit(tuple(args.training)), ensure_ascii=False,
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
