"""弃牌动作价值模型使用的玩家可见、座位相对化特征编码。"""

from __future__ import annotations

from typing import Any

from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, CANONICAL_TILE_ORDER, Discard
from hangma_bot.policy.interface import DecisionRequest

from .claim_value_features import (
    _candidate_facts,
    _observation,
    _optional,
    _value_facts,
)


SCHEMA = "r11-discard-value-features/1"


def _discard_action(candidate: Any, focal_seat: int) -> dict[str, Any]:
    """编码一个规则确认合法的具体弃牌及其已有规则事实。"""

    action = candidate.action
    if not isinstance(action, Discard):
        raise ValueError("R11 首版只接受合法弃牌动作")
    return {
        "kind": "discard",
        "tile": CANONICAL_TILE_INDEX[action.tile.code],
        "facts": _candidate_facts(candidate.facts),
        "value_facts": _value_facts(candidate.value_facts, focal_seat),
    }


def encode_discard_value_features(
    request: DecisionRequest, discard_action_key: str
) -> dict[str, Any]:
    """生成 R11 单个弃牌动作的玩家可见价值输入。

    编码只消费线上策略本来可见的 ``DecisionRequest``。它不读取模拟器
    ``WorldState``、他家暗手、未来牌墙、来源根、面板种子、对手实现或
    续打结果；向听、有效牌、条件路线和结算只使用 ``HangmaRules`` 已经
    生产的候选事实。四家向量按本人、下家、对家、上家排列。
    """

    by_key = {candidate.action_key: candidate for candidate in request.rules.legal_candidates}
    try:
        candidate = by_key[discard_action_key]
    except KeyError as exc:
        raise ValueError("指定弃牌不属于当前规则合法候选") from exc
    observation = request.observation
    ranking = sorted(request.competition.ranking, key=lambda item: item.rank)
    return {
        "schema": SCHEMA,
        "tile_order": list(CANONICAL_TILE_ORDER),
        "observation": _observation(observation),
        "competition": {
            "stage_no": _optional(request.competition.stage_no),
            "stage_role": _optional(request.competition.stage_role),
            "stage_total": _optional(request.competition.stage_total),
            "participant_rank": _optional(request.competition.participant_rank),
            "ranking": [
                {
                    "rank": item.rank,
                    "total_score": item.total_score,
                    "place_points": item.place_points,
                    "god_count": item.god_count,
                    "games_played": item.games_played,
                }
                for item in ranking
            ],
        },
        "rules": {
            "completeness": request.rules.completeness.value,
            "ruleset_version": request.rules.ruleset_version,
            "issue_areas": sorted(item.area for item in request.rules.issues),
        },
        "discard": _discard_action(candidate, observation.seat),
    }


__all__ = ["SCHEMA", "encode_discard_value_features"]
