"""吃碰动作价值模型使用的玩家可见、座位相对化特征编码。"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from hangma_bot.hangma.interface import (
    CandidateFacts,
    CandidateValueFacts,
    FollowupBranchFacts,
    RuleCandidate,
    Settlement,
    UsefulTileFact,
    ValueRoute,
)
from hangma_bot.kernel.actions import (
    CANONICAL_TILE_INDEX,
    CANONICAL_TILE_ORDER,
    Chi,
    Peng,
    Tile,
)
from hangma_bot.kernel.observation import PlayerObservation, PublicEvent, PublicMeld
from hangma_bot.policy.interface import DecisionRequest


SCHEMA = "r10-claim-value-features/1"


def _optional(value: Any) -> dict[str, Any]:
    """显式区分已知零值与未知值，避免用零填充未知事实。"""

    return {"known": value is not None, "value": value}


def _relative_seat(seat: Optional[int], focal_seat: int) -> Optional[int]:
    """把绝对座位转成以本人为 0、下家为 1 的相对座位。"""

    return None if seat is None else (seat - focal_seat) % 4


def _relative_vector(values: Sequence[Any], focal_seat: int) -> list[Any]:
    """按本人、下家、对家、上家重排四家向量。"""

    if len(values) != 4:
        raise ValueError("座位向量必须恰好包含四家")
    return [values[(focal_seat + offset) % 4] for offset in range(4)]


def _tile_index(tile: Optional[Tile | str]) -> Optional[int]:
    """把规范牌值转成唯一 0—33 下标；空值保持为空。"""

    if tile is None:
        return None
    code = tile.code if isinstance(tile, Tile) else tile
    return CANONICAL_TILE_INDEX[code]


def _tile_counts(tiles: Iterable[Tile | str]) -> list[int]:
    """按仓库唯一规范牌序生成 34 维计数。"""

    counts = [0] * len(CANONICAL_TILE_ORDER)
    for tile in tiles:
        index = _tile_index(tile)
        assert index is not None
        counts[index] += 1
    return counts


def _tile_sequence(tiles: Iterable[Tile | str]) -> list[int]:
    """保留公开牌河或事件中的先后顺序。"""

    result: list[int] = []
    for tile in tiles:
        index = _tile_index(tile)
        assert index is not None
        result.append(index)
    return result


def _useful_tiles(values: Optional[tuple[UsefulTileFact, ...]]) -> dict[str, Any]:
    """编码有效牌未见张数，并保留未分析与已知空集合的差异。"""

    if values is None:
        return {"known": False, "remaining_by_tile": None}
    remaining = [0] * len(CANONICAL_TILE_ORDER)
    for item in values:
        remaining[CANONICAL_TILE_INDEX[item.code]] = item.remaining_estimate
    return {"known": True, "remaining_by_tile": remaining}


def _meld(meld: PublicMeld, focal_seat: int) -> dict[str, Any]:
    """编码一组公开副露，不携带绝对座号。"""

    return {
        "owner_relative_seat": _relative_seat(meld.seat, focal_seat),
        "kind": meld.kind,
        "tile_counts": _tile_counts(meld.tiles),
        "from_relative_seat": _optional(_relative_seat(meld.from_seat, focal_seat)),
    }


def _event(event: PublicEvent, focal_seat: int) -> dict[str, Any]:
    """编码已公开事件；省略墙上时钟和自由文本计番明细。"""

    return {
        "seq": event.seq,
        "kind": event.kind,
        "relative_seat": _optional(_relative_seat(event.seat, focal_seat)),
        "tiles": _tile_sequence(event.tiles),
        "detail_kind": _optional(event.detail_kind),
        "catch_play": _optional(event.catch_play),
        "gang_replenish": _optional(event.gang_replenish),
        "response_window": _optional(event.response_window),
        "result_draw": _optional(event.result_draw),
        "result_fan": _optional(event.result_fan),
        "result_scores": _optional(
            None
            if event.result_scores is None
            else _relative_vector(event.result_scores, focal_seat)
        ),
        "final_scores": _optional(
            None
            if event.final_scores is None
            else _relative_vector(event.final_scores, focal_seat)
        ),
        "claimed_tile": _optional(_tile_index(event.claimed_tile)),
    }


def _observation(observation: PlayerObservation) -> dict[str, Any]:
    """无损保留决策相关公开状态，并删除场次身份与绝对座号。"""

    seat = observation.seat
    discards = _relative_vector(observation.discards, seat)
    melds = _relative_vector(observation.melds, seat)
    return {
        "phase": observation.phase,
        "round_no": observation.round_no,
        "snapshot_seq": observation.snapshot_seq,
        "dealer_relative_seat": _relative_seat(observation.dealer_seat, seat),
        "turn_relative_seat": _relative_seat(observation.turn_seat, seat),
        "responding_relative_seats": sorted(
            _relative_seat(value, seat) for value in observation.responding_seats
        ),
        "my_hand_counts": _tile_counts(observation.my_hand),
        "drawn_tile": _optional(_tile_index(observation.drawn_tile)),
        "discards": [
            {"sequence": _tile_sequence(river), "counts": _tile_counts(river)}
            for river in discards
        ],
        "melds": [
            [_meld(item, seat) for item in seat_melds]
            for seat_melds in melds
        ],
        "hand_counts": _relative_vector(observation.hand_counts, seat),
        "last_discard": _optional(
            None
            if observation.last_discard is None
            else {
                "relative_seat": _relative_seat(observation.last_discard.seat, seat),
                "tile": _tile_index(observation.last_discard.tile),
                "seq": observation.last_discard.seq,
            }
        ),
        "remaining_tile_count": _optional(observation.remaining_tile_count),
        "scores": _relative_vector(observation.scores, seat),
        "rule_state": {
            "wealth_god": _tile_index(observation.rule_state.wealth_god),
            "baotou": observation.rule_state.baotou,
            "chain_count": observation.rule_state.chain_count,
            "catch_play": observation.rule_state.catch_play,
            "catch_play_owner_relative_seat": _optional(
                _relative_seat(observation.rule_state.catch_play_owner_seat, seat)
            ),
        },
        "public_history": [_event(item, seat) for item in observation.public_history],
        "consumed_seq": _optional(observation.consumed_seq),
        "history_complete": observation.history_complete,
        "chain_piao": _optional(observation.chain_piao),
        "gang_draw": _optional(observation.gang_draw),
        "observation_issues": sorted(observation.observation_issues),
    }


def _settlement(value: Settlement, focal_seat: int) -> dict[str, Any]:
    """编码条件结算数值；不使用可变自由文本明细。"""

    return {
        "score_delta": _relative_vector(value.score_delta, focal_seat),
        "fan": value.fan,
    }


def _route(value: ValueRoute, focal_seat: int) -> dict[str, Any]:
    """编码规则模块产生的一次摸牌条件路线。"""

    return {
        "settlement": _settlement(value.conditional_settlement, focal_seat),
        "shanten": value.shanten,
        "useful_tiles": _useful_tiles(value.useful_tiles),
        "followup_discard": _optional(_tile_index(value.followup_discard)),
        "conditions": {
            "draw_kind": value.conditions.draw_kind,
            "pre_draw_hand_counts": _tile_counts(value.conditions.pre_draw_hand),
            "meld_count": value.conditions.meld_count,
            "chain_count": value.conditions.chain_count,
            "chain_piao": value.conditions.chain_piao,
            "baotou": value.conditions.baotou,
        },
    }


def _value_facts(
    value: Optional[CandidateValueFacts], focal_seat: int
) -> dict[str, Any]:
    """编码分值事实，并保留未提供、部分和完整覆盖的状态。"""

    if value is None:
        return {"known": False, "coverage": None, "routes": None}
    return {
        "known": True,
        "coverage": value.coverage.value,
        "immediate_settlement": _optional(
            None
            if value.immediate_settlement is None
            else _settlement(value.immediate_settlement, focal_seat)
        ),
        "routes": [_route(item, focal_seat) for item in value.routes],
        "issue_areas": sorted(item.area for item in value.issues),
    }


def _followup(value: FollowupBranchFacts) -> dict[str, Any]:
    """编码一条吃碰后的合法弃牌分支。"""

    return {
        "discard": _tile_index(value.followup_discard),
        "combined_shanten": _optional(value.combined_shanten),
        "standard_shanten": _optional(value.standard_shanten_after),
        "seven_pairs_shanten": _optional(value.seven_pairs_shanten_after),
        "useful_tiles": _useful_tiles(value.useful_tiles),
        "support_remaining": _optional(value.support_remaining),
    }


def _candidate_facts(value: Optional[CandidateFacts]) -> dict[str, Any]:
    """编码唯一规则模块提供的牌效事实，不复算麻将规则。"""

    if value is None:
        return {"known": False}
    followups = None
    if value.followup_branches is not None:
        followups = [
            _followup(item)
            for item in sorted(
                value.followup_branches,
                key=lambda item: CANONICAL_TILE_INDEX[item.followup_discard],
            )
        ]
    return {
        "known": True,
        "fact_kind": value.fact_kind.value,
        "shanten": _optional(value.shanten_after),
        "useful_tiles": _useful_tiles(value.useful_tiles),
        "best_followup_discard": _optional(_tile_index(value.best_followup_discard)),
        "replacement_draw_unknown": value.replacement_draw_unknown,
        "completeness": value.completeness.value,
        "standard_shanten": _optional(value.standard_shanten_after),
        "seven_pairs_shanten": _optional(value.seven_pairs_shanten_after),
        "standard_useful_tiles": _useful_tiles(value.standard_useful_tiles),
        "seven_pairs_useful_tiles": _useful_tiles(value.seven_pairs_useful_tiles),
        "followup_branches": _optional(followups),
        "family_progress": [
            {
                "family": item.family.value,
                "progress": item.progress.value,
                "route_status": item.route_status.value,
            }
            for item in value.family_progress
        ],
    }


def _action(candidate: RuleCandidate, focal_seat: int) -> dict[str, Any]:
    """编码当前具体鸣牌动作及其规则事实。"""

    action = candidate.action
    if isinstance(action, Chi):
        action_payload = {"kind": "chi", "tiles": _tile_sequence(action.tiles)}
    elif isinstance(action, Peng):
        action_payload = {"kind": "peng", "tiles": [_tile_index(action.tile)]}
    else:
        raise ValueError("AV1 首版只接受合法吃或碰动作")
    return {
        **action_payload,
        "facts": _candidate_facts(candidate.facts),
        "value_facts": _value_facts(candidate.value_facts, focal_seat),
    }


def encode_claim_value_features(
    request: DecisionRequest, claim_action_key: str
) -> dict[str, Any]:
    """生成 AV1 玩家可见动作价值输入。

    输入只来自线上策略本来就能读取的 ``DecisionRequest``。编码不接触
    ``WorldState``、模拟器、未来牌墙、他家暗手、场次/来源根身份或续打
    结果；牌效、合法后继和条件结算只消费 ``HangmaRules`` 已给出的事实。
    输出中的四家向量统一按本人、下家、对家、上家排列。
    """

    by_key = {candidate.action_key: candidate for candidate in request.rules.legal_candidates}
    if "pass" not in by_key:
        raise ValueError("吃碰相对过牌的价值编码要求同窗存在合法 pass")
    try:
        claim = by_key[claim_action_key]
    except KeyError as exc:
        raise ValueError("指定鸣牌动作不属于当前规则合法候选") from exc
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
        "claim": _action(claim, observation.seat),
    }


__all__ = ["SCHEMA", "encode_claim_value_features"]
