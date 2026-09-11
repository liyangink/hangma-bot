"""计算给定单局目标下的期望效用；不推测晋级线，不选择动作。"""

import math

from hangma_bot.kernel.outcomes import (
    HandObjectiveKind, HandOutcomeObjective, JointOutcome, MeanOutcome,
)


def expected_utility(estimate: MeanOutcome | JointOutcome, objective: HandOutcomeObjective) -> float:
    """将模型结果转换为目标值；未知或能力不够时抛 ValueError。

    EXPECTED_SCORE 返回本人期望净增桌内积分。TARGET_PROBABILITY 返回
    本单局净增达到显式门槛的概率（0—1），不是海选晋级概率。
    不从四家均值推断非线性目标，也不对模型输出重复加启发式分。
    """
    if not isinstance(estimate, (MeanOutcome, JointOutcome)) or not isinstance(objective, HandOutcomeObjective):
        raise ValueError("结果或目标类型错误")
    if objective.kind is HandObjectiveKind.UNAVAILABLE:
        raise ValueError("objective_unavailable")
    if objective.kind is HandObjectiveKind.EXPECTED_SCORE:
        if isinstance(estimate, MeanOutcome):
            return estimate.score_delta[objective.seat]
        return math.fsum(a.probability * a.score_delta[objective.seat] for a in estimate.atoms)
    if not isinstance(estimate, JointOutcome):
        raise ValueError("joint_distribution_required")
    return math.fsum(a.probability for a in estimate.atoms if a.score_delta[objective.seat] >= objective.target_score_delta)
