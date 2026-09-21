"""R18 条件一次自摸代理；消费 ``hangma`` 已生产的完整动作价值事实。

本模块不重算胡牌、爆头、链、合法性或结算。它把规则层
``CandidateValueFacts`` 中的“候选动作完成后，下一次本人摸牌立即胡”路线
转换为同一题内可比较的期望积分。该数只在声明的交换性未知牌假设下成立，
不含他家先胡、鸣牌、轮转生存率或更远续值；必须经配对反事实校准后才能
用于隐藏能力门。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Tuple

from hangma_bot.hangma.interface import RuleCompleteness, ValueCoverage
from hangma_bot.hangma.internal_types import TILE_INDEX
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.policy.interface import DecisionRequest

from .opportunity_capability import OracleActionValue


ORACLE_VERSION = "hangma-one-self-draw-score-delta/1"


@dataclass(frozen=True)
class OneDrawOracleResult:
    """一次自摸代理的动作值与不能计值的明确原因。"""

    values: Tuple[OracleActionValue, ...]
    issues: Tuple[str, ...]
    unseen_tile_count: int | None


def _route_value(request: DecisionRequest, candidate, denominator: int):
    facts = candidate.value_facts
    if facts is None:
        return None, "缺少 CandidateValueFacts"
    if facts.coverage is not ValueCoverage.COMPLETE:
        return None, "一次摸牌价值覆盖不是 COMPLETE"
    if facts.immediate_settlement is not None:
        return (
            float(facts.immediate_settlement.score_delta[request.observation.seat]),
            "当前合法胡的确定结算",
        )
    if not facts.routes:
        return 0.0, "完整一次摸牌范围内没有直接胡路线"

    groups = defaultdict(list)
    for route in facts.routes:
        groups[route.followup_discard].append(route)
    group_values = []
    for followup, routes in groups.items():
        seen_codes = set()
        numerator = 0.0
        for route in routes:
            settlement = float(route.conditional_settlement.score_delta[request.observation.seat])
            for useful in route.useful_tiles:
                if useful.code in seen_codes:
                    return None, "同一后续弃牌内重复出现条件进张 " + useful.code
                seen_codes.add(useful.code)
                numerator += settlement * useful.remaining_estimate
        group_values.append((numerator / denominator, followup))
    value, followup = max(
        group_values,
        key=lambda item: (item[0], "" if item[1] is None else item[1]),
    )
    return value, (
        "动作后下一次本人摸牌立即胡的条件期望；后续弃牌="
        + ("无" if followup is None else followup)
    )


def build_one_draw_self_win_oracle(request: DecisionRequest) -> OneDrawOracleResult:
    """把全合法动作投影为一次自摸条件期望；缺一项就由上层退出整题。

    分母是玩家视角全部未知物理牌数；在“他家暗牌与未来牌墙对玩家交换”
    的代理假设下，逐码未知容量除以该分母。数值误差界为零只表示对该有限
    代理的计算是确定的，不表示它与完整桌赛真实动作价值无偏。
    """

    issues = []
    if request.rules.completeness is not RuleCompleteness.COMPLETE:
        return OneDrawOracleResult(
            (), ("RuleAnalysis 不是 COMPLETE",), None,
        )
    unseen = count_unseen_tiles(request.observation)
    if any(value is None for value in unseen):
        return OneDrawOracleResult(
            (), ("未知牌容量包含矛盾牌码",), None,
        )
    denominator = sum(int(value) for value in unseen)
    if denominator <= 0:
        return OneDrawOracleResult((), ("未知牌容量为零",), denominator)

    values = []
    for candidate in request.rules.legal_candidates:
        value, evidence = _route_value(request, candidate, denominator)
        if value is None:
            issues.append(candidate.action_key + ": " + evidence)
            continue
        # 路线的逐码容量必须由同一玩家视角牌池容纳。违反时说明规则事实、
        # 观察计数或题目身份至少有一项漂移，不能用截断掩盖。
        invalid = False
        facts = candidate.value_facts
        if facts is not None:
            for route in facts.routes:
                for useful in route.useful_tiles:
                    capacity = unseen[TILE_INDEX[useful.code]]
                    if capacity is None or useful.remaining_estimate > capacity:
                        issues.append(
                            candidate.action_key + ": 进张容量超过同题未知牌池 "
                            + useful.code
                        )
                        invalid = True
                        break
                if invalid:
                    break
        if invalid:
            continue
        values.append(
            OracleActionValue(
                action_key=candidate.action_key,
                value=value,
                error_bound=0.0,
                oracle_level="declared_conditional_proxy",
                evidence=evidence + "；" + ORACLE_VERSION,
            )
        )
    return OneDrawOracleResult(tuple(values), tuple(issues), denominator)


__all__ = [
    "ORACLE_VERSION",
    "OneDrawOracleResult",
    "build_one_draw_self_win_oracle",
]
