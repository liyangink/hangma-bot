"""新参数批次策略（`v2_hu_upgrade_v2`）：枚举只换权重，默认策略与默认权重一律不动。

2026-09-18 立：`v2_hu_upgrade_v1` 保持冻结，数值调整由新枚举承载（用户裁定）。

本文件承担三件事：

* **批次内容即事实**——`_TUNED_FIELDS` 声明本批次改了哪些字段、改成多少；
  改数必须同时改这里，改错字段/漏改都会转红，防止悄悄改数；
* **不破坏正确性**——两组权重在同一请求上都必须产出合法且带保底的计划；
* **可配置**——新名字必须出现在唯一可配置策略名来源里，否则运行配置会拒绝它。
"""

from dataclasses import fields

from hangma_bot.bootstrap import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN, AVAILABLE_STRATEGIES
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1, V2_PARAM_BATCH_WEIGHTS

from .support import discards_for, make_budget, make_observation, make_request, make_rules, run_choose

#: 本参数批次相对冻结 V2 的**全部**改动；新增/修改参数时必须同步这里。
_TUNED_FIELDS = {
    "safe_tile_bonus": 0.0,  # 无放铳赛制下收益恒 0，却造成 86.7% 的窄进张选择
}


def _request():
    """一个含多候选的真实形状请求：两组权重都要能在它上面给出计划。"""

    return make_request(make_observation(), make_rules(discards_for(("1w", "2w", "9t", "白"))))


def _policy(weights):
    return V2HuUpgradePolicy(
        weights, monotonic=lambda: 0,
        risk_cells=RISK_CELLS, risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN,
    )


def test_param_batch_differs_only_in_declared_fields():
    """批次只改 `_TUNED_FIELDS` 声明的字段，且取值与声明一致。"""

    different = {
        item.name
        for item in fields(DEFAULT_WEIGHTS_V1)
        if getattr(DEFAULT_WEIGHTS_V1, item.name) != getattr(V2_PARAM_BATCH_WEIGHTS, item.name)
    }
    assert different == set(_TUNED_FIELDS), (
        "批次改动与 _TUNED_FIELDS 声明不一致；改数请连同声明一起更新：" + repr(sorted(different))
    )
    for name, value in _TUNED_FIELDS.items():
        assert getattr(V2_PARAM_BATCH_WEIGHTS, name) == value
    assert _TUNED_FIELDS, "空批次等于新枚举与 v1 完全等价，没有可比的差异"


def test_both_weight_sets_produce_usable_plans():
    """两组权重都必须产出非空、rank 连续、候选互不重复的计划。"""

    for label, weights in (("frozen-v2", DEFAULT_WEIGHTS_V1), ("param-batch", V2_PARAM_BATCH_WEIGHTS)):
        plan = run_choose(_policy(weights), _request(), make_budget())
        keys = [item.action_key for item in plan.candidates]
        assert keys, label + " 产出了空计划"
        assert len(keys) == len(set(keys)), label + " 出现重复候选"
        assert [item.rank for item in plan.candidates] == list(range(1, len(keys) + 1)), label + " rank 不连续"


def test_enum_is_configurable():
    """新枚举必须在唯一可配置策略名来源里，且冻结版本不被移除。"""

    assert "v2_hu_upgrade_v2" in AVAILABLE_STRATEGIES
    assert "v2_hu_upgrade_v1" in AVAILABLE_STRATEGIES
