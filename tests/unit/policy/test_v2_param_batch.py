"""新参数批次策略（`v2_hu_upgrade_v2`）：枚举只换权重，不引入任何其它行为差异。

2026-09-18 立：`v2_hu_upgrade_v1` 保持冻结，数值调整由新枚举承载。
本文件是**着陆前置**与**标定触发器**：

* 着陆前置——新枚举在默认权重下必须与冻结 V2 产出完全相同的计划；
* 标定触发器——参数一旦被标定，`test_param_batch_starts_identical_to_frozen_v2` 会转红，
  提醒把「与冻结 V2 逐字相同」改成「与门禁报告口径一致」，避免悄悄改数。
"""

from hangma_bot.bootstrap import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN, AVAILABLE_STRATEGIES
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.policy.weights_v1 import V2_PARAM_BATCH_WEIGHTS
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1

from .support import (
    discards_for, make_budget, make_observation, make_request, make_rules, run_choose,
)


def _request():
    """一个含多候选的真实形状请求：两种权重在同一输入上必须给同一计划。"""

    observation = make_observation()
    candidates = discards_for(("1w", "2w", "9t", "白"))
    return make_request(observation, make_rules(candidates))


def _policy(weights):
    return V2HuUpgradePolicy(
        weights, monotonic=lambda: 0,
        risk_cells=RISK_CELLS, risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN,
    )


def _fingerprint(plan):
    return [(item.rank, item.action_key, item.total_score) for item in plan.candidates]


def test_enum_swaps_weights_only():
    """同一请求上，只换权重常量不改变计划；换权重后计划随权重变化。"""

    request = _request()
    frozen = run_choose(_policy(DEFAULT_WEIGHTS_V1), request, make_budget())
    batch = run_choose(_policy(V2_PARAM_BATCH_WEIGHTS), request, make_budget())
    assert _fingerprint(batch) == _fingerprint(frozen)


def test_param_batch_starts_identical_to_frozen_v2():
    """着陆前置：批次参数此刻与冻结 V2 逐字相同。

    标定某个参数后本条会转红——这是**刻意**的：请连同本用例一起更新为
    「与策略目录门禁报告中的口径一致」，而不是直接删掉断言。
    """

    assert V2_PARAM_BATCH_WEIGHTS == DEFAULT_WEIGHTS_V1


def test_enum_is_configurable():
    """新枚举必须出现在唯一可配置策略名来源里，否则运行配置会拒绝它。"""

    assert "v2_hu_upgrade_v2" in AVAILABLE_STRATEGIES
    assert "v2_hu_upgrade_v1" in AVAILABLE_STRATEGIES  # 冻结版本仍在清单内
