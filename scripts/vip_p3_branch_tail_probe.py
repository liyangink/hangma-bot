"""P3 按下一摸牌分支聚合后继牌形的离线积分探针。

首次事件分布仍取冻结教师的根均频率；公开未见容量仅按交换性近似
加权，绝不当真实牌墙概率。新增特征从行动前 P1 条件前沿逐摸牌码
取两种抓打包络的最佳续行牌效，再聚合。其余完整单局积分沿用根内
中心化岭回归；仅供已开根开发诊断，未校准不得接线上或称 C_alg。
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
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_anchored_value_probe import _roots as _anchored_roots
from scripts.vip_p3_anchored_value_probe import _FEATURE_NAMES as _BASE_NAMES
from scripts.vip_p3_anchored_value_probe import _project
from scripts.vip_p3_competing_value_probe import _load
from scripts.vip_p3_payoff_frontier import ordinary_discard_one_draw_component
from scripts.vip_p3_poststate_value_probe import features
from scripts.vip_p3_value_fit_probe import _solve


_LIMITS = ValueAnalysisLimits(max_expansions=8192)
_RIDGE = 10.0  # 与前一锚定探针相同，未用本批结局搜索超参
_BRANCH_NAMES = (
    "branch_available",
    "restricted_expected_best_shanten",
    "unrestricted_expected_best_shanten",
    "restricted_expected_best_support",
    "unrestricted_expected_best_support",
    "restricted_expected_frontier_size",
    "unrestricted_expected_frontier_size",
)
FEATURE_NAMES = _BASE_NAMES + _BRANCH_NAMES


@dataclass(frozen=True)
class _Arm:
    """一条合法动作的行动前特征及冻结教师单局净分标签。"""

    action_key: str
    features: tuple[float, ...]
    exact_current_hu: float | None
    direct_component: float  # 若首次事件为本人普通摸牌的规则支付近似
    observed_mean_net: float


@dataclass(frozen=True)
class _Root:
    """同一玩家观察下全部合法动作，统计时每根总权重相同。"""

    root_id: str
    arms: tuple[_Arm, ...]
    normal_draw_fraction: float | None


def branch_features(frontier_root) -> tuple[float, ...]:
    """按互斥摸牌码聚合两种抓打包络的后继牌形，缺边即拒绝。"""

    if frontier_root.gap_kind is not None or not frontier_root.structure_complete:
        raise ValueError("普通弃牌的条件后继前沿不完整")
    edges = frontier_root.draw_edges
    total = sum(edge.support_capacity for edge in edges)
    if any(edge.support_capacity <= 0 for edge in edges):
        raise ValueError("条件下一摸牌边出现非正公开容量")
    if total == 0:
        return (0.0,) * len(_BRANCH_NAMES)
    sums = [0.0] * 6
    for edge in edges:
        weight = edge.support_capacity / total
        for index, envelope in enumerate((edge.successor.restricted,
                                          edge.successor.unrestricted)):
            leaves = envelope.discard_frontier
            best = min(leaves, key=lambda leaf: (
                leaf.shanten_after, -leaf.support_remaining, leaf.action_key,
            )) if leaves else None
            sums[index] += weight * (best.shanten_after / 4.0 if best else 1.0)
            sums[2 + index] += weight * (best.support_remaining / 100.0
                                         if best else 0.0)
            sums[4 + index] += weight * (len(leaves) / 16.0)
    result = (1.0, *sums)
    if len(result) != len(_BRANCH_NAMES) or not all(math.isfinite(x) for x in result):
        raise ValueError("下一摸牌分支特征维度或数值无效")
    return result


def _rows(paths: tuple[Path, ...]) -> tuple[_Root, ...]:
    """复用已核教师标签，追加同次 P1 后继，不读取其未来事件。"""

    base_roots, _ = _anchored_roots(paths)
    by_id = {root.root_id: root for root in base_roots}
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    result = []
    seen = set()
    for path in paths:
        report = _load(path)
        for row in report["rows"]:
            root_id = row["root_id"]
            if root_id in seen or root_id not in by_id:
                raise ValueError("下一摸牌训练观察根重复或教师标签缺失")
            seen.add(root_id)
            observation = observation_from_json(row["observation"])
            if hashlib.sha256(repr(observation).encode()).hexdigest() != root_id:
                raise ValueError("下一摸牌训练玩家观察摘要不符")
            analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
            frontier = analysis.route_frontier
            if (analysis.completeness is not RuleCompleteness.COMPLETE
                    or frontier is None
                    or [item.action_key for item in analysis.legal_candidates] !=
                    row["legal_action_keys"]
                    or [item.action_key for item in frontier.roots] !=
                    row["legal_action_keys"]):
                raise ValueError("下一摸牌训练合法动作与前沿不完整")
            base = {arm.action_key: arm for arm in by_id[root_id].arms}
            arms = []
            for candidate, route in zip(analysis.legal_candidates, frontier.roots):
                arm = base[candidate.action_key]
                branch = (branch_features(route) if isinstance(candidate.action, Discard)
                          else (0.0,) * len(_BRANCH_NAMES))
                arms.append(_Arm(arm.action_key, arm.features + branch,
                                 arm.exact_current_hu, arm.direct_component,
                                 arm.observed_mean_net))
            result.append(_Root(root_id, tuple(arms),
                                by_id[root_id].normal_draw_fraction))
    if len(result) != len(base_roots):
        raise ValueError("下一摸牌训练根数不守恒")
    return tuple(result)


def fit(paths: tuple[Path, ...]) -> dict:
    """维持支付锚定概率和岭强度，只检验分支牌形能否补充余项。"""

    roots = _rows(paths)
    normal = [root.normal_draw_fraction for root in roots
              if root.normal_draw_fraction is not None]
    if not normal:
        raise ValueError("下一摸牌训练缺普通弃牌根")
    p_normal = sum(normal) / len(normal)
    nfeat = len(FEATURE_NAMES)
    gram = [[_RIDGE if i == j else 0.0 for j in range(nfeat)]
            for i in range(nfeat)]
    rhs = [0.0] * nfeat
    for root in roots:
        n = len(root.arms)
        mean_x = [sum(arm.features[i] for arm in root.arms) / n
                  for i in range(nfeat)]
        y = [arm.observed_mean_net - (arm.exact_current_hu or 0.0)
             - p_normal * arm.direct_component for arm in root.arms]
        mean_y = sum(y) / n
        for arm, target in zip(root.arms, y):
            x = [arm.features[i] - mean_x[i] for i in range(nfeat)]
            for i in range(nfeat):
                rhs[i] += x[i] * (target - mean_y) / n
                for j in range(nfeat):
                    gram[i][j] += x[i] * x[j] / n
    beta = _solve(gram, rhs)
    if len(beta) != nfeat or not all(math.isfinite(x) for x in beta):
        raise ValueError("下一摸牌分支余项系数无效")
    return {
        "schema": "vip-p3-branch-tail-probe/1",
        "scope": "offline_shape_teacher_development_not_C_alg",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "feature_names": list(FEATURE_NAMES), "ridge": _RIDGE,
        "first_event_normal_draw_root_mean": p_normal,
        "direct_payoff_condition": "first_self_normal_draw_and_exchangeable_public_unseen",
        "branch_projection": "P1_both_catch_envelopes_weighted_by_public_capacity_not_wall_probability",
        "root_count": len(roots),
        "coefficients": list(beta),
        "training_sources": [{"path": str(path),
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                             for path in paths],
        "feature_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def predict_observation(observation, model: dict) -> list[dict]:
    """当前玩家观察的全部合法动作在同一积分尺度记账；缺证据即停止。"""

    if (model.get("schema") != "vip-p3-branch-tail-probe/1"
            or model.get("feature_names") != list(FEATURE_NAMES)
            or model.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}):
        raise ValueError("下一摸牌模型版本或规则配置不符")
    beta = tuple(model["coefficients"])
    p_normal = model["first_event_normal_draw_root_mean"]
    if (len(beta) != len(FEATURE_NAMES) or not all(math.isfinite(x) for x in beta)
            or not isinstance(p_normal, (int, float)) or not 0 <= p_normal <= 1):
        raise ValueError("下一摸牌模型参数无效")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
    frontier = analysis.route_frontier
    if (analysis.completeness is not RuleCompleteness.COMPLETE
            or frontier is None
            or analysis.conditional_roots is None
            or any(root.gap_kind is not None for root in analysis.conditional_roots)
            or [item.action_key for item in analysis.conditional_roots] !=
            [item.action_key for item in analysis.legal_candidates]
            or [item.action_key for item in frontier.roots] !=
            [item.action_key for item in analysis.legal_candidates]):
        raise ValueError("下一摸牌预测的合法动作与规则前沿不完整")
    rows = []
    for candidate, conditional, route in zip(
        analysis.legal_candidates, analysis.conditional_roots, frontier.roots,
    ):
        x, exact = features(candidate, conditional, observation)
        branch = (branch_features(route) if isinstance(candidate.action, Discard)
                  else (0.0,) * len(_BRANCH_NAMES))
        direct = (ordinary_discard_one_draw_component(
            candidate, conditional, observation.seat
        ).conditional_exchangeable_direct_hu_net if isinstance(candidate.action, Discard)
                  else 0.0)
        residual = 0.0 if exact is not None else sum(
            a * b for a, b in zip(beta, _project(x) + branch))
        value = exact if exact is not None else p_normal * direct + residual
        rows.append({"action_key": candidate.action_key,
                     "exact_current_hu_net": exact,
                     "first_normal_draw_direct_payoff": p_normal * direct,
                     "conditional_branch_tail_estimate": residual,
                     "predicted_own_net": value})
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
